"""Build the China Special Situations desk page + machine-readable emits.

Runs the special-situations desk engine, writes site/chinaspecialdata/special.json,
renders site/china_special_situations.html. Callable standalone + importable.
CONTEXT-ONLY · never raises. See research/CHINA_INTEL_HUB_MASTERPLAN.md §W2.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config, site_assets
from lib.pages import write_page

log = logging.getLogger(__name__)

ASSETS = ("theme.css", "theme.js")


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def build() -> dict | None:
    from engine import china_special_situations as css

    snap = css.build()   # writes site/chinaspecialdata/special.json

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

    # render with snap (or empty dict so the template degrades gracefully)
    html = env.get_template("china_special_situations.html.j2").render(
        special=snap or {}
    )
    write_page(site / "china_special_situations.html", html)

    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            site_assets.copy_asset(a, src, site)

    log.info("wrote %s/china_special_situations.html (%d KB)",
             site, len(html) // 1024)
    return snap


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
