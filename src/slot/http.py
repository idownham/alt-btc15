"""GET JSON from a public API, backing off on rate limits.

Copied from alt-scalp `src/altscalp/http.py` @ db83d7d (itself from alt-arb @ 594878f) and
adapted: JSON numbers with a fraction are parsed as `Decimal`, never float. Kalshi sends
`floor_strike` as a bare JSON number (e.g. 67345.399999), and Coinbase sends candle prices
as numbers, so a float parse would put float error into money values (CLAUDE.md rule 8).

Kalshi's 429s carry no Retry-After header (docs.kalshi.com/getting_started/rate_limits), so
this always uses exponential backoff, and counts 429s so callers can log them.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx

log = logging.getLogger(__name__)


class RateLimitCounter:
    """Running count of 429 responses, for logging how close we run to the limit."""

    def __init__(self) -> None:
        self.count = 0


def get_json(
    http: httpx.Client,
    path: str,
    params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    max_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    rate_limits: RateLimitCounter | None = None,
) -> Any:
    """GET `path` and return the JSON body, with non-integer numbers as Decimal.

    On 429 Too Many Requests, waits 1s, 2s, 4s, ... and retries up to `max_retries`
    times. Any other error status raises immediately.
    """
    for attempt in range(max_retries + 1):
        response = http.get(path, params=params)
        if response.status_code != 429:
            break
        if rate_limits is not None:
            rate_limits.count += 1
        if attempt == max_retries:
            break
        wait = float(2**attempt)
        log.warning("429 rate limited on %s; retrying in %.0fs", path, wait)
        sleep(wait)
    response.raise_for_status()
    return json.loads(response.text, parse_float=Decimal)
