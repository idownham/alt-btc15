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

**C. Late favorite (Ian's rule).** Near the end (e.g., ≤ 60–120 s left) when BTC is well past the target and the
contract trades ~90–97¢, buy the favorite **only if model fair value exceeds the ask by a margin** (after fees).
At 95¢, risking ~95¢ to win ~4.7¢ requires true probability > ~95.5%. The model is the whole edge here.

**D. Longshot fade.** Cheap contracts (≤ 10¢) late in the window may be overpriced by retail. Test selling/buying the
other side when model fair value is well below the price. Pattern-level edge, not a speed race.

**E. (Later) Fair-value gaps.** Trade whenever Kalshi lags the model by more than spread + fees. Likely a speed race
vs professional bots; measure gap size/duration from our host before considering it.

## Fair-value model
Probability BTC ends above target K at expiry: digital-option style `P = N(d)`, `d = ln(S/K) / (σ·√τ)` (drift ≈ 0
at this horizon), with S = live BTC, τ = time left, σ = recent realized volatility (test 5/15/60-min lookbacks).
**S0 must confirm exactly how Kalshi settles** (which index, single print vs. average over the final seconds) and the
model must match it — this matters most for strategy C.

> **S0 finding (2026-10-13):** settlement = simple average of the 60 one-second BRTI prints before close; target =
> the same average before open. `N(d)` with τ = time left overstates uncertainty late in the window (use τ − 40 s for
> τ ≥ 60 s, and the running average for τ < 60 s). Proposed model and C entry band: `docs/s0-research.md` §7, pending Ian.

## Stages
**S0 — Research + plumbing (no trading).** Settlement rules/source; fee type + multiplier for `KXBTC15M`; tick
size, min size; market listing/open/close timing; historical data available (Kalshi trades/candlesticks for past
windows; BTC 1-min history from a public exchange); rate limits. Build Kalshi + BTC data clients. Write
`docs/s0-research.md` with sources.

**S1 — Backtest.** Reconstruct past windows (≥ 3 months of BTC 1-min data; Kalshi history as available). Test A–D
with honest fills (where Kalshi book history is missing, say so and use conservative assumptions). Split data:
tune on the first 2/3, report on the last 1/3 only once. Output per strategy: trades, win rate vs break-even, net P&L
after fees, worst day, max drawdown.

**S2 — Live paper trader.** Runs on Ian's laptop (owner decision 2026-10-13); gaps from sleep/offline are logged and excluded, not hidden. Polls Kalshi book + BTC price, runs every
strategy simultaneously, logs every would-be order/fill/skip, enforces the caps exactly as live would.
Daily report: per-strategy P&L, trades, win rate, cap hits.

**S3 — Small live.** Only strategies that pass the gate, only after Ian's dated decision. Own server and keys.
Same caps. Circuit breaker vs paper results.

## Risk caps (hard-coded; same in paper and live)
$5 max per trade · $25 max net loss per day (Chicago calendar day) · $100 max total net loss → permanent halt
until owner resets. Kill switch: `STOP` file or `KILL=1`.

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
