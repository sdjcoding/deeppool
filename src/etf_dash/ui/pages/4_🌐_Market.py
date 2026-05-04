"""Market — feature F. Asset class distribution, fund flows, correlation."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from etf_dash.analysis.correlation import correlation_matrix
from etf_dash.analysis.flows import top_flows
from etf_dash.ui._shared import cached_meta, cached_prices, cached_snapshots
from etf_dash.ui.components.charts import asset_class_pie, correlation_heatmap

st.set_page_config(page_title="Market", page_icon="🌐", layout="wide")
st.title("🌐 시장 / 매크로 분석")

meta = cached_meta()
if meta.empty:
    st.warning("ETF 데이터가 없습니다.")
    st.stop()

snap_all = cached_snapshots()
if snap_all.empty:
    st.warning("스냅샷 데이터가 없습니다. ingest --job meta를 먼저 실행하세요.")
    st.stop()

latest_snap_date = snap_all["snap_date"].max()
latest = snap_all[snap_all["snap_date"] == latest_snap_date]

# --- 1. asset class distribution ---
st.subheader(f"자산군 분포 (시가총액 기준, {latest_snap_date.date()})")
joined = latest.merge(meta[["ticker", "asset_class"]], on="ticker", how="left")
by_class = joined.groupby("asset_class")["mar_cap"].sum().sort_values(ascending=False)
col1, col2 = st.columns([1, 1])
with col1:
    st.plotly_chart(asset_class_pie(by_class), width="stretch")
with col2:
    by_class_df = by_class.reset_index()
    by_class_df.columns = ["자산군", "시가총액 (억원)"]
    by_class_df["비중(%)"] = (by_class_df["시가총액 (억원)"] / by_class_df["시가총액 (억원)"].sum() * 100)
    st.dataframe(
        by_class_df,
        hide_index=True,
        width="stretch",
        column_config={
            "시가총액 (억원)": st.column_config.NumberColumn(format="%,d"),
            "비중(%)": st.column_config.NumberColumn(format="%.1f"),
        },
    )

# --- 2. top movers (당일) ---
st.subheader(f"오늘의 주요 움직임 ({latest_snap_date.date()})")
movers = latest.merge(meta[["ticker", "name", "asset_class"]], on="ticker")
top_up = movers.nlargest(10, "change_rate")[["ticker", "name", "asset_class", "change_rate"]]
top_dn = movers.nsmallest(10, "change_rate")[["ticker", "name", "asset_class", "change_rate"]]
col1, col2 = st.columns(2)
with col1:
    st.markdown("**상승 Top 10**")
    st.dataframe(
        top_up.rename(columns={"ticker": "코드", "name": "이름",
                                "asset_class": "자산군", "change_rate": "변동(%)"}),
        hide_index=True,
        width="stretch",
        column_config={"변동(%)": st.column_config.NumberColumn(format="%+.2f")},
    )
with col2:
    st.markdown("**하락 Top 10**")
    st.dataframe(
        top_dn.rename(columns={"ticker": "코드", "name": "이름",
                                "asset_class": "자산군", "change_rate": "변동(%)"}),
        hide_index=True,
        width="stretch",
        column_config={"변동(%)": st.column_config.NumberColumn(format="%+.2f")},
    )

# --- 3. fund flows (needs >= 2 snapshot dates) ---
st.subheader("자금 유입/유출 (스냅샷 기반 추정)")
distinct_dates = snap_all["snap_date"].nunique()
if distinct_dates < 2:
    st.info(
        f"자금흐름 추정에는 최소 2일치 스냅샷이 필요합니다 (현재 {distinct_dates}일). "
        "매일 `python -m etf_dash.ingest --job meta`를 실행해 누적해 주세요."
    )
else:
    inflows = top_flows(snap_all, n=10, direction="in").merge(
        meta[["ticker", "name", "asset_class"]], on="ticker"
    )
    outflows = top_flows(snap_all, n=10, direction="out").merge(
        meta[["ticker", "name", "asset_class"]], on="ticker"
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**순유입 Top 10**")
        st.dataframe(
            inflows.rename(columns={"ticker": "코드", "name": "이름",
                                    "asset_class": "자산군", "total_flow": "추정 순유입 (억원)"}),
            hide_index=True,
            width="stretch",
            column_config={"추정 순유입 (억원)": st.column_config.NumberColumn(format="%,d")},
        )
    with col2:
        st.markdown("**순유출 Top 10**")
        st.dataframe(
            outflows.rename(columns={"ticker": "코드", "name": "이름",
                                     "asset_class": "자산군", "total_flow": "추정 순유출 (억원)"}),
            hide_index=True,
            width="stretch",
            column_config={"추정 순유출 (억원)": st.column_config.NumberColumn(format="%,d")},
        )

# --- 4. correlation heatmap ---
st.markdown("---")
st.subheader("상관관계 히트맵")
st.caption(
    "ETF를 2-15개 선택하면 일일 수익률 기준 피어슨 상관계수 행렬을 표시합니다."
)
options_label = {row["ticker"]: f"{row['ticker']} — {row['name']}" for _, row in meta.iterrows()}
default = ["069500", "273130", "360750", "132030"]
default = [t for t in default if t in options_label]
selected = st.multiselect(
    "ETF 선택",
    options=list(options_label.keys()),
    default=default,
    format_func=lambda t: options_label.get(t, t),
    max_selections=15,
)
if 2 <= len(selected) <= 15:
    prices = cached_prices(tuple(selected))
    if prices.empty:
        st.info(
            "선택한 ETF 중 일부의 가격 데이터가 없습니다. ingest를 실행하세요."
        )
    else:
        wide = prices.pivot(index="date", columns="ticker", values="close")
        corr = correlation_matrix(wide)
        if corr.empty or corr.shape[0] < 2:
            st.info("선택한 ETF들의 공통 거래 구간이 부족합니다.")
        else:
            st.plotly_chart(correlation_heatmap(corr), width="stretch")
elif len(selected) >= 1:
    st.info("2개 이상 선택해 주세요.")
