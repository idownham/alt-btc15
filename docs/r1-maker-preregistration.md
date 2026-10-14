# R1 maker test — pre-registration

*Written 2026-10-14 (CDT) by Claude, **before any analysis of the recorded book or tape**. Up to now the recorded data
has only had health checks (row counts, gaps, errors, schema).*
**Status: APPROVED by Ian, 2026-10-14, as written (decisions.md).** Before approval, Ian could approve, revise or reject it. Nothing below is analyzed until an approval is recorded in
`docs/decisions.md`. Changes after approval get a dated amendment here, with the reason, before new results are seen.

Context: S1 tested only entries that take an existing price and found no edge for A–D (`docs/s1-results.md`).
KXBTC15M charges **no maker fee** (`fee_type: quadratic`). This test asks one question: **can resting orders
earn the spread, after adverse selection, on this market?** It uses the order book and trade tape recorded by the R1
recorder (`src/slot/recorder.py`).

## 1. Data

**Range.** Windows that open at or after **2026-10-14 20:15 UTC** (the first full window after the paced-tape fix was
deployed) and close at or before **2026-10-28 05:00 UTC** (midnight 2026-10-28 Chicago). That is about 13⅓ days, at
most 1,283 windows.

**Usable window.** A window counts only if **all** of these hold. Failures are counted by reason.
- Book snapshots cover ≥ 95% of the seconds from open+60 to close (any second with no snapshot counts as missing).
- No logged gap overlaps the quoting period (open+60 to close−120).
- The trade tape was fetched through the close: the recorder's sweep finished, with no `error:trades` event for that
  ticker after its close.
- A result (`yes`/`no`) is recorded.
- A BTC price exists for every decision time, with the σ lookback covered.

**Minimum size.** At least **900 usable windows**. If the range above yields fewer, the end date is pushed back in whole
days until it doesn't, checking only the count of usable windows (no results). The extension and the reason are
recorded here.

**Split.** Usable windows in time order: the first 2/3 are **train**, the last 1/3 are **test**. The test set is run
**once**, for the variants chosen on train.

## 2. Fill model (pessimistic, queue-aware)

Notation: a resting **YES bid at p** is matched by takers buying NO, which shows on the tape as
`taker_side = 'no'` at `yes_price = p`. A resting **NO bid at q** is matched by takers buying YES:
`taker_side = 'yes'` at `yes_price = 1 − q`.

1. **Decision** at time *t* uses the newest book snapshot with `t_recv ≤ t` and BTC prices ≤ *t*. Nothing later.
2. **Placement latency.** The order rests from *t* + **1.0 s**. Only trades with `created_time` > *t* + 1.0 s can fill it.
3. **Queue position.** If the order joins an existing level, the size already at that price (from the decision
   snapshot) is ahead of it. If it improves the price (a new level), nothing is ahead.
   **Cancels ahead of us never move us forward**: the queue shrinks only through trades.
4. **Fills.**
   - Trades on our side at **exactly** our price consume the queue ahead first, then us.
   - A trade on our side at a price **worse than ours for the taker** (YES bid: `yes_price < p`) means our level was
     cleared, so whatever remains of our order fills in full.
   - Partial fills are allowed, in 0.01-contract steps. Fills are never counted from trades on the other side of the book.
5. **Cancel latency.** A cancel takes effect **1.0 s** after it is decided. Fills during that second count.
6. **Fees.** Maker fills: the series' maker rate at analysis time (0 for `quadratic`). If Kalshi has changed the fee
   type by then, the real rate is used. Taker exits (none are planned below): 0.07·C·P·(1−P), ceil to the cent.
   Settlement is free.
7. **Not modeled.** Our order's effect on other traders, and hidden or iceberg size. Both are negligible at ≤ $5. If the
   1-s snapshots miss a level that briefly appeared, the model can only miss fills (pessimistic), never invent them.

## 3. Fair value (as approved 2026-10-13)

