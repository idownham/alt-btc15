"""Pull S1 history into SQLite (data/s1.sqlite, gitignored): windows, Kalshi 1-min candles, Coinbase 1-min BTC.

    .venv/bin/python -m slot.history --start 2026-06-01 --end 2026-10-13

Resumable (windows already holding candles are skipped) and paced: Kalshi requests are spaced
`--pace` seconds apart (default 0.5 s = 2 req/s) because other alt projects share this laptop's IP.

Storage units: Kalshi prices as integer 1/10,000 dollar (e4), sizes 1/100 contract (e2); BTC as integer
cents. Strikes and settlement values as exact decimal TEXT.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from slot.btc import CoinbaseClient
from slot.kalshi import SERIES, KalshiClient, Window, price_e4, size_e2

log = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "s1.sqlite"
BATCH_WINDOWS = 24  # 24 windows x 361 minutes < Kalshi's 10,000-candle batch limit

SCHEMA = """
CREATE TABLE IF NOT EXISTS windows (
    ticker TEXT PRIMARY KEY, open_ts INTEGER NOT NULL, close_ts INTEGER NOT NULL,
    strike TEXT, expiration_value TEXT, result TEXT, era TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kcandles (
    ticker TEXT NOT NULL, end_ts INTEGER NOT NULL,
    yb_o INTEGER, yb_h INTEGER, yb_l INTEGER, yb_c INTEGER,
    ya_o INTEGER, ya_h INTEGER, ya_l INTEGER, ya_c INTEGER,
    p_o INTEGER, p_h INTEGER, p_l INTEGER, p_c INTEGER,
    volume_e2 INTEGER,
    PRIMARY KEY (ticker, end_ts)
);
CREATE TABLE IF NOT EXISTS candles_done (ticker TEXT PRIMARY KEY, n INTEGER NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS btc (start_ts INTEGER PRIMARY KEY, o INTEGER, h INTEGER, l INTEGER, c INTEGER);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def _ts(d: datetime) -> int:
    return int(d.timestamp())


def _e4(block: dict[str, Any] | None, field: str) -> int | None:
    """Candle price field in either API format ('close_dollars' now, 'close' in older history)."""
    if not block:
        return None
    value = block.get(f"{field}_dollars", block.get(field))
    return None if value is None else price_e4(str(value))


def cents(value: Decimal) -> int:
    scaled = value * 100
    if scaled != scaled.to_integral_value():
        raise ValueError(f"BTC price with sub-cent precision: {value}")
    return int(scaled)


def candle_row(ticker: str, c: dict[str, Any]) -> tuple:
    yb, ya, p = c.get("yes_bid"), c.get("yes_ask"), c.get("price")
    vol = c.get("volume_fp", c.get("volume"))
    return (
        ticker, int(c["end_period_ts"]),
        *(_e4(yb, f) for f in ("open", "high", "low", "close")),
        *(_e4(ya, f) for f in ("open", "high", "low", "close")),
        *(_e4(p, f) for f in ("open", "high", "low", "close")),
        None if vol is None else size_e2(str(vol)),
    )


def save_windows(db: sqlite3.Connection, windows: Iterable[Window], era: str) -> int:
    rows = [
        (w.ticker, _ts(w.open_time), _ts(w.close_time), None if w.strike is None else str(w.strike),
         None if w.expiration_value is None else str(w.expiration_value), w.result, era)
        for w in windows
    ]
    db.executemany("INSERT OR REPLACE INTO windows VALUES (?,?,?,?,?,?,?)", rows)
    db.commit()
    return len(rows)


def fetch_windows(db: sqlite3.Connection, k: KalshiClient, start: datetime, end: datetime) -> None:
    cutoff = datetime.fromisoformat(k.historical_cutoff()["market_settled_ts"].replace("Z", "+00:00"))
    # Era decides the candle endpoint: markets settled before the cutoff are only on /historical.
    hist = [w for w in k.historical_windows() if start < w.close_time <= min(end, cutoff)]
    live = [w for w in k.windows(status="settled", min_close_ts=_ts(max(start, cutoff)), max_close_ts=_ts(end))
            if max(start, cutoff) < w.close_time <= end]
    n_hist, n_live = save_windows(db, hist, "hist"), save_windows(db, live, "live")
    log.info("windows: %d historical, %d live (cutoff %s)", n_hist, n_live, cutoff)


def _store_candles(db: sqlite3.Connection, ticker: str, candles: list[dict[str, Any]]) -> None:
    db.executemany(f"INSERT OR REPLACE INTO kcandles VALUES ({','.join('?' * 15)})",
                   [candle_row(ticker, c) for c in candles])
    db.execute("INSERT OR REPLACE INTO candles_done VALUES (?,?,?)",
               (ticker, len(candles), datetime.now(timezone.utc).isoformat()))


def fetch_candles(db: sqlite3.Connection, k: KalshiClient, pace: float) -> None:
    todo = db.execute(
        "SELECT ticker, open_ts, close_ts, era FROM windows WHERE ticker NOT IN (SELECT ticker FROM candles_done)"
        " ORDER BY close_ts").fetchall()
    log.info("candles to fetch: %d windows", len(todo))
    hist = [r for r in todo if r[3] == "hist"]
    live = [r for r in todo if r[3] == "live"]
    for i, (ticker, open_ts, close_ts, _) in enumerate(hist):
        _store_candles(db, ticker, k.historical_candlesticks(ticker, open_ts - 60, close_ts))
        if i % 100 == 0:
            db.commit()
            log.info("historical candles %d/%d (%s), 429s so far %d", i, len(hist), ticker, k.rate_limits.count)
        time.sleep(pace)
    db.commit()
    for batch in _batches(live):
        got = k.batch_candlesticks([r[0] for r in batch], min(r[1] for r in batch) - 60, max(r[2] for r in batch))
        for ticker, open_ts, close_ts, _ in batch:
            own = [c for c in got.get(ticker, []) if open_ts - 60 < int(c["end_period_ts"]) <= close_ts]
            _store_candles(db, ticker, own)
        db.commit()
        log.info("live candles through %s", batch[-1][0])
        time.sleep(pace)


def _batches(rows: list[tuple]) -> Iterable[list[tuple]]:
    """Group windows so markets x minutes spanned stays under Kalshi's 10,000-candle batch limit."""
    batch: list[tuple] = []
    for row in rows:
        trial = batch + [row]
        span_min = (max(r[2] for r in trial) - min(r[1] for r in trial)) // 60 + 1
        if batch and (len(trial) > BATCH_WINDOWS or len(trial) * span_min > 9000):
            yield batch
            trial = [row]
        batch = trial
    if batch:
        yield batch


def fetch_btc(db: sqlite3.Connection, cb: CoinbaseClient, start: datetime, end: datetime) -> None:
    have = db.execute("SELECT MAX(start_ts) FROM btc").fetchone()[0]
    begin = max(start, datetime.fromtimestamp(have + 60, tz=timezone.utc)) if have else start
    rows = []
    for c in cb.candles(begin, end):
        rows.append((_ts(c.start), *(cents(v) for v in (c.open, c.high, c.low, c.close))))
        if len(rows) >= 5000:
            db.executemany("INSERT OR REPLACE INTO btc VALUES (?,?,?,?,?)", rows)
            db.commit()
            log.info("btc through %s", c.start)
            rows = []
    db.executemany("INSERT OR REPLACE INTO btc VALUES (?,?,?,?,?)", rows)
    db.commit()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat, required=True, help="windows closing after this UTC date")
    p.add_argument("--end", type=date.fromisoformat, required=True, help="windows closing up to this UTC date")
    p.add_argument("--pace", type=float, default=0.5)
    p.add_argument("--db", type=Path, default=DB_PATH)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    start = datetime.combine(args.start, datetime.min.time(), timezone.utc)
    end = datetime.combine(args.end, datetime.min.time(), timezone.utc)
    db = connect(args.db)
    with KalshiClient() as k, CoinbaseClient() as cb:
        # BTC needs 60 min of lookback before the first window opens.
        fetch_btc(db, cb, start - timedelta(minutes=90), end)
        if not db.execute("SELECT COUNT(*) FROM windows").fetchone()[0]:
            fetch_windows(db, k, start, end)
        fetch_candles(db, k, args.pace)
    log.info("done; series %s", SERIES)


if __name__ == "__main__":
    main()
