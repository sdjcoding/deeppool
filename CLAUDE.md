# CLAUDE.md — Agent context for DeepPool

This file gives Claude Code (CLI / web / IDE) durable context about the project so it can pick up work in any environment without losing decisions or conventions.

## What this project is

**DeepPool** is a personal Streamlit dashboard for analyzing KRX-listed ETFs (~1,099) and backtesting curated asset-allocation strategies. Single-user, run locally or behind a tunnel.

- Primary user: SHEN DONGJIE (`sdjcoding` on GitHub). Communicate in **Korean** by default. Code/identifiers stay in English.
- Original approved plan/spec: [`docs/spec.md`](docs/spec.md). Read it before making structural changes.
- Operations / how to run: [`docs/operations.md`](docs/operations.md).
- Data source notes: [`docs/data-sources.md`](docs/data-sources.md).

## MVP scope (locked — don't expand without user OK)

Included:
- **A** ETF Screener · **B** ETF Detail · **E** Strategy backtest templates · **F** Market/macro analysis
- **G** Rebalancing advisor (added on user request 2026-06) — periodic 건仓/조仓 advice for
  fixed-target strategies (incl. Permanent Portfolio). NOT an optimizer; see exclusion below.

**Explicitly excluded** (don't add unprompted, even if "easy"):
- User-defined portfolio builder / Markowitz / risk-parity optimization. (The rebalancing
  advisor only nudges holdings back to a strategy's *fixed* target weights — it never *chooses*
  weights, so it stays on the allowed side of this line.)
- LLM-generated narratives (interface stub `analysis/llm_explainer.py` only — `NullExplainer` lives there)
- Overseas ETFs (US/EU/JP). `region` column reserved but only KR populated.
- User authentication beyond the single shared password gate
- Holdings/expense_ratio/inception_date/benchmark columns (deferred — see `docs/data-sources.md`)
- Dividend-adjusted total returns (UI is explicit: returns are **price-based**)

## Critical decisions (don't reverse without re-confirming)

1. **Data source = FinanceDataReader (FDR), not pykrx.**
   `data.krx.co.kr` returned `LOGOUT` (HTTP 400) for bot calls during bootstrap (2026-05); session-cookie warm-up didn't help. Don't try pykrx again unless the user explicitly says it's been worked around or KRX OPEN API has been registered.

2. **Issuer is inferred from name prefix** (KODEX→삼성, TIGER→미래에셋, RISE→KB, ACE→한국투자, PLUS→한화 etc). Map lives in `src/etf_dash/domain/schemas.py::_ISSUER_PREFIXES`. ~96.5% of ETFs map cleanly; the rest fall to `기타`.

3. **No SQLAlchemy / vectorbt / backtrader / Pandera / quantstats.** All deliberately rejected; raw SQL + pandas-only is the rule. Add only if the user asks for it.

4. **Daily snapshots accumulate AUM/NAV history** (we save `fdr.StockListing('ETF/KR')` per day to `etf_snapshot`). This is our homegrown replacement for the historical NAV/AUM time series pykrx would have provided.

5. **Password gate is mandatory** (`src/etf_dash/ui/auth.py::require_password`). The app refuses to start without `app_password` set in `.streamlit/secrets.toml` or `APP_PASSWORD` env var. `secrets.toml` is gitignored.

## Repository layout

```
src/etf_dash/
├── domain/         # dataclasses + column constants + Category/Issuer maps (no I/O)
├── providers/      # DataProvider Protocol + FDRProvider (only impl)
├── repository/     # SQLite (raw sqlite3) — etf_meta, etf_price, etf_snapshot, ingest_log
├── ingest/         # CLI: `python -m etf_dash.ingest --job all|meta|prices|validate`
├── analysis/       # metrics · backtest · correlation · flows · strategies · rebalancing · llm_explainer (stub)
├── reporting/      # static public HTML report (report_data + render + __main__) — sink layer like ui/
└── ui/             # Streamlit: app.py + pages/ (5) + components/ + auth.py
config/
├── settings.yaml   # cache paths, ingest tunables
└── strategies.yaml # 4 templates: all_weather_kr, classic_60_40, core_satellite_kr, permanent_portfolio_kr
tests/unit/         # 50 golden-data tests (metrics + backtest + rebalancing + yaml)
data/               # gitignored. SQLite + future Parquet holdings cache
```

**Dependency direction (one-way):** `providers → repository → analysis → ui`. UI never calls a provider directly; cache misses surface as "run ingest" guidance.

## Conventions

- **Returns** in `analysis/metrics.py` are simple, not log. Annualization factor 252.
- **Dates** in SQLite are ISO strings (`YYYY-MM-DD`) for portability.
- **`MarCap`** unit is **억원** (100M KRW), as FDR returns it. Don't reinterpret.
- **`change_rate`** in snapshots is in **percent** (e.g. `2.5` = +2.5%). Daily `change` in `etf_price` is a **fraction** (e.g. `0.025`).
- **Errors during ingest** go to `ingest_log` table, not crash. Failures per-ticker are logged + skipped.

## How to run / test

```bash
# Install deps (uv required — install via `curl -LsSf https://astral.sh/uv/install.sh | sh`)
uv sync --extra dev

# Bootstrap data (first time, ~10s for meta, ~1-2h for full price history)
uv run python -m etf_dash.ingest --job meta
uv run python -m etf_dash.ingest --job prices --full

# Tests
uv run pytest tests/unit/ -v        # 21 should pass

# Run dashboard (needs .streamlit/secrets.toml with app_password)
./scripts/run_dashboard.sh
```

External access via ngrok: see `docs/operations.md`.

## What's done vs what remains

**Done (MVP shipped):**
- Bootstrap, GitHub repo, FDR pivot
- Domain + repository + ingest CLI (1099 ETFs ingested)
- Analysis layer (metrics + backtest + correlation + flows + rebalancing) with 50 unit tests
- 4 strategy templates with real-data validation (incl. Permanent Portfolio `permanent_portfolio_kr`)
- Rebalancing advisor (`analysis/rebalancing.py`): build_plan(건仓/조仓 buy-sell sizing),
  cadence comparison (weekly/monthly/quarterly/semi_annual/yearly), drift-band & Browne 35/15
  weight-band triggers. UI page `5_♻️_Rebalancing.py`.
- Streamlit UI: 5 pages + components + password gate
- Public static report (`reporting/`): 전략+리밸런싱+시장 단일 HTML, 무작위 슬러그(noindex),
  로컬 생성 후 gh-pages 게시. CLI `python -m etf_dash.reporting`, scripts
  `build_report.sh`/`publish_report.sh`. 슬러그는 gitignored `config/report.local.yaml`.
- Helper scripts (`scripts/run_dashboard.sh`, `scripts/run_tunnel.sh`)
- Docs: README, `docs/spec.md`, `docs/data-sources.md`, `docs/operations.md`

**Likely next** (only on user request):
- Price ingest for `153130` (KODEX 단기채권, Permanent Portfolio cash leg — new in 2026-06)
- Full price ingest for all 1099 ETFs (currently only ~8 strategy tickers have 5y history)
- Set up daily refresh via launchd/cron
- Naver Finance scraper for holdings / expense_ratio (deferred)
- LLM explainer impl (Claude API) for ETF/strategy narrative
- Tailscale alternative to ngrok (more secure for personal-only access)

## Working-style preferences

- Keep replies in Korean; code in English.
- The user picks options from menus when given trade-offs — present 2–4 well-explained choices when there's a real decision.
- Don't re-introduce excluded items. Don't suggest premature abstractions.
- Commit at meaningful milestones with descriptive messages; push after each.
- The user is comfortable with concise CLI walk-throughs.
