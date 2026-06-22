"""Detect dead-name DELISTING REASONS + impute bankruptcy −100% terminals —
Phase 1A+ survivorship de-bias (the bankruptcy tail).

Pipeline (each step resumable / drip-capped / resilient):
  1. detect   classify each resolved dead CIK acquisition / bankruptcy / unknown
              from its 8-K item codes (data.sec.gov submissions; Item 1.03 =
              Bankruptcy or Receivership). -> data/edgar/dead_name_delisting.json
  2. impute   append a ~0 terminal close (source=imputed_bankruptcy) for every
              flagged bankruptcy that has a recovered price anchor, leak-free at
              max(filed, last_close). -> data/edgar/dead_name_prices.parquet
  3. coverage refresh the dead-name price coverage + the softened residual-bias
              caveat + the delisting-reason breakdown.

Run after the prices build (scripts.build_dead_name_prices) so there is a price
anchor to wipe; needs resolved CIKs from scripts.build_dead_name_fundamentals.
data.sec.gov is reachable everywhere, so detection runs anywhere a CIK is cached.

Usage:
  python -m scripts.build_dead_name_delisting                 # full resolved set, capped
  python -m scripts.build_dead_name_delisting --tickers SIVB BBBY --force
  python -m scripts.build_dead_name_delisting --max-new 50
"""
from __future__ import annotations

import argparse
import json
import logging

from collectors import edgar_deadname_prices as dp
from collectors import edgar_delisting as dl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None,
                    help="restrict to these dead tickers (default: full resolved set)")
    ap.add_argument("--max-new", type=int, default=200,
                    help="cap submissions scans this run (drip)")
    ap.add_argument("--force", action="store_true", help="ignore the scan cache / re-scan")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    dl.detect_delisting_reasons(force=args.force, max_new=args.max_new, tickers=args.tickers)
    dl.impute_bankruptcies()
    print(json.dumps({"delisting_reason": dl.delisting_breakdown(),
                      "price_coverage": dp.price_coverage()}, indent=1))


if __name__ == "__main__":
    main()
