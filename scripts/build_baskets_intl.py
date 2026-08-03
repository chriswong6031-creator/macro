"""Build the international thematic-baskets page -> site/baskets_intl.html (+ intlbasketdata/baskets.json).

The cross-country (developed ex-US + India) analogue of scripts/build_baskets_china.py. Reads
data/baskets_intl/membership.json + the intl_search close cache via
engine.baskets_intl.compute_intl_baskets() and renders the same FactorWatch-style baskets view,
benchmarked to a synthetic cap-weighted composite of the universe (the "Intl ex-US composite").

UNLIKE the other markets, the benchmark is built, not loaded: refresh_inputs() recomputes the
composite (data/intl/_INTLC.parquet) and the breadth tape (data/intl_breadth/breadth.parquet)
FIRST, so both this engine and the Theme Rotation Desk (engine.narrative_rotation._setup, via
lib.store) see the same benchmark and the concentration card has a real international breadth read.

Additive — any failure logs and returns 0 so it can never break the rest of the site.

Usage: python -m scripts.build_baskets_intl
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
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_baskets_intl")


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine import baskets_intl
        baskets_intl.refresh_inputs()                 # composite benchmark + breadth tape FIRST
        data = baskets_intl.compute_intl_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("intl baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no intl baskets (need data/baskets_intl/membership.json + intl_search cache) — skipping")
        return 0

    # THEME ROTATION DESK (regionalized) — score/label/recommend + 5-day rotation + act-now +
    # concentration, rides inside baskets_json; region alerts feed the alert ledger. Additive.
    try:
        from engine.theme_scoring import compute_theme_intel
        ti = compute_theme_intel("intl")
        if ti:
            data["theme_intel"] = ti
            from engine import theme_alerts
            theme_alerts.rebuild(ti, "intl")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("intl theme desk failed: %s", e)

    # 🔥 FORMING NARRATIVES (engine.narrative_emergence) — coherent, TIGHTENING cross-country
    # groups not yet in a basket, with clean-entry recommended tickers. Display-only, additive.
    emergence = None
    try:
        from engine.narrative_emergence import compute_emergence
        emergence = compute_emergence("intl")
        if emergence:
            from engine import emergence_alerts
            emergence_alerts.rebuild(emergence, "intl")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("intl narrative emergence failed: %s", e)

    fdir = site / "intlbasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    # baskets.json is written AFTER the sector_pulse block below — the merge adds the pulse_*
    # velocity/heat keys to theme_intel IN PLACE, so a write here froze a pre-merge snapshot on
    # disk while the rendered page (which inlines the same dict later) looked fine. Same defect
    # class already fixed for US in scripts/build_baskets.py and for China.
    # SECTOR PULSE — compact per-theme rotation data product. Also merges velocity/heat keys
    # into theme_intel for the rotation-scorecard page enhancements. Additive — never breaks build.
    try:
        if data.get("theme_intel"):
            from engine import sector_pulse as _sp
            _sp.write_pulse(data["theme_intel"], "intl", fdir)
            _sp.merge_pulse_into_theme_intel(data["theme_intel"], "intl")
            _sp.write_score_snapshot(data["theme_intel"], "intl")   # accrues the baskets_intl velocity stream
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_pulse intl hook failed: %s", e)

    # Post-pulse-merge so the artifact carries the pulse_* keys its DISK consumers read
    # (engine.conviction_accrual, the Mastermind brain_gateway ticker grounding), and
    # pre-chart-pop so they get BASKETS + CHART from one file. Unconditional and outside the
    # block above — a pulse failure is already caught there, so today's artifact always ships.
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))
    if emergence:
        (fdir / "narrative_emergence.json").write_text(
            json.dumps(emergence, separators=(",", ":"), ensure_ascii=False, default=str))

    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets_intl.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(chart, separators=(",", ":")),
        bench_en="Intl ex-US", bench_zh="国际(除美)",
        generated_utc=built)
    write_page(site / "baskets_intl.html", html)
    # per-theme detail pages (site/basket_intl/<id>.html) + the shared desk renderer
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, "intl", chart)
        deskjs = config.ROOT / "templates" / "baskets_desk.js"
        if deskjs.exists():
            (site / "baskets_desk.js").write_text(deskjs.read_text())
        ne = config.ROOT / "templates" / "forming_narratives.js"
        if ne.exists():
            (site / "forming_narratives.js").write_text(ne.read_text())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("intl theme detail pages failed: %s", e)
    # ship the TradingView Lightweight Charts runtime (Apache-2.0) used by the page
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_intl.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
