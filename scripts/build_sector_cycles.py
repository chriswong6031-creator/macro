"""Build the Sector Cycle Intelligence page -> site/sector_cycles.html.

A data-driven sibling of Cycle Intelligence (build_cycle.py): engine/sector_cycles
derives each US sector ETF's real-price series, auto-detected turns, cycle phase and
next-turn projection; this script binds the researched leg narratives
(data/sector_cycles/narratives.json), emits them as site/sector_cycles_data.js
(window.SECTOR_CYCLES + window.SECTOR_NARR), renders the page shell from
templates/sector_cycles.html.j2, and copies the page-specific assets. It reuses the
already-committed site/mm_charts.js + site/cycle.css (the shared cycle design system).

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

log = logging.getLogger("build_sector_cycles")

PAGE_ASSETS = ("sector_cycles.css", "sector_cycles.js")
# the shared cycle design system this page reuses — must exist in site/ (built by
# build_cycle.py and committed); copied from templates/ only if a refactor moves them.
SHARED_ASSETS = ("mm_charts.js", "cycle.css")


def _load_narratives(root: Path) -> dict:
    f = root / "data" / "sector_cycles" / "narratives.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("sector_cycles: narratives.json unreadable (%s) — page renders without narratives", e)
        return {}
    return doc.get("sectors", doc) if isinstance(doc, dict) else {}


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

    narr = _load_narratives(root)

    # data JS (loaded directly by the page — no fetch, works on file:// + preview)
    payload = ("window.SECTOR_CYCLES=" + json.dumps(data, separators=(",", ":")) + ";\n"
               + "window.SECTOR_NARR=" + json.dumps(narr, separators=(",", ":"), ensure_ascii=False) + ";\n")
    (site / "sector_cycles_data.js").write_text(payload, encoding="utf-8")

    # also publish the raw model for external consumers / debugging
    fdir = site / "sectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "sector_cycles.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,  # macro pages emit raw HTML; _navlinks uses |safe
    )
    html = env.get_template("sector_cycles.html.j2").render()
    (site / "sector_cycles.html").write_text(html, encoding="utf-8")

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
