"""Kalshi trading fees for KXBTC15M (see docs/s0-research.md section 2).

GET /series/KXBTC15M (2026-10-13): fee_type "quadratic", fee_multiplier 1, no fee changes on
record (GET /series/fee_changes?series_ticker=KXBTC15M&show_historical=true -> empty).

  taker fee = 0.07 x multiplier x contracts x P x (1 - P)
  maker fee = 0 for fee_type "quadratic" (series with maker fees use the separate type
              "quadratic_with_maker_fees", 0.0175 x C x P x (1 - P)).
  Settlement (holding to expiry) has no fee.

Rounding: Kalshi rounds each fill's fee up to $0.000001 and rebates the overpayment past a
whole cent through a fee accumulator (docs.kalshi.com/getting_started/fee_rounding). The
conservative variant used by default here rounds each order's fee up to the whole cent.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

TAKER_RATE = Decimal("0.07")
MAKER_RATE = {"quadratic": Decimal("0"), "quadratic_with_maker_fees": Decimal("0.0175")}
CENT = Decimal("0.01")
MICRO = Decimal("0.000001")


def fee(
    count: Decimal,
    price: Decimal,
    *,
    maker: bool = False,
    fee_type: str = "quadratic",
    multiplier: Decimal = Decimal(1),
    conservative: bool = True,
) -> Decimal:
    """Fee in dollars for `count` contracts at `price` (dollars, 0..1) on one order."""
    for name, value in (("count", count), ("price", price), ("multiplier", multiplier)):
        if not isinstance(value, (Decimal, int)) or isinstance(value, bool):
            raise TypeError(f"{name} must be Decimal or int, not {type(value).__name__}")
    if not Decimal(0) <= price <= Decimal(1):
        raise ValueError(f"price must be in [0, 1], got {price}")
    rate = MAKER_RATE[fee_type] if maker else TAKER_RATE
    raw = rate * Decimal(multiplier) * Decimal(count) * price * (1 - price)
    return raw.quantize(CENT if conservative else MICRO, rounding=ROUND_CEILING)
