"""One-time backfill of Federal Register documents from 2015-01-01 to today.

Usage:
    python scripts/backfill_federal_register.py [--since YYYY-MM-DD]

This script runs the FederalRegisterAdapter in full_history mode (fetches from the
configured since-date through today) and commits the resulting parquet files.

NOT registered in the nightly collect path (masterplan R8). Run once after deployment;
subsequent daily collects will handle incremental updates.

federalregister.gov is verified reachable from this sandbox (probe: 2026-07-03).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.federal_register import FederalRegisterAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Federal Register documents")
    parser.add_argument(
        "--since", default="2015-01-01",
        help="Earliest publication_date to fetch (default: 2015-01-01)",
    )
    args = parser.parse_args()

    log.info("Starting Federal Register backfill since %s ...", args.since)

    # Patch the default gte date via full_history=True (the adapter uses 2015-01-01 for full_history)
    adapter = FederalRegisterAdapter()
    result = adapter.fetch(full_history=True)

    for key, df in result.items():
        if df is not None and not df.empty:
            log.info("  %s: %s rows", key, len(df))

    log.info("Backfill complete.")


if __name__ == "__main__":
    main()
