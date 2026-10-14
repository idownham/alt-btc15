"""Read-only BTC-USD price client (Coinbase Exchange public API, no keys).

Kalshi settles KXBTC15M on CF Benchmarks' BRTI, which is not freely available in real time.
Coinbase is one of BRTI's constituent exchanges, so its BTC-USD price is used as a proxy;
docs/s0-research.md measures how close the proxy is to the official settlement values.

Endpoints (docs.cdp.coinbase.com/exchange/reference):
  GET /products/BTC-USD/ticker   last trade, best bid/ask
  GET /products/BTC-USD/candles  [time, low, high, open, close, volume], newest first,
                                 at most 300 candles per request
Prices are Decimal (the JSON numbers are parsed as Decimal by slot.http).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from slot.http import RateLimitCounter, get_json
from slot.kalshi import parse_ts

BASE_URL = "https://api.exchange.coinbase.com"
PRODUCT = "BTC-USD"
MAX_CANDLES = 300


@dataclass(frozen=True)
class Tick:
    time: datetime  # exchange time of the last trade (UTC)
    price: Decimal  # last trade price
    bid: Decimal
    ask: Decimal


@dataclass(frozen=True)
class Candle:
    start: datetime  # UTC; the candle covers [start, start + granularity)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class CoinbaseClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 10.0,
        http: httpx.Client | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # Coinbase rejects requests without a User-Agent.
        self._http = http or httpx.Client(base_url=base_url, timeout=timeout, headers={"User-Agent": "alt-btc15"})
        self._max_retries = max_retries
        self._sleep = sleep
        self.rate_limits = RateLimitCounter()

    def __enter__(self) -> CoinbaseClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def ticker(self, product: str = PRODUCT) -> Tick:
        d = self._get(f"/products/{product}/ticker")
        return Tick(time=parse_ts(d["time"]), price=Decimal(d["price"]), bid=Decimal(d["bid"]), ask=Decimal(d["ask"]))

    def candles(
        self, start: datetime, end: datetime, granularity_s: int = 60, product: str = PRODUCT
    ) -> Iterator[Candle]:
        """Candles with start in [start, end), oldest first, fetched in 300-candle chunks.

        Coinbase omits candles for intervals with no trades; gaps are left as gaps.
        """
        step = timedelta(seconds=granularity_s * MAX_CANDLES)
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + step, end)
            params = {
                "start": chunk_start.isoformat(),
                # Coinbase's end is inclusive; stop one candle short so chunks don't overlap.
                "end": (chunk_end - timedelta(seconds=granularity_s)).isoformat(),
                "granularity": granularity_s,
            }
            rows = self._get(f"/products/{product}/candles", params)
            for row in sorted(rows, key=lambda r: r[0]):
                candle = parse_candle(row)
                if start <= candle.start < end:
                    yield candle
            chunk_start = chunk_end

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return get_json(self._http, path, params, self._max_retries, self._sleep, self.rate_limits)


def parse_candle(row: list[Any]) -> Candle:
    ts, low, high, open_, close, volume = row
    return Candle(
        start=datetime.fromtimestamp(int(ts), tz=timezone.utc),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
    )
