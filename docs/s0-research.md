# S0 research — KXBTC15M (Project Slot Machine)

*Researched 2026-10-13 (evening CDT) from Kalshi's public API, Kalshi's contract filings and Coinbase's public API.
No keys and no trading. Numbers can be re-run with `scripts/s0_checks.py --history`.*

## TL;DR: what changes the plan

1. **Settlement is a 60-second average, and so is the target.** YES if the simple average of the 60 one-second
   BRTI prints before close ≥ the simple average of the 60 prints before open. This changes the fair-value model
   most in the last minute (§7). **The spec's `N(d)` with τ = time left is wrong for strategy C.** It must be
   replaced by an average-aware model before S1 tests C or D.
2. **In the final ~45 s the outcome is mostly locked in**, because most of the average is already known. With BTC
   $30 ahead at 30 s left, the naive model says 89%; the average-aware model says ≈100%. The market knows this
   (the settled window checked closed at 99.9¢). C's edge, if there is one, sits in the 60–180 s band and in how
   well we track BRTI, not in "the favorite usually wins".
3. **Our BTC price is only a proxy.** Kalshi settles on CF Benchmarks' BRTI, which isn't free in real time. The
   Coinbase 1-min proxy picked the wrong winner in **10 of 288** recent windows (3.5%). Backtest outcomes must use
   Kalshi's own `result`, never the proxy. Late in the window, proxy error (~$5) is the same size as the remaining
   BTC uncertainty, which hurts C most.
4. **The backtest needs 1-second BTC data for anything in the last minute.** 1-min candles can't show the inside
   of the averaging minute. Binance publishes free 1-second klines (BTCUSDT/BTCUSDC: a USD-stablecoin proxy, not USD).
5. **There is no historical order book.** Kalshi has 1-min candlesticks (bid/ask/trade OHLC) and the full trade
   tape for every window since 2025-12-10. S1 fills must use conservative candle prices (§5). This is allowed by
   spec S1 ("say so and use conservative assumptions"), but it is weaker than rule 5's depth walk.
6. **Prices go to 0.1¢ near the tails** (`tapered_deci_cent` since 2026-03-17): 0.1¢ ticks below 10¢ and above
   90¢, 1¢ in between. Strategies C and D trade exactly in those bands.
7. **Fees are taker-only.** `quadratic`, multiplier 1: taker 0.07·C·P·(1−P), makers pay nothing, holding to
   settlement is free. A resting order is fee-free, which matters for B's +10¢ exit.

## 1. Settlement (the most important question)

| Item | Finding | Source |
|---|---|---|
| Index | CF Benchmarks **BRTI** (Bitcoin Real Time Index) | series `settlement_sources`; market `rules_primary` |
| Settlement value | **Simple average of the 60 seconds of BRTI before close** ("At the last minute before expiration, 60 RTI prices are collected. The official and final value is the average of these prices, rounded to the nearest 2 decimal places.") | market `rules_secondary`; series `product_metadata.important_info`; CRYPTO contract terms ("simple average of the CF … index for the 60 seconds prior to <time>") |
| Target ("strike") | **Simple average of the 60 seconds of BRTI before open**, shown as `floor_strike` / "Target Price" from the open | `rules_primary` on every market since 2026-01-10 |
| Chain | The next window's target **equals** the previous window's settlement value in 19,981 of 19,985 back-to-back pairs. The 4 exceptions are data errors (2 strikes stored as 7.24 / 7.20 instead of ~72,437 on 2026-04-13; 2 off by $0.07 / $3.15). | `/historical/markets`, checked here |
| Comparison | `strike_type: greater_or_equal`: **a tie settles YES** ("at least X means X or greater"). No exact ties in 22,886 windows. | contract terms; market fields |
| Missing data | "If no data is available or incomplete … affected strikes resolve to No." | CRYPTO contract terms |
| Timing | Windows are :00/:15/:30/:45 UTC, back to back, 24/7. Settlement posts ~5 s after close recently (`settlement_ts` 03:15:04.6 for a 03:15 close). Across all history: median 13 s, p95 ~31 min, max ~24 h (reviews). | market `settlement_ts` |
| Rules history | Settlement has been a 60-s average since the series started (2025-12-10). Before 2026-01-10 the target was worded "the price of Bitcoin at <open> according to CF Benchmarks" (single print?). On 2026-03-10 and 2026-06-05 (two windows) the target was a fixed number. | `rules_primary` across all historical markets |

## 2. Fees

