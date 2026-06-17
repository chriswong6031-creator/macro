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


def _run_macro_narrative() -> None:
    """Write the market-level macro-narrative backdrop (keyless GDELT news bus) the AI desk
    reads as COINCIDENT regime context. The BUILD SCRIPT owns engine.news_vector so engine/
    stays free of the bus (the scoring-isolation invariant). Additive/never fatal."""
    try:
        from engine import news_vector as nv
        panel = nv.recent_panel(days=5, top_n=6)
        ev = (panel or {}).get("events")
        if not ev:
            return
        top = sorted((ev.get("by_theme") or {}).items(), key=lambda kv: -kv[1])[:4]
        heads = [{"title": it.get("title"), "theme": it.get("theme"), "domain": it.get("domain")}
                 for it in (ev.get("items") or []) if int(it.get("tier", 9)) == 1][:4]
        out = {"dominant_themes": [{"theme": t, "n": n} for t, n in top],
               "n_recent": ev.get("n_recent"), "unscheduled_share": ev.get("unscheduled_share"),
               "top_headlines": heads, "window_days": (panel or {}).get("window_days"),
               "note": "market-level macro/policy/geo narrative flow; coincident, not per-theme, never a trigger"}
        d = config.ROOT / "site" / "allocationdata"
        d.mkdir(parents=True, exist_ok=True)
        (d / "macro_narrative.json").write_text(json.dumps(out, separators=(",", ":"), default=str))
        log.info("macro_narrative: %d themes", len(out["dominant_themes"]))
    except Exception as e:  # noqa: BLE001
        log.error("macro_narrative backdrop failed: %s", e)


def _run_theme_discovery() -> None:
    """Theme-discovery radar — a DISPLAY-ONLY candidate generator for emerging US themes
    (site/allocationdata/theme_candidates.json + a copy of the committed Phase-0 verdict).
    Run BEFORE the desk so the narrative-scout can see the candidates. Additive/never fatal."""
    try:
        from engine.theme_discovery import discover_candidates
        d = discover_candidates("us")
        if not d:
            return
        out = config.ROOT / "site" / "allocationdata"
        out.mkdir(parents=True, exist_ok=True)
        # fold in the committed offline Phase-0 verdict so the page can show "how validated"
        p0 = config.data_dir() / "theme_discovery" / "phase0.json"
        if p0.exists():
            try:
                d["phase0"] = json.loads(p0.read_text())
            except Exception:  # noqa: BLE001
                pass
        (out / "theme_candidates.json").write_text(json.dumps(d, separators=(",", ":"), default=str))
        log.info("theme_discovery: %d US candidates", len(d.get("candidates", [])))
    except Exception as e:  # noqa: BLE001
        log.error("theme_discovery failed: %s", e)


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
    _run_macro_narrative()             # GDELT macro-narrative backdrop the desk reads (bus owned here)
    _run_theme_discovery()             # candidate-theme radar (US) → feeds the scout + a page panel
    _run_thematic_desk(regions)        # additive AI layer; gated + never fatal
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(main(args or None))
