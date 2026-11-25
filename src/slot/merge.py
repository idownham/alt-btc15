"""Build the R1 analysis DB from the laptop and droplet recordings (docs/r1-droplet-move.md, "Bringing the data together").

    .venv/bin/python -m slot.merge LAPTOP_DB DROPLET_DB OUT_DB [--report docs/r1-merge-report.json]

Rules, as written in the move plan (cutover T = 2026-11-09 04:45:00 UTC, decisions.md 2026-11-08):
- `books` and `btc`: laptop rows before T, droplet rows from T. T is a window boundary, so no window's book mixes hosts.
- `trades`: the union, deduplicated on `trade_id`. Where both hosts recorded a window's tape, the trade_id sets are
  compared and the result goes in the report (the overlap window must match).
- `windows`: the union. A result (or strike) recorded by either host fills a missing one; conflicting values are
  reported and make the merge fail.
- `gaps` and `events`: kept per host, with a `host` column added.

Inputs are opened read-only (immutable). Nothing is looked at beyond counts and identity checks: no prices or results
are analysed here. An extra index on btc(t_recv_ns) is added to the output for speed; it changes no data.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from slot.recorder import SCHEMA

T_CUTOVER = int(datetime(2026, 11, 9, 4, 45, tzinfo=timezone.utc).timestamp())
NS = 1_000_000_000
HOSTS = ("laptop", "droplet")

OUT_SCHEMA = SCHEMA.replace("PRAGMA journal_mode = WAL;", "").replace(
    "CREATE TABLE IF NOT EXISTS gaps (start_ns INTEGER NOT NULL, end_ns INTEGER NOT NULL, seconds REAL NOT NULL);",
    "CREATE TABLE IF NOT EXISTS gaps (start_ns INTEGER NOT NULL, end_ns INTEGER NOT NULL, seconds REAL NOT NULL, "
    "host TEXT NOT NULL);").replace(
    "CREATE TABLE IF NOT EXISTS events (t_ns INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);",
    "CREATE TABLE IF NOT EXISTS events (t_ns INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL, "
    "host TEXT NOT NULL);")


class MergeError(RuntimeError):
    pass


def _uri(path: Path) -> str:
    return f"file:{path.resolve()}?immutable=1"


def merge(laptop: Path, droplet: Path, out: Path, t_cutover: int = T_CUTOVER) -> dict:
    if t_cutover % 900:
        raise MergeError("the cutover must be a window boundary")
    if out.exists():
        raise MergeError(f"{out} exists; the merge writes a fresh DB")
    t_ns = t_cutover * NS
    db = sqlite3.connect(f"file:{out.resolve()}", uri=True)
    db.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF; PRAGMA cache_size = -2000000;")
    db.executescript(OUT_SCHEMA)
    db.execute("ATTACH DATABASE ? AS l", (_uri(laptop),))
    db.execute("ATTACH DATABASE ? AS d", (_uri(droplet),))
    rep: dict = {"t_cutover_utc": datetime.fromtimestamp(t_cutover, tz=timezone.utc).isoformat(),
                 "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    q = lambda sql, *a: db.execute(sql, a).fetchone()[0]  # noqa: E731

    # windows: union; fill missing strike/result/expiration_value from the other host; conflicts fail the merge.
    conflicts = db.execute(
        "SELECT l.ticker FROM l.windows l JOIN d.windows d USING (ticker) WHERE "
        "(l.result IS NOT NULL AND d.result IS NOT NULL AND l.result != d.result) OR "
        "(l.strike IS NOT NULL AND d.strike IS NOT NULL AND l.strike != d.strike) OR "
        "l.open_ts != d.open_ts OR l.close_ts != d.close_ts").fetchall()
    if conflicts:
        raise MergeError(f"windows conflict between hosts: {[c[0] for c in conflicts][:10]}")
    db.execute("INSERT INTO windows SELECT * FROM l.windows")
    db.execute("INSERT INTO windows SELECT * FROM d.windows WHERE true ON CONFLICT(ticker) DO UPDATE SET "
               "strike = COALESCE(strike, excluded.strike), result = COALESCE(result, excluded.result), "
               "expiration_value = COALESCE(expiration_value, excluded.expiration_value), "
               "first_seen_ns = MIN(first_seen_ns, excluded.first_seen_ns)")
    rep["windows"] = {"laptop": q("SELECT COUNT(*) FROM l.windows"), "droplet": q("SELECT COUNT(*) FROM d.windows"),
                      "merged": q("SELECT COUNT(*) FROM windows"),
                      "results_filled_from_droplet": q(
                          "SELECT COUNT(*) FROM l.windows l JOIN d.windows d USING (ticker) "
                          "WHERE l.result IS NULL AND d.result IS NOT NULL"),
                      "results_filled_from_laptop": q(
                          "SELECT COUNT(*) FROM l.windows l JOIN d.windows d USING (ticker) "
                          "WHERE d.result IS NULL AND l.result IS NOT NULL")}

    # books and btc: by host, split at T.
    for table in ("books", "btc"):
        db.execute(f"INSERT INTO {table} SELECT * FROM l.{table} WHERE t_recv_ns < ? ORDER BY rowid", (t_ns,))
        db.execute(f"INSERT INTO {table} SELECT * FROM d.{table} WHERE t_recv_ns >= ? ORDER BY rowid", (t_ns,))
        rep[table] = {"laptop_kept": q(f"SELECT COUNT(*) FROM l.{table} WHERE t_recv_ns < ?", t_ns),
                      "laptop_dropped_from_T": q(f"SELECT COUNT(*) FROM l.{table} WHERE t_recv_ns >= ?", t_ns),
                      "droplet_kept": q(f"SELECT COUNT(*) FROM d.{table} WHERE t_recv_ns >= ?", t_ns),
                      "droplet_dropped_before_T": q(f"SELECT COUNT(*) FROM d.{table} WHERE t_recv_ns < ?", t_ns),
                      "merged": q(f"SELECT COUNT(*) FROM {table}")}
    db.execute("CREATE INDEX IF NOT EXISTS btc_t ON btc (t_recv_ns)")

    # trades: union on trade_id, laptop first; then compare the tapes of every window both hosts recorded.
    db.execute("INSERT OR IGNORE INTO trades SELECT * FROM l.trades ORDER BY rowid")
    db.commit()
    shared = [r[0] for r in db.execute("SELECT DISTINCT ticker FROM d.trades WHERE ticker IN "
                                       "(SELECT ticker FROM windows WHERE open_ts < ?)", (t_cutover + 900,))]
    overlap = {}
    for ticker in shared:
        lt = {r[0]: r[1:] for r in db.execute("SELECT trade_id, created_time, yes_price_e4, count_e2, taker_side "
                                              "FROM l.trades WHERE ticker = ?", (ticker,))}
        dt = {r[0]: r[1:] for r in db.execute("SELECT trade_id, created_time, yes_price_e4, count_e2, taker_side "
                                              "FROM d.trades WHERE ticker = ?", (ticker,))}
        if not lt:
            continue
        both = lt.keys() & dt.keys()
        overlap[ticker] = {"both": len(both), "laptop_only": len(lt.keys() - dt.keys()),
                           "droplet_only": len(dt.keys() - lt.keys()),
                           "field_mismatch": sum(lt[k] != dt[k] for k in both)}
    mismatched = [t for t, o in overlap.items() if o["field_mismatch"]]
    if mismatched:
        raise MergeError(f"same trade_id, different fields: {mismatched}")
    first_droplet = db.execute("SELECT ticker FROM windows WHERE open_ts = ?", (t_cutover,)).fetchone()
    db.execute("INSERT OR IGNORE INTO trades SELECT * FROM d.trades ORDER BY rowid")
    rep["trades"] = {"laptop": q("SELECT COUNT(*) FROM l.trades"), "droplet": q("SELECT COUNT(*) FROM d.trades"),
                     "merged": q("SELECT COUNT(*) FROM trades"), "windows_on_both_tapes": overlap,
                     "cutover_window": first_droplet[0] if first_droplet else None}
    if first_droplet and first_droplet[0] in overlap:
        o = overlap[first_droplet[0]]
        rep["trades"]["cutover_window_tapes_match"] = o["laptop_only"] == 0 and o["droplet_only"] == 0

    # gaps and events: per host.
    for host, alias in zip(HOSTS, ("l", "d")):
        db.execute(f"INSERT INTO gaps SELECT start_ns, end_ns, seconds, ? FROM {alias}.gaps", (host,))
        db.execute(f"INSERT INTO events SELECT t_ns, kind, detail, ? FROM {alias}.events", (host,))
    rep["gaps"] = {h: q("SELECT COUNT(*) FROM gaps WHERE host = ?", h) for h in HOSTS}
    rep["gaps"]["laptop_ending_after_T"] = q("SELECT COUNT(*) FROM gaps WHERE host='laptop' AND end_ns > ?", t_ns)
    rep["gaps"]["droplet_starting_before_T"] = q("SELECT COUNT(*) FROM gaps WHERE host='droplet' AND start_ns < ?",
                                                 t_ns)
    rep["events"] = {h: q("SELECT COUNT(*) FROM events WHERE host = ?", h) for h in HOSTS}
    rep["events"]["laptop_trade_errors_from_T"] = q(
        "SELECT COUNT(*) FROM events WHERE host='laptop' AND kind='error:trades' AND t_ns >= ?", t_ns)
    db.commit()
    db.execute("DETACH DATABASE l")
    db.execute("DETACH DATABASE d")
    db.close()
    return rep


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("laptop", type=Path)
    p.add_argument("droplet", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    rep = merge(a.laptop, a.droplet, a.out)
    text = json.dumps(rep, indent=2)
    print(text)
    if a.report:
        a.report.write_text(text + "\n")


if __name__ == "__main__":
    main()
