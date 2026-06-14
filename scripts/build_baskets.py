"""Build the thematic-baskets page -> site/baskets.html (+ basketdata/baskets.json).

Standalone (clones build_discovery.py / build_seasonality.py): reads
data/baskets/membership.json + the price caches + SPY via engine.baskets.compute_baskets()
and renders the FactorWatch-style baskets view — a sortable performance table
(1d/5d/20d/60d/YTD, raw or relative-to-SPY), a cumulative spark per basket, a
per-basket members drill and a dated membership changelog. Additive — any failure
logs and returns 0 so it can never break the rest of the site.

Usage: python -m scripts.build_baskets
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
log = logging.getLogger("build_baskets")


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.baskets import compute_baskets
        data = compute_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no baskets (need data/baskets/membership.json + price caches) — skipping")
        return 0

    fdir = site / "basketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=td, tr=tr, zip=zip)
    html = env.get_template("baskets.html.j2").render(data=data, built=built)
    (site / "baskets.html").write_text(html)
    log.info("wrote %s/baskets.html (%d baskets, %d KB)",
             site, len(data["baskets"]), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
