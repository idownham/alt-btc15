"""R1 maker backtest, exactly as pre-registered in docs/r1-maker-preregistration.md (approved 2026-10-14).

    .venv/bin/python -m slot.maker count   # usable windows by reason (data health; no P&L)
    .venv/bin/python -m slot.maker train   # 8 variants on train -> docs/r1-train.md + docs/r1-selection.json
    .venv/bin/python -m slot.maker test    # chosen variants on test, once -> docs/r1-test.md

On the real recording (data/recorder/book.sqlite) every phase refuses to run before END_CLOSE_TS
(2026-10-28 05:00 UTC): the approval said no analysis before then. `--end` may only push the end later
(the >= 900-usable-window rule), and only once docs/r1-maker-preregistration.md records an amendment
naming that date.

Units: prices e4 (1/10,000 $), sizes e2 (1/100 contract), costs e6 (price_e4 x size_e2), P&L e4. Model
probabilities are floats (not money). Windows are loaded one at a time; a busy window has ~48k trades.

Interpretations of the pre-registration, fixed here before any data is seen:
- Quoting decisions: M1 at open+60, +90, ..., +750 (24 placements); M2 'once' at open+60, 'every 60 s' at
  open+60, +120, ..., +720 (12). At close-120 (open+780) every resting order is cancelled.
- M1 'improve' with a spread under 2 ticks: no quote that round (the pre-registration allows improving
  "only if the spread is >= 2 ticks"; it does not fall back to joining).
- Every decision cancels all resting orders (effective +latency) before placing new ones. A new order's size
  reserves budget for the still-cancelling orders' unfilled remainder, so the $5 window budget can't be exceeded.
- "Tape fetched through the close": a window is unusable if any `error:trades` event falls in
  [close, close + 300 s], while the recorder sweeps that window's tape.
- BTC "covered": a Coinbase tick within the 5 s before the decision time and before each of the 15 one-minute
  lookback points.
- Caps: one RiskManager per variant; each traded window is one position whose max loss is its actual filled
  cost plus fees (the same convention as S1).
"""

from __future__ import annotations

import argparse
import bisect
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
from decimal import Decimal
from pathlib import Path

from slot.backtest import ONE, Trade, metrics, p_yes, pct, usd
from slot.fees import fee
from slot.recorder import DB_PATH, parse_levels_text
from slot.risk import KillSwitch, Order, RiskManager

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs" / "r1-maker-preregistration.md"
SELECTION = ROOT / "docs" / "r1-selection.json"
START_OPEN_TS = int(datetime(2026, 10, 14, 20, 15, tzinfo=timezone.utc).timestamp())
END_CLOSE_TS = int(datetime(2026, 10, 28, 5, 0, tzinfo=timezone.utc).timestamp())
MIN_USABLE = 900
MIN_TRADED = 50
BUDGET_E6 = 5_000_000  # $5 of filled cost per window
NS = 1_000_000_000
COVERAGE = 0.95
SWEEP_S = 300
BTC_STALE_S = 5
LOOKBACK_MIN = 15
INF = 2**62


# --- data ---------------------------------------------------------------------------------------

@dataclass
class Snap:
    t_ns: int
    yes: list[tuple[int, int]]  # (price_e4, size_e2), best first
    no: list[tuple[int, int]]

    def best(self, side: str) -> tuple[int, int] | None:
        levels = self.yes if side == "yes" else self.no
        return levels[0] if levels else None

    def size_at(self, side: str, price: int) -> int:
        for p, s in (self.yes if side == "yes" else self.no):
            if p == price:
                return s
        return 0


