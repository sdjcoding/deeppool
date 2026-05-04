"""Bootstrap probe: verify what data sources actually return today.

Decides which source to use as the primary DataProvider.

Originally targeted pykrx but the KRX info site started rejecting bot
requests with 'LOGOUT' (HTTP 400) — see notes below. FDR (Naver-backed)
still works and covers the core needs.
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def probe_pykrx() -> dict:
    from pykrx import stock

    end_dt = datetime.now() - timedelta(days=14)
    end = end_dt.strftime("%Y%m%d")
    start = (end_dt - timedelta(days=365)).strftime("%Y%m%d")
    out = {"window": f"{start} -> {end}"}

    try:
        tickers = stock.get_etf_ticker_list(end)
        out["ticker_list"] = f"{len(tickers)} tickers"
    except Exception as exc:  # noqa: BLE001
        out["ticker_list_error"] = f"{type(exc).__name__}: {exc}"

    try:
        df = stock.get_etf_ohlcv_by_date(start, end, "069500")
        out["ohlcv_shape"] = f"{df.shape}, cols={list(df.columns)}"
    except Exception as exc:  # noqa: BLE001
        out["ohlcv_error"] = f"{type(exc).__name__}: {exc}"

    try:
        pdf = stock.get_etf_portfolio_deposit_file("069500")
        out["holdings_shape"] = f"{pdf.shape}, cols={list(pdf.columns)}"
    except Exception as exc:  # noqa: BLE001
        out["holdings_error"] = f"{type(exc).__name__}: {exc}"

    return out


def probe_fdr() -> dict:
    import FinanceDataReader as fdr

    out: dict[str, str] = {}
    try:
        etfs = fdr.StockListing("ETF/KR")
        out["etf_list"] = f"{etfs.shape[0]} rows, cols={list(etfs.columns)}"
        out["etf_categories"] = f"unique Category={sorted(etfs['Category'].dropna().unique().tolist())}"
        out["sample"] = etfs.head(3).to_dict(orient="records")
    except Exception as exc:  # noqa: BLE001
        out["etf_list_error"] = f"{type(exc).__name__}: {exc}"

    try:
        df = fdr.DataReader("069500", "2025-01-01", "2025-12-31")
        out["ohlcv_shape"] = f"{df.shape}, cols={list(df.columns)}"
    except Exception as exc:  # noqa: BLE001
        out["ohlcv_error"] = f"{type(exc).__name__}: {exc}"

    return out


def main() -> int:
    _section("pykrx probe")
    for k, v in probe_pykrx().items():
        print(f"  {k}: {v}")

    _section("FinanceDataReader probe")
    for k, v in probe_fdr().items():
        print(f"  {k}: {v}")

    _section("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
