"""Build the US Intelligence Hub — the central-command fusion of all five signal desks
(news · alt-data · divergence radar · factor buy-board · policy intent).

Emits site/intel_hub/hub.json (the command data the page + the future US Mastermind read)
AND renders site/intelligence_hub.html. Run AFTER build_intelligence + build_briefing +
build_policy_watch + build_radar_plus (so every feeder artifact exists). Standalone,
degrade-safe — absent inputs degrade to empty panels, never breaks the build.

Run:  python -m scripts.build_intel_hub
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine import intel_hub  # noqa: E402

log = logging.getLogger(__name__)


def build(write: bool = True) -> dict:
    hub = intel_hub.load_and_build(top=30)
    if not write:
        return hub
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    (site / "intel_hub").mkdir(parents=True, exist_ok=True)
    (site / "intel_hub" / "hub.json").write_text(json.dumps(hub, default=str))
    log.info("built site/intel_hub/hub.json — %d universe, %d actionable, EE=%d CT=%d",
             hub.get("n_universe", 0), hub.get("n_actionable", 0),
             hub.get("counts", {}).get("early_edge", 0), hub.get("counts", {}).get("crowded_top", 0))
    if not hub.get("command"):                 # surface an empty fuse in the daily.yml logs
        log.warning("intel hub: empty command — feeders (intelligence/policy/radar) may be missing")

    # render the page
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        env = Environment(loader=FileSystemLoader(str(root / "templates")),
                          autoescape=select_autoescape(["html", "xml"]))
        html = env.get_template("intelligence_hub.html.j2").render(
            hub=hub, built=datetime.now(timezone.utc).isoformat(), mode="intel_hub")
        (site / "intelligence_hub.html").write_text(html)
        log.info("built site/intelligence_hub.html")
    except Exception as e:  # noqa: BLE001
        log.error("intelligence_hub render failed: %s", e)
    return hub


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_intel_hub failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
