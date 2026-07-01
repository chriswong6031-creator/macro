"""Render the Global Market Cycles page (templates/markets.html.j2 -> site/markets.html).

Sibling of build_cycle.py: a bespoke cycle-family dashboard (nine national equity
markets on one clock) whose data, logic and styles live as committed site/ assets —
markets_data.js (the curated dataset), markets_app.js (synthesis + UI), markets_i18n.js
(bilingual copy), cycle.css (the shared cycle design system) and mm_charts.js (the
dependency-free SVG charting engine). The browser loads those directly; this builder
only re-renders the HTML shell so the shared navigation (_navlinks.html.j2) and the
theme/lang bootstrap stay in sync with the rest of the site on every build.

Previously markets.html was a hand-committed static page, so its nav froze at the
last manual sync (#617) and missed the Research mega-menu. Templatising it onto the
shared _site_nav include is what lets nav changes reach it automatically from now on.
"""
from __future__ import annotations

import logging
import shutil

from jinja2 import Environment, FileSystemLoader

from lib import config

log = logging.getLogger(__name__)

# committed page assets (kept in site/); copied from templates/ only if a future
# refactor moves the canonical copy there — otherwise these are graceful no-ops.
PAGE_ASSETS = ("cycle.css", "mm_charts.js", "markets_i18n.js", "markets_data.js", "markets_app.js")


def main() -> int:
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,  # macro pages emit raw HTML; _navlinks uses |safe
    )
    try:                                       # _navlinks references t()/td()/tr() i18n globals
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    html = env.get_template("markets.html.j2").render()
    (site / "markets.html").write_text(html, encoding="utf-8")

    for asset in PAGE_ASSETS:
        src = root / "templates" / asset
        if src.exists():
            shutil.copy2(src, site / asset)

    log.info("built site/markets.html (global market cycles)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
