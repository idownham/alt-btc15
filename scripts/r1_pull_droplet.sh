#!/usr/bin/env bash
# Pull a logical copy of the droplet's R1 recording to the laptop, without a second copy on the droplet.
#
#   scripts/r1_pull_droplet.sh OUT_DIR
#
# Why not `.backup` + scp (the plan in docs/r1-droplet-move.md): on 2026-11-25 the droplet DB was 20.8 GB with 20 GB
# free, so a backup file on the droplet would have filled its disk under the live recorder. Instead each table is
# streamed over ssh as SQL INSERT statements (gzip -1), read-only (`sqlite3 -readonly`), at nice 19 / idle I/O class,
# in rowid chunks, and rebuilt on the laptop by scripts/r1_load_pull.py. The recorder keeps running throughout.
#
# The snapshot is fixed by the rowid high-water marks read at the start (written to OUT_DIR/marks.txt), so rows the
# recorder adds during the pull are left out. The droplet address comes from DROPLET_HOST in ../project-osprey/.env
# and is never printed.
set -euo pipefail
OUT=${1:?usage: r1_pull_droplet.sh OUT_DIR}
mkdir -p "$OUT"
HERE=$(cd "$(dirname "$0")/.." && pwd)
H=$(grep '^DROPLET_HOST=' "$HERE/../project-osprey/.env" | cut -d= -f2-)
DB=/opt/alt-btc15/data/recorder/book.sqlite
CHUNK=2000000

remote() { ssh -o BatchMode=yes -o ServerAliveInterval=30 "$H" "$@"; }

if [[ ! -s "$OUT/marks.txt" ]]; then
  remote "sqlite3 -readonly $DB \"select 'books', max(rowid) from books; select 'trades', max(rowid) from trades;
    select 'btc', max(rowid) from btc; select 'gaps', max(rowid) from gaps; select 'events', max(rowid) from events;
    select 'windows', max(rowid) from windows;\"" > "$OUT/marks.txt"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/pulled_at_utc.txt"
fi

pull() {  # table lo hi
  local f="$OUT/$1.$2.sql.gz"
  [[ -s "$f" ]] && return 0
  remote "nice -n 19 ionice -c3 sqlite3 -readonly $DB '.mode insert $1' \
    'select * from $1 where rowid between $2 and $3 order by rowid' | gzip -1" > "$f.part"
  mv "$f.part" "$f"
  echo "$(date -u +%H:%M:%S) $1 $2-$3"
}

while IFS='|' read -r table hi; do
  [[ -z "$hi" ]] && continue
  lo=1
  while (( lo <= hi )); do
    end=$(( lo + CHUNK - 1 )); (( end > hi )) && end=$hi
    pull "$table" "$lo" "$end"
    lo=$(( end + 1 ))
  done
done < "$OUT/marks.txt"
echo done > "$OUT/COMPLETE"
