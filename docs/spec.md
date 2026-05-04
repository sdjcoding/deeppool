# DeepPool — KRX ETF 분석 대시보드 (MVP)

## Context

한국거래소(KRX)에 상장된 ETF(약 800개+)를 한 곳에서 탐색·분석하고, 검증된 자산배분 전략(All Weather, 60/40 등)을 KRX ETF로 매핑해 보여주는 **개인용 Streamlit 대시보드**를 그린필드로 구축한다.

- 사용자: 개인 투자자 1인 (인증/멀티유저 없음)
- 출발점: 빈 디렉토리 (`/Users/dj-mbpm3max/Library/CloudStorage/Dropbox/Claude Code Dropbox/DeepPool(Project DJ Perma)/`)
- MVP 4대 기능: **(A)** ETF 스크리닝 · **(B)** 개별 ETF 상세 분석 · **(E)** 전략 템플릿 시뮬레이션 · **(F)** 시장/매크로 분석
- 명시적으로 제외: 사용자 정의 포트폴리오 빌더/최적화, LLM 통합, 해외 ETF, 사용자 인증
- 확장성은 **인터페이스 추상화에서만** 고려 (DataProvider, llm_explainer stub). 두 번째 구현체는 만들지 않는다.

---

## 기술 스택

| 영역 | 선택 | 이유 |
|---|---|---|
| 패키지 매니저 | `uv` | 빠르고 lockfile 관리 일원화 |
| UI | Streamlit (multipage) | 분석 코드와 동일 Python 스택, MVP 속도 최우선 |
| 데이터 수집 | `pykrx` (주력) + `FinanceDataReader` (배당 보조) | 둘 다 무료/안정적. KRX 공식 데이터 |
| 저장 | SQLite (메타·시계열) + Parquet (보유종목 스냅샷) | ORM 없이 raw SQL. 추후 Postgres 마이그레이션 가능 |
| 차트 | Plotly | Streamlit 궁합·줌/range slider 무료 |
| 통계/백테스트 | numpy + pandas 직접 구현 | 정적 비중 + 주기 리밸런스라 vectorbt/backtrader 불필요 |
| 설정 | pydantic-settings + PyYAML | 전략 정의를 YAML로 외부화 |
| 테스트 | pytest (+ 골든 데이터) | metrics/backtest는 회귀 버그 자주 발생 |

---

## 디렉토리 구조

```
DeepPool/
├── pyproject.toml
├── README.md
├── .env.example
├── data/                          # gitignore. 캐시
│   ├── cache.db                   # SQLite
│   └── holdings/{ticker}/{yyyymmdd}.parquet
├── config/
│   ├── strategies.yaml            # 전략 템플릿 정의
│   └── settings.yaml
├── src/etf_dash/
│   ├── config.py
│   ├── domain/
│   │   ├── models.py              # ETFMeta, Strategy 등 dataclass
│   │   └── schemas.py             # DataFrame 컬럼 상수
│   ├── providers/
│   │   ├── base.py                # DataProvider Protocol
│   │   ├── pykrx_provider.py      # 주력
│   │   └── fdr_provider.py        # 배당 등 보조
│   ├── repository/
│   │   ├── db.py                  # SQLite 연결/DDL
│   │   └── etf_repository.py      # CRUD + 캐시 진입점
│   ├── ingest/
│   │   ├── __main__.py            # `python -m etf_dash.ingest`
│   │   └── jobs.py                # ingest_meta/prices/dividends/holdings
│   ├── analysis/
│   │   ├── metrics.py             # returns, vol, MDD, Sharpe, tracking error
│   │   ├── correlation.py
│   │   ├── flows.py               # AUM/순자산 변화 → 자금유입 추정
│   │   ├── backtest.py            # 정적 비중 + 주기 리밸런스
│   │   ├── strategies.py          # YAML → Strategy 객체
│   │   └── llm_explainer.py       # 빈 stub (Protocol만)
│   └── ui/
│       ├── app.py                 # 홈
│       ├── pages/
│       │   ├── 1_Screener.py      # 기능 A
│       │   ├── 2_ETF_Detail.py    # 기능 B
│       │   ├── 3_Strategies.py    # 기능 E
│       │   └── 4_Market.py        # 기능 F
│       └── components/
│           ├── filters.py
│           ├── charts.py
│           └── tables.py
└── tests/
    ├── unit/
    │   ├── test_metrics.py
    │   ├── test_backtest.py
    │   └── test_strategies_yaml.py
    └── integration/
        └── test_pykrx_smoke.py    # @pytest.mark.slow
```

**의존 방향(단방향):** `providers → repository → analysis → ui`. UI는 provider를 직접 호출하지 않는다 (캐시 미스 시 "ingest 실행 필요" 안내).

---

## 데이터 모델

### SQLite

