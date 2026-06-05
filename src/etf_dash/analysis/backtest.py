"""Static-weight portfolio backtest with periodic rebalancing.

Approach: for each leg, compute a normalized price series (price / first
price). Hold the static target weights, redistributing back to target at each
rebalance date. Output equity curve + per-asset weight history + summary
metrics.

Why we wrote this instead of using vectorbt/backtrader:
- Strategies are static target weights (4-6 ETFs) with periodic rebalances —
  the simplest possible backtest. The full implementation is well under 100
  lines, with no learning curve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from etf_dash.analysis import metrics
from etf_dash.domain.models import RebalanceFreq, Strategy


@dataclass
class BacktestResult:
    strategy_id: str
    equity_curve: pd.Series  # indexed by date, normalized to initial=1.0
    weights_over_time: pd.DataFrame  # columns = tickers, rows = dates
    summary: dict[str, float]
    start: date
    end: date
    initial: float
    benchmark_curve: pd.Series | None = None


def simulate(
    strategy: Strategy,
    prices_wide: pd.DataFrame,
    *,
    start: date | None = None,
    end: date | None = None,
    initial: float = 1_000_000.0,
    benchmark_prices: pd.Series | None = None,
) -> BacktestResult:
    """Simulate a strategy.

    Args:
        strategy: validated Strategy object.
        prices_wide: DataFrame indexed by date with one column per leg ticker.
            Must contain at least every leg's ticker. Missing values are
            forward-filled per ticker (handles a leg listing on a non-trading
            day for another).
        start, end: optional clamp; default = full range of prices_wide.
        initial: starting capital (units arbitrary; reported equity uses same).
        benchmark_prices: optional Series of a benchmark price for comparison.
    """
    strategy.validate()
    missing = [leg.ticker for leg in strategy.legs if leg.ticker not in prices_wide.columns]
    if missing:
        raise ValueError(f"prices_wide is missing tickers: {missing}")

    prices = prices_wide[[leg.ticker for leg in strategy.legs]].copy()
    prices = prices.ffill().dropna(how="any")
    if start is not None:
        prices = prices[prices.index >= pd.Timestamp(start)]
    if end is not None:
        prices = prices[prices.index <= pd.Timestamp(end)]
    if len(prices) < 2:
        raise ValueError(
            "Not enough overlapping price history for legs in given window. "
            "All legs must have at least 2 common trading days."
        )

    target = pd.Series({leg.ticker: leg.weight for leg in strategy.legs})

    # Number of "shares" per asset; recomputed on each rebalance day.
    shares = pd.Series(0.0, index=target.index)
    rebalance_dates = _rebalance_dates(prices.index, strategy.rebalance)

    equity = pd.Series(0.0, index=prices.index)
    weights_history = pd.DataFrame(index=prices.index, columns=target.index, dtype=float)

    cash_value = initial
    for current in prices.index:
        if current in rebalance_dates:
            # Reset positions to target weights using current portfolio value.
            current_value = (shares * prices.loc[current]).sum() or cash_value
            shares = (target * current_value) / prices.loc[current]
            cash_value = 0.0
        port_value = (shares * prices.loc[current]).sum()
        equity[current] = port_value
        weights_history.loc[current] = (shares * prices.loc[current]) / port_value

    equity_curve = equity / initial  # normalize to 1.0 at start

    rets = metrics.daily_returns(equity)
    summary = {
        "ann_return": metrics.annualized_return(equity),
        "ann_volatility": metrics.annualized_volatility(rets),
        "sharpe": metrics.sharpe_ratio(rets),
        "max_drawdown": metrics.max_drawdown(equity),
        "total_return": metrics.total_return(equity),
    }

    bench_curve: pd.Series | None = None
    if benchmark_prices is not None:
        bp = benchmark_prices.reindex(prices.index).ffill().dropna()
        if len(bp) >= 2:
            bench_curve = bp / bp.iloc[0]

    return BacktestResult(
        strategy_id=strategy.id,
        equity_curve=equity_curve,
        weights_over_time=weights_history,
        summary=summary,
        start=prices.index[0].date(),
        end=prices.index[-1].date(),
        initial=initial,
        benchmark_curve=bench_curve,
    )


def _rebalance_dates(index: pd.DatetimeIndex, freq: RebalanceFreq) -> set[pd.Timestamp]:
    """Return the set of timestamps in `index` that are rebalance days.

    The first day always rebalances (entry). For periodic frequencies, we use
    the first trading day of each period after the start.
    """
    dates: set[pd.Timestamp] = {index[0]}
    if freq == "none" or len(index) < 2:
        return dates

    if freq == "weekly":
        period_key = index.to_period("W")
    elif freq == "monthly":
        period_key = index.to_period("M")
    elif freq == "quarterly":
        period_key = index.to_period("Q")
    elif freq == "semi_annual":
        # pandas has no 6-month period; key each date to its calendar half.
        period_key = [f"{ts.year}-H{(ts.month - 1) // 6}" for ts in index]
    elif freq == "yearly":
        period_key = index.to_period("Y")
    else:
        raise ValueError(f"Unknown rebalance frequency: {freq!r}")

    df = pd.DataFrame({"period": period_key}, index=index)
    first_of_each = df.groupby("period").apply(lambda g: g.index[0])
    for ts in first_of_each.values:
        dates.add(pd.Timestamp(ts))
    return dates


def yearly_returns(equity_curve: pd.Series) -> pd.Series:
    """Calendar-year returns from an equity curve."""
    if equity_curve.empty:
        return pd.Series(dtype=float)
    eoy = equity_curve.resample("YE").last()
    return eoy.pct_change().dropna()


def drawdown_curve(equity_curve: pd.Series) -> pd.Series:
    """Drawdown series (negative or zero)."""
    return equity_curve / equity_curve.cummax() - 1.0
