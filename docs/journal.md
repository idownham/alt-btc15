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

### 2026-10-14 — Project stopped at S1 ⭐ evidence → decision → consequence
**Decision:** Ian chose to stop Slot Machine at S1 (decisions.md), following Claude's recommendation.
**Evidence → consequence:** out-of-sample backtest shows no edge for A–D (`docs/s1-results.md`) → no paper or live
phase → no money risked. The project's result is the evidence trail itself.
**AI use + Ian's judgment:** Claude recommended stopping, with D-only paper as optional. Ian **accepted** the
recommendation to stop and declined the optional D paper run.

### 2026-10-14 — Class summary written
**Work:** one-page project summary for the class: `docs/class-summary.md` (question, timeline with commit links, the four
evidence → decision → consequence steps, results, lessons, AI use + Ian's judgment). Drawn only from this journal,
decisions.md and git history.

---

## 2026-10-14 — Reopened for idea 1; R1 order-book recorder built and running ⭐ evidence → decision → consequence

**Evidence → decision → consequence:** S1 tested only entries that take an existing price. The series charges makers no
fee, and Kalshi keeps no book history (s1-results "What S1 did not test") → Ian reopened the project for idea 1 and
chose to start recording now, kept light (decisions.md 2026-10-14) → a read-only recorder now builds the book history
that a maker test needs. No maker analysis until a pre-registration is committed.

**Work:** `src/slot/recorder.py` + 9 tests (65 total pass). Each second it records one book snapshot (top 20 levels per
side) and one Coinbase BTC price. Every 10 s it fetches the trade tape. After each window it records the result. Gaps,
errors and 429 pauses are logged; SIGTERM stops it cleanly (found in testing: a background process ignored Ctrl-C).
launchd file written but **not installed**. Started 2026-10-14 15:04 CDT as a background process.

**Observation (first minutes):** 77 snapshots in 76 s at ~48 ms per request, 0 errors, 0 rate-limit pauses. The tape is
heavy (~48k trades per window), so storage is ~600 B per trade, an estimated 1–3 GB/day. 656 GB is free.

**AI use + Ian's judgment:** Claude listed the three untested ideas and recommended idea 1 with a delayed start (after
Coin Toss's recordings, Oct 22). Ian **accepted** idea 1 and **overrode** the timing: run now, kept light.

### 2026-10-14 — launchd agent installed; restart burst found and fixed ⭐ evidence → decision → consequence
**Work:** at Ian's request, installed the launchd agent (`com.idownham.slot.recorder`, starts at login, restarts on crash)
and stopped the plain background copy. Restart gaps are now logged from the last stored snapshot (`5ab6675`).
**Evidence:** on the switch to launchd (15:08), the recorder re-fetched the whole window's tape from the open in one
burst and hit Kalshi's rate limit 8 times in about 80 s (each followed by the 10 s back-off). That's the load "kept
light" was meant to rule out, with Coin Toss sharing the IP.
**Decision → consequence:** the tape is now fetched oldest-first in 60 s slices, at most one request per tick,
resuming from the newest stored trade (`cf0f1dd`, 3 new tests, 68 pass). Since the restart at 15:10: 0 errors, 0
rate-limit pauses, tape current to within ~3 s.
**AI use + Ian's judgment:** Ian asked for the install. Claude found and fixed the burst during the install check.

### 2026-10-14 — Maker pre-registration drafted (PROPOSED)
**Work:** `docs/r1-maker-preregistration.md`. Data range Oct 14 20:15 UTC → Oct 28 (≥ 900 usable windows), 2/3 train
and 1/3 test; pessimistic queue-aware fill model (1 s latency, cancels never move us up); M1 fair-value bid (4
variants) and M2 pair capture (4 variants); selection on uncapped mean per traded window (the lesson from S1); pass =
capped test net > 0 **and** CI above 0. Written before any analysis of recorded data (health checks only).
**AI use + Ian's judgment:** Claude drafted it. *Pending:* Ian's approval, revision or rejection.

### 2026-10-14 — Maker pre-registration approved
**Decision:** Ian approved `docs/r1-maker-preregistration.md` as written (decisions.md). Approval came before any
analysis of the recorded data. Analysis is planned for after 2026-10-28 05:00 UTC.
**AI use + Ian's judgment:** Claude drafted it and flagged four optional changes (window minimum and end date, the CI
requirement, the quoting cutoff, early exit for one-sided M2 fills). Ian **accepted** it unchanged.

### 2026-10-14 — Maker backtest engine built (synthetic data only)
**Work:** `src/slot/maker.py`: usable-window checks, the queue-aware fill model with 3 sensitivity modes, M1 and M2,
per-variant caps, and count/train/test phases. The test phase runs only after the selection is committed.
`tests/test_maker.py`: 21 tests on synthetic data (88 total pass). The engine **refuses to read the real recording
before 2026-10-28 05:00 UTC**, enforcing the approval in code. Seven interpretation points are recorded as dated
clarifications in the pre-registration, before any data. Estimated full run: ~10–15 min.
**AI use + Ian's judgment:** Claude built it; Ian asked for it. *Pending:* Ian may overrule any clarification before Oct 28.

