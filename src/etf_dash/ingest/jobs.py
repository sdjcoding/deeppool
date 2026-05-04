"""Ingest jobs: pull from provider, transform, persist via repository.

Each job is a plain function so it can be invoked from the CLI or from a
notebook for spot checks. Jobs are idempotent (safe to re-run).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import pandas as pd

from etf_dash.config import get_settings
from etf_dash.domain.schemas import (
    category_to_asset_class,
    issuer_from_name,
)
from etf_dash.providers.fdr_provider import FDRProvider
from etf_dash.repository.etf_repository import ETFRepository

logger = logging.getLogger(__name__)


# --- meta + snapshot (cheap, run together daily) -----------------------------


def ingest_meta_and_snapshot(
    repo: ETFRepository,
    provider: FDRProvider | None = None,
    *,
    snap_date: date | None = None,
) -> dict[str, int]:
    """Refresh etf_meta from current ETF listing and append today's snapshot.

    A single FDR call returns both — they're written atomically per table.
    """
    provider = provider or FDRProvider()
    snap_date = snap_date or date.today()
    listing = provider.list_etfs()

    # --- meta upsert ---
    meta_df = pd.DataFrame(
        {
            "ticker": listing["ticker"],
            "name": listing["name"],
            "category": listing.get("category"),
            "asset_class": listing.get("category", pd.Series(dtype="float")).map(
                category_to_asset_class
            ),
            "issuer": listing["name"].map(issuer_from_name),
            "region": "KR",
            "inception_date": None,
            "expense_ratio": None,
            "benchmark": None,
            "is_active": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    meta_count = repo.upsert_meta(meta_df)
    deactivated = repo.deactivate_missing(set(listing["ticker"].astype(str)))

    # --- snapshot upsert ---
    snap_df = pd.DataFrame(
        {
            "ticker": listing["ticker"],
            "snap_date": snap_date.isoformat(),
            "price": listing.get("price"),
            "nav": listing.get("nav"),
            "mar_cap": listing.get("mar_cap"),
            "volume": listing.get("volume"),
            "amount": listing.get("amount"),
            "earning_rate": listing.get("earning_rate"),
            "change_rate": listing.get("change_rate"),
        }
    )
    snap_count = repo.upsert_snapshots(snap_df)

    repo.log_ingest(
        "meta_snapshot",
        "ok",
        message=f"meta={meta_count} snapshot={snap_count} deactivated={deactivated}",
    )
    return {"meta": meta_count, "snapshot": snap_count, "deactivated": deactivated}


# --- prices (per-ticker, slow, supports incremental) -------------------------


def ingest_prices(
    repo: ETFRepository,
    tickers: list[str] | None = None,
    *,
    provider: FDRProvider | None = None,
    full: bool = False,
    end: date | None = None,
) -> dict[str, int]:
    """Pull OHLCV history for each ticker.

    - full=False (default): incremental, from `last_price_date(ticker) + 1` to `end`.
    - full=True: from `default_lookback_years` ago to `end`.
    - tickers=None: all active ETFs in repo.
    """
    provider = provider or FDRProvider()
    settings = get_settings()
    end = end or date.today()

    if tickers is None:
        meta = repo.list_etfs(active_only=True)
        tickers = meta["ticker"].astype(str).tolist()

    full_start = end - timedelta(days=365 * settings.ingest.default_lookback_years)
    sleep = settings.ingest.request_sleep_seconds

    inserted = 0
    fetched_tickers = 0
    failed: list[str] = []

    for i, ticker in enumerate(tickers):
        try:
            if full:
                start = full_start
            else:
                last = repo.last_price_date(ticker)
                start = (last + timedelta(days=1)) if last else full_start
                if start > end:
                    continue
            df = provider.get_ohlcv(ticker, start, end)
            if df.empty:
                continue
            df.insert(0, "ticker", ticker)
            inserted += repo.upsert_prices(df)
            fetched_tickers += 1
        except Exception as exc:  # noqa: BLE001
            failed.append(ticker)
            repo.log_ingest("prices", "error", ticker=ticker, message=str(exc))
            logger.warning("prices fetch failed for %s: %s", ticker, exc)
        finally:
            if sleep > 0 and i < len(tickers) - 1:
                time.sleep(sleep)

    repo.log_ingest(
        "prices",
        "ok" if not failed else "partial",
        message=(
            f"fetched={fetched_tickers}/{len(tickers)} rows={inserted} "
            f"failed={len(failed)}"
        ),
    )
    return {
        "tickers_fetched": fetched_tickers,
        "rows_inserted": inserted,
        "failed": len(failed),
    }


# --- validation --------------------------------------------------------------


def validate(repo: ETFRepository) -> dict[str, int]:
    """Lightweight integrity checks — print counts and flag obvious issues."""
    from etf_dash.repository.db import connect

    out: dict[str, int] = {}
    with connect() as conn:
        for tbl in ("etf_meta", "etf_price", "etf_snapshot", "ingest_log"):
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {tbl}").fetchone()
            out[tbl] = row["c"]
        out["price_with_nan_close"] = conn.execute(
            "SELECT COUNT(*) AS c FROM etf_price WHERE close IS NULL"
        ).fetchone()["c"]
        out["price_negative_close"] = conn.execute(
            "SELECT COUNT(*) AS c FROM etf_price WHERE close < 0"
        ).fetchone()["c"]
        out["meta_missing_issuer"] = conn.execute(
            "SELECT COUNT(*) AS c FROM etf_meta WHERE issuer IS NULL OR issuer = ''"
        ).fetchone()["c"]
    return out
