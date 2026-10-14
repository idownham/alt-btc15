from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import httpx
import pytest

from slot.btc import Tick
from slot.http import RateLimitCounter
from slot.kalshi import Window, parse_book
from slot.recorder import DEPTH, Recorder, Store, levels_text, parse_levels_text, status

T0 = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
BOOK_FP = {"no_dollars": [["0.4800", "100.00"], ["0.4700", "50.00"]],
           "yes_dollars": [["0.5000", "80.00"], ["0.5100", "20.50"]]}


def win(i: int, result: str = "") -> Window:
    o = T0 + timedelta(minutes=15 * i)
    return Window(f"KXBTC15M-W{i}", o, o + timedelta(minutes=15), "active" if not result else "finalized",
                  D("83000.00"), D("83010.00") if result else None, result, "tapered_deci_cent", {})


def trade(tid: str, ticker: str, t: datetime) -> dict:
    return {"trade_id": tid, "ticker": ticker, "created_time": t.isoformat().replace("+00:00", "Z"),
            "yes_price_dollars": "0.5100", "count_fp": "3.00", "taker_side": "yes"}


class Clock:
    def __init__(self, t: datetime) -> None:
        self.ns = int(t.timestamp() * 1e9)

    def __call__(self) -> int:
        return self.ns

    def advance(self, s: float) -> None:
        self.ns += int(s * 1e9)


