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

    # 🔥 FORMING NARRATIVES (engine.narrative_emergence) — coherent, TIGHTENING A-share
    # groups not yet in a basket, with clean-entry recommended tickers. emergence_alerts
    # diffs vs prior + fires a "narrative_forming" event. Display-only, additive, noisy.
    emergence = None
    try:
        from engine.narrative_emergence import compute_emergence
        emergence = compute_emergence("china")
        if emergence:
            from engine import emergence_alerts
            emergence_alerts.rebuild(emergence, "china")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china narrative emergence failed: %s", e)

    # Validated sleeve-size chip (W6-CN Fix 1) — thread risk_radar_intl gross_factor into the
    # baskets JSON header as a DISPLAY chip. Regime sizes sleeves, never vetoes names.
    try:
        from engine.risk_radar_intl import cn_sleeve_chip
        data["sleeve_chip"] = cn_sleeve_chip()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china baskets: sleeve chip failed (%s)", e)

    # attach each basket's cycle record (engine.china_sector_cycles, written by
    # scripts.build_china_sector_cycles) so BOTH the overview payload (baskets.json + the
    # rendered page, e.g. the Leadership Health "contested" read) AND the per-theme detail
    # pages can see it. MUST run BEFORE the JSON write / overview render below — it used to
    # sit after them, so only detail pages ever saw cycle data (the stale-label problem).
    # Optional + ordering-safe: absent map (cycles not built yet) simply omits the record.
    try:
        cyc_map_p = site / "chinasectordata" / "sector_cycles_basket_map.json"
        if cyc_map_p.exists():
            cyc_map = json.loads(cyc_map_p.read_text())
            for b in data.get("baskets", []):
                cyc = cyc_map.get(b.get("id"))
                if cyc:
                    b["cycle"] = cyc
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china baskets cycle-map attach failed: %s", e)

    fdir = site / "chinabasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))
    if emergence:
        (fdir / "narrative_emergence.json").write_text(
            json.dumps(emergence, separators=(",", ":"), ensure_ascii=False, default=str))

    # split the dense CHART (level matrix, for the interactive chart + live σ/sort table)
    # from the BASKETS metadata (thesis/members/rationale/perf/changelog/reference).
    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets_china.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(chart, separators=(",", ":")),
        theme_alerts_json=json.dumps(theme_alerts_recent, separators=(",", ":")),
        bench_en="CSI 300", bench_zh="沪深300",
        generated_utc=built)
    (site / "baskets_china.html").write_text(html)

    # per-theme detail pages (site/basket_china/<id>.html) + the shared desk renderer
    # (basket cycle records were attached above, before the JSON write, so the detail
    # builder still sees b["cycle"] exactly as before)
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, "china")
        deskjs = config.ROOT / "templates" / "baskets_desk.js"
        if deskjs.exists():
            (site / "baskets_desk.js").write_text(deskjs.read_text())
        ne = config.ROOT / "templates" / "forming_narratives.js"
        if ne.exists():
            (site / "forming_narratives.js").write_text(ne.read_text())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china theme detail pages failed: %s", e)
    # ship the TradingView Lightweight Charts runtime (Apache-2.0) used by the page
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_china.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)

    # W3.8 — FREEZE China (curated) basket levels + membership hashes (append-only, PIT).
    # chart was popped from data above and is still in scope.
    try:
        from engine.basket_freeze import freeze_domain, FreezeSkipped
        from engine.baskets_china import _membership as _cn_mem, _closes as _cn_closes
        _cn_mem_data = _cn_mem()
        try:
            _cn_cl = _cn_closes()
        except Exception:  # noqa: BLE001
            _cn_cl = None
        _freeze_result = freeze_domain("china", {"chart": chart}, _cn_cl, _cn_mem_data)
        log.info("basket_freeze[china]: %s", _freeze_result)
    except FreezeSkipped as e:
        log.error("basket_freeze[china]: SKIPPED (churn guard): %s", e)
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[china]: failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
