"""Gather the data behind the public static report.

Compute functions are pure (take DataFrames, return dataclasses) so they can be
unit-tested with synthetic data and no DB. `gather_report` is the only function
that touches the repository, wiring the cache into those pure builders.

This is a sink layer alongside `ui/` — it consumes `analysis` + `repository`
and never the other way round.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from etf_dash.analysis import backtest, rebalancing
from etf_dash.analysis.correlation import correlation_matrix
from etf_dash.analysis.flows import top_flows
from etf_dash.domain.models import RebalancePlan, Strategy

PP_STRATEGY_ID = "permanent_portfolio_kr"
PP_NOTIONAL = 10_000_000.0  # display capital for the rebalancing snapshot
PP_WEIGHT_BAND = (0.15, 0.35)  # Harry Browne 35/15 rule


@dataclass
class StrategyReport:
    strategy: Strategy
    summary: dict[str, float] = field(default_factory=dict)
    equity_curve: pd.Series | None = None
    benchmark_curve: pd.Series | None = None
    start: date | None = None
    end: date | None = None
    error: str | None = None


@dataclass
class PPRebalanceReport:
    plan: RebalancePlan
    current_weights: dict[str, float]
    last_rebalance: date | None


@dataclass
class MarketReport:
    asset_class_counts: pd.Series = field(default_factory=lambda: pd.Series(dtype=int))
    top_gainers: pd.DataFrame = field(default_factory=pd.DataFrame)
    top_losers: pd.DataFrame = field(default_factory=pd.DataFrame)
    inflows: pd.DataFrame = field(default_factory=pd.DataFrame)
    outflows: pd.DataFrame = field(default_factory=pd.DataFrame)
    corr: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class ReportBundle:
    generated_at: datetime
    data_as_of: date | None
    strategies: list[StrategyReport]
    market: MarketReport
    pp_rebalance: PPRebalanceReport | None = None


# --- pure compute builders ---------------------------------------------------


def compute_strategy_report(
    strategy: Strategy,
    prices_wide: pd.DataFrame,
    benchmark_prices: pd.Series | None = None,
) -> StrategyReport:
    """Run a full-range backtest; capture failures as a message, never raise."""
    try:
        result = backtest.simulate(strategy, prices_wide, benchmark_prices=benchmark_prices)
    except ValueError as exc:
        return StrategyReport(strategy=strategy, error=str(exc))
    return StrategyReport(
        strategy=strategy,
        summary=result.summary,
        equity_curve=result.equity_curve,
        benchmark_curve=result.benchmark_curve,
        start=result.start,
        end=result.end,
    )


def compute_pp_rebalance(
    strategy: Strategy,
    prices_wide: pd.DataFrame,
    *,
    as_of: date | None = None,
    notional: float = PP_NOTIONAL,
) -> PPRebalanceReport | None:
    """Snapshot of where the Permanent Portfolio sits *today* vs target.

    We simulate the strategy (which rebalances on its own cadence), then read
    the latest realized weights — i.e. the drift since the last scheduled
    rebalance — and feed those into the advisor under the 35/15 band rule.
    """
    try:
        result = backtest.simulate(strategy, prices_wide, end=as_of)
    except ValueError:
        return None
    weights_hist = result.weights_over_time.dropna(how="any")
    if weights_hist.empty:
        return None

    current_weights = {str(k): float(v) for k, v in weights_hist.iloc[-1].items()}
    reb_dates = backtest._rebalance_dates(weights_hist.index, strategy.rebalance)
    last_reb = max(reb_dates).date() if reb_dates else None

    latest_prices = {
        t: float(prices_wide[t].dropna().iloc[-1])
        for t in current_weights
        if not prices_wide[t].dropna().empty
    }
    current_values = {t: notional * w for t, w in current_weights.items()}
    plan = rebalancing.build_plan(
        strategy,
        current_values=current_values,
        latest_prices=latest_prices,
        weight_band=PP_WEIGHT_BAND,
        as_of=as_of or date.today(),
    )
    return PPRebalanceReport(plan=plan, current_weights=current_weights, last_rebalance=last_reb)


def compute_market_report(
    meta: pd.DataFrame,
    snapshots: pd.DataFrame,
    corr_prices_wide: pd.DataFrame,
    *,
    top_n: int = 10,
) -> MarketReport:
    """Asset-class mix, today's movers, estimated flows, and a correlation grid."""
    report = MarketReport()

    if not meta.empty and "asset_class" in meta.columns:
        report.asset_class_counts = meta["asset_class"].value_counts()

    if not snapshots.empty:
        latest_date = snapshots["snap_date"].max()
        latest = snapshots[snapshots["snap_date"] == latest_date]
        movers_cols = [c for c in ("ticker", "change_rate") if c in latest.columns]
        if "change_rate" in latest.columns:
            ranked = latest[movers_cols].dropna(subset=["change_rate"])
            report.top_gainers = ranked.nlargest(top_n, "change_rate").reset_index(drop=True)
            report.top_losers = ranked.nsmallest(top_n, "change_rate").reset_index(drop=True)
        report.inflows = top_flows(snapshots, n=top_n, direction="in")
        report.outflows = top_flows(snapshots, n=top_n, direction="out")

    if not corr_prices_wide.empty and corr_prices_wide.shape[1] >= 2:
        report.corr = correlation_matrix(corr_prices_wide)

    return report


# --- repository wiring -------------------------------------------------------


def gather_report(repo, strategies: list[Strategy], *, as_of: date | None = None) -> ReportBundle:
    """Pull from the SQLite cache and assemble a full ReportBundle."""
    strat_reports: list[StrategyReport] = []
    pp_report: PPRebalanceReport | None = None

    for strat in strategies:
        tickers = [leg.ticker for leg in strat.legs]
        prices_long = repo.get_prices(tickers)
        prices_wide = (
            prices_long.pivot(index="date", columns="ticker", values="close")
            if not prices_long.empty
            else pd.DataFrame()
        )
        bench = None
        if strat.benchmark_ticker:
            bl = repo.get_prices(strat.benchmark_ticker)
            if not bl.empty:
                bench = bl.set_index("date")["close"]

        if prices_wide.empty:
            strat_reports.append(
                StrategyReport(strategy=strat, error="가격 데이터 없음 (ingest 필요)")
            )
            continue

        strat_reports.append(compute_strategy_report(strat, prices_wide, bench))
        if strat.id == PP_STRATEGY_ID:
            pp_report = compute_pp_rebalance(strat, prices_wide, as_of=as_of)

    # Market section: all meta, all snapshots, correlation across strategy legs.
    meta = repo.list_etfs()
    snapshots = repo.get_snapshots()
    all_legs = sorted({leg.ticker for s in strategies for leg in s.legs})
    corr_long = repo.get_prices(all_legs) if all_legs else pd.DataFrame()
    corr_wide = (
        corr_long.pivot(index="date", columns="ticker", values="close")
        if not corr_long.empty
        else pd.DataFrame()
    )
    market = compute_market_report(meta, snapshots, corr_wide)

    return ReportBundle(
        generated_at=datetime.now(),
        data_as_of=repo.last_snapshot_date(),
        strategies=strat_reports,
        market=market,
        pp_rebalance=pp_report,
    )
