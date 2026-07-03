"""Rebuild the historical archetype series (data/archetypes/history.parquet).

Usage
-----
  python -m scripts.build_archetype_history           # rebuild to default path
  python -m scripts.build_archetype_history --out PATH  # write to a custom path

Output
------
  data/archetypes/history.parquet  -- annual archetype labels per ticker/FY
                                      (19,487 rows expected for FY2009-2025)

Lifecycle
---------
  Rebuilt on demand; NOT on the nightly path; frozen between rebuilds.
  Run when: (a) the EDGAR fundamentals_panel is refreshed, (b) the v2 archetype
  thresholds change, or (c) a new archetype bucket is added.

Note on PIT status
------------------
  Altman Z inputs and rev/EPS CAGRs are genuinely PIT (statements filtered to
  fy <= row fy). Sector, rates_beta, oil_beta_raw, and factor z-scores are
  CURRENT-SNAPSHOT (single 2026 value for all historical rows). Labels for
  beta/sector-driven buckets are therefore non-PIT for historical rows.
  See archetypes_history() docstring for the full breakdown.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.stock_fundamentals import archetypes_history  # noqa: E402

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Rebuild data/archetypes/history.parquet (on-demand, not nightly)"
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="Override output path (default: data/archetypes/history.parquet)",
    )
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else None

    log.info("build_archetype_history: starting rebuild …")
    df = archetypes_history(out_path=out_path)

    if df.empty:
        log.warning("build_archetype_history: result is empty — check input data paths")
        return 1

    n_rows = len(df)
    n_tickers = df["ticker"].nunique() if "ticker" in df.columns else 0
    log.info(
        "build_archetype_history: done — %d rows, %d unique tickers",
        n_rows,
        n_tickers,
    )
    if "fy" in df.columns:
        log.info(
            "build_archetype_history: FY range %d – %d",
            int(df["fy"].min()),
            int(df["fy"].max()),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
