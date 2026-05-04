"""DeepPool — KRX ETF analysis dashboard. Streamlit entry point."""

from __future__ import annotations

import streamlit as st

from etf_dash.ui._shared import get_repo, show_data_health
from etf_dash.ui.auth import require_password

st.set_page_config(
    page_title="DeepPool — KRX ETF Dashboard",
    page_icon="📊",
    layout="wide",
)

require_password()

st.title("DeepPool")
st.caption("KRX 상장 ETF 분석 · 자산배분 전략 백테스트 · 시장 매크로 모니터")

repo = get_repo()
show_data_health(repo)

st.markdown(
    """
### 페이지 안내

- **🔍 Screener** — 자산군·운용사·이름으로 ETF 탐색·비교
- **📈 ETF Detail** — 개별 ETF의 가격·수익률·MDD·Sharpe 등 지표
- **🧭 Strategies** — All Weather · 60/40 · Core-Satellite 백테스트
- **🌐 Market** — 자산군 분포·자금흐름·상관관계

좌측 사이드바에서 페이지를 선택하세요.
"""
)

with st.expander("ℹ️ 데이터 출처 / 한계"):
    st.markdown(
        """
- 가격·NAV·시가총액: **FinanceDataReader** (Naver Finance)
- 운용사: ETF 이름 prefix 기반 매핑 (KODEX→삼성, TIGER→미래에셋 등)
- 자산군: FinanceDataReader Category(1~7) 매핑
- **수익률은 가격 기준** (분배락 보정 미반영). 분배금 정확 반영은 추후 단계.
- **총보수·상장일·벤치마크·보유종목**은 MVP 미수집. 추후 추가 예정.
- pykrx는 KRX 봇 차단으로 현재 미사용. KRX OPEN API 등록 시 재검토.
"""
    )
