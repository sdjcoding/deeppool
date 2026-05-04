# Data Sources

## Decision: FinanceDataReader only (MVP)

**MVP uses [`FinanceDataReader`](https://github.com/FinanceData/FinanceDataReader) (FDR)** as the sole data source. FDR proxies Naver Finance, which is permissive and stable for retail-level usage.

### Why not pykrx?

The original plan called for `pykrx` as the primary source. **As of 2026-05, pykrx is broken** because the KRX information site (`data.krx.co.kr`) added bot protection — direct API calls return `LOGOUT` (HTTP 400) and even session-cookie warm-up does not bypass it. See `scripts/smoke_data_sources.py` for the probe.

### What we get from FDR

- `fdr.StockListing('ETF/KR')` — snapshot of all KR-listed ETFs (≈1,100): `Symbol, Category, Name, Price, NAV, EarningRate, ChangeRate, Volume, Amount, MarCap`
- `fdr.DataReader(ticker, start, end)` — historical OHLCV + Change

### Category mapping (FDR `Category` column)

| Code | Bucket | Examples |
|---|---|---|
| 1 | 국내 시장지수 | KODEX 200, TIGER 200, KODEX 코스닥150 |
| 2 | 국내 섹터/테마 | KODEX 반도체, TIGER AI, KODEX 삼성그룹 |
| 3 | 국내 파생/레버리지/인버스 | KODEX 레버리지, KODEX 200선물인버스2X |
| 4 | 해외 주식 | TIGER 미국S&P500, KODEX 미국나스닥100 |
| 5 | 원자재 | KODEX 골드선물, ACE KRX금현물 |
| 6 | 채권/금리 | KODEX CD금리액티브, KODEX 종합채권 |
| 7 | 혼합/MMF | KODEX 머니마켓액티브, ACE 미국S&P500미국채혼합50 |

### Issuer inference (from name prefix)

| Prefix | Issuer (운용사) |
|---|---|
| KODEX | 삼성자산운용 |
| TIGER | 미래에셋자산운용 |
| RISE | KB자산운용 (구 KBSTAR) |
| ACE | 한국투자신탁운용 (구 KINDEX) |
| PLUS | 한화자산운용 (구 ARIRANG) |
| SOL | 신한자산운용 |
| KIWOOM | 키움투자자산운용 |
| HANARO | NH-Amundi자산운용 |
| 1Q | 하나자산운용 |
| KoAct | 한국투자신탁운용 (액티브) |
| TIME | 타임폴리오자산운용 |
| WON | 우리자산운용 |
| BNK | BNK자산운용 |

Anything else → `기타` (rare).

## Deferred / TBD (post-MVP)

| Field | Why deferred | Future plan |
|---|---|---|
| `expense_ratio` (총보수) | Not in FDR | Naver Finance ETF detail page scrape, OR KRX OPEN API registration |
| `inception_date` (상장일) | Not in FDR listing | Same as above |
| `benchmark` (추종지수) | Not in FDR | Same as above |
| `holdings` (보유종목 PDF) | Not in FDR | Naver Finance "구성종목" tab scrape, OR official KRX disclosure |
| `dividend_history` | FDR `DataReader` doesn't return | `fdr.SnapDataReader` (TBD probe) or Naver scrape |
| `historical_nav_aum` | Only current snapshot | We **save the daily snapshot** ourselves and accumulate over time |

UI must clearly show "보유종목 정보 미제공" / "총보수 추후 보강" where applicable.

## Snapshot accumulation strategy

`fdr.StockListing('ETF/KR')` returns a *current-day* snapshot of NAV, MarCap, Volume, Amount, etc. for every ETF. By saving this as a daily row per ticker, we build a **historical AUM/NAV time series ourselves** — replacing one of the things pykrx would have given us directly.

Stored in SQLite as `etf_snapshot(ticker, snap_date, nav, mar_cap, volume, amount, earning_rate)`.
