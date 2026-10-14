"""Maker engine tests, on synthetic data only (the real recording is off-limits until 2026-10-28)."""

import json
import sqlite3
from dataclasses import replace

import pytest

from slot import maker
from slot.maker import (
    BASE, NS, Mode, RestingOrder, Snap, Variant, WinData, advance, simulate, unusable_reason,
)
from slot.recorder import Store

OPEN = maker.START_OPEN_TS + 900 * 4
CLOSE = OPEN + 900
STRIKE = 80_000.0


def ns(sec_from_open: float) -> int:
    return int((OPEN + sec_from_open) * NS)


def book(yes=((4800, 1000_00),), no=((5000, 1000_00),)) -> tuple:
    return [tuple(x) for x in yes], [tuple(x) for x in no]


def mk(hits_yes=(), hits_no=(), yes_won=True, levels=None, btc_above=0.0, snaps=None) -> WinData:
    """A window with a 1-per-second constant book (YES bid 48c, NO bid 50c -> YES ask 50c, 2c spread)."""
    yes, no = levels or book()
    snaps = snaps or [Snap(ns(s), list(yes), list(no)) for s in range(0, 900)]
    btc_t, btc_c = [], []
    for s in range(-16 * 60 - 10, 900):
        btc_t.append(ns(s))
        wiggle = 300 if s % 120 < 60 else -300  # sigma > 0
        btc_c.append(int((STRIKE + btc_above) * 100) + wiggle)
    hy = sorted((ns(t), p, c) for t, p, c in hits_yes)
    hn = sorted((ns(t), p, c) for t, p, c in hits_no)
    return WinData("KXBTC15M-SYN", OPEN, CLOSE, STRIKE, yes_won, snaps, [s.t_ns for s in snaps],
                   {"yes": hy, "no": hn}, {"yes": [h[0] for h in hy], "no": [h[0] for h in hn]}, btc_t, btc_c)


def order(side="yes", price=4800, size=1000, queue=0, active=60.0, **kw) -> RestingOrder:
    return RestingOrder(side, price, size, queue, ns(active), done_ns=ns(active), **kw)


# --- fill model -----------------------------------------------------------------------------------

def test_queue_ahead_is_consumed_before_we_fill():
    w = mk(hits_yes=[(70, 4800, 600), (80, 4800, 600)])
    o = order(queue=1000)
    advance(o, w, ns(100), BASE)
    assert o.filled == 200 and o.queue == 0  # 1,200 traded: 1,000 ahead of us, then 200 to us


def test_trades_before_the_order_is_active_dont_count():
    w = mk(hits_yes=[(60.5, 4800, 5000)])  # inside the 1 s placement latency
    o = order(active=61.0)
    advance(o, w, ns(100), BASE)
    assert o.filled == 0


def test_trade_through_our_price_fills_the_rest():
    w = mk(hits_yes=[(70, 4700, 1)])  # a lower YES bid was hit, so our 48c level was cleared
    o = order(queue=10**9)
    advance(o, w, ns(100), BASE)
    assert o.filled == o.size


def test_other_side_and_better_prices_never_fill_us():
    w = mk(hits_yes=[(70, 4900, 5000)], hits_no=[(75, 4800, 5000)])
    o = order()
    advance(o, w, ns(100), BASE)
    assert o.filled == 0


def test_cancels_ahead_never_help_in_base_but_do_in_optimistic_mode():
    snaps = [Snap(ns(s), [(4800, 1000 if s < 65 else 100)], [(5000, 1000)]) for s in range(0, 900)]
    w = mk(hits_yes=[(70, 4800, 150)], snaps=snaps)
    base = order(queue=1000, last_level=1000)
    advance(base, w, ns(100), BASE)
    assert base.filled == 0
    opt = order(queue=1000, last_level=1000)
    advance(opt, w, ns(100), Mode("optimistic", optimistic_queue=True))
    assert opt.filled == 50  # queue fell to 100 pro rata, then 150 traded


def test_back_only_mode_needs_a_trade_through():
    w = mk(hits_yes=[(70, 4800, 10_000), (80, 4700, 1)])
    o = order()
    advance(o, w, ns(75), Mode("back", back_only=True))
    assert o.filled == 0
    advance(o, w, ns(100), Mode("back", back_only=True))
    assert o.filled == o.size


