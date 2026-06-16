"""Build the Thematic Narrative-Rotation page -> site/allocation.html
(+ site/allocationdata/allocation.json).

Reads engine.narrative_rotation.compute_narrative_rotation() (which itself reads the
baskets membership + price caches + the Phase-0 validation artifact) and renders the
"where do I allocate across themes?" decision page: the prevailing narrative, a suggested
trend-following allocation, the durability/crowding scorecard, the rotation radar, the
honest 27-year workhorse backtest, and the AI handoff. Additive — any failure logs and
returns 0 so it never breaks the rest of the site.

Run standalone (`python -m scripts.build_allocation`) or hooked from build_baskets.py so
it ships on every CI run without needing a new daily.yml step (PAT lacks workflow scope).
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
log = logging.getLogger("build_allocation")


# region -> (json filename, html page). US keeps the bare names; the others are suffixed.
PAGES = {"us": ("allocation.json", "allocation.html"),
         "china": ("allocation_china.json", "allocation_china.html"),
         "hk": ("allocation_hk.json", "allocation_hk.html"),
         "canada": ("allocation_canada.json", "allocation_canada.html")}


def build_region(region: str, env, built: str, site) -> bool:
    """Build one market's Narrative-Rotation page + JSON. Additive — logs and returns False
    on shortfall (e.g. a market's caches absent locally) so the others still build."""
    try:
        from engine.narrative_rotation import compute_narrative_rotation
        data = compute_narrative_rotation(region)
    except Exception as e:  # noqa: BLE001
        log.error("[%s] narrative_rotation engine failed: %s", region, e)
        return False
    if not data:
        log.warning("[%s] no narrative_rotation data (caches absent?) — skipping", region)
        return False
    jname, page = PAGES[region]
    fdir = site / "allocationdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / jname).write_text(json.dumps(data, separators=(",", ":"), default=str))
    html = env.get_template("allocation.html.j2").render(
        d=data, data_json=json.dumps(data, separators=(",", ":")), generated_utc=built)
    (site / page).write_text(html)
    log.info("[%s] wrote %s (%d themes, headline=%s)", region, page,
             data.get("n_themes", 0), (data.get("headline") or {}).get("name", "—"))
    return True


def _run_thematic_desk(regions: list[str]) -> None:
    """AI Desk for Thematic Investing — after the allocation JSONs are written, let the LLM
    desk produce falsifiable per-theme leans for each market (site/allocationdata/ai_desk_*.json)
    and grade the past-due ledger. GATED (engine.thematic_desk.run skips unless the AI layer is
    enabled + a key is present) and fully additive — a failure never breaks the pages, which
    fetch the brief client-side and degrade to the static handoff contract when it's absent."""
    try:
        from engine import thematic_desk as td
    except Exception as e:  # noqa: BLE001
        log.error("thematic_desk import failed: %s", e)
        return
    for r in regions:
        try:
            td.run(r)
        except Exception as e:  # noqa: BLE001 — one market must not sink the others
            log.error("thematic_desk run[%s] failed: %s", r, e)
    try:
        td.score_ledger()      # grade past-due theses → track_record + public ai_desk_track.json
    except Exception as e:  # noqa: BLE001
        log.error("thematic_desk score_ledger failed: %s", e)


def main(regions: list[str] | None = None) -> int:
    site = config.ROOT / "site"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    regions = regions or list(PAGES.keys())
    for r in regions:
        build_region(r, env, built, site)
    # ship the live-desk renderer alongside the pages (self-contained, like build_baskets'
    # lightweight-charts.js) so the new JS is always present when the page is built.
    js = config.ROOT / "templates" / "ai_desk_thematic.js"
    if js.exists():
        (site / "ai_desk_thematic.js").write_text(js.read_text())
    _run_thematic_desk(regions)        # additive AI layer; gated + never fatal
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(main(args or None))
