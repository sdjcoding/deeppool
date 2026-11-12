"""Rebalancing — 정기 건仓/조仓 제안 + 주기 비교 백테스트.

전략(영구 포트폴리오 포함)을 고르고 주기를 선택하면
  A) 현재 보유액(또는 총 투자금) 기준 매수/매도 금액·주수와 다음 리밸런싱 예정일을 산출하고
  B) 주/월/분기/반기/연 리밸런싱의 과거 성과를 비교한다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from etf_dash.analysis import rebalancing
from etf_dash.ui._shared import cached_prices, cached_strategies, fetch_prices_now
from etf_dash.ui.auth import require_password

st.set_page_config(page_title="Rebalancing", page_icon="♻️", layout="wide")
require_password()
st.title("♻️ 정기 리밸런싱 제안")
st.caption(
    "영구 포트폴리오 등 고정 목표비중 전략에 대해 건仓(매수)·감仓(매도)·조仓(리밸런싱) "
    "제안을 주기(주/월/분기/반기/연)별로 산출합니다."
)

FREQ_LABELS: dict[str, str] = {
    "weekly": "매주",
    "monthly": "매월",
    "quarterly": "분기",
    "semi_annual": "반기",
    "yearly": "매년",
}
FREQ_OPTIONS = list(FREQ_LABELS.keys())

strategies = cached_strategies()
choice = st.selectbox("전략 선택", options=strategies, format_func=lambda s: s.name)

st.markdown(f"**설명**: {choice.description}")

default_freq = choice.rebalance if choice.rebalance in FREQ_OPTIONS else "quarterly"
freq = st.selectbox(
    "리밸런싱 주기",
    options=FREQ_OPTIONS,
    index=FREQ_OPTIONS.index(default_freq),
    format_func=lambda f: FREQ_LABELS[f],
    help="전략의 권장 주기가 기본값으로 선택됩니다.",
)

# --- latest close per leg (for share counts) ---------------------------------
leg_tickers = tuple(leg.ticker for leg in choice.legs)
prices_long = cached_prices(leg_tickers)
latest_prices: dict[str, float] = {}
if not prices_long.empty:
    last_rows = prices_long.sort_values("date").groupby("ticker").tail(1)
    latest_prices = dict(zip(last_rows["ticker"], last_rows["close"], strict=False))

missing_prices = [t for t in leg_tickers if t not in latest_prices]
if missing_prices:
    st.warning(
        "다음 구성 ETF의 가격 데이터가 캐시에 없어 주수 계산/백테스트가 제한됩니다: "
        f"{', '.join(missing_prices)}"
    )
    with st.expander("지금 가격 데이터 적재하기"):
        st.caption("FDR에서 최근 5년 일봉을 받아 캐시에 저장합니다 (네트워크 필요).")
        for t in missing_prices:
            if st.button(f"{t} 적재", key=f"ingest_{t}"):
                with st.spinner(f"{t} 가격 적재 중…"):
                    ok, msg = fetch_prices_now(t)
                (st.success if ok else st.error)(msg)
                st.rerun()

st.markdown("---")

# === 섹션 A — 건仓/조仓 어드바이저 ===========================================
st.header("① 건仓 · 조仓 어드바이저")

mode = st.radio(
    "모드",
    options=["신규 건仓", "기존 조仓"],
    horizontal=True,
    help=(
        "신규 건仓: 총 투자금을 목표 비중대로 분할 매수. "
        "기존 조仓: 현재 평가액 입력 후 목표 비중 회복."
    ),
)

if mode == "신규 건仓":
    total_capital = st.number_input(
        "총 투자금 (원)",
        min_value=0,
        value=10_000_000,
        step=1_000_000,
        format="%d",
    )
    plan = rebalancing.build_plan(
        choice,
        current_values=None,
        total_capital=float(total_capital),
        latest_prices=latest_prices or None,
        freq=freq,
    )
else:
    st.caption("각 구성 ETF의 현재 평가액(원)을 입력하세요.")
    current_values: dict[str, float] = {}
    cols = st.columns(min(len(choice.legs), 4))
    for i, leg in enumerate(choice.legs):
        with cols[i % len(cols)]:
            current_values[leg.ticker] = float(
                st.number_input(
                    f"{leg.ticker} · {leg.role}",
                    min_value=0,
                    value=2_500_000,
                    step=100_000,
                    format="%d",
                    key=f"cur_{leg.ticker}",
                )
            )

    # --- rebalancing trigger rule ---
    trigger = st.radio(
        "리밸런싱 기준",
        options=["드리프트 밴드", "절대 비중 밴드 (Browne)"],
        horizontal=True,
        help=(
            "드리프트 밴드: 목표 비중에서 ±기준% 이상 벗어나면 권장. "
            "절대 비중 밴드: 어떤 자산이라도 하한~상한(%) 범위를 벗어나면 권장 "
            "(영구 포트폴리오의 35/15 규칙)."
        ),
    )
    weight_band = None
    drift_band = 0.05
    if trigger == "드리프트 밴드":
        drift_band = (
            st.slider("허용 드리프트 (±%)", min_value=1, max_value=20, value=5) / 100.0
        )
    else:
        bc1, bc2 = st.columns(2)
        low = bc1.number_input("하한 (%)", min_value=0, max_value=100, value=15, step=1)
        high = bc2.number_input("상한 (%)", min_value=0, max_value=100, value=35, step=1)
        weight_band = (low / 100.0, high / 100.0)

    if sum(current_values.values()) <= 0:
        st.info("평가액을 입력하면 조정 제안이 표시됩니다.")
        st.stop()
    plan = rebalancing.build_plan(
        choice,
        current_values=current_values,
        latest_prices=latest_prices or None,
        freq=freq,
        drift_band=drift_band,
        weight_band=weight_band,
    )

# --- banner + schedule ---
if plan.needs_rebalance:
    st.warning(plan.note)
else:
    st.success(plan.note)

info_cols = st.columns(3)
info_cols[0].metric("총 평가액", f"{plan.total_value:,.0f} 원")
info_cols[1].metric("최대 드리프트", f"{plan.max_drift * 100:.1f}%")
info_cols[2].metric(
    "다음 리밸런싱 예정",
    plan.next_rebalance_date.strftime("%Y-%m-%d") if plan.next_rebalance_date else "—",
)


def _shares_text(action) -> str:
    if action.delta_shares is None:
        return "—"
    verb = "매수" if action.delta_shares > 0 else "매도"
    return f"{verb} {abs(action.delta_shares):,.0f}주"


plan_df = pd.DataFrame(
    [
        {
            "코드": a.ticker,
            "역할": a.role,
            "목표비중": f"{a.target_weight * 100:.1f}%",
            "현재비중": f"{a.current_weight * 100:.1f}%",
            "목표금액": f"{a.target_value:,.0f}",
            "조정금액": f"{a.delta_value:+,.0f}",
            "주문(개략)": _shares_text(a),
            "액션": a.action,
        }
        for a in plan.actions
    ]
)
st.dataframe(plan_df, hide_index=True, width="stretch")
st.caption(
    "주문 수량은 최신 종가 기준 개략치입니다 (소수주 미반영, 호가/체결가 차이 가능). "
    "현금성 레그를 단기채 ETF가 아닌 예금/CMA로 보유한다면 해당 행은 현금 비중으로 해석하세요."
)

# === 섹션 B — 주기 비교 백테스트 =============================================
st.markdown("---")
st.header("② 주기 비교 백테스트")

if missing_prices:
    st.info("구성 ETF 가격 데이터가 모두 적재되면 주기별 성과 비교가 가능합니다.")
    st.stop()

prices_wide = prices_long.pivot(index="date", columns="ticker", values="close")
common = prices_wide[list(leg_tickers)].dropna(how="any")
if len(common) < 2:
    st.error("구성 ETF들의 공통 거래 구간이 부족합니다.")
    st.stop()

common_start, common_end = common.index.min(), common.index.max()
st.caption(
    f"데이터 가용 구간: {common_start.date()} → {common_end.date()} "
    "(가장 늦게 상장된 구성 ETF 기준)"
)
date_range = st.slider(
    "비교 기간",
    min_value=common_start.date(),
    max_value=common_end.date(),
    value=(common_start.date(), common_end.date()),
    format="YYYY-MM-DD",
)

bench_series = None
if choice.benchmark_ticker:
    bench_long = cached_prices((choice.benchmark_ticker,))
    if not bench_long.empty:
        bench_series = bench_long.set_index("date")["close"]

comp = rebalancing.compare_rebalance_frequencies(
    choice,
    prices_wide,
    start=date_range[0],
    end=date_range[1],
    benchmark_prices=bench_series,
)

comp_display = pd.DataFrame(
    {
        "주기": [FREQ_LABELS.get(f, f) for f in comp.index],
        "연환산 수익률": [f"{v * 100:+.2f}%" for v in comp["ann_return"]],
        "연환산 변동성": [f"{v * 100:.2f}%" for v in comp["ann_volatility"]],
        "샤프비율": [f"{v:.2f}" for v in comp["sharpe"]],
        "최대낙폭": [f"{v * 100:.2f}%" for v in comp["max_drawdown"]],
        "총 수익률": [f"{v * 100:+.2f}%" for v in comp["total_return"]],
    }
)
st.dataframe(comp_display, hide_index=True, width="stretch")
st.bar_chart(comp["sharpe"].rename("샤프비율"))

st.markdown("---")
st.caption(
    "ℹ️ 백테스트는 가격 기준 (분배락 미반영) · 수수료/세금 0% 가정 · "
    "리밸런스 시점에서 정확한 비중으로 즉시 재배분. 본 화면은 투자 자문이 아닙니다."
)
