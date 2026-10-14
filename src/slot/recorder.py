"""R1 recorder: live KXBTC15M order book, trade tape and BTC price, read-only (decisions.md 2026-10-14).

    .venv/bin/python -m slot.recorder            # run (Ctrl-C to stop)
    .venv/bin/python -m slot.recorder status     # data health: rows, last snapshot, gaps

Every `interval` seconds (default 1 s):
- one GET /markets/orderbooks for the window trading now: top `DEPTH` levels per side, with
  send/receive timestamps;
- one Coinbase BTC-USD ticker (a different host, so not counted against Kalshi).
Every `TRADES_EVERY` seconds: the window's new trades (deduplicated by trade_id). At each window change:
a final trade sweep for the old window, and later its settlement result.

Kalshi load is about 1.1-1.3 requests/s, against a Basic limit of ~20/s shared with Coin Toss's recorder.
On any 429 the recorder pauses `BACKOFF_429` seconds, so it gives way instead of competing. Gaps longer
than `GAP_SECONDS` (laptop sleep, network loss) are written to the `gaps` table. Errors are logged and
the loop continues.

This module holds no keys and cannot place orders. Prices are integer e4 (1/10,000 $), sizes e2
(1/100 contract), BTC in integer cents.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from slot.btc import CoinbaseClient
from slot.history import cents
from slot.kalshi import Book, KalshiClient, Level, Window, price_e4, size_e2

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "recorder" / "book.sqlite"
DEPTH = 20  # levels kept per side; a <= $5 order never reaches past the top few
TRADES_EVERY = 10.0
RESULT_DELAY = 60.0  # read a closed window's result this long after close (settlement takes ~5 s)
GAP_SECONDS = 5.0
BACKOFF_429 = 10.0

SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS windows (
    ticker TEXT PRIMARY KEY, open_ts INTEGER NOT NULL, close_ts INTEGER NOT NULL,
    strike TEXT, result TEXT, expiration_value TEXT, first_seen_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
    ticker TEXT NOT NULL, t_send_ns INTEGER NOT NULL, t_recv_ns INTEGER NOT NULL,
    yes_bids TEXT NOT NULL, no_bids TEXT NOT NULL,  -- "price_e4:size_e2,..." best first, top DEPTH
    yes_levels INTEGER NOT NULL, no_levels INTEGER NOT NULL  -- full depth level counts
);
CREATE INDEX IF NOT EXISTS books_ticker_t ON books (ticker, t_recv_ns);
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, created_time TEXT NOT NULL,
    yes_price_e4 INTEGER NOT NULL, count_e2 INTEGER NOT NULL, taker_side TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS trades_ticker_t ON trades (ticker, created_time);
CREATE TABLE IF NOT EXISTS btc (
    t_recv_ns INTEGER NOT NULL, exch_time TEXT NOT NULL, price_c INTEGER NOT NULL, bid_c INTEGER NOT NULL,
    ask_c INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS gaps (start_ns INTEGER NOT NULL, end_ns INTEGER NOT NULL, seconds REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (t_ns INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
"""


def levels_text(levels: list[Level]) -> str:
    return ",".join(f"{lvl.price_e4}:{lvl.size_e2}" for lvl in levels[:DEPTH])


def parse_levels_text(text: str) -> list[Level]:
    return [Level(*map(int, item.split(":"))) for item in text.split(",") if item]


