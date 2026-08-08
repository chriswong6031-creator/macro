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
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_flow_velocity")


def _leg_map(snap: dict) -> dict:
    """Flatten the desk payload into {display name: leg} for the staleness check.

    The payload is not uniform — ``aggregate`` is a list of channel dicts while
    the rest are single dicts — so the shape knowledge lives here and
    lib.desk_guard stays a pure date comparison it can share with other desks.
    """
    legs: dict[str, dict] = {}
    for chan in (snap.get("aggregate") or []):
        if isinstance(chan, dict) and chan.get("key"):
            legs[f"aggregate:{chan['key']}"] = chan
    for key in ("ashare_names", "ashare_sectors", "hk_names"):
        leg = snap.get(key)
        if isinstance(leg, dict):
            legs[key] = leg
    return legs


def _warn_if_stale(snap: dict) -> list[dict]:
    """Emit a GitHub annotation for any desk leg that stopped advancing.

    The alarm this desk did not have. ``site/flowdata/desk.json`` sat 12 days
    stale (A-share legs pinned at 2026-07-24 by a dark upstream Tushare plane)
    while declaring a DAILY cadence, and nothing anywhere went red: the artifact
    was rewritten nightly, so every mtime- and existence-based check read healthy.

    Annotations are bare ``print`` at column 0 with ``flush=True`` per repo law —
    this module runs inside an Actions step (asia-close), so it is not in the
    FastAPI exemption list in tests/test_gh_annotation_line_start.py, and a
    logger call here would be silently swallowed by the level prefix.
    """
    from datetime import date

    from lib.desk_guard import stale_legs

    findings = stale_legs(_leg_map(snap), today=date.today())
    for f in findings:
        if f["reason"] == "unreadable":
            print(f"::warning title=flow-velocity-stale::flow desk leg {f['leg']} has an "
                  f"unreadable as_of ({f['as_of']!r}) — the staleness guard cannot read it, "
                  f"so this leg is now unguarded. Fix the stamp or the guard in "
                  f"lib/desk_guard.stale_legs.", flush=True)
        elif f["reason"] == "desk_frozen":
            print(f"::warning title=flow-velocity-stale::flow desk is FROZEN — its freshest "
                  f"live leg ({f['leg']}) is {f['age_days']}d old (as_of {f['as_of']}). Every "
                  f"leg stopped advancing, so site/flowdata/desk.json is serving a stale "
                  f"vintage. Check the China/HK collectors in the asia lane.", flush=True)
        else:
            print(f"::warning title=flow-velocity-stale::flow desk leg {f['leg']} is "
                  f"{f['lag_days']}d behind the desk's freshest leg (as_of {f['as_of']}, "
                  f"{f['age_days']}d old) while declaring cadence "
                  f"{(_leg_map(snap).get(f['leg']) or {}).get('cadence') or 'daily'}. Its "
                  f"upstream store has stopped advancing — consumers that gate on freshness "
                  f"(engine/cn_theme_tape, 7d) will drop this leg's chips.", flush=True)
    if findings:
        log.warning("flow desk staleness: %d leg(s) flagged — %s",
                    len(findings), ", ".join(f"{f['leg']}:{f['reason']}" for f in findings))
    return findings


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

    # Before the render: a template error returns 0 early (below), and the
    # staleness of the DATA is worth saying even on a night the page fails to
    # draw. Never fatal — an alarm that can sink the build is an alarm someone
    # eventually deletes.
    try:
        _warn_if_stale(snap)
    except Exception as e:  # noqa: BLE001
        log.warning("flow desk staleness check failed (non-fatal): %s", e)

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
    write_page(site / "flow_velocity.html", html)

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
