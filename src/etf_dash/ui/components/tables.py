"""DataFrame formatting helpers for st.dataframe."""

from __future__ import annotations

import pandas as pd

KRW_BILLIONS = "MarCap (억원)"


def format_screener_table(meta: pd.DataFrame, snap: pd.DataFrame) -> pd.DataFrame:
    """Join meta with the latest snapshot per ticker and produce a display frame."""
    if meta.empty:
        return meta

    if not snap.empty:
        latest = snap.sort_values("snap_date").groupby("ticker").tail(1)
        joined = meta.merge(
            latest[["ticker", "price", "nav", "mar_cap", "earning_rate", "change_rate"]],
            on="ticker",
            how="left",
        )
    else:
        joined = meta.assign(price=None, nav=None, mar_cap=None, earning_rate=None, change_rate=None)

    display = joined[
        [
            "ticker",
            "name",
            "asset_class",
            "issuer",
            "price",
            "nav",
            "mar_cap",
            "change_rate",
            "earning_rate",
        ]
    ].rename(
        columns={
            "ticker": "코드",
            "name": "ETF 이름",
            "asset_class": "자산군",
            "issuer": "운용사",
            "price": "가격",
            "nav": "NAV",
            "mar_cap": KRW_BILLIONS,
            "change_rate": "당일변동(%)",
            "earning_rate": "1Y수익률(%)",
        }
    )
    return display


def format_metrics_table(summary: dict[str, float]) -> pd.DataFrame:
    """Convert a metrics summary dict into a tidy 2-column display frame."""
    label_map = {
        "total_return_1m": "1개월 수익률",
        "total_return_3m": "3개월 수익률",
        "total_return_1y": "1년 수익률",
        "total_return_3y": "3년 수익률",
        "ann_return": "연환산 수익률",
        "ann_volatility": "연환산 변동성",
        "max_drawdown": "최대낙폭 (MDD)",
        "sharpe": "샤프비율",
        "total_return": "총 수익률",
    }
    rows = []
    for key, value in summary.items():
        label = label_map.get(key, key)
        if key == "sharpe":
            text = f"{value:.2f}" if not _is_nan(value) else "—"
        else:
            text = f"{value*100:+.2f}%" if not _is_nan(value) else "—"
        rows.append({"지표": label, "값": text})
    return pd.DataFrame(rows)


def _is_nan(x) -> bool:
    try:
        return x != x  # noqa: PLR0124
    except Exception:  # noqa: BLE001
        return True
