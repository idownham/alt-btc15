"""Rebuild the droplet DB on the laptop from the chunks written by scripts/r1_pull_droplet.sh.

    .venv/bin/python scripts/r1_load_pull.py PULL_DIR OUT_DB

Each chunk (`<table>.<first rowid>.sql.gz`, INSERT statements from `sqlite3 .mode insert`) is applied in its own
transaction, in rowid order, into the recorder's schema. Row counts are then checked against the rowid
high-water marks in PULL_DIR/marks.txt (the recorder never deletes rows, so count == max rowid).
"""

import gzip
import sqlite3
import sys
from pathlib import Path

from slot.recorder import SCHEMA


def main() -> None:
    pull, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not (pull / "COMPLETE").exists():
        sys.exit("pull not complete")
    if out.exists():
        sys.exit(f"{out} exists")
    marks = dict(line.split("|") for line in (pull / "marks.txt").read_text().split())
    db = sqlite3.connect(out)
    db.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF; PRAGMA cache_size = -2000000;")
    db.executescript(SCHEMA.replace("PRAGMA journal_mode = WAL;", ""))
    db.execute("PRAGMA journal_mode = DELETE")
    for table in marks:
        chunks = sorted(pull.glob(f"{table}.*.sql.gz"), key=lambda p: int(p.name.split(".")[1]))
        for c in chunks:
            with gzip.open(c, "rt") as f:
                db.executescript("BEGIN;" + f.read() + "COMMIT;")
            print(c.name, flush=True)
    bad = []
    for table, hi in marks.items():
        n = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {n} rows (mark {hi})")
        if n != int(hi):
            bad.append(table)
    db.close()
    if bad:
        sys.exit(f"row counts differ from the marks: {bad}")


if __name__ == "__main__":
    main()
