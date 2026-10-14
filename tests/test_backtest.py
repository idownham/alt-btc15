import math
from dataclasses import replace

import pytest

from slot.backtest import (
    Btc, Candle, Result, Trade, Win, apply_caps, fee_e4, metrics, p_yes, size, strategy_a, strategy_b, strategy_c,
    tick_up, worst_ask, worst_bid,
)

OPEN = 1_786_000_000 - (1_786_000_000 % 900)
CLOSE = OPEN + 900
K = 80_000.0


def flat(yb=4900, ya=5100, p=5000, **kw):
    """A quiet candle: bid 49c / ask 51c / trades at 50c all minute."""
    base = dict(yb_h=yb, yb_l=yb, yb_c=yb, ya_h=ya, ya_l=ya, ya_c=ya, p_h=p, p_l=p)
    base.update(kw)
    return Candle(**base)


def window(yes_won=True, candles=None, strike=K):
    cs = {k: flat() for k in range(1, 16)}
    cs.update(candles or {})
    return Win("KXBTC15M-T", OPEN, CLOSE, strike, yes_won, cs)


def btc_rising(start=K - 50, step_cents=100, vol=True):
    """BTC 1-min closes from 70 min before open to close, rising $1/min with a small wiggle."""
    closes = {}
    for i, t in enumerate(range(OPEN - 70 * 60, CLOSE, 60)):
        wiggle = (300 if i % 2 else -300) if vol else 0
        closes[t] = int(start * 100) + i * step_cents + wiggle
    return Btc(closes)


def test_worst_prices_and_no_side_conversion():
    c = flat(yb_l=4000, ya_h=6000)
    assert worst_ask(c, "yes") == 6000 and worst_ask(c, "no") == 6000  # 1 - 0.40
    assert worst_bid(c, "yes") == 4000 and worst_bid(c, "no") == 4000  # 1 - 0.60


def test_size_keeps_max_loss_within_5_dollars():
    for price in (100, 4900, 5100, 9500, 9990):
        n = size(price)
        assert n * price + fee_e4(n, price) <= 50_000
        assert (n + 1) * price + fee_e4(n + 1, price) > 50_000


def test_fee_is_ceiled_to_the_cent():
    assert fee_e4(9, 5100) == 1600  # 0.07 x 9 x 0.51 x 0.49 = $0.1574 -> $0.16
    assert fee_e4(5, 9500) == 200


def test_tick_grid():
    assert tick_up(5050) == 5100 and tick_up(9001) == 9010 and tick_up(950) == 950 and tick_up(951) == 960


def test_model_is_symmetric_and_average_aware():
    assert p_yes(K, K, 0.0005, 300) == pytest.approx(0.5)
    sd = 0.0005 * K / math.sqrt(60) * math.sqrt(120 - 40)
    assert p_yes(K + sd, K, 0.0005, 120) == pytest.approx(0.8413, abs=1e-4)


def test_a_buys_at_worst_ask_in_minute_2_and_settles():
    w = window(yes_won=True, candles={2: flat(ya_h=5800)})
    t = strategy_a("lean").run(w, btc_rising(), False)  # BTC above strike at T0+60 -> YES
    assert isinstance(t, Trade) and t.side == "yes" and t.entry_e4 == 5800
    assert t.pnl_e4 == t.n * (10_000 - 5800) - t.entry_fee


def test_ask_of_one_dollar_is_no_fill():
    w = window(candles={2: flat(ya_h=10_000)})
    assert strategy_a("lean").run(w, btc_rising(), False) == "no_fill"


def test_a_decision_ignores_the_future():
    """Changing BTC after the decision at T0+60 must not change A's side. (The candle starting at
    T0 ends at T0+60, so it is allowed; anything starting later is the future.)"""
    btc = btc_rising()
    later = Btc({t: (c if t < OPEN + 60 else c - 1_000_000) for t, c in btc.close.items()})
    assert strategy_a("mom15").run(window(), btc, False).side == strategy_a("mom15").run(window(), later, False).side


def test_b_target_needs_trades_past_the_price_not_at_it():
    at = window(candles={3: flat(p=6100, ya_h=5100)})  # entry 51c, +10c target = 61c; trades only AT 61c
    past = window(candles={3: flat(p=6200)})
    v = strategy_b("lean", 10, False, None)
    assert v.run(at, btc_rising(), False).exit_kind == "settle"
    t = v.run(past, btc_rising(), False)
    assert t.exit_kind == "target" and t.exit_e4 == 6100 and t.exit_fee == 0
    assert t.pnl_e4 == t.n * 1000 - t.entry_fee


def test_b_stop_beats_target_in_the_same_minute():
    w = window(candles={3: flat(yb_l=2500, p_h=7000, p_l=2500)})  # bid falls to 25c and trades reach 70c
    t = strategy_b("lean", 10, True, None).run(w, btc_rising(), False)
    assert t.exit_kind == "stop" and t.exit_e4 == 2500 and t.exit_fee > 0


def test_b_time_exit_at_worst_bid_retries_on_zero_bid():
    w = window(candles={3: flat(yb_l=0, yb_c=0), 4: flat(yb_l=4500)})
    t = strategy_b("lean", 15, False, 1).run(w, btc_rising(), False)
    assert t.exit_kind == "time" and t.exit_e4 == 4500 and t.exit_ts == OPEN + 4 * 60


def test_c_decision_uses_only_candles_up_to_the_decision_minute():
    btc = btc_rising(start=K + 200)  # BTC far above target -> YES favorite
    w = window(yes_won=True, candles={12: flat(yb=9400, ya=9500, p=9450), 13: flat(yb=9400, ya=9600, p=9500)})
    v = strategy_c(0, 15)
    t = v.run(w, btc, False)
    assert isinstance(t, Trade) and t.entry_ts == OPEN + 12 * 60 and t.entry_e4 == 9600  # fills in minute 13
    # The minute-13 price is the fill only; making it worse doesn't change the decision, only the fill.
    w2 = replace(w, candles={**w.candles, 13: flat(yb=9400, ya=9900, p=9500)})
    assert v.run(w2, btc, False).entry_e4 == 9900


def test_c_ignores_favorites_outside_90_to_97():
    btc = btc_rising(start=K + 200)
    w = window(candles={12: flat(yb=9800, ya=9900), 13: flat(yb=9800, ya=9900)})
    assert strategy_c(0, 15).run(w, btc, False) == "no_signal"


def test_caps_refuse_after_25_dollar_day():
    trades = [Trade("T", "yes", OPEN + i * 900, OPEN + i * 900 + 900, 5000, 9, 16 * 100, "settle", None, 0, -46_600)
              for i in range(8)]
    res = Result(strategy_a("lean"), trades=trades)
    apply_caps(res)
    # 5 x -$4.66 = -$23.30; a 6th (max loss $4.66) could breach $25, so it and the rest of the day are refused.
    assert len(res.capped) == 5 and res.cap_events["day_cap"] == 3


def test_metrics_drawdown_and_breakeven():
    mk = lambda p: Trade("T", "yes", OPEN, CLOSE, 5000, 1, 0, "settle", None, 0, p)  # noqa: E731
    m = metrics([mk(10_000), mk(-5000), mk(-5000), mk(2000)])
    assert m["max_drawdown"] == 10_000 and m["net"] == 2000
    assert m["breakeven_win_rate"] == pytest.approx(5000 / (6000 + 5000))
