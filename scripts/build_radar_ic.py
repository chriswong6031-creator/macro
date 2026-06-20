"""Build script: accrue today's radar edge snapshots + compute IC, write outputs.

Usage:
    python -m scripts.build_radar_ic
    python -m scripts.build_radar_ic --horizon 63   # ~3-month horizon

Writes:
    data/radar/edge_snapshots.jsonl   (append-only; idempotent per date+subject)
    data/radar/radar_ic.json          (full IC result)
    site/basketdata/radar_ic.json     (compact copy for the frontend)

Never raises — degrade-safe (emits n_matured:0 on first run).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

# Make sure the repo root is on the path when run as `python -m scripts.build_radar_ic`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import radar_ic as ric
from lib import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main(horizon_d: int = ric._HORIZON_D, root: Path | None = None) -> dict:
    root = root or config.ROOT
    today = date.today()

    # 1. Accrue today's snapshots
    n_new = ric.snapshot(today=today, root=root)
    log.info("build_radar_ic: %d new snapshot rows for %s", n_new, today)

    # 2. Compute IC over all matured snapshots
    result = ric.compute_ic(today=today, horizon_d=horizon_d, root=root)
    log.info(
        "build_radar_ic: n_snapshots=%d  n_matured=%d  ic_all=%s",
        result["n_snapshots"], result["n_matured"], result["ic_all"],
    )

    # 3. Write outputs
    try:
        data_out = root / "data" / "radar" / "radar_ic.json"
        data_out.parent.mkdir(parents=True, exist_ok=True)
        data_out.write_text(json.dumps(result, indent=2, default=str))

        site_out = root / "site" / "basketdata" / "radar_ic.json"
        site_out.parent.mkdir(parents=True, exist_ok=True)
        site_out.write_text(json.dumps(result, separators=(",", ":"), default=str))

        log.info("build_radar_ic: wrote %s and %s", data_out, site_out)
    except Exception as e:  # noqa: BLE001
        log.warning("build_radar_ic: write failed: %s", e)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build radar IC validation harness.")
    parser.add_argument("--horizon", type=int, default=ric._HORIZON_D,
                        help=f"Forward horizon in calendar days (default: {ric._HORIZON_D})")
    args = parser.parse_args()
    r = main(horizon_d=args.horizon)
    print(json.dumps({k: r[k] for k in ("schema", "as_of", "n_snapshots", "n_matured",
                                         "ic_all", "note")}, indent=2))
