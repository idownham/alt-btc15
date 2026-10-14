"""S1 backtest of strategies A-D, exactly as pre-registered in docs/s1-preregistration.md.

    .venv/bin/python -m slot.backtest train   # all 61 variants on the train set -> docs/s1-train.md + selection
    .venv/bin/python -m slot.backtest test    # the 4 selected variants on the test set, once -> docs/s1-test.md

Units: Kalshi prices and P&L in integer 1/10,000 dollar ("e4"); counts are whole contracts. Model
probabilities are floats: they are not money.

Candle k (1..15) covers (open + 60(k-1), open + 60k]. A decision "at the end of candle k" reads candles
<= k and BTC candles that ended by then, and fills in candle k + 1 (no look-ahead).
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from slot.fees import TAKER_RATE, fee
from slot.history import DB_PATH
from slot.risk import KillSwitch, Order, RiskManager, chicago_day

ONE = 10_000  # $1 in e4
SPLIT_TS = int(datetime(2026, 8, 29, tzinfo=timezone.utc).timestamp())
START_TS = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
END_TS = int(datetime(2026, 10, 13, tzinfo=timezone.utc).timestamp())
MAX_RISK_E4 = 5 * ONE
ROOT = Path(__file__).resolve().parents[2]
SELECTION = ROOT / "docs" / "s1-selection.json"


# --- data ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Candle:
    yb_h: int | None
    yb_l: int | None
    yb_c: int | None
    ya_h: int | None
    ya_l: int | None
    ya_c: int | None
    p_h: int | None
    p_l: int | None


@dataclass
class Win:
    ticker: str
    open_ts: int
    close_ts: int
    strike: float  # for the model only; the outcome comes from `yes_won`
    yes_won: bool
    candles: dict[int, Candle]  # k -> candle


@dataclass
class Btc:
    close: dict[int, int]  # candle start ts -> close in cents

    def price_at(self, t: int) -> float | None:
        """Close of the 1-min candle that ended at t."""
        c = self.close.get(t - 60)
        return None if c is None else c / 100

    def sigma(self, t: int, lookback_min: int) -> float | None:
        """Population sd of 1-min log returns over the `lookback_min` minutes ending at t."""
        closes = [self.close.get(t - 60 * (i + 1)) for i in range(lookback_min + 1)]
        if any(c is None for c in closes):
            return None
        rets = [math.log(a / b) for a, b in zip(closes, closes[1:])]
        return statistics.pstdev(rets)


def load(db_path: Path = DB_PATH) -> tuple[list[Win], Btc, Counter]:
    db = sqlite3.connect(db_path)
    skips: Counter = Counter()
    candles: dict[str, dict[int, Candle]] = defaultdict(dict)
    opens = dict(db.execute("SELECT ticker, open_ts FROM windows"))
    for row in db.execute("SELECT ticker, end_ts, yb_h, yb_l, yb_c, ya_h, ya_l, ya_c, p_h, p_l FROM kcandles"):
        ticker, end_ts = row[0], row[1]
        k = (end_ts - opens[ticker]) // 60
        if 1 <= k <= 15:
            candles[ticker][k] = Candle(*row[2:])
    wins = []
    for ticker, open_ts, close_ts, strike, result in db.execute(
        "SELECT ticker, open_ts, close_ts, strike, result FROM windows WHERE close_ts > ? AND close_ts <= ? "
        "ORDER BY close_ts", (START_TS, END_TS)
    ):
        if strike is None or Decimal(strike) < 1000:
            skips["bad_strike"] += 1
        elif result not in ("yes", "no"):
            skips["no_result"] += 1
        elif len(candles[ticker]) != 15:
            skips["missing_candles"] += 1
        else:
            wins.append(Win(ticker, open_ts, close_ts, float(strike), result == "yes", candles[ticker]))
    btc = Btc(dict(db.execute("SELECT start_ts, c FROM btc")))
    return wins, btc, skips


# --- prices, fees, model ------------------------------------------------------------------------

def ask_close(c: Candle, side: str) -> int | None:
    if side == "yes":
        return c.ya_c
    return None if c.yb_c is None else ONE - c.yb_c


def worst_ask(c: Candle, side: str) -> int | None:
    if side == "yes":
        return c.ya_h
    return None if c.yb_l is None else ONE - c.yb_l


def worst_bid(c: Candle, side: str) -> int | None:
    if side == "yes":
        return c.yb_l
    return None if c.ya_h is None else ONE - c.ya_h


def bid_close(c: Candle, side: str) -> int | None:
    if side == "yes":
        return c.yb_c
    return None if c.ya_c is None else ONE - c.ya_c


def trade_high(c: Candle, side: str) -> int | None:
    if side == "yes":
        return c.p_h
    return None if c.p_l is None else ONE - c.p_l


def fee_e4(n: int, price_e4: int) -> int:
    return int(fee(Decimal(n), Decimal(price_e4) / ONE) * ONE)


def fee_per_contract(price_e4: int) -> float:
    p = price_e4 / ONE
    return float(TAKER_RATE) * p * (1 - p)


def size(price_e4: int) -> int:
    """Largest whole n with n * price + fee <= $5."""
    n = MAX_RISK_E4 // price_e4
    while n > 0 and n * price_e4 + fee_e4(n, price_e4) > MAX_RISK_E4:
        n -= 1
    return n


def tick_up(price_e4: int) -> int:
    """Round up to the tapered_deci_cent grid: 0.1c in [0, 10c] and [90c, $1], 1c in between."""
    step = 10 if price_e4 < 1000 or price_e4 >= 9000 else 100
    return -(-price_e4 // step) * step


def p_yes(s: float, k: float, sigma_log: float, tau_s: int) -> float:
    """Average-aware fair value for tau >= 60 s (approved 2026-10-13)."""
    sd = sigma_log * s / math.sqrt(60) * math.sqrt(tau_s - 40)
    return 0.5 * (1 + math.erf((s - k) / (sd * math.sqrt(2))))


# --- trades -------------------------------------------------------------------------------------

@dataclass
class Trade:
    ticker: str
    side: str
    entry_ts: int
    exit_ts: int
    entry_e4: int
    n: int
    entry_fee: int
    exit_kind: str
    exit_e4: int | None
    exit_fee: int
    pnl_e4: int

    @property
    def max_loss_e4(self) -> int:
        return self.n * self.entry_e4 + self.entry_fee


@dataclass
class Variant:
    strategy: str
    name: str
    run: Callable[[Win, Btc, bool], Trade | str | None]  # trade, skip reason, or None (no signal)


def _enter(w: Win, side: str, k_fill: int, close_fills: bool) -> tuple[int, int, int] | str:
    c = w.candles[k_fill]
    price = ask_close(c, side) if close_fills else worst_ask(c, side)
    if price is None or price >= ONE or price <= 0:
        return "no_fill"
    n = size(price)
    if n == 0:
        return "size_zero"
    return price, n, fee_e4(n, price)


def _settle(w: Win, side: str, k_fill: int, price: int, n: int, f: int) -> Trade:
    won = w.yes_won == (side == "yes")
    pnl = n * (ONE if won else 0) - n * price - f
    return Trade(w.ticker, side, w.open_ts + 60 * (k_fill - 1), w.close_ts, price, n, f, "settle", None, 0, pnl)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def signal(w: Win, btc: Btc, name: str, t: int) -> str | None:
    s = btc.price_at(t)
    if s is None:
        return None
    if name in ("lean", "antilean"):
        d = _sign(s - w.strike)
    else:
        past = btc.price_at(t - 60 * int(name[3:]))
        if past is None:
            return None
        d = _sign(s - past)
    if name.startswith(("rev", "anti")):
        d = -d
    return None if d == 0 else ("yes" if d > 0 else "no")


def strategy_a(sig: str) -> Variant:
    def run(w: Win, btc: Btc, close_fills: bool) -> Trade | str | None:
        side = signal(w, btc, sig, w.open_ts + 60)
        if side is None:
            return "no_signal"
        e = _enter(w, side, 2, close_fills)
        return e if isinstance(e, str) else _settle(w, side, 2, *e)
    return Variant("A", sig, run)


def strategy_b(sig: str, target_c: int, stop: bool, limit: int | None) -> Variant:
    def run(w: Win, btc: Btc, close_fills: bool) -> Trade | str | None:
        side = signal(w, btc, sig, w.open_ts + 60)
        if side is None:
            return "no_signal"
        e = _enter(w, side, 2, close_fills)
        if isinstance(e, str):
            return e
        price, n, f = e
        target = tick_up(price + target_c * 100)
        target = target if target < ONE else None
        stop_at = price - 2500 if stop else None
        pending_exit = False  # a stop or time exit waiting for a non-zero bid
        for k in range(3, 16):
            c = w.candles[k]
            bid = bid_close(c, side) if close_fills else worst_bid(c, side)
            end_ts = w.open_ts + 60 * k
            if stop_at is not None and bid is not None and bid <= stop_at:
                pending_exit = True
            elif not pending_exit and target is not None and (th := trade_high(c, side)) is not None and th > target:
                return Trade(w.ticker, side, w.open_ts + 60, end_ts, price, n, f, "target", target, 0,
                             n * (target - price) - f)
            if limit is not None and k == 2 + limit:
                pending_exit = True
            if pending_exit and bid is not None and bid > 0:
                xf = fee_e4(n, bid)
                kind = "stop" if stop_at is not None and bid <= stop_at else "time"
                return Trade(w.ticker, side, w.open_ts + 60, end_ts, price, n, f, kind, bid, xf,
                             n * (bid - price) - f - xf)
        return _settle(w, side, 2, price, n, f)
    lim = "hold" if limit is None else f"{limit}m"
    return Variant("B", f"{sig} +{target_c}c stop={'25c' if stop else 'none'} limit={lim}", run)


def _model(w: Win, btc: Btc, t: int, lookback: int) -> float | None:
    s, sig = btc.price_at(t), btc.sigma(t, lookback)
    if s is None or not sig:
        return None
    return p_yes(s, w.strike, sig, w.close_ts - t)


def strategy_c(margin_c: int, lookback: int) -> Variant:
    def run(w: Win, btc: Btc, close_fills: bool) -> Trade | str | None:
        reason = "no_signal"
        for k_obs in (12, 13):  # decisions at T1 - 180 s and T1 - 120 s
            p = _model(w, btc, w.open_ts + 60 * k_obs, lookback)
            if p is None:
                reason = "no_model"
                continue
            side, p_side = ("yes", p) if p > 0.5 else ("no", 1 - p)
            ask = ask_close(w.candles[k_obs], side)
            if ask is None or not 9000 <= ask <= 9700:
                continue
            if p_side - ask / ONE - fee_per_contract(ask) < margin_c / 100:
                continue
            e = _enter(w, side, k_obs + 1, close_fills)
            if isinstance(e, str):
                reason = e  # no fill: the next decision time may still trade
                continue
            return _settle(w, side, k_obs + 1, *e)
        return reason
    return Variant("C", f"margin={margin_c}c L={lookback}", run)


def strategy_d(direction: str, margin_c: int, lookback: int) -> Variant:
    def run(w: Win, btc: Btc, close_fills: bool) -> Trade | str | None:
        reason = "no_signal"
        for k_obs in (9, 10, 11):  # decisions at T1 - 360, -300, -240 s
            c = w.candles[k_obs]
            asks = {s: ask_close(c, s) for s in ("yes", "no")}
            longs = [s for s, a in asks.items() if a is not None and a <= 1000]
            if not longs:
                continue
            p = _model(w, btc, w.open_ts + 60 * k_obs, lookback)
            if p is None:
                reason = "no_model"
                continue
            long_side = longs[0]
            fav = "no" if long_side == "yes" else "yes"
            p_long = p if long_side == "yes" else 1 - p
            if direction == "fade":
                side, edge = fav, None if asks[fav] is None else (1 - p_long) - asks[fav] / ONE - fee_per_contract(asks[fav])
            else:
                side, edge = long_side, p_long - asks[long_side] / ONE - fee_per_contract(asks[long_side])
            if edge is None or edge < margin_c / 100:
                continue
            e = _enter(w, side, k_obs + 1, close_fills)
            if isinstance(e, str):
                reason = e
                continue
            return _settle(w, side, k_obs + 1, *e)
        return reason
    return Variant("D", f"{direction} margin={margin_c}c L={lookback}", run)


def variants() -> list[Variant]:
    vs = [strategy_a(s) for s in ("mom5", "mom15", "mom60", "rev5", "rev15", "rev60", "lean", "antilean")]
    vs += [strategy_b(sig, t, stop, lim) for sig in ("lean", "mom15") for t in (5, 10, 15)
           for stop in (False, True) for lim in (1, 5, None)]
    vs += [strategy_c(m, lb) for m in (0, 1, 2) for lb in (5, 15, 60)]
    vs += [strategy_d(d, m, lb) for d in ("fade", "buy") for m in (2, 5) for lb in (15, 60)]
    return vs


# --- running and metrics ------------------------------------------------------------------------

@dataclass
class Result:
    variant: Variant
    trades: list[Trade] = field(default_factory=list)  # every trade the strategy wanted (uncapped)
    capped: list[Trade] = field(default_factory=list)  # trades the per-strategy RiskManager allowed
    skips: Counter = field(default_factory=Counter)
    cap_events: Counter = field(default_factory=Counter)
    halted_at: int | None = None


def run_variant(v: Variant, wins: list[Win], btc: Btc, close_fills: bool = False) -> Result:
    res = Result(v)
    for w in wins:
        out = v.run(w, btc, close_fills)
        if isinstance(out, Trade):
            res.trades.append(out)
        elif out:
            res.skips[out] += 1
    apply_caps(res)
    return res


class _SimClock:
    def __init__(self) -> None:
        self.t = datetime(2000, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.t


def apply_caps(res: Result) -> None:
    """Replay trades through a fresh RiskManager ($5 / $25 day / $100 total, per strategy variant)."""
    clock = _SimClock()
    rm = RiskManager(kill_switch=KillSwitch(Path("/nonexistent-backtest-root"), environ={}), now=clock)
    for i, t in enumerate(res.trades):
        clock.t = datetime.fromtimestamp(t.entry_ts, tz=timezone.utc)
        order = Order(f"o{i}", res.variant.strategy, t.ticker, t.side, "buy", Decimal(t.n),
                      Decimal(t.entry_e4) / ONE, Decimal(t.entry_fee) / ONE)
        d = rm.check(order)
        if not d.allowed:
            res.cap_events[d.reason.split(":")[0]] += 1
            if d.reason.startswith("total_cap") and res.halted_at is None:
                res.halted_at = t.entry_ts
            continue
        rm.record_open(order)
        rm.record_close(order.order_id, Decimal(t.pnl_e4) / ONE, datetime.fromtimestamp(t.exit_ts, tz=timezone.utc))
        res.capped.append(t)


def metrics(trades: list[Trade]) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    pnl = [t.pnl_e4 for t in trades]
    wins_, losses = [p for p in pnl if p > 0], [-p for p in pnl if p <= 0]
    aw = statistics.mean(wins_) if wins_ else 0.0
    al = statistics.mean(losses) if losses else 0.0
    mean = statistics.mean(pnl)
    sd = statistics.stdev(pnl) if n > 1 else 0.0
    days: dict = defaultdict(int)
    for t in trades:
        days[chicago_day(datetime.fromtimestamp(t.exit_ts, tz=timezone.utc))] += t.pnl_e4
    cum = peak = dd = 0
    for p in pnl:
        cum += p
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return {
        "trades": n,
        "win_rate": len(wins_) / n,
        "breakeven_win_rate": al / (aw + al) if aw + al else None,
        "net": sum(pnl),
        "mean": mean,
        "ci95": (mean - 1.96 * sd / math.sqrt(n), mean + 1.96 * sd / math.sqrt(n)),
        "worst_day": min(days.values()),
        "max_drawdown": dd,
        "avg_entry": statistics.mean(t.entry_e4 for t in trades),
        "exits": dict(Counter(t.exit_kind for t in trades)),
    }


def usd(e4: float | None) -> str:
    if e4 is None:
        return "–"
    d = (Decimal(e4) / ONE).quantize(Decimal("0.01"))
    return f"−${-d}" if d < 0 else f"${d}"


def pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.1f}%"


def select(results: list[Result]) -> dict[str, str]:
    """Pre-registered rule: highest capped net P&L among variants with >= 30 capped trades; ties -> earlier."""
    chosen: dict[str, tuple[int, str]] = {}
    for r in results:
        m = metrics(r.capped)
        if m["trades"] < 30:
            continue
        best = chosen.get(r.variant.strategy)
        if best is None or m["net"] > best[0]:
            chosen[r.variant.strategy] = (m["net"], r.variant.name)
    return {s: name for s, (_, name) in sorted(chosen.items())}


def _row(r: Result) -> str:
    m, mu = metrics(r.capped), metrics(r.trades)
    if not m["trades"]:
        return f"| {r.variant.strategy} | {r.variant.name} | 0 | – | – | – | {usd(mu.get('net'))} | – | – | – | – |"
    return (f"| {r.variant.strategy} | {r.variant.name} | {m['trades']} | {pct(m['win_rate'])} | "
            f"{pct(m['breakeven_win_rate'])} | **{usd(m['net'])}** | {usd(mu['net'])} | {usd(m['mean'])} | "
            f"{usd(m['worst_day'])} | {usd(m['max_drawdown'])} | {dict(r.cap_events) or ''} |")


HEADER = ("| Strat | Variant | Trades (capped) | Win rate | Break-even WR | Net P&L capped | Net uncapped | "
          "Mean/trade | Worst day | Max DD | Cap refusals |\n|---|---|---|---|---|---|---|---|---|---|---|")


def _git_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def phase_train(db: Path) -> None:
    wins, btc, skips = load(db)
    train = [w for w in wins if w.close_ts <= SPLIT_TS]
    results = [run_variant(v, train, btc) for v in variants()]
    chosen = select(results)
    lines = [f"# S1 train results (all 61 variants)\n",
             f"*Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m slot.backtest train` at commit "
             f"{_git_head()}. Train = windows closing 2026-06-01 → 2026-08-29 UTC: {len(train)} usable windows. "
             f"Windows skipped in the whole range: {dict(skips)}. Worst-in-minute fills; caps per variant.*\n",
             "**This is in-sample.** With 61 variants tried, the best numbers here are inflated by selection. "
             "Only the test set (`docs/s1-test.md`) counts.\n", HEADER]
    lines += [_row(r) for r in results]
    lines += ["", "## Skips per variant (train)", "", "| Strat | Variant | Skips |", "|---|---|---|"]
    lines += [f"| {r.variant.strategy} | {r.variant.name} | {dict(r.skips)} |" for r in results]
    lines += ["", "## Selected for the test set (pre-registered rule)", ""]
    lines += [f"- **{s}:** {name}" for s, name in chosen.items()] or ["- none"]
    missing = sorted({v.strategy for v in variants()} - set(chosen))
    if missing:
        lines.append(f"- No variant with ≥ 30 capped trades for: {', '.join(missing)} (not tested).")
    (ROOT / "docs" / "s1-train.md").write_text("\n".join(lines) + "\n")
    SELECTION.write_text(json.dumps({"chosen": chosen, "train_windows": len(train), "commit": _git_head()}, indent=2) + "\n")
    print("\n".join(lines[-(len(chosen) + 3):]))


def phase_test(db: Path) -> None:
    if not SELECTION.exists():
        sys.exit("run the train phase first")
    status = subprocess.run(["git", "status", "--porcelain", str(SELECTION)], cwd=ROOT, capture_output=True, text=True)
    if status.stdout.strip():
        sys.exit("commit docs/s1-selection.json before running the test set (evidence that selection came first)")
    chosen = json.loads(SELECTION.read_text())["chosen"]
    wins, btc, skips = load(db)
    test = [w for w in wins if w.close_ts > SPLIT_TS]
    by_name = {(v.strategy, v.name): v for v in variants()}
    lines = [f"# S1 test results (out-of-sample, run once)\n",
             f"*Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m slot.backtest test` at commit "
             f"{_git_head()}. Test = windows closing 2026-08-29 → 2026-10-13 UTC: {len(test)} usable windows. "
             f"Variants selected on train only (`docs/s1-selection.json`).*\n", HEADER]
    detail, sens = [], []
    for strat, name in chosen.items():
        r = run_variant(by_name[(strat, name)], test, btc)
        lines.append(_row(r))
        m = metrics(r.capped)
        verdict = "**passes S1** (test net > 0)" if m["trades"] and m["net"] > 0 else "**does not pass S1**"
        ci = m.get("ci95")
        detail.append(f"- **{strat} ({name}):** {verdict}. Mean per trade {usd(m.get('mean'))}, 95% CI "
                      f"{usd(ci[0]) if ci else '–'} to {usd(ci[1]) if ci else '–'}"
                      f"{' (excludes 0)' if ci and (ci[0] > 0 or ci[1] < 0) else ' (includes 0)'}; "
                      f"avg entry {usd(m.get('avg_entry'))}; exits {m.get('exits')}; skips {dict(r.skips)}; "
                      f"{'permanent $100 halt at ' + datetime.fromtimestamp(r.halted_at, tz=timezone.utc).strftime('%Y-%m-%d') if r.halted_at else 'no $100 halt'}.")
        rs = run_variant(by_name[(strat, name)], test, btc, close_fills=True)
        sens.append(_row(rs))
    lines += ["", "## Verdicts", ""] + detail
    lines += ["", "## Sensitivity: fills at the minute's close quote (NOT an S1 result; shows the cost of the "
              "worst-in-minute rule)", "", HEADER] + sens
    (ROOT / "docs" / "s1-test.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["train", "test"])
    p.add_argument("--db", type=Path, default=DB_PATH)
    args = p.parse_args()
    {"train": phase_train, "test": phase_test}[args.phase](args.db)


if __name__ == "__main__":
    main()
