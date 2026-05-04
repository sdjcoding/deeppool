# DeepPool

KRX 상장 ETF를 탐색·분석하고 검증된 자산배분 전략(All Weather, 60/40 등)을 KRX ETF로 매핑해 보여주는 개인용 Streamlit 대시보드.

> 상태: MVP 부트스트랩 진행 중. 자세한 설계는 `docs/spec.md` 참고.

## 기능 (MVP)

- **A. ETF 스크리너** — 자산군/섹터/규모/총보수/배당률 등으로 KRX ETF 필터·비교
- **B. ETF 상세** — 가격 차트, 수익률(1M/3M/1Y/3Y), 변동성, MDD, Sharpe, 보유종목 Top 10
- **E. 전략 템플릿** — All Weather, 60/40, 코어-새틀라이트를 KRX ETF로 매핑한 백테스트
- **F. 시장/매크로** — 자산군별 트렌드, 자금유입/유출, 상관관계 히트맵

## 빠른 시작

```bash
# 1. 의존성 설치 (uv)
uv sync --extra dev

# 2. 데이터 부트스트랩 (5년치, 1~2시간 소요)
uv run python -m etf_dash.ingest --job all --full

# 3. 대시보드 실행
uv run streamlit run src/etf_dash/ui/app.py
```

## 일일 갱신

```bash
# 장마감 후 18:00 권장 (cron / launchd)
uv run python -m etf_dash.ingest --job meta
uv run python -m etf_dash.ingest --job prices       # 증분
```

자세한 명령어는 `docs/operations.md` (TBD).

## 프로젝트 구조

```
src/etf_dash/
├── domain/         # 모델/스키마
├── providers/      # pykrx, FDR 어댑터
├── repository/     # SQLite + Parquet 영속성
├── ingest/         # 일/주 배치 잡
├── analysis/       # 지표·백테스트·전략
└── ui/             # Streamlit 페이지
```

의존 방향: `providers → repository → analysis → ui`.

## 데이터 출처

- 가격·NAV·시가총액·ETF 리스트: [`FinanceDataReader`](https://github.com/FinanceData/FinanceDataReader) (Naver Finance 기반)
- 자세한 출처/매핑/누락 필드: [docs/data-sources.md](docs/data-sources.md)

> 원래 `pykrx`를 주력으로 쓰려 했으나 KRX 정보사이트가 봇 차단을 강화해 현재 미사용. 추후 KRX OPEN API 등록 시 재검토.

## 라이선스

개인 프로젝트. 외부 배포 시 데이터 출처 약관 확인 필요.
