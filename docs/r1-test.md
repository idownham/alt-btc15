# R1 maker test: test results (out-of-sample, run once)

*Generated 2026-11-25 07:48 UTC by `python -m slot.maker test` at commit 0f412ec. Test = last 304 of 910 usable windows. Fee type: `quadratic`.*

| Strat | Variant | Mode | Traded windows | Fill rate | Pairs completed | Net capped | Net uncapped | Mean/window (95% CI) | Spread earned | Adverse selection | Worst day | Max DD | Cap refusals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 | margin=3c join | base | 304 | 80.6% | – | **−$65.12** | −$143.02 | −$0.47 (−$1.05 to $0.11) | $227.66 | −$370.69 | −$24.64 | $99.23 | {'day_cap': 211} |

## Verdicts (pass = capped net > 0 and 95% CI of mean per traded window above 0)

- **M1 (margin=3c join):** **does not pass R1**. Capped: 93 traded windows, net −$65.12, CI −$1.79 to $0.39.

## Sensitivity (NOT the result; shows how much the fill model matters)

| Strat | Variant | Mode | Traded windows | Fill rate | Pairs completed | Net capped | Net uncapped | Mean/window (95% CI) | Spread earned | Adverse selection | Worst day | Max DD | Cap refusals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 | margin=3c join | optimistic queue | 304 | 82.4% | – | **−$89.01** | −$145.98 | −$0.48 (−$1.07 to $0.10) | $226.72 | −$372.69 | −$23.64 | $123.13 | {'day_cap': 238} |
| M1 | margin=3c join | 3 s latency | 304 | 79.5% | – | **−$93.61** | −$142.89 | −$0.47 (−$1.05 to $0.11) | $226.43 | −$369.31 | −$24.63 | $127.73 | {'day_cap': 235} |
| M1 | margin=3c join | back of queue only | 304 | 77.0% | – | **−$66.00** | −$159.83 | −$0.53 (−$1.10 to $0.05) | $225.30 | −$385.13 | −$24.64 | $100.11 | {'day_cap': 208} |
