# DeepPool

KRX 상장 ETF를 한 곳에서 탐색·분석하고, 검증된 자산배분 전략(All Weather, 60/40, 코어-새틀라이트)을 KRX ETF로 매핑해 보여주는 **개인용 Streamlit 대시보드**.

## 기능 (MVP)

| 페이지 | 기능 |
|---|---|
| 🔍 **Screener** | 1,099개 KRX ETF를 자산군·운용사·이름으로 필터링/정렬/비교 (정규화 가격 오버레이) |
| 📈 **ETF Detail** | 가격 차트(1M/3M/1Y/3Y/MAX), 수익률·변동성·MDD·Sharpe, NAV/시총 추이 |
| 🧭 **Strategies** | All Weather · 60/40 · Core-Satellite 백테스트 (equity curve, drawdown, 연도별 수익률, 벤치마크 비교) |
| 🌐 **Market** | 자산군 분포, 오늘의 등락 Top 10, 자금유입/유출 추정, 상관관계 히트맵 |

## 빠른 시작

```bash
# 0. uv 설치 (한 번만)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 1. 의존성 설치
uv sync --extra dev

# 2. 데이터 부트스트랩 (5년치, 1~2시간 소요)
uv run python -m etf_dash.ingest --job meta            # ~10초, 1099개 ETF 메타
uv run python -m etf_dash.ingest --job prices --full   # 전체 5년치 일봉

# 또는 빠르게 핵심 ETF만:
uv run python -m etf_dash.ingest --job prices --full \
  --ticker 069500 --ticker 148070 --ticker 136340 --ticker 132030 \
  --ticker 261220 --ticker 273130 --ticker 360750 --ticker 133690

# 3. 비밀번호 설정 (앱 게이트 — 외부 노출 시 필수)
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# 에디터로 .streamlit/secrets.toml 열어서 app_password 변경
# 강한 비번 생성: openssl rand -base64 24

# 4. 대시보드 실행
./scripts/run_dashboard.sh
# 또는: uv run streamlit run src/etf_dash/ui/app.py
```

브라우저에서 `http://localhost:8501` 접속 → 비밀번호 입력 → 4개 페이지 사용.

**외부에서 접속하려면** ngrok 설정: [docs/operations.md](docs/operations.md)의 "Exposing to the internet (ngrok)" 절 참고.

## 일일 갱신

장마감 후 (≈18:00 KST):
```bash
uv run python -m etf_dash.ingest --job all
```

스케줄러 설정 예시(launchd / cron)는 [docs/operations.md](docs/operations.md) 참고.

## 테스트

```bash
uv run pytest tests/unit/ -v
```

## 프로젝트 구조

```
src/etf_dash/
├── domain/         # 모델/스키마 (외부 의존 없음)
├── providers/      # FDRProvider (DataProvider Protocol 구현)
├── repository/     # SQLite + Parquet 영속성 (raw SQL)
├── ingest/         # 일배치 잡 + CLI (`python -m etf_dash.ingest`)
├── analysis/       # metrics · backtest · correlation · flows · strategies
└── ui/             # Streamlit 진입점 (app.py + pages/)
config/
├── settings.yaml   # 캐시 경로, ingest 파라미터
└── strategies.yaml # 전략 템플릿 정의 (코드 변경 없이 추가/수정)
data/               # gitignore. SQLite + Parquet 캐시
```

의존 방향: `providers → repository → analysis → ui` (단방향).

## 데이터 출처

- 주력: [`FinanceDataReader`](https://github.com/FinanceData/FinanceDataReader) (Naver Finance 기반)
- 자세한 매핑/제약/누락 필드: [docs/data-sources.md](docs/data-sources.md)

> 원래 `pykrx`를 주력으로 쓰려 했으나 KRX 정보사이트가 봇 차단을 강화해 현재 미사용. KRX OPEN API 정식 등록 시 재검토.

## 의도적으로 제외된 것 (MVP)

| 항목 | 사유 / 향후 |
|---|---|
| 사용자 정의 포트폴리오 빌더/최적화 | YAGNI. 전략 템플릿이 핵심. |
| LLM 자연어 해석 | `analysis/llm_explainer.py`에 Protocol stub만. |
| 해외 ETF 직투 | KR-only로 시작. `region` 컬럼은 예약. |
| 사용자 인증/멀티유저 | 개인용. |
| 보유종목 Top 10 | FDR 미제공. Naver 크롤링 또는 KRX OPEN API 정식 등록 시. |
| 총보수·상장일·벤치마크 | 위와 동일. |
| 분배락 보정 (total return) | MVP는 가격 기준만. |

## 모바일에서 Claude와 작업 이어가기

핸드폰 브라우저에서 [claude.ai/code](https://claude.ai/code)에 접속하면 같은 GitHub repo로 작업을 이어갈 수 있습니다.

1. Claude 계정으로 로그인
2. GitHub 연동 (sdjcoding/deeppool 선택)
3. 새 세션 시작 — Claude가 [`CLAUDE.md`](CLAUDE.md)를 자동으로 읽어 프로젝트 컨텍스트 + 결정/관행을 파악
4. 한국어로 자연스럽게 대화 (예: "Strategies 페이지에 위험기여도 도넛 차트 추가해줘")

데스크톱과 동일한 코드/스펙/문서가 모두 GitHub에 있어 컨텍스트 전환이 매끄럽습니다.

## 라이선스

개인 프로젝트. 외부 배포 시 데이터 출처 약관 확인 필요.
