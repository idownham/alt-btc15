# R1 maker test: train results (all 8 variants, in-sample)

*Generated 2026-11-25 07:44 UTC by `python -m slot.maker train` at commit 5a0434a. Usable windows 910 of 2334 ({'no_result': 1, 'book_coverage': 1363, 'usable': 910, 'btc_missing': 38, 'gap_in_quoting': 20, 'tape_error': 2}); train = first 606. Fee type at analysis: `quadratic`. Pessimistic queue model, 1 s latency.*

In-sample, with 8 variants tried. Only the test set (`docs/r1-test.md`) counts.

| Strat | Variant | Mode | Traded windows | Fill rate | Pairs completed | Net capped | Net uncapped | Mean/window (95% CI) | Spread earned | Adverse selection | Worst day | Max DD | Cap refusals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 | margin=1c join | base | 606 | 81.7% | – | **$27.63** | −$63.86 | −$0.11 (−$0.51 to $0.30) | $316.27 | −$380.13 | −$23.85 | $109.60 | {'day_cap': 140, 'per_trade': 2} |
| M1 | margin=1c improve | base | 34 | 93.0% | – | **−$79.06** | −$98.51 | −$2.90 (−$3.85 to −$1.95) | $103.60 | −$202.11 | −$24.33 | $80.84 | {'day_cap': 4} |
| M1 | margin=3c join | base | 601 | 82.1% | – | **$77.90** | $93.74 | $0.16 (−$0.33 to $0.64) | $418.80 | −$325.06 | −$23.88 | $118.05 | {'day_cap': 109, 'per_trade': 2} |
| M1 | margin=3c improve | base | 26 | 98.7% | – | **−$70.39** | −$84.84 | −$3.26 (−$4.35 to −$2.18) | $100.61 | −$185.46 | −$24.33 | $72.17 | {'day_cap': 3} |
| M2 | spread>=2c once | base | 0 | – | – | – | – | – | – | – | – | – | – |
| M2 | spread>=2c every 60 s | base | 4 | 75.0% | 66.7% | **−$1.70** | −$1.70 | −$0.42 (−$2.54 to $1.69) | $0.25 | −$1.95 | −$3.50 | $3.50 |  |
| M2 | spread>=3c once | base | 0 | – | – | – | – | – | – | – | – | – | – |
| M2 | spread>=3c every 60 s | base | 2 | 75.0% | 66.7% | **$1.70** | $1.70 | $0.85 (−$0.52 to $2.22) | $0.15 | $1.55 | $1.70 | $0.00 |  |

## Selected for the test set (pre-registered rule)

- **M1:** margin=3c join
- M2: no variant reached 50 traded windows (not tested).
