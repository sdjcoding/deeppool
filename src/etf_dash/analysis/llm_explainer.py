"""LLM explanation interface — empty stub for the MVP.

Future implementations will provide natural-language summaries of an ETF or
strategy backtest. For now, the abstract interface and a NullExplainer let
the UI code call `.explain_*` without conditional checks.
"""

from __future__ import annotations

from typing import Protocol

from etf_dash.analysis.backtest import BacktestResult
from etf_dash.domain.models import ETFMeta, Strategy


class Explainer(Protocol):
    def explain_etf(self, meta: ETFMeta, metrics: dict) -> str: ...
    def explain_strategy(self, strategy: Strategy, result: BacktestResult) -> str: ...


class NullExplainer:
    """No-op implementation — used until a real LLM provider is wired in."""

    def explain_etf(self, meta: ETFMeta, metrics: dict) -> str:  # noqa: ARG002
        return ""

    def explain_strategy(self, strategy: Strategy, result: BacktestResult) -> str:  # noqa: ARG002
        return ""
