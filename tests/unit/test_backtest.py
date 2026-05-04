"""Backtest engine sanity checks with synthetic price data."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from etf_dash.analysis import backtest
from etf_dash.domain.models import Strategy, StrategyLeg


def _wide_prices(panels: dict[str, list[float]], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=len(next(iter(panels.values()))), freq="B")
    return pd.DataFrame(panels, index=idx)


def test_simulate_single_asset_matches_passive_buy_and_hold():
    """A 100% allocation must produce equity curve identical (up to scaling) to
    the underlying price series."""
    prices = _wide_prices({"A": [100.0, 110.0, 99.0, 121.0]})
    strat = Strategy(
        id="solo",
        name="Solo A",
        description="100% A",
        legs=(StrategyLeg("A", 1.0, "only"),),
        rebalance="none",
    )
    result = backtest.simulate(strat, prices, initial=1_000_000)
    expected_ratios = prices["A"] / prices["A"].iloc[0]
    np.testing.assert_array_almost_equal(
        result.equity_curve.values, expected_ratios.values
    )


def test_simulate_50_50_no_rebalance_drifts():
    """50/50, no rebalance, with one asset doubling and other halving — final
    equity should equal mean of the multipliers (0.5*2 + 0.5*0.5 = 1.25)."""
    prices = _wide_prices({"A": [100.0, 200.0], "B": [100.0, 50.0]})
    strat = Strategy(
        id="fifty",
        name="50/50",
        description="",
        legs=(StrategyLeg("A", 0.5, ""), StrategyLeg("B", 0.5, "")),
        rebalance="none",
    )
    result = backtest.simulate(strat, prices, initial=1_000_000)
    assert pytest.approx(result.equity_curve.iloc[-1], rel=1e-9) == 1.25


def test_weights_sum_to_one_at_every_step():
    """Internal invariant: weights row should sum to 1 (within floating tol)."""
    rng = np.random.default_rng(0)
    prices = _wide_prices(
        {
            "A": (1 + rng.normal(0, 0.01, 60)).cumprod() * 100,
            "B": (1 + rng.normal(0, 0.01, 60)).cumprod() * 100,
            "C": (1 + rng.normal(0, 0.005, 60)).cumprod() * 100,
        }
    )
    strat = Strategy(
        id="three",
        name="Three",
        description="",
        legs=(
            StrategyLeg("A", 0.4, ""),
            StrategyLeg("B", 0.4, ""),
            StrategyLeg("C", 0.2, ""),
        ),
        rebalance="monthly",
    )
    result = backtest.simulate(strat, prices)
    sums = result.weights_over_time.sum(axis=1).dropna()
    assert all(math.isclose(s, 1.0, abs_tol=1e-9) for s in sums)


def test_simulate_raises_on_missing_ticker():
    prices = _wide_prices({"A": [100.0, 101.0]})
    strat = Strategy(
        id="bad",
        name="bad",
        description="",
        legs=(StrategyLeg("A", 0.5, ""), StrategyLeg("Z", 0.5, "")),
        rebalance="none",
    )
    with pytest.raises(ValueError, match="missing tickers"):
        backtest.simulate(strat, prices)


def test_strategy_validate_rejects_bad_weights():
    s = Strategy(
        id="bad",
        name="",
        description="",
        legs=(StrategyLeg("A", 0.5, ""), StrategyLeg("B", 0.4, "")),
    )
    with pytest.raises(ValueError, match="sum to"):
        s.validate()


def test_yearly_returns_basic():
    idx = pd.date_range("2022-01-01", "2024-12-31", freq="B")
    eq = pd.Series(np.linspace(1.0, 1.5, len(idx)), index=idx)
    yr = backtest.yearly_returns(eq)
    assert len(yr) >= 2
    assert all(yr > 0)
