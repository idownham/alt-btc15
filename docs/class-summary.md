# Project Slot Machine — class journal summary

*Ian Downham · Supply Chain Management, University of Arkansas · Founder documentary, Fall 2026.
Written 2026-10-14 from this repo's journal, decisions log and commit history. Repo: https://github.com/idownham/alt-btc15*

## The question
Kalshi runs a new "Will Bitcoin be up in the next 15 minutes?" market every 15 minutes, 24/7 (`KXBTC15M`). A YES pays
$1. After watching it live and placing one $5 trade by phone, I wanted to know whether a small automated system could
**win more than it loses after fees**, with hard risk caps ($5 per trade, $25 per day, $100 total) and paper trading
before any real money.

**Answer: no.** None of the four strategies beat the spread plus fees in an out-of-sample backtest of 12,690 windows.
I stopped the project before it risked any money.

## Timeline (all dates 2026, times CDT)
| When | Step | Evidence |
|---|---|---|
| Oct 13, evening | Watched the market, placed one manual $5 trade, defined strategies A–D, risk caps and the paper-first plan | [af3fdca](https://github.com/idownham/alt-btc15/commit/af3fdca) |
| Oct 13 | Decided to run on my laptop instead of the shared server | [edcb4ce](https://github.com/idownham/alt-btc15/commit/edcb4ce) |
| Oct 13 | **S0 research:** how the market settles, fees, data available; read-only data clients; risk-cap code with tests | [6e87595](https://github.com/idownham/alt-btc15/commit/6e87595), `docs/s0-research.md` |
| Oct 13 | Reviewed S0 and approved 4 design decisions *before* any backtest results | [3278539](https://github.com/idownham/alt-btc15/commit/3278539) [1423945](https://github.com/idownham/alt-btc15/commit/1423945) [ab0e8e8](https://github.com/idownham/alt-btc15/commit/ab0e8e8) [c7cd296](https://github.com/idownham/alt-btc15/commit/c7cd296) |
| Oct 13 | **Pre-registered** the backtest (data range, 61 variants, train/test split, pass rule) before pulling any data | [816d8c7](https://github.com/idownham/alt-btc15/commit/816d8c7) |
| Oct 13 | Amendment 1 (found in a test pull, approved before results) | [fa08712](https://github.com/idownham/alt-btc15/commit/fa08712), [d37db63](https://github.com/idownham/alt-btc15/commit/d37db63) |
| Oct 13 | Backtest engine + tests | [c4f070a](https://github.com/idownham/alt-btc15/commit/c4f070a) |
| Oct 13, 23:58 | Train phase: all 61 variants; selection committed *before* the test run | [654d73e](https://github.com/idownham/alt-btc15/commit/654d73e) |
| Oct 13, 23:59 | Test phase, run once: no strategy passes | [db0ed43](https://github.com/idownham/alt-btc15/commit/db0ed43), `docs/s1-results.md` |
| Oct 14 | **Decision: stop at S1** | [e84871b](https://github.com/idownham/alt-btc15/commit/e84871b) |

## The strategies tested
- **A. Direction at open:** pick up or down from a BTC signal, hold to the end.
- **B. Open scalp (my rule):** buy near the open and sell at +10¢ (+5/+15¢, stops and time limits also tested).
- **C. Late favorite (my rule):** with 1–3 minutes left, buy the side trading at 90–97¢ when a pricing model says
  it's underpriced.
- **D. Longshot fade:** with 4–6 minutes left, bet against sides priced at 10¢ or less when the model says they're
  overpriced.

## Evidence-based decisions (evidence → decision → consequence)
1. **Settlement turned out to be an average, so the model changed.** Kalshi settles on the *average* of 60
   one-second index prices before close, not one final price. Checked on 19,985 windows. → I approved a model that
   accounts for the averaging, and limited C to 60–180 s before close. → C stopped targeting the final minute, where
   our free price feed (off by about $5 from the official index) would decide the result instead of our model.
2. **There is no historical order book, so fills had to be pessimistic.** Kalshi only keeps 1-minute price summaries.
   → I approved "assume the worst price in that minute" for every simulated trade. → Any edge had to survive a harsh
   test, and I also pre-registered a generous-price check to show how much the rule cost.
3. **The first minute's prices were fake.** In 85% of windows the first minute contains the empty opening book (asks at
   about $1.00). → Amendment 1: A and B enter in minute 2, approved before any results. → A and B were tested at
   prices someone could actually trade.
4. **The results showed no edge, so I stopped.** All four strategies failed the pre-registered test. → I stopped
   instead of paper trading. → No money was risked, and the project's result is a documented negative finding.

## Results (test set: Aug 29 – Oct 12, run once)
| Strategy | Average per trade, all test windows (harsh fills) | Same with generous fills | Verdict |
|---|---|---|---|
| A. Direction at open | −$0.81 | −$0.29 | fail |
| B. Open scalp | −$1.18 | −$0.35 | fail |
| C. Late favorite | −$0.27 | −$0.11 | fail |
| D. Longshot fade | −$0.13 | +$0.03 (not distinguishable from $0) | fail |

**Why it didn't work:**
- Within a single minute, the price swings about 15–17¢ between the worst buy and worst sell price. That's bigger than
  the +10¢ scalp target.
- The market prices late favorites correctly: 90–97¢ favorites won 93–95% of the time.
- By the time a bot working minute by minute can buy, the price has usually reached 99¢, leaving nothing to win.

## What went wrong / lessons
- **My selection rule was weak.** For each strategy I picked the variant with the best result *after* the $100 cap.
  Nearly every variant hit the cap, so the rule mostly picked the smallest loser. It didn't change the verdict
  (every A–C variant lost even without caps), but next time I'd rank on per-trade results and use caps only as the
  money guardrail.
- **The manual trade isn't fully documented.** My first $5 phone trade has an unknown side, entry and final result
  (`docs/manual-trades.md`).
- **Small process slips**, caught and fixed the same night: build files and a database temp file were committed by
  mistake and then removed, and two unit tests had arithmetic errors in the tests themselves.

## AI use and my judgment
| What the AI (Claude) did | My judgment |
|---|---|
| Computed break-even win rates in planning and argued that exits don't create an edge | **Partly accepted:** I kept my own rules (B, C) as strategies to test with evidence instead of dropping them |
| Researched settlement, fees and data; built the data clients and risk-cap code | Used as the basis for my decisions below (I didn't recheck the sources myself) |
| Proposed the averaging model and C's 60–180 s band | **Accepted** |
| Proposed worst-price-in-minute backtest fills | **Accepted** |
| Proposed per-strategy caps for the $25/day cap | **Accepted**, and I extended it to the $100 total myself |
| Proposed amendment 1 (enter in minute 2) | **Accepted** before any results |
| Designed the 61-variant grid and split; ran the backtest | **Accepted** the protocol; asked for the train and test runs |
| Recommended stopping at S1, with D-only paper trading as optional | **Accepted** stopping; **declined** the optional D run |

## Limits of the result
- The BTC prices came from Coinbase as a stand-in for the official CF Benchmarks index.
- The backtest uses 1-minute data only, with no order-book depth history.
- It covers about 4.5 months of windows.
- A much faster bot with the official index feed is a different strategy, competing on speed with professional
  traders. I didn't test it.

**Where to look:** `docs/s0-research.md` (research), `docs/s1-preregistration.md` (pre-registered plan),
`docs/s1-train.md`, `docs/s1-test.md`, `docs/s1-results.md` (results), `docs/decisions.md`, `docs/journal.md`.
