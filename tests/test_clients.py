from datetime import datetime, timezone
from decimal import Decimal as D

import httpx
import pytest

from slot import btc, kalshi
from slot.btc import CoinbaseClient
from slot.kalshi import KalshiClient, parse_book, parse_window

# Trimmed from GET /markets?series_ticker=KXBTC15M&status=open (2026-10-13 22:15 CDT).
MARKET_TEXT = """{"markets": [{"ticker": "KXBTC15M-26OCT132330-30", "status": "active",
 "open_time": "2026-10-14T03:15:00Z", "close_time": "2026-10-14T03:30:00Z",
 "floor_strike": 83628.01, "expiration_value": "", "result": "",
 "price_level_structure": "tapered_deci_cent", "custom_strike": {"round_digits": "2"}}], "cursor": ""}"""

# Settled market whose strike arrived with float noise (historical, Feb 2026).
NOISY = {"ticker": "KXBTC15M-26FEB051115-15", "status": "finalized", "open_time": "2026-02-05T16:00:00Z",
         "close_time": "2026-02-05T16:15:00Z", "floor_strike": D("67345.399999"),
         "expiration_value": "67190.18", "result": "no", "price_level_structure": "linear_cent"}

# Real orderbook_fp levels (trimmed), worst-to-best as the API sent them.
BOOK_FP = {"no_dollars": [["0.0010", "5000.00"], ["0.2000", "30.00"], ["0.2100", "12.50"]],
           "yes_dollars": [["0.0010", "8000.00"], ["0.7700", "40.00"], ["0.7800", "20.00"]]}


def _kalshi(handler):
    return KalshiClient(http=httpx.Client(base_url=kalshi.BASE_URL, transport=httpx.MockTransport(handler)),
                        sleep=lambda s: None)


def test_current_window_parses_strike_as_exact_decimal():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, text=MARKET_TEXT)

    w = _kalshi(handler).current_window()
    assert seen["series_ticker"] == "KXBTC15M" and seen["status"] == "open"
    assert w.strike == D("83628.01") and isinstance(w.strike, D)
    assert w.close_time == datetime(2026, 10, 14, 3, 30, tzinfo=timezone.utc)
    assert w.expiration_value is None and w.result == ""


def test_float_noise_in_strike_is_rounded_to_cents():
    assert parse_window(NOISY).strike == D("67345.40")


def test_book_asks_and_walk():
    book = parse_book("T", BOOK_FP)
    assert book.best_yes_bid_e4 == 7800 and book.best_yes_ask_e4 == 7900
    assert book.best_no_ask_e4 == 2200
    assert [lvl.price_e4 for lvl in book.asks("yes")] == [7900, 8000, 9990]
    # 20 YES: 12.50 @ 0.79 + 7.50 @ 0.80 = 9.875 + 6.00 = $15.875
    assert book.walk_buy("yes", 2000) == (2000, 1250 * 7900 + 750 * 8000)
    assert book.walk_buy("yes", 2000)[1] == 15_875_000  # e6 dollars


def test_walk_reports_partial_fill_on_thin_book():
    book = parse_book("T", {"no_dollars": [["0.2100", "1.00"]], "yes_dollars": []})
    assert book.walk_buy("yes", 500) == (100, 100 * 7900)
    assert book.walk_buy("no", 500) is None


def test_pagination_follows_cursor_until_empty():
    pages = iter([{"markets": [NOISY_JSON], "cursor": "c2"}, {"markets": [], "cursor": "c3"}])

    def handler(request):
        import json
        return httpx.Response(200, text=json.dumps(next(pages)))

    assert len(list(_kalshi(handler).historical_windows())) == 1


NOISY_JSON = {**NOISY, "floor_strike": 67345.399999}


# Coinbase GET /products/BTC-USD/candles rows: [time, low, high, open, close, volume], newest first.
CANDLES_TEXT = "[[1791947640, 83601.1, 83650.25, 83610.0, 83640.5, 12.5], [1791947580, 83590.0, 83615.0, 83600.0, 83610.0, 9.1]]"


def test_coinbase_candles_are_decimal_oldest_first_and_bounded():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, text=CANDLES_TEXT)

    cb = CoinbaseClient(http=httpx.Client(base_url=btc.BASE_URL, transport=httpx.MockTransport(handler)))
    start = datetime.fromtimestamp(1791947580, tz=timezone.utc)
    end = datetime.fromtimestamp(1791947700, tz=timezone.utc)
    cs = list(cb.candles(start, end))
    assert [c.start for c in cs] == [start, datetime.fromtimestamp(1791947640, tz=timezone.utc)]
    assert cs[1].close == D("83640.5") and isinstance(cs[1].close, D)
    assert seen[0]["granularity"] == "60"


def test_coinbase_ticker():
    body = '{"price": "83689.33", "bid": "83689.32", "ask": "83689.33", "time": "2026-10-14T03:22:32.616524Z"}'
    cb = CoinbaseClient(http=httpx.Client(base_url=btc.BASE_URL,
                                          transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))))
    t = cb.ticker()
    assert t.price == D("83689.33") and t.time.tzinfo is not None


@pytest.mark.live
def test_live_read_only_smoke():
    with KalshiClient() as k, CoinbaseClient() as cb:
        s = k.series()
        assert (s["fee_type"], s["fee_multiplier"]) == ("quadratic", 1)
        w = k.current_window()
        assert w is not None and w.strike is not None
        assert k.orderbook(w.ticker) is not None
        assert cb.ticker().price > 0