@dataclass
class WinData:
    ticker: str
    open_ts: int
    close_ts: int
    strike: float | None
    yes_won: bool | None
    snaps: list[Snap]
    snap_t: list[int]
    # Fills for a resting bid on `side` come from takers on the other side, stored here per *our* side as
    # (t_ns, price in our side's terms, count_e2), time-ordered.
    hits: dict[str, list[tuple[int, int, int]]]
    hit_t: dict[str, list[int]]
    btc_t: list[int]
    btc_c: list[int]

    def snap_at(self, t_ns: int) -> Snap | None:
        i = bisect.bisect_right(self.snap_t, t_ns) - 1
        return self.snaps[i] if i >= 0 else None

    def btc_at(self, t_ns: int) -> float | None:
        i = bisect.bisect_right(self.btc_t, t_ns) - 1
        if i < 0 or t_ns - self.btc_t[i] > BTC_STALE_S * NS:
            return None
        return self.btc_c[i] / 100

    def model(self, t_ns: int) -> float | None:
        """Pre-registered fair value: average-aware N(d) with sigma from 15 one-minute log returns."""
        closes = [self.btc_at(t_ns - 60 * j * NS) for j in range(LOOKBACK_MIN + 1)]
        if any(c is None for c in closes) or self.strike is None:
            return None
        rets = [math.log(a / b) for a, b in zip(closes, closes[1:])]  # type: ignore[arg-type]
        sigma = statistics.pstdev(rets)
        if sigma == 0:
            return None
        return p_yes(closes[0], self.strike, sigma, self.close_ts - t_ns // NS)  # type: ignore[arg-type]


def _iso_ns(s: str) -> int:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return int(dt.timestamp()) * NS + dt.microsecond * 1000


def windows_in_range(db: sqlite3.Connection, end_close_ts: int) -> list[tuple]:
    return db.execute(
        "SELECT ticker, open_ts, close_ts, strike, result FROM windows WHERE open_ts >= ? AND close_ts <= ? "
        "ORDER BY open_ts", (START_OPEN_TS, end_close_ts)).fetchall()


def load_window(db: sqlite3.Connection, row: tuple) -> WinData:
    ticker, open_ts, close_ts, strike, result = row
    o, c = open_ts * NS, close_ts * NS
    snaps = [Snap(t, [(lvl.price_e4, lvl.size_e2) for lvl in parse_levels_text(y)],
                  [(lvl.price_e4, lvl.size_e2) for lvl in parse_levels_text(n)])
             for t, y, n in db.execute("SELECT t_recv_ns, yes_bids, no_bids FROM books WHERE ticker = ? AND "
                                       "t_recv_ns >= ? AND t_recv_ns < ? ORDER BY t_recv_ns", (ticker, o, c))]
    hits: dict[str, list[tuple[int, int, int]]] = {"yes": [], "no": []}
    for created, yes_price, count_e2, taker in db.execute(
            "SELECT created_time, yes_price_e4, count_e2, taker_side FROM trades WHERE ticker = ?", (ticker,)):
        t = _iso_ns(created)
        if not o <= t < c:
            continue
        if taker == "no":  # taker bought NO -> hit resting YES bids at yes_price
            hits["yes"].append((t, yes_price, count_e2))
        elif taker == "yes":  # taker bought YES -> hit resting NO bids at 1 - yes_price
            hits["no"].append((t, ONE - yes_price, count_e2))
    for side in hits:
        hits[side].sort()
    lo = o - (LOOKBACK_MIN * 60 + 2 * BTC_STALE_S) * NS
    btc = db.execute("SELECT t_recv_ns, price_c FROM btc WHERE t_recv_ns >= ? AND t_recv_ns < ? ORDER BY t_recv_ns",
                     (lo, c)).fetchall()
    return WinData(ticker, open_ts, close_ts, None if strike is None else float(strike),
                   None if result not in ("yes", "no") else result == "yes",
                   snaps, [s.t_ns for s in snaps], hits, {k: [h[0] for h in v] for k, v in hits.items()},
                   [b[0] for b in btc], [b[1] for b in btc])


def m1_times(w: WinData) -> list[int]:
    return [(w.open_ts + 60 + 30 * k) * NS for k in range(24)]


def m2_times(w: WinData, every: bool) -> list[int]:
    return [(w.open_ts + 60 + 60 * k) * NS for k in range(12 if every else 1)]


def cancel_all_ns(w: WinData) -> int:
    return (w.close_ts - 120) * NS


def unusable_reason(w: WinData, gaps: list[tuple[int, int]], trade_errors: list[int]) -> str | None:
    if w.yes_won is None:
        return "no_result"
    if w.strike is None:
        return "no_strike"
    start, end = (w.open_ts + 60) * NS, w.close_ts * NS
    seconds = {t // NS for t in w.snap_t if start <= t < end}
    if len(seconds) < COVERAGE * (w.close_ts - w.open_ts - 60):
        return "book_coverage"
    q0, q1 = (w.open_ts + 60) * NS, cancel_all_ns(w)
    if any(g0 < q1 and g1 > q0 for g0, g1 in gaps):
        return "gap_in_quoting"
    if any(w.close_ts * NS <= t <= (w.close_ts + SWEEP_S) * NS for t in trade_errors):
        return "tape_error"
    for t in m1_times(w):
        if any(w.btc_at(t - 60 * j * NS) is None for j in range(LOOKBACK_MIN + 1)):
            return "btc_missing"
    return None


# --- the fill model ------------------------------------------------------------------------------

@dataclass
class RestingOrder:
    side: str
    price: int  # e4, in our side's terms
    size: int  # e2
    queue: int  # e2 ahead of us
    active_ns: int
    value: float | None = None  # model P(side) at the decision (M1), for the spread/adverse split
    end_ns: int = INF  # cancel effective
    filled: int = 0
    done_ns: int = 0  # tape processed up to here
    last_level: int | None = None  # level size at our price at the last snapshot seen (optimistic mode)

    @property
    def remaining(self) -> int:
        return self.size - self.filled


@dataclass(frozen=True)
class Mode:
    name: str = "base"
    latency_s: float = 1.0
    optimistic_queue: bool = False
    back_only: bool = False  # fills only on trades through our price


BASE = Mode()
SENSITIVITY = [Mode("optimistic queue", optimistic_queue=True), Mode("3 s latency", latency_s=3.0),
               Mode("back of queue only", back_only=True)]


def advance(o: RestingOrder, w: WinData, upto_ns: int, mode: Mode) -> None:
    """Apply the tape (and, in optimistic mode, book snapshots) to one order, up to `upto_ns`."""
    lo, hi = max(o.done_ns, o.active_ns), min(upto_ns, o.end_ns)
    o.done_ns = max(o.done_ns, upto_ns)
    if hi <= lo or o.remaining <= 0:
        return
    hits, times = w.hits[o.side], w.hit_t[o.side]
    i, j = bisect.bisect_right(times, lo), bisect.bisect_right(times, hi)
    if mode.optimistic_queue:
        k, kend = bisect.bisect_right(w.snap_t, lo), bisect.bisect_right(w.snap_t, hi)
    for t, price, count in hits[i:j]:
        if mode.optimistic_queue:
            while k < kend and w.snap_t[k] <= t:
                _shrink_queue(o, w.snaps[k])
                k += 1
        if o.remaining <= 0:
            return
        if price < o.price:  # a taker went through our price: our level was cleared
            o.filled = o.size
        elif price == o.price and not mode.back_only:
            ahead = min(o.queue, count)
            o.queue -= ahead
            o.filled += min(count - ahead, o.remaining)


def _shrink_queue(o: RestingOrder, snap: Snap) -> None:
    level = snap.size_at(o.side, o.price)
    if o.last_level is not None and o.last_level > 0 and level < o.last_level:
        o.queue = o.queue * level // o.last_level  # cancels ahead of us, pro rata (an upper bound)
    o.last_level = level


def tick_size(price: int) -> int:
    return 10 if price < 1000 or price >= 9000 else 100


# --- strategies ---------------------------------------------------------------------------------

@dataclass
class WinResult:
    pnl: int = 0  # e4
    cost: int = 0  # e4, filled cost + fees
    contracts: int = 0  # e2
    quoted: int = 0  # e2
    yes_e2: int = 0
    no_e2: int = 0
    pairs_e2: int = 0
    spread_earned: int = 0  # e4
    adverse: int = 0  # e4
    fees: int = 0  # e4

    @property
    def traded(self) -> bool:
        return self.contracts > 0


@dataclass(frozen=True)
class Variant:
    strategy: str  # 'M1' or 'M2'
    name: str
    margin_c: int = 0
    improve: bool = False
    s_min_c: int = 0
    every_60: bool = False


def variants() -> list[Variant]:
    vs = [Variant("M1", f"margin={m}c {'improve' if imp else 'join'}", margin_c=m, improve=imp)
          for m in (1, 3) for imp in (False, True)]
    vs += [Variant("M2", f"spread>={s}c {'every 60 s' if ev else 'once'}", s_min_c=s, every_60=ev)
           for s in (2, 3) for ev in (False, True)]
    return vs


def _committed_e6(orders: list[RestingOrder], t_ns: int) -> int:
    """Filled cost so far, plus the unfilled remainder of every order whose cancel hasn't taken effect by `t_ns`."""
    return sum(o.price * o.filled + (o.price * o.remaining if o.end_ns > t_ns else 0) for o in orders)


def simulate(v: Variant, w: WinData, mode: Mode = BASE, fee_type: str = "quadratic") -> WinResult:
    lat = int(mode.latency_s * NS)
    orders: list[RestingOrder] = []
    times = m1_times(w) if v.strategy == "M1" else m2_times(w, v.every_60)
    for t in times:
        for o in orders:
            advance(o, w, t, mode)
            o.end_ns = min(o.end_ns, t + lat)  # cancel and replace every round
        snap = w.snap_at(t)
        if snap is None:
            continue
        budget = BUDGET_E6 - _committed_e6(orders, t)
        new = _quote_m1(v, w, snap, t, budget) if v.strategy == "M1" else _quote_m2(v, snap, budget)
        for o in new:
            o.active_ns, o.done_ns = t + lat, t + lat
            o.last_level = snap.size_at(o.side, o.price)
        orders += new
    end = cancel_all_ns(w)
    for o in orders:
        o.end_ns = min(o.end_ns, end + lat)
        advance(o, w, w.close_ts * NS, mode)
    return _settle(orders, w, fee_type)


def _quote_m1(v: Variant, w: WinData, snap: Snap, t: int, budget: int) -> list[RestingOrder]:
    p = w.model(t)
    if p is None:
        return []
    best = None
    for side, value in (("yes", p), ("no", 1 - p)):
        bid, other = snap.best(side), snap.best("no" if side == "yes" else "yes")
        if bid is None:
            continue
        edge = value - bid[0] / ONE
        if edge >= v.margin_c / 100 and (best is None or edge > best[0]):
            best = (edge, side, value, bid, other)
    if best is None:
        return []
    _, side, value, (bid_p, bid_s), other = best
    if v.improve:
        ask = ONE - other[0] if other else ONE
        step = tick_size(bid_p)
        if ask - bid_p < 2 * step:
            return []
        price, queue = bid_p + step, 0
    else:
        price, queue = bid_p, bid_s
    n = budget // (price * 100)
    return [RestingOrder(side, price, n * 100, queue, 0, value)] if n > 0 else []


def _quote_m2(v: Variant, snap: Snap, budget: int) -> list[RestingOrder]:
    yb, nb = snap.best("yes"), snap.best("no")
    if yb is None or nb is None:
        return []
    spread = (ONE - nb[0]) - yb[0]
    if spread < v.s_min_c * 100:
        return []
    n = budget // ((yb[0] + nb[0]) * 100)
    if n <= 0:
        return []
    return [RestingOrder("yes", yb[0], n * 100, yb[1], 0), RestingOrder("no", nb[0], n * 100, nb[1], 0)]


def _settle(orders: list[RestingOrder], w: WinData, fee_type: str) -> WinResult:
    r = WinResult()
    cost_by_side = {"yes": 0, "no": 0}
    for o in orders:
        r.quoted += o.size
        if o.filled <= 0:
            continue
        won = w.yes_won == (o.side == "yes")
        f = int(fee(Decimal(o.filled) / 100, Decimal(o.price) / ONE, maker=True, fee_type=fee_type) * ONE)
        pnl = o.filled * ((ONE if won else 0) - o.price) // 100 - f
        r.pnl += pnl
        r.fees += f
        r.cost += o.filled * o.price // 100 + f
        r.contracts += o.filled
        cost_by_side[o.side] += o.filled * o.price
        if o.side == "yes":
            r.yes_e2 += o.filled
        else:
            r.no_e2 += o.filled
        if o.value is not None:
            r.spread_earned += int(o.filled * (o.value * ONE - o.price) / 100)
    r.pairs_e2 = min(r.yes_e2, r.no_e2)
    if r.pairs_e2 and not any(o.value is not None for o in orders):
        avg_yes = cost_by_side["yes"] / r.yes_e2
        avg_no = cost_by_side["no"] / r.no_e2
        r.spread_earned = int(r.pairs_e2 * (ONE - avg_yes - avg_no) / 100)
    r.adverse = r.pnl - r.spread_earned
    return r


# --- running, caps, metrics ---------------------------------------------------------------------

@dataclass
class VariantRun:
    variant: Variant
    mode: Mode = BASE
    windows: list[tuple[WinData, WinResult]] = field(default_factory=list)  # traded windows only
    quoted_windows: int = 0
    quoted_e2: int = 0
    capped: list[Trade] = field(default_factory=list)
    cap_events: Counter = field(default_factory=Counter)

    def add(self, w: WinData, r: WinResult) -> None:
        self.quoted_e2 += r.quoted
        self.quoted_windows += r.quoted > 0
        if r.traded:
            self.windows.append((_strip(w), r))

    def trades(self) -> list[Trade]:
        out = []
        for w, r in self.windows:
            avg = r.cost * 100 // r.contracts  # e4 per contract, fees included
            out.append(Trade(w.ticker, "yes" if r.yes_e2 >= r.no_e2 else "no", w.open_ts + 60, w.close_ts,
                             avg, r.contracts, 0, "settle", None, 0, r.pnl))
        return out


def _strip(w: WinData) -> WinData:
    """Keep only what reporting needs, so a run doesn't hold every window's tape in memory."""
    return WinData(w.ticker, w.open_ts, w.close_ts, w.strike, w.yes_won, [], [], {"yes": [], "no": []},
                   {"yes": [], "no": []}, [], [])


class _Clock:
    def __init__(self) -> None:
        self.t = datetime(2000, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.t


def apply_caps(run: VariantRun) -> None:
    clock = _Clock()
    rm = RiskManager(kill_switch=KillSwitch(Path("/nonexistent-backtest-root"), environ={}), now=clock)
    trades = run.trades()
    for i, (w, r) in enumerate(run.windows):
        clock.t = datetime.fromtimestamp(w.open_ts + 60, tz=timezone.utc)
        contracts = Decimal(r.contracts) / 100
        order = Order(f"w{i}", run.variant.strategy, w.ticker, "yes", "buy", contracts,
                      (Decimal(r.cost - r.fees) / ONE) / contracts, Decimal(r.fees) / ONE)
        d = rm.check(order)
        if not d.allowed:
            run.cap_events[d.reason.split(":")[0]] += 1
            continue
        rm.record_open(order)
        rm.record_close(order.order_id, Decimal(r.pnl) / ONE, datetime.fromtimestamp(w.close_ts, tz=timezone.utc))
        run.capped.append(trades[i])


def run_all(db: sqlite3.Connection, rows: list[tuple], runs: list[VariantRun], fee_type: str) -> None:
    for row in rows:
        w = load_window(db, row)
        for run in runs:
            run.add(w, simulate(run.variant, w, run.mode, fee_type))
    for run in runs:
        apply_caps(run)


def select(runs: list[VariantRun]) -> dict[str, str]:
    """Pre-registered: highest uncapped mean P&L per traded window, >= 50 traded windows; ties -> earlier."""
    chosen: dict[str, tuple[float, str]] = {}
    for run in runs:
        trades = run.trades()
        if len(trades) < MIN_TRADED:
            continue
        mean = statistics.mean(t.pnl_e4 for t in trades)
        best = chosen.get(run.variant.strategy)
        if best is None or mean > best[0]:
            chosen[run.variant.strategy] = (mean, run.variant.name)
    return {s: name for s, (_, name) in sorted(chosen.items())}


def passes(run: VariantRun) -> bool:
    m = metrics(run.capped)
    return bool(m["trades"]) and m["net"] > 0 and m["ci95"][0] > 0


HEADER = ("| Strat | Variant | Mode | Traded windows | Fill rate | Pairs completed | Net capped | Net uncapped | "
          "Mean/window (95% CI) | Spread earned | Adverse selection | Worst day | Max DD | Cap refusals |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def row_md(run: VariantRun) -> str:
    m, mu = metrics(run.capped), metrics(run.trades())
    filled = sum(r.contracts for _, r in run.windows)
    fill_rate = filled / run.quoted_e2 if run.quoted_e2 else None
    pairs = sum(r.pairs_e2 for _, r in run.windows)
    pair_share = (2 * pairs / filled) if (filled and run.variant.strategy == "M2") else None
    spread = sum(r.spread_earned for _, r in run.windows)
    adverse = sum(r.adverse for _, r in run.windows)
    if not mu["trades"]:
        return f"| {run.variant.strategy} | {run.variant.name} | {run.mode.name} | 0 | – | – | – | – | – | – | – | – | – | – |"
    ci = f"{usd(mu['mean'])} ({usd(mu['ci95'][0])} to {usd(mu['ci95'][1])})"
    return (f"| {run.variant.strategy} | {run.variant.name} | {run.mode.name} | {mu['trades']} | {pct(fill_rate)} | "
            f"{pct(pair_share)} | **{usd(m.get('net', 0))}** | {usd(mu['net'])} | {ci} | {usd(spread)} | "
            f"{usd(adverse)} | {usd(m.get('worst_day'))} | {usd(m.get('max_drawdown'))} | {dict(run.cap_events) or ''} |")


# --- phases ---------------------------------------------------------------------------------------

def usable_rows(db: sqlite3.Connection, end_close_ts: int) -> tuple[list[tuple], Counter]:
    gaps = db.execute("SELECT start_ns, end_ns FROM gaps").fetchall()
    errs = [t for (t,) in db.execute("SELECT t_ns FROM events WHERE kind = 'error:trades'")]
    usable, reasons = [], Counter()
    for row in windows_in_range(db, end_close_ts):
        reason = unusable_reason(load_window(db, row), gaps, errs)
        reasons[reason or "usable"] += 1
        if reason is None:
            usable.append(row)
    return usable, reasons


def split(rows: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    n_train = len(rows) * 2 // 3
    return rows[:n_train], rows[n_train:]


def _git_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def phase_count(db: sqlite3.Connection, end: int, out: Callable[[str], None] = print) -> list[tuple]:
    usable, reasons = usable_rows(db, end)
    out(f"windows in range: {sum(reasons.values())}; usable: {len(usable)} (minimum {MIN_USABLE})")
    out(f"by reason: {dict(reasons)}")
    if len(usable) < MIN_USABLE:
        out("BELOW MINIMUM: extend --end by whole days (record the amendment in the pre-registration first).")
    return usable


def phase_train(db: sqlite3.Connection, end: int, fee_type: str, docs: Path = ROOT / "docs") -> dict[str, str]:
    usable, reasons = usable_rows(db, end)
    if len(usable) < MIN_USABLE:
        sys.exit(f"only {len(usable)} usable windows (< {MIN_USABLE}); extend the end date per the pre-registration")
    train, _ = split(usable)
    runs = [VariantRun(v) for v in variants()]
    run_all(db, train, runs, fee_type)
    chosen = select(runs)
    lines = ["# R1 maker test: train results (all 8 variants, in-sample)\n",
             f"*Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m slot.maker train` at commit "
             f"{_git_head()}. Usable windows {len(usable)} of {sum(reasons.values())} ({dict(reasons)}); train = "
             f"first {len(train)}. Fee type at analysis: `{fee_type}`. Pessimistic queue model, 1 s latency.*\n",
             "In-sample, with 8 variants tried. Only the test set (`docs/r1-test.md`) counts.\n", HEADER]
    lines += [row_md(r) for r in runs]
    lines += ["", "## Selected for the test set (pre-registered rule)", ""]
    lines += [f"- **{s}:** {name}" for s, name in chosen.items()] or ["- none"]
    for s in sorted({v.strategy for v in variants()} - set(chosen)):
        lines.append(f"- {s}: no variant reached {MIN_TRADED} traded windows (not tested).")
    (docs / "r1-train.md").write_text("\n".join(lines) + "\n")
    (docs / "r1-selection.json").write_text(json.dumps(
        {"chosen": chosen, "usable": len(usable), "train": len(train), "end_close_ts": end, "commit": _git_head()},
        indent=2) + "\n")
    return chosen


def phase_test(db: sqlite3.Connection, end: int, fee_type: str, docs: Path = ROOT / "docs",
               require_commit: bool = True) -> list[VariantRun]:
    sel_path = docs / "r1-selection.json"
    if not sel_path.exists():
        sys.exit("run the train phase first")
    if require_commit:
        dirty = subprocess.run(["git", "status", "--porcelain", str(sel_path)], cwd=ROOT, capture_output=True, text=True)
        if dirty.stdout.strip():
            sys.exit("commit docs/r1-selection.json before running the test set")
    sel = json.loads(sel_path.read_text())
    usable, _ = usable_rows(db, sel["end_close_ts"])
    _, test = split(usable)
    by_name = {(v.strategy, v.name): v for v in variants()}
    chosen = [by_name[(s, n)] for s, n in sel["chosen"].items()]
    runs = [VariantRun(v) for v in chosen] + [VariantRun(v, m) for v in chosen for m in SENSITIVITY]
    run_all(db, test, runs, fee_type)
    official = [r for r in runs if r.mode == BASE]
    lines = ["# R1 maker test: test results (out-of-sample, run once)\n",
             f"*Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m slot.maker test` at commit "
             f"{_git_head()}. Test = last {len(test)} of {len(usable)} usable windows. Fee type: `{fee_type}`.*\n",
             HEADER] + [row_md(r) for r in official]
    lines += ["", "## Verdicts (pass = capped net > 0 and 95% CI of mean per traded window above 0)", ""]
    for r in official:
        m = metrics(r.capped)
        verdict = "**passes R1**" if passes(r) else "**does not pass R1**"
        ci = m.get("ci95")
        lines.append(f"- **{r.variant.strategy} ({r.variant.name}):** {verdict}. Capped: {m['trades']} traded windows, "
                     f"net {usd(m.get('net', 0))}, CI {usd(ci[0]) if ci else '–'} to {usd(ci[1]) if ci else '–'}.")
    lines += ["", "## Sensitivity (NOT the result; shows how much the fill model matters)", "", HEADER]
    lines += [row_md(r) for r in runs if r.mode != BASE]
    (docs / "r1-test.md").write_text("\n".join(lines) + "\n")
    return official


def _end_allowed(end: int) -> None:
    if end == END_CLOSE_TS:
        return
    if end < END_CLOSE_TS:
        sys.exit("--end can only push the pre-registered end later")
    day = datetime.fromtimestamp(end, tz=timezone.utc).date().isoformat()
    text = PREREG.read_text()
    if "Amendment" not in text or day not in text:
        sys.exit(f"record an amendment naming {day} in {PREREG.name} before extending the end date")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["count", "train", "test"])
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument("--end", type=lambda s: int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()),
                   default=END_CLOSE_TS, help="UTC close cutoff, e.g. 2026-10-29T05:00 (extension only)")
    p.add_argument("--fee-type", default=None, help="default: read from GET /series/KXBTC15M at analysis time")
    args = p.parse_args()
    now = datetime.now(timezone.utc).timestamp()
    if args.db.resolve() == DB_PATH.resolve() and now < max(args.end, END_CLOSE_TS):
        sys.exit("refusing: the approved pre-registration allows no analysis of the recording before "
                 f"{datetime.fromtimestamp(max(args.end, END_CLOSE_TS), tz=timezone.utc):%Y-%m-%d %H:%M} UTC")
    _end_allowed(args.end)
    fee_type = args.fee_type
    if fee_type is None:
        from slot.kalshi import KalshiClient
        with KalshiClient() as k:
            fee_type = k.series()["fee_type"]
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    if args.phase == "count":
        phase_count(db, args.end)
    elif args.phase == "train":
        print(phase_train(db, args.end, fee_type))
    else:
        phase_test(db, args.end, fee_type)


if __name__ == "__main__":
    main()
