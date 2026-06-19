"""Build the China thematic-baskets page -> site/baskets_china.html (+ chinabasketdata/baskets.json).

The A-share analogue of scripts/build_baskets.py. Reads data/baskets_china/membership.json +
the china_search close cache + the CSI 300 ETF via engine.baskets_china.compute_china_baskets()
and renders the same FactorWatch-style baskets view (sortable performance table, interactive
overlay chart, per-category cards + member drill), benchmarked to the CSI 300 (沪深300).
Additive — any failure logs and returns 0 so it can never break the rest of the site.

Usage: python -m scripts.build_baskets_china
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
log = logging.getLogger("build_baskets_china")


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.baskets_china import compute_china_baskets
        data = compute_china_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no china baskets (need data/baskets_china/membership.json + china_search cache) — skipping")
        return 0

    # THEME ROTATION DESK (regionalized) — score/label/recommend + 5-day rotation + act-now +
    # concentration, rides inside baskets_json; region alerts feed the page bell. Additive.
    theme_alerts_recent = []
    try:
        from engine.theme_scoring import compute_theme_intel
        ti = compute_theme_intel("china")
        if ti:
            data["theme_intel"] = ti
            from engine import theme_alerts
            theme_alerts.rebuild(ti, "china")
            theme_alerts_recent = theme_alerts.recent(30, as_of=ti.get("as_of"), region="china")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china theme desk failed: %s", e)

    fdir = site / "chinabasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))

    # split the dense CHART (level matrix, for the interactive chart + live σ/sort table)
    # from the BASKETS metadata (thesis/members/rationale/perf/changelog/reference).
    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets_china.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(chart, separators=(",", ":")),
        theme_alerts_json=json.dumps(theme_alerts_recent, separators=(",", ":")),
        generated_utc=built)
    (site / "baskets_china.html").write_text(html)
    # per-theme detail pages (site/basket_china/<id>.html) + the shared desk renderer
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, "china")
        deskjs = config.ROOT / "templates" / "baskets_desk.js"
        if deskjs.exists():
            (site / "baskets_desk.js").write_text(deskjs.read_text())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china theme detail pages failed: %s", e)
    # ship the TradingView Lightweight Charts runtime (Apache-2.0) used by the page
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_china.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
