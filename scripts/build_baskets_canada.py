"""Build the Canada thematic-baskets page -> site/baskets_canada.html (+ canadabasketdata/baskets.json).

The Canada analogue of scripts/build_baskets_china.py. Reads data/baskets_canada/membership.json +
the canada_search close cache + the benchmark via engine.baskets_canada.compute_canada_baskets() and renders the same
FactorWatch-style baskets view. Additive — any failure logs and returns 0 so it can never
break the rest of the site.

Usage: python -m scripts.build_baskets_canada
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
log = logging.getLogger("build_baskets_canada")

STALE_TRADING_DAYS = 3     # §5.2 hard freshness gate: warn when basket prices > this old vs today
# Oil-flip applies to resource sleeves ONLY (oil overlay factor). Precious Metals (gold/silver)
# excluded on purpose — gold/copper transmission is NO-GO per the red-team reports (§4/§5.1).
CA_RESOURCE_CATEGORIES = ("Energy", "Materials")


def _ca_overlay() -> dict:
    """The CA cross-asset overlay snapshot the builder already has — reused for the oil-flip flag."""
    try:
        from engine import canada_overlay as _cov
        return _cov.snapshot() or {}
    except Exception as e:  # noqa: BLE001
        log.error("canada overlay snapshot failed: %s", e)
        return {}


def _ca_ignition(data: dict, overlay: dict) -> dict:
    """Sector-ignition strip (engine.sector_ignition) + forward ledger. CA adds the oil-flip.

    The ledger legs self-gate on ignition_audit.ledger_lane_armed() (COLLECT_LANE=nightly —
    daily.yml's engine job, this ledger's advancing lane, sets it job-wide). Off-lane
    (closing-bell / engine-render / render run this via build_vector) snapshot_and_grade is
    a pure scorecard read, so the scoreboard still renders."""
    try:
        from engine.sector_ignition import compute_ignition
        from engine.baskets_canada import _closes, member_closes_getter
        closes = _closes()
        getter = member_closes_getter(closes)
        ign = compute_ignition(data.get("chart") or {}, data.get("baskets") or [],
                               getter, market="ca", overlay=overlay,
                               resource_categories=CA_RESOURCE_CATEGORIES)
        try:
            from engine import ignition_audit as _ia
            from engine import basket_levels_persist as _blp
            sc = _ia.snapshot_and_grade(
                ign, "ca",
                level_of=lambda bid: _blp.level_series("ca", bid),
                bench_series=_blp.bench_series("ca"))
            ign["scoreboard"] = sc
        except Exception as e:  # noqa: BLE001
            log.error("canada ignition ledger failed: %s", e)
        return ign
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("canada ignition failed: %s", e)
        return {"market": "ca", "items": [], "as_of": None, "has_southbound_leg": False}


def _persist_ca_levels(data: dict) -> None:
    try:
        from engine import basket_levels_persist as _blp
        _blp.persist(data, "ca")
    except Exception as e:  # noqa: BLE001
        log.error("canada basket-levels persist failed: %s", e)


def _ca_provenance(data: dict) -> dict:
    try:
        from engine.baskets_canada import _membership
        mem = _membership() or {}
        curated = mem.get("curated")
        bdict = mem.get("baskets") or {}
        by_id = {}
        for bid, b in (bdict.items() if isinstance(bdict, dict) else [(x["id"], x) for x in bdict]):
            by_id[bid] = {"curated": curated, "created": b.get("created")}
        return {"curated": curated, "by_id": by_id}
    except Exception as e:  # noqa: BLE001
        log.error("canada provenance failed: %s", e)
        return {"curated": None, "by_id": {}}


def _ca_freshness(data: dict) -> dict:
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
        log.error("canada freshness failed: %s", e)
        return {"as_of": None, "stale": False, "trading_days_old": None}


def _ca_radar() -> dict:
    try:
        from engine import risk_radar_intl as _rri
        snap = _rri.snapshot(_rri.CA_PROFILE)
        if not snap or snap.get("state") is None:
            return {}
        dd = snap.get("drawdown_prob")
        dd21 = dd.get("h21") if isinstance(dd, dict) else dd     # h21 scalar for the banner
        return {"state": snap.get("state"), "market": "ca",
                "dominant_scare": snap.get("dominant_scare"),
                "drawdown_prob": dd21,
                "asof": snap.get("asof")}
    except Exception as e:  # noqa: BLE001
        log.error("canada risk-radar strip failed: %s", e)
        return {}


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.baskets_canada import compute_canada_baskets
        data = compute_canada_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("canada baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no canada baskets (need data/baskets_canada/membership.json + canada_search cache) — skipping")
        return 0

    # THEME ROTATION DESK (regionalized) + region alerts (additive)
    theme_alerts_recent = []
    try:
        from engine.theme_scoring import compute_theme_intel
        ti = compute_theme_intel('canada')
        if ti:
            data['theme_intel'] = ti
            from engine import theme_alerts
            theme_alerts.rebuild(ti, 'canada')
            theme_alerts_recent = theme_alerts.recent(30, as_of=ti.get('as_of'), region='canada')
    except Exception as e:  # noqa: BLE001
        log.error('canada theme desk failed: %s', e)

    # 🔥 FORMING NARRATIVES (engine.narrative_emergence) — coherent, TIGHTENING TSX groups
    # not yet in a basket, with clean-entry recommended tickers. Display-only, additive, noisy.
    emergence = None
    try:
        from engine.narrative_emergence import compute_emergence
        emergence = compute_emergence('canada')
        if emergence:
            from engine import emergence_alerts
            emergence_alerts.rebuild(emergence, 'canada')
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error('canada narrative emergence failed: %s', e)

    # W5 — persist basket level series, sector-ignition strip (+ oil-flip), forward ledger,
    # provenance/freshness/risk-radar payloads. Additive, None-safe, guarded.
    _persist_ca_levels(data)          # persist first so ignition grading reads the fresh series
    overlay = _ca_overlay()
    ignition = _ca_ignition(data, overlay)
    provenance = _ca_provenance(data)
    freshness = _ca_freshness(data)
    radar = _ca_radar()

    fdir = site / "canadabasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))
    # SECTOR PULSE — compact per-theme rotation data product. Also merges velocity/heat keys
    # into theme_intel for the rotation-scorecard page enhancements. Additive — never breaks build.
    try:
        if data.get("theme_intel"):
            from engine import sector_pulse as _sp
            _sp.write_pulse(data["theme_intel"], "canada", fdir)
            _sp.merge_pulse_into_theme_intel(data["theme_intel"], "canada")
            _sp.write_score_snapshot(data["theme_intel"], "canada")   # accrues the baskets_canada velocity stream
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_pulse canada hook failed: %s", e)
    if emergence:
        (fdir / "narrative_emergence.json").write_text(
            json.dumps(emergence, separators=(",", ":"), ensure_ascii=False, default=str))

    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("baskets_canada.html.j2").render(
        baskets_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        chart_json=json.dumps(chart, separators=(",", ":")),
        theme_alerts_json=json.dumps(theme_alerts_recent, separators=(",", ":")),
        ignition_json=json.dumps(ignition, separators=(",", ":"), ensure_ascii=False),
        provenance_json=json.dumps(provenance, separators=(",", ":"), ensure_ascii=False),
        freshness_json=json.dumps(freshness, separators=(",", ":"), ensure_ascii=False),
        radar_json=json.dumps(radar, separators=(",", ":"), ensure_ascii=False),
        bench_en="S&P/TSX", bench_zh="标普/TSX",
        generated_utc=built)
    write_page(site / "baskets_canada.html", html)
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, 'canada')
        deskjs = config.ROOT / 'templates' / 'baskets_desk.js'
        if deskjs.exists():
            (site / 'baskets_desk.js').write_text(deskjs.read_text())
        ne = config.ROOT / 'templates' / 'forming_narratives.js'
        if ne.exists():
            (site / 'forming_narratives.js').write_text(ne.read_text())
    except Exception as e:  # noqa: BLE001
        log.error('canada theme detail pages failed: %s', e)
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_canada.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)

    # W0 — FREEZE Canada basket levels + membership hashes (append-only, PIT).
    # chart was popped from data above and is still in scope.
    try:
        from engine.basket_freeze import freeze_domain, FreezeSkipped
        from engine.baskets_canada import _membership as _ca_mem, _closes as _ca_closes
        _ca_mem_data = _ca_mem()
        try:
            _ca_cl = _ca_closes()
        except Exception:  # noqa: BLE001
            _ca_cl = None
        _freeze_result = freeze_domain("canada", {"chart": chart}, _ca_cl, _ca_mem_data)
        log.info("basket_freeze[canada]: %s", _freeze_result)
    except FreezeSkipped as e:
        log.error("basket_freeze[canada]: SKIPPED (churn guard): %s", e)
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[canada]: failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
