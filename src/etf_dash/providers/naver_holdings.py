"""Naver Finance scraper for ETF constituent holdings.

FDR doesn't expose the "구성종목" table — Naver Finance's ETF main page does,
as a plain HTML table that pandas.read_html parses directly. This module is
intentionally minimal: one URL, one table, one DataFrame.

Page: https://finance.naver.com/item/main.naver?code={ticker}
The constituents table is the 4th table (index 3) on every KR ETF page.
Columns (verified against KODEX 200/305720/360750):
    구성종목(구성자산) | 주식수(계약수) | 구성비중 | 현재가 | 전일비 | 등락률
"""

from __future__ import annotations

import warnings
from io import StringIO

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

warnings.filterwarnings("ignore", category=UserWarning)

NAVER_URL = "https://finance.naver.com/item/main.naver?code={ticker}"
HOLDINGS_TABLE_INDEX = 3
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


class NaverHoldingsProvider:
    name = "NaverFinanceHoldings"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def get_holdings(self, ticker: str) -> pd.DataFrame:
        """Return a DataFrame of constituents with normalized column names.

        Columns: constituent_name, shares, weight_pct, price.
        Returns an empty DataFrame (with the right columns) if the ETF has no
        publishable holdings (some active/foreign-asset ETFs).
        """
        url = NAVER_URL.format(ticker=ticker)
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = "euc-kr"

        try:
            tables = pd.read_html(StringIO(resp.text))
        except ValueError:
            return _empty()
        if len(tables) <= HOLDINGS_TABLE_INDEX:
            return _empty()

        raw = tables[HOLDINGS_TABLE_INDEX]
        if raw.empty or raw.shape[1] < 3:
            return _empty()

        # Column positions are stable; names sometimes vary by page version.
        df = raw.iloc[:, :4].copy()
        df.columns = ["constituent_name", "shares", "weight_pct_str", "price"]
        df = df.dropna(subset=["constituent_name", "weight_pct_str"])
        df["weight_pct"] = df["weight_pct_str"].astype(str).str.rstrip("%").astype(float)
        df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df.drop(columns=["weight_pct_str"])
        df = df[df["weight_pct"] > 0].reset_index(drop=True)
        return df[["constituent_name", "shares", "weight_pct", "price"]]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["constituent_name", "shares", "weight_pct", "price"]
    )