| Item | Value | Source |
|---|---|---|
| `fee_type` / `fee_multiplier` | `quadratic` / `1` | `GET /series/KXBTC15M` |
| Taker fee | 0.07 × C × P × (1−P): 1.75¢/contract at 50¢, 0.33¢ at 95¢, 0.07¢ at 99¢ | coefficient per alt-scalp S0 research (Kalshi fee-schedule page) |
| Maker fee | **0**: `quadratic` series have no maker fee; maker-fee series use type `quadratic_with_maker_fees` (0.0175×) | API `fee_type` naming; alt-scalp S0 research. *The fee-schedule PDF/page blocked automated download (HTTP 429), so this is not quoted from it. Ian: worth a 1-minute check on kalshi.com/fee-schedule.* |
| Settlement fee | none (hold-to-expiry pays only the entry fee) | fee schedule as summarized in spec / alt-scalp |
| Rounding | Each fill is rounded up to $0.000001, and overpayment is rebated via an accumulator. We use the conservative variant: ceil to the cent per order. | [docs: fee rounding](https://docs.kalshi.com/getting_started/fee_rounding) |
| Fee changes | None ever recorded for KXBTC15M | `GET /series/fee_changes?series_ticker=KXBTC15M&show_historical=true` → `[]` |

Implemented in `src/slot/fees.py`.

## 3. Market mechanics

- **Listing:** the 96 windows for a day are created in one batch around 20:01 UTC the day before (status
  `initialized`), turn `active` at `open_time`, and are `finalized` after settlement. Ticker format:
  `KXBTC15M-26OCT132330-30` (event date/time is the **close**, in ET).
- **Ticks:** `price_level_structure` = `tapered_deci_cent` since 2026-03-17 (0.1¢ in [0, 10¢] and [90¢, $1], 1¢ in
  between). Before that: `linear_cent` (1¢ everywhere). Backtests across the switch must use the tick grid of the day.
- **Fractional contracts** trade (sizes have 2 decimals, e.g. 915.99), so a $5 stake can be sized exactly.
- **Liquidity:** median volume per window was 224k contracts over the full history and 1.6M over the last month
  before the cutoff. A live book had 168 YES / 111 NO levels and thousands of contracts at the top. A $5 order
  is tiny next to that.
- **Position accountability:** $25,000 per strike per member (irrelevant at our size).
- `can_close_early: true`; `expiration_time` is one week after close (Kalshi's latest allowed), and settlement is
  normally seconds after close.
- **Gaps:** 39 breaks in the 15-min chain in the historical set (mostly Dec 2025, with overnight pauses, and a few
  1–3 h pauses later). 357 early-December markets have no `floor_strike`. Backtests must skip windows whose
  strike is missing or doesn't match the rules.
- **Base rate:** 11,419 YES / 11,467 NO (49.8% YES) across 22,886 historical windows.

## 4. Rate limits and our footprint

- Kalshi Basic tier ≈ 20 reads/s per key/IP (HQ CLAUDE.md; docs.kalshi.com/getting_started/rate_limits). 429s carry
  no Retry-After header, so the client backs off 1, 2, 4 s.
- I hit 7 × 429 while paging one window's trade tape fast from the laptop, which is also the IP of the Coin Toss
  recorder. **Bulk history pulls must be paced (≤ 2–3 req/s)** and should avoid running while Coin Toss records
  kickoffs.
- Coinbase public: no keys; a User-Agent is required. No 429s seen.

## 5. Historical data available

| Data | Coverage | Endpoint | Cost to pull | Use |
|---|---|---|---|---|
| Kalshi markets (strike, settlement value, result) | 2025-12-10 → now (22,886 historical + everything since 2026-08-14) | `/historical/markets` (before cutoff), `/markets` (after) | ~25 requests total | **Ground-truth outcomes** |
| Kalshi 1-min candlesticks: yes_bid / yes_ask / trade OHLC, volume, OI | per window, both eras | `/series/KXBTC15M/markets/{t}/candlesticks` (also `/historical/markets/{t}/candlesticks`) | 1 request per window ≈ 8,600 for 3 months (~1 h paced) | Entry/exit prices for S1 |
| Kalshi trade tape | every trade | `/markets/trades`, `/historical/trades` | **heavy**: ~48,000 trades per window now (~50 pages); ~30,000 in Aug; ~360 in Jan | Spot checks and resting-limit fills (B) on samples only |
| Kalshi order-book history | **none** | — | — | Not available, so S2 records it live |
| BTC 1-min OHLCV (Coinbase BTC-USD) | years | `api.exchange.coinbase.com/products/BTC-USD/candles` (300 per request) | ~430 requests per 3 months | Signals for A/B; σ estimates |
| BTC 1-second klines (Binance BTCUSDT / BTCUSDC) | daily zip files, ~1–2 MB/day | `data.binance.vision/data/spot/daily/klines/<pair>/1s/` (checked reachable: HTTP 200) | ~90 files per 3 months | Final-minute modelling for C/D (stablecoin pair, so a proxy) |
| Coinbase BTC-USD trades | recent, paged backwards | `/products/BTC-USD/trades` | slow for long ranges | Not planned |

**Kalshi cutoff:** markets settled before `GET /historical/cutoff` → `market_settled_ts` (2026-08-14 as of today)
are only on `/historical/*`. The client has both.

**Honest-fill assumption for S1 (proposed):** without book history, a buy fills at the **high of that minute's
yes_ask** (no_ask for NO), and a sell fills at the **low of the bid**. Trades with entry and exit in the same minute
count as the worse ordering. Depth is assumed sufficient for ≤ $5 orders and reported as an assumption. Resting
+10¢ exits (B) fill only if the candle's **trade** high reaches the price, using the trade tape on a sample to
check that it trades *through*.

## 6. BTC price proxy vs the official settlement (measured)

Over the 288 windows of 2026-10-11 → 10-14, comparing Coinbase 1-min candles to Kalshi's `expiration_value`:

| Proxy for the 60-s settlement average | mean error | median abs error | p90 | max |
|---|---|---|---|---|
| Close of the last 1-min candle | −$2.70 | $8.84 | $26.92 | $107 |
| OHLC/4 of the last 1-min candle | −$1.71 | **$4.59** | $11.01 | $34 |

- Using the same proxy for the target, the proxy's direction matched the official result in **278 / 288 (96.5%)**.
- In 13.5% of windows the settlement landed within **$10** of the target (median distance $64). Those close
  calls are where proxy error flips outcomes.
- S2 should log 1-s Coinbase prices (and ideally a second constituent exchange) and re-measure the error at 1-s
  resolution. The 1-min numbers above are an upper bound.

## 7. How the averaging changes the fair-value model (flag for strategy C)

Treat BTC as a driftless random walk with σ dollars per √second (recent 3 days: 4.2 bp per minute ≈ **$4.56/√s** at
$83.7k). Let τ be the seconds left.

- **τ ≥ 60 s:** settlement = price at (close − 60 s) + the average of the final minute's path. Its spread is
  σ·√(τ − 40), so **τ_eff = τ − 40 s**, not τ.
- **τ < 60 s:** (60 − τ) of the 60 prints are **already known**. Settlement = [(60−τ)·A_known + τ·S_now]/60 ± the
  remaining average, whose spread is only σ·√(τ³ / 10,800).

Probability YES when BTC (and the running average) is **$30 above target**:

| seconds left | spread, naive single print | spread, 60-s average | P(YES) naive | P(YES) average-aware |
|---|---|---|---|---|
| 900 | $137 | $134 | 0.587 | 0.589 |
| 300 | $79 | $74 | 0.648 | 0.658 |
| 120 | $50 | $41 | 0.726 | 0.769 |
| 60 | $35 | $20 | 0.802 | **0.929** |
| 45 | $31 | $13 | 0.837 | **0.988** |
| 30 | $25 | $7 | 0.885 | **≈1.000** |
| 15 | $18 | $2.5 | 0.955 | ≈1.000 |

*(Illustration under a random-walk assumption. For τ < 60 it assumes the known part of the average sits at the same
+$30; the real model must track the running average.)*

**Consequences:**
- **C (late favorite):** the naive model **understates** the favorite's chance in the last ~90 s, so it would make
  95¢ favorites look overpriced and skip them, or mis-size the margin. The average-aware model is required. Inside
  ~45 s the remaining BTC spread ($7–13) is about the size of our proxy error ($5+), so the edge there is about
  **replicating BRTI**, where traders with a licensed BRTI feed beat us. Proposal: define C's entry band as
  **60–180 s left** (where the model matters and our proxy is adequate) and test ≤ 60 s separately as a
  "proxy-limited" variant. Prices also go up to 99.9¢ (0.1¢ ticks), so the margin per trade can be only tenths of
  a cent. That makes this a large-sample question.
- **D (longshot fade):** the reverse. The naive model overstates longshots' chances late, so it would hide
  overpricing. Same fix.
- **A (direction at open):** the target is fixed from the minute *before* open, so BTC has already moved ~30 s
  away from it when the window opens. The opening price is not exactly 50¢, and the model must use S_open vs K.
  Break-even math is unchanged.
- **B (open scalp):** unaffected by settlement (it exits before close). The 1¢ ticks in 10–90¢ apply, and the
  resting exit pays no maker fee.

## 8. Code built in S0 (read-only)

| File | What | Tests |
|---|---|---|
| `src/slot/kalshi.py` | Public KXBTC15M client: series, current/live/historical windows, order books (with ask ladders and a depth walk), trades, candlesticks. Exact integer prices/sizes, Decimal strikes. Adapted from alt-scalp `kalshi.py` @ db83d7d. | `tests/test_clients.py` |
| `src/slot/btc.py` | Coinbase BTC-USD ticker + 1-min candles (Decimal) | `tests/test_clients.py` |
| `src/slot/http.py` | GET with 429 backoff; JSON numbers parsed as **Decimal** (Kalshi sends `floor_strike` as a float-noisy number like 67345.399999). From alt-scalp `http.py` @ db83d7d. | via client tests |
| `src/slot/fees.py` | Taker/maker fee, conservative cent rounding | `tests/test_fees.py` |
| `src/slot/risk.py` | $5/trade, $25/Chicago day, $100 total (permanent until a dated "reset" entry in decisions.md), STOP file / KILL=1 kill switch. Caps apply to the **worst case** (realized + open risk + new order), so fills can't break a cap. | `tests/test_risk.py` (28 tests incl. parametrized) |
| `scripts/s0_checks.py` | Re-runs the measurements in this doc | — |

`pytest`: 40 unit tests pass. `pytest -m live`: 1 read-only smoke test against both APIs passes. No order code exists.

## 9. Open questions / decisions for Ian (before S1)

1. **Replace the fair-value model** in spec with the average-aware version (§7) and **set C's entry band**
   (proposal: 60–180 s, with ≤ 60 s as a separate variant). Strategy parameters, not gates; record them before S1
   results.
2. **Approve the S1 fill assumption** in §5 (worst-in-minute candle prices, no depth history).
3. **Risk-cap scope in paper:** one shared $25/day for all strategies (as live would be), or one cap per strategy
   so they don't block each other in S2? The code supports either (one `RiskManager` per ledger). Proposal: per
   strategy in paper, one global in live.
4. **Second BTC source** for S2 (e.g., Kraken or Bitstamp, both BRTI constituents per CF Benchmarks; to verify) to
   get closer to BRTI.
5. Confirm on kalshi.com/fee-schedule that KXBTC15M has no maker fee (blocked to automated fetch).
6. Go-live gate in spec is still PROPOSED (unchanged; needs Ian before S2).

## Sources

- Kalshi public API (fetched 2026-10-13): `GET /series/KXBTC15M`, `/markets?series_ticker=KXBTC15M`,
  `/historical/markets`, `/historical/cutoff`, `/historical/trades`, `/markets/trades`,
  `/series/KXBTC15M/markets/{ticker}/candlesticks`, `/series/fee_changes` — base `https://external-api.kalshi.com/trade-api/v2`
- Kalshi CRYPTO contract terms: https://assets.kalshi.com/contract_terms/CRYPTO.pdf; product certification:
  https://assets.kalshi.com/regulatory/product-certifications/CRYPTO.pdf
- Kalshi docs: https://docs.kalshi.com/getting_started/fee_rounding, https://docs.kalshi.com/getting_started/rate_limits
- Kalshi fee schedule (blocked to automated fetch here): https://kalshi.com/fee-schedule,
  https://kalshi.com/docs/kalshi-fee-schedule.pdf; fee coefficient as recorded in `../alt-scalp/docs/s0-research.md` §1
- CF Benchmarks BRTI: https://www.cfbenchmarks.com/data/indices/BRTI (methodology consultation, Apr 2026:
  https://www.cfbenchmarks.com/blog/announcement-of-consultation-on-changes-to-the-cme-cf-real-time-index-methodology)
- Third-party fee explainer (cross-check only): https://pm.wiki/fr/learn/prediction-market-arbitrage-after-fees
- Coinbase Exchange public API: https://api.exchange.coinbase.com (`/products/BTC-USD/ticker`, `/candles`, `/trades`)
- Binance public data (1-s klines): https://data.binance.vision/
