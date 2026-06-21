"""Build the US Intelligence Hub — the central-command fusion of all five signal desks
(news · alt-data · divergence radar · factor buy-board · policy intent).

Emits site/intel_hub/hub.json (the command data the page + the future US Mastermind read)
AND renders site/intelligence_hub.html. Run AFTER build_intelligence + build_briefing +
build_policy_watch + build_radar_plus (so every feeder artifact exists). Standalone,
degrade-safe — absent inputs degrade to empty panels, never breaks the build.

Run:  python -m scripts.build_intel_hub
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date  # noqa: E402

from lib import config  # noqa: E402
from engine import intel_hub, hub_track_record  # noqa: E402

log = logging.getLogger(__name__)


def _attach_live_prices(hub: dict, root, asof: str) -> None:
    """Best-effort nightly close on the SURFACED names only (~60, not the whole universe), so
    the live.js progressive-enhancement layer can patch them to ~15-min-delayed / live prices
    intraday and flag any name whose live price breaches its nightly band. Degrade-safe."""
    try:
        from engine.ai_desk import _level_asof
    except Exception as e:  # noqa: BLE001
        log.debug("live-price helper unavailable: %s", e)
        return
    cache: dict[str, float | None] = {}

    def px(t: str):
        if t not in cache:
            try:
                cache[t] = _level_asof(t, root, asof)
            except Exception:  # noqa: BLE001
                cache[t] = None
        return cache[t]

    lists = ([hub.get("command") or []]
             + [hub.get(k) or [] for k in ("emerging", "exhausted", "catalysts", "discovery")])
    for lst in lists:
        for d in lst:
            t = d.get("ticker")
            if t and "price" not in d:                 # always set the key (None or float) so the
                d["price"] = px(t)                     # template's `d.price is not none` guard is safe


def build(write: bool = True) -> dict:
    hub = intel_hub.load_and_build(top=30)
    _attach_live_prices(hub, config.ROOT, hub.get("as_of") or date.today().isoformat())
    # FALSIFIABLE TRACK-RECORD: record today's claims, grade matured ones (degrade-safe)
    track = {}
    try:
        today = date.today()
        n_new = hub_track_record.snapshot(hub.get("track_rows"), today)
        track = hub_track_record.compute(today)
        log.info("hub track-record: +%d snapshots, %d total, %d matured-any",
                 n_new, track.get("n_snapshots", 0), sum(1 for h in (track.get("horizons") or {}).values() if h.get("n_matured")))
    except Exception as e:  # noqa: BLE001
        log.warning("hub track-record step failed: %s", e)
    hub.pop("track_rows", None)                    # heavy; not part of the published command view
    hub["track_record"] = track
    if not write:
        return hub
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    (site / "intel_hub").mkdir(parents=True, exist_ok=True)
    (site / "intel_hub" / "hub.json").write_text(json.dumps(hub, default=str))
    (site / "intel_hub" / "track_record.json").write_text(json.dumps(track, default=str))
    log.info("built site/intel_hub/hub.json — %d universe, %d actionable, EE=%d CT=%d",
             hub.get("n_universe", 0), hub.get("n_actionable", 0),
             hub.get("counts", {}).get("early_edge", 0), hub.get("counts", {}).get("crowded_top", 0))
    if not hub.get("command"):                 # surface an empty fuse in the daily.yml logs
        log.warning("intel hub: empty command — feeders (intelligence/policy/radar) may be missing")

    # render the page
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        env = Environment(loader=FileSystemLoader(str(root / "templates")),
                          autoescape=select_autoescape(["html", "xml"]))
        html = env.get_template("intelligence_hub.html.j2").render(
            hub=hub, built=datetime.now(timezone.utc).isoformat(), mode="intel_hub")
        (site / "intelligence_hub.html").write_text(html)
        log.info("built site/intelligence_hub.html")
    except Exception as e:  # noqa: BLE001
        log.error("intelligence_hub render failed: %s", e)
    return hub


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_intel_hub failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
