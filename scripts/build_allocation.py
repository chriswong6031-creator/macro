"""Build the Thematic Narrative-Rotation page -> site/allocation.html
(+ site/allocationdata/allocation.json).

Reads engine.narrative_rotation.compute_narrative_rotation() (which itself reads the
baskets membership + price caches + the Phase-0 validation artifact) and renders the
"where do I allocate across themes?" decision page: the prevailing narrative, a suggested
trend-following allocation, the durability/crowding scorecard, the rotation radar, the
honest 27-year workhorse backtest, and the AI handoff. Additive — any failure logs and
returns 0 so it never breaks the rest of the site.

Run standalone (`python -m scripts.build_allocation`) or hooked from build_baskets.py so
it ships on every CI run without needing a new daily.yml step (PAT lacks workflow scope).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_allocation")


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.narrative_rotation import compute_narrative_rotation
        data = compute_narrative_rotation()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("narrative_rotation engine failed: %s", e)
        return 0
    if not data:
        log.warning("no narrative_rotation data (need baskets membership + caches) — skipping")
        return 0

    fdir = site / "allocationdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "allocation.json").write_text(json.dumps(data, separators=(",", ":"), default=str))

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("allocation.html.j2").render(
        d=data, data_json=json.dumps(data, separators=(",", ":")), generated_utc=built)
    (site / "allocation.html").write_text(html)
    log.info("wrote %s/allocation.html (%d themes, headline=%s)",
             site, data.get("n_themes", 0),
             (data.get("headline") or {}).get("name", "—"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
