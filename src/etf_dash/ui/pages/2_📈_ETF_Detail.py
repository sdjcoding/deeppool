"""ETF Detail — feature B. Charts + metrics + Naver-sourced top holdings."""

from __future__ import annotations

import streamlit as st

from etf_dash.analysis import metrics
from etf_dash.ui._shared import (
    cached_holdings,
    cached_meta,
    cached_prices,
    cached_snapshots,
    fetch_holdings_now,
    fetch_prices_now,
    get_repo,
)
from etf_dash.ui.auth import require_password
from etf_dash.ui.components.charts import holdings_donut, price_line
from etf_dash.ui.components.tables import format_metrics_table

st.set_page_config(page_title="ETF Detail", page_icon="📈", layout="wide")
require_password()

meta = cached_meta()
if meta.empty:
    st.warning("ETF 데이터가 없습니다. 먼저 ingest를 실행하세요.")
    st.stop()

# --- pick ticker ---
all_tickers = meta["ticker"].tolist()
default_ticker = st.query_params.get("ticker", "069500")
if default_ticker not in all_tickers:
    default_ticker = all_tickers[0]

options_label = {row["ticker"]: f"{row['ticker']} — {row['name']}" for _, row in meta.iterrows()}
ticker = st.selectbox(
    "ETF 선택",
    options=all_tickers,
    index=all_tickers.index(default_ticker),
    format_func=lambda t: options_label.get(t, t),
)
if ticker != st.query_params.get("ticker"):
    st.query_params.update(ticker=ticker)

repo = get_repo()
etf = repo.get_etf(ticker)
assert etf is not None

# --- meta header ---
st.title(f"📈 {etf.name}")
st.caption(f"`{etf.ticker}` · {etf.asset_class} · {etf.issuer}")

# --- prices ---
prices_df = cached_prices((ticker,))
if prices_df.empty:
    st.warning(f"`{ticker}` 가격 데이터가 캐시에 없습니다.")
    if st.button("📥 지금 가져오기 (5년치)", key="fetch_prices"):
        with st.spinner("FDR에서 가격 데이터 가져오는 중…"):
            ok, msg = fetch_prices_now(ticker)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)
    st.stop()

prices = prices_df.set_index("date")["close"]
window_choice = st.radio(
    "기간",
    options=["1M", "3M", "1Y", "3Y", "MAX"],
    index=2,
    horizontal=True,
)
sliced = metrics._slice_window(prices, window_choice)
st.plotly_chart(price_line(sliced, title=""), width="stretch")

# --- metrics ---
st.subheader("성과 지표")
summary = metrics.summary(prices)
st.dataframe(format_metrics_table(summary), hide_index=True, width="stretch")

# --- holdings (Naver Finance) ---
st.markdown("---")
st.subheader("구성종목 (상위 10)")
st.caption(
    "출처: Naver Finance ETF 페이지의 '구성종목(구성자산)' 표. "
    "ETF 구성종목 = 펀드가 실제로 보유 중인 자산 목록과 비중. "
    "비중이 높은 종목이 ETF 수익률에 더 큰 영향을 줍니다."
)

holdings = cached_holdings(ticker)
if holdings.empty:
    st.info(
        f"`{ticker}`의 구성종목이 캐시에 없습니다. Naver Finance에서 가져옵니다 "
        "(액티브/해외자산 ETF는 미공개일 수 있음)."
    )
    if st.button("📥 구성종목 지금 가져오기", key="fetch_holdings"):
        with st.spinner("Naver Finance에서 구성종목 가져오는 중…"):
            ok, msg = fetch_holdings_now(ticker)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)
else:
    last_h = repo.last_holdings_date(ticker)
    col_chart, col_table = st.columns([1, 1])
    with col_chart:
        st.plotly_chart(holdings_donut(holdings, top_n=10), width="stretch")
    with col_table:
        display_h = holdings.head(10).rename(
            columns={
                "constituent_name": "종목",
                "shares": "주식수",
                "weight_pct": "비중(%)",
                "price": "현재가",
            }
        )
        st.dataframe(
            display_h,
            hide_index=True,
            width="stretch",
            column_config={
                "주식수": st.column_config.NumberColumn(format="%,d"),
                "비중(%)": st.column_config.NumberColumn(format="%.2f"),
                "현재가": st.column_config.NumberColumn(format="%,d"),
            },
        )
        st.caption(f"스냅샷: {last_h} · 새로 가져오려면 ↓ 버튼")
        if st.button("🔄 다시 가져오기", key="refresh_holdings"):
            with st.spinner("Naver Finance에서 다시 가져오는 중…"):
                ok, msg = fetch_holdings_now(ticker)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# --- snapshot trend ---
snap = cached_snapshots((ticker,))
if not snap.empty and len(snap) >= 2:
    st.markdown("---")
    st.subheader("스냅샷 추이 (NAV / 시가총액)")
    snap_indexed = snap.set_index("snap_date").sort_index()
    cols = st.columns(2)
    cols[0].line_chart(snap_indexed[["nav"]], height=240)
    cols[1].line_chart(snap_indexed[["mar_cap"]], height=240)
elif snap.shape[0] == 1:
    st.caption("스냅샷이 1개뿐입니다. 일배치를 며칠 누적하면 NAV/AUM 추이가 보입니다.")

# --- disclosures ---
st.markdown("---")
st.markdown(
    "_⚠️ 수익률은 가격 기준 (분배락 보정 미반영). 구성종목은 Naver Finance에서 "
    "가져온 상위 10개 스냅샷이며 ETF의 실제 전체 보유 종목 중 일부입니다. "
    "총보수·상장일·벤치마크 정보는 MVP에서 수집되지 않으며 추후 추가 예정입니다._"
)