P(YES) = N((S − K)/sd), sd = σ$ · √(τ − 40), σ$ = sd(1-min log returns over the last **15 min**) · S / √60.
S is the recorded Coinbase price at *t*, K is the window's strike, and τ is seconds to close. Quoting stops at
τ = 120 s, so the τ < 60 branch is never needed.

## 4. Strategies and grids (8 variants)

All variants quote only from **open + 60 s to close − 120 s**, hold every filled contract to settlement, and keep each
window's **total cost of filled contracts ≤ $5**: a resting order's size is the remaining budget divided by its price,
in whole contracts.

**M1. Fair-value bid (one side).** Every 30 s (open+60, +90, …, close−120), compute P. For the side where
P_side − best bid ≥ **margin**, rest a bid at the **join** price (the best bid) or the **improve** price (best bid +
1 tick, only if the spread is ≥ 2 ticks). At the next decision time, cancel and replace the order (going to the back
of the queue), or just cancel it if the condition no longer holds. Only one side is quoted at a time; if the favored
side flips, the old bid is cancelled.
Grid: margin ∈ {1¢, 3¢} × placement ∈ {join, improve} → **4 variants.**

**M2. Pair capture (both sides).** If the spread (YES ask − YES bid) is ≥ **s_min**, rest a YES bid at the best YES bid
**and** a NO bid at the best NO bid. If both fill, the pair costs 1 − spread and pays exactly $1: a locked gain with no
fees. Size per side n = whole contracts with n × (YES bid + NO bid) ≤ $5. Quotes are placed either **once** (at
open+60) or **requoted every 60 s** (cancel and replace both sides at the then-best bids; already-filled contracts
stay). Any unpaired contracts at close − 120 are held to settlement (directional risk, which is the adverse-selection
cost being measured).
Grid: s_min ∈ {2¢, 3¢} × quoting ∈ {once, every 60 s} → **4 variants.**

## 5. Caps

One `RiskManager` per variant, as approved: $5 per window position, $25 per Chicago day, $100 total, all per
strategy. The official numbers are **with caps**; uncapped numbers are shown too.

## 6. Selection and pass rule

Lesson from S1, where selecting on capped P&L mostly picked the smallest loser because nearly every variant hit the
$100 halt:
- **Selection (train):** for each of M1 and M2, the variant with the highest **uncapped mean P&L per traded window**,
  among variants with ≥ **50 traded windows**. Ties go to the earlier variant in the order listed.
  The selection is committed before the test run (the engine refuses otherwise, as in S1).
- **Pass (test, run once):** a strategy **passes R1** only if, on test, its **capped net P&L > 0 and the 95% CI of
  mean P&L per traded window is entirely above 0**. That is stricter than S1, which required only net > 0, because
  the queue model is the biggest uncertainty and the bar should be above noise.
- A pass is an input to the existing go-live gate (≥ 7 days of paper with no changes, etc.). It is not permission to
  trade. Paper trading a maker strategy would itself need a new decision.

## 7. Reported (train: all 8 variants; test: the chosen ones)

Traded windows; fill rate (filled ÷ quoted contracts); for M2, the share of pairs completed vs left one-sided; P&L split
into **spread earned** (locked pairs, and fill price vs model value) and **adverse selection** (settlement loss on
one-sided fills); net P&L capped and uncapped; mean per traded window with 95% CI; worst Chicago day; max drawdown;
cap events; usable-window counts by reason.

**Sensitivity (reported, never used for selection or the verdict):**
(a) **optimistic queue**: cancels ahead of us move us forward in proportion to the level's size drop between snapshots;
(b) **slower**: 3.0 s placement and cancel latency;
(c) **back of the queue for everything**: an order fills only on trades through its price.
These show how much the result depends on the queue model.

## 8. Known limits (stated up front)

- Book snapshots are 1 s apart, so queue position between snapshots is inferred from trades only.
- Trade timestamps are Kalshi's and snapshot timestamps are ours (≈ 50 ms apart); the 1 s latency covers this.
- Two weeks of one market in one season (Oct 2026); a BTC volatility regime change could flip the result.
- Coinbase stands in for BRTI in the fair-value model (M1 only; M2 uses no model).