class Store:
    def __init__(self, path: Path | str = DB_PATH) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def window(self, w: Window, t_ns: int) -> None:
        self.db.execute(
            "INSERT INTO windows VALUES (?,?,?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET "
            "strike=COALESCE(excluded.strike, strike), result=COALESCE(NULLIF(excluded.result,''), result), "
            "expiration_value=COALESCE(excluded.expiration_value, expiration_value)",
            (w.ticker, int(w.open_time.timestamp()), int(w.close_time.timestamp()),
             None if w.strike is None else str(w.strike), w.result or None,
             None if w.expiration_value is None else str(w.expiration_value), t_ns))

    def book(self, b: Book, t_send: int, t_recv: int) -> None:
        self.db.execute("INSERT INTO books VALUES (?,?,?,?,?,?,?)",
                        (b.ticker, t_send, t_recv, levels_text(b.yes_bids), levels_text(b.no_bids),
                         len(b.yes_bids), len(b.no_bids)))

    def trades(self, rows: list[dict[str, Any]]) -> int:
        before = self.db.total_changes
        self.db.executemany(
            "INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?)",
            [(t["trade_id"], t["ticker"], t["created_time"], price_e4(t["yes_price_dollars"]),
              size_e2(t["count_fp"]), t["taker_side"]) for t in rows])
        return self.db.total_changes - before

    def btc(self, t_recv: int, tick: Any) -> None:
        self.db.execute("INSERT INTO btc VALUES (?,?,?,?,?)",
                        (t_recv, tick.time.isoformat(), cents(tick.price), cents(tick.bid), cents(tick.ask)))

    def gap(self, start_ns: int, end_ns: int) -> None:
        self.db.execute("INSERT INTO gaps VALUES (?,?,?)", (start_ns, end_ns, (end_ns - start_ns) / 1e9))

    def event(self, t_ns: int, kind: str, detail: str) -> None:
        self.db.execute("INSERT INTO events VALUES (?,?,?)", (t_ns, kind, detail[:500]))

    def commit(self) -> None:
        self.db.commit()


