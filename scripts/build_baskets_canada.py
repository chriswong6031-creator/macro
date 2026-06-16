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

    fdir = site / "canadabasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))

    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets_canada.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(chart, separators=(",", ":")),
        generated_utc=built)
    (site / "baskets_canada.html").write_text(html)
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_canada.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
