"""Off-render dispatchable: full backfill of edgar_facts FLOW fields for the
~1,334-name fundamentals universe.

Triggered via the `edgar-flow-backfill` action in .github/workflows/edgar_flow_ops.yml
(workflow_dispatch; never pushes to main; data rides the next nightly ENGINE git-add).

WHY THIS EXISTS
---------------
PR-H (Long-Hold Thesis Layer W2) added SBC and R&D to the edgar_facts.py FLOW
concept table.  The weekly drip (collectors/edgar_facts.py REFRESH_DAYS=30) fetches
at most max_new=200 tickers per run, so full universe coverage takes ~7 runs
(~7 weeks).  This dispatchable runs the full universe in one shot (respecting SEC
pacing), so the new columns populate promptly after the PR merges.

It is ALSO the correct tool to force-refresh existing tickers after a FLOW dict
change (e.g. adding a new concept), because fetch_statements(force=True) bypasses
the 30-day staleness guard.

NIGHTLY-SOLE-ADVANCER LAW
--------------------------
This script writes ONLY to data/edgar/statements.parquet (via fetch_statements).
It does NOT push to git.  The nightly ENGINE job's broad "git add data/" sweeps
the updated parquet on the next run.

USAGE
-----
  # Sample run — 30 tickers, force re-fetch (validates concept flow end-to-end):
  python -m scripts.backfill_edgar_flow --max 30 --force

  # Full universe backfill (1,334 tickers, ~45 min at SEC pacing):
  python -m scripts.backfill_edgar_flow --max 9999 --force

  # Specific tickers only (CI / validation):
  python -m scripts.backfill_edgar_flow --tickers AAPL MSFT NVDA

COVERAGE STAMP
--------------
After a run, check coverage of new fields:
  python -c "
  import pandas as pd
  df = pd.read_parquet('data/edgar/statements.parquet')
  for col in ('depreciation', 'interest_exp', 'sbc', 'research_dev'):
      n = df['ticker'].nunique() if col not in df else df[col].notna().sum()
      cov = df[col].notna().groupby(df['ticker']).any().mean() if col in df else 0
      print(f'{col}: ticker-coverage={cov:.1%}')
  "
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("backfill_edgar_flow")

import pandas as pd


def _coverage_report(df: pd.DataFrame) -> None:
    """Print per-field ticker-level coverage for the FLOW fields added/extended in W2 PR-H."""
    new_fields = ["depreciation", "interest_exp", "sbc", "research_dev"]
    existing_fields = ["op_income", "cfo", "revenue", "gross_profit", "ni"]
    log.info("=== coverage report (ticker-level: ≥1 non-null FY row) ===")
    for col in existing_fields + new_fields:
        if col not in df.columns:
            log.info("  %-20s  ABSENT from parquet (column not yet written)", col)
            continue
        by_ticker = df.groupby("ticker")[col].apply(lambda s: s.notna().any())
        cov = by_ticker.mean()
        n_tickers = by_ticker.sum()
        total = len(by_ticker)
        marker = " <-- W2 PR-H" if col in new_fields else ""
        log.info("  %-20s  %5.1f%%  (%d / %d tickers)%s",
                 col, 100 * cov, n_tickers, total, marker)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max", type=int, default=30,
                    help="max new tickers to fetch (default 30 for sample run; "
                         "use 9999 for full universe)")
    ap.add_argument("--force", action="store_true",
                    help="bypass the 30-day staleness guard (required to pick up "
                         "new FLOW concepts on already-fetched tickers)")
    ap.add_argument("--tickers", nargs="+", metavar="TICK",
                    help="restrict to specific tickers (overrides --max)")
    args = ap.parse_args()

    from collectors.edgar_facts import fetch_statements, FLOW as FACTS_FLOW

    log.info("=== edgar_flow backfill ===")
    log.info("FLOW concepts in edgar_facts.py: %s", list(FACTS_FLOW.keys()))
    log.info("force=%s  max=%d  tickers=%s",
             args.force, args.max, args.tickers or "(universe)")

    df = fetch_statements(
        force=args.force,
        max_new=len(args.tickers) if args.tickers else args.max,
        tickers=args.tickers,
    )

    if df.empty:
        log.warning("statements.parquet is empty after run — check CIK map / network")
        return 1

    log.info("statements.parquet: %d rows, %d tickers, %d columns",
             len(df), df["ticker"].nunique() if "ticker" in df else 0, df.shape[1])
    _coverage_report(df)

    # spot-check: for a sample ticker confirm new fields populated at least one row
    spot = args.tickers[0] if args.tickers else "AAPL"
    if "ticker" in df.columns:
        sub = df[df["ticker"] == spot].sort_values("fy")
        if not sub.empty:
            log.info("=== spot-check %s ===", spot)
            check_cols = [c for c in ("fy", "op_income", "interest_exp", "depreciation",
                                      "sbc", "research_dev", "revenue", "ni", "cfo")
                          if c in sub.columns]
            log.info("\n%s", sub[check_cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
