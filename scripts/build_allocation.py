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

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_allocation")


# region -> (json filename, html page). US keeps the bare names; the others are suffixed.
PAGES = {"us": ("allocation.json", "allocation.html"),
         "china": ("allocation_china.json", "allocation_china.html"),
         "hk": ("allocation_hk.json", "allocation_hk.html"),
         "canada": ("allocation_canada.json", "allocation_canada.html")}


def _write_alloc_snapshot(region: str, data: dict) -> None:
    """Slim playbook snapshot -> data/allocation/latest_<region>.json (archived daily by
    scripts.archive_signals into 'allocation_<region>' → the risk-over-time history)."""
    alloc = data.get("allocation") or {}
    rot = data.get("rotation") or {}
    slim = {"as_of": data.get("as_of"), "region": region,
            "cash": alloc.get("cash"), "n_held": alloc.get("n_held"),
            "held": [w["id"] for w in alloc.get("weights", [])],
            "leader": (rot.get("leader") or {}).get("id"),
            "absorption": rot.get("absorption"),
            "crash": bool((alloc.get("crash_overlay") or {}).get("active"))}
    p = config.data_dir() / "allocation" / f"latest_{region}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(slim, separators=(",", ":"), default=str))


def _alloc_history(region: str) -> list[dict]:
    """Dated [{date, cash, n_held}] from the allocation signal-archive — the risk dial over
    time. Empty until history accrues (the page then shows 'history accruing')."""
    try:
        from engine.signal_archive import load_archive
        df = load_archive(f"allocation_{region}")
    except Exception:  # noqa: BLE001
        return []
    if df is None or df.empty:
        return []
    out = []
    for _, r in df.iterrows():
        cash = r.get("cash")
        if cash is not None and pd.notna(cash):
            out.append({"date": str(r.get("asof")), "cash": float(cash),
                        "n_held": (int(r["n_held"]) if pd.notna(r.get("n_held")) else None)})
    return out


def _standouts_per_theme(region: str, site) -> dict:
    """{theme_id -> count of its members on the US standout BUY board} — the allocation→stock
    bridge so a held theme can show how many individual standouts back it. US only (the board
    is US); reads the already-built us_standouts.json + basketdata/baskets.json. Empty on any
    shortfall — additive, never fatal."""
    if region != "us":
        return {}
    try:
        su = json.loads((site / "factordata" / "us_standouts.json").read_text())
        board = {r.get("ticker") for r in (su.get("buy") or []) if r.get("ticker")}
        bk = json.loads((site / "basketdata" / "baskets.json").read_text())
    except Exception:  # noqa: BLE001 — additive, never fatal
        return {}
    out: dict = {}
    for b in (bk.get("baskets") or []):
        n = sum(1 for m in (b.get("members") or []) if m.get("symbol") in board)
        if n:
            out[b.get("id")] = n
    return out


# region -> the per-market basketdata dir holding the already-built theme desk (act_now lives in
# theme_intel). The desk now scores CN/HK/CA too (engine.theme_scoring region-aware), so the
# allocation page's buy/reduce shortlist is no longer US-only.
_BASKETDATA = {"us": "basketdata", "china": "chinabasketdata",
               "hk": "hkbasketdata", "canada": "canadabasketdata"}


def _theme_act_now(region: str, site) -> dict | None:
    """The theme-level WHAT-TO-ACT-ON-NOW (buy/add vs reduce/avoid) from the baskets desk.
    Region-aware: reads the region's own already-built <region>basketdata/baskets.json. Returns
    None on shortfall — additive."""
    sub = _BASKETDATA.get(region)
    if not sub:
        return None
    try:
        p = site / sub / "baskets.json"
        ti = (json.loads(p.read_text()).get("theme_intel") or {}) if p.exists() else {}
        return ti.get("act_now")
    except Exception:  # noqa: BLE001
        return None


def _hk_turn_context(region: str, site) -> dict | None:
    """HK only: the leadership organ's participation read (site/factordata/hk_standouts.json,
    HKRV-W2) so the allocation page can carry the ratified 'Leaders moving first' banner
    (HKRV-W3 idiom) when mega-caps thrust ahead of the slow book. One-directional display
    context — never read back by the engine, never touches allocate(). Fail-open: None on
    any shortfall, wrong region, non-firing state, or a stale artifact (a frozen asia lane
    must not leave a weeks-old banner up — 5-calendar-day freshness fence)."""
    if region != "hk":
        return None
    try:
        d = json.loads((site / "factordata" / "hk_standouts.json").read_text())
        led = d.get("leadership") or {}
        if led.get("state") != "leaders_participating":
            return None
        as_of = pd.Timestamp(d.get("as_of"))
        if pd.isna(as_of) or (pd.Timestamp.now(tz="UTC").tz_localize(None) - as_of).days > 5:
            return None
        return led
    except Exception:  # noqa: BLE001 — additive, never fatal
        return None


