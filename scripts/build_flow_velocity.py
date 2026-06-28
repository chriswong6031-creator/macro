"""Build the Capital-Flow Velocity desk -> site/flow_velocity.html (+ flowdata/desk.json).

"How fast is big money flowing into China / HK names and sectors" — the velocity &
acceleration of the net-flow series the build already collects (Stock-Connect channels,
the Tushare 主力 weekly grid, the Dragon-Tiger institutional seats, southbound holdings).
engine.flow_velocity is the brain; this script is the thin render tier.

Additive — any failure logs and returns 0 so it never breaks the rest of the build.
Run: python -m scripts.build_flow_velocity
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
log = logging.getLogger("build_flow_velocity")


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        from engine.flow_velocity import snapshot
        snap = snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("flow_velocity engine failed: %s", e)
        return 0
    if not snap:
        log.warning("no flow-velocity data (run the China/Tushare collectors first) — skipping")
        return 0

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)

    try:
        from scripts.build_vector import C  # shared palette
    except Exception:  # noqa: BLE001
        C = {}

    try:
        html = env.get_template("flow_velocity.html.j2").render(C=C, snap=snap, built=built)
    except Exception as e:  # noqa: BLE001 — a template error must not sink the China build
        log.error("flow_velocity render failed: %s", e)
        return 0
    (site / "flow_velocity.html").write_text(html)

    # small JSON payload (parity with the other desks; handy for a future hub card)
    try:
        fdir = site / "flowdata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "desk.json").write_text(
            json.dumps(snap, separators=(",", ":"), ensure_ascii=False, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("flow_velocity json payload failed: %s", e)

    n_sec = len((snap.get("ashare_sectors") or {}).get("rows", []))
    n_names = (snap.get("ashare_names") or {}).get("n", 0)
    log.info("wrote %s/flow_velocity.html (%d sectors, %d names, %d KB)",
             site, n_sec, n_names, len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
