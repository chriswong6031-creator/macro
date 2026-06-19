"""Build the Canada thematic-baskets page -> site/baskets_canada.html (+ canadabasketdata/baskets.json).

The Canada analogue of scripts/build_baskets_china.py. Reads data/baskets_canada/membership.json +
the canada_search close cache + the benchmark via engine.baskets_canada.compute_canada_baskets() and renders the same
FactorWatch-style baskets view. Additive — any failure logs and returns 0 so it can never
break the rest of the site.

Usage: python -m scripts.build_baskets_canada
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
log = logging.getLogger("build_baskets_canada")


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.baskets_canada import compute_canada_baskets
        data = compute_canada_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("canada baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no canada baskets (need data/baskets_canada/membership.json + canada_search cache) — skipping")
        return 0

    # THEME ROTATION DESK (regionalized) + region alerts (additive)
    theme_alerts_recent = []
    try:
        from engine.theme_scoring import compute_theme_intel
        ti = compute_theme_intel('canada')
        if ti:
            data['theme_intel'] = ti
            from engine import theme_alerts
            theme_alerts.rebuild(ti, 'canada')
            theme_alerts_recent = theme_alerts.recent(30, as_of=ti.get('as_of'), region='canada')
    except Exception as e:  # noqa: BLE001
        log.error('canada theme desk failed: %s', e)

    fdir = site / "canadabasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))

    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets_canada.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(chart, separators=(",", ":")),
        theme_alerts_json=json.dumps(theme_alerts_recent, separators=(",", ":")),
        generated_utc=built)
    (site / "baskets_canada.html").write_text(html)
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, 'canada')
        deskjs = config.ROOT / 'templates' / 'baskets_desk.js'
        if deskjs.exists():
            (site / 'baskets_desk.js').write_text(deskjs.read_text())
    except Exception as e:  # noqa: BLE001
        log.error('canada theme detail pages failed: %s', e)
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_canada.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
