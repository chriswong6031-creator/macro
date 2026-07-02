"""Build the Country Cycle Intelligence page -> site/country_cycles.html.

The international sibling of scripts/build_sector_cycles.py: engine/country_cycles derives
every country / region ETF's real-USD-price cycle (rebased price + 0-100 oscillator,
auto-detected turns, the 5-phase wheel, a median-half-cycle next-turn projection, RS vs
SPY). This script binds any researched leg narratives (data/country_cycles/narratives.json)
and cycle-DNA profiles (data/country_cycles/cycle_dna.json), emits site/country_cycles_data.js
(window.SECTOR_CYCLES + window.SECTOR_NARR + window.SECTOR_DNA — the SAME globals the shared
sector_cycles.js consumes), publishes the raw model under site/countrycyclesdata/, renders
templates/country_cycles.html.j2, and copies the shared cycle assets.

Reuses the already-built site/sector_cycles.{css,js} + mm_charts.js + cycle.css — the shared
cycle design system — so this page reads identically to the US and China cycle pages.

Additive — any failure is logged and returns 0 so it can never break the rest of the site build.

Usage: python -m scripts.build_country_cycles
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger("build_country_cycles")

PAGE_ASSETS = ("sector_cycles.css", "sector_cycles.js")   # SHARED with the US/China cycle pages
SHARED_ASSETS = ("mm_charts.js", "cycle.css")             # the shared cycle design system


def _load_narratives(root: Path) -> dict:
    """NARR keyed by the chart series id: countries by ticker.lower() (ewj…), aggregates
    likewise (efa…). Merges the file's `sectors` + `baskets` maps. Optional."""
    f = root / "data" / "country_cycles" / "narratives.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("country_cycles: narratives.json unreadable (%s) — rendering without", e)
        return {}
    if not isinstance(doc, dict):
        return {}
    narr = dict(doc.get("sectors", {}))
    narr.update(doc.get("baskets", {}) or {})
    return narr


def _load_dna(root: Path) -> dict:
    """SECTOR_DNA cycle-cause profiles, same id keying as narratives (ticker.lower())."""
    f = root / "data" / "country_cycles" / "cycle_dna.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("country_cycles: cycle_dna.json unreadable (%s) — rendering without DNA", e)
        return {}
    if not isinstance(doc, dict):
        return {}
    dna = dict(doc.get("sectors", {}))
    dna.update(doc.get("baskets", {}) or {})
    return dna


def main() -> int:
    root = config.ROOT
    try:
        site = root / config.load()["storage"]["site_dir"]
    except Exception:  # noqa: BLE001
        site = root / "site"
    site.mkdir(parents=True, exist_ok=True)

    try:
        from engine import country_cycles
        data = country_cycles.compute()
    except Exception as e:  # noqa: BLE001
        log.exception("country_cycles engine failed: %s", e)
        return 0
    if not data or not data.get("sectors"):
        log.warning("country_cycles: no data — skipped")
        return 0

    # W0.2: append prospective forward-log stamp (keep-FIRST per (date,id), additive)
    try:
        from engine.cycle_forward_log import append_forward_log
        n_stamped = append_forward_log(data, "country_cycles")
        log.info("country_cycles: forward log: %d rows stamped", n_stamped)
    except Exception as e:  # noqa: BLE001
        log.warning("country_cycles: forward log append skipped: %s", e)

    narr = _load_narratives(root)
    dna = _load_dna(root)

    # data JS (loaded directly by the page — no fetch, works on file:// + preview)
    payload = ("window.SECTOR_CYCLES=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
               + "window.SECTOR_NARR=" + json.dumps(narr, separators=(",", ":"), ensure_ascii=False) + ";\n"
               + "window.SECTOR_DNA=" + json.dumps(dna, separators=(",", ":"), ensure_ascii=False) + ";\n")
    (site / "country_cycles_data.js").write_text(payload, encoding="utf-8")

    # also publish the raw model for external consumers / debugging
    fdir = site / "countrycyclesdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "country_cycles.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,  # macro pages emit raw HTML; _navlinks uses |safe
    )
    try:                                       # _navlinks references t()/td()/tr() i18n globals
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    html = env.get_template("country_cycles.html.j2").render()
    (site / "country_cycles.html").write_text(html, encoding="utf-8")

    for asset in PAGE_ASSETS:
        src = root / "templates" / asset
        if src.exists():
            shutil.copy2(src, site / asset)
    for asset in SHARED_ASSETS:
        if not (site / asset).exists():
            src = root / "templates" / asset
            if src.exists():
                shutil.copy2(src, site / asset)
            else:
                log.warning("country_cycles: shared asset %s missing — run build_cycle first", asset)

    log.info("built site/country_cycles.html (%d countries, %d aggregates, %d narratives, %d dna)",
             len(data["sectors"]), len(data.get("baskets", [])), len(narr), len(dna))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
