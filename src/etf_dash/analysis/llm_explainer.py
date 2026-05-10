"""LLM-based natural-language explanations for ETFs and strategies.

Two implementations:

- `NullExplainer` — no-op fallback. Used when no API key is configured so the
  UI can call `.explain_*()` unconditionally.
- `ClaudeExplainer` — calls the Anthropic Messages API.

Design notes (kept deliberately minimal — see `claude-api` skill for reference):

- Model: `claude-sonnet-4-6` by default (Sonnet is the cost/quality sweet spot
  for short Korean summaries; configured via `config/settings.yaml` → `llm.model`).
- `thinking={"type": "disabled"}` — these are short summarization tasks; reasoning
  is unnecessary and would inflate cost.
- `output_config={"effort": "low"}` — minimum overall token spend.
- **No prompt caching.** The Sonnet 4.6 minimum cacheable prefix is 2048 tokens;
  our prompts are ~500-700 tokens, so `cache_control` would never activate.
  Cost-control comes from Streamlit's `@st.cache_data` instead (1 call per
  ticker per day at most — see `ui/_shared.py`).
- Failures return a short Korean apology string rather than raising — the UI
  must not die because Anthropic had a hiccup.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

from etf_dash.analysis.backtest import BacktestResult
from etf_dash.config import get_settings
from etf_dash.domain.models import ETFMeta, Strategy

logger = logging.getLogger(__name__)


class Explainer(Protocol):
    def explain_etf(self, meta: ETFMeta, metrics: dict) -> str: ...
    def explain_strategy(self, strategy: Strategy, result: BacktestResult) -> str: ...


class NullExplainer:
    """No-op fallback used when no API key is configured."""

    def explain_etf(self, meta: ETFMeta, metrics: dict) -> str:  # noqa: ARG002
        return ""

    def explain_strategy(self, strategy: Strategy, result: BacktestResult) -> str:  # noqa: ARG002
        return ""


# --- Claude implementation ---------------------------------------------------

_SYSTEM_PROMPT_KO = (
    "당신은 한국 ETF 시장에 정통한 차분한 투자 분석가입니다. "
    "사용자가 보고 있는 ETF 또는 자산배분 전략의 핵심을 한국어로 간결하게 요약합니다.\n\n"
    "규칙:\n"
    "1. 200~400자 한국어. 마크다운 사용 금지(굵게/리스트 X), 단순 평문.\n"
    "2. 매수/매도 권유 금지. '투자 판단은 본인 책임'이라는 안전 문구는 마지막 한 문장으로만.\n"
    "3. 숫자는 입력에서 받은 값만 인용 (지어내지 말 것).\n"
    "4. 자산군·운용사·수익률·변동성·MDD·Sharpe 등 입력으로 들어온 사실에만 기반.\n"
    "5. 정중하고 단정한 어조. 과장된 표현 금지."
)


def _format_pct(x) -> str:
    try:
        if x is None:
            return "—"
        return f"{float(x) * 100:+.2f}%"
    except (TypeError, ValueError):
        return "—"


def _format_ratio(x) -> str:
    try:
        if x is None:
            return "—"
        return f"{float(x):.2f}"
    except (TypeError, ValueError):
        return "—"


class ClaudeExplainer:
    """Anthropic-backed explainer.

    Raises `ValueError` from `__init__` if no API key is configured —
    callers should catch and fall back to `NullExplainer`.
    """

    def __init__(self, api_key: str | None = None):
        # Imported here so the module can load even when anthropic isn't
        # installed (e.g. in lightweight test environments).
        import anthropic

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("No Anthropic API key provided")
        self._client = anthropic.Anthropic(api_key=key)
        self._settings = get_settings().llm

    def explain_etf(self, meta: ETFMeta, metrics: dict) -> str:
        user_msg = (
            f"다음 ETF를 한국어로 200~300자 요약해줘.\n\n"
            f"이름: {meta.name}\n"
            f"코드: {meta.ticker}\n"
            f"자산군: {meta.asset_class}\n"
            f"운용사: {meta.issuer}\n"
            f"성과 지표:\n"
            f"  - 1개월 수익률: {_format_pct(metrics.get('total_return_1m'))}\n"
            f"  - 3개월 수익률: {_format_pct(metrics.get('total_return_3m'))}\n"
            f"  - 1년 수익률: {_format_pct(metrics.get('total_return_1y'))}\n"
            f"  - 3년 수익률: {_format_pct(metrics.get('total_return_3y'))}\n"
            f"  - 연환산 변동성: {_format_pct(metrics.get('ann_volatility'))}\n"
            f"  - 최대낙폭(MDD): {_format_pct(metrics.get('max_drawdown'))}\n"
            f"  - Sharpe 비율: {_format_ratio(metrics.get('sharpe'))}\n\n"
            f"요약 형식: 이 ETF가 무엇을 추종하는지(자산군/운용사 기준) → "
            f"위 수치들이 시사하는 위험·수익 특성 → "
            f"마지막 한 문장으로 '투자 판단은 본인 책임' 안전 문구."
        )
        return self._call(user_msg, max_tokens=self._settings.max_tokens_etf)

    def explain_strategy(self, strategy: Strategy, result: BacktestResult) -> str:
        legs_str = "\n".join(
            f"  - {leg.ticker} ({leg.role}): {leg.weight * 100:.1f}%"
            for leg in strategy.legs
        )
        s = result.summary
        user_msg = (
            f"다음 자산배분 전략의 백테스트 결과를 한국어로 350~400자 평가해줘.\n\n"
            f"전략명: {strategy.name}\n"
            f"리밸런스: {strategy.rebalance}\n"
            f"구성:\n{legs_str}\n\n"
            f"백테스트 기간: {result.start} ~ {result.end}\n"
            f"백테스트 결과:\n"
            f"  - 총 수익률: {_format_pct(s.get('total_return'))}\n"
            f"  - 연환산 수익률: {_format_pct(s.get('ann_return'))}\n"
            f"  - 연환산 변동성: {_format_pct(s.get('ann_volatility'))}\n"
            f"  - 최대낙폭(MDD): {_format_pct(s.get('max_drawdown'))}\n"
            f"  - Sharpe 비율: {_format_ratio(s.get('sharpe'))}\n\n"
            f"평가 형식: 전략의 자산배분 의도(예: 위험 분산 / 주식 편중 등) → "
            f"백테스트 수치가 그 의도를 잘 반영했는지 → 어떤 시장 환경에 적합/부적합한지 → "
            f"마지막 한 문장으로 '과거 성과가 미래를 보장하지 않으며 투자 판단은 본인 책임'."
        )
        return self._call(user_msg, max_tokens=self._settings.max_tokens_strategy)

    def _call(self, user_message: str, *, max_tokens: int) -> str:
        try:
            response = self._client.messages.create(
                model=self._settings.model,
                max_tokens=max_tokens,
                thinking={"type": "disabled"},
                output_config={"effort": "low"},
                system=_SYSTEM_PROMPT_KO,
                messages=[{"role": "user", "content": user_message}],
            )
            return next(
                (block.text for block in response.content if block.type == "text"), ""
            ).strip()
        except Exception as exc:  # noqa: BLE001 — surface a friendly message instead of dying
            logger.warning("Claude explain failed: %s: %s", type(exc).__name__, exc)
            return f"(AI 해설을 가져오지 못했습니다 — {type(exc).__name__})"


def get_default_explainer(api_key: str | None = None) -> Explainer:
    """Factory: ClaudeExplainer if a key is available, else NullExplainer."""
    try:
        return ClaudeExplainer(api_key=api_key)
    except ValueError:
        return NullExplainer()
