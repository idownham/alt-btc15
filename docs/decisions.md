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
