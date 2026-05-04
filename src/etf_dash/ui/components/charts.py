"""Reusable Plotly chart builders.

Each function returns a `plotly.graph_objects.Figure` so callers can mutate
layout further if needed before passing to `st.plotly_chart`.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px


def price_line(prices: pd.Series, title: str = "") -> go.Figure:
    fig = go.Figure(
        data=[
            go.Scatter(
                x=prices.index,
                y=prices.values,
                mode="lines",
                line={"width": 2},
                name="Close",
            )
        ]
    )
    fig.update_layout(
        title=title,
        xaxis_title=None,
        yaxis_title="가격 (KRW)",
        margin={"l": 30, "r": 20, "t": 40 if title else 10, "b": 30},
        hovermode="x unified",
    )
    fig.update_xaxes(rangeslider_visible=False, showspikes=True)
    return fig


def normalized_overlay(prices_wide: pd.DataFrame, title: str = "") -> go.Figure:
    """Overlay several tickers normalized to 1.0 at the first overlapping date."""
    df = prices_wide.dropna(how="any")
    if df.empty:
        return go.Figure()
    norm = df / df.iloc[0]
    fig = go.Figure()
    for col in norm.columns:
        fig.add_trace(
            go.Scatter(x=norm.index, y=norm[col], mode="lines", name=str(col))
        )
    fig.update_layout(
        title=title,
        yaxis_title="정규화 (시작=1.0)",
        margin={"l": 30, "r": 20, "t": 40 if title else 10, "b": 30},
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.15},
    )
    return fig


def equity_curve(
    equity: pd.Series,
    benchmark: pd.Series | None = None,
    *,
    strategy_name: str = "",
    benchmark_name: str = "벤치마크",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=equity.index,
            y=equity.values,
            mode="lines",
            line={"width": 3},
            name=strategy_name or "Strategy",
        )
    )
    if benchmark is not None and not benchmark.empty:
        fig.add_trace(
            go.Scatter(
                x=benchmark.index,
                y=benchmark.values,
                mode="lines",
                line={"width": 2, "dash": "dash"},
                name=benchmark_name,
            )
        )
    fig.update_layout(
        yaxis_title="누적 수익 (시작=1.0)",
        margin={"l": 30, "r": 20, "t": 10, "b": 30},
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.15},
    )
    return fig


def drawdown_chart(dd: pd.Series) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Scatter(
                x=dd.index,
                y=dd.values * 100,
                fill="tozeroy",
                mode="lines",
                line={"color": "#cc3333", "width": 1},
                name="Drawdown",
            )
        ]
    )
    fig.update_layout(
        yaxis_title="Drawdown (%)",
        margin={"l": 30, "r": 20, "t": 10, "b": 30},
        hovermode="x unified",
    )
    return fig


def yearly_returns_bar(yr: pd.Series) -> go.Figure:
    if yr.empty:
        return go.Figure()
    years = yr.index.year.astype(str)
    colors = ["#2c7bb6" if v >= 0 else "#d7191c" for v in yr.values]
    fig = go.Figure(
        data=[
            go.Bar(
                x=years,
                y=yr.values * 100,
                marker_color=colors,
                text=[f"{v*100:+.1f}%" for v in yr.values],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        yaxis_title="연수익률 (%)",
        margin={"l": 30, "r": 20, "t": 10, "b": 30},
    )
    return fig


def correlation_heatmap(corr: pd.DataFrame) -> go.Figure:
    fig = px.imshow(
        corr,
        x=corr.columns,
        y=corr.index,
        color_continuous_scale="RdBu",
        zmin=-1,
        zmax=1,
        text_auto=".2f",
        aspect="auto",
    )
    fig.update_layout(
        margin={"l": 30, "r": 20, "t": 10, "b": 30},
    )
    return fig


def asset_class_pie(by_class: pd.Series) -> go.Figure:
    fig = go.Figure(
        data=[go.Pie(labels=by_class.index.tolist(), values=by_class.values, hole=0.4)]
    )
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 10, "b": 10},
        legend={"orientation": "v"},
    )
    return fig
