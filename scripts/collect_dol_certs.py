"""scripts/collect_dol_certs.py — CLI entry-point for DOL labor cert collection.

Collect-lane step (off the render critical path).  Downloads the newest quarterly
DOL PERM/LCA disclosure data not yet ingested and appends to the compact store
data/dol_certs/certs.parquet (runner-local, gitignored).

No-ops in seconds when no new quarterly file exists.

Usage:
    python -m scripts.collect_dol_certs
    python -m scripts.collect_dol_certs --programs lca
    python -m scripts.collect_dol_certs --dry-run
    python -m scripts.collect_dol_certs --store /path/to/custom/certs.parquet

Env override for store: DOL_CERTS_STORE=/path/to/certs.parquet
(Mirrors WARN_STORE / THETADATA_STORE pattern.)

WIRING NOTE (mirroring warn_notices.py pattern):
  Do NOT add this to scripts/collect.py until Phase-1 gates pass.
  The dag.yml entry is registered in the collect lane as a standalone step;
  it is safe to invoke nightly but does not block the engine lane.
  Invoke standalone:
      python -m scripts.collect_dol_certs

Exit 0 always (tolerant; missing store / network error → log + exit 0).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.dol_labor_certs import main  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    raise SystemExit(main())
