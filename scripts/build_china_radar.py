"""Build the standalone China Divergence Radar page + machine-readable emits.

Runs the divergence scan, accrues fired divergences into the falsification ledger, resolves
matured calls, renders site/china_radar.html, and emits site/chinaradar/{radar,ledger}.json
(radar.json is the context lens the intel bus reads). Callable standalone + importable.
CONTEXT-ONLY · never raises. See research/CHINA_INTEL_POWERHOUSE.md §4.
"""
from __future__ import annotations

import json
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
    from engine import china_radar as cr
    from engine import china_radar_ledger as ledger

    radar = cr.scan()
    ledger.accrue(radar)              # accrue today's divergences (keep-FIRST)
    track = ledger.track_record()    # resolve matured calls

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("china_radar.html.j2").render(radar=radar, ledger=track)
    (site / "china_radar.html").write_text(html)
    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            (site / a).write_text(src.read_text())
    log.info("wrote %s/china_radar.html (%d KB)", site, len(html) // 1024)

    out = site / "chinaradar"
    out.mkdir(parents=True, exist_ok=True)
    (out / "radar.json").write_text(
        json.dumps(radar or {}, ensure_ascii=False, separators=(",", ":"), default=str))
    (out / "ledger.json").write_text(
        json.dumps(track or {}, ensure_ascii=False, separators=(",", ":"), default=str))
    log.info("wrote %s/chinaradar/{radar,ledger}.json", site)
    return radar


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
