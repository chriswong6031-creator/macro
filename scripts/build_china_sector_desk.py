"""Build the China Sector Desk -> site/china_sector_desk.html (+ chinasectordata/*.json).

The free analogue of the Bloomberg GS China sector-basket monitor (GSXAC* family):
  • the LIVE BOARD — all 16 dashboard sectors as authoritative Shenwan (申万) L1 indices,
    with an intraday ETF-proxy tape (site/live.js), RS vs CSI 300, valuation, and a
    washout↔euphoria cycle-position read (engine.china_sector_desk).
  • the PATHWAY DESK — the four GS-style sectors (Banks / Consumption / Real Estate /
    Auto) with their major tops/bottoms and an evidence-gated, conditional forward tilt
    (engine.china_sector_pathway, gated by engine.china_sector_pathway_backtest;
    research/CHINA_SECTOR_PATHWAY_PHASE0.md).

Additive — any failure logs and returns 0 so it never breaks the rest of the China build.
Run: python -m scripts.build_china_sector_desk
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
log = logging.getLogger("build_china_sector_desk")


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        from engine.china_sector_desk import snapshot as desk_snapshot
        desk = desk_snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china sector desk engine failed: %s", e)
        return 0
    if not desk:
        log.warning("no china sector desk data (run collectors.china_sectors first) — skipping")
        return 0

    pathway = None
    try:
        from engine.china_sector_pathway import snapshot as pw_snapshot
        pathway = pw_snapshot()
    except Exception as e:  # noqa: BLE001 — additive
        log.error("china sector pathway engine failed: %s", e)

    # evidence gate — log (and surface on the page) but never block the build
    gate = None
    try:
        from engine.china_sector_pathway_backtest import run_gate
        gate = run_gate()
        log.info("pathway evidence gate: passed=%s (%s)", gate.get("passed"), gate.get("note"))
    except Exception as e:  # noqa: BLE001
        log.error("pathway gate failed: %s", e)

    # JSON payloads (client-side sparklines / live tape / hub)
    fdir = site / "chinasectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "desk.json").write_text(json.dumps(desk, separators=(",", ":"), ensure_ascii=False, default=str))
    if pathway:
        (fdir / "pathway.json").write_text(json.dumps(pathway, separators=(",", ":"), ensure_ascii=False, default=str))

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)

    from scripts.build_vector import C  # shared palette
    html = env.get_template("china_sector_desk.html.j2").render(
        C=C, desk=desk, pathway=pathway, gate=gate,
        desk_json=json.dumps(desk, separators=(",", ":"), ensure_ascii=False),
        built=built)
    write_page(site / "china_sector_desk.html", html)

    # small hub card payload
    try:
        lead = (desk.get("summary", {}).get("leaders") or [{}])[0]
        (config.data_dir() / "china_regime").mkdir(parents=True, exist_ok=True)
        (config.data_dir() / "china_regime" / "china_sector_desk_latest.json").write_text(
            json.dumps({"as_of": desk.get("as_of"), "n_sectors": len(desk.get("sectors", [])),
                        "leader": lead.get("name"), "leader_rs": lead.get("rs_60d")}, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("china sector desk hub payload failed: %s", e)

    log.info("wrote %s/china_sector_desk.html (%d sectors, pathway=%s, %d KB)",
             site, len(desk.get("sectors", [])), bool(pathway), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
