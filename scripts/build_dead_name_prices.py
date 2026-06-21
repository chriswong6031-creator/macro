"""Recover dead-name daily prices — Phase 1A survivorship de-bias (prices half).

Resumable, drip-capped, RESILIENT: attempts Stooq → Polygon → yfinance per resolved
dead ticker, caches what it gets, no-ops where sources are IP-blocked. Run after the
fundamentals build (scripts.build_dead_name_fundamentals) so CIKs are resolved.

Usage:
  python -m scripts.build_dead_name_prices                 # full resolved set, capped
  python -m scripts.build_dead_name_prices --tickers ATVI AET --force
  python -m scripts.build_dead_name_prices --max-new 50
"""
from __future__ import annotations

import argparse
import json
import logging

from collectors import edgar_deadname_prices as dp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None)
    ap.add_argument("--max-new", type=int, default=150)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    dp.fetch_dead_prices(force=args.force, max_new=args.max_new, tickers=args.tickers)
    print(json.dumps(dp.price_coverage(), indent=1))


if __name__ == "__main__":
    main()
