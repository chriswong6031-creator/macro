"""Build the single-name Cremers-Weinbaum IV-spread context surface.

  1. ACCRUE — append today's per-underlying call−put IV spread to the forward snapshot
     ledger (data/options_ivspread/snapshots.parquet). Run daily, this is the apparatus
     that eventually gives scripts/validate_options_ivspread.py the history to earn a verdict.
  2. EMIT — site/options_ivspread/latest.json (display-only context; the gate stays closed
     until the panel is wide/long enough — see engine/options_ivspread).

No-op-safe: degrades cleanly if the GEX chain snapshots aren't present.
"""
from __future__ import annotations

import json
import logging

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import options_ivspread as S  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_options_ivspread")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    added = S.snapshot()                       # accrue today's spread into the ledger
    payload = S.build_snapshot()
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out = site / "options_ivspread"
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(payload, separators=(",", ":"), default=float))
    log.info("options_ivspread: accrued %d rows, emitted %d names (scored=%s, %s)",
             added, payload["n"], payload["scored"], payload["gate_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
