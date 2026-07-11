"""Build the Sector Cycle Intelligence page -> site/sector_cycles.html.

A data-driven sibling of Cycle Intelligence (build_cycle.py): engine/sector_cycles
derives each US sector ETF's real-price series, auto-detected turns, cycle phase and
next-turn projection; this script binds the researched leg narratives
(data/sector_cycles/narratives.json), emits them as three split data files:
  - site/sector_cycles_data.js      -> window.SECTOR_CYCLES only (core, ~2MB)
  - site/sector_cycles_narr_data.js -> window.SECTOR_NARR only (lazy-loaded, ~1.8MB)
  - site/sector_cycles_dna_data.js  -> window.SECTOR_DNA only (lazy-loaded, ~330KB)
NARR and DNA are loaded lazily after boot (only used in tap-to-focus panels / dnaHTML).
Renders the page shell from templates/sector_cycles.html.j2, copies the page-specific
assets. Reuses the already-committed site/mm_charts.js + site/cycle.css (the shared
cycle design system).

Additive — any failure is logged and returns 0 so it can never break the rest of the
site build.

Usage: python -m scripts.build_sector_cycles
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
from lib.pages import write_page  # noqa: E402

log = logging.getLogger("build_sector_cycles")

PAGE_ASSETS = ("sector_cycles.css", "sector_cycles.js")
# the shared cycle design system this page reuses — must exist in site/ (built by
# build_cycle.py and committed); copied from templates/ only if a refactor moves them.
SHARED_ASSETS = ("mm_charts.js", "cycle.css")


def _load_narratives(root: Path) -> dict:
    """NARR keyed by the chart's series id: sectors by ticker.lower() (xlk…), baskets
    by the engine's "b-"+membership-key (b-mag7…). Merges the file's sectors+baskets.

    W2.1: epoch-aware — resolves narratives.<epoch>.json for the engine's current epoch,
    falling back to the legacy un-suffixed file (tagged tr_v0). Zero behaviour change
    today (no flip → legacy file resolves exactly as before)."""
    from scripts._narrative_epoch import resolve_narratives
    res = resolve_narratives("sector_cycles", root / "data" / "sector_cycles", "narratives")
    if res["stale_quarantined"]:
        log.warning("sector_cycles: narratives stale-quarantined (epoch %s) — page renders without",
                    res["epoch"])
    return res["map"]


def _load_dna(root: Path) -> dict:
    """SECTOR_DNA (the front-loaded "history rhymes" / cycle-cause profiles), same id keying as
    narratives: sectors by ticker.lower(), baskets by "b-"+key. Optional — page renders without.

    W2.1: epoch-aware (resolves cycle_dna.<epoch>.json, falls back to legacy cycle_dna.json)."""
    from scripts._narrative_epoch import resolve_narratives
    res = resolve_narratives("sector_cycles", root / "data" / "sector_cycles", "cycle_dna")
    if res["stale_quarantined"]:
        log.warning("sector_cycles: cycle_dna stale-quarantined (epoch %s) — rendering without DNA",
                    res["epoch"])
    return res["map"]


def main() -> int:
    root = config.ROOT
    try:
        site = root / config.load()["storage"]["site_dir"]
    except Exception:  # noqa: BLE001
        site = root / "site"
    site.mkdir(parents=True, exist_ok=True)

    try:
        from engine import sector_cycles
        data = sector_cycles.compute()
    except Exception as e:  # noqa: BLE001
        log.exception("sector_cycles engine failed: %s", e)
        return 0
    if not data or not data.get("sectors"):
        log.warning("sector_cycles: no data — skipped")
        return 0

    # W0.2: append prospective forward-log stamp (keep-FIRST per (date,id), additive)
    try:
        from engine.cycle_forward_log import append_forward_log
        n_stamped = append_forward_log(data, "sector_cycles")
        log.info("sector_cycles: forward log: %d rows stamped", n_stamped)
    except Exception as e:  # noqa: BLE001
        log.warning("sector_cycles: forward log append skipped: %s", e)

    narr = _load_narratives(root)
    dna = _load_dna(root)

    # W3.4: enrich NARR map with TTL / staleness / archetype-check metadata
    try:
        from scripts._narrative_ttl import enrich_narr_ttl
        narr = enrich_narr_ttl(narr)
        log.info("sector_cycles: narrative TTL enrichment applied")
    except Exception as e:  # noqa: BLE001
        log.warning("sector_cycles: TTL enrichment skipped: %s", e)

    # data JS split into three files for lazy loading:
    #   sector_cycles_data.js      -> SECTOR_CYCLES (core, loaded at boot)
    #   sector_cycles_narr_data.js -> SECTOR_NARR (lazy, only needed in focus panels)
    #   sector_cycles_dna_data.js  -> SECTOR_DNA  (lazy, only needed in dnaHTML())
    (site / "sector_cycles_data.js").write_text(
        "window.SECTOR_CYCLES=" + json.dumps(data, separators=(",", ":")) + ";\n",
        encoding="utf-8")
    (site / "sector_cycles_narr_data.js").write_text(
        "window.SECTOR_NARR=" + json.dumps(narr, separators=(",", ":"), ensure_ascii=False) + ";\n",
        encoding="utf-8")
    (site / "sector_cycles_dna_data.js").write_text(
        "window.SECTOR_DNA=" + json.dumps(dna, separators=(",", ":"), ensure_ascii=False) + ";\n",
        encoding="utf-8")

    # also publish the raw model for external consumers / debugging
    fdir = site / "sectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "sector_cycles.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,  # macro pages emit raw HTML; _navlinks uses |safe
    )
    try:                                       # _navlinks references t()/td()/tr() i18n globals
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    html = env.get_template("sector_cycles.html.j2").render()
    write_page(site / "sector_cycles.html", html, encoding="utf-8")

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
                log.warning("sector_cycles: shared asset %s missing from site/ — run build_cycle first", asset)

    log.info("built site/sector_cycles.html (%d sectors, %d with narratives)",
             len(data["sectors"]), len(narr))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
