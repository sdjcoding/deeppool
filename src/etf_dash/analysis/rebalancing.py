"""Forward-looking rebalancing advice on top of the static-weight strategies.

Where `backtest.simulate()` answers "how would this have performed", this module
answers "what should I buy/sell right now to hold the target weights, and when is
the next scheduled rebalance". Two entry points:

- `build_plan()` — given current holdings (or a fresh capital amount), produce a
  concrete set of buy/sell actions (건仓·증액·감액·유지) toward target weights.
- `compare_rebalance_frequencies()` — backtest the same strategy under each
  cadence (weekly/monthly/quarterly/semi_annual/yearly) so the user can see the
  cost/benefit of rebalancing more or less often.

Pure functions only (no I/O); pandas + stdlib, consistent with the rest of
`analysis/`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date

import pandas as pd

from etf_dash.analysis import backtest
from etf_dash.domain.models import (
    RebalanceAction,
    RebalanceFreq,
    RebalancePlan,
    Strategy,
)

DEFAULT_FREQS: tuple[RebalanceFreq, ...] = (
    "weekly",
    "monthly",
    "quarterly",
    "semi_annual",
    "yearly",
)


def next_rebalance_date(freq: RebalanceFreq, from_date: date) -> date | None:
    """First scheduled rebalance date strictly after ``from_date``.

    Mirrors the "first calendar day of each period" rule used by the backtest's
    `_rebalance_dates`. Returns ``None`` for the buy-and-hold ("none") cadence.
    """
    if freq == "none":
        return None
    if freq == "weekly":
        # Next Monday (weekday 0). Always strictly in the future.
        days_ahead = 7 - from_date.weekday()
        return _add_days(from_date, days_ahead if days_ahead > 0 else 7)
    if freq == "monthly":
        return _first_of_month(from_date.year + (from_date.month // 12), (from_date.month % 12) + 1)
    if freq == "quarterly":
        q = (from_date.month - 1) // 3  # 0..3
        nxt = q + 1
        year = from_date.year + (nxt // 4)
        month = (nxt % 4) * 3 + 1
        return _first_of_month(year, month)
    if freq == "semi_annual":
        h = (from_date.month - 1) // 6  # 0 or 1
        if h == 0:
            return date(from_date.year, 7, 1)
        return date(from_date.year + 1, 1, 1)
    if freq == "yearly":
        return date(from_date.year + 1, 1, 1)
    raise ValueError(f"Unknown rebalance frequency: {freq!r}")


def build_plan(
    strategy: Strategy,
    current_values: Mapping[str, float] | None,
    *,
    total_capital: float | None = None,
    latest_prices: Mapping[str, float] | None = None,
    as_of: date | None = None,
    freq: RebalanceFreq | None = None,
    drift_band: float = 0.05,
) -> RebalancePlan:
    """Produce concrete buy/sell actions to move ``strategy`` to target weights.

    Two modes:
      * Initial build — ``current_values`` is ``None``: every leg starts at 0 and
        we deploy ``total_capital`` into the target weights ("건仓").
      * Rebalance — ``current_values`` maps ticker -> current KRW value: we
        compare against target weights of the total and emit 증액/감액/유지.

    ``latest_prices`` (ticker -> price), when given, turns the KRW deltas into
    share counts. ``drift_band`` is the max-drift threshold (fraction) above which
    ``needs_rebalance`` is flagged.
    """
    strategy.validate()
    as_of = as_of or date.today()
    freq = freq or strategy.rebalance

    is_initial = current_values is None
    if is_initial:
        if total_capital is None or total_capital <= 0:
            raise ValueError("total_capital must be positive for an initial build")
        total = float(total_capital)
        values = {leg.ticker: 0.0 for leg in strategy.legs}
    else:
        values = {leg.ticker: float(current_values.get(leg.ticker, 0.0)) for leg in strategy.legs}
        total = sum(values.values())
        if total <= 0:
            raise ValueError("sum of current_values must be positive")

    # First pass: drift drives the overall rebalance decision.
    max_drift = max(
        abs((0.0 if is_initial else values[leg.ticker] / total) - leg.weight)
        for leg in strategy.legs
    )
    needs_rebalance = is_initial or max_drift > drift_band

    actions: list[RebalanceAction] = []
    for leg in strategy.legs:
        current_value = values[leg.ticker]
        current_weight = 0.0 if is_initial else current_value / total
        target_value = total * leg.weight
        delta_value = target_value - current_value

        price = None if latest_prices is None else latest_prices.get(leg.ticker)
        delta_shares = None
        if price:
            delta_shares = delta_value / price

        actions.append(
            RebalanceAction(
                ticker=leg.ticker,
                role=leg.role,
                target_weight=leg.weight,
                current_weight=current_weight,
                current_value=current_value,
                target_value=target_value,
                delta_value=delta_value,
                current_price=price,
                delta_shares=delta_shares,
                action=_action_label(is_initial, needs_rebalance, delta_value),
            )
        )

    note = _build_note(strategy, freq, is_initial, needs_rebalance, max_drift, drift_band)

    return RebalancePlan(
        strategy_id=strategy.id,
        as_of=as_of,
        freq=freq,
        total_value=total,
        actions=tuple(actions),
        max_drift=max_drift,
        needs_rebalance=needs_rebalance,
        next_rebalance_date=next_rebalance_date(freq, as_of),
        note=note,
    )


def compare_rebalance_frequencies(
    strategy: Strategy,
    prices_wide: pd.DataFrame,
    *,
    freqs: Sequence[RebalanceFreq] = DEFAULT_FREQS,
    start: date | None = None,
    end: date | None = None,
    benchmark_prices: pd.Series | None = None,
) -> pd.DataFrame:
    """Backtest ``strategy`` under each cadence and tabulate summary metrics.

    Returns a DataFrame indexed by frequency with the columns from each
    backtest's ``summary`` (ann_return, ann_volatility, sharpe, max_drawdown,
    total_return), so the user can weigh rebalancing more vs. less often.
    """
    rows: dict[str, dict[str, float]] = {}
    for f in freqs:
        variant = dataclasses.replace(strategy, rebalance=f)
        result = backtest.simulate(
            variant,
            prices_wide,
            start=start,
            end=end,
            benchmark_prices=benchmark_prices,
        )
        rows[f] = result.summary
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "freq"
    return df


# --- internal helpers ---------------------------------------------------------


def _action_label(is_initial: bool, needs_rebalance: bool, delta_value: float) -> str:
    """Korean label for a single leg's required move.

    When the portfolio is within band (``needs_rebalance`` False) we mark every
    leg as 유지 so the advice matches the overall hold decision; otherwise the
    sign of the delta dictates 증액 vs 감액.
    """
    if is_initial:
        return "건仓"
    if not needs_rebalance:
        return "유지"
    return "증액" if delta_value > 0 else "감액"


def _build_note(
    strategy: Strategy,
    freq: RebalanceFreq,
    is_initial: bool,
    needs_rebalance: bool,
    max_drift: float,
    drift_band: float,
) -> str:
    if is_initial:
        return (
            f"신규 건仓: '{strategy.name}'의 목표 비중대로 분할 매수하세요. "
            f"이후 {freq} 주기로 점검합니다."
        )
    if needs_rebalance:
        return (
            f"리밸런싱 권장: 최대 드리프트 {max_drift * 100:.1f}%가 허용 밴드 "
            f"{drift_band * 100:.0f}%를 초과했습니다. 아래 매수/매도로 목표 비중을 회복하세요."
        )
    return (
        f"유지 권장: 최대 드리프트 {max_drift * 100:.1f}%로 허용 밴드 "
        f"{drift_band * 100:.0f}% 이내입니다. 다음 정기 점검까지 조정 불필요."
    )


def _add_days(d: date, n: int) -> date:
    from datetime import timedelta

    return d + timedelta(days=n)


def _first_of_month(year: int, month: int) -> date:
    return date(year, month, 1)
