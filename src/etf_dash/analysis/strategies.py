"""Load Strategy templates from a YAML file."""

from __future__ import annotations

from pathlib import Path

import yaml

from etf_dash.domain.models import Strategy, StrategyLeg


def load_strategies(path: Path) -> list[Strategy]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"strategies file must be a YAML list, got {type(raw).__name__}")

    strategies: list[Strategy] = []
    for entry in raw:
        legs = tuple(
            StrategyLeg(
                ticker=str(leg["ticker"]),
                weight=float(leg["weight"]),
                role=str(leg.get("role", "")),
            )
            for leg in entry["legs"]
        )
        strategy = Strategy(
            id=str(entry["id"]),
            name=str(entry["name"]),
            description=str(entry.get("description", "")),
            legs=legs,
            rebalance=str(entry.get("rebalance", "quarterly")),  # type: ignore[arg-type]
            benchmark_ticker=(
                str(entry["benchmark_ticker"]) if entry.get("benchmark_ticker") else None
            ),
        )
        strategy.validate()
        strategies.append(strategy)
    return strategies
