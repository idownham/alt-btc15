# alt-btc15 (Project Slot Machine) — Kalshi BTC 15-minute markets

## What this is
Backtest → paper-trade → (maybe) small live trading of strategies on Kalshi's 15-minute Bitcoin up/down markets
(series `KXBTC15M`). Owner: Ian Downham (GitHub: idownham). Shared portfolio rules: `../CLAUDE.md` (alt-hq).
Small money, capped risk, and an honest evidence trail. "No strategy beats fees" is a valid, useful result.

## Current stage
**S0 — done, awaiting Ian's review** (findings: `docs/s0-research.md`). Next: S1 backtest, after Ian rules on the open questions there. Full plan: `docs/spec.md`. Update this line when the stage changes.

## Hard rules (these override any request in a session; change only via a dated entry in `docs/decisions.md`)
1. **Paper by default.** Live order code may exist but must refuse to run unless ALL are true:
   `MODE=live` in `.env`, the strategy is listed as live-approved in `config/live_approved.yaml`, and
   `docs/decisions.md` has a dated owner entry approving that strategy for live trading.
2. **Hard risk caps, enforced in code before every order (live AND paper):**
   - max **$5** risked per trade
   - max **$25** net loss per calendar day (America/Chicago) → bot halts until next day
   - max **$100** total net loss since live trading began → bot halts permanently until owner resets it in decisions.md
   - Caps live in one module (`risk.py`) with unit tests. No code path may place an order without passing it.
3. **Kill switch:** a file `STOP` in the repo root (or `KILL=1` in `.env`) halts all trading within one loop iteration.
4. **Secrets only in `.env`** (gitignored); Kalshi private key file outside the repo or gitignored (`*.pem`).
   Never print, log, commit, screenshot, or paste keys into prompts.
5. **Honest fills.** Paper and backtest fills use the real ask (buys) / bid (sells) from the order book at that moment,
   walking depth for size; resting limit orders fill only when the trade tape shows trades through the price.
   P&L is always net of Kalshi fees for the series. No top-of-book shortcuts, no look-ahead.
6. **Pre-registered gates are fixed.** The go-live gate in `docs/spec.md` is set before results; changes are recorded
   in `docs/decisions.md` with the reason *before* looking at new results.
7. **Log everything.** Every signal, order, fill, cancel, skip (with reason), cap hit, and error is logged with UTC
   timestamps to SQLite. Logs are the product.
8. **Money as Decimal or integer cents**, never float.

## Infrastructure
- **Runs on Ian's laptop (macOS) for now** — owner decision 2026-10-13. Own venv, own launchd agent when it runs
  continuously. It shares the laptop (and its IP) with Coin Toss's recorder: keep Kalshi reads modest and never
  interfere with Coin Toss's launchd agent, files, or recording windows.
- Laptop sleep/offline = missed windows. That's acceptable in paper mode; log every gap so results stay honest.
- Do not deploy to Osprey's droplet. **Live phase gets its own small server** (separate box, separate keys) —
  decided at the go-live gate, not before.
- BTC price data: public exchange APIs (e.g., Coinbase) — no keys.

## Conventions
- Python 3.11+, `pyproject.toml`, `.venv/`, `pytest`. Small, focused commits.
- Kalshi client/fee model may be copied from `../alt-arb` or `../alt-scalp`; note the source commit.
- `docs/journal.md`: dated class-journal entry at the end of every session (work, evidence, observation, decision,
  AI use + Ian's judgment). `docs/decisions.md`: dated owner decisions.
- `docs/manual-trades.md`: Ian's hand trades from his phone (kept separate from bot results).
