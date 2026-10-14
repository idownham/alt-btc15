from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from slot.risk import PER_DAY, PER_TRADE, TOTAL, KillSwitch, Order, Realized, RiskManager, chicago_day

# 2026-10-14 15:00 UTC = 10:00 Chicago (CDT) on Oct 14.
NOON = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def buy(order_id="o1", count="5", price="0.50", fee="0.09", **kw):
    return Order(order_id=order_id, strategy="A", ticker="KXBTC15M-X", side="yes", action="buy",
                 count=D(count), price=D(price), fee=D(fee), **kw)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "decisions.md").write_text("# Decisions\n")
    return tmp_path


@pytest.fixture
def clock():
    return Clock(NOON)


def manager(root, clock, **kw):
    return RiskManager(kill_switch=KillSwitch(root, environ={}), now=clock,
                       decisions_path=root / "docs" / "decisions.md", **kw)


def test_caps_are_the_owner_values():
    assert (PER_TRADE, PER_DAY, TOTAL) == (D(5), D(25), D(100))


# --- $5 per trade -------------------------------------------------------------------------

def test_order_within_5_dollars_is_allowed(root, clock):
    assert manager(root, clock).check(buy(count="9", price="0.54", fee="0.14")).allowed  # 4.86 + 0.14 = 5.00


def test_order_over_5_dollars_including_fee_is_refused(root, clock):
    d = manager(root, clock).check(buy(count="9", price="0.54", fee="0.15"))  # 5.01
    assert not d.allowed and d.reason.startswith("per_trade")


def test_float_inputs_are_refused(root, clock):
    o = Order("o1", "A", "T", "yes", "buy", count=5, price=0.5, fee=D(0))  # type: ignore[arg-type]
    d = manager(root, clock).check(o)
    assert not d.allowed and "Decimal" in d.reason


@pytest.mark.parametrize("field,value", [("price", "1"), ("price", "0"), ("count", "0"), ("fee", "-0.01")])
def test_nonsense_orders_are_refused(root, clock, field, value):
    kw = {"count": "5", "price": "0.5", "fee": "0.09", field: value}
    assert not manager(root, clock).check(buy(**kw)).allowed


def test_sell_must_close_an_open_position(root, clock):
    rm = manager(root, clock)
    sell = Order("s1", "B", "T", "yes", "sell", D(5), D("0.60"), D("0.08"), closes="o1")
    assert not rm.check(sell).allowed
    rm.record_open(buy())
    assert rm.check(sell).allowed


# --- $25 per Chicago day ------------------------------------------------------------------

def test_day_halts_after_25_dollar_net_loss_and_resumes_next_chicago_day(root, clock):
    rm = manager(root, clock)
    for i in range(5):
        rm.record_close(f"p{i}", D("-5.00"))
    assert rm.day_pnl() == D(-25)
    d = rm.check(buy())
    assert not d.allowed and d.reason.startswith("day_cap")
    # 23:59 Chicago the same day: still halted. 00:00 Chicago next day: allowed again.
    clock.t = datetime(2026, 10, 15, 4, 59, tzinfo=timezone.utc)
    assert not rm.check(buy()).allowed
    clock.t = datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc)
    assert rm.check(buy()).allowed


def test_day_cap_counts_open_risk_so_it_cannot_be_breached(root, clock):
    rm = manager(root, clock)
    for i in range(4):
        rm.record_close(f"p{i}", D("-5.00"))  # -20 realized
    rm.record_open(buy("o1", count="4", price="0.50", fee="0.07"))  # 2.07 at risk
    assert rm.check(buy("o2", count="6", price="0.50", fee="0.11")).allowed is False  # 20+2.07+3.11 = 25.18
    assert rm.check(buy("o2", count="5", price="0.50", fee="0.09")).allowed  # 20+2.07+2.59 = 24.66


def test_wins_offset_losses_within_the_day(root, clock):
    rm = manager(root, clock)
    rm.record_close("p1", D("-24.00"))
    rm.record_close("p2", D("4.00"))
    assert rm.check(buy()).allowed  # net -20, worst case -22.59


