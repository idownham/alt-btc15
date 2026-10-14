# S1 backtest — pre-registration

*Written and committed 2026-10-13 (CDT), **before any S1 data was pulled or any strategy result was seen**. Strategy
parameters, the split, the selection rule and the metrics below are fixed. Any change gets a dated note here with the
reason before new results are looked at. The go-live gate in `spec.md` is not touched by this document.*

Approved inputs used here (decisions.md 2026-10-13): the average-aware fair-value model, C's entry band of 60–180 s,
worst-price-in-minute fills, and $25/day + $100 total caps per strategy.

## Data
- **Windows:** every KXBTC15M window that closes from **2026-06-01 00:00 UTC to 2026-10-13 00:00 UTC** (134 days,
  about 12,900 windows). Why this range: ≥ 3 months as the spec requires; all of it on the current 0.1¢/1¢ tick grid;
  recent enough to reflect today's much higher volume. Pull cost: about 7,100 per-window requests for the pre-cutoff
  part, run paced at ≤ 2 req/s.
- **Outcomes:** Kalshi `result` only. Skipped and counted: windows with a missing strike, `strike < 1000`
  (data errors like 7.24), no `result`, or missing candles.
- **Kalshi prices:** 1-min candlesticks. Candle *k* (k = 1..15) covers (open + 60(k−1), open + 60k]. The candle
  ending exactly at the open is the empty pre-open book (ask $1.00 / bid ≈ 0) and is never used.
- **BTC:** Coinbase BTC-USD 1-min candles. S at time *t* = close of the candle that ended at *t*.

## No look-ahead
A decision at time *t* uses only Kalshi candles ending ≤ *t* and BTC candles ending ≤ *t*. The order fills in the next
minute, (t, t+60]. Kalshi's strike is known at the open.

## Fills and fees (approved worst-in-minute rule)
- Buy at that minute's **worst ask** for our side: YES = yes_ask high; NO = 1 − yes_bid low.
  An ask of $1.00 means nobody is selling, so there is **no fill** (counted as a skip).
- Sell (stop or time exit) at the **worst bid**: YES = yes_bid low; NO = 1 − yes_ask high. A bid of $0 means no fill;
  the order tries again the next minute, and the position is held to settlement if no minute fills.
- Resting take-profit (B): fills in a minute only if our side's trade price goes *past* the target
  (YES: trade high > target; NO: 1 − trade low > target). Never in the entry minute. If a stop and a target are both
  possible in the same minute, the stop counts (the worse ordering).
- Size: the largest whole number of contracts *n* with n × fill price + fee ≤ **$5**.
- Fees: taker 0.07·n·P·(1−P) rounded **up to the cent** per order on every buy, stop and time exit. A resting target
  pays no fee (maker, `quadratic` series). Settlement is free.
- Caps: one `RiskManager` per strategy variant ($5/trade, $25/Chicago day, $100 total, all per strategy). The **official
  result is with caps**. Uncapped numbers are also shown.

