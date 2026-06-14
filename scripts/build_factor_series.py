"""Compute the factor portfolio return series -> site/factordata/factor_series.json.

Standalone, run BEFORE build_site in CI (build_site's factors page loads the JSON,
like it loads the IC scorecard). Walks ~38 month-ends calling compute_factors(asof=d),
so it is the heavier (~15s) factor step; kept separate so it can't slow/break the
macro build. Additive — any failure logs and returns 0. See engine/factor_series.py.

Usage: python -m scripts.build_factor_series
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")          # short trailing slices emit benign numpy RuntimeWarnings

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_factor_series")


def main() -> int:
    try:
        from engine.factor_series import compute_factor_series
        data = compute_factor_series()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("factor series engine failed: %s", e)
        return 0
    if not data:
        log.warning("no price caches — skipping factor series")
        return 0
    fdir = config.ROOT / "site" / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "factor_series.json").write_text(json.dumps(data, separators=(",", ":")))
    log.info("wrote factor_series.json (%d factors, %d rebalances)",
             len(data["factors"]), data["n_rebalances"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
