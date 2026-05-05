"""Shared cached accessors used by every Streamlit page."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from etf_dash.analysis.strategies import load_strategies
from etf_dash.config import PROJECT_ROOT, get_settings
from etf_dash.repository.etf_repository import ETFRepository

STRATEGIES_YAML = PROJECT_ROOT / "config" / "strategies.yaml"


@st.cache_resource
def get_repo() -> ETFRepository:
    return ETFRepository()


@st.cache_data(ttl=3600)
def cached_meta() -> pd.DataFrame:
    return get_repo().list_etfs()


@st.cache_data(ttl=3600)
def cached_snapshots(tickers: tuple[str, ...] | None = None) -> pd.DataFrame:
    return get_repo().get_snapshots(list(tickers) if tickers else None)


@st.cache_data(ttl=3600)
def cached_prices(
    tickers: tuple[str, ...], start: date | None = None, end: date | None = None
) -> pd.DataFrame:
    return get_repo().get_prices(list(tickers), start=start, end=end)


@st.cache_data(ttl=3600)
def cached_strategies():
    return load_strategies(STRATEGIES_YAML)


@st.cache_data(ttl=3600)
def cached_holdings(ticker: str) -> pd.DataFrame:
    return get_repo().get_holdings(ticker)


def fetch_holdings_now(ticker: str) -> tuple[bool, str]:
    """User-triggered holdings fetch from Naver Finance.

    Returns (ok, message). On success, also clears the cached_holdings cache
    for this ticker so the UI sees the new rows immediately on rerun.
    """
    from datetime import date as _date

    from etf_dash.providers.naver_holdings import NaverHoldingsProvider

    repo = get_repo()
    try:
        df = NaverHoldingsProvider().get_holdings(ticker)
    except Exception as exc:  # noqa: BLE001
        return False, f"Naver 호출 실패: {type(exc).__name__}: {exc}"
    if df.empty:
        return False, "Naver Finance에 구성종목 표가 없습니다 (액티브/해외자산 ETF는 미공개일 수 있음)."
    repo.upsert_holdings(ticker, _date.today(), df)
    cached_holdings.clear()
    return True, f"{len(df)}개 보유종목 적재 완료."


def fetch_prices_now(ticker: str) -> tuple[bool, str]:
    """User-triggered full-history price fetch for a single ticker."""
    from datetime import date as _date, timedelta as _td

    from etf_dash.providers.fdr_provider import FDRProvider

    repo = get_repo()
    end = _date.today()
    start = end - _td(days=365 * 5)
    try:
        df = FDRProvider().get_ohlcv(ticker, start, end)
    except Exception as exc:  # noqa: BLE001
        return False, f"FDR 호출 실패: {type(exc).__name__}: {exc}"
    if df.empty:
        return False, "FDR이 빈 가격 데이터를 반환했습니다."
    df.insert(0, "ticker", ticker)
    n = repo.upsert_prices(df)
    cached_prices.clear()
    return True, f"{n}개 일봉 적재 완료."


def show_data_health(repo: ETFRepository) -> None:
    """Top-of-page banner showing cache freshness and any 'no data' guidance."""
    last_meta = repo.last_meta_update()
    last_snap = repo.last_snapshot_date()
    n_etfs = len(repo.list_etfs())
    if n_etfs == 0:
        st.warning(
            "데이터가 비어 있습니다. 터미널에서 다음을 실행하세요:\n\n"
            "```bash\n"
            "uv run python -m etf_dash.ingest --job meta\n"
            "uv run python -m etf_dash.ingest --job prices --full\n"
            "```"
        )
        return
    cols = st.columns(3)
    cols[0].metric("등록 ETF", f"{n_etfs:,}")
    cols[1].metric(
        "메타 갱신", last_meta.strftime("%Y-%m-%d %H:%M") if last_meta else "—"
    )
    cols[2].metric(
        "스냅샷 최신", last_snap.strftime("%Y-%m-%d") if last_snap else "—"
    )
