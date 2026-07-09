"""Build the thematic-baskets page -> site/baskets.html (+ basketdata/baskets.json).

Standalone (clones build_discovery.py / build_seasonality.py): reads
data/baskets/membership.json + the price caches + SPY via engine.baskets.compute_baskets()
and renders the FactorWatch-style baskets view — a sortable performance table
(1d/5d/20d/60d/YTD, raw or relative-to-SPY), a cumulative spark per basket, a
per-basket members drill and a dated membership changelog. Additive — any failure
logs and returns 0 so it can never break the rest of the site.

Usage: python -m scripts.build_baskets
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
log = logging.getLogger("build_baskets")


def _write_score_snapshot(ti: dict) -> None:
    """Slim per-theme score snapshot -> data/baskets/latest.json (archived daily by
    scripts.archive_signals into the 'baskets' stream → detail-page score history)."""
    slim = {"as_of": ti.get("as_of"), "themes": []}
    for t in ti.get("themes", []):
        tx = t.get("textures") or {}
        slim["themes"].append({
            "id": t["id"], "name": t.get("name"), "score": t.get("score"),
            "label": t.get("label"), "reco": t.get("reco"), "rank": t.get("rank"),
            "net_ad": t.get("net_ad"), "components": t.get("components"),
            "bull_days": (tx.get("bull_age") or {}).get("days"),
            "overbought": (tx.get("overbought") or {}).get("value"),
            "clean_entry": (tx.get("clean_entry") or {}).get("flag"),
            "rollover": (tx.get("rollover_risk") or {}).get("risk"),
        })
    p = config.data_dir() / "baskets" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(slim, separators=(",", ":"), default=str))


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.baskets import compute_baskets
        data = compute_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no baskets (need data/baskets/membership.json + price caches) — skipping")
        return 0

    # THEME ROTATION DESK (engine.theme_scoring) — score / label / recommend every theme,
    # 5-day rotation, impulse + new-hi-lo scorecards. Rides inside baskets_json. Then
    # engine.theme_alerts diffs vs the prior snapshot and fires change events into
    # data/themes/alerts.jsonl (picked up by alert_triage -> alerts.html with zero new
    # plumbing); recent events feed the page's bell dropdown. Additive — never fatal.
    theme_alerts_recent = []
    try:
        from engine.theme_scoring import compute_theme_intel
        ti = compute_theme_intel()
        if ti:
            data["theme_intel"] = ti
            from engine import theme_alerts
            theme_alerts.rebuild(ti)
            theme_alerts_recent = theme_alerts.recent(30, as_of=ti.get("as_of"))
            _write_score_snapshot(ti)            # data/baskets/latest.json → score-history archive
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme rotation desk failed: %s", e)

    # 🔥 FORMING NARRATIVES (engine.narrative_emergence) — fuse the theme-discovery radar
    # (coherent, TIGHTENING name-groups not yet in a basket) with the GDELT attention
    # backdrop + the AI desk's emerging_watch into a ranked, surfaced read with clean-entry
    # recommended tickers. engine.emergence_alerts diffs vs the prior snapshot and fires a
    # "narrative_forming" event (picked up by alert_triage). Display-only, additive, noisy —
    # a watchlist / avoid-the-peak lens, never a buy list. Never fatal.
    emergence = None
    try:
        from engine.narrative_emergence import compute_emergence
        emergence = compute_emergence("us")
        if emergence:
            from engine import emergence_alerts
            emergence_alerts.rebuild(emergence, "us")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("narrative emergence desk failed: %s", e)

    fdir = site / "basketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))
    if emergence:
        (fdir / "narrative_emergence.json").write_text(
            json.dumps(emergence, separators=(",", ":"), default=str))

    # Engine-1 FLOW LENS (display-only characterization + the AI-handoff payload). It
    # ranks where cross-sectional flow is CONCENTRATING (PIT sectors + baskets), maps the
    # cross-group cluster, and carries the validated-honest verdict/caveats. flow.json is
    # the contract a downstream AI judge reads. Additive — never breaks the page.
    flow = None
    try:
        from engine.group_flow import compute_group_flows
        flow = compute_group_flows()
        if flow:
            (fdir / "flow.json").write_text(json.dumps(flow, separators=(",", ":"), default=str))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("group_flow lens failed: %s", e)

    # SECTOR PULSE — compact per-theme rotation data product for Mastermind bot / Terminal.
    # Reads theme_intel (already computed above) and writes basketdata/sector_pulse.json.
    # Also merges per-theme velocity/heat keys into theme_intel so the page JS can render
    # the rotation velocity scorecard enhancements (heat pill, 20d rank trajectory, act-now
    # pulse strip).  Additive — never breaks the build.
    try:
        if data.get("theme_intel"):
            from engine import sector_pulse as _sp
            _sp.write_pulse(data["theme_intel"], "us", fdir)
            _sp.merge_pulse_into_theme_intel(data["theme_intel"], "us")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_pulse hook failed: %s", e)

    # THEME ROTATION DESK ADD-ONS (display-only context): ETF Pulse (style/risk/sector
    # rotation), vol-regime + CBOE put/call chip, and per-theme ATR extension. Each writes
    # its own basketdata/*.json, consumed client-side by site/theme_addons.js (the
    # _theme_addons.html.j2 panel). Additive — never breaks the page.
    try:
        from scripts.build_theme_addons import main as _build_theme_addons
        _build_theme_addons()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme add-ons failed: %s", e)

    # 🛰️ DIVERGENCE RADAR (display-only): federal contract spend (collectors.usaspending)
    # vs each theme's already-priced 60-day relative strength -> per-theme divergence
    # states + falsifiable watch-hypotheses (data/radar/theses.jsonl, graded later).
    # Read client-side via site/radar_panel.js (the _radar_panel.html.j2 panel).
    # Additive — never breaks the page.
    try:
        from engine.radar import append_ledger, compute_radar
        radar = compute_radar(data)
        if radar:
            (fdir / "radar.json").write_text(json.dumps(radar, separators=(",", ":"), default=str))
            append_ledger(radar)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("divergence radar failed: %s", e)
    # dedicated Divergence Radar page (site/radar.html) — pure render of the radar/brain JSON
    try:
        from scripts.build_radar_page import main as _build_radar_page
        _build_radar_page()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("radar page failed: %s", e)

    # split the dense CHART (level matrix, for the interactive chart + live σ/sort table)
    # from the BASKETS metadata (thesis/members/rationale/perf/changelog/reference).
    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Risk strip (top of page): the headline mirrors the canonical Market Risk Radar
    # (engine/risk_radar.py → latest.json.risk_radar) shown identically on macro.html, so the
    # two pages always agree on the number. The risk_state engine (engine/risk_state.py) supplies
    # the de-gross SIZING guidance (gross factor / leadership cap) — the leadership-driven
    # baskets surface should DOWN-SIZE and favor good entries, not chase extended leaders.
    # Read-only from latest.json; never fatal. Both surfaced only at caution or worse.
    risk_state = None
    risk_radar = None
    try:
        _latest = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
        rs = _latest.get("risk_state")
        if rs and rs.get("state") in ("caution", "elevated", "risk-off"):
            risk_state = rs
        rr = _latest.get("risk_radar")
        if rr and rr.get("state") in ("caution", "elevated", "risk-off"):
            risk_radar = rr
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("baskets risk-state read failed: %s", e)
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":")),
        chart_json=json.dumps(chart, separators=(",", ":")),
        theme_alerts_json=json.dumps(theme_alerts_recent, separators=(",", ":")),
        flow=flow,
        risk_state=risk_state,
        risk_radar=risk_radar,
        generated_utc=built)
    write_page(site / "baskets.html", html)
    # PER-THEME DETAIL PAGES (one site/basket/<id>.html each) — needs `data` (with
    # theme_intel + members) and the env; chart already split off above. Additive.
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, "us")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme detail pages failed: %s", e)
    # ship the TradingView Lightweight Charts runtime (Apache-2.0) used by the page
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    # ship the prevailing-narrative scorecard renderer (all baskets pages use it)
    sc = config.ROOT / "templates" / "allocation_scorecard.js"
    if sc.exists():
        (site / "allocation_scorecard.js").write_text(sc.read_text())
    # ship the Forming Narratives renderer (all baskets pages use it)
    ne = config.ROOT / "templates" / "forming_narratives.js"
    if ne.exists():
        (site / "forming_narratives.js").write_text(ne.read_text())
    log.info("wrote %s/baskets.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)

    # Thematic Narrative-Rotation pages (engine.narrative_rotation -> site/allocation*.html)
    # for ALL FOUR markets (US + China + HK + Canada). Built here off the same baskets
    # membership + price caches the collectors already refresh, so they ship on every CI run
    # without new daily.yml steps (the PAT lacks `workflow` scope, like build_canada /
    # build_baskets_china). First refresh the honest Phase-0 backtest artifacts the pages
    # cite (US 27y + Canada ~24y + China ~8y; HK is too thin → cites the US proxy) — committed
    # copies are the fallback if a refresh fails; an absent file just hides that panel. Both
    # additive — never fatal. TODO: promote to dedicated daily.yml steps once a workflow-scoped
    # token is available.
    try:
        from scripts.thematic_rotation_phase0 import run_all as _phase0_all
        _phase0_all()                                     # us, canada, china (HK skipped → US proxy)
    except Exception as e:  # noqa: BLE001 — additive; falls back to the committed artifacts
        log.error("thematic rotation Phase-0 refresh failed (using committed artifacts): %s", e)
    _alloc_stale = False
    try:
        from scripts.build_allocation import main as _build_allocation
        _alloc_stale = _build_allocation()                # builds all four allocation pages
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        _alloc_stale = True
        log.error("allocation pages (via build_baskets) failed: %s", e, exc_info=True)
        print("::warning::allocation sub-build (via build_baskets) raised an unhandled exception"
              " — data/allocation/latest_*.json will NOT be updated this run. "
              f"Root cause: {type(e).__name__}: {e}")
    # Always write freshness.json so the file reflects the CURRENT run, not the worst
    # run in history.  If we only write on failure the file persists stale=true in the
    # committed tree forever after the first bad nightly, permanently misleading W3.
    import json as _json
    from datetime import datetime, timezone
    from lib import config as _cfg
    _fdir = _cfg.ROOT / "site" / "allocationdata"
    _fdir.mkdir(parents=True, exist_ok=True)
    (_fdir / "freshness.json").write_text(
        _json.dumps({"stale": _alloc_stale,
                     "reason": ("allocation sub-build failed or returned stale"
                                if _alloc_stale else "ok"),
                     "stamped_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                    separators=(",", ":")))
    try:
        from scripts.build_anticipation import main as _build_anticipation
        _build_anticipation()                             # anticipation.html + per-ticker cones
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("anticipation page (via build_baskets) failed: %s", e)

    # W3.8 — FREEZE US basket levels + membership hashes (append-only, PIT).
    # Runs AFTER compute_baskets() and the chart pop, so both `data` (BASKETS metadata)
    # and `chart` (level matrix) are in scope.  Additive + never fatal: a freeze failure
    # skips today's snapshot without breaking the page.  The grader reports
    # "accruing from <date>" for any day the freeze was skipped.
    try:
        from engine.basket_freeze import freeze_domain, FreezeSkipped
        from engine.baskets import _membership as _us_mem
        from engine.equity_factors import _closes as _us_closes
        _us_mem_data = _us_mem()
        try:
            _us_cl = _us_closes()
        except Exception:  # noqa: BLE001
            _us_cl = None
        # chart was popped from data above and is still in scope
        _freeze_payload = {"chart": chart}
        _freeze_result = freeze_domain("us", _freeze_payload, _us_cl, _us_mem_data)
        log.info("basket_freeze[us]: %s", _freeze_result)
    except FreezeSkipped as e:
        log.error("basket_freeze[us]: SKIPPED (churn guard): %s", e)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("basket_freeze[us]: failed: %s", e)

    # FT-R8 — surface-freshness sentinel: assert first-class artifacts carry today's
    # NYSE session.  Warn-only (exits 0 always); annotations appear in the job summary.
    try:
        from scripts.check_surface_freshness import run as _check_freshness
        _check_freshness()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("check_surface_freshness failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
