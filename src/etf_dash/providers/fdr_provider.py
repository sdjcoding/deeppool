"""FinanceDataReader (Naver Finance) — primary data source for the MVP."""

from __future__ import annotations

import warnings
from datetime import date

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

# FDR can warn loudly during imports/calls; suppress at module load.
warnings.filterwarnings("ignore", category=UserWarning)

import FinanceDataReader as fdr  # noqa: E402


class FDRProvider:
    name = "FinanceDataReader"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def list_etfs(self) -> pd.DataFrame:
        raw = fdr.StockListing("ETF/KR")
        # Normalize to repository-aligned column names.
        df = raw.rename(
            columns={
                "Symbol": "ticker",
                "Category": "category",
                "Name": "name",
                "Price": "price",
                "NAV": "nav",
                "MarCap": "mar_cap",
                "Volume": "volume",
                "Amount": "amount",
                "EarningRate": "earning_rate",
                "ChangeRate": "change_rate",
                "Change": "change",
                "RiseFall": "rise_fall",
            }
        )
        # Drop rows without a ticker (defensive — shouldn't happen)
        df = df[df["ticker"].notna()].copy()
        df["ticker"] = df["ticker"].astype(str)
        return df

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_ohlcv(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        raw = fdr.DataReader(ticker, start.isoformat(), end.isoformat())
        if raw.empty:
            return pd.DataFrame(
                columns=["date", "open", "high", "low", "close", "volume", "change"]
            )
        df = raw.reset_index().rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
                "Change": "change",
            }
        )
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[["date", "open", "high", "low", "close", "volume", "change"]]
