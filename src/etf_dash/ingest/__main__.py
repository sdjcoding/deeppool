"""CLI: `python -m etf_dash.ingest [--job ...] [--ticker ...] [--full]`."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from etf_dash.ingest.jobs import (
    ingest_meta_and_snapshot,
    ingest_prices,
    validate,
)
from etf_dash.providers.fdr_provider import FDRProvider
from etf_dash.repository.etf_repository import ETFRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="etf_dash.ingest")
    parser.add_argument(
        "--job",
        choices=["all", "meta", "prices", "validate"],
        default="all",
        help="Which job to run. 'meta' updates etf_meta + today's snapshot. "
        "'prices' refreshes OHLCV (incremental by default). "
        "'all' runs meta then prices.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        default=None,
        help="Restrict price ingest to one or more tickers. Repeatable.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ignore last cached date and refetch full lookback window.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    repo = ETFRepository()
    provider = FDRProvider()
    summary: dict = {}

    if args.job in ("all", "meta"):
        summary["meta"] = ingest_meta_and_snapshot(repo, provider)
    if args.job in ("all", "prices"):
        summary["prices"] = ingest_prices(
            repo, tickers=args.ticker, provider=provider, full=args.full
        )
    if args.job == "validate":
        summary["validate"] = validate(repo)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