## Fair-value model (approved 2026-10-13)
P(YES) = N((S − K) / sd), sd = σ$ · √(τ − 40) for τ ≥ 60 s. σ$ = sd(1-min log returns over the last *L* min) · S / √60.
(All entries in S1 fill with τ ≥ 60 s, so the τ < 60 branch isn't used.) If σ = 0, skip.

## Strategies and parameter grids
Notation: T0 = open, T1 = close.

**A. Direction at open, hold to settlement.** Decide at T0, fill in minute 1. Side from the signal (skip if 0):
`mom5, mom15, mom60` = sign(S_T0 − S_{T0−L}); `rev5, rev15, rev60` = the opposite; `lean` = sign(S_T0 − K);
`antilean` = the opposite. **8 variants.**

**B. Open scalp (Ian's rule).** Same entry as A. Side ∈ {`lean`, `mom15`} × target ∈ {+5, +10, +15¢} (rounded up to the
tick; no target if it would reach ≥ $1) × stop ∈ {none, −25¢} × time limit ∈ {1 min, 5 min, hold}. A time exit sells in
minute 1 + limit at the worst bid; targets and stops are checked from minute 2. **36 variants.** (A 10 s limit can't be
resolved with 1-min data, so it is not tested in S1; S2 will test it.)

**C. Late favorite.** Decide at T1 − 180 s, then T1 − 120 s (first that qualifies; at most one trade per window). The fill
lands in the next minute, so every entry is 60–180 s before close. Favorite = the side with model P > 0.5. Its observed
ask (close of the candle ending at *t*) must be in [0.90, 0.97], and P − ask − fee per contract ≥ margin.
Margin ∈ {0, 1¢, 2¢} × L ∈ {5, 15, 60}. **9 variants.**

**D. Longshot.** Decide at T1 − 360, −300, −240 s (first that qualifies). Longshot = the side whose observed ask ≤ 10¢.
`fade`: buy the favorite if (1 − P_long) − favorite ask − fee per contract ≥ margin. `buy`: buy the longshot if
P_long − longshot ask − fee per contract ≥ margin. Direction ∈ {fade, buy} × margin ∈ {2¢, 5¢} × L ∈ {15, 60}.
**8 variants.**

Total: 61 variants. With this many tries, the best training result will look good by luck. That's why only one variant per
strategy goes to the test set.

## Split and selection
- **Train:** windows closing 2026-06-01 → 2026-08-29 00:00 UTC (≈ 2/3). **Test:** 2026-08-29 → 2026-10-13 (≈ 1/3).
- On train, each strategy's chosen variant is the one with the highest **capped net P&L among variants with ≥ 30
  trades**. Ties go to the earlier variant in the list above.
- The test set is run **once**, for the 4 chosen variants only. All train results for all 61 variants are published.

## Reported per chosen variant (test set)
Trades; skips by reason; win rate; break-even win rate (= avg loss / (avg win + avg loss)); net P&L after fees, capped
and uncapped; mean P&L per trade with a 95% CI; worst Chicago day; max drawdown; cap events.
**S1 verdict per strategy:** "passes S1" only if capped net P&L on the test set is > 0. That is the spec's gate input
("backtest out-of-sample result also net positive"). Whether the CI excludes 0 is reported as information.

## Sensitivity (reported, never used for selection or the verdict)
The same chosen variants, re-run on test with fills at the minute's **close** quote instead of the worst. This shows
how much the harsh fill rule costs. It is clearly labeled and not an S1 result.

## Known limitations (stated up front)
Coinbase is only a proxy for BRTI. There is no depth history, so ≤ $5 is assumed to fill. Whole contracts only.
Sizing uses the fill price. Within-minute timing is unknown.

## Amendment 1 — 2026-10-13 (CDT), after a 3-day plumbing test pull, before any strategy code or results
**Finding:** Kalshi's candles run k = 1..15 (no candle ends at the open). Candle 1 includes the open itself: in the
trial pull (119 windows, 2026-08-12 → 08-15), 85% of candle-1s have a yes_ask high ≥ 99¢ and a bid low ≤ 1¢ from the
empty book at the open. Minutes 2–10 had none. Under the worst-in-minute rule, any minute-1 entry would "fill" at
~$1.00. That is an artifact of the opening book, not a price anyone could trade at.
**Change:** A and B decide at **T0 + 60 s** (with data up to then) and fill in **minute 2**. B's time exits shift by
one minute (1 min → exit in minute 3; 5 min → minute 7), and targets/stops are checked from minute 3. The signals use
S and the lean at T0 + 60 s. Nothing else changes. The sentence above about "the candle ending exactly at the open" is
wrong and is replaced by this note.
**Also seen (plumbing, not results):** the average range between the worst ask and the worst bid within one minute
was about 15–17¢ in minutes 2–10, so the worst-in-minute rule costs a lot per round trip. That is the point of a
pessimistic rule, and the pre-registered close-price sensitivity will show how much.