class Recorder:
    def __init__(
        self,
        kalshi: KalshiClient,
        coinbase: CoinbaseClient,
        store: Store,
        interval: float = 1.0,
        clock: Callable[[], int] = time.time_ns,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.k, self.cb, self.store = kalshi, coinbase, store
        self.interval = interval
        self.clock, self.sleep = clock, sleep
        self.current: Window | None = None
        self.last_tick_ns: int | None = None
        self.next_trades_ns = 0
        self.trade_cursor: dict[str, int] = {}  # ticker -> min_ts (s) for the next trade fetch
        self.pending_results: dict[str, int] = {}  # ticker -> time (ns) to read its result
        self.seen_429 = 0

    # --- one loop iteration --------------------------------------------------------------------
    def tick(self) -> None:
        now = self.clock()
        if self.last_tick_ns is not None and (now - self.last_tick_ns) / 1e9 > GAP_SECONDS:
            self.store.gap(self.last_tick_ns, now)
            log.warning("gap of %.0f s (sleep or network)", (now - self.last_tick_ns) / 1e9)
        self.last_tick_ns = now
        self._step("window", self._ensure_window, now)
        if self.current is not None and now / 1e9 < self.current.close_time.timestamp():
            self._step("book", self._record_book)
            if now >= self.next_trades_ns:
                self._step("trades", self._record_trades, self.current.ticker)
                self.next_trades_ns = now + int(TRADES_EVERY * 1e9)
        self._step("btc", self._record_btc)
        for ticker, due in list(self.pending_results.items()):
            if now >= due:
                self._step("result", self._record_result, ticker)
        self.store.commit()

    def _step(self, name: str, fn: Callable[..., None], *args: Any) -> None:
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001 - a recorder must keep running; every error is logged
            self.store.event(self.clock(), f"error:{name}", f"{type(exc).__name__}: {exc}")
            log.warning("%s failed: %s", name, exc)

    def _ensure_window(self, now: int) -> None:
        now_s = now / 1e9
        if self.current is not None and now_s < self.current.close_time.timestamp():
            return
        w = self.k.current_window()
        if w is None or not (w.open_time.timestamp() <= now_s < w.close_time.timestamp()):
            return  # between windows for a moment; try next tick
        if self.current is not None and w.ticker != self.current.ticker:
            old = self.current.ticker
            self._record_trades(old)  # final sweep of the closed window's tape
            self.pending_results[old] = now + int(RESULT_DELAY * 1e9)
        if self.current is None or w.ticker != self.current.ticker:
            self.current = w
            self.store.window(w, now)
            self.trade_cursor.setdefault(w.ticker, int(w.open_time.timestamp()) - 1)
            self.next_trades_ns = 0
            log.info("recording %s (strike %s)", w.ticker, w.strike)

    def _record_book(self) -> None:
        assert self.current is not None
        t_send = self.clock()
        book = self.k.orderbook(self.current.ticker)
        t_recv = self.clock()
        if book is not None:
            self.store.book(book, t_send, t_recv)

    def _record_trades(self, ticker: str) -> None:
        since = self.trade_cursor.get(ticker)
        rows = list(self.k.trades(ticker, min_ts=since))
        added = self.store.trades(rows)
        if rows:
            newest = max(datetime.fromisoformat(r["created_time"].replace("Z", "+00:00")) for r in rows)
            self.trade_cursor[ticker] = int(newest.timestamp()) - 1  # 1 s overlap; trade_id dedupes
        log.debug("%s: %d trades fetched, %d new", ticker, len(rows), added)

    def _record_btc(self) -> None:
        tick = self.cb.ticker()
        self.store.btc(self.clock(), tick)

    def _record_result(self, ticker: str) -> None:
        w = self.k.window(ticker)
        if w.result:
            self.store.window(w, self.clock())
            del self.pending_results[ticker]
            self.trade_cursor.pop(ticker, None)
            log.info("%s settled %s at %s", ticker, w.result, w.expiration_value)
        else:
            self.pending_results[ticker] = self.clock() + int(RESULT_DELAY * 1e9)

    # --- loop ----------------------------------------------------------------------------------
    def run(self, max_ticks: int | None = None) -> None:
        self.store.event(self.clock(), "start", f"interval={self.interval}s depth={DEPTH}")
        self.store.commit()
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            started = self.clock()
            self.tick()
            ticks += 1
            if self.k.rate_limits.count > self.seen_429:
                self.store.event(self.clock(), "rate_limited", f"total 429s {self.k.rate_limits.count}")
                self.store.commit()
                self.seen_429 = self.k.rate_limits.count
                self.sleep(BACKOFF_429)
                continue
            elapsed = (self.clock() - started) / 1e9
            self.sleep(max(0.0, self.interval - elapsed))


def status(store: Store) -> str:
    q = lambda sql: store.db.execute(sql).fetchone()  # noqa: E731
    now = time.time_ns()
    lines = []
    for table in ("windows", "books", "trades", "btc", "gaps"):
        lines.append(f"{table:8} {q(f'SELECT COUNT(*) FROM {table}')[0]:>10,}")
    last_book = q("SELECT MAX(t_recv_ns) FROM books")[0]
    lines.append("last book: " + ("none" if not last_book else f"{(now - last_book) / 1e9:.0f} s ago"))
    day = now - 86_400 * 10**9
    n_gaps, gap_s = q(f"SELECT COUNT(*), COALESCE(SUM(seconds), 0) FROM gaps WHERE end_ns > {day}")
    lines.append(f"gaps (24 h): {n_gaps}, {gap_s / 60:.1f} min total")
    n_err = q(f"SELECT COUNT(*) FROM events WHERE kind LIKE 'error:%' AND t_ns > {day}")[0]
    n_429 = q(f"SELECT COUNT(*) FROM events WHERE kind = 'rate_limited' AND t_ns > {day}")[0]
    lines.append(f"errors (24 h): {n_err}; rate-limit pauses (24 h): {n_429}")
    settled = q("SELECT COUNT(*) FROM windows WHERE result IS NOT NULL")[0]
    lines.append(f"windows with result: {settled}")
    return "\n".join(lines)


def _stop(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", nargs="?", default="run", choices=["run", "status"])
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--db", type=Path, default=DB_PATH)
    args = p.parse_args()
    store = Store(args.db)
    if args.command == "status":
        print(status(store))
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    signal.signal(signal.SIGTERM, _stop)  # launchd and `kill` send SIGTERM; treat it like Ctrl-C
    with KalshiClient(max_retries=0) as k, CoinbaseClient(max_retries=0) as cb:
        try:
            Recorder(k, cb, store, interval=args.interval).run()
        except KeyboardInterrupt:
            store.event(time.time_ns(), "stop", "signal")
            store.commit()
            log.info("stopped")


if __name__ == "__main__":
    main()
