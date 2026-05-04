"""ETF fund-flow analysis from accumulated daily snapshots.

We don't have an authoritative `shares_outstanding` time series from FDR,
so 'flow' is approximated as the day-over-day change in MarCap (시가총액)
that ISN'T explained by price change. That isolates net creations/redemptions
from market movement.
"""

from __future__ import annotations

import pandas as pd


def estimated_flows(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Estimate net fund flows per ticker from successive snapshots.

    Args:
        snapshots: rows from etf_snapshot, columns include
            (ticker, snap_date, mar_cap, change_rate).
            change_rate is daily price return in % (FDR convention).

    Returns:
        DataFrame indexed by (ticker, snap_date) with column `flow_estimate`
        in the same units as mar_cap (억원). Positive = net inflow.
    """
    if snapshots.empty:
        return pd.DataFrame()

    df = snapshots.sort_values(["ticker", "snap_date"]).copy()
    df["mar_cap_prev"] = df.groupby("ticker")["mar_cap"].shift(1)
    df["change_rate_frac"] = df["change_rate"].fillna(0) / 100.0
    # Expected MarCap if only price moved:
    df["mar_cap_expected"] = df["mar_cap_prev"] * (1.0 + df["change_rate_frac"])
    df["flow_estimate"] = df["mar_cap"] - df["mar_cap_expected"]
    return df.set_index(["ticker", "snap_date"])[["flow_estimate"]]


def top_flows(
    snapshots: pd.DataFrame,
    *,
    n: int = 10,
    direction: str = "in",
) -> pd.DataFrame:
    """Top N tickers by net flow over the available snapshot history."""
    flows = estimated_flows(snapshots)
    if flows.empty:
        return pd.DataFrame(columns=["ticker", "total_flow"])
    summed = flows.groupby(level="ticker")["flow_estimate"].sum().rename("total_flow")
    if direction == "in":
        return summed.nlargest(n).reset_index()
    return summed.nsmallest(n).reset_index()
