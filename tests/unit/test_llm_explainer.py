"""Unit tests for the LLM explainer module.

Anthropic API calls are mocked — these tests never hit the network.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from etf_dash.analysis.backtest import BacktestResult
from etf_dash.analysis.llm_explainer import (
    ClaudeExplainer,
    NullExplainer,
    get_default_explainer,
)
from etf_dash.domain.models import ETFMeta, Strategy, StrategyLeg


@pytest.fixture
def sample_meta():
    return ETFMeta(
        ticker="069500",
        name="KODEX 200",
        category=1,
        asset_class="국내주식 (시장지수)",
        issuer="삼성자산운용",
    )


@pytest.fixture
def sample_metrics():
    return {
        "total_return_1m": 0.025,
        "total_return_3m": 0.061,
        "total_return_1y": 0.182,
        "total_return_3y": 0.34,
        "ann_volatility": 0.158,
        "max_drawdown": -0.198,
        "sharpe": 1.05,
    }


@pytest.fixture
def sample_strategy():
    return Strategy(
        id="test_60_40",
        name="60/40 Test",
        description="",
        legs=(
            StrategyLeg("069500", 0.6, "주식"),
            StrategyLeg("273130", 0.4, "채권"),
        ),
        rebalance="quarterly",
    )


@pytest.fixture
def sample_backtest_result():
    idx = pd.date_range("2021-01-01", "2025-12-31", freq="B")
    equity = pd.Series([1.0 + i * 0.0001 for i in range(len(idx))], index=idx)
    weights = pd.DataFrame(
        {"069500": [0.6] * len(idx), "273130": [0.4] * len(idx)}, index=idx
    )
    return BacktestResult(
        strategy_id="test_60_40",
        equity_curve=equity,
        weights_over_time=weights,
        summary={
            "total_return": 0.94,
            "ann_return": 0.14,
            "ann_volatility": 0.15,
            "max_drawdown": -0.25,
            "sharpe": 0.99,
        },
        start=date(2021, 1, 1),
        end=date(2025, 12, 31),
        initial=1_000_000,
    )


# --- NullExplainer -----------------------------------------------------------


def test_null_explainer_returns_empty(sample_meta, sample_metrics):
    e = NullExplainer()
    assert e.explain_etf(sample_meta, sample_metrics) == ""


def test_null_explainer_strategy_returns_empty(sample_strategy, sample_backtest_result):
    e = NullExplainer()
    assert e.explain_strategy(sample_strategy, sample_backtest_result) == ""


# --- get_default_explainer fallback ------------------------------------------


def test_default_explainer_returns_null_when_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    e = get_default_explainer(api_key=None)
    assert isinstance(e, NullExplainer)


def test_default_explainer_returns_claude_when_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    e = get_default_explainer()
    assert isinstance(e, ClaudeExplainer)


# --- ClaudeExplainer (mocked SDK) --------------------------------------------


def _make_mock_response(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_claude_explainer_etf_calls_anthropic_with_expected_params(
    monkeypatch, sample_meta, sample_metrics
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MockAnthropic.return_value
        mock_client.messages.create.return_value = _make_mock_response(
            "KODEX 200은 코스피 200을 추종합니다... 투자 판단은 본인 책임입니다."
        )
        explainer = ClaudeExplainer()
        result = explainer.explain_etf(sample_meta, sample_metrics)

    assert "KODEX 200" in result
    assert mock_client.messages.create.called
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["thinking"] == {"type": "disabled"}
    assert call_kwargs["output_config"] == {"effort": "low"}
    user_msg = call_kwargs["messages"][0]["content"]
    assert "069500" in user_msg
    assert "+18.20%" in user_msg  # 1y return formatted
    assert "삼성자산운용" in user_msg


def test_claude_explainer_strategy_includes_legs_in_prompt(
    monkeypatch, sample_strategy, sample_backtest_result
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MockAnthropic.return_value
        mock_client.messages.create.return_value = _make_mock_response("60/40 전략은...")
        explainer = ClaudeExplainer()
        explainer.explain_strategy(sample_strategy, sample_backtest_result)

    user_msg = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "069500" in user_msg
    assert "273130" in user_msg
    assert "60.0%" in user_msg
    assert "quarterly" in user_msg


def test_claude_explainer_returns_friendly_string_on_api_error(
    monkeypatch, sample_meta, sample_metrics
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MockAnthropic.return_value
        mock_client.messages.create.side_effect = RuntimeError("boom")
        explainer = ClaudeExplainer()
        result = explainer.explain_etf(sample_meta, sample_metrics)

    assert "AI 해설을 가져오지 못했습니다" in result
    assert "RuntimeError" in result


def test_claude_explainer_init_raises_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="No Anthropic API key"):
        ClaudeExplainer(api_key=None)
