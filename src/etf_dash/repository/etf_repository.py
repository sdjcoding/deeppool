"""ETFRepository — single point of truth for cached data access."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from etf_dash.domain.models import ETFMeta
from etf_dash.repository.db import connect, init_db


class ETFRepository:
    def __init__(self, db_path: Path | None = None):
        self._db_path = init_db(db_path)

    # ------------------------------------------------------------------ reads
    def list_etfs(
        self,
        *,
        category: int | None = None,
        issuer: str | None = None,
        active_only: bool = True,
    ) -> pd.DataFrame:
        sql = "SELECT * FROM etf_meta WHERE 1=1"
        params: list = []
        if active_only:
            sql += " AND is_active = 1"
        if category is not None:
            sql += " AND category = ?"
            params.append(category)
        if issuer is not None:
            sql += " AND issuer = ?"
            params.append(issuer)
        sql += " ORDER BY name"
        with connect(self._db_path) as conn:
            return pd.read_sql_query(sql, conn, params=params)

    def get_etf(self, ticker: str) -> ETFMeta | None:
        with connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM etf_meta WHERE ticker = ?", (ticker,)
            ).fetchone()
        if row is None:
            return None
        return ETFMeta(
            ticker=row["ticker"],
            name=row["name"],
            category=row["category"],
            asset_class=row["asset_class"],
            issuer=row["issuer"],
            region=row["region"] or "KR",
            inception_date=_parse_date(row["inception_date"]),
            expense_ratio=row["expense_ratio"],
            benchmark=row["benchmark"],
            is_active=bool(row["is_active"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    def get_prices(
        self,
        tickers: list[str] | str,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame:
        if isinstance(tickers, str):
            tickers = [tickers]
        if not tickers:
            return pd.DataFrame()
        placeholders = ",".join(["?"] * len(tickers))
        sql = f"SELECT * FROM etf_price WHERE ticker IN ({placeholders})"
        params: list = list(tickers)
        if start is not None:
            sql += " AND date >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY ticker, date"
        with connect(self._db_path) as conn:
            df = pd.read_sql_query(sql, conn, params=params, parse_dates=["date"])
        return df

    def get_snapshots(
        self,
        tickers: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame:
        sql = "SELECT * FROM etf_snapshot WHERE 1=1"
        params: list = []
        if tickers:
            placeholders = ",".join(["?"] * len(tickers))
            sql += f" AND ticker IN ({placeholders})"
            params.extend(tickers)
        if start is not None:
            sql += " AND snap_date >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND snap_date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY ticker, snap_date"
        with connect(self._db_path) as conn:
            return pd.read_sql_query(sql, conn, params=params, parse_dates=["snap_date"])

    def last_price_date(self, ticker: str) -> date | None:
        with connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT MAX(date) AS d FROM etf_price WHERE ticker = ?", (ticker,)
            ).fetchone()
        if row is None or row["d"] is None:
            return None
        return _parse_date(row["d"])

    def last_snapshot_date(self) -> date | None:
        with connect(self._db_path) as conn:
            row = conn.execute("SELECT MAX(snap_date) AS d FROM etf_snapshot").fetchone()
        return _parse_date(row["d"]) if row and row["d"] else None

    def last_meta_update(self) -> datetime | None:
        with connect(self._db_path) as conn:
            row = conn.execute("SELECT MAX(updated_at) AS u FROM etf_meta").fetchone()
        return _parse_datetime(row["u"]) if row and row["u"] else None

    # ------------------------------------------------------------------ writes
    def upsert_meta(self, df: pd.DataFrame) -> int:
        """Insert or replace ETF metadata. Expects schema-aligned columns."""
        if df.empty:
            return 0
        rows = df.to_dict(orient="records")
        sql = """
            INSERT INTO etf_meta
                (ticker, name, category, asset_class, issuer, region,
                 inception_date, expense_ratio, benchmark, is_active, updated_at)
            VALUES
                (:ticker, :name, :category, :asset_class, :issuer, :region,
                 :inception_date, :expense_ratio, :benchmark, :is_active, :updated_at)
            ON CONFLICT(ticker) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                asset_class=excluded.asset_class,
                issuer=excluded.issuer,
                region=excluded.region,
                inception_date=COALESCE(excluded.inception_date, etf_meta.inception_date),
                expense_ratio=COALESCE(excluded.expense_ratio, etf_meta.expense_ratio),
                benchmark=COALESCE(excluded.benchmark, etf_meta.benchmark),
                is_active=excluded.is_active,
                updated_at=excluded.updated_at
        """
        with connect(self._db_path) as conn:
            conn.execute("BEGIN")
            try:
                conn.executemany(sql, rows)
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
                raise
        return len(rows)

    def upsert_prices(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        rows = df.to_dict(orient="records")
        sql = """
            INSERT INTO etf_price (ticker, date, open, high, low, close, volume, change)
            VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :change)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume, change=excluded.change
        """
        with connect(self._db_path) as conn:
            conn.execute("BEGIN")
            try:
                conn.executemany(sql, rows)
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
                raise
        return len(rows)

    def upsert_snapshots(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        df = df.copy()
        df["snap_date"] = pd.to_datetime(df["snap_date"]).dt.strftime("%Y-%m-%d")
        rows = df.to_dict(orient="records")
        sql = """
            INSERT INTO etf_snapshot
                (ticker, snap_date, price, nav, mar_cap, volume, amount,
                 earning_rate, change_rate)
            VALUES
                (:ticker, :snap_date, :price, :nav, :mar_cap, :volume, :amount,
                 :earning_rate, :change_rate)
            ON CONFLICT(ticker, snap_date) DO UPDATE SET
                price=excluded.price, nav=excluded.nav, mar_cap=excluded.mar_cap,
                volume=excluded.volume, amount=excluded.amount,
                earning_rate=excluded.earning_rate, change_rate=excluded.change_rate
        """
        with connect(self._db_path) as conn:
            conn.execute("BEGIN")
            try:
                conn.executemany(sql, rows)
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
                raise
        return len(rows)

    def log_ingest(
        self, job: str, status: str, *, ticker: str | None = None, message: str | None = None
    ) -> None:
        with connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO ingest_log (job, ticker, run_at, status, message) "
                "VALUES (?, ?, ?, ?, ?)",
                (job, ticker, datetime.now().isoformat(timespec="seconds"), status, message),
            )

    def deactivate_missing(self, present_tickers: set[str]) -> int:
        """Mark tickers absent from `present_tickers` as inactive (delisted)."""
        with connect(self._db_path) as conn:
            existing = {r["ticker"] for r in conn.execute("SELECT ticker FROM etf_meta")}
            missing = existing - present_tickers
            if not missing:
                return 0
            placeholders = ",".join("?" * len(missing))
            conn.execute(
                f"UPDATE etf_meta SET is_active = 0 WHERE ticker IN ({placeholders})",
                tuple(missing),
            )
        return len(missing)


# ----- helpers ---------------------------------------------------------------


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value).date() if "T" in value else date.fromisoformat(value)


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
