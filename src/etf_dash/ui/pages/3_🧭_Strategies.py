"""Strategies — feature E. Backtest curated asset-allocation templates."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from etf_dash.analysis import backtest
from etf_dash.ui._shared import (
    cached_explain_strategy,
    cached_prices,
    cached_strategies,
    has_explainer,
)
from etf_dash.ui.auth import require_password
from etf_dash.ui.components.charts import (
    drawdown_chart,
    equity_curve,
    yearly_returns_bar,
)
from etf_dash.ui.components.tables import format_metrics_table

st.set_page_config(page_title="Strategies", page_icon="🧭", layout="wide")
require_password()
st.title("🧭 자산배분 전략 백테스트")

strategies = cached_strategies()

choice = st.selectbox(
    "전략 선택",
    options=strategies,
    format_func=lambda s: s.name,
)

st.markdown(f"**설명**: {choice.description}")

# --- legs table ---
legs_df = pd.DataFrame(
    [
        {
            "코드": leg.ticker,
            "비중": f"{leg.weight*100:.1f}%",
            "역할": leg.role,
        }
        for leg in choice.legs
    ]
)
st.dataframe(legs_df, hide_index=True, width="stretch")

st.caption(
    f"리밸런스: **{choice.rebalance}** · "
    f"벤치마크: **{choice.benchmark_ticker or '없음'}**"
)

# --- fetch prices for all legs + benchmark ---
leg_tickers = tuple(leg.ticker for leg in choice.legs)
prices_long = cached_prices(leg_tickers)
if prices_long.empty:
    st.error(
        "구성 ETF의 가격 데이터가 캐시에 없습니다. 다음 명령으로 적재하세요:\n\n"
        "```bash\n"
        "uv run python -m etf_dash.ingest --job prices --full "
        + " ".join(f"--ticker {t}" for t in leg_tickers)
        + "\n```"
    )
    st.stop()

prices_wide = prices_long.pivot(index="date", columns="ticker", values="close")
missing = [t for t in leg_tickers if t not in prices_wide.columns]
if missing:
    st.error(f"가격 데이터가 누락된 티커: {', '.join(missing)}")
    st.stop()

bench_series = None
if choice.benchmark_ticker:
    bench_long = cached_prices((choice.benchmark_ticker,))
    if not bench_long.empty:
        bench_series = bench_long.set_index("date")["close"]

# --- date range clamp ---
common_start = prices_wide.dropna(how="any").index.min()
common_end = prices_wide.dropna(how="any").index.max()
if pd.isna(common_start):
    st.error("구성 ETF들의 공통 거래 구간이 없습니다.")
    st.stop()

st.caption(
    f"데이터 가용 구간: {common_start.date()} → {common_end.date()} "
    f"(가장 늦게 상장된 구성 ETF 기준)"
)
date_range = st.slider(
    "백테스트 기간",
    min_value=common_start.date(),
    max_value=common_end.date(),
    value=(common_start.date(), common_end.date()),
    format="YYYY-MM-DD",
)

# --- run backtest ---
result = backtest.simulate(
    choice,
    prices_wide,
    start=date_range[0],
    end=date_range[1],
    benchmark_prices=bench_series,
)

# --- equity curve + benchmark ---
st.subheader("Equity Curve")
st.plotly_chart(
    equity_curve(
        result.equity_curve,
        result.benchmark_curve,
        strategy_name=choice.name,
        benchmark_name=f"{choice.benchmark_ticker} (벤치)",
    ),
    width="stretch",
)

# --- summary metrics ---
st.subheader("요약 지표")
st.dataframe(format_metrics_table(result.summary), hide_index=True, width="stretch")

# --- AI 해설 (optional, click-to-fetch) ---
with st.expander("🤖 AI 전략 해설 (Claude Sonnet)", expanded=False):
    if not has_explainer():
        st.info(
            "Anthropic API 키 미설정. `.streamlit/secrets.toml`에 "
            "`anthropic_api_key = \"sk-ant-...\"`를 추가하고 재시작하세요."
        )
    else:
        st.caption(
            "버튼을 누르면 Claude가 위 백테스트 결과를 한국어 350~400자로 평가합니다. "
            "같은 전략은 하루 1회만 실제 API 호출."
        )
        if st.button("AI 해설 받기", key="ai_strat"):
            sig = (
                f"{result.summary.get('total_return'):.4f}|"
                f"{result.summary.get('sharpe'):.4f}|"
                f"{result.start}|{result.end}"
            )
            with st.spinner("Claude 호출 중…"):
                text = cached_explain_strategy(choice.id, sig)
            st.write(text or "_(빈 응답)_")

# --- drawdown + yearly ---
col1, col2 = st.columns(2)
with col1:
    st.subheader("Drawdown")
    st.plotly_chart(drawdown_chart(backtest.drawdown_curve(result.equity_curve)), width="stretch")
with col2:
    st.subheader("연도별 수익률")
    yr = backtest.yearly_returns(result.equity_curve)
    st.plotly_chart(yearly_returns_bar(yr), width="stretch")

st.markdown("---")
st.caption(
    "ℹ️ 백테스트는 가격 기준 (분배락 미반영) · 수수료 0% 가정 · "
    "리밸런스 시점에서 정확한 비중으로 즉시 재배분."
)
