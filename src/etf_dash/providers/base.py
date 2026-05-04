"""DataProvider Protocol — interface that all sources implement.

MVP has only one implementation (FDRProvider). This abstraction exists so a
future PykrxProvider, KrxOpenApiProvider, or NaverScraperProvider can drop in
without touching the repository or analysis layers.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class DataProvider(Protocol):
    name: str

    def list_etfs(self) -> pd.DataFrame:
        """Return a current snapshot of all ETFs the source knows about.

        Required columns (others permitted but ignored): ticker, name.
        Recommended: category (int), price, nav, mar_cap, volume, amount,
        earning_rate, change_rate.
        """
        ...

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """Return daily OHLCV history for a single ticker.

        Required columns: date, open, high, low, close, volume.
        Optional: change (daily return as a fraction).
        """
        ...
