# alt-btc15 (Project Slot Machine) — Kalshi BTC 15-minute markets

## What this is
Backtest → paper-trade → (maybe) small live trading of strategies on Kalshi's 15-minute Bitcoin up/down markets
(series `KXBTC15M`). Owner: Ian Downham (GitHub: idownham). Shared portfolio rules: `../CLAUDE.md` (alt-hq).
Small money, capped risk, and an honest evidence trail. "No strategy beats fees" is a valid, useful result.

## Current stage
**R1 — read-only order-book recorder (reopened 2026-10-14 for idea 1, maker strategies).** S1 found no edge for A–D (`docs/s1-results.md`). No orders of any kind. No maker analysis until a maker pre-registration is committed (decisions.md 2026-10-14).

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
   *S1 exception (decisions.md 2026-10-13): no book history exists, so backtests use the worst-in-minute candle rule in `docs/spec.md`.*
6. **Pre-registered gates are fixed.** The go-live gate in `docs/spec.md` is set before results; changes are recorded
   in `docs/decisions.md` with the reason *before* looking at new results.
7. **Log everything.** Every signal, order, fill, cancel, skip (with reason), cap hit, and error is logged with UTC
   timestamps to SQLite. Logs are the product.
8. **Money as Decimal or integer cents**, never float.

## Infrastructure
- **R1 recorder runs on the shared droplet `alt-arb` since 2026-11-09** (cutover T = 04:45 UTC; owner decision 2026-10-18;
  HQ decision 2026-10-15; plan and log in `docs/r1-droplet-move.md`): `alt-btc15-recorder.service`, user `altbtc15`,
  `/opt/alt-btc15`, DB `/opt/alt-btc15/data/recorder/book.sqlite`. The laptop launchd agent is unloaded, and the laptop DB
  is kept as is for the merge.
  On the droplet: own Linux user, own folder (`/opt/alt-btc15`), own systemd unit, read-only, **no keys**, **no Polymarket
  calls** (Osprey only), and never touch Osprey's (or Coin Toss's) user, files or services. Kalshi's IP limit is shared,
  so keep the 429 back-off.
- Laptop sleep/offline = missed windows. Log every gap so results stay honest.
- **Live phase gets its own small server** (separate box, separate keys), decided at the go-live gate, not before. The
  shared droplet never holds keys or places orders.
- BTC price data: public exchange APIs (e.g., Coinbase) — no keys.

## Conventions
- Python 3.11+, `pyproject.toml`, `.venv/`, `pytest`. Small, focused commits.
- Kalshi client/fee model may be copied from `../project-osprey` (repo alt-arb) or `../project-coin-toss` (repo alt-scalp); note the source commit.
- `docs/journal.md`: dated class-journal entry at the end of every session (work, evidence, observation, decision,
  AI use + Ian's judgment). `docs/decisions.md`: dated owner decisions.
- `docs/manual-trades.md`: Ian's hand trades from his phone (kept separate from bot results).
