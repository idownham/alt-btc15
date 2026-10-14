# Decisions (alt-btc15 / Project Slot Machine)

Dated owner decisions. Newest last. Gate or cap changes must be recorded here before looking at new results.

---

## 2026-10-13 — Start Project Slot Machine
**Decision (Ian):** build an automated system for Kalshi's 15-minute BTC markets. Paper first, then live.
**Risk caps:** $5/trade, $25/day loss, $100 total loss — hard-coded.
**Strategies:** A direction-at-open hold to expiry; B open scalp (+10¢ target, wide stop ~−$2.50 on $5); C late
favorite; D longshot fade. (E fair-value gaps later.)
**Host:** paper phase may share Osprey's droplet; live phase gets its own server.
**Framing (Ian):** "This is definitely gambling but maybe fun. It's low risk and I can afford it. Just need to win
more than we lose (after fees)."
**Pending:** Ian to confirm the proposed go-live gate in `spec.md` before S2.

## 2026-10-13 — Run on the laptop for now
**Decision (Ian):** Slot Machine runs on his laptop, not Osprey's droplet. Replaces the earlier "paper phase may
share Osprey's droplet" note. Live phase still requires its own server, decided at the go-live gate.
**Consequence:** sleep/offline gaps will miss windows; every gap is logged so paper results stay honest. Shares the
laptop's Kalshi rate budget with Coin Toss's recorder.

## 2026-10-13 — Average-aware fair-value model; strategy C entry band 60–180 s
**Decision (Ian):** approve the average-aware fair-value model from `docs/s0-research.md` §7 (now in `spec.md`
"Fair-value model") and set strategy C's entry band to **60–180 s before close**.
**Evidence:** S0 found settlement = 60-s BRTI average before close, target = 60-s average before open. The
single-print model overstates late-window uncertainty (e.g. $30 ahead with 30 s left: 0.89 naive vs ≈1.00
average-aware). Below 60 s, the remaining uncertainty is about the size of our Coinbase-vs-BRTI proxy error (~$5 median).
**Consequence:** S1/S2 use this model for C and D. C does not enter with < 60 s left. Recorded before any strategy
results were looked at.
**Not decided here:** a separate "< 60 s" C variant; S1 fill assumption; risk-cap scope in paper; second BTC
source; go-live gate (all still pending, s0-research §9).

## 2026-10-13 — S1 backtest fills: worst price in the minute
**Decision (Ian):** approve the conservative S1 fill rule (`docs/s0-research.md` §5, now in `spec.md` under S1).
Buys fill at the worst ask of that minute, sells at the worst bid. Same-minute round trips take the worse ordering.
Resting exits fill only when trades go through the price. Depth is assumed sufficient for ≤ $5 and stated as an assumption.
**Evidence:** Kalshi serves 1-min candlesticks and the trade tape for every past window but **no order-book
history**, so rule 5's depth walk is impossible in a backtest.
**Consequence:** a scoped exception to CLAUDE.md rule 5 for S1 only (noted there). Backtest P&L is biased
pessimistic. S2 paper trading uses real depth-walked fills. Recorded before any S1 results exist.

## 2026-10-13 — Paper trading: $25/day cap per strategy
**Decision (Ian):** in paper trading (S2), the $25 daily loss cap is applied **separately to each strategy**.
**Reason:** strategies A–D run at the same time and are gated separately. A shared cap would let one strategy's bad day
stop the others from collecting paper evidence.
**Consequence:** S2 keeps one `RiskManager` ledger per strategy for the daily cap ($5/trade and the kill switch are
unchanged). **Not decided:** whether the $100 total cap is per strategy or shared in paper; cap scope for live (S3).

## 2026-10-13 — Paper trading: $100 total cap per strategy
**Decision (Ian):** in paper trading (S2), the $100 total loss cap is also applied **separately to each strategy**.
**Consequence:** each strategy's ledger halts permanently on its own at −$100 net (until a dated owner reset entry
naming it). The other strategies keep running. With the per-strategy $25/day cap (entry above), each strategy is
capped exactly as it would be if it ran alone. **Not decided:** cap scope for live (S3), set at the go-live gate.

## 2026-10-13 — S1 pre-registration amendment 1 approved (A and B enter in minute 2)
**Decision (Ian):** approve amendment 1 in `docs/s1-preregistration.md`. A and B decide at open + 60 s and fill in
minute 2; B's time exits and target/stop checks shift by one minute.
**Evidence:** in a 119-window plumbing pull, 85% of minute-1 candles carry the empty opening book (ask ≥ 99¢, bid ≤ 1¢),
so a minute-1 entry under the worst-in-minute rule would "fill" at ~$1.00, a price nobody could trade at.
**Consequence:** A and B are tested one minute after open rather than at the open itself. Approved before any S1
strategy result was seen (the pull was still running).

## 2026-10-14 — Stop Slot Machine at S1
**Decision (Ian):** stop the project at S1. No S2 paper trading and no live trading.
**Evidence:** `docs/s1-results.md`. None of A–D passed the pre-registered out-of-sample test. A, B and C lose even with
generous close-quote fills (mean per trade −$0.29, −$0.35, −$0.11; CIs below 0). D is ≈ 0 (−$0.13 harsh / +$0.03
generous; CIs include 0).
**Consequence:** the outcome is a well-evidenced "no edge after spread and fees" on KXBTC15M at 1-minute speed. No
service was ever deployed, and no keys or order code exist. Code and data stay as the evidence trail. Reopening needs a
new dated entry here.

## 2026-10-14 — Reopen Slot Machine for idea 1: record the KXBTC15M order book (stage R1)
**Decision (Ian):** reopen the project to build a **read-only live order-book recorder** for KXBTC15M, the first step
toward testing a resting-order (maker) strategy (s1-results.md, "What S1 did not test", idea 1). Run it **now**, kept
light, on the laptop alongside Coin Toss's recorder.
**Why:** S1 only tested entries that take an existing price. The series charges makers no fee, and maker strategies
can't be backtested without book history, which Kalshi doesn't keep.
**Rules for this stage:**
- No orders of any kind (paper or live). The recorder holds no keys.
- Kalshi load about 1 book request/second plus occasional trade/market requests (≈ 1.2 req/s, well under 20). It backs
  off on any 429 so it can't crowd out Coin Toss's game-window recordings (Oct 15–22).
- Every sleep/offline gap is logged.
- **No maker-strategy analysis of the recorded data until a maker pre-registration is committed** (strategy rules,
  fill model from the recorded book/tape, split, pass rule). Looking at data health (gaps, row counts) is fine.
- S1's verdict on A–D stands. The go-live gate is unchanged.
