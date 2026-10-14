"""Read-only Kalshi client for the KXBTC15M series (public market-data endpoints only).

Adapted from alt-scalp `src/altscalp/kalshi.py` @ db83d7d (itself from alt-arb @ 594878f).
It holds no credentials and has no order-placement code: S0 is read-only.

Units: Kalshi sends prices as dollar strings with up to 4 decimals ("0.9530") and contract
counts as fixed-point strings with 2 decimals ("915.99" - fractional contracts trade). They
are converted exactly to integers: prices in 1/10,000 dollar ("e4"), sizes in 1/100 contract
("e2"). Never float (CLAUDE.md rule 8).

Order books contain bids only. The YES ask is 1 - best NO bid, and the depth you can buy
YES from is the NO bid ladder. Levels are always sorted best first here, because the API
has been seen returning them worst-to-best.

Markets that settled before the cutoff in GET /historical/cutoff (2026-08-14 as of
2026-10-13) are served only by the /historical/* endpoints; see docs/s0-research.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

import httpx

from slot.http import RateLimitCounter, get_json

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
SERIES = "KXBTC15M"
MAX_ORDERBOOK_TICKERS = 100  # GET /markets/orderbooks limit
CENT = Decimal("0.01")


def price_e4(value: str) -> int:
    """'0.5100' -> 5100. Raises if the string has more precision than 1/10,000."""
    return _exact_int(Decimal(value) * 10_000, value)


def size_e2(value: str) -> int:
    """'102.94' -> 10294. Raises if the string has more precision than 1/100."""
    return _exact_int(Decimal(value) * 100, value)


def _exact_int(scaled: Decimal, original: str) -> int:
    if scaled != scaled.to_integral_value():
        raise ValueError(f"unexpected precision in {original!r}")
    return int(scaled)


def parse_ts(value: str) -> datetime:
    """'2026-10-14T03:15:00Z' -> aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Level:
    price_e4: int
    size_e2: int


@dataclass(frozen=True)
class Book:
    ticker: str
    yes_bids: list[Level]  # best (highest) first
    no_bids: list[Level]  # best (highest) first
    raw: dict[str, Any]  # the API's orderbook_fp object, as received

    @property
    def best_yes_bid_e4(self) -> int | None:
        return self.yes_bids[0].price_e4 if self.yes_bids else None

    @property
    def best_yes_ask_e4(self) -> int | None:
        return 10_000 - self.no_bids[0].price_e4 if self.no_bids else None

    @property
    def best_no_ask_e4(self) -> int | None:
        return 10_000 - self.yes_bids[0].price_e4 if self.yes_bids else None

    def asks(self, side: str) -> list[Level]:
        """Ask ladder for buying `side` ('yes'/'no'), best (lowest) first."""
        opposite = {"yes": self.no_bids, "no": self.yes_bids}[side]
        return [Level(10_000 - lvl.price_e4, lvl.size_e2) for lvl in opposite]

    def walk_buy(self, side: str, count_e2: int) -> tuple[int, int] | None:
        """Cost of taking `count_e2` contracts of `side` by walking the ask ladder.

        Returns (filled_e2, cost_e6) where cost is in 1/1,000,000 dollar (e4 price x e2 size),
        before fees. Returns None for an empty ladder. A partial fill (thin book) is reported
        as filled_e2 < count_e2, never padded.
        """
        ladder = self.asks(side)
        if not ladder:
            return None
        filled = cost = 0
        for lvl in ladder:
            take = min(lvl.size_e2, count_e2 - filled)
            filled += take
            cost += take * lvl.price_e4
            if filled == count_e2:
                break
        return filled, cost


def parse_book(ticker: str, orderbook_fp: dict[str, Any]) -> Book:
    return Book(
        ticker=ticker,
        yes_bids=_parse_levels(orderbook_fp.get("yes_dollars")),
        no_bids=_parse_levels(orderbook_fp.get("no_dollars")),
        raw=orderbook_fp,
    )


def _parse_levels(raw: list[list[str]] | None) -> list[Level]:
    levels = [Level(price_e4(price), size_e2(size)) for price, size in raw or []]
    return sorted(levels, key=lambda lvl: lvl.price_e4, reverse=True)


@dataclass(frozen=True)
class Window:
    """One KXBTC15M market: 'is the 60 s BRTI average at close >= the 60 s average at open?'"""

    ticker: str
    open_time: datetime
    close_time: datetime
    status: str
    strike: Decimal | None  # target price; None until set at open (and on some Dec-2025 markets)
    expiration_value: Decimal | None  # settlement 60 s average, once known
    result: str  # 'yes' / 'no' / '' while open
    price_level_structure: str
    raw: dict[str, Any]


def parse_window(m: dict[str, Any]) -> Window:
    strike = m.get("floor_strike")
    # Usually "83628.01", but two Aug/Sep 2026 markets sent "77,362.10".
    exp = (m.get("expiration_value") or "").replace(",", "") or None
    return Window(
        ticker=m["ticker"],
        open_time=parse_ts(m["open_time"]),
        close_time=parse_ts(m["close_time"]),
        status=m["status"],
        # floor_strike arrives as a JSON number with float noise (67345.399999); the rules
        # round to 2 decimals (custom_strike.round_digits = "2").
        strike=None if strike is None else Decimal(strike).quantize(CENT, ROUND_HALF_EVEN),
        expiration_value=None if exp is None else Decimal(exp),
        result=m.get("result") or "",
        price_level_structure=m.get("price_level_structure", ""),
        raw=m,
    )


