"""SQLite connection and schema management."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from etf_dash.config import get_settings, resolve_path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS etf_meta (
  ticker TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category INTEGER,
  asset_class TEXT,
  issuer TEXT,
  region TEXT DEFAULT 'KR',
  inception_date TEXT,
  expense_ratio REAL,
  benchmark TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etf_price (
  ticker TEXT NOT NULL,
  date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume INTEGER,
  change REAL,
  PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_price_date ON etf_price(date);

CREATE TABLE IF NOT EXISTS etf_snapshot (
  ticker TEXT NOT NULL,
  snap_date TEXT NOT NULL,
  price REAL,
  nav REAL,
  mar_cap REAL,
  volume INTEGER,
  amount REAL,
  earning_rate REAL,
  change_rate REAL,
  PRIMARY KEY (ticker, snap_date)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_date ON etf_snapshot(snap_date);

CREATE TABLE IF NOT EXISTS ingest_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job TEXT NOT NULL,
  ticker TEXT,
  run_at TEXT NOT NULL,
  status TEXT NOT NULL,
  message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingest_log_run_at ON ingest_log(run_at);
"""


def db_path() -> Path:
    return resolve_path(get_settings().cache.db_path)


def init_db(path: Path | None = None) -> Path:
    """Create database file (incl. parent dir) and apply DDL idempotently."""
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(p) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.commit()
    return p


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, isolation_level=None)  # autocommit; we BEGIN manually
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
    finally:
        conn.close()
