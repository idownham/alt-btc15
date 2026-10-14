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
