"""Reproduce the S0 evidence numbers in docs/s0-research.md (read-only, public APIs, no keys).

    .venv/bin/python scripts/s0_checks.py            # proxy check over the last 3 days
    .venv/bin/python scripts/s0_checks.py --history  # also page all historical markets (~23 requests)

Light on purpose: Kalshi requests are paced, because other alt projects share this IP.
"""

from __future__ import annotations

import argparse
import collections
import math
import statistics
from datetime import datetime, timedelta, timezone

from slot.btc import CoinbaseClient
from slot.kalshi import KalshiClient


def ohlc4(c):
    return (c.open + c.high + c.low + c.close) / 4


def proxy_check(k: KalshiClient, cb: CoinbaseClient, days: int) -> None:
    now = datetime.now(timezone.utc)
    ws = [w for w in k.windows(status="settled", min_close_ts=int((now - timedelta(days=days)).timestamp()))
          if w.expiration_value is not None and w.strike is not None]
    ws.sort(key=lambda w: w.close_time)
    candles = {c.start: c for c in cb.candles(ws[0].open_time - timedelta(minutes=1), ws[-1].close_time)}
    errs, agree, n, margins = [], 0, 0, []
    for w in ws:
        last, first = candles.get(w.close_time - timedelta(minutes=1)), candles.get(w.open_time - timedelta(minutes=1))
        if not last or not first:
            continue
        n += 1
        errs.append(ohlc4(last) - w.expiration_value)
        agree += (ohlc4(last) >= ohlc4(first)) == (w.result == "yes")
        margins.append(abs(w.expiration_value - w.strike))
    a = sorted(abs(e) for e in errs)
    print(f"windows {n} ({ws[0].close_time:%Y-%m-%d %H:%M} .. {ws[-1].close_time:%Y-%m-%d %H:%M} UTC)")
    print(f"Coinbase 1-min OHLC4 minus official settlement: mean {statistics.mean(errs):.2f}, "
          f"|err| p50 {a[n // 2]:.2f} p90 {a[int(n * .9)]:.2f} max {a[-1]:.2f}")
    print(f"proxy direction agrees with official result: {agree}/{n}")
    m = sorted(margins)
    print(f"|settlement - strike|: p10 {m[n // 10]} p50 {m[n // 2]}; share < $10: {sum(x < 10 for x in m) / n:.1%}")
    r = [math.log(b.close / a.close) for a, b in zip(list(candles.values()), list(candles.values())[1:])
         if (b.start - a.start) == timedelta(minutes=1)]
    print(f"BTC 1-min log-return sd: {statistics.pstdev(r) * 1e4:.2f} bp")


def history(k: KalshiClient) -> None:
    print("historical cutoff:", k.historical_cutoff())
    ws = list(k.historical_windows())
    ws.sort(key=lambda w: w.close_time)
    print(f"historical markets {len(ws)}: {ws[0].close_time:%Y-%m-%d} .. {ws[-1].close_time:%Y-%m-%d}")
    print("results:", dict(collections.Counter(w.result for w in ws)))
    print("price_level_structure:", dict(collections.Counter(w.price_level_structure for w in ws)))
    gaps = [(a.close_time, b.open_time) for a, b in zip(ws, ws[1:]) if a.close_time != b.open_time]
    print(f"gaps in the 15-min chain: {len(gaps)}")
    chained = [(a, b) for a, b in zip(ws, ws[1:]) if a.close_time == b.open_time and b.strike and a.expiration_value]
    same = sum(a.expiration_value == b.strike for a, b in chained)
    print(f"next window's strike == previous settlement value: {same}/{len(chained)}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--history", action="store_true")
    args = p.parse_args()
    with KalshiClient() as k, CoinbaseClient() as cb:
        k.series()
        proxy_check(k, cb, args.days)
        if args.history:
            history(k)


if __name__ == "__main__":
    main()
