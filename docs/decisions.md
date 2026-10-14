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
