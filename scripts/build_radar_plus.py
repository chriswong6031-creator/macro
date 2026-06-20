"""Build the additive radar upgrade (Phase 2):
  • enrich site/basketdata/radar.json with edge_score + confirm legs + regime + decay
  • emit site/basketdata/radar_ticker.json (per-ticker divergence)

Runs AFTER build_baskets (which emits radar.json) + build_alt_data (mastermind.json) +
build_news/build_intelligence. Additive + degrade-safe; never aborts the build.

Run:  python -m scripts.build_radar_plus
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine import radar_plus, radar_ticker  # noqa: E402

log = logging.getLogger(__name__)


def build(write: bool = True) -> dict:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out = {"radar_enriched": False, "radar_ticker": 0}

    radar_p = site / "basketdata" / "radar.json"
    if radar_p.exists():
        try:
            radar = json.loads(radar_p.read_text())
            radar_plus.enrich(radar)
            if write:
                radar_p.write_text(json.dumps(radar, default=str))
            top = (radar.get("edge_ranked") or [{}])[0]
            out["radar_enriched"] = True
            log.info("radar enriched: %d flags, top edge %s (%s), regime mult %s",
                     len(radar.get("flags", [])), top.get("edge_score"), top.get("basket"),
                     (radar.get("regime") or {}).get("mult"))
        except Exception as e:  # noqa: BLE001
            log.error("radar enrich failed: %s", e)
    else:
        log.warning("radar.json absent — skipping enrich")

    try:
        rt = radar_ticker.build()
        if write:
            (site / "basketdata").mkdir(parents=True, exist_ok=True)
            (site / "basketdata" / "radar_ticker.json").write_text(json.dumps(rt, default=str))
        out["radar_ticker"] = rt.get("n", 0)
        log.info("radar_ticker: %d names (%d divergences)", rt.get("n", 0), rt.get("n_divergences", 0))
    except Exception as e:  # noqa: BLE001
        log.error("radar_ticker failed: %s", e)
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_radar_plus failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