### 2026-10-14 — Folder renamed to `project-slot-machine`
**Work:** HQ folder rename (HQ `docs/decisions.md`): this checkout moved from `~/code/alt/alt-btc15` to
`~/code/alt/project-slot-machine` (GitHub repo name unchanged). The recorder agent was unloaded at 15:30 CT, `.venv`
rebuilt (88 tests pass), the plist template updated to the new path, and the agent reinstalled and loaded at 15:31.
**Observation:** the recorder logged one gap of 69 s (15:30:43–15:31:51), the planned downtime, and resumed recording
book snapshots within seconds. This gap falls inside the maker pre-registration's data range and is in the `gaps`
table like any other gap (not checked against the usable-window rules here).
**AI use + Ian's judgment:** Ian asked for the rename; Claude ran it in an HQ session.

### 2026-10-14 (evening) — Recorder health check; drift fixed; clarifications accepted ⭐ evidence → decision → consequence
**Work:** health-only check of the R1 recording (no prices, P&L or strategy numbers looked at). Agent running; newest
snapshot 0.2 s old; ~200 MB in 3.5 h (≈ 1.4 GB/day), 657 GB free. A **network outage from about 17:34 to 18:00 CDT**
(DNS failures, longest gap 962 s) is in the `gaps` table. The recorder recovered by itself.
*Correction 2026-10-15: this was not a network outage. The Mac was asleep with the lid closed ('Clamshell Sleep' at
17:34:57 on battery, pmset log). The DNS errors came as the network came back on wake. See the 2026-10-15 entry.*
**Evidence:** snapshots were ~1.055 s apart (≈ 57/min), so even a window with no outage would cover only ~94.8% of its
seconds, under the pre-registration's ≥ 95% usable-window rule. The first in-range window
(`KXBTC15M-26OCT141630`) has no result because its result read fell inside the rename downtime.
**Decision → consequence:** Ian chose to fix the loop to a fixed 1-s schedule (2 new tests, 90 pass), keep the 95%
rule unchanged, and **not** backfill results. The recorder was restarted at 18:40:30 CDT. Afterwards: 60 snapshots in each full
minute, mean spacing 1.000 s, 0 errors. Windows recorded before the fix keep their real coverage and are judged
by the rule as written. `…141630` will count as unusable.
**Clarifications:** Claude walked Ian through all seven. Ian **accepted** all seven as written (decisions.md).
**AI use + Ian's judgment:** Claude found the drift and the missing result during the health check and recommended both
fixes. Ian **accepted** the schedule fix and **rejected** the backfill.

### 2026-10-15 → 10-18 — Laptop sleep is costing most of the R1 recording ⭐ evidence → decision (pending) → consequence
**Evidence (health only, no prices or results looked at):** HQ flagged it on Oct 15 (cross-project checkpoint, Ian approved
sending it), and Claude checked it here. pmset shows 'Clamshell Sleep' whenever the lid closes on battery (first at
17:34:57 on Oct 14, which corrects the "network outage" above), plus repeated maintenance DarkWakes overnight. The system
sleep setting is 1 min, and the recorder holds no keep-awake. Book-snapshot coverage of each Chicago day (share of 86,400 s):
Oct 15 **24.3%**, Oct 16 **52.7%**, Oct 17 **2.6%**, Oct 18 **39.2%** (through 22:23). From Oct 14 19:00 to Oct 15 11:13 CT it
was 16.8%, with 13.4 h in the `gaps` table.
**Consequence for the pre-registration:** most windows since Oct 14 evening will fail the ≥ 95% coverage rule, so the
900-usable-window minimum will very likely force the end-date extension (in whole days, counting usable windows only,
as written). The rule is unchanged.
**Decision (pending):** Claude gave three options: a small separate server, the laptop kept open and plugged in with a
keep-awake hold, or accepting the gaps. Ian replied that he is "working on upgrading server". **No dated decision yet.**
Note: CLAUDE.md says not to deploy to Osprey's droplet, so if the plan is to host R1 on an upgraded `alt-arb`, that
needs a dated decision entry (and an HQ note) first.
**AI use + Ian's judgment:** HQ found the sleep cause and Claude confirmed it from pmset and the DB. Ian chose to move
toward a server. Details to be recorded when he decides.

### 2026-10-18 — Decision: move the R1 recorder to the shared droplet ⭐ evidence → decision → consequence
**Evidence:** laptop sleep (entry above) → **Decision:** Ian chose to run R1 on the resized `alt-arb` droplet (HQ
decision 2026-10-15; decisions.md 2026-10-18) → **Consequence:** CLAUDE.md's infrastructure rule is updated. The move
plan is in `docs/r1-droplet-move.md`: own user, folder and systemd unit; overlap then cutover; a merge rule that never mixes hosts within a window.
Nothing is deployed until the resize is confirmed.
**Observation:** the disk check found the trade tape is ≈ 98% of storage (≈ 1.0 GB/day) and is backfilled after gaps,
so the DB grows at full rate even when book coverage is low. This corrects the day-one 1.4 GB/day estimate (a busy afternoon).
**AI use + Ian's judgment:** Claude offered a separate VPS or the upgraded droplet. Ian **chose** the droplet, in line with
the HQ decision. Claude measured disk use and wrote the move plan.
