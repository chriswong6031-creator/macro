"""Render the Cycle Intelligence page (templates/cycle.html.j2 -> site/cycle.html).

This page is a bespoke cross-cycle dashboard whose data, logic and styles live as
committed site/ assets — cycle_data.js (the curated 15-cycle dataset / single
source of truth), cycle_app.js (oscillator + projection synthesis + UI), cycle.css
(the design system) and mm_charts.js (a dependency-free, reusable SVG charting
engine, a deliberate upgrade path away from Plotly). The browser loads those
directly; this builder only re-renders the HTML shell so the shared navigation
(_navlinks.html.j2) and the theme/lang bootstrap stay in sync with the rest of the
site on every build.

mm_charts.js is reusable across pages — when a second page adopts it, promote it
to templates/ and add it to the shared static-asset copy list in build_site.py.
"""
from __future__ import annotations

import logging
import shutil

from jinja2 import Environment, FileSystemLoader

from lib import config

log = logging.getLogger(__name__)

# committed page assets (kept in site/); copied from templates/ only if a future
# refactor moves the canonical copy there — otherwise these are graceful no-ops.
PAGE_ASSETS = ("cycle.css", "mm_charts.js", "cycle_data.js", "cycle_app.js")


def main() -> int:
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,  # macro pages emit raw HTML; _navlinks uses |safe
    )
    html = env.get_template("cycle.html.j2").render()
    (site / "cycle.html").write_text(html, encoding="utf-8")

    for asset in PAGE_ASSETS:
        src = root / "templates" / asset
        if src.exists():
            shutil.copy2(src, site / asset)

    log.info("built site/cycle.html (15-cycle dashboard)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
