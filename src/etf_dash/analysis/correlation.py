"""Correlation analysis across multiple ETFs."""

from __future__ import annotations

import pandas as pd

from etf_dash.analysis.metrics import daily_returns


def correlation_matrix(
    prices_wide: pd.DataFrame,
    *,
    method: str = "pearson",
) -> pd.DataFrame:
    """Pairwise correlation of daily returns across the columns of prices_wide.

    Inner-join on dates so partial overlaps are handled gracefully.
    """
    if prices_wide.empty:
        return pd.DataFrame()
    rets = prices_wide.apply(daily_returns)
    return rets.corr(method=method)
