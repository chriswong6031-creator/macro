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


_CONV_CACHE: dict = {}


def _member_conviction(ticker: str) -> dict | None:
    """Pluck the per-stock Conviction Profile from site/stockdata/<T>.json (already computed
    by build_stock_library). None if the name has no library record (off-index / thin)."""
    if ticker in _CONV_CACHE:
        return _CONV_CACHE[ticker]
    val = None
    p = config.ROOT / "site" / "stockdata" / (ticker + ".json")
    if p.exists():
        try:
            c = json.loads(p.read_text()).get("conviction") or {}
            if c:
                val = {"score": c.get("score"), "band": c.get("band"),
                       "band_zh": c.get("band_zh"),
                       "verdict": c.get("verdict") if isinstance(c.get("verdict"), str) else None,
                       "verdict_zh": c.get("verdict_zh"),
                       "cycle_blocked": bool(c.get("cycle_blocked")),
                       "entry_pct": ((c.get("axes") or {}).get("entry") or {}).get("pct"),
                       "trust": (c.get("trust_tier") or {}).get("tier")}
        except Exception:  # noqa: BLE001
            val = None
    _CONV_CACHE[ticker] = val
    return val


def _build_detail_pages(data: dict, site: Path, env) -> int:
    """One site/basket/<id>.html per theme: holdings scoreboard w/ per-member conviction,
    advanced textures, signals, score history + change timeline. Additive."""
    from engine import basket_history, basket_score
    ti = data.get("theme_intel") or {}
    tmap = {t["id"]: t for t in ti.get("themes", [])}
    out_dir = site / "basket"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = env.get_template("basket_detail.html.j2")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n = 0
    for b in data.get("baskets", []):
        bid = b["id"]
        members = [{**m, "conviction": _member_conviction(m["symbol"])} for m in b.get("members", [])]
        detail = {
            "basket": b, "members": members, "theme": tmap.get(bid, {}),
            "act_now": basket_score.act_now_stocks(members, tmap.get(bid, {})),
            "history": basket_history.score_series(bid, "score"),
            "timeline": basket_history.change_timeline(bid),
            "as_of": ti.get("as_of") or b.get("created"),
            "market_concentration": ti.get("market_concentration") or {},
        }
        html = tmpl.render(detail_json=json.dumps(detail, separators=(",", ":"), default=str),
                           basket_name=b.get("name", bid), generated_utc=built)
        (out_dir / (bid + ".html")).write_text(html)
        n += 1
    log.info("wrote %d theme detail pages -> %s/basket/", n, site)
    return n


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

    fdir = site / "basketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))

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

    # THEME ROTATION DESK ADD-ONS (display-only context): ETF Pulse (style/risk/sector
    # rotation), vol-regime + CBOE put/call chip, and per-theme ATR extension. Each writes
    # its own basketdata/*.json, consumed client-side by site/theme_addons.js (the
    # _theme_addons.html.j2 panel). Additive — never breaks the page.
    try:
        from scripts.build_theme_addons import main as _build_theme_addons
        _build_theme_addons()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme add-ons failed: %s", e)

    # split the dense CHART (level matrix, for the interactive chart + live σ/sort table)
    # from the BASKETS metadata (thesis/members/rationale/perf/changelog/reference).
    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":")),
        chart_json=json.dumps(chart, separators=(",", ":")),
        theme_alerts_json=json.dumps(theme_alerts_recent, separators=(",", ":")),
        flow=flow,
        generated_utc=built)
    (site / "baskets.html").write_text(html)
    # PER-THEME DETAIL PAGES (one site/basket/<id>.html each) — needs `data` (with
    # theme_intel + members) and the env; chart already split off above. Additive.
    try:
        _build_detail_pages(data, site, env)
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
    try:
        from scripts.build_allocation import main as _build_allocation
        _build_allocation()                               # builds all four allocation pages
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("allocation pages (via build_baskets) failed: %s", e)
    try:
        from scripts.build_anticipation import main as _build_anticipation
        _build_anticipation()                             # anticipation.html + per-ticker cones
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("anticipation page (via build_baskets) failed: %s", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
