"""Render a ReportBundle into a single self-contained HTML page.

No templating dependency: charts come from the existing Plotly builders in
`ui/components/charts.py` via `fig.to_html`, embedded into a hand-written HTML
shell. Plotly JS is pulled from the CDN once (first figure).
"""

from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go

from etf_dash.reporting.report_data import (
    MarketReport,
    PPRebalanceReport,
    ReportBundle,
    StrategyReport,
)
from etf_dash.ui.components import charts

_METRIC_LABELS = {
    "ann_return": "연환산 수익률",
    "ann_volatility": "연환산 변동성",
    "sharpe": "샤프비율",
    "max_drawdown": "최대낙폭",
    "total_return": "총 수익률",
}


class _PlotlyEmbedder:
    """Emits plotly.js from the CDN exactly once, on the first figure."""

    def __init__(self) -> None:
        self._first = True

    def __call__(self, fig: go.Figure, *, height: int = 360) -> str:
        fig.update_layout(height=height)
        include = "cdn" if self._first else False
        self._first = False
        return fig.to_html(full_html=False, include_plotlyjs=include)


def _pct(v: float | None) -> str:
    return "—" if v is None or pd.isna(v) else f"{v * 100:+.2f}%"


def _num(v: float | None) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.2f}"


def _df_html(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "<p class='muted'>데이터 없음</p>"
    return df.to_html(index=False, border=0, classes="tbl", escape=True)


def render_html(bundle: ReportBundle, *, title: str = "DeepPool 분석 리포트") -> str:
    emb = _PlotlyEmbedder()
    parts: list[str] = []
    parts.append(_render_header(bundle, title))
    parts.append(_render_strategies(bundle.strategies, emb))
    if bundle.pp_rebalance is not None:
        parts.append(_render_pp(bundle.pp_rebalance))
    parts.append(_render_market(bundle.market, emb))
    parts.append(_render_footer())
    body = "\n".join(parts)
    return _SHELL.format(title=html.escape(title), body=body)


def _render_header(bundle: ReportBundle, title: str) -> str:
    gen = bundle.generated_at.strftime("%Y-%m-%d %H:%M")
    asof = bundle.data_as_of.strftime("%Y-%m-%d") if bundle.data_as_of else "—"
    return f"""
    <header>
      <h1>{html.escape(title)}</h1>
      <p class="meta">생성: {gen} · 데이터 최신일: {asof}</p>
      <p class="disclaimer">⚠️ 가격 기준(분배락 미반영) · 수수료/세금 0% 가정 ·
         <b>투자 자문이 아닙니다</b>.</p>
    </header>
    """


def _render_strategies(reports: list[StrategyReport], emb: _PlotlyEmbedder) -> str:
    rows = []
    for r in reports:
        if r.error:
            rows.append(
                f"<tr><td>{html.escape(r.strategy.name)}</td>"
                f"<td colspan='5' class='muted'>{html.escape(r.error)}</td></tr>"
            )
            continue
        s = r.summary
        rows.append(
            "<tr>"
            f"<td>{html.escape(r.strategy.name)}</td>"
            f"<td>{_pct(s.get('ann_return'))}</td>"
            f"<td>{_pct(s.get('ann_volatility'))}</td>"
            f"<td>{_num(s.get('sharpe'))}</td>"
            f"<td>{_pct(s.get('max_drawdown'))}</td>"
            f"<td>{_pct(s.get('total_return'))}</td>"
            "</tr>"
        )
    table = (
        "<table class='tbl'><thead><tr>"
        "<th>전략</th><th>연수익</th><th>변동성</th><th>샤프</th><th>MDD</th><th>총수익</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    # Combined equity-curve overlay across strategies that ran successfully.
    chart_html = ""
    curves = {
        r.strategy.name: r.equity_curve
        for r in reports
        if r.equity_curve is not None and not r.equity_curve.empty
    }
    if curves:
        fig = go.Figure()
        for name, curve in curves.items():
            fig.add_trace(go.Scatter(x=curve.index, y=curve.values, mode="lines", name=name))
        fig.update_layout(
            yaxis_title="누적 수익 (시작=1.0)",
            margin={"l": 30, "r": 20, "t": 10, "b": 30},
            hovermode="x unified",
            legend={"orientation": "h", "y": -0.2},
        )
        chart_html = emb(fig, height=420)

    return f"""
    <section>
      <h2>① 전략 백테스트 요약</h2>
      {table}
      {chart_html}
    </section>
    """


def _render_pp(pp: PPRebalanceReport) -> str:
    plan = pp.plan
    banner_cls = "warn" if plan.needs_rebalance else "ok"
    last = pp.last_rebalance.strftime("%Y-%m-%d") if pp.last_rebalance else "—"
    nxt = plan.next_rebalance_date.strftime("%Y-%m-%d") if plan.next_rebalance_date else "—"

    body_rows = []
    for a in plan.actions:
        body_rows.append(
            "<tr>"
            f"<td>{html.escape(a.ticker)}</td>"
            f"<td>{html.escape(a.role)}</td>"
            f"<td>{a.target_weight * 100:.1f}%</td>"
            f"<td>{a.current_weight * 100:.1f}%</td>"
            f"<td>{a.delta_value:+,.0f}</td>"
            f"<td>{html.escape(a.action)}</td>"
            "</tr>"
        )
    table = (
        "<table class='tbl'><thead><tr>"
        "<th>코드</th><th>역할</th><th>목표</th><th>현재</th><th>조정금액(원)</th><th>액션</th>"
        "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"
    )
    return f"""
    <section>
      <h2>② 영구 포트폴리오 리밸런싱 현황</h2>
      <p class="{banner_cls}">{html.escape(plan.note)}</p>
      <p class="meta">마지막 정기 리밸런싱: {last} · 다음 예정: {nxt} ·
         최대 드리프트: {plan.max_drift * 100:.1f}% · 기준 평가액: {plan.total_value:,.0f}원</p>
      {table}
    </section>
    """


def _render_market(market: MarketReport, emb: _PlotlyEmbedder) -> str:
    pie_html = ""
    if not market.asset_class_counts.empty:
        pie_html = emb(charts.asset_class_pie(market.asset_class_counts), height=380)

    heat_html = ""
    if not market.corr.empty:
        heat_html = emb(charts.correlation_heatmap(market.corr), height=420)

    def _movers(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
        if df.empty:
            return df
        out = df.copy()
        if "change_rate" in out.columns:
            out = out.rename(columns={"ticker": "코드", "change_rate": "등락(%)"})
        elif "total_flow" in out.columns:
            out = out.rename(columns={"ticker": "코드", "total_flow": "추정유출입(억원)"})
        return out

    return f"""
    <section>
      <h2>③ 시장 스냅샷</h2>
      <div class="grid2">
        <div><h3>자산군 분포</h3>{pie_html or "<p class='muted'>데이터 없음</p>"}</div>
        <div><h3>핵심 ETF 상관관계</h3>{heat_html or "<p class='muted'>데이터 없음</p>"}</div>
      </div>
      <div class="grid2">
        <div><h3>오늘 상승 Top</h3>{_df_html(_movers(market.top_gainers, "코드"))}</div>
        <div><h3>오늘 하락 Top</h3>{_df_html(_movers(market.top_losers, "코드"))}</div>
      </div>
      <div class="grid2">
        <div><h3>자금 유입 추정 Top</h3>{_df_html(_movers(market.inflows, "코드"))}</div>
        <div><h3>자금 유출 추정 Top</h3>{_df_html(_movers(market.outflows, "코드"))}</div>
      </div>
    </section>
    """


def _render_footer() -> str:
    return """
    <footer>
      <p class="muted">DeepPool · KRX ETF 자산배분 분석 · 개인용 비공개 리포트</p>
    </footer>
    """


_SHELL = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>{title}</title>
<style>
  :root {{ --bg:#0f1419; --card:#1a2029; --fg:#e6e6e6; --muted:#8a94a6; --accent:#4a9eff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;
         line-height:1.5; }}
  header, section, footer {{ max-width:1080px; margin:0 auto; padding:20px 24px; }}
  header {{ border-bottom:1px solid #2a323d; }}
  h1 {{ margin:0 0 4px; font-size:1.6rem; }}
  h2 {{ margin:8px 0 16px; font-size:1.25rem; color:var(--accent); }}
  h3 {{ font-size:1rem; color:var(--muted); margin:12px 0 6px; }}
  section {{ border-bottom:1px solid #2a323d; }}
  .meta {{ color:var(--muted); font-size:.9rem; margin:2px 0; }}
  .disclaimer {{ color:#e0b341; font-size:.85rem; }}
  .muted {{ color:var(--muted); }}
  .ok {{ color:#46c98b; font-weight:600; }}
  .warn {{ color:#e0b341; font-weight:600; }}
  table.tbl {{ width:100%; border-collapse:collapse; margin:8px 0 16px; font-size:.9rem; }}
  table.tbl th, table.tbl td {{ text-align:right; padding:6px 10px;
    border-bottom:1px solid #2a323d; }}
  table.tbl th:first-child, table.tbl td:first-child,
  table.tbl th:nth-child(2), table.tbl td:nth-child(2) {{ text-align:left; }}
  table.tbl thead th {{ color:var(--muted); font-weight:600; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  @media (max-width:760px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
{body}
</body>
</html>
"""
