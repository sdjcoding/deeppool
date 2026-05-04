"""Verify the bundled strategies.yaml loads cleanly and is internally consistent."""

from __future__ import annotations

from pathlib import Path

import pytest

from etf_dash.analysis.strategies import load_strategies

STRATEGIES_YAML = Path(__file__).resolve().parents[2] / "config" / "strategies.yaml"


@pytest.fixture(scope="module")
def strategies():
    return load_strategies(STRATEGIES_YAML)


def test_at_least_three_strategies(strategies):
    assert len(strategies) >= 3


def test_unique_ids(strategies):
    ids = [s.id for s in strategies]
    assert len(ids) == len(set(ids))


def test_each_strategy_validates(strategies):
    for s in strategies:
        s.validate()  # raises on bad weights / dupes


def test_known_strategies_present(strategies):
    ids = {s.id for s in strategies}
    assert {"all_weather_kr", "classic_60_40", "core_satellite_kr"} <= ids


def test_no_negative_weights(strategies):
    for s in strategies:
        for leg in s.legs:
            assert leg.weight > 0
