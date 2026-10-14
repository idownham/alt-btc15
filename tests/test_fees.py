from decimal import Decimal as D

import pytest

from slot.fees import fee


def test_taker_fee_at_50_cents_is_1_75_cents_per_contract():
    assert fee(D(100), D("0.50"), conservative=False) == D("1.750000")
    assert fee(D(10), D("0.50")) == D("0.18")  # 0.175 rounded up to the cent


def test_taker_fee_is_small_near_the_extremes():
    # Strategy C buys near 95c: 0.07 x 0.95 x 0.05 = 0.3325c per contract.
    assert fee(D(5), D("0.95"), conservative=False) == D("0.016625")
    assert fee(D(5), D("0.95")) == D("0.02")


def test_maker_fee_is_zero_for_quadratic_series():
    assert fee(D(10), D("0.50"), maker=True) == D("0.00")
    assert fee(D(10), D("0.50"), maker=True, fee_type="quadratic_with_maker_fees", conservative=False) == D("0.043750")


def test_fractional_contracts():
    assert fee(D("9.47"), D("0.51"), conservative=False) == D("0.165659")  # 0.16565871 rounded up


def test_rejects_floats_and_bad_prices():
    with pytest.raises(TypeError):
        fee(10, 0.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        fee(D(1), D("1.5"))
    with pytest.raises(KeyError):
        fee(D(1), D("0.5"), maker=True, fee_type="mystery")
