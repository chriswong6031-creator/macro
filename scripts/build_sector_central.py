"""Build the US Sector Central Intelligence dashboard -> site/sector_central.html.

The consolidation hub: engine.sector_central fuses the cycle map + the VALIDATED absolute-trend
drawdown gate + the macro regime posture + the (audited) momentum / heat / crowding CONTEXT into
one per-sector conviction read with a reasoning trace. This script emits the data JS
(window.SECTOR_CENTRAL), the raw JSON, runs the self-grader (append today's calls + grade matured
ones), and renders the page. It links + embeds the four sub-dashboards it sits above (Sector
Cycles overlay + Sector Heatmap scorecard embedded; Thematic Baskets + Narrative Rotation linked).

Additive — any failure logs and returns 0 so it never breaks the rest of the build.
Run: python -m scripts.build_sector_central
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_sector_central")


def main() -> int:
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    try:
        from engine import sector_central as cc
        data = cc.compute()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.exception("sector_central engine failed: %s", e)
        return 0
    if not data or not data.get("sectors"):
        log.warning("sector_central: no data — skipping")
        return 0

    # self-grader: append today's calls (PIT) + grade matured ones; attach the scorecard
    try:
        from engine import sector_central_grader as cg
        n_logged = cg.append_central_log(data)
        data["grader"] = cg.grade()
    except Exception as e:  # noqa: BLE001
        n_logged = 0
        log.warning("sector_central: grader failed: %s", e)
        data["grader"] = {"available": False, "note": "grader error"}

    payload = "window.SECTOR_CENTRAL=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
    (site / "sector_central_data.js").write_text(payload, encoding="utf-8")
    fdir = site / "sectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "sector_central.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=False)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    try:
        html = env.get_template("sector_central.html.j2").render()
        (site / "sector_central.html").write_text(html, encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — a template error must NOT abort the daily engine job
        # The CI step that runs this is a bare `run:` (its claim "the builder returns 0 on any
        # failure" is only true if main() never raises), so an unguarded render here aborts the
        # whole engine job → no commit → stale site (this exact `t`-undefined crash, #624→#643).
        # Degrade: keep the last-good committed sector_central.html (the fresh data JS/JSON written
        # above still drive the page's runtime content) and return 0 so the rest of the build ships.
        log.exception("sector_central: page render failed (%s) — keeping last-good HTML", e)
        return 0

    # the page embeds the cycle-map overlay (window.SECTOR_CYCLES) + the heatmap scorecard →
    # ensure their shared assets are present. The cycles DATA (sector_cycles_data.js) is written
    # by build_sector_cycles, which must run before this; we copy the page assets and warn if
    # required runtime files are absent.
    import shutil
    for asset in ("sector_cycles.css", "sector_cycles.js"):
        src = root / "templates" / asset
        if src.exists():
            shutil.copy2(src, site / asset)
    for need in ("sector_cycles_data.js", "mm_charts.js", "cycle.css"):
        if not (site / need).exists():
            log.warning("sector_central: %s missing — embedded cycle chart needs "
                        "build_sector_cycles (+ build_cycle) to run first", need)
    if not (site / "heatmap.js").exists():
        log.warning("sector_central: heatmap.js missing — embedded heatmap scorecard needs "
                    "build_site to run first")

    log.info("built site/sector_central.html (%d sectors, %d baskets, %d calls logged, grader=%s)",
             len(data["sectors"]), len(data.get("baskets", [])), n_logged,
             (data.get("grader") or {}).get("available"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