class KalshiClient:
    """Public market-data client. Holds no credentials and cannot place orders."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 10.0,
        http: httpx.Client | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http or httpx.Client(base_url=base_url, timeout=timeout)
        self._max_retries = max_retries
        self._sleep = sleep
        self.rate_limits = RateLimitCounter()

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def series(self, series_ticker: str = SERIES) -> dict[str, Any]:
        """Series metadata, including fee_type / fee_multiplier and settlement source."""
        return self._get(f"/series/{series_ticker}")["series"]

    def windows(self, status: str | None = None, series_ticker: str = SERIES, **filters: Any) -> Iterator[Window]:
        """Live (non-historical) markets in the series. Filters: min_close_ts, max_close_ts, ..."""
        params: dict[str, Any] = {"series_ticker": series_ticker, "limit": 1000, **filters}
        if status:
            params["status"] = status
        for m in self._paginate("/markets", params, "markets"):
            yield parse_window(m)

    def current_window(self, series_ticker: str = SERIES) -> Window | None:
        """The window trading now (status 'open' in the API's filter vocabulary)."""
        return next(self.windows(status="open", series_ticker=series_ticker), None)

    def historical_windows(self, series_ticker: str = SERIES) -> Iterator[Window]:
        """Markets settled before the historical cutoff, newest first."""
        params = {"series_ticker": series_ticker, "limit": 1000}
        for m in self._paginate("/historical/markets", params, "markets"):
            yield parse_window(m)

    def historical_cutoff(self) -> dict[str, Any]:
        return self._get("/historical/cutoff")

    def orderbooks(self, tickers: Iterable[str], max_retries: int = 0) -> dict[str, Book]:
        """Full-depth books for up to 100 tickers in one request.

        Retries default to 0: a poller's next tick is the retry, and blocking on backoff
        would only widen the gap.
        """
        tickers = list(tickers)
        if not 1 <= len(tickers) <= MAX_ORDERBOOK_TICKERS:
            raise ValueError(f"need 1..{MAX_ORDERBOOK_TICKERS} tickers, got {len(tickers)}")
        params = [("tickers", t) for t in tickers]
        data = get_json(self._http, "/markets/orderbooks", params, max_retries, self._sleep, self.rate_limits)
        return {ob["ticker"]: parse_book(ob["ticker"], ob["orderbook_fp"]) for ob in data.get("orderbooks", [])}

    def orderbook(self, ticker: str) -> Book | None:
        return self.orderbooks([ticker]).get(ticker)

    def trades(self, ticker: str, min_ts: int | None = None, max_ts: int | None = None) -> Iterator[dict[str, Any]]:
        """Public trade tape for one market (newest first). Timestamps are Unix seconds."""
        yield from self._paginate("/markets/trades", _trade_params(ticker, min_ts, max_ts), "trades")

    def historical_trades(self, ticker: str) -> Iterator[dict[str, Any]]:
        yield from self._paginate("/historical/trades", _trade_params(ticker, None, None), "trades")

    def candlesticks(self, ticker: str, start_ts: int, end_ts: int, period_minutes: int = 1) -> list[dict[str, Any]]:
        """OHLC of trade price, bid and ask per period (1, 60 or 1440 minutes)."""
        params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_minutes}
        path = f"/series/{SERIES}/markets/{ticker}/candlesticks"
        return self._get(path, params).get("candlesticks") or []

    def historical_candlesticks(self, ticker: str, start_ts: int, end_ts: int) -> list[dict[str, Any]]:
        """1-min candles for a market settled before the historical cutoff."""
        params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 1}
        return self._get(f"/historical/markets/{ticker}/candlesticks", params).get("candlesticks") or []

    def batch_candlesticks(self, tickers: list[str], start_ts: int, end_ts: int) -> dict[str, list[dict[str, Any]]]:
        """1-min candles for several live-era markets in one request. Kalshi caps a request at 10,000
        candles in total (markets x minutes), and pre-cutoff markets come back empty."""
        params = {"market_tickers": ",".join(tickers), "start_ts": start_ts, "end_ts": end_ts, "period_interval": 1}
        data = self._get("/markets/candlesticks", params)
        return {m["market_ticker"]: m.get("candlesticks") or [] for m in data.get("markets", [])}

    def _paginate(self, path: str, params: dict[str, Any], key: str) -> Iterator[dict[str, Any]]:
        params = dict(params)
        while True:
            data = self._get(path, params)
            items = data.get(key) or []
            yield from items
            cursor = data.get("cursor")
            if not cursor or not items:
                return
            params["cursor"] = cursor

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return get_json(self._http, path, params, self._max_retries, self._sleep, self.rate_limits)


def _trade_params(ticker: str, min_ts: int | None, max_ts: int | None) -> dict[str, Any]:
    params: dict[str, Any] = {"ticker": ticker, "limit": 1000}
    if min_ts is not None:
        params["min_ts"] = min_ts
    if max_ts is not None:
        params["max_ts"] = max_ts
    return params
