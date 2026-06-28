"""Build the China Sector Central Intelligence dashboard -> site/sector_central_china.html.

The Phase-2 consolidation: engine.china_sector_central fuses the cycle map + the evidence-gated
pathway forward layer + the (audited) momentum/flow/crowding CONTEXT into one per-sector
conviction read under a validated regime GATE, with a reasoning trace. This script emits the
data JS (window.SECTOR_CENTRAL), the raw JSON, runs the self-grader (append today's calls +
grade matured ones), and renders the page. Links the three sub-dashboards (Sector Cycles,
Thematic Baskets, Narrative Rotation) it sits above.

Additive — any failure logs and returns 0 so it never breaks the rest of the China build.
Run: python -m scripts.build_china_sector_central
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
log = logging.getLogger("build_china_sector_central")


def main() -> int:
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    try:
        from engine import china_sector_central as cc
        data = cc.compute()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.exception("china_sector_central engine failed: %s", e)
        return 0
    if not data or not data.get("sectors"):
        log.warning("china_sector_central: no data — skipping")
        return 0

    # self-grader: append today's calls (PIT) + grade matured ones; attach the scorecard
    try:
        from engine import china_sector_central_grader as cg
        n_logged = cg.append_central_log(data)
        data["grader"] = cg.grade()
    except Exception as e:  # noqa: BLE001
        n_logged = 0
        log.warning("china_sector_central: grader failed: %s", e)
        data["grader"] = {"available": False, "note": "grader error"}

    payload = "window.SECTOR_CENTRAL=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
    (site / "sector_central_china_data.js").write_text(payload, encoding="utf-8")
    fdir = site / "chinasectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "sector_central.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=False)
    html = env.get_template("sector_central_china.html.j2").render()
    (site / "sector_central_china.html").write_text(html, encoding="utf-8")

    log.info("built site/sector_central_china.html (%d sectors, %d baskets, %d calls logged, grader=%s)",
             len(data["sectors"]), len(data.get("baskets", [])), n_logged,
             (data.get("grader") or {}).get("available"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