```sql
CREATE TABLE etf_meta (
  ticker TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  issuer TEXT,                  -- KODEX/TIGER/ACE...
  asset_class TEXT,             -- equity/bond/commodity/multi/alt
  region TEXT,                  -- KR (확장 위해 컬럼만)
  sector TEXT,
  benchmark TEXT,
  inception_date DATE,
  expense_ratio REAL,
  listed_shares INTEGER,
  is_active INTEGER DEFAULT 1,  -- 상장폐지 시 0
  updated_at TIMESTAMP
);

CREATE TABLE etf_price (
  ticker TEXT, date DATE,
  open REAL, high REAL, low REAL, close REAL,
  volume INTEGER, value REAL,
  nav REAL, aum REAL,
  shares_outstanding INTEGER,
  PRIMARY KEY (ticker, date)
);
CREATE INDEX idx_price_date ON etf_price(date);

CREATE TABLE etf_dividend (
  ticker TEXT, ex_date DATE, amount REAL,
  PRIMARY KEY (ticker, ex_date)
);

CREATE TABLE ingest_log (
  job TEXT, ticker TEXT, run_at TIMESTAMP,
  status TEXT, message TEXT
);
```

### 보유종목 (Parquet)

```
data/holdings/{ticker}/{yyyymmdd}.parquet
컬럼: constituent_ticker, constituent_name, shares, weight_pct, value_krw
```

### 전략 정의 (YAML 예시)

```yaml
- id: all_weather_kr
  name: All Weather (KR 변형)
  description: "..."
  rebalance: quarterly      # none|monthly|quarterly|yearly
  benchmark_ticker: "069500"
  legs:
    - { ticker: "069500", weight: 0.30, role: "주식 코어" }
    - { ticker: "148070", weight: 0.40, role: "장기 국채" }
    - { ticker: "136340", weight: 0.15, role: "중기 국채" }
    - { ticker: "132030", weight: 0.075, role: "금" }
    - { ticker: "261220", weight: 0.075, role: "원자재" }
```

수록할 초기 전략(최소 3개): All Weather, 60/40, 코어-새틀라이트.

---

## 핵심 인터페이스

```python
# providers/base.py
class DataProvider(Protocol):
    name: str
    def list_etfs(self, as_of: date) -> pd.DataFrame: ...
    def get_ohlcv(self, ticker: str, start: date, end: date) -> pd.DataFrame: ...
    def get_aum_nav(self, ticker: str, start: date, end: date) -> pd.DataFrame: ...
    def get_holdings(self, ticker: str, as_of: date) -> pd.DataFrame | None: ...

# repository/etf_repository.py
class ETFRepository:
    def list_etfs(self, filters: dict | None = None) -> pd.DataFrame
    def get_etf(self, ticker: str) -> ETFMeta | None
    def get_prices(self, tickers: list[str], start, end) -> pd.DataFrame
    def get_holdings(self, ticker: str, as_of: date | None = None)
    def upsert_etfs(self, df) / upsert_prices(self, df) / write_holdings(...)
    def last_price_date(self, ticker: str) -> date | None    # 증분 갱신용

# analysis/metrics.py — 순수 함수
total_return / annualized_volatility / max_drawdown / sharpe_ratio / tracking_error

# analysis/strategies.py
@dataclass(frozen=True)
class StrategyLeg: ticker, weight, role
@dataclass(frozen=True)
class Strategy: id, name, description, legs, rebalance, benchmark_ticker
def load_strategies(path) -> list[Strategy]

# analysis/backtest.py
def simulate(strategy, prices, start, end, initial=1e7) -> BacktestResult
# BacktestResult: equity_curve, metrics(dict), weights_over_time

# analysis/llm_explainer.py — Protocol만, NullExplainer만 구현
```

---

## Streamlit 페이지 매핑

| 파일 | 기능 | 핵심 |
|---|---|---|
| `app.py` | 홈 | 캐시 마지막 갱신일, 시장 요약 카드, 가이드 |
| `1_Screener.py` | **A** | 사이드바 필터(자산군/섹터/AUM/총보수/배당률/이슈어), 정렬 표, 다중 선택 시 비교 오버레이 |
| `2_ETF_Detail.py` | **B** | URL `?ticker=XXX`. 메타 → 가격(1M/3M/1Y/3Y/MAX) → 지표 표 → 보유종목 Top 10 → 배당 이력 → 비용 |
| `3_Strategies.py` | **E** | 전략 카드 → 설명·구성·equity curve·drawdown·연도별 수익률·벤치마크 비교 |
| `4_Market.py` | **F** | 자산군/섹터별 트렌드, 자금유입 Top/Bottom, 상관관계 히트맵 (사용자 다중 선택) |

**캐싱:** `@st.cache_data(ttl=3600)` on repository reads, `@st.cache_resource` on `ETFRepository` 인스턴스. 페이지 간 ticker 전달은 `st.query_params`.

---

## Ingest 스크립트

`python -m etf_dash.ingest [--job all|meta|prices|holdings|dividends] [--full] [--ticker XXX] [--validate]`

| Job | 주기 | 갱신 방식 | 소스 |
|---|---|---|---|
| meta | 일 1회 | 전체 덮어쓰기 | pykrx `get_etf_ticker_list/name` (+ 필요 시 KRX 상세 보강) |
| prices | 일 1회 (장마감 후) | **증분**: `last_price_date+1`부터 today | pykrx `get_etf_ohlcv_by_date` per ticker |
| dividends | 주 1회 | 최근 1년 갱신 | FDR (pykrx 미지원) |
| holdings | 주 1회 | 신규 스냅샷, 이전 보존 | pykrx `get_etf_portfolio_deposit_file` (실패는 skip + 로그) |

