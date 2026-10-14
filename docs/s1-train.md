# S1 train results (all 61 variants)

*Generated 2026-10-14 04:57 UTC by `python -m slot.backtest train` at commit d37db63. Train = windows closing 2026-06-01 → 2026-08-29 UTC: 8396 usable windows. Windows skipped in the whole range: {'bad_strike': 11, 'missing_candles': 11}. Worst-in-minute fills; caps per variant.*

**This is in-sample.** With 61 variants tried, the best numbers here are inflated by selection. Only the test set (`docs/s1-test.md`) counts.

| Strat | Variant | Trades (capped) | Win rate | Break-even WR | Net P&L capped | Net uncapped | Mean/trade | Worst day | Max DD | Cap refusals |
|---|---|---|---|---|---|---|---|---|---|---|
| A | mom5 | 62 | 46.8% | 71.3% | **−$98.98** | −$5771.42 | −$1.60 | −$24.94 | $98.98 | {'day_cap': 249, 'total_cap': 8072} |
| A | mom15 | 140 | 55.0% | 64.5% | **−$97.44** | −$7366.92 | −$0.70 | −$24.78 | $102.34 | {'day_cap': 205, 'total_cap': 8045} |
| A | mom60 | 135 | 54.1% | 63.8% | **−$96.99** | −$7413.27 | −$0.72 | −$23.61 | $100.92 | {'day_cap': 179, 'total_cap': 8078} |
| A | rev5 | 146 | 48.6% | 56.8% | **−$99.90** | −$8555.98 | −$0.68 | −$23.78 | $104.30 | {'day_cap': 253, 'total_cap': 7984} |
| A | rev15 | 73 | 41.1% | 57.9% | **−$99.89** | −$6975.71 | −$1.37 | −$24.75 | $99.89 | {'day_cap': 236, 'total_cap': 8081} |
| A | rev60 | 60 | 41.7% | 63.8% | **−$98.65** | −$6934.78 | −$1.64 | −$23.71 | $103.08 | {'day_cap': 253, 'total_cap': 8079} |
| A | lean | 249 | 65.5% | 71.7% | **−$99.90** | −$4954.92 | −$0.40 | −$24.51 | $99.90 | {'day_cap': 94, 'total_cap': 8052} |
| A | antilean | 45 | 28.9% | 53.8% | **−$98.33** | −$9396.85 | −$2.19 | −$24.14 | $101.63 | {'day_cap': 265, 'total_cap': 8085} |
| B | lean +5c stop=none limit=1m | 80 | 26.2% | 88.0% | **−$96.26** | −$9611.66 | −$1.20 | −$22.22 | $96.26 | {'day_cap': 235, 'total_cap': 8080} |
| B | lean +5c stop=none limit=5m | 82 | 53.7% | 92.6% | **−$98.46** | −$7735.00 | −$1.20 | −$23.11 | $98.46 | {'day_cap': 239, 'total_cap': 8074} |
| B | lean +5c stop=none limit=hold | 88 | 72.7% | 95.3% | **−$97.01** | −$6428.00 | −$1.10 | −$24.07 | $97.01 | {'day_cap': 227, 'total_cap': 8080} |
| B | lean +5c stop=25c limit=1m | 80 | 26.2% | 88.0% | **−$96.26** | −$9669.77 | −$1.20 | −$22.22 | $96.26 | {'day_cap': 235, 'total_cap': 8080} |
| B | lean +5c stop=25c limit=5m | 79 | 45.6% | 91.7% | **−$98.35** | −$8526.20 | −$1.24 | −$22.36 | $98.35 | {'day_cap': 239, 'total_cap': 8077} |
| B | lean +5c stop=25c limit=hold | 75 | 45.3% | 91.9% | **−$97.10** | −$8463.39 | −$1.29 | −$22.36 | $97.10 | {'day_cap': 242, 'total_cap': 8078} |
| B | lean +10c stop=none limit=1m | 73 | 9.6% | 72.2% | **−$96.48** | −$10452.82 | −$1.32 | −$22.18 | $96.48 | {'day_cap': 242, 'total_cap': 8080} |
| B | lean +10c stop=none limit=5m | 82 | 45.1% | 82.4% | **−$96.08** | −$8370.44 | −$1.17 | −$24.36 | $96.08 | {'day_cap': 236, 'total_cap': 8077} |
| B | lean +10c stop=none limit=hold | 123 | 74.0% | 89.3% | **−$97.59** | −$6132.59 | −$0.79 | −$23.82 | $97.59 | {'day_cap': 204, 'total_cap': 8068} |
| B | lean +10c stop=25c limit=1m | 73 | 9.6% | 72.2% | **−$96.48** | −$10471.77 | −$1.32 | −$22.18 | $96.48 | {'day_cap': 242, 'total_cap': 8080} |
| B | lean +10c stop=25c limit=5m | 76 | 36.8% | 80.8% | **−$97.43** | −$8938.16 | −$1.28 | −$23.56 | $97.43 | {'day_cap': 235, 'total_cap': 8084} |
| B | lean +10c stop=25c limit=hold | 82 | 46.3% | 83.3% | **−$98.18** | −$8692.85 | −$1.20 | −$22.73 | $98.18 | {'day_cap': 237, 'total_cap': 8076} |
| B | lean +15c stop=none limit=1m | 74 | 8.1% | 61.0% | **−$95.97** | −$10940.64 | −$1.30 | −$22.13 | $95.97 | {'day_cap': 241, 'total_cap': 8080} |
| B | lean +15c stop=none limit=5m | 87 | 39.1% | 73.8% | **−$97.76** | −$8936.27 | −$1.12 | −$24.06 | $97.76 | {'day_cap': 234, 'total_cap': 8074} |
| B | lean +15c stop=none limit=hold | 116 | 69.0% | 84.3% | **−$97.70** | −$5707.81 | −$0.84 | −$23.38 | $97.70 | {'day_cap': 215, 'total_cap': 8064} |
| B | lean +15c stop=25c limit=1m | 74 | 8.1% | 61.0% | **−$95.97** | −$10948.03 | −$1.30 | −$22.13 | $95.97 | {'day_cap': 241, 'total_cap': 8080} |
| B | lean +15c stop=25c limit=5m | 77 | 31.2% | 72.8% | **−$98.33** | −$9292.87 | −$1.28 | −$23.71 | $98.33 | {'day_cap': 238, 'total_cap': 8080} |
| B | lean +15c stop=25c limit=hold | 72 | 36.1% | 75.3% | **−$97.58** | −$8635.14 | −$1.36 | −$23.24 | $97.58 | {'day_cap': 246, 'total_cap': 8077} |
| B | mom15 +5c stop=none limit=1m | 76 | 28.9% | 88.1% | **−$95.83** | −$10648.15 | −$1.26 | −$23.66 | $95.83 | {'day_cap': 234, 'total_cap': 8080} |
| B | mom15 +5c stop=none limit=5m | 92 | 60.9% | 92.4% | **−$98.52** | −$9029.24 | −$1.07 | −$23.49 | $98.52 | {'day_cap': 219, 'total_cap': 8079} |
| B | mom15 +5c stop=none limit=hold | 131 | 79.4% | 94.7% | **−$99.26** | −$7990.44 | −$0.76 | −$24.92 | $100.93 | {'day_cap': 183, 'total_cap': 8076} |
| B | mom15 +5c stop=25c limit=1m | 76 | 28.9% | 88.1% | **−$95.83** | −$10709.63 | −$1.26 | −$23.66 | $95.83 | {'day_cap': 234, 'total_cap': 8080} |
| B | mom15 +5c stop=25c limit=5m | 82 | 52.4% | 91.5% | **−$96.09** | −$9672.95 | −$1.17 | −$23.13 | $96.09 | {'day_cap': 228, 'total_cap': 8080} |
| B | mom15 +5c stop=25c limit=hold | 78 | 51.3% | 92.1% | **−$98.70** | −$9643.54 | −$1.27 | −$22.22 | $98.70 | {'day_cap': 236, 'total_cap': 8076} |
| B | mom15 +10c stop=none limit=1m | 68 | 11.8% | 73.0% | **−$96.14** | −$11430.01 | −$1.41 | −$21.45 | $96.14 | {'day_cap': 245, 'total_cap': 8077} |
| B | mom15 +10c stop=none limit=5m | 96 | 51.0% | 80.4% | **−$96.54** | −$9610.76 | −$1.01 | −$23.51 | $96.54 | {'day_cap': 215, 'total_cap': 8079} |
| B | mom15 +10c stop=none limit=hold | 144 | 75.0% | 88.1% | **−$99.77** | −$7767.98 | −$0.69 | −$23.88 | $100.88 | {'day_cap': 167, 'total_cap': 8079} |
| B | mom15 +10c stop=25c limit=1m | 68 | 11.8% | 73.0% | **−$96.14** | −$11452.11 | −$1.41 | −$21.45 | $96.14 | {'day_cap': 245, 'total_cap': 8077} |
| B | mom15 +10c stop=25c limit=5m | 82 | 41.5% | 79.0% | **−$97.82** | −$10049.94 | −$1.19 | −$21.76 | $97.82 | {'day_cap': 230, 'total_cap': 8078} |
| B | mom15 +10c stop=25c limit=hold | 81 | 46.9% | 81.5% | **−$98.43** | −$9912.84 | −$1.22 | −$22.22 | $98.43 | {'day_cap': 231, 'total_cap': 8078} |
| B | mom15 +15c stop=none limit=1m | 69 | 10.1% | 63.1% | **−$96.34** | −$11966.60 | −$1.40 | −$23.09 | $96.34 | {'day_cap': 242, 'total_cap': 8079} |
| B | mom15 +15c stop=none limit=5m | 100 | 44.0% | 71.0% | **−$96.51** | −$10161.24 | −$0.97 | −$21.54 | $96.51 | {'day_cap': 212, 'total_cap': 8078} |
| B | mom15 +15c stop=none limit=hold | 129 | 69.0% | 82.3% | **−$97.31** | −$7551.06 | −$0.75 | −$22.62 | $99.07 | {'day_cap': 182, 'total_cap': 8079} |
| B | mom15 +15c stop=25c limit=1m | 69 | 10.1% | 63.1% | **−$96.34** | −$11982.30 | −$1.40 | −$23.09 | $96.34 | {'day_cap': 242, 'total_cap': 8079} |
| B | mom15 +15c stop=25c limit=5m | 81 | 35.8% | 70.9% | **−$98.55** | −$10427.26 | −$1.22 | −$22.73 | $98.55 | {'day_cap': 231, 'total_cap': 8078} |
| B | mom15 +15c stop=25c limit=hold | 73 | 39.7% | 73.8% | **−$95.84** | −$9986.38 | −$1.31 | −$23.64 | $95.84 | {'day_cap': 237, 'total_cap': 8080} |
| C | margin=0c L=5 | 646 | 74.0% | 90.8% | **−$95.91** | −$364.79 | −$0.15 | −$9.01 | $96.66 | {'total_cap': 889} |
| C | margin=0c L=15 | 389 | 77.9% | 94.6% | **−$96.12** | −$294.00 | −$0.25 | −$14.33 | $96.78 | {'total_cap': 607} |
| C | margin=0c L=60 | 331 | 74.3% | 94.8% | **−$97.22** | −$204.34 | −$0.29 | −$9.46 | $97.70 | {'total_cap': 276} |
| C | margin=1c L=5 | 531 | 82.5% | 94.6% | **−$98.63** | −$342.55 | −$0.19 | −$9.49 | $99.24 | {'total_cap': 875} |
| C | margin=1c L=15 | 374 | 75.9% | 94.3% | **−$97.16** | −$234.74 | −$0.26 | −$14.42 | $97.82 | {'total_cap': 459} |
| C | margin=1c L=60 | 269 | 74.3% | 95.6% | **−$96.37** | −$169.70 | −$0.36 | −$9.56 | $96.86 | {'total_cap': 182} |
| C | margin=2c L=5 | 481 | 81.3% | 94.6% | **−$98.04** | −$308.95 | −$0.20 | −$14.38 | $98.58 | {'total_cap': 772} |
| C | margin=2c L=15 | 336 | 75.9% | 94.5% | **−$99.00** | −$202.71 | −$0.29 | −$14.42 | $99.57 | {'total_cap': 306} |
| C | margin=2c L=60 | 227 | 75.8% | 96.1% | **−$97.38** | −$123.59 | −$0.43 | −$18.28 | $97.78 | {'total_cap': 86} |
| D | fade margin=2c L=15 | 893 | 95.2% | 97.4% | **−$97.58** | −$166.03 | −$0.11 | −$16.65 | $102.86 | {'total_cap': 591} |
| D | fade margin=2c L=60 | 572 | 92.8% | 97.1% | **−$98.03** | −$134.41 | −$0.17 | −$18.00 | $99.94 | {'total_cap': 354} |
| D | fade margin=5c L=15 | 338 | 94.4% | 96.3% | **−$31.82** | −$31.82 | −$0.09 | −$4.68 | $36.53 |  |
| D | fade margin=5c L=60 | 130 | 90.0% | 96.2% | **−$39.76** | −$39.76 | −$0.31 | −$7.38 | $41.03 |  |
| D | buy margin=2c L=15 | 30 | 3.3% | 9.7% | **−$97.69** | −$5306.77 | −$3.26 | −$24.81 | $114.00 | {'day_cap': 31, 'total_cap': 1611} |
| D | buy margin=2c L=60 | 30 | 3.3% | 9.7% | **−$97.59** | −$6725.13 | −$3.25 | −$24.84 | $118.86 | {'day_cap': 50, 'total_cap': 2097} |
| D | buy margin=5c L=15 | 34 | 5.9% | 13.9% | **−$97.19** | −$2873.81 | −$2.86 | −$24.76 | $113.50 | {'day_cap': 9, 'total_cap': 910} |
| D | buy margin=5c L=60 | 34 | 5.9% | 13.9% | **−$96.85** | −$3751.72 | −$2.85 | −$24.71 | $118.12 | {'day_cap': 9, 'total_cap': 1258} |

