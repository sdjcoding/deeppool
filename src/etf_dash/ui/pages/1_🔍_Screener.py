"""Screener — feature A. Filter, sort, and compare KRX ETFs."""

from __future__ import annotations

import streamlit as st

from etf_dash.ui._shared import cached_meta, cached_prices, cached_snapshots
from etf_dash.ui.components.charts import normalized_overlay
from etf_dash.ui.components.filters import apply_filters, screener_sidebar
from etf_dash.ui.components.tables import format_screener_table

st.set_page_config(page_title="ETF Screener", page_icon="🔍", layout="wide")
st.title("🔍 ETF Screener")
st.caption("KRX 상장 ETF를 자산군·운용사·이름으로 탐색하고 비교하세요.")

meta = cached_meta()
if meta.empty:
    st.warning("ETF 데이터가 없습니다. 먼저 ingest를 실행하세요.")
    st.stop()

filters = screener_sidebar(meta)
filtered = apply_filters(meta, filters)

snap = cached_snapshots(tuple(filtered["ticker"].tolist()) if not filtered.empty else None)
display_df = format_screener_table(filtered, snap)

st.markdown(f"**검색 결과: {len(display_df):,}개 ETF**")
selected = st.dataframe(
    display_df,
    width="stretch",
    height=480,
    hide_index=True,
    column_config={
        "MarCap (억원)": st.column_config.NumberColumn(format="%,d"),
        "가격": st.column_config.NumberColumn(format="%,d"),
        "NAV": st.column_config.NumberColumn(format="%,d"),
        "당일변동(%)": st.column_config.NumberColumn(format="%+.2f"),
        "1Y수익률(%)": st.column_config.NumberColumn(format="%+.2f"),
    },
    on_select="rerun",
    selection_mode="multi-row",
)

selected_indices = selected.selection.rows if hasattr(selected, "selection") else []
selected_tickers = display_df.iloc[selected_indices]["코드"].tolist() if selected_indices else []

# --- selection actions ---
col1, col2 = st.columns([1, 3])
with col1:
    if selected_tickers:
        st.markdown(f"**선택됨**: `{', '.join(selected_tickers)}`")
        if len(selected_tickers) == 1 and st.button(f"📈 `{selected_tickers[0]}` 상세 보기"):
            st.query_params.update(ticker=selected_tickers[0])
            st.switch_page("pages/2_📈_ETF_Detail.py")
    else:
        st.markdown("_표에서 ETF를 선택하면 액션 옵션이 보입니다._")

# --- comparison overlay (2-4 selected) ---
if 2 <= len(selected_tickers) <= 6:
    st.markdown("---")
    st.subheader("선택 ETF 비교 (정규화 가격 오버레이)")
    prices = cached_prices(tuple(selected_tickers))
    if prices.empty:
        st.info(
            "선택한 ETF의 가격 데이터가 캐시에 없습니다. "
            "다음 명령으로 적재하세요:\n\n"
            "```bash\n"
            f"uv run python -m etf_dash.ingest --job prices --full "
            + " ".join(f"--ticker {t}" for t in selected_tickers)
            + "\n```"
        )
    else:
        wide = prices.pivot(index="date", columns="ticker", values="close")
        st.plotly_chart(normalized_overlay(wide), width="stretch")
elif len(selected_tickers) > 6:
    st.warning("비교는 최대 6개까지만 지원합니다.")
