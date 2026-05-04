"""Golden-data tests for analysis.metrics."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from etf_dash.analysis import metrics


def _series(values: list[float], start: str = "2024-01-01", freq: str = "B") -> pd.Series:
    idx = pd.date_range(start=start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, name="price")


def test_daily_returns_simple():
    s = _series([100.0, 110.0, 99.0])
    r = metrics.daily_returns(s)
    assert pytest.approx(r.iloc[0]) == 0.10
    assert pytest.approx(r.iloc[1]) == -0.10


def test_total_return_full_window():
    s = _series([100.0, 110.0, 99.0, 121.0])
    assert pytest.approx(metrics.total_return(s)) == 0.21


def test_max_drawdown_simple():
    # 100 -> 120 (peak) -> 60 (trough) -> 90
    # Trough drawdown = 60/120 - 1 = -0.5
    s = _series([100.0, 120.0, 60.0, 90.0])
    assert pytest.approx(metrics.max_drawdown(s)) == -0.5


def test_max_drawdown_monotonic_up_is_zero():
    s = _series([100.0, 105.0, 110.0])
    assert metrics.max_drawdown(s) == 0.0


def test_annualized_volatility_known_series():
    # Constant +1% / -1% alternating; daily std = 0.01, annualized = 0.01 * sqrt(252)
    rets = pd.Series([0.01, -0.01] * 50)
    vol = metrics.annualized_volatility(rets)
    expected = 0.01 * math.sqrt(metrics.TRADING_DAYS) * math.sqrt(100 / 99)  # ddof=1
    assert pytest.approx(vol, rel=0.01) == expected


def test_sharpe_zero_risk_free():
    # Constant positive 0.1% daily return → sharpe should be very high (limit: inf
    # because std=0). Use slightly noisy series to get a finite value.
    rng = np.random.default_rng(42)
    rets = pd.Series(rng.normal(loc=0.001, scale=0.005, size=252))
    sharpe = metrics.sharpe_ratio(rets)
    # Mean 0.001 / std 0.005 * sqrt(252) ≈ 3.17 (target, with sampling noise)
    assert 2.0 < sharpe < 5.0


def test_sharpe_zero_std_is_nan():
    rets = pd.Series([0.01, 0.01, 0.01])
    assert math.isnan(metrics.sharpe_ratio(rets))


def test_tracking_error_perfect_replication_is_zero():
    rets = pd.Series([0.01, 0.02, -0.01, 0.0])
    assert metrics.tracking_error(rets, rets) == 0.0


def test_window_slicing_1m():
    # 90 business days; 1M window should return the trailing ~22 days
    s = _series(list(range(1, 91)), start="2024-01-01")
    sliced = metrics._slice_window(s, "1M")
    assert 15 < len(sliced) <= 25
    assert sliced.index[-1] == s.index[-1]


def test_summary_returns_expected_keys():
    s = _series([100, 101, 102, 103, 105, 110, 108, 112] * 50)
    out = metrics.summary(s)
    expected_keys = {
        "total_return_1m", "total_return_3m", "total_return_1y", "total_return_3y",
        "ann_return", "ann_volatility", "max_drawdown", "sharpe",
    }
    assert set(out.keys()) == expected_keys