**Rate limit 방어:** ticker 순회 시 `time.sleep(0.2)` + `tenacity` 재시도. 800개 prices 증분 ≈ 5–10분 예상.

**스케줄링은 OS에 위임** (cron/launchd 예시 README에).

---

## 중요한 의사결정 / 명시적 제외

1. **운용사(KODEX/TIGER) 사이트 크롤링 ❌** — `pykrx.get_etf_portfolio_deposit_file`이 KRX 공식 PDF를 파싱하므로 충분. `issuer_scraper.py`는 만들지 않음.
2. **vectorbt/backtrader/quantstats ❌** — 정적 비중 + 주기 리밸런스는 pandas 50줄로 구현.
3. **SQLAlchemy ❌** — raw SQL로 충분. Postgres 마이그레이션 시 도입.
4. **Pandera 보류** — 통증이 생기면 그때.
5. **두 번째 DataProvider 구현체 ❌ (MVP)** — `PykrxProvider` 1개. FDR은 배당 메서드 한정 호출.
6. **수익률 정의 명시** — MVP는 "**가격 기준 수익률**" (분배락 보정 X). UI에 명시 + 분배금은 별도 표로. 풀 total return adjustment는 오해 위험으로 후속 단계.
7. **상장폐지 ETF** — 메타에 `is_active=0` 플래그만 두고 시계열은 보존 (백테스트 무결성).

---

## 위험요소 (사전 인지)

- **pykrx는 KRX 사이트 스크레이핑 기반** — KRX UI 변경 시 깨짐. 라이브러리 버전 lock + ingest 실패 알림.
- **NAV vs Close 차이** — 추적오차는 NAV 기반. pykrx OHLCV 함수의 NAV 컬럼 제공 여부를 부트스트랩 시 실측 확인.
- **총보수(expense_ratio) 출처 미확인** — pykrx 직접 제공 여부 확인, 안되면 KRX 상세검색 페이지 별도 스크레이핑 필요. **부트스트랩 첫 단계에서 결론 내림**.
- **액티브/해외자산 ETF는 PDF 비공개일 수 있음** — `get_holdings` None 반환 시 "보유종목 비공개"로 표시.
- **상관관계 히트맵 전체 ETF 로드 금지** — 사용자가 선택한 다중 ETF만.
- **백테스트 시작일 자동 클램프** — `max(leg.inception_date)` 이후로. UI에 가용 구간 표시 필수.

---

## 단계별 구현 순서 (참고)

1. **Bootstrap**: pyproject.toml(uv), 디렉토리 스캐폴드, config/settings.yaml, 1개 ETF(069500)로 pykrx 함수 4종 실측 → NAV·총보수·holdings 가용성 확정
2. **Repository + SQLite DDL** + ETFRepository 기본 CRUD
3. **PykrxProvider** 구현 + **ingest meta/prices** 동작
4. **analysis/metrics + backtest** + 단위 테스트(골든 데이터)
5. **strategies.yaml** + 초기 3개 전략 + `load_strategies`
6. **Streamlit `app.py` + Screener (A)** — 가장 단순한 페이지로 시작
7. **ETF Detail (B)** — Plotly 차트, 지표, holdings
8. **Strategies (E)** — 백테스트 결과 시각화
9. **Market (F)** — 상관관계, 자금유입
10. **ingest dividends/holdings** + 주간 잡 셋업
11. **README** (실행/스케줄 안내)

---

## Critical Files

- `src/etf_dash/providers/pykrx_provider.py` — pykrx 호출 전부 캡슐화
- `src/etf_dash/repository/etf_repository.py` — UI/analysis가 데이터에 닿는 유일 경로
- `src/etf_dash/analysis/metrics.py` — 모든 지표의 단일 출처. 테스트 1순위
- `src/etf_dash/analysis/backtest.py` — 시뮬레이션 신뢰성의 핵심
- `config/strategies.yaml` — 전략 추가/조정의 확장점

---

## Verification

- `pytest tests/unit/` — metrics/backtest/strategies 전부 통과
- `python -m etf_dash.ingest --job meta` 후 SQLite에 800개+ 행 존재
- `python -m etf_dash.ingest --job prices --ticker 069500 --full` 후 5년치 일봉 적재 확인
- `python -m etf_dash.ingest --validate` — NaN/음수/날짜 갭 리포트 깨끗
- `streamlit run src/etf_dash/ui/app.py` — 4개 페이지 진입, Screener에서 069500 클릭 → Detail에서 차트·지표·보유종목 렌더링
- 알려진 ETF(예: 069500 KODEX 200) 1년 수익률을 운용사 공시와 스폿 체크 (±0.5%p 허용)
- 60/40 전략 백테스트 결과의 equity curve가 단조 증가/감소 구간이 시장 흐름과 일치하는지 시각 검증