def test_fills_during_cancel_latency_count_and_after_dont():
    w = mk(hits_yes=[(90.5, 4800, 300), (91.5, 4800, 300)])
    o = order(end_ns=ns(91.0))  # cancel decided at 90 s, effective 91 s
    advance(o, w, ns(120), BASE)
    assert o.filled == 300


# --- strategies -----------------------------------------------------------------------------------

def test_m2_completed_pair_locks_the_spread_whatever_the_outcome():
    hits_yes = [(65, 4800, 10**6)]
    hits_no = [(66, 5000, 10**6)]
    v = Variant("M2", "spread>=2c once", s_min_c=2)
    for won in (True, False):
        r = simulate(v, mk(hits_yes, hits_no, yes_won=won))
        n = 5_000_000 // ((4800 + 5000) * 100)  # 5 pairs at 98c
        assert r.pairs_e2 == n * 100 and r.fees == 0
        assert r.pnl == n * 200 == r.spread_earned and r.adverse == 0


def test_m2_one_sided_fill_is_adverse_selection():
    r = simulate(Variant("M2", "x", s_min_c=2), mk(hits_yes=[(65, 4800, 10**6)], yes_won=False))
    assert r.pairs_e2 == 0 and r.pnl == -r.yes_e2 * 4800 // 100 and r.adverse == r.pnl


def test_m2_needs_the_minimum_spread():
    assert simulate(Variant("M2", "x", s_min_c=3), mk(hits_yes=[(65, 4800, 10**6)])).quoted == 0


def test_m1_bids_the_side_the_model_favours_and_stays_within_5_dollars():
    w = mk(hits_yes=[(t, 4700, 10**6) for t in range(65, 780, 30)], btc_above=150.0)  # YES clearly underpriced at 48c
    r = simulate(Variant("M1", "x", margin_c=1), w)
    assert r.yes_e2 > 0 and r.no_e2 == 0
    assert r.cost <= 50_000  # $5 of filled cost, however many requotes fill
    assert r.spread_earned > 0


def test_m1_improve_needs_two_ticks_and_jumps_the_queue():
    hits = [(t, 4900, 50) for t in range(65, 780, 30)]  # trades only at 49c
    wide = mk(hits_yes=hits, btc_above=150.0, levels=book(yes=((4800, 10**6),), no=((5000, 10**6),)))
    r = simulate(Variant("M1", "x", margin_c=1, improve=True), wide)
    assert r.yes_e2 > 0  # bid 49c, first in line
    tight = mk(hits_yes=hits, btc_above=150.0, levels=book(yes=((4900, 10**6),), no=((5000, 10**6),)))
    assert simulate(Variant("M1", "x", margin_c=1, improve=True), tight).quoted == 0


def test_maker_fee_applies_when_the_series_has_maker_fees():
    w = mk(hits_yes=[(65, 4800, 10**6)], hits_no=[(66, 5000, 10**6)])
    r = simulate(Variant("M2", "x", s_min_c=2), w, fee_type="quadratic_with_maker_fees")
    assert r.fees > 0 and r.pnl < r.pairs_e2 * 200 // 100


def test_no_decision_reads_future_snapshots():
    w = mk(hits_yes=[(65, 4800, 10**6)], hits_no=[(66, 5000, 10**6)])
    later = [Snap(s.t_ns, [(4800, 1)], [(5000, 1)]) if s.t_ns > ns(60) else s for s in w.snaps]
    assert simulate(Variant("M2", "x", s_min_c=2), w).pnl == \
        simulate(Variant("M2", "x", s_min_c=2), replace(w, snaps=later)).pnl


# --- usability ------------------------------------------------------------------------------------

def test_usable_window_and_each_failure_reason():
    w = mk()
    assert unusable_reason(w, [], []) is None
    thin = replace(w, snaps=w.snaps[::2], snap_t=w.snap_t[::2])
    assert unusable_reason(thin, [], []) == "book_coverage"
    assert unusable_reason(w, [(ns(300), ns(320))], []) == "gap_in_quoting"
    assert unusable_reason(w, [(ns(850), ns(870))], []) is None  # gap after quoting ends
    assert unusable_reason(w, [], [CLOSE * NS + 10 * NS]) == "tape_error"
    assert unusable_reason(replace(w, yes_won=None), [], []) == "no_result"
    assert unusable_reason(replace(w, btc_t=w.btc_t[:100], btc_c=w.btc_c[:100]), [], []) == "btc_missing"


