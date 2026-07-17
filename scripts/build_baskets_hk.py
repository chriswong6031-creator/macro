"""Build the Hong Kong thematic-baskets page -> site/baskets_hk.html (+ hkbasketdata/baskets.json).

The Hong Kong analogue of scripts/build_baskets_china.py. Reads data/baskets_hk/membership.json +
the hk_search close cache + the benchmark via engine.baskets_hk.compute_hk_baskets() and renders the same
FactorWatch-style baskets view. Additive — any failure logs and returns 0 so it can never
break the rest of the site.

Usage: python -m scripts.build_baskets_hk
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
log = logging.getLogger("build_baskets_hk")

STALE_TRADING_DAYS = 3     # §5.2 hard freshness gate: warn when basket prices > this old vs today


def _hk_ignition(data: dict) -> dict:
    """Sector-ignition strip (engine.sector_ignition) + forward ledger log/grade. Never fatal.

    The ledger legs self-gate on ignition_audit.ledger_lane_armed() (COLLECT_LANE=nightly —
    asia-close, this ledger's advancing lane, arms it inline on this module's invocation;
    daily.yml's build_vector hook is armed job-wide). Off-lane (closing-bell / engine-render /
    render) snapshot_and_grade is a pure scorecard read, so the scoreboard still renders."""
    try:
        from engine.sector_ignition import compute_ignition
        from engine.baskets_hk import _closes, member_closes_getter
        closes = _closes()
        getter = member_closes_getter(closes)
        ign = compute_ignition(data.get("chart") or {}, data.get("baskets") or [],
                               getter, market="hk", overlay=None)
        try:
            from engine import ignition_audit as _ia
            from engine import basket_levels_persist as _blp
            sc = _ia.snapshot_and_grade(
                ign, "hk",
                level_of=lambda bid: _blp.level_series("hk", bid),
                bench_series=_blp.bench_series("hk"))
            ign["scoreboard"] = sc
        except Exception as e:  # noqa: BLE001
            log.error("hk ignition ledger failed: %s", e)
        return ign
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("hk ignition failed: %s", e)
        return {"market": "hk", "items": [], "as_of": None, "has_southbound_leg": False}


def _persist_hk_levels(data: dict) -> None:
    try:
        from engine import basket_levels_persist as _blp
        _blp.persist(data, "hk")
    except Exception as e:  # noqa: BLE001
        log.error("hk basket-levels persist failed: %s", e)


def _hk_provenance(data: dict) -> dict:
    """Per-basket membership-provenance labels from data/baskets_hk/membership.json."""
    try:
        from engine.baskets_hk import _membership
        mem = _membership() or {}
        curated = mem.get("curated")
        bdict = mem.get("baskets") or {}
        by_id = {}
        for bid, b in (bdict.items() if isinstance(bdict, dict) else [(x["id"], x) for x in bdict]):
            by_id[bid] = {"curated": curated, "created": b.get("created")}
        return {"curated": curated, "by_id": by_id}
    except Exception as e:  # noqa: BLE001
        log.error("hk provenance failed: %s", e)
        return {"curated": None, "by_id": {}}


def _hk_freshness(data: dict) -> dict:
    """Basket price as-of date + stale flag (>3 trading days older than today)."""
    try:
        import pandas as pd
        asof = (data.get("chart") or {}).get("dates", [None])[-1] or data.get("as_of")
        if not asof:
            return {"as_of": None, "stale": False, "trading_days_old": None}
        today = pd.Timestamp.utcnow().normalize().tz_localize(None)
        n_bdays = int(len(pd.bdate_range(pd.Timestamp(asof), today))) - 1
        return {"as_of": str(asof), "trading_days_old": max(0, n_bdays),
                "stale": n_bdays > STALE_TRADING_DAYS, "threshold": STALE_TRADING_DAYS}
    except Exception as e:  # noqa: BLE001
        log.error("hk freshness failed: %s", e)
        return {"as_of": None, "stale": False, "trading_days_old": None}


def _hk_radar() -> dict:
    """Drawdown-risk banner from the HK risk_radar_intl snapshot (presence-guarded)."""
    try:
        from engine import risk_radar_intl as _rri
        snap = _rri.snapshot(_rri.HK_PROFILE)
        if not snap or snap.get("state") is None:
            return {}
        dd = snap.get("drawdown_prob")
        dd21 = dd.get("h21") if isinstance(dd, dict) else dd     # h21 scalar for the banner
        return {"state": snap.get("state"), "market": "hk",
                "dominant_scare": snap.get("dominant_scare"),
                "drawdown_prob": dd21,
                "asof": snap.get("asof")}
    except Exception as e:  # noqa: BLE001
        log.error("hk risk-radar strip failed: %s", e)
        return {}


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.baskets_hk import compute_hk_baskets
        data = compute_hk_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("hk baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no hk baskets (need data/baskets_hk/membership.json + hk_search cache) — skipping")
        return 0

    # THEME ROTATION DESK (regionalized) + region alerts (additive)
    theme_alerts_recent = []
    try:
        from engine.theme_scoring import compute_theme_intel
        ti = compute_theme_intel('hk')
        if ti:
            data['theme_intel'] = ti
            from engine import theme_alerts
            theme_alerts.rebuild(ti, 'hk')
            theme_alerts_recent = theme_alerts.recent(30, as_of=ti.get('as_of'), region='hk')
    except Exception as e:  # noqa: BLE001
        log.error('hk theme desk failed: %s', e)

    # 🔥 FORMING NARRATIVES (engine.narrative_emergence) — coherent, TIGHTENING HK groups
    # not yet in a basket, with clean-entry recommended tickers. Display-only, additive, noisy.
    emergence = None
    try:
        from engine.narrative_emergence import compute_emergence
        emergence = compute_emergence('hk')
        if emergence:
            from engine import emergence_alerts
            emergence_alerts.rebuild(emergence, 'hk')
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error('hk narrative emergence failed: %s', e)

    # W5 — persist the per-basket EW level SERIES + 20d rel (the gap §5.2), then compute the
    # sector-ignition strip, log+grade the ignition forward ledger, and build the desk-header
    # provenance/freshness + risk-radar strip payloads. All additive, None-safe, guarded.
    _persist_hk_levels(data)          # persist first so ignition grading reads the fresh series
    ignition = _hk_ignition(data)
    provenance = _hk_provenance(data)
    freshness = _hk_freshness(data)
    radar = _hk_radar()

    fdir = site / "hkbasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))
    # SECTOR PULSE — compact per-theme rotation data product. Also merges velocity/heat keys
    # into theme_intel for the rotation-scorecard page enhancements. Additive — never breaks build.
    try:
        if data.get("theme_intel"):
            from engine import sector_pulse as _sp
            _sp.write_pulse(data["theme_intel"], "hk", fdir)
            _sp.merge_pulse_into_theme_intel(data["theme_intel"], "hk")
            _sp.write_score_snapshot(data["theme_intel"], "hk")   # accrues the baskets_hk velocity stream
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_pulse hk hook failed: %s", e)
    if emergence:
        (fdir / "narrative_emergence.json").write_text(
            json.dumps(emergence, separators=(",", ":"), ensure_ascii=False, default=str))

    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets_hk.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(chart, separators=(",", ":")),
        theme_alerts_json=json.dumps(theme_alerts_recent, separators=(",", ":")),
        ignition_json=json.dumps(ignition, separators=(",", ":"), ensure_ascii=False),
        provenance_json=json.dumps(provenance, separators=(",", ":"), ensure_ascii=False),
        freshness_json=json.dumps(freshness, separators=(",", ":"), ensure_ascii=False),
        radar_json=json.dumps(radar, separators=(",", ":"), ensure_ascii=False),
        bench_en="Hang Seng", bench_zh="恒生指数",
        generated_utc=built)
    write_page(site / "baskets_hk.html", html)
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, 'hk')
        deskjs = config.ROOT / 'templates' / 'baskets_desk.js'
        if deskjs.exists():
            (site / 'baskets_desk.js').write_text(deskjs.read_text())
        ne = config.ROOT / 'templates' / 'forming_narratives.js'
        if ne.exists():
            (site / 'forming_narratives.js').write_text(ne.read_text())
    except Exception as e:  # noqa: BLE001
        log.error('hk theme detail pages failed: %s', e)
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_hk.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)

    # W3.8 — FREEZE HK basket levels + membership hashes (append-only, PIT).
    # chart was popped from data above and is still in scope.
    try:
        from engine.basket_freeze import freeze_domain, FreezeSkipped
        from engine.baskets_hk import _membership as _hk_mem, _closes as _hk_closes
        _hk_mem_data = _hk_mem()
        try:
            _hk_cl = _hk_closes()
        except Exception:  # noqa: BLE001
            _hk_cl = None
        _freeze_result = freeze_domain("hk", {"chart": chart}, _hk_cl, _hk_mem_data)
        log.info("basket_freeze[hk]: %s", _freeze_result)
    except FreezeSkipped as e:
        log.error("basket_freeze[hk]: SKIPPED (churn guard): %s", e)
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[hk]: failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
