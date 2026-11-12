"""Frozen dataclasses for typed handoff between layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class ETFMeta:
    ticker: str
    name: str
    category: int | None
    asset_class: str
    issuer: str
    region: str = "KR"
    inception_date: date | None = None
    expense_ratio: float | None = None
    benchmark: str | None = None
    is_active: bool = True
    updated_at: datetime | None = None


RebalanceFreq = Literal[
    "none", "weekly", "monthly", "quarterly", "semi_annual", "yearly"
]


@dataclass(frozen=True, slots=True)
class StrategyLeg:
    ticker: str
    weight: float
    role: str = ""


@dataclass(frozen=True, slots=True)
class Strategy:
    id: str
    name: str
    description: str
    legs: tuple[StrategyLeg, ...]
    rebalance: RebalanceFreq = "quarterly"
    benchmark_ticker: str | None = None

    def validate(self) -> None:
        total = sum(leg.weight for leg in self.legs)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Strategy {self.id!r} weights sum to {total:.6f}, expected 1.0"
            )
        seen: set[str] = set()
        for leg in self.legs:
            if leg.ticker in seen:
                raise ValueError(f"Strategy {self.id!r} has duplicate ticker {leg.ticker}")
            seen.add(leg.ticker)
            if leg.weight <= 0:
                raise ValueError(f"Strategy {self.id!r} leg {leg.ticker} weight must be > 0")


@dataclass(frozen=True, slots=True)
class RebalanceAction:
    """A single buy/sell instruction to move one leg toward its target weight."""

    ticker: str
    role: str
    target_weight: float
    current_weight: float
    current_value: float  # KRW
    target_value: float  # KRW
    delta_value: float  # target - current; >0 매수(건仓/증액), <0 매도(감액)
    current_price: float | None = None
    delta_shares: float | None = None  # delta_value / current_price (양수 매수, 음수 매도)
    action: str = ""  # "건仓" / "증액" / "감액" / "유지"


@dataclass(frozen=True, slots=True)
class RebalancePlan:
    """The full set of actions to rebalance a strategy as of a given date."""

    strategy_id: str
    as_of: date
    freq: RebalanceFreq
    total_value: float
    actions: tuple[RebalanceAction, ...]
    max_drift: float
    needs_rebalance: bool
    next_rebalance_date: date | None
    note: str
