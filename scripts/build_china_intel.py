"""Build the China Intelligence hub + the Mastermind transmission feed.

Fans the four China intelligence surfaces (News · PBoC/Policy · Alt-Data · Divergence
Radar) into the schema-versioned china_intel.briefing.v1 (engine/china_intel_bus.build →
site/china_intel/{briefing,digest}.json), then renders the hub page site/china_intel.html.
This is the connector the future China Mastermind consumes. Callable standalone +
importable. CONTEXT-ONLY · never raises. See research/CHINA_INTEL_POWERHOUSE.md §5.
"""
from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config

log = logging.getLogger(__name__)

ASSETS = ("theme.css", "theme.js")


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def build() -> dict | None:
    from engine import china_intel_bus

    b = china_intel_bus.build()    # writes site/china_intel/{briefing,digest}.json
    if not b:
        log.error("china intel bus produced no briefing; skipping hub render")
        return None

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("china_intel.html.j2").render(b=b)
    (site / "china_intel.html").write_text(html)
    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            (site / a).write_text(src.read_text())
    log.info("wrote %s/china_intel.html (%d surfaces: %s)",
             site, len(b.get("surfaces_present", [])), b.get("surfaces_present"))
    return b


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
