"""Hard risk caps and kill switch (CLAUDE.md rules 2-3). Every order, paper or live, must pass
`RiskManager.check()` first; no other module may decide whether an order is allowed.

Caps are constants, not settings: changing them needs a dated entry in docs/decisions.md.

  PER_TRADE  $5    max loss of one order: count x price + fee (a bought contract can go to $0)
  PER_DAY    $25   net loss per America/Chicago calendar day -> halt until the next day
  TOTAL      $100  net loss since start -> halt permanently until the owner records a reset

Caps are enforced on the worst case, not just on realized P&L: an order is refused if the
loss already taken, plus everything still at risk in open positions, plus this order's max
loss could breach the day or total cap. So no sequence of fills can break a cap.

Kill switch: a file named STOP in the repo root, or KILL=1 in .env or the environment, refuses
every order. It is checked on every call, so it takes effect within one loop iteration.

State (realized P&L history, permanent-halt flag, total-reset time) is passed in by the caller; S2 will persist
it in SQLite so a restart cannot reset the caps.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

PER_TRADE = Decimal("5")
PER_DAY = Decimal("25")
TOTAL = Decimal("100")
CHICAGO = ZoneInfo("America/Chicago")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def chicago_day(ts: datetime) -> date:
    if ts.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware (UTC)")
    return ts.astimezone(CHICAGO).date()


@dataclass(frozen=True)
class Order:
    """An order a strategy wants to place. Money values are Decimal dollars."""

    order_id: str
    strategy: str
    ticker: str
    side: str  # 'yes' or 'no'
    action: str  # 'buy' opens a position, 'sell' closes one
    count: Decimal
    price: Decimal  # limit price in dollars, 0 < price < 1
    fee: Decimal  # expected fee for the order (slot.fees.fee, conservative)
    closes: str | None = None  # for 'sell': order_id of the position being closed

    @property
    def max_loss(self) -> Decimal:
        """Most this order can lose: a buy can go to zero; a closing sell can only cost its fee
        (the position's own loss is already counted as open risk)."""
        if self.action == "buy":
            return self.count * self.price + self.fee
        return self.fee


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str  # 'ok' or the cap / check that refused it (logged to risk_events)


@dataclass(frozen=True)
class Realized:
    ts: datetime  # UTC time the P&L was realized (close fill or settlement)
    pnl: Decimal  # net of fees; negative is a loss


class KillSwitch:
    def __init__(self, root: Path = REPO_ROOT, environ: Mapping[str, str] = os.environ) -> None:
        self.root = root
        self.environ = environ

    def reason(self) -> str | None:
        if (self.root / "STOP").exists():
            return "kill_switch: STOP file"
        if self.environ.get("KILL", "").strip() == "1":
            return "kill_switch: KILL=1 in environment"
        if _env_file_kill(self.root / ".env"):
            return "kill_switch: KILL=1 in .env"
        return None


def _env_file_kill(path: Path) -> bool:
    """True if .env sets KILL=1. Reads only the KILL line; never logs the file's other values."""
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return False
    for line in lines:
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key.strip() == "KILL":
            return value.split("#")[0].strip().strip("'\"") == "1"
    return False


class RiskManager:
    def __init__(
        self,
        history: Iterable[Realized] = (),
        permanently_halted: bool = False,
        total_reset_at: datetime | None = None,
        kill_switch: KillSwitch | None = None,
        now: Callable[[], datetime] = _utcnow,
        decisions_path: Path = REPO_ROOT / "docs" / "decisions.md",
    ) -> None:
        self.history: list[Realized] = list(history)
        self.open_risk: dict[str, Decimal] = {}
        self.kill_switch = kill_switch or KillSwitch()
        self.now = now
        self.decisions_path = decisions_path
        self.total_reset_at = total_reset_at  # total cap counts only P&L realized after this
        self.permanently_halted = permanently_halted or self.total_pnl() <= -TOTAL

    # --- P&L views -------------------------------------------------------------------------
    def total_pnl(self) -> Decimal:
        since = self.total_reset_at
        return sum((r.pnl for r in self.history if since is None or r.ts > since), Decimal(0))

    def day_pnl(self, day: date | None = None) -> Decimal:
        day = day or chicago_day(self.now())
        return sum((r.pnl for r in self.history if chicago_day(r.ts) == day), Decimal(0))

    def open_exposure(self) -> Decimal:
        return sum(self.open_risk.values(), Decimal(0))

    def halt_reason(self) -> str | None:
        """Why all orders are refused right now, or None."""
        if reason := self.kill_switch.reason():
            return reason
        if self.permanently_halted:
            return "total_cap: halted until owner reset in decisions.md"
        if self.day_pnl() <= -PER_DAY:
            return "day_cap: halted until next Chicago day"
        return None

    # --- the gate --------------------------------------------------------------------------
    def check(self, order: Order) -> Decision:
        if reason := self.halt_reason():
            return Decision(False, reason)
        if reason := _invalid(order):
            return Decision(False, f"invalid: {reason}")
        if order.action == "sell" and order.closes not in self.open_risk:
            return Decision(False, "invalid: sell must close an open position")
        risk = order.max_loss
        if order.action == "buy" and risk > PER_TRADE:
            return Decision(False, f"per_trade: max loss {risk} > {PER_TRADE}")
        at_risk = self.open_exposure() + risk
        if self.day_pnl() - at_risk < -PER_DAY:
            return Decision(False, f"day_cap: worst case {self.day_pnl() - at_risk} < -{PER_DAY}")
        if self.total_pnl() - at_risk < -TOTAL:
            return Decision(False, f"total_cap: worst case {self.total_pnl() - at_risk} < -{TOTAL}")
        return Decision(True, "ok")

    # --- bookkeeping (call after the fill / close actually happens) ------------------------
    def record_open(self, order: Order) -> None:
        if order.action != "buy":
            raise ValueError("record_open is for buys")
        self.open_risk[order.order_id] = order.max_loss

    def record_close(self, position_id: str, pnl: Decimal, ts: datetime | None = None) -> None:
        """A position closed (sold or settled) with net P&L `pnl` (after all fees)."""
        if not isinstance(pnl, Decimal):
            raise TypeError("pnl must be Decimal")
        self.open_risk.pop(position_id, None)
        self.history.append(Realized(ts or self.now(), pnl))
        if self.total_pnl() <= -TOTAL:
            self.permanently_halted = True

    def reset_total_halt(self, decision_date: date) -> None:
        """Clear the permanent halt. Requires a dated owner entry in docs/decisions.md whose
        heading contains that date and the word 'reset' (e.g. '## 2026-11-20 — Reset risk cap')."""
        text = self.decisions_path.read_text() if self.decisions_path.exists() else ""
        heading = re.compile(rf"^##\s+{decision_date.isoformat()}\b.*\breset\b", re.IGNORECASE | re.MULTILINE)
        if not heading.search(text):
            raise PermissionError(f"no '## {decision_date.isoformat()} ... reset' entry in {self.decisions_path}")
        self.permanently_halted = False
        # Losses before the reset stay in history (and in that day's P&L); the total restarts here.
        self.total_reset_at = self.now()


def _invalid(order: Order) -> str | None:
    for name in ("count", "price", "fee"):
        if not isinstance(getattr(order, name), Decimal):
            return f"{name} must be Decimal"
    if order.side not in ("yes", "no"):
        return f"side {order.side!r}"
    if order.action not in ("buy", "sell"):
        return f"action {order.action!r}"
    if order.count <= 0:
        return "count must be positive"
    if not Decimal(0) < order.price < Decimal(1):
        return "price must be between 0 and 1"
    if order.fee < 0:
        return "fee must be >= 0"
    return None
