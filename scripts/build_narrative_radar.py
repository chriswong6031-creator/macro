"""Build the China Narrative Basket Radar page.

Outputs:
  site/factordata/china_narrative_radar.json  — raw data (full basket list)
  site/narrative_radar.html                   — rendered page

Usage: python -m scripts.build_narrative_radar

Standalone: does NOT depend on any other China build.
Never raises — logs and returns 0 on failure so it cannot break the site.
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
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_narrative_radar")


def main() -> int:
    site = config.ROOT / "site"

    # ── 1. Engine ─────────────────────────────────────────────────────────────
    try:
        from engine.china_narrative_radar import build_radar
        data = build_radar()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_narrative_radar engine failed: %s", e)
        return 0

    if not data.get("baskets"):
        log.warning("china_narrative_radar: no baskets returned — skipping render")
        return 0

    # ── 2. Write JSON ─────────────────────────────────────────────────────────
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    json_path = fdir / "china_narrative_radar.json"
    json_path.write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)
    )
    log.info("wrote %s (%d baskets)", json_path, len(data["baskets"]))

    # ── 3. Render HTML ────────────────────────────────────────────────────────
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env   = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")),
        autoescape=True,
    )
    try:
        from scripts.build_vector import C  # shared palette
    except Exception:  # noqa: BLE001
        C = {}

    # Pass a JSON-safe string for the inline <script> data island
    data_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)

    html = env.get_template("china_narrative_radar.html.j2").render(
        data=data,
        data_json=data_json,
        generated_utc=built,
        C=C,
    )
    html_path = site / "narrative_radar.html"
    write_page(html_path, html)
    log.info(
        "wrote %s (%d KB, %d baskets)",
        html_path, len(html) // 1024, len(data["baskets"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
