"""Reporting layer tests — pure builders + HTML render with synthetic data."""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

from etf_dash.domain.models import Strategy, StrategyLeg
from etf_dash.reporting import report_data
from etf_dash.reporting.render import render_html


def _wide_prices(tickers, periods=400, start="2022-01-03", seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=periods, freq="B")
    return pd.DataFrame(
        {t: (1 + rng.normal(0.0003, 0.01, periods)).cumprod() * 100 for t in tickers},
        index=idx,
    )


def _pp_strategy() -> Strategy:
    return Strategy(
        id=report_data.PP_STRATEGY_ID,
        name="영구 포트폴리오",
        description="",
        legs=(
            StrategyLeg("069500", 0.25, "주식"),
            StrategyLeg("148070", 0.25, "장기국채"),
            StrategyLeg("132030", 0.25, "금"),
            StrategyLeg("153130", 0.25, "현금성"),
        ),
        rebalance="yearly",
    )


def test_compute_strategy_report_success_and_error():
    strat = _pp_strategy()
    tickers = [leg.ticker for leg in strat.legs]
    ok = report_data.compute_strategy_report(strat, _wide_prices(tickers))
    assert ok.error is None
    assert {"ann_return", "sharpe", "max_drawdown"}.issubset(ok.summary)
    assert ok.equity_curve is not None and not ok.equity_curve.empty

    # Missing tickers -> captured as an error, never raised.
    bad = report_data.compute_strategy_report(strat, _wide_prices(["069500"]))
    assert bad.error is not None
    assert bad.equity_curve is None


def test_compute_pp_rebalance_returns_plan():
    strat = _pp_strategy()
    tickers = [leg.ticker for leg in strat.legs]
    pp = report_data.compute_pp_rebalance(strat, _wide_prices(tickers, seed=7))
    assert pp is not None
    assert pp.last_rebalance is not None
    assert len(pp.plan.actions) == 4
    # Current weights should be a real distribution summing to ~1.
    assert abs(sum(pp.current_weights.values()) - 1.0) < 1e-6


def test_compute_market_report_movers_and_corr():
    meta = pd.DataFrame(
        {
            "ticker": ["069500", "148070", "132030", "153130"],
            "name": ["A", "B", "C", "D"],
            "asset_class": ["국내주식", "채권", "원자재", "채권"],
        }
    )
    snapshots = pd.DataFrame(
        {
            "ticker": ["069500", "148070", "132030", "153130"],
            "snap_date": ["2026-06-05"] * 4,
            "mar_cap": [1000.0, 2000.0, 500.0, 800.0],
            "change_rate": [2.5, -1.0, 3.3, 0.1],
        }
    )
    corr = _wide_prices(["069500", "148070", "132030", "153130"])
    market = report_data.compute_market_report(meta, snapshots, corr)
    assert market.asset_class_counts.loc["채권"] == 2
    # Top gainer is the highest change_rate.
    assert market.top_gainers.iloc[0]["ticker"] == "132030"
    assert market.top_losers.iloc[0]["ticker"] == "148070"
    assert market.corr.shape == (4, 4)


def test_render_html_contains_all_sections():
    strat = _pp_strategy()
    tickers = [leg.ticker for leg in strat.legs]
    prices = _wide_prices(tickers)
    bundle = report_data.ReportBundle(
        generated_at=datetime(2026, 6, 6, 9, 0),
        data_as_of=date(2026, 6, 5),
        strategies=[report_data.compute_strategy_report(strat, prices)],
        market=report_data.compute_market_report(
            pd.DataFrame({"ticker": tickers, "asset_class": ["주식", "채권", "금", "채권"]}),
            pd.DataFrame(),
            prices,
        ),
        pp_rebalance=report_data.compute_pp_rebalance(strat, prices),
    )
    out = render_html(bundle)
    assert "<!DOCTYPE html>" in out
    assert "noindex" in out
    assert "전략 백테스트 요약" in out
    assert "영구 포트폴리오 리밸런싱 현황" in out
    assert "시장 스냅샷" in out
    assert "투자 자문이 아닙니다" in out
    # Plotly is embedded exactly once via the CDN.
    assert out.count("cdn.plot.ly") == 1
