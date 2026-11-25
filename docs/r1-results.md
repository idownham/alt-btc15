# R1 maker test: results and verdict

*2026-11-25 (UTC). Protocol: `docs/r1-maker-preregistration.md` (approved by Ian 2026-10-14, clarifications 1–7
accepted 2026-10-14, amendment 1 committed `5a0434a` before any fills). Train results for all 8 variants:
`docs/r1-train.md` (selection committed `0f412ec` before the test run). Test, run once: `docs/r1-test.md`. Data: the
merged laptop + droplet recording (`docs/r1-merge-report.json`). Paper analysis only: no orders of any kind.*

## Verdict: M1 does not pass R1; M2 could not be tested

| Strategy (variant chosen on train) | Test traded windows (capped) | Net P&L capped | Mean/window, capped (95% CI) | R1 |
|---|---|---|---|---|
| M1 fair-value bid (`margin=3c join`) | 93 of 304 (211 refused by the $25/day cap) | **−$65.12** | −$0.70 (−$1.79 to +$0.39) | **fail** |
| M2 pair capture | none: no variant reached 50 traded windows on train | – | – | **not tested** |

Pass rule (pre-registered): capped test net > 0 **and** the 95% CI of mean P&L per traded window entirely above 0.
M1 fails both parts. **Confirmed by Ian, 2026-11-25:** "Confirm, stop recorder" (decisions.md 2026-11-25).

## Data and sample

| | Windows | Usable | Range (UTC, window open → last close) | Host |
|---|---|---|---|---|
| Original range | 1,158 in the table | 347 | 2026-10-14 20:15 → 10-28 05:00 | laptop |
| **Extended range (amendment 1)** | 2,334 in the table | **910** | 2026-10-14 20:15 → **11-10 06:00** | laptop, then droplet from 11-09 04:45 |
| Train (first 2/3) | | 606 | 10-14 21:30 → 11-06 05:45 | laptop only |
| Test (last 1/3) | | 304 | 11-06 14:45 → 11-10 06:00 | 203 laptop, 101 droplet |

Unusable windows by reason (extended range): book coverage < 95%: 1,363 · BTC missing: 38 · gap in quoting period: 20 ·
tape error: 2 · no result: 1. Almost all of the loss is laptop sleep. About 200 more windows in the range never reached
the windows table, because the laptop was asleep for all of them. The droplet recording after 2026-11-10 06:00 UTC
(≈ 1,400 windows) is **not used** and has not been analysed. Only its usable-window counts were computed.

## What happened (uncapped, so every window counts)

| Strategy / variant | Sample | Traded windows | Fill rate | Mean/window (95% CI) | Spread earned | Adverse selection | Net |
|---|---|---|---|---|---|---|---|
| M1 `margin=3c join` | train (in-sample, best of 4) | 601 | 82.1% | +$0.16 (−$0.33 to +$0.64) | +$418.80 | −$325.06 | +$93.74 |
| M1 `margin=3c join` | **test** | 304 | 80.6% | **−$0.47 (−$1.05 to +$0.11)** | +$227.66 | −$370.69 | **−$143.02** |

- **Resting bids do earn the spread, but adverse selection takes more.** On test the fills were bought ≈ $228 cheaper
  than the model's fair value. Settlement then cost ≈ $371 more than that, so the orders that fill are mostly the ones
  the market is about to move through. This is the textbook maker problem, and it is what R1 set out to measure.
- **The train edge did not hold out of sample.** The chosen variant was the best of four M1 variants in-sample, and even
  there its CI included 0. On test the mean flipped to −$0.47. This is what selection on noise looks like.
- **The fill model is not driving the result.** All three sensitivity runs (reported only, not used for the verdict)
  lose about the same: optimistic queue −$0.48, 3 s latency −$0.47, back of queue only −$0.53 per window
  (`docs/r1-test.md`). The loss comes from *which* orders fill, not from queue details.
- **M2 (pair capture) almost never had a spread to capture.** At the decision times the book's YES bid/ask spread was
  nearly always 1¢. On train, the "once" variants never quoted and the "every 60 s" variants traded in 2–4 windows. That
  is far below the 50-window minimum, so M2 isn't tested. The market is too tight for this idea at ≤ $5 size.
- **The caps bind hard.** M1 fills in nearly every window (fill rate ≈ 81%, all 304 test windows traded) and risks up to
  $5 each, so a few losing windows reach the $25/day cap. On test, 211 of 304 windows were refused by it. The official
  capped numbers are therefore a smaller, earlier sample (93 windows), and the uncapped numbers above tell the same
  story with more data.

## Things to read the numbers correctly

1. **Train is all laptop data and test is a third droplet data.** The merge rules keep each window to one host, and
   the usable-window rules are the same for both, so this shouldn't bias the result. It is still a difference between
   train and test, and so is the calendar (Oct 14 → Nov 6 vs Nov 6 → 10).
2. **The live tape can miss a few trades.** In the one window both hosts recorded, 94 trades were only on the droplet's
   tape and 2 only on the laptop's (0.2% of 45,498; same times, different trade IDs, no duplicates). The merge keeps the
   union. Missing trades can only remove fills, so this can't create the losses above.
3. **Coinbase stands in for BRTI** in M1's fair value, so the "spread earned vs model" split is only as good as that
   proxy. The net P&L does not depend on it.
4. **Two train windows** were refused by the $5 per-trade check (M1 1¢/3¢ join; `docs/r1-train.md`). Not investigated,
   because it is train-only and doesn't affect the test or the selection.
5. **One market and one season** (Oct–Nov 2026). A different volatility regime could change the result. That is a
   reason a new test would need new data, not a reason to doubt this one.

## How the data was built (evidence trail)
- **Droplet copy:** each table was streamed read-only over ssh at low priority (`scripts/r1_pull_droplet.sh`), then
  rebuilt on the laptop (`scripts/r1_load_pull.py`). Snapshot at 2026-11-25 05:53 UTC, all row counts equal to the
  rowid marks (74.0 M trades, 1.35 M book snapshots). The move plan's `.backup` on the droplet was not used, because the
  DB (20.8 GB) was larger than the free disk (20 GB). The recorder kept running (checked: 301 snapshots in 300 s, 0 errors, 0 gaps).
- **Merge:** `src/slot/merge.py` (8 synthetic-data tests, committed `e01e16c` before use), with the move plan's rules
  (books/btc from the laptop before T = 2026-11-09 04:45 UTC, from the droplet from T; trades union; windows union;
  gaps/events per host). No laptop gap ends after T, no droplet gap starts before T, and no window results conflict.
  162.5 M trades merged.
- **Counts → amendment → train → selection → test**, each committed before the next step: `56151e0` (count script),
  `5a0434a` (amendment 1), `0f412ec` (train + selection), then the test run once at `0f412ec`.
