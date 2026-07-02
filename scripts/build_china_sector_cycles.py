"""Build the China Sector Cycle Intelligence page -> site/sector_cycles_china.html.

The China analogue of scripts/build_sector_cycles.py: engine/china_sector_cycles derives every
Shenwan (申万) L1 sector index AND every curated A-share thematic basket's real-price cycle
(rebased price + 0-100 oscillator, auto-detected turns, the 5-phase wheel, a median-half-cycle
next-turn projection, RS vs the Shanghai Composite, the washout↔euphoria signature, and — for
the four GS-style sectors — the evidence-gated conditional forward odds from
engine/china_sector_pathway). This script binds any researched narratives
(data/china_sector_cycles/narratives.json), emits site/sector_cycles_china_data.js
(window.SECTOR_CYCLES + window.SECTOR_NARR), the raw model under site/chinasectordata/, renders
templates/sector_cycles_china.html.j2, copies the shared cycle assets, and appends today's
signal to the point-in-time forward log so the calls can be graded over time.

Also writes site/chinasectordata/sector_cycles_basket_map.json — id -> compact cycle record —
which scripts/build_baskets_china.py reads to embed a cyclical mini-chart on each per-theme page.

Additive — any failure is logged and returns 0 so it can never break the rest of the site build.

Usage: python -m scripts.build_china_sector_cycles
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

log = logging.getLogger("build_china_sector_cycles")

PAGE_ASSETS = ("sector_cycles.css", "sector_cycles.js")   # SHARED with the US cycles page
SHARED_ASSETS = ("mm_charts.js", "cycle.css")             # the shared cycle design system


def _load_narratives(root: Path) -> dict:
    """NARR keyed by the chart series id: sectors by Shenwan code (801080…), baskets by the
    engine's "b-"+membership-key (b-cn_semis…). Optional — page renders without it."""
    f = root / "data" / "china_sector_cycles" / "narratives.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("china_sector_cycles: narratives.json unreadable (%s) — rendering without", e)
        return {}
    if not isinstance(doc, dict):
        return {}
    narr = dict(doc.get("sectors", {}))
    for k, v in (doc.get("baskets", {}) or {}).items():
        narr["b-" + k] = v
    return narr


def _load_dna(root: Path) -> dict:
    """SECTOR_DNA cycle-cause profiles, same id keying as narratives (Shenwan code / "b-"+key)."""
    f = root / "data" / "china_sector_cycles" / "cycle_dna.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("china_sector_cycles: cycle_dna.json unreadable (%s) — rendering without DNA", e)
        return {}
    if not isinstance(doc, dict):
        return {}
    dna = dict(doc.get("sectors", {}))
    for k, v in (doc.get("baskets", {}) or {}).items():
        dna["b-" + k] = v
    return dna


def _basket_cycle_map(data: dict) -> dict:
    """A compact per-basket cycle record (membership-key -> {price, turns, now, proj, signature})
    for the per-theme detail pages — small enough to inline on every basket_china page."""
    out = {}
    for b in data.get("baskets", []):
        bid = b.get("basket_id")
        if not bid:
            continue
        nw = b.get("now") or {}
        out[bid] = {
            "name": b.get("name"), "name_zh": b.get("name_zh"), "accent": b.get("accent"),
            "asOf": (data.get("meta") or {}).get("asOf"),
            "today": (data.get("meta") or {}).get("today"),
            "xDomain": (data.get("meta") or {}).get("xDomain"),
            "price": b.get("price"), "turns": b.get("turns"), "proj": b.get("proj"),
            "phases": data.get("phases"),
            "now": {k: nw.get(k) for k in ("phase", "phaseLabel", "pos", "signal", "above200d",
                                           "ret_win_pct", "rs_63d", "rs_rank", "lastTrough",
                                           "lastPeak", "signature")},
        }
    return out


def main() -> int:
    root = config.ROOT
    try:
        site = root / config.load()["storage"]["site_dir"]
    except Exception:  # noqa: BLE001
        site = root / "site"
    site.mkdir(parents=True, exist_ok=True)

    try:
        from engine import china_sector_cycles as ccc
        data = ccc.compute()
    except Exception as e:  # noqa: BLE001
        log.exception("china_sector_cycles engine failed: %s", e)
        return 0
    if not data or not data.get("sectors"):
        log.warning("china_sector_cycles: no data (run collectors.china_sectors first) — skipped")
        return 0

    narr = _load_narratives(root)
    dna = _load_dna(root)

    # Validated sleeve-size chip (W6-CN Fix 1) — thread risk_radar_intl gross_factor into the
    # sector cycles data payload as a DISPLAY chip. Regime sizes sleeves, never vetoes names.
    try:
        from engine.risk_radar_intl import cn_sleeve_chip
        data["sleeve_chip"] = cn_sleeve_chip()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_cycles_china: sleeve chip failed (%s)", e)

    # data JS (loaded directly by the page — no fetch, works on file:// + preview)
    payload = ("window.SECTOR_CYCLES=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
               + "window.SECTOR_NARR=" + json.dumps(narr, separators=(",", ":"), ensure_ascii=False) + ";\n"
               + "window.SECTOR_DNA=" + json.dumps(dna, separators=(",", ":"), ensure_ascii=False) + ";\n")
    (site / "sector_cycles_china_data.js").write_text(payload, encoding="utf-8")

    # raw model + the per-theme cycle map (read by build_baskets_china for the mini-charts)
    fdir = site / "chinasectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "sector_cycles.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (fdir / "sector_cycles_basket_map.json").write_text(
        json.dumps(_basket_cycle_map(data), separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,  # macro pages emit raw HTML; _navlinks uses |safe
    )
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    html = env.get_template("sector_cycles_china.html.j2").render()
    (site / "sector_cycles_china.html").write_text(html, encoding="utf-8")

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
                log.warning("china_sector_cycles: shared asset %s missing — run build_cycle first", asset)

    # append today's signal to the point-in-time forward log (graded later; never read back)
    try:
        n_logged = ccc.append_forward_log(data)
    except Exception as e:  # noqa: BLE001
        n_logged = 0
        log.warning("china_sector_cycles: forward log failed: %s", e)

    log.info("built site/sector_cycles_china.html (%d sectors, %d baskets, %d narratives, %d logged)",
             len(data["sectors"]), len(data.get("baskets", [])), len(narr), n_logged)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
