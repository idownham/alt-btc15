# S1 test results (out-of-sample, run once)

*Generated 2026-10-14 04:58 UTC by `python -m slot.backtest test` at commit 654d73e. Test = windows closing 2026-08-29 → 2026-10-13 UTC: 4272 usable windows. Variants selected on train only (`docs/s1-selection.json`).*

| Strat | Variant | Trades (capped) | Win rate | Break-even WR | Net P&L capped | Net uncapped | Mean/trade | Worst day | Max DD | Cap refusals |
|---|---|---|---|---|---|---|---|---|---|---|
| A | mom60 | 65 | 40.0% | 58.7% | **−$98.09** | −$3447.24 | −$1.51 | −$22.88 | $98.09 | {'day_cap': 275, 'total_cap': 3931} |
| B | mom15 +5c stop=none limit=1m | 93 | 25.8% | 85.8% | **−$95.91** | −$5040.10 | −$1.03 | −$22.53 | $95.91 | {'day_cap': 224, 'total_cap': 3954} |
| C | margin=0c L=5 | 313 | 73.2% | 94.0% | **−$95.97** | −$301.46 | −$0.31 | −$21.98 | $96.70 | {'day_cap': 13, 'total_cap': 774} |
| D | fade margin=5c L=15 | 284 | 93.3% | 95.9% | **−$35.71** | −$35.71 | −$0.13 | −$12.56 | $44.04 |  |

## Verdicts

- **A (mom60):** **does not pass S1**. Mean per trade −$1.51, 95% CI −$2.52 to −$0.50 (excludes 0); avg entry $0.55; exits {'settle': 65}; skips {'no_signal': 1}; permanent $100 halt at 2026-09-01.
- **B (mom15 +5c stop=none limit=1m):** **does not pass S1**. Mean per trade −$1.03, 95% CI −$1.24 to −$0.83 (excludes 0); avg entry $0.62; exits {'time': 69, 'target': 24}; skips {'no_signal': 1}; permanent $100 halt at 2026-09-01.
- **C (margin=0c L=5):** **does not pass S1**. Mean per trade −$0.31, 95% CI −$0.45 to −$0.16 (excludes 0); avg entry $0.98; exits {'settle': 313}; skips {'no_signal': 3138, 'no_fill': 33, 'no_model': 1}; permanent $100 halt at 2026-09-08.
- **D (fade margin=5c L=15):** **does not pass S1**. Mean per trade −$0.13, 95% CI −$0.27 to $0.02 (includes 0); avg entry $0.95; exits {'settle': 284}; skips {'no_signal': 3988}; no $100 halt.

## Sensitivity: fills at the minute's close quote (NOT an S1 result; shows the cost of the worst-in-minute rule)

| Strat | Variant | Trades (capped) | Win rate | Break-even WR | Net P&L capped | Net uncapped | Mean/trade | Worst day | Max DD | Cap refusals |
|---|---|---|---|---|---|---|---|---|---|---|
| A | mom60 | 75 | 40.0% | 55.1% | **−$98.37** | −$1241.45 | −$1.31 | −$22.90 | $98.37 | {'day_cap': 269, 'total_cap': 3927} |
| B | mom15 +5c stop=none limit=1m | 212 | 43.9% | 78.1% | **−$96.48** | −$1496.18 | −$0.46 | −$22.24 | $96.48 | {'day_cap': 177, 'total_cap': 3882} |
| C | margin=0c L=5 | 933 | 85.1% | 89.0% | **−$98.45** | −$119.51 | −$0.11 | −$21.01 | $102.91 | {'day_cap': 13, 'total_cap': 160} |
| D | fade margin=5c L=15 | 284 | 93.3% | 92.7% | **$8.85** | $8.85 | $0.03 | −$10.83 | $17.56 |  |
