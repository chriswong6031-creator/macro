"""Build the dead-name fundamentals panel — Phase 1B survivorship de-bias.

Pipeline (each step resumable / drip-capped):
  1. resolve   dead ticker -> CIK   (curated seed + company_tickers.json + Polygon)
  1b.fts       lift the unresolved long tail via the windowed EDGAR full-text crawl
              (efts.sec.gov + data.sec.gov submissions confirm); opt-in via --fts-max
  2. pull      companyfacts -> leak-free filed-stamped panel rows  (data.sec.gov)
  3. coverage  write the honest dead_name_coverage ratio

CIK resolution at scale needs www.sec.gov's company_tickers.json or a Polygon key
(IP-gated — run where reachable, e.g. CI; the cache persists). The full-text crawl
(step 1b) and companyfacts (step 2) live on data.sec.gov / efts.sec.gov and run
anywhere; both are drip-capped so coverage accrues across CI runs.

Usage:
  python -m scripts.build_dead_name_fundamentals               # full universe, capped
  python -m scripts.build_dead_name_fundamentals --tickers ATVI AET ABMD
  python -m scripts.build_dead_name_fundamentals --max-new 50 --no-polygon
  python -m scripts.build_dead_name_fundamentals --resolve-only --fts-max 200
"""
from __future__ import annotations

import argparse
import json
import logging

from collectors import edgar_deadnames as dn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None,
                    help="restrict to these dead tickers (default: full dead universe)")
    ap.add_argument("--max-new", type=int, default=200,
                    help="cap companyfacts fetches this run (drip)")
    ap.add_argument("--no-polygon", action="store_true",
                    help="skip the Polygon CIK fallback")
    ap.add_argument("--fts-max", type=int, default=0,
                    help="EDGAR full-text crawl cap for the unresolved long tail this "
                         "run (0 = off; opt-in because it is the heavy SEC-paced leg)")
    ap.add_argument("--resolve-only", action="store_true",
                    help="resolve CIKs and stop (no companyfacts pull)")
    ap.add_argument("--force", action="store_true", help="ignore caches / refetch")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    universe = args.tickers if args.tickers is not None else dn.dead_universe()
    log = logging.getLogger("dead_names")
    log.info("dead-name universe: %d tickers", len(universe))

    dn.resolve_dead_ciks(universe, force=args.force, use_polygon=not args.no_polygon)
    if args.fts_max > 0:
        dn.resolve_via_fulltext(tickers=args.tickers if args.tickers is not None else None,
                                max_new=args.fts_max, force=args.force)
    if args.resolve_only:
        cov = dn.coverage(dead_universe=universe if args.tickers is not None else None)
        print(json.dumps(cov, indent=1))
        return

    dn.build_dead_panel(force=args.force, max_new=args.max_new,
                        tickers=args.tickers if args.tickers is not None else None)
    cov = dn.coverage(dead_universe=universe if args.tickers is not None else None)
    print(json.dumps(cov, indent=1))


if __name__ == "__main__":
    main()