class FakeKalshi:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.rate_limits = RateLimitCounter()
        self.calls: list[tuple] = []
        self.tape: dict[str, list[dict]] = {}
        self.fail_book = False
        self.settled: set[str] = set()

    def _i(self) -> int:
        return int((self.clock() / 1e9 - T0.timestamp()) // 900)

    def current_window(self):
        self.calls.append(("current",))
        return win(self._i())

    def orderbook(self, ticker):
        self.calls.append(("book", ticker))
        if self.fail_book:
            raise httpx.ConnectError("offline")
        return parse_book(ticker, BOOK_FP)

    def trades(self, ticker, min_ts=None, max_ts=None):
        self.calls.append(("trades", ticker, min_ts))
        ts = lambda t: datetime.fromisoformat(t["created_time"].replace("Z", "+00:00")).timestamp()  # noqa: E731
        return iter([t for t in self.tape.get(ticker, [])
                     if (min_ts is None or ts(t) >= min_ts) and (max_ts is None or ts(t) <= max_ts)])

    def window(self, ticker):
        self.calls.append(("window", ticker))
        i = int(ticker.removeprefix("KXBTC15M-W"))
        return win(i, "yes" if ticker in self.settled else "")


class FakeCoinbase:
    def ticker(self):
        return Tick(T0, D("83001.25"), D("83001.24"), D("83001.25"))


@pytest.fixture
def setup():
    clock = Clock(T0 + timedelta(seconds=30))
    k = FakeKalshi(clock)
    store = Store(":memory:")
    rec = Recorder(k, FakeCoinbase(), store, clock=clock, sleep=lambda s: None)
    return clock, k, store, rec


def count(store, table):
    return store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_levels_round_trip_and_depth_cap():
    book = parse_book("T", BOOK_FP)
    assert parse_levels_text(levels_text(book.yes_bids)) == book.yes_bids
    many = parse_book("T", {"yes_dollars": [[f"0.{i:02d}00", "1.00"] for i in range(1, 60)], "no_dollars": []})
    assert len(parse_levels_text(levels_text(many.yes_bids))) == DEPTH


def test_one_book_and_one_btc_per_tick_and_no_order_calls(setup):
    clock, k, store, rec = setup
    for _ in range(5):
        rec.tick()
        clock.advance(1)
    assert count(store, "books") == 5 and count(store, "btc") == 5
    assert {c[0] for c in k.calls} <= {"current", "book", "trades", "window"}  # read-only endpoints only
    assert sum(c[0] == "current" for c in k.calls) == 1  # window looked up once, not every tick


def test_trades_are_polled_every_10_s_and_deduplicated(setup):
    clock, k, store, rec = setup
    k.tape["KXBTC15M-W0"] = [trade("a", "KXBTC15M-W0", T0 + timedelta(seconds=5))]
    for _ in range(25):
        rec.tick()
        clock.advance(1)
    assert sum(c[0] == "trades" for c in k.calls) == 3  # at 30, 40 and 50 s into the window
    assert count(store, "trades") == 1


def trade_calls(k):
    return [c for c in k.calls if c[0] == "trades"]


def test_catch_up_is_one_chunk_per_tick_oldest_first(setup):
    clock, k, store, rec = setup
    clock.advance(570)  # recorder starts 10 minutes into the window: 600 s of tape to catch up
    for _ in range(12):
        rec.tick()
        clock.advance(1)
    starts = [c[2] for c in trade_calls(k)]
    assert starts == sorted(starts) and len(starts) == 10  # 10 one-minute slices; the 10-s cadence resumes after
    assert all(b - a == 60 for a, b in zip(starts[:10], starts[1:10]))


def test_restart_resumes_tape_from_newest_stored_trade(setup):
    clock, k, store, rec = setup
    k.tape["KXBTC15M-W0"] = [trade("a", "KXBTC15M-W0", T0 + timedelta(seconds=25))]
    rec.tick()
    clock.advance(5)
    fresh = Recorder(k, FakeCoinbase(), store, clock=clock, sleep=lambda s: None)
    k.calls.clear()
    fresh.tick()
    assert trade_calls(k)[0][2] == int((T0 + timedelta(seconds=25)).timestamp())


def test_window_roll_sweeps_old_tape_then_reads_result(setup):
    clock, k, store, rec = setup
    rec.tick()
    clock.advance(900)  # into window 1
    k.tape["KXBTC15M-W0"] = [trade("late", "KXBTC15M-W0", T0 + timedelta(seconds=899))]
    for _ in range(16):  # the old window's remaining tape, one 60-s slice per tick
        rec.tick()
        clock.advance(1)
    assert rec.current.ticker == "KXBTC15M-W1" and not rec.sweeping
    assert store.db.execute("SELECT COUNT(*) FROM trades WHERE trade_id='late'").fetchone()[0] == 1
    k.settled.add("KXBTC15M-W0")
    clock.advance(61)
    rec.tick()
    assert store.db.execute("SELECT result FROM windows WHERE ticker='KXBTC15M-W0'").fetchone()[0] == "yes"
    assert "KXBTC15M-W0" not in rec.pending_results


def test_unsettled_result_is_retried_later(setup):
    clock, k, store, rec = setup
    rec.tick()
    clock.advance(900)
    rec.tick()
    clock.advance(61)
    rec.tick()  # not settled yet
    assert "KXBTC15M-W0" in rec.pending_results


def test_no_book_after_close_until_next_window_found(setup):
    clock, k, store, rec = setup
    rec.tick()
    k.current_window = lambda: None  # between windows
    clock.advance(900)
    rec.tick()
    assert count(store, "books") == 1


def test_gap_is_logged_after_sleep(setup):
    clock, k, store, rec = setup
    rec.tick()
    clock.advance(120)  # laptop asleep
    rec.tick()
    assert store.db.execute("SELECT seconds FROM gaps").fetchone()[0] == pytest.approx(120)


def test_errors_are_logged_and_loop_continues(setup):
    clock, k, store, rec = setup
    k.fail_book = True
    rec.tick()
    assert count(store, "btc") == 1
    assert store.db.execute("SELECT kind FROM events").fetchone()[0] == "error:book"


def test_rate_limit_pauses_the_loop(setup):
    clock, k, store, rec = setup
    sleeps = []
    rec.sleep = sleeps.append
    original = k.orderbook

    def limited(ticker):
        k.rate_limits.count += 1
        raise httpx.HTTPStatusError("429", request=None, response=None)  # type: ignore[arg-type]

    k.orderbook = limited
    rec.run(max_ticks=1)
    assert sleeps == [10.0]
    k.orderbook = original
    assert "rate-limit pauses (24 h)" in status(store)


def test_restart_gap_is_logged_from_last_stored_snapshot(setup):
    clock, k, store, rec = setup
    rec.tick()
    clock.advance(300)  # process stopped for 5 minutes, then a fresh Recorder starts on the same store
    fresh = Recorder(k, FakeCoinbase(), store, clock=clock, sleep=lambda s: None)
    fresh.run(max_ticks=1)
    assert store.db.execute("SELECT seconds FROM gaps").fetchone()[0] == pytest.approx(300)