# --- guards and end-to-end ------------------------------------------------------------------------

def test_refuses_the_real_recording_before_the_end_date(monkeypatch):
    monkeypatch.setattr(maker, "END_CLOSE_TS", 4_102_444_800)  # 2100: stays "before the end" whatever today is
    monkeypatch.setattr("sys.argv", ["slot.maker", "count", "--fee-type", "quadratic"])
    with pytest.raises(SystemExit, match="no analysis of the recording before 2100-01-01"):
        maker.main()


def test_the_real_end_date_is_the_approved_one():
    assert maker.END_CLOSE_TS == 1_793_163_600  # 2026-10-28 05:00 UTC, midnight Chicago
    assert maker.START_OPEN_TS == 1_792_008_900  # 2026-10-14 20:15 UTC


def test_end_date_can_only_be_extended_with_a_recorded_amendment():
    with pytest.raises(SystemExit, match="later"):
        maker._end_allowed(maker.END_CLOSE_TS - 86_400)
    with pytest.raises(SystemExit, match="amendment"):
        maker._end_allowed(maker.END_CLOSE_TS + 86_400)


def _synthetic_db(path, n_windows):
    store = Store(path)
    db = store.db
    for i in range(n_windows):
        o = maker.START_OPEN_TS + 900 * (i + 2)
        won = i % 2 == 0
        db.execute("INSERT INTO windows VALUES (?,?,?,?,?,?,?)",
                   (f"KXBTC15M-S{i}", o, o + 900, "80000.00", "yes" if won else "no", "80001.00", o * NS))
        db.executemany("INSERT INTO books VALUES (?,?,?,?,?,?,?)",
                       [(f"KXBTC15M-S{i}", (o + s) * NS, (o + s) * NS, "4800:100000", "5000:100000", 1, 1)
                        for s in range(900)])
        db.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?)", [
            (f"t{i}y", f"KXBTC15M-S{i}", _iso(o + 70), 4700, 10**6, "no"),
            (f"t{i}n", f"KXBTC15M-S{i}", _iso(o + 75 if i % 3 else o + 899), 5000 - 100, 10**6, "yes"),
        ])
    first = maker.START_OPEN_TS + 900 * 2 - 17 * 60
    db.executemany("INSERT INTO btc VALUES (?,?,?,?,?)",
                   [((first + s) * NS, "x", 8_000_000 + (300 if s % 120 < 60 else -300), 0, 0)
                    for s in range(900 * (n_windows + 3) + 17 * 60)])
    db.commit()
    return db


def _iso(ts: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def test_train_then_test_end_to_end_on_synthetic_recording(tmp_path, monkeypatch):
    monkeypatch.setattr(maker, "MIN_USABLE", 12)
    monkeypatch.setattr(maker, "MIN_TRADED", 3)
    db = _synthetic_db(str(tmp_path / "syn.sqlite"), 15)
    usable, reasons = maker.usable_rows(db, maker.END_CLOSE_TS)
    assert len(usable) == 15 and reasons == {"usable": 15}
    chosen = maker.phase_train(db, maker.END_CLOSE_TS, "quadratic", docs=tmp_path)
    assert set(chosen) == {"M2"} or set(chosen) == {"M1", "M2"}
    sel = json.loads((tmp_path / "r1-selection.json").read_text())
    assert sel["train"] == 10 and sel["usable"] == 15
    runs = maker.phase_test(db, maker.END_CLOSE_TS, "quadratic", docs=tmp_path, require_commit=False)
    text = (tmp_path / "r1-test.md").read_text()
    assert "Verdicts" in text and "Sensitivity" in text and len(runs) == len(chosen)
    assert all(len(r.windows) <= 5 for r in runs)  # test = last 1/3 only


def test_train_refuses_below_the_minimum(tmp_path):
    db = _synthetic_db(str(tmp_path / "small.sqlite"), 3)
    with pytest.raises(SystemExit, match="usable windows"):
        maker.phase_train(db, maker.END_CLOSE_TS, "quadratic", docs=tmp_path)
