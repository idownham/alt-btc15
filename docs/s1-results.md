# S1 backtest — results and verdict

*2026-10-13/14 (CDT). Protocol: `docs/s1-preregistration.md` (committed `816d8c7` before any data; amendment 1 approved
by Ian before results). Train results for all 61 variants: `docs/s1-train.md` (selection committed `654d73e` before
the test run). Test, run once: `docs/s1-test.md`. Data: 12,690 KXBTC15M windows closing 2026-06-01 → 2026-10-12 UTC
(12,668 usable: 11 with bad strikes, 11 with missing candles); Coinbase 1-min BTC.*

## Verdict: no strategy passes S1

| Strategy (variant chosen on train) | Test trades (capped) | Net P&L capped | Mean/trade (95% CI) | S1 |
|---|---|---|---|---|
| A — direction at open (`mom60`) | 65 (then $100 halt, 2026-09-01) | −$98.09 | −$1.51 (−$2.52 to −$0.50) | **fail** |
| B — open scalp (`mom15`, +5¢, no stop, 1-min limit) | 93 (halt 2026-09-01) | −$95.91 | −$1.03 (−$1.24 to −$0.83) | **fail** |
| C — late favorite (margin 0¢, σ over 5 min) | 313 (halt 2026-09-08) | −$95.97 | −$0.31 (−$0.45 to −$0.16) | **fail** |
| D — longshot fade (margin 5¢, σ over 15 min) | 284 (no halt) | −$35.71 | −$0.13 (−$0.27 to +$0.02) | **fail** |

Under the pre-registered gate ("backtest out-of-sample result also net positive"), **no strategy can go live**,
whatever paper trading shows later. That stays true unless Ian changes the gate in decisions.md, with the reason
recorded first.

## How robust is "no edge"?

Uncapped, so every window counts (the capped runs stop at the $100 halt, so they're small samples):

| Strategy | Test trades | Mean/trade, worst-in-minute fills (official rule) | Mean/trade, close-quote fills (generous, sensitivity only) |
|---|---|---|---|
| A | 4,271 | −$0.81 (−$0.93 to −$0.68) | −$0.29 (−$0.44 to −$0.14) |
| B | 4,271 | −$1.18 (−$1.21 to −$1.15) | −$0.35 (−$0.37 to −$0.33) |
| C | 1,100 | −$0.27 (−$0.35 to −$0.20) | −$0.11 (−$0.20 to −$0.02) |
| D | 284 | −$0.13 (−$0.27 to +$0.02) | **+$0.03 (−$0.13 to +$0.19)** |

- **A, B and C lose even with the generous fills**, and their confidence intervals exclude zero. The harsh fill rule
  makes the losses bigger, but it isn't what causes them. This is the strongest finding: these strategies don't beat
  the spread plus fees on this market.
- **D is the only one near break-even**: −$0.13 per trade with harsh fills, +$0.03 with generous fills, and both
  intervals include zero. That is "no detectable edge", not "a small edge". 284 trades can't tell a few cents per trade
  from zero.
- **B (Ian's +10¢ open scalp):** every one of its 36 variants lost on train, including all +10¢ variants. The
  1-minute bid/ask swing (15–17¢ from worst ask to worst bid) is bigger than the target.

## Things to read the numbers correctly

1. **The selection rule was weak, and I didn't see that when writing it.** Almost every train variant hit the $100
   per-strategy halt, so "highest capped net P&L" mostly picked whichever variant halted at the smallest loss. That
   is close to random among losers. It doesn't change the verdict: on train, every A, B and C variant lost even
   uncapped, so a better rule couldn't have picked a winner. It is a lesson for S2's design: rank on uncapped
   per-trade P&L, and use caps as the money guardrail.
2. **"Win rate" means P&L > 0 after fees.** At a 99.9¢ fill, a *correct* call earns 0.1¢ × 5 contracts = ½¢, and the
   fee rounded up to a whole cent makes it a net loss. That's why C's "win rate" (73%) looks far below the market's
   own calibration (favorites at 90–97¢ won 93–95% on train).
3. **C's main problem is the price reached by the time you fill.** Checked on train: with the favorite quoted at
   90–97¢, by the fill minute about half of C's trades had to pay 99¢ or more. At that price there's nothing left
   to win, and those were also the minutes when BTC reversed (one example: YES traded from 0.2¢ to 98¢ inside a
   single minute). The market *is* calibrated; a 1-min backtest can't buy the favorite before the price moves.
4. **Limits:** Coinbase is only a proxy for BRTI; there is no depth history; 1-min resolution only. A faster bot with a
   BRTI feed is a different strategy (spec E) and a speed race against professionals.

## What S1 did *not* test (added 2026-10-14)
"No edge found" covers the four strategies as designed, at 1-minute speed, entering by taking an existing price. These
remain untested:

1. **Resting limit orders (maker side).** KXBTC15M charges makers **no fee** (`quadratic` series). Every S1 entry paid
   the spread and the taker fee. A strategy that rests bids and earns the spread was never tested. It needs a **live
   order-book recorder**, because Kalshi keeps no book history. This is the closest idea to Coin Toss's thesis (maker
   on sports markets), so Coin Toss's result is an early signal for it.
2. **Speed: second-level reaction with the official index.** A bot reacting within seconds, ideally on the licensed
   CF Benchmarks BRTI feed, is a different strategy (spec E). It competes on speed with professional firms, and the
   feed costs money. Unlikely to suit $5 trades.
3. **D with more data.** D's result (−$0.13 harsh / +$0.03 generous per trade, both CIs include 0, 284 trades) can't
   tell a small edge from none. Settling it needs weeks of paper trading with real depth-walked fills and 1-s prices.

Any of these means **reopening** the project: a new dated entry in `decisions.md` and a new pre-registration before
any data, like S1.

## What this means for the plan (decisions for Ian, not made here)

- This is a well-evidenced "no edge" result for A–C, which `CLAUDE.md` calls a valid, useful outcome.
- Options:
  1. **Stop Slot Machine at S1** and write it up as the result.
  2. **Run S2 paper for D only, as evidence-gathering.** Real depth-walked fills and 1-s data would settle whether D's
     ≈ 0 is slightly positive or slightly negative. Under the current gate it could not go live, because S1 failed.
  3. **Change the gate.** That needs a dated decisions.md entry with the reason before any new results, and it would
     be hard to defend after seeing these numbers.
- Recommendation: **option 1**, with option 2 only if the extra class evidence is worth the laptop time. Nothing in
  these results suggests a live edge.
