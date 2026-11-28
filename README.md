# alt-btc15 — Project Slot Machine

Automated trading research on Kalshi's 15-minute Bitcoin "up or down" markets (`KXBTC15M`).
A new market opens every 15 minutes, 24/7. The system backtests strategies, paper-trades them live with full logs,
and can only trade real money — with hard caps — after a strategy passes a pre-set gate and the owner records the decision.

Honest framing: this is small-stakes, capped-risk speculation. The goal is to find out, with evidence, whether any
strategy wins more than it loses after fees.

See `docs/spec.md` (plan) and `CLAUDE.md` (rules). Part of the `alt` portfolio — see [alt-hq](https://github.com/idownham/alt-hq).

## Status
**Done.** S1 backtest: no edge for strategies A–D (`docs/s1-results.md`). R1 maker test: **FAIL** (2026-11-25,
`docs/r1-results.md`). The recorder was stopped and disabled on 2026-11-25. No orders were ever placed.

## Setup
Requires Python 3.11 or newer. No API keys are needed: everything uses Kalshi's and Coinbase's public, read-only
endpoints. There is no `.env` to fill in (the code only reads an optional `KILL=1` kill-switch line from it).

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

## Reproducing the results
The data files are not in the repo (`data/` is gitignored), so the S1 history has to be pulled first. The R1 recorder
data can't be re-created: it was recorded live from Oct 14 to Nov 25, 2026.

```bash
# S1: pull history into data/s1.sqlite (paced public API calls), then run the backtest
.venv/bin/python -m slot.history --start 2026-06-01 --end 2026-10-13
.venv/bin/python -m slot.backtest train
.venv/bin/python -m slot.backtest test

# R1: maker test on the merged recorder DB (count usable windows, train, then test once)
.venv/bin/python -m slot.maker count --db data/recorder/r1-merged.sqlite --end 2026-11-10T06:00
.venv/bin/python -m slot.maker train --db data/recorder/r1-merged.sqlite --end 2026-11-10T06:00
.venv/bin/python -m slot.maker test  --db data/recorder/r1-merged.sqlite --end 2026-11-10T06:00

# Recorder status (counts and last rows in a recorder DB)
.venv/bin/python -m slot.recorder status --db data/recorder/book.sqlite
```

The merged R1 DB was built with `python -m slot.merge LAPTOP DROPLET OUT --report`. Results are written to `docs/`
(`s1-train.md`, `s1-test.md`, `r1-train.md`, `r1-test.md`).
