"""Rebalancing advisor + cadence-comparison tests with synthetic data."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from etf_dash.analysis import backtest, rebalancing
from etf_dash.domain.models import Strategy, StrategyLeg


def _wide_prices(panels: dict[str, list[float]], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=len(next(iter(panels.values()))), freq="B")
    return pd.DataFrame(panels, index=idx)


def _strategy(legs: tuple[StrategyLeg, ...], rebalance: str = "quarterly") -> Strategy:
    return Strategy(
        id="t",
        name="Test",
        description="",
        legs=legs,
        rebalance=rebalance,  # type: ignore[arg-type]
    )


# --- new rebalance frequencies in the backtest engine ------------------------


def test_rebalance_dates_weekly_picks_first_trading_day_of_each_week():
    idx = pd.date_range("2024-01-01", periods=15, freq="B")  # Mon 1/1 .. 1/19
    dates = backtest._rebalance_dates(idx, "weekly")
    # First trading day of each ISO week present (Mondays here).
    mondays = {ts for ts in idx if ts.weekday() == 0}
    assert mondays.issubset(dates)
    # No Tue–Fri sneaking in beyond the week's first day.
    assert idx[0] in dates


def test_rebalance_dates_semi_annual_has_two_per_year():
    idx = pd.date_range("2023-01-01", "2024-12-31", freq="B")
    dates = backtest._rebalance_dates(idx, "semi_annual")
    # First trading day always rebalances, plus the first trading day of each
    # half-year: 2023-H1, 2023-H2, 2024-H1, 2024-H2 -> 4 distinct halves.
    months = {ts.month for ts in dates}
    # Each half opens in January (month 1) or July (month 7).
    assert months.issubset({1, 7})
    assert len(dates) == 4


def test_new_freqs_simulate_end_to_end():
    prices = _wide_prices({"A": [100.0, 110.0, 99.0, 121.0, 130.0]})
    for freq in ("weekly", "semi_annual"):
        strat = _strategy((StrategyLeg("A", 1.0, "only"),), rebalance=freq)
        result = backtest.simulate(strat, prices)
        assert len(result.equity_curve) == len(prices)


# --- next_rebalance_date -----------------------------------------------------


@pytest.mark.parametrize(
    "freq,frm,expected",
    [
        ("weekly", date(2024, 6, 5), date(2024, 6, 10)),  # Wed -> next Mon
        ("weekly", date(2024, 6, 10), date(2024, 6, 17)),  # Mon -> strictly next Mon
        ("monthly", date(2024, 6, 5), date(2024, 7, 1)),
        ("monthly", date(2024, 12, 20), date(2025, 1, 1)),
        ("quarterly", date(2024, 6, 5), date(2024, 7, 1)),
        ("quarterly", date(2024, 11, 1), date(2025, 1, 1)),
        ("semi_annual", date(2024, 3, 1), date(2024, 7, 1)),
        ("semi_annual", date(2024, 9, 1), date(2025, 1, 1)),
        ("yearly", date(2024, 6, 5), date(2025, 1, 1)),
        ("none", date(2024, 6, 5), None),
    ],
)
def test_next_rebalance_date_each_freq(freq, frm, expected):
    assert rebalancing.next_rebalance_date(freq, frm) == expected


# --- build_plan: initial build -----------------------------------------------


def test_build_plan_initial_build_splits_capital():
    strat = _strategy(
        (
            StrategyLeg("A", 0.25, "주식"),
            StrategyLeg("B", 0.25, "채권"),
            StrategyLeg("C", 0.25, "금"),
            StrategyLeg("D", 0.25, "현금성"),
        ),
        rebalance="yearly",
    )
    plan = rebalancing.build_plan(
        strat,
        current_values=None,
        total_capital=10_000_000,
        latest_prices={"A": 1000, "B": 2000, "C": 5000, "D": 1000},
        as_of=date(2024, 6, 5),
    )
    assert plan.needs_rebalance is True
    assert plan.total_value == pytest.approx(10_000_000)
    assert all(a.action == "건仓" for a in plan.actions)
    # Each leg gets 2.5M; deltas sum to the capital.
    assert sum(a.delta_value for a in plan.actions) == pytest.approx(10_000_000)
    a = next(a for a in plan.actions if a.ticker == "A")
    assert a.delta_value == pytest.approx(2_500_000)
    assert a.delta_shares == pytest.approx(2_500)  # 2.5M / 1000
    assert plan.next_rebalance_date == date(2025, 1, 1)


def test_build_plan_initial_requires_positive_capital():
    strat = _strategy((StrategyLeg("A", 1.0, ""),))
    with pytest.raises(ValueError, match="total_capital"):
        rebalancing.build_plan(strat, current_values=None)


# --- build_plan: rebalance / drift -------------------------------------------


def test_build_plan_drift_triggers_rebalance():
    strat = _strategy(
        (StrategyLeg("A", 0.5, ""), StrategyLeg("B", 0.5, "")),
        rebalance="quarterly",
    )
    # A has grown to 70%, B to 30% -> 20% drift, exceeds 5% band.
    plan = rebalancing.build_plan(
        strat,
        current_values={"A": 7_000_000, "B": 3_000_000},
        latest_prices={"A": 1000, "B": 1000},
        as_of=date(2024, 6, 5),
    )
    assert plan.needs_rebalance is True
    assert plan.max_drift == pytest.approx(0.20)
    a = next(a for a in plan.actions if a.ticker == "A")
    b = next(a for a in plan.actions if a.ticker == "B")
    assert a.delta_value == pytest.approx(-2_000_000)  # sell A down to 5M
    assert a.action == "감액"
    assert b.delta_value == pytest.approx(2_000_000)  # buy B up to 5M
    assert b.action == "증액"
    # delta cash is net-zero across legs.
    assert sum(x.delta_value for x in plan.actions) == pytest.approx(0.0)


def test_build_plan_within_band_holds():
    strat = _strategy((StrategyLeg("A", 0.5, ""), StrategyLeg("B", 0.5, "")))
    # 51/49 split -> 1% drift, within 5% band.
    plan = rebalancing.build_plan(
        strat,
        current_values={"A": 5_100_000, "B": 4_900_000},
    )
    assert plan.needs_rebalance is False
    assert all(a.action == "유지" for a in plan.actions)


def test_weight_band_triggers_when_leg_leaves_band():
    """Browne-style 15/35 band: rebalance only when a leg leaves [15%, 35%]."""
    strat = _strategy(
        (
            StrategyLeg("A", 0.25, ""),
            StrategyLeg("B", 0.25, ""),
            StrategyLeg("C", 0.25, ""),
            StrategyLeg("D", 0.25, ""),
        ),
        rebalance="yearly",
    )
    # A at 36% (>35%), B at 14% (<15%) -> outside band -> rebalance.
    plan = rebalancing.build_plan(
        strat,
        current_values={"A": 3_600_000, "B": 1_400_000, "C": 2_500_000, "D": 2_500_000},
        weight_band=(0.15, 0.35),
    )
    assert plan.needs_rebalance is True
    assert "밴드" in plan.note


def test_weight_band_holds_despite_large_drift():
    """Band rule is more lenient than drift: 34/16/25/25 has 9% drift but stays
    within [15%, 35%], so no rebalance — even though drift_band(5%) would fire."""
    strat = _strategy(
        (
            StrategyLeg("A", 0.25, ""),
            StrategyLeg("B", 0.25, ""),
            StrategyLeg("C", 0.25, ""),
            StrategyLeg("D", 0.25, ""),
        )
    )
    holdings = {"A": 3_400_000, "B": 1_600_000, "C": 2_500_000, "D": 2_500_000}
    band_plan = rebalancing.build_plan(strat, current_values=holdings, weight_band=(0.15, 0.35))
    drift_plan = rebalancing.build_plan(strat, current_values=holdings)  # default drift_band
    assert band_plan.needs_rebalance is False
    assert band_plan.max_drift == pytest.approx(0.09)
    # Same holdings under the default drift rule would trigger.
    assert drift_plan.needs_rebalance is True


def test_build_plan_rejects_zero_holdings():
    strat = _strategy((StrategyLeg("A", 1.0, ""),))
    with pytest.raises(ValueError, match="current_values"):
        rebalancing.build_plan(strat, current_values={"A": 0.0})


# --- cadence comparison ------------------------------------------------------


def test_compare_frequencies_has_row_per_freq():
    rng = np.random.default_rng(0)
    prices = _wide_prices(
        {
            "A": (1 + rng.normal(0, 0.01, 400)).cumprod() * 100,
            "B": (1 + rng.normal(0, 0.008, 400)).cumprod() * 100,
        }
    )
    strat = _strategy((StrategyLeg("A", 0.6, ""), StrategyLeg("B", 0.4, "")))
    comp = rebalancing.compare_rebalance_frequencies(strat, prices)
    assert list(comp.index) == list(rebalancing.DEFAULT_FREQS)
    assert {"ann_return", "sharpe", "max_drawdown"}.issubset(comp.columns)
    assert not comp["sharpe"].isna().all()
