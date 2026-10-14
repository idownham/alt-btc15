# alt-btc15 (Project Slot Machine) — Spec

*Written 2026-10-13 from the planning chat. Owner: Ian Downham.*

## The market
Kalshi `KXBTC15M`: "Will BTC be up/above the target price at the end of this 15-minute window?" A new market opens as
the previous one closes, 24/7. YES pays $1, NO pays $0. Contracts can be sold any time before close.
Fair value at any moment depends on: BTC's current price vs the target, time remaining, and BTC's short-term volatility.

## Strategies (each tracked, capped and gated separately)
**A. Direction at open, hold to expiry.** At the window's open (~50¢), predict up/down from a signal and hold to
settlement (no exit fee). Break-even ≈ 52% accuracy at 50¢ after the taker entry fee. Candidate signals: BTC
momentum / mean reversion over the last 5–60 min, time of day, Kalshi's own opening lean.

**B. Open scalp (Ian's rule).** Enter near the open, rest a sell at entry **+10¢**; exit on a stop (default −25¢ ≈
−$2.50 on a $5 stake) or a time limit, else hold to expiry. Variants to test: +5/+10/+15¢ targets; 10 s / 60 s /
5 min / hold time limits; with and without a stop. Rough break-even with a symmetric ±10¢ stop ≈ 63%.

**C. Late favorite (Ian's rule).** Entry only with **60–180 s left** (approved 2026-10-13, see decisions.md) when BTC is
well past the target and the contract trades ~90–97¢; buy the favorite **only if model fair value exceeds the ask by a
margin** (after fees). At 95¢, risking ~95¢ to win ~4.7¢ requires true probability > ~95.5%. The model is the whole
edge here. Entries with < 60 s left are out of scope for C (there the edge is replicating BRTI, not BTC volatility).

**D. Longshot fade.** Cheap contracts (≤ 10¢) late in the window may be overpriced by retail. Test selling/buying the
other side when model fair value is well below the price. Pattern-level edge, not a speed race.

**E. (Later) Fair-value gaps.** Trade whenever Kalshi lags the model by more than spread + fees. Likely a speed race
vs professional bots; measure gap size/duration from our host before considering it.

## Fair-value model (average-aware; approved by Ian 2026-10-13)
Kalshi settles on the **simple average of the 60 one-second BRTI prints before close** vs a target K that is the same
60-s average before open (S0 finding, `docs/s0-research.md` §1). With BTC treated as a driftless random walk:

`P(YES) = N((M − K) / sd)`, with σ$ = σ · S dollars per √second, and τ = seconds left:
- **τ ≥ 60 s:** M = S (live BTC proxy), sd = σ$ · √(τ − 40)  (i.e. τ_eff = τ − 40 s)
- **τ < 60 s:** M = [(60 − τ) · A_known + τ · S] / 60, sd = σ$ · √(τ³ / 10,800), where A_known is the average of
  the proxy's 1-s prices already inside the final minute.

σ = recent realized volatility of 1-min log returns (test 5/15/60-min lookbacks; tune on the first 2/3 of data only).
S is a proxy (Coinbase; BRTI is not free), so proxy error is part of the model's error and is reported, not hidden.
Outcomes in backtests always come from Kalshi's `result`, never from the proxy.
*Replaces the single-print `N(d)`, `d = ln(S/K)/(σ·√τ)`, which overstates uncertainty late in the window.*

## Stages
**S0 — Research + plumbing (no trading).** Settlement rules/source; fee type + multiplier for `KXBTC15M`; tick
size, min size; market listing/open/close timing; historical data available (Kalshi trades/candlesticks for past
windows; BTC 1-min history from a public exchange); rate limits. Build Kalshi + BTC data clients. Write
`docs/s0-research.md` with sources.

**S1 — Backtest.** Reconstruct past windows (≥ 3 months of BTC 1-min data; Kalshi history as available). Test A–D
with honest fills (where Kalshi book history is missing, say so and use conservative assumptions). Split data:
tune on the first 2/3, report on the last 1/3 only once. Output per strategy: trades, win rate vs break-even, net P&L
after fees, worst day, max drawdown.

**S1 fill rule (approved by Ian 2026-10-13).** Kalshi has no order-book history, only 1-min candlesticks
(yes_bid / yes_ask / trade OHLC). Every backtest fill uses the **worst price in that minute**:
- buy YES at the minute's **yes_ask high**; buy NO at **1 − yes_bid low** (the worst NO ask);
- sell YES at the minute's **yes_bid low**; sell NO at **1 − yes_ask high**;
- entry and exit in the same minute: take the worse of the two possible orderings;
- resting limit exits (B's +10¢) fill only if the minute's **trade high** (low, for NO) goes *past* the price, not just
  touches it; check against the trade tape on a sample of windows;
- prices snapped to the tick grid in force that day (`linear_cent` before 2026-03-17, `tapered_deci_cent` after);
- depth is assumed enough for ≤ $5 orders. This is an assumption, stated in every S1 report, not a measurement;
- fees: conservative taker fee (ceil to the cent per order) on every taking fill, none on settlement.
S2 replaces all of this with real depth-walked fills from the recorded live book (rule 5).

**S2 — Live paper trader.** Runs on Ian's laptop (owner decision 2026-10-13); gaps from sleep/offline are logged and excluded, not hidden. Polls Kalshi book + BTC price, runs every
strategy simultaneously, logs every would-be order/fill/skip, enforces the caps exactly as live would.
Daily report: per-strategy P&L, trades, win rate, cap hits.

**S3 — Small live.** Only strategies that pass the gate, only after Ian's dated decision. Own server and keys.
Same caps. Circuit breaker vs paper results.

## Risk caps (hard-coded; same in paper and live)
$5 max per trade · $25 max net loss per day (Chicago calendar day) · $100 max total net loss → permanent halt
until owner resets. Kill switch: `STOP` file or `KILL=1`.
**Scope in paper (S2), Ian 2026-10-13:** the $25/day cap applies **per strategy**: each strategy has its own ledger,
so one strategy's losing day doesn't halt the others. $5/trade applies to every order. The kill switch stops
everything. Still open: whether the $100 total is per strategy or shared in paper, and the cap scope for live (S3).

## Go-live gate (pre-registered — PROPOSED, Ian to confirm before S2 starts)
Per strategy, all of:
- ≥ 7 days and ≥ 200 trades of live paper trading (S2), with no code/parameter changes during the window;
- paper net P&L after fees > 0 and win rate above that strategy's computed break-even;
- backtest (S1) out-of-sample result also net positive.
Live circuit breaker: halt a strategy automatically if its live P&L after ≥ 50 trades is more than 2 standard
deviations below its paper P&L per trade.

## Logs and reports
SQLite tables (at minimum): `windows` (market, target, open/close, settlement), `quotes` (book snapshots),
`btc_ticks`, `signals`, `orders`, `fills`, `skips` (reason), `risk_events`, `pnl_daily`.
CLI: `python -m slot.report --day YYYY-MM-DD` and `--strategy X`.

## Timeline (proposed)
| When | Step |
|---|---|
| This week | S0 research + data clients |
| Next week | S1 backtest |
| After S1 | S2 paper trader 24/7 (≥ 7 days) |
| After gate | S3 small live (owner decision) |
Coin Toss recording (Oct 17–22) and the Oct 25 / Nov 8 class checkpoints take priority if time is tight.