## Skips per variant (train)

| Strat | Variant | Skips |
|---|---|---|
| A | mom5 | {'no_signal': 13} |
| A | mom15 | {'no_signal': 6} |
| A | mom60 | {'no_signal': 4} |
| A | rev5 | {'no_signal': 13} |
| A | rev15 | {'no_signal': 6} |
| A | rev60 | {'no_signal': 4} |
| A | lean | {'no_signal': 1} |
| A | antilean | {'no_signal': 1} |
| B | lean +5c stop=none limit=1m | {'no_signal': 1} |
| B | lean +5c stop=none limit=5m | {'no_signal': 1} |
| B | lean +5c stop=none limit=hold | {'no_signal': 1} |
| B | lean +5c stop=25c limit=1m | {'no_signal': 1} |
| B | lean +5c stop=25c limit=5m | {'no_signal': 1} |
| B | lean +5c stop=25c limit=hold | {'no_signal': 1} |
| B | lean +10c stop=none limit=1m | {'no_signal': 1} |
| B | lean +10c stop=none limit=5m | {'no_signal': 1} |
| B | lean +10c stop=none limit=hold | {'no_signal': 1} |
| B | lean +10c stop=25c limit=1m | {'no_signal': 1} |
| B | lean +10c stop=25c limit=5m | {'no_signal': 1} |
| B | lean +10c stop=25c limit=hold | {'no_signal': 1} |
| B | lean +15c stop=none limit=1m | {'no_signal': 1} |
| B | lean +15c stop=none limit=5m | {'no_signal': 1} |
| B | lean +15c stop=none limit=hold | {'no_signal': 1} |
| B | lean +15c stop=25c limit=1m | {'no_signal': 1} |
| B | lean +15c stop=25c limit=5m | {'no_signal': 1} |
| B | lean +15c stop=25c limit=hold | {'no_signal': 1} |
| B | mom15 +5c stop=none limit=1m | {'no_signal': 6} |
| B | mom15 +5c stop=none limit=5m | {'no_signal': 6} |
| B | mom15 +5c stop=none limit=hold | {'no_signal': 6} |
| B | mom15 +5c stop=25c limit=1m | {'no_signal': 6} |
| B | mom15 +5c stop=25c limit=5m | {'no_signal': 6} |
| B | mom15 +5c stop=25c limit=hold | {'no_signal': 6} |
| B | mom15 +10c stop=none limit=1m | {'no_signal': 6} |
| B | mom15 +10c stop=none limit=5m | {'no_signal': 6} |
| B | mom15 +10c stop=none limit=hold | {'no_signal': 6} |
| B | mom15 +10c stop=25c limit=1m | {'no_signal': 6} |
| B | mom15 +10c stop=25c limit=5m | {'no_signal': 6} |
| B | mom15 +10c stop=25c limit=hold | {'no_signal': 6} |
| B | mom15 +15c stop=none limit=1m | {'no_signal': 6} |
| B | mom15 +15c stop=none limit=5m | {'no_signal': 6} |
| B | mom15 +15c stop=none limit=hold | {'no_signal': 6} |
| B | mom15 +15c stop=25c limit=1m | {'no_signal': 6} |
| B | mom15 +15c stop=25c limit=5m | {'no_signal': 6} |
| B | mom15 +15c stop=25c limit=hold | {'no_signal': 6} |
| C | margin=0c L=5 | {'no_signal': 6773, 'no_fill': 85, 'no_model': 3} |
| C | margin=0c L=15 | {'no_signal': 7344, 'no_fill': 50, 'no_model': 6} |
| C | margin=0c L=60 | {'no_model': 21, 'no_signal': 7736, 'no_fill': 32} |
| C | margin=1c L=5 | {'no_signal': 6910, 'no_fill': 77, 'no_model': 3} |
| C | margin=1c L=15 | {'no_signal': 7520, 'no_fill': 37, 'no_model': 6} |
| C | margin=1c L=60 | {'no_model': 21, 'no_signal': 7902, 'no_fill': 22} |
| C | margin=2c L=5 | {'no_signal': 7073, 'no_fill': 67, 'no_model': 3} |
| C | margin=2c L=15 | {'no_signal': 7727, 'no_model': 6, 'no_fill': 21} |
| C | margin=2c L=60 | {'no_model': 21, 'no_signal': 8043, 'no_fill': 19} |
| D | fade margin=2c L=15 | {'no_signal': 6907, 'no_model': 5} |
| D | fade margin=2c L=60 | {'no_model': 13, 'no_signal': 7457} |
| D | fade margin=5c L=15 | {'no_signal': 8053, 'no_model': 5} |
| D | fade margin=5c L=60 | {'no_model': 13, 'no_signal': 8253} |
| D | buy margin=2c L=15 | {'no_signal': 6719, 'no_model': 5} |
| D | buy margin=2c L=60 | {'no_model': 12, 'no_signal': 6207} |
| D | buy margin=5c L=15 | {'no_signal': 7438, 'no_model': 5} |
| D | buy margin=5c L=60 | {'no_model': 12, 'no_signal': 7083} |

## Selected for the test set (pre-registered rule)

- **A:** mom60
- **B:** mom15 +5c stop=none limit=1m
- **C:** margin=0c L=5
- **D:** fade margin=5c L=15