def _hk_index_turn(region: str) -> dict | None:
    """HK only: the index-momentum organ's recent ^HSI washout-turn read
    (data/index_momentum/latest.json, IHM W1) as ONE context row inside the ratified
    'Leaders moving first' popover (audit GAP-2: the tag rendered nowhere). Display
    tier, one-directional — a context row only, never a K input, never read back by
    the engine; the IHM program owns engine/index_momentum.py. Fail-open: None on
    wrong region, missing/stale artifact (runner-local data/ does not ride into
    worktrees/CI), no recent washout_turn, or any shortfall. Two recency fences:
    5-calendar-day artifact fence on data_as_of (frozen-lane guard, same spirit as
    _hk_turn_context) + the event itself within ~15 sessions (21 calendar days)."""
    if region != "hk":
        return None
    try:
        p = config.data_dir() / "index_momentum" / "latest.json"
        d = json.loads(p.read_text())
        data_as_of = pd.Timestamp(d.get("data_as_of"))
        now = pd.Timestamp.now(tz="UTC").tz_localize(None)
        if pd.isna(data_as_of) or (now - data_as_of).days > 5:
            return None
        grids = ((d.get("indices") or {}).get("^HSI") or {}).get("grids") or {}
        events = (grids.get("1D") or {}).get("recent_events") or []
        turns = []
        for ev in events:
            if ev.get("direction") != "bull" or ev.get("quality_tag") != "washout_turn":
                continue
            ev_d = pd.Timestamp(ev.get("date"))
            if pd.isna(ev_d) or (now - ev_d).days > 21:  # ~15 HK sessions
                continue
            turns.append((ev_d, ev))
        if not turns:
            return None
        ev_d, ev = max(turns, key=lambda t: t[0])
        return {"date": str(ev_d.date()),
                "date_en": f"{ev_d:%b} {ev_d.day}",
                "date_zh": f"{ev_d.month}月{ev_d.day}日",
                "us_confirm": bool(ev.get("us_confirm"))}
    except Exception:  # noqa: BLE001 — additive, never fatal
        return None


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
    # Slim PIT snapshot (data/allocation/latest_<region>.json) — written BEFORE the
    # alerts try/except so it is never silently dropped by an alerts rebuild failure.
    # Root cause of 2026-07-07→09 freeze: _write_alloc_snapshot was inside the same
    # try block as allocation_alerts.rebuild(); when rebuild() raised, the snapshot was
    # never written and data/allocation/latest_us.json went 3 days stale.
    try:
        _write_alloc_snapshot(region, data)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("[%s] alloc snapshot write failed: %s", region, e, exc_info=True)
    # ROTATION ALERTS + risk-over-time history + the theme buy/sell shortlist (additive)
    rot_alerts, hist = [], []
    try:
        from engine import allocation_alerts
        allocation_alerts.rebuild(data, region)
        rot_alerts = allocation_alerts.recent(region, 45, as_of=data.get("as_of"))
        hist = _alloc_history(region)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("[%s] rotation alerts/history failed: %s", region, e, exc_info=True)
    act_now = _theme_act_now(region, site)
    standouts = _standouts_per_theme(region, site)
    html = env.get_template("allocation.html.j2").render(
        d=data, data_json=json.dumps(data, separators=(",", ":")),
        rotation_alerts_json=json.dumps(rot_alerts, separators=(",", ":")),
        risk_history_json=json.dumps(hist, separators=(",", ":")),
        act_now_json=json.dumps(act_now, separators=(",", ":"), default=str),
        standouts_json=json.dumps(standouts, separators=(",", ":")),
        hk_leadership=_hk_turn_context(region, site),
        hk_index_turn=_hk_index_turn(region),
        generated_utc=built)
    write_page(site / page, html)
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


def main(regions: list[str] | None = None) -> bool:
    """Build all allocation pages.  Returns True (stale) when any region failed or produced
    no output — used by build_baskets.py to stamp site/allocationdata/freshness.json."""
    site = config.ROOT / "site"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    regions = regions or list(PAGES.keys())
    any_failed = False
    for r in regions:
        ok = build_region(r, env, built, site)
        if not ok:
            any_failed = True
    # ship the live-desk renderer alongside the pages (self-contained, like build_baskets'
    # lightweight-charts.js) so the new JS is always present when the page is built.
    js = config.ROOT / "templates" / "ai_desk_thematic.js"
    if js.exists():
        (site / "ai_desk_thematic.js").write_text(js.read_text())
    _run_macro_narrative()             # GDELT macro-narrative backdrop the desk reads (bus owned here)
    _run_theme_discovery()             # candidate-theme radar (US) → feeds the scout + a page panel
    _run_thematic_desk(regions)        # additive AI layer; gated + never fatal
    return any_failed  # True = stale; build_baskets stamps freshness.json


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(1 if main(args or None) else 0)
