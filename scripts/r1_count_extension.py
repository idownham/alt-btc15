"""Usable-window counts for each candidate end date (pre-registration §1 extension rule). Counts only: no prices,
fills or P&L are computed or shown.

    .venv/bin/python scripts/r1_count_extension.py MERGED_DB [OUT_JSON]

Uses the engine's own `slot.maker.unusable_reason` on every window from the pre-registered start, then reports, for
the pre-registered end (2026-10-28 05:00 UTC = midnight Chicago) and each whole day after it, the number of usable
windows and the failures by reason. Candidate ends are Chicago midnights, like the original end (so 06:00 UTC after
DST ends on 2026-11-01). The first end with >= 900 usable windows is the extension the rule asks for.
"""

import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from slot import maker

CHICAGO = ZoneInfo("America/Chicago")


def main() -> None:
    db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    gaps = db.execute("SELECT start_ns, end_ns FROM gaps").fetchall()
    errs = [t for (t,) in db.execute("SELECT t_ns FROM events WHERE kind = 'error:trades'")]
    last_close = db.execute("SELECT MAX(close_ts) FROM windows WHERE result IS NOT NULL").fetchone()[0]
    reasons = []  # (close_ts, reason)
    for row in maker.windows_in_range(db, last_close):
        reasons.append((row[2], maker.unusable_reason(maker.load_window(db, row), gaps, errs) or "usable"))
    out, chosen = [], None
    day = datetime.fromtimestamp(maker.END_CLOSE_TS, tz=CHICAGO).date()
    while True:
        end = int(datetime(day.year, day.month, day.day, tzinfo=CHICAGO).timestamp())
        if end > last_close:
            break
        c = Counter(r for close, r in reasons if close <= end)
        row = {"end_close_utc": datetime.fromtimestamp(end, tz=timezone.utc).isoformat(), "end_close_ts": end,
               "windows": sum(c.values()), "usable": c["usable"],
               "by_reason": {k: v for k, v in sorted(c.items()) if k != "usable"}}
        out.append(row)
        print(f"{row['end_close_utc']}  windows {row['windows']:5d}  usable {row['usable']:5d}  {row['by_reason']}")
        if chosen is None and c["usable"] >= maker.MIN_USABLE:
            chosen = row
        day += timedelta(days=1)
    print("first end with >= 900 usable:", chosen and chosen["end_close_utc"])
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w") as f:
            json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "first_end_with_900": chosen, "by_end": out}, f, indent=2)
            f.write("\n")


if __name__ == "__main__":
    main()
