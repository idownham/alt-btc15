# Journal (alt-btc15 / Project Slot Machine)

Dated entries: work, evidence, observation, decision, AI use + Ian's judgment.

---

## 2026-10-13 — Project defined (planning chat)

**Work:** Ian watched KXBTC15M live and placed a manual $5 trade; planning chat (Claude) and Ian defined strategies A–D, risk caps, paper-first plan, and go-live gate draft. Repo scaffolded (rules, spec, decisions).

**Observation:** The 15-min BTC market moves in runs that track BTC's live price (information-driven), unlike the 1¢ bid-ask flicker seen the same evening in a college football market.

**AI use + Ian's judgment:** Claude computed break-even win rates (≈75% for ±5¢ exits, ≈63% for ±10¢, ≈52% hold-to-expiry, ≈95.5% for buying at 95¢) and argued exits don't create edge. Ian accepted testing it with evidence but kept his own rules (B: +10¢ open scalp; C: late favorite) as strategies to test rather than dropping them.

---

## 2026-10-13 — S0: settlement research, data clients, risk caps (Claude session)

**Work:** Researched how KXBTC15M settles, its fees, window timing and the history available, using Kalshi's public
API, contract filings and Coinbase. Built read-only clients (Kalshi KXBTC15M book/windows/history; Coinbase BTC
price), the fee model, and `risk.py` ($5/trade, $25/Chicago day, $100 total, STOP/KILL kill switch) with tests.
Write-up: `docs/s0-research.md`. Kalshi client adapted from alt-scalp @ db83d7d.

**Evidence:**
- Kalshi's own rules text (every market) and CRYPTO contract terms: settlement = **simple average of 60 one-second
  BRTI prints before close**; the target = the same average before open. Checked on 19,985 back-to-back windows:
  the next window's target equals the previous settlement value in 19,981 cases (the 4 exceptions are data errors).
- Fees: `quadratic` ×1 (taker 0.07·C·P·(1−P), no maker fee), no fee changes ever for the series.
- History: 22,886 settled windows on `/historical` (2025-12-10 → 2026-08-13) plus everything since. 49.8% YES.
  1-min candlesticks and the full trade tape exist per window; **no order-book history**.
- Proxy test, 288 windows: the Coinbase 1-min proxy was off from the official settlement by $4.59 (median) and picked
  the wrong outcome in 10/288 windows (3.5%).
- Tests: 40 unit tests pass; 1 live read-only smoke test passes.

**Observation (flag):** The averaging makes the final minute much more predictable than the spec's model assumed.
With BTC $30 above target and 30 s left, the naive model says 89% and the average-aware model says ≈100%. The
market seems to know it (a checked window closed at 99.9¢). So strategy C's edge, if any, is in the 60–180 s band
and in tracking BRTI well, not in "favorites usually win".

**Decision:** None by Ian yet. Proposed for Ian's review (s0-research §9): average-aware model, C entry band
60–180 s, conservative candle-based fills for S1, risk-cap scope per strategy in paper. Stopped before S1 as asked.

**AI use + Ian's judgment:** Claude did the API research, the measurements and the code. *Pending:* Ian to review
the findings and the §9 proposals (accept / revise / reject).

### 2026-10-13 (later) — Ian's review of S0, part 1 ⭐ evidence → decision → consequence
**Decision:** Ian approved the average-aware model and the 60–180 s entry band for C (decisions.md, same date).
**Evidence → consequence:** settlement averaging (S0 §1, §7) → the spec's model replaced → C no longer trades the final
minute, where our price proxy, not BTC volatility, would decide the edge.
**AI use + Ian's judgment:** Claude proposed the model and band; Ian **accepted** both. The other S0 proposals
(fill assumption, cap scope, second BTC source, < 60 s variant) are still open.

### 2026-10-13 (later) — Ian's review of S0, part 2 ⭐ evidence → decision → consequence
**Decision:** Ian approved worst-price-in-minute fills for the S1 backtest (decisions.md, same date).
**Evidence → consequence:** no Kalshi order-book history (S0 §5) → S1 uses the most pessimistic price in each
1-min candle, a scoped exception to rule 5 → any S1 edge has to survive a deliberately harsh fill model. S2 measures
real fills.
**AI use + Ian's judgment:** Claude proposed the rule; Ian **accepted** it. Still open: risk-cap scope in paper,
second BTC source, maker-fee check, go-live gate.

### 2026-10-13 (later) — Ian's review of S0, part 3
**Decision:** $25/day cap applies per strategy in paper (decisions.md). Claude proposed it; Ian **accepted**.
Open: $100 total scope in paper, live cap scope, second BTC source, maker-fee check, go-live gate.

### 2026-10-13 (later) — Ian's review of S0, part 4
**Decision:** $100 total cap also per strategy in paper (decisions.md). Ian's call, extending part 3.
Open: live cap scope (at the gate), second BTC source, maker-fee check, go-live gate.

### 2026-10-13 (later) — S1 started ⭐ evidence → decision → consequence
**Work:** pre-registered S1 (`docs/s1-preregistration.md`, committed before any data). Built the paced history puller and
the backtest engine (61 variants) with tests. Full pull of 12,690 windows (Jun 1 – Oct 12) running.
**Evidence → decision → consequence:** the trial pull showed minute 1 carries the empty opening book (ask ≈ $1.00 in 85%
of windows) → amendment 1: A/B enter in minute 2 → **Ian approved** it before any results.
**Observation:** the worst-ask-to-worst-bid gap within a minute averages 15–17¢, so the approved fill rule will be
harsh on A/B. The pre-registered close-price sensitivity will measure how much.
**AI use + Ian's judgment:** Claude designed the grids, split and amendment; Ian **accepted** amendment 1.

---

## 2026-10-13/14 — S1 backtest: no strategy passes ⭐ evidence → decision → consequence

**Work:** Pulled 12,690 windows (Jun 1 – Oct 12) of Kalshi 1-min candles plus Coinbase 1-min BTC (paced, 2 rate-limit
hits in total). Ran all 61 pre-registered variants on train (`docs/s1-train.md`), committed the selection
(`654d73e`), then ran the 4 chosen variants once on test (`docs/s1-test.md`). Write-up: `docs/s1-results.md`.

**Evidence (test, out-of-sample):** capped net P&L A −$98.09, B −$95.91, C −$95.97 (each hit the $100 halt), D −$35.71.
Uncapped mean per trade: A −$0.81, B −$1.18, C −$0.27, D −$0.13. With generous close-quote fills (sensitivity only):
A −$0.29, B −$0.35, C −$0.11 (all CIs below 0), D +$0.03 (CI includes 0).

**Observation:** A–C lose even with generous fills. The 1-min bid/ask swing (~15–17¢) is bigger than B's +10¢
target. For C, the market is calibrated (90–97¢ favorites won 93–95%), and the price usually runs to 99¢+ before a
1-min bot can fill. Self-critique: the pre-registered selection rule (best *capped* P&L) was weak, because nearly
every variant hit the $100 halt. It doesn't change the verdict: every A–C variant lost even uncapped.

**Decision:** pending Ian. Claude recommends stopping at S1 (a valid "no edge" result), with D-only paper trading as
optional extra evidence.

**AI use + Ian's judgment:** Claude ran the pull, the backtest and the write-up under the pre-registered protocol.
Ian approved the protocol inputs (model, C band, fill rule, caps, amendment 1) before results and asked for the
train and test runs. *Pending:* Ian's response to the results.
