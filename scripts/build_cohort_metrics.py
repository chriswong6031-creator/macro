"""scripts/build_cohort_metrics.py — W0.4 Setup-Species cohort-context metrics.

Nightly, display-only.  Runs after build_subsector_confluence (reads the committed
subsector_confluence.json for member T1-T4 tier states).

Writes:
  site/factordata/cohort_metrics.json   — full cohort metrics payload (chips source)
  data/cohort_metrics/<YYYY-MM-DD>.parquet — within-cohort RS rank series (S7 dependency)

Sentinel git-add set (non-gitignored):
  site/factordata/cohort_metrics.json
  data/cohort_metrics/

DISPLAY-ONLY: metrics are available to builders as a chip payload but must NOT be
wired into blend_sorted/scores without the promotion ladder (§1.4 ship-shape law).

See engine/cohort_metrics.py for the full spec and coverage law.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("build_cohort_metrics")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")


def main() -> None:
    t0 = time.perf_counter()
    from engine import cohort_metrics as cm

    log.info("build_cohort_metrics: loading sector/tier maps")
    sector_map = cm.load_sector_map()
    tier_map   = cm.load_tier_map()

    if not sector_map:
        log.error("build_cohort_metrics: sector_map empty — subsector_confluence.json "
                  "must exist before running this script")
        sys.exit(1)

    log.info("build_cohort_metrics: computing cohort metrics (%d tickers in %d sectors)",
             len(sector_map),
             len(set(sector_map.values())))

    metrics = cm.compute(sector_map=sector_map, tier_map=tier_map)

    elapsed = time.perf_counter() - t0
    log.info("build_cohort_metrics: compute done in %.1fs — "
             "%d tickers, %d cohort-null (coverage law)",
             elapsed,
             metrics.get("n_tickers", 0),
             metrics.get("cohort_null_count", 0))

    if elapsed > 60:
        log.warning("build_cohort_metrics: %.1fs exceeds 60s profile budget — "
                    "consider pre-caching member states from existing engines", elapsed)

    # Write JSON (site/factordata/cohort_metrics.json)
    json_path = cm.write_json(metrics)
    if json_path:
        log.info("build_cohort_metrics: JSON written → %s", json_path)
    else:
        log.error("build_cohort_metrics: JSON write failed")

    # Persist RS rank series (data/cohort_metrics/<date>.parquet)
    parquet_path = cm.append_rs_rank_series(metrics)
    if parquet_path:
        log.info("build_cohort_metrics: RS rank series → %s", parquet_path)
    else:
        log.warning("build_cohort_metrics: RS rank series not written (may already exist)")

    total = time.perf_counter() - t0
    log.info("build_cohort_metrics: total %.1fs", total)


if __name__ == "__main__":
    main()
