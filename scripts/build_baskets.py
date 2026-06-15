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

    # Engine-1 FLOW LENS (display-only characterization + the AI-handoff payload). It
    # ranks where cross-sectional flow is CONCENTRATING (PIT sectors + baskets), maps the
    # cross-group cluster, and carries the validated-honest verdict/caveats. flow.json is
    # the contract a downstream AI judge reads. Additive — never breaks the page.
    flow = None
    try:
        from engine.group_flow import compute_group_flows
        flow = compute_group_flows()
        if flow:
            (fdir / "flow.json").write_text(json.dumps(flow, separators=(",", ":"), default=str))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("group_flow lens failed: %s", e)

    # split the dense CHART (level matrix, for the interactive chart + live σ/sort table)
    # from the BASKETS metadata (thesis/members/rationale/perf/changelog/reference).
    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":")),
        chart_json=json.dumps(chart, separators=(",", ":")),
        flow=flow,
        generated_utc=built)
    (site / "baskets.html").write_text(html)
    # ship the TradingView Lightweight Charts runtime (Apache-2.0) used by the page
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
