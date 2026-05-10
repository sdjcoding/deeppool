"""Shared cached accessors used by every Streamlit page."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from etf_dash.analysis.llm_explainer import Explainer, get_default_explainer
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


# --- LLM explainer (cached so repeats don't burn API budget) -----------------


@st.cache_resource
def get_explainer() -> Explainer:
    """Resolve API key from secrets.toml or env, return ClaudeExplainer or NullExplainer."""
    api_key: str | None = None
    try:
        api_key = st.secrets.get("anthropic_api_key")
    except (FileNotFoundError, AttributeError):
        pass
    return get_default_explainer(api_key=api_key)


def has_explainer() -> bool:
    """True iff a real (non-Null) explainer is configured."""
    from etf_dash.analysis.llm_explainer import NullExplainer

    return not isinstance(get_explainer(), NullExplainer)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_explain_etf(ticker: str, _metrics_signature: str) -> str:
    """Cache key: (ticker, metrics_signature). Same inputs → 1 API call per day.

    `_metrics_signature` is a stringified hash of the metrics dict so different
    inputs invalidate the cache; the underscore prefix tells Streamlit to skip
    serializing the value for the hash key (it's already in the string).
    """
    repo = get_repo()
    meta = repo.get_etf(ticker)
    if meta is None:
        return ""
    # Re-derive metrics inside the cached fn so we don't depend on caller state.
    from etf_dash.analysis import metrics as metrics_mod

    prices_df = get_repo().get_prices(ticker)
    if prices_df.empty:
        return ""
    summary = metrics_mod.summary(prices_df.set_index("date")["close"])
    return get_explainer().explain_etf(meta, summary)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_explain_strategy(strategy_id: str, _result_signature: str) -> str:
    """Same caching pattern for strategy explanations."""
    from etf_dash.analysis import backtest as backtest_mod

    strategies = cached_strategies()
    strategy = next((s for s in strategies if s.id == strategy_id), None)
    if strategy is None:
        return ""
    leg_tickers = tuple(leg.ticker for leg in strategy.legs)
    prices_long = get_repo().get_prices(list(leg_tickers))
    if prices_long.empty:
        return ""
    prices_wide = prices_long.pivot(index="date", columns="ticker", values="close")
    if any(t not in prices_wide.columns for t in leg_tickers):
        return ""
    bench_series = None
    if strategy.benchmark_ticker:
        bench_long = get_repo().get_prices(strategy.benchmark_ticker)
        if not bench_long.empty:
            bench_series = bench_long.set_index("date")["close"]
    result = backtest_mod.simulate(strategy, prices_wide, benchmark_prices=bench_series)
    return get_explainer().explain_strategy(strategy, result)


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
