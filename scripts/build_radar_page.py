"""Build the dedicated Divergence Radar page -> site/radar.html.

Pure render — no engine compute here. The page is client-fetched: it reads
site/basketdata/radar.json (engine/radar.py, written by build_baskets) and
narrative_brain.json (engine/narrative_brain.py) via site/radar_panel.js, so this
just renders the static shell + lifecycle pipeline. Additive + resilient — returns 0
even on failure so it never aborts the daily build. Run after build_baskets so the
radar JSON exists.
"""
from __future__ import annotations

import logging

from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page

log = logging.getLogger(__name__)


def main() -> int:
    try:
        env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
        html = env.get_template("radar.html.j2").render()
        write_page(config.ROOT / "site" / "radar.html", html)
        log.info("wrote site/radar.html (%d KB)", len(html) // 1024)
    except Exception as e:  # noqa: BLE001 — additive, never abort the build
        log.error("build_radar_page failed: %s", e)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
