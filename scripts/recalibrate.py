"""Regenerate the signal-ladder calibration (data/regime/ladder_calibration.json).

Walk-forward over sector ETFs + a sample of top holdings; ~10 minutes of
compute, so this runs weekly (Saturday workflow), not nightly. The sector
drill-down pages read the cached JSON.

Usage: python -m scripts.recalibrate
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.sector_holdings import top10_union  # noqa: E402
from engine.cycles import calibrate_ladder  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("recalibrate")


def main() -> int:
    panel = {}
    for t in config.load()["sponsors"]["sector_funds"] + ["SPY", "IWM"]:
        df = store.read("yahoo", t)
        if df is not None:
            panel[t] = df["close"]
    for t in top10_union()[::4]:  # every 4th holding keeps runtime ~10 min
        df = store.read("stocks", t)
        if df is not None and len(df) > 1500:
            panel[t] = df["close"]
    log.info("calibrating ladder on %d instruments", len(panel))
    cal = calibrate_ladder(panel)
    p = config.data_dir() / "regime" / "ladder_calibration.json"
    with open(p, "w") as f:
        json.dump(cal, f, indent=1)
    log.info("wrote %s: %s", p, {k: v["n"] for k, v in cal.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