def test_day_boundary_is_chicago_not_utc():
    # 03:00 UTC on Oct 14 is still Oct 13 in Chicago (CDT, UTC-5); in January it is UTC-6.
    assert chicago_day(datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc)) == date(2026, 10, 13)
    assert chicago_day(datetime(2026, 1, 14, 5, 59, tzinfo=timezone.utc)) == date(2026, 1, 13)
    with pytest.raises(ValueError):
        chicago_day(datetime(2026, 10, 14, 3, 0))


# --- $100 total ---------------------------------------------------------------------------

def _losing_days(n, per_day="-20"):
    return [Realized(NOON - timedelta(days=d + 1), D(per_day)) for d in range(n)]


def test_total_halt_after_100_dollars_persists_across_days(root, clock):
    rm = manager(root, clock, history=_losing_days(4))  # -80 over 4 earlier days
    assert rm.check(buy()).allowed
    rm.record_close("p", D("-20"))
    assert rm.permanently_halted
    clock.t += timedelta(days=30)
    d = rm.check(buy())
    assert not d.allowed and d.reason.startswith("total_cap")


def test_total_halt_is_restored_from_history_on_restart(root, clock):
    rm = manager(root, clock, history=_losing_days(5))  # -100
    assert rm.permanently_halted and not rm.check(buy()).allowed


def test_total_cap_counts_open_risk(root, clock):
    rm = manager(root, clock, history=_losing_days(4, "-24"))  # -96
    assert not rm.check(buy(count="9", price="0.50", fee="0.16")).allowed  # 4.66 at risk -> -100.66
    assert rm.check(buy(count="7", price="0.50", fee="0.13")).allowed  # 3.63 -> -99.63


def test_total_reset_requires_dated_reset_entry_in_decisions(root, clock):
    rm = manager(root, clock, history=_losing_days(5))
    with pytest.raises(PermissionError):
        rm.reset_total_halt(date(2026, 10, 14))
    (root / "docs" / "decisions.md").write_text("# Decisions\n\n## 2026-10-14 — Reset total risk cap\nIan: ...\n")
    rm.reset_total_halt(date(2026, 10, 14))
    assert not rm.permanently_halted
    assert rm.total_pnl() == 0
    assert rm.check(buy()).allowed
    assert len(rm.history) == 5  # old losses kept for the record


def test_reset_does_not_loosen_todays_day_cap(root, clock):
    rm = manager(root, clock, history=_losing_days(4))
    rm.record_close("p", D("-25"))  # -25 today -> also -105 total
    (root / "docs" / "decisions.md").write_text("## 2026-10-14 reset\n")
    rm.reset_total_halt(date(2026, 10, 14))
    d = rm.check(buy())
    assert not d.allowed and d.reason.startswith("day_cap")


# --- kill switch --------------------------------------------------------------------------

def test_stop_file_halts_within_one_check(root, clock):
    rm = manager(root, clock)
    assert rm.check(buy()).allowed
    (root / "STOP").touch()
    d = rm.check(buy())
    assert not d.allowed and d.reason == "kill_switch: STOP file"
    (root / "STOP").unlink()
    assert rm.check(buy()).allowed


@pytest.mark.parametrize("line,killed", [
    ("KILL=1", True), ("export KILL=1", True), ('KILL="1"', True), ("KILL=1  # panic", True),
    ("KILL=0", False), ("KILL=", False), ("SKILL=1", False),
])
def test_kill_in_env_file(root, clock, line, killed):
    (root / ".env").write_text(f"KALSHI_KEY_ID=not-a-real-key\n{line}\n")
    assert (manager(root, clock).check(buy()).allowed) is not killed


def test_kill_in_process_environment(root, clock):
    rm = RiskManager(kill_switch=KillSwitch(root, environ={"KILL": "1"}), now=clock)
    assert rm.check(buy()).reason == "kill_switch: KILL=1 in environment"


def test_kill_switch_beats_everything_even_valid_sells(root, clock):
    rm = manager(root, clock)
    rm.record_open(buy())
    (root / "STOP").touch()
    sell = Order("s1", "B", "T", "yes", "sell", D(5), D("0.60"), D("0.08"), closes="o1")
    assert not rm.check(sell).allowed
