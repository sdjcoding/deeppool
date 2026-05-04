"""ETF Detail — feature B. Charts + metrics for a single ETF."""

from __future__ import annotations

import streamlit as st

from etf_dash.analysis import metrics
from etf_dash.ui._shared import (
    cached_meta,
    cached_prices,
    cached_snapshots,
    get_repo,
)
from etf_dash.ui.components.charts import price_line
from etf_dash.ui.components.tables import format_metrics_table

st.set_page_config(page_title="ETF Detail", page_icon="📈", layout="wide")

meta = cached_meta()
if meta.empty:
    st.warning("ETF 데이터가 없습니다. 먼저 ingest를 실행하세요.")
    st.stop()

# --- pick ticker ---
all_tickers = meta["ticker"].tolist()
default_ticker = st.query_params.get("ticker", "069500")
if default_ticker not in all_tickers:
    default_ticker = all_tickers[0]

# Quick switcher (preserves URL state)
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
assert etf is not None  # selected from dropdown

# --- meta header ---
st.title(f"📈 {etf.name}")
st.caption(f"`{etf.ticker}` · {etf.asset_class} · {etf.issuer}")

# --- prices ---
prices_df = cached_prices((ticker,))
if prices_df.empty:
    st.info(
        f"`{ticker}` 가격 데이터가 캐시에 없습니다. 다음 명령으로 적재하세요:\n\n"
        "```bash\n"
        f"uv run python -m etf_dash.ingest --job prices --full --ticker {ticker}\n"
        "```"
    )
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

# --- snapshot trend ---
snap = cached_snapshots((ticker,))
if not snap.empty and len(snap) >= 2:
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
    "_⚠️ 수익률은 가격 기준 (분배락 보정 미반영). 보유종목 / 총보수 / 상장일 / "
    "벤치마크 정보는 MVP에서 수집되지 않으며 추후 추가 예정입니다._"
)
