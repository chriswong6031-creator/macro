"""Backfill SEC Fails-to-Deliver history from 2009-07 (earliest available) to present.

Source: https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data

NOTE ON DATA HISTORY: The SEC FTD page states data begins 2004, but the actual
available files online begin 2009-07.  Direct URL tests confirm 404 for all
pre-2009 files.  This script backfills from 2009-07 onwards and documents the
limitation clearly.

PIT LAW (pre-registered in collectors.sec_ftd):
  availability_date = period_end + 30 calendar days (uniform, conservative).

Resumable: already-fetched file keys are tracked in panel.parquet._file_key and
skipped on re-run.

Usage:
    python -m scripts.backfill_sec_ftd [--start YYYY] [--end YYYY-MM-DD] [--dry-run]
    python -m scripts.backfill_sec_ftd --incremental     # nightly: recent files only

The store is written to data/sec_ftd/panel.parquet in your worktree (a NEW real
directory — not a symlink — because this lane writes to it).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collectors.sec_ftd import backfill, incremental

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", type=int, default=2009,
                   help="Start year (default 2009; earliest data available is 2009-07)")
    p.add_argument("--end", default=str(date.today()),
                   help="End date YYYY-MM-DD (default today)")
    p.add_argument("--dry-run", action="store_true",
                   help="Count files to fetch without downloading")
    p.add_argument("--incremental", action="store_true",
                   help="Fetch only the most recent missing files (nightly mode)")
    args = p.parse_args()

    if args.incremental:
        result = incremental(lookback_files=4)
    else:
        result = backfill(
            start_year=args.start,
            end_date=date.fromisoformat(args.end),
            dry_run=args.dry_run,
        )

    print(f"[backfill_sec_ftd] {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
