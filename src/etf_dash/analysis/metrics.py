"""Performance metrics — pure functions, DataFrame in / scalar out.

All functions assume:
- `prices` is a price series indexed by date (any frequency, but daily expected).
- `returns` is a simple-return series (NOT log returns).
- Annualization factor is fixed at 252 (KRX trading days/year ≈ 246, but 252
  is the universal convention; the small bias is well-understood).
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def daily_returns(prices: pd.Series) -> pd.Series:
    """Simple daily returns from a price series."""
    return prices.pct_change().dropna()


WindowName = Literal["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "MAX"]


def total_return(prices: pd.Series, window: WindowName | None = None) -> float:
    """Total simple return over a window. None / 'MAX' uses the full series."""
    s = _slice_window(prices, window)
    if len(s) < 2:
        return float("nan")
    return float(s.iloc[-1] / s.iloc[0] - 1.0)


def annualized_return(prices: pd.Series, window: WindowName | None = None) -> float:
    s = _slice_window(prices, window)
    if len(s) < 2:
        return float("nan")
    n_days = (s.index[-1] - s.index[0]).days
    if n_days <= 0:
        return float("nan")
    years = n_days / 365.25
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1.0)


def annualized_volatility(returns: pd.Series) -> float:
    """Std dev of daily returns × sqrt(252)."""
    if len(returns) < 2:
        return float("nan")
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))


def max_drawdown(prices: pd.Series) -> float:
    """Worst peak-to-trough drawdown as a negative fraction (e.g. -0.32)."""
    if prices.empty:
        return float("nan")
    cummax = prices.cummax()
    dd = prices / cummax - 1.0
    return float(dd.min())


def sharpe_ratio(returns: pd.Series, risk_free: float = 0.0) -> float:
    """Sharpe = (mean(daily_excess) / std(daily_excess)) × sqrt(252).

    `risk_free` is annualized; converted to daily by dividing by 252.
    """
    if len(returns) < 2:
        return float("nan")
    daily_rf = risk_free / TRADING_DAYS
    excess = returns - daily_rf
    sd = excess.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS))


def tracking_error(etf_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Annualized std of (etf - benchmark) returns. Series are aligned on index."""
    aligned = pd.concat([etf_returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return float("nan")
    diff = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    return float(diff.std(ddof=1) * np.sqrt(TRADING_DAYS))


def summary(prices: pd.Series, risk_free: float = 0.0) -> dict[str, float]:
    """Bundle of common metrics for a single ETF."""
    rets = daily_returns(prices)
    return {
        "total_return_1m": total_return(prices, "1M"),
        "total_return_3m": total_return(prices, "3M"),
        "total_return_1y": total_return(prices, "1Y"),
        "total_return_3y": total_return(prices, "3Y"),
        "ann_return": annualized_return(prices),
        "ann_volatility": annualized_volatility(rets),
        "max_drawdown": max_drawdown(prices),
        "sharpe": sharpe_ratio(rets, risk_free),
    }


# --- helpers -----------------------------------------------------------------


def _slice_window(prices: pd.Series, window: WindowName | None) -> pd.Series:
    if window is None or window == "MAX":
        return prices
    if prices.empty:
        return prices
    end = prices.index[-1]
    if window == "YTD":
        start = pd.Timestamp(year=end.year, month=1, day=1)
    else:
        months = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60}
        if window not in months:
            raise ValueError(f"Unknown window: {window!r}")
        start = end - pd.DateOffset(months=months[window])
    return prices[prices.index >= start]
