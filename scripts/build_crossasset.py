"""Build the Cross-Asset Vector page -> site/crossasset.html.

Standalone like build_commodities.py. Reads engine/cross_asset_trend.snapshot()
(TSMOM trend board + intermarket ratios + carry context) and the existing
correlation-regime leaf, and renders a REGIME/CONTEXT board. The trend factor is
academically contested and only modestly beats buy&hold after cost (verdict
CONTESTED, scripts/cross_asset_phase0.py), so the page frames it as a regime read,
never a strategy. UI only — never recomputes the validation.

Usage: python -m scripts.build_crossasset
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
log = logging.getLogger("build_crossasset")


def _sparkline(vals, w: int = 180, h: int = 38, pad: int = 3) -> str:
    """SVG polyline points for a tiny sparkline from a list of values."""
    vals = [v for v in (vals or []) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    return " ".join(f"{pad + i * (w - 2 * pad) / (n - 1):.1f},"
                    f"{pad + (h - 2 * pad) * (1 - (v - lo) / rng):.1f}"
                    for i, v in enumerate(vals))


def main() -> int:
    from engine import cross_asset_trend as cat
    try:
        snap = cat.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("cross-asset snapshot failed: %s", e)
        return 0
    if not snap:
        log.warning("cross-asset snapshot empty (need >=4 legs) — skipping page")
        return 0

    # global central-bank liquidity (additive macro-driver leaf; None if FRED data absent)
    try:
        from engine import global_liquidity
        liquidity = global_liquidity.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("global liquidity snapshot failed: %s", e)
        liquidity = None

    # funding/repo plumbing stress (additive leaf; None if OFR data absent)
    try:
        from engine import funding_stress
        funding = funding_stress.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("funding-stress snapshot failed: %s", e)
        funding = None

    # cross-asset lead/lag transmission read (additive leaf; HAC + FDR gated,
    # validated DISPLAY-only by scripts/cross_asset_leadlag_phase0.py — a regime
    # gauge, not a hedge ratio). None if <3 markets / too little overlap.
    try:
        from engine import cross_asset
        leadlag = cross_asset.leadlag_snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("lead/lag snapshot failed: %s", e)
        leadlag = None

    # Dollar factor — the forex Dollar Desk's cross-asset transmission (display-only,
    # contemporaneous). Degrades to None if build_forex hasn't written latest.json.
    try:
        from lib import forex_link
        _tr = forex_link.transmission()
        _rows = []
        for k in ("SPY", "EEM", "GC=F", "CL=F", "HG=F", "UST10", "BTC"):
            ac = forex_link.asset_corr(k, _tr)
            if ac:
                _rows.append({"label": ac["label"], "label_zh": ac["label_zh"],
                              "corr": ac["corr"], "stable": ac["stable"]})
        _rows.sort(key=lambda r: r["corr"])            # most negative (biggest headwind) first
        dollar_factor = {"rows": _rows, "usd_dir": _tr.get("usd_dir")} if _rows else None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("dollar-factor read failed: %s", e)
        dollar_factor = None

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("crossasset.html.j2").render(
        as_of=snap.get("asof"), built=built, regime=snap.get("regime"),
        breadth=snap.get("breadth"), trend=snap.get("trend"), ratios=snap.get("ratios"),
        carry=snap.get("carry"), correlation=snap.get("correlation"), note=snap.get("note"),
        leadlag=leadlag, dollar_factor=dollar_factor,
        liquidity=liquidity, liq_spark=(_sparkline(liquidity["spark"]) if liquidity else ""),
        funding=funding, fund_spark=(_sparkline(funding["spark"]) if funding else ""))
    site = config.ROOT / config.load()["storage"]["site_dir"]
    write_page(site / "crossasset.html", html)
    log.info("wrote %s/crossasset.html (%d KB)", site, len(html) // 1024)

    # hub feed (consumed by build_vector's hub card; runs before build_vector)
    outdir = config.data_dir() / "crossasset"
    outdir.mkdir(parents=True, exist_ok=True)

    # ── flows block (R6 — display-only, fail-open per sub-snapshot) ──────────
    # Each sub-field is None/[] when its source is absent (RUL-CA-1/CA-5).
    _FLOWS_NOTE = (
        "display-only regime read; TSMOM fails DSR (cross-asset-phase0), "
        "lead/lag=lag-1 timezone (cross-asset-leadlag-phase0) — "
        "not a strategy/hedge-ratio"
    )

    # correlation sub-block: from snap.correlation (cross_asset.snapshot())
    _corr_raw = snap.get("correlation") or {}
    _corr_block: dict | None
    if isinstance(_corr_raw, dict) and _corr_raw.get("verdict") not in (None, "unknown"):
        _corr_block = {
            "verdict": _corr_raw.get("verdict"),
            "absorption_pctile": _corr_raw.get("absorption_pctile_5y"),
            "n_markets": len(_corr_raw.get("markets") or []) or None,
        }
    else:
        _corr_block = None

    # trend_top: top 6 rows from snap.trend (tsmom panel rows)
    _trend_raw = snap.get("trend") or {}
    _trend_rows = (_trend_raw.get("rows") or [])[:6]
    _trend_top: list[dict] = [
        {"asset": r.get("key"), "trend": r.get("trend"), "z": r.get("score")}
        for r in _trend_rows
    ] if _trend_rows else []

    # intermarket: from snap.ratios (ratio_panel output)
    _ratios_raw = snap.get("ratios") or []
    _intermarket: list[dict] = [
        {"pair": r.get("key"), "ratio": r.get("value"), "trend": r.get("state")}
        for r in _ratios_raw
    ] if _ratios_raw else []

    # carry: compact from snap.carry
    _carry_raw = snap.get("carry") or {}
    _carry_block: dict | None = None
    _carry_rows = _carry_raw.get("rows") or []
    if _carry_rows:
        _carry_block = {"rows": _carry_rows, "note": _carry_raw.get("note")}

    # leadlag: from the cross_asset.leadlag_snapshot() computed above
    _leadlag_block: dict | None
    if leadlag is not None and isinstance(leadlag, dict):
        _ll_links = leadlag.get("links") or []
        _leadlag_block = {
            "verdict": leadlag.get("verdict"),
            "links": _ll_links[:6],
        }
    else:
        _leadlag_block = {"verdict": None, "links": []}

    # global_liquidity: compact from global_liquidity.snapshot()
    _liq_block: dict | None = None
    if liquidity is not None and isinstance(liquidity, dict):
        _liq_block = {
            "asof": liquidity.get("asof"),
            "state": liquidity.get("state"),
            "accel": liquidity.get("accel"),
            "total_usd_tn": liquidity.get("total_usd_tn"),
        }

    # funding_stress: compact from funding_stress.snapshot()
    _fund_block: dict | None = None
    if funding is not None and isinstance(funding, dict):
        _fund_block = {
            "asof": funding.get("asof"),
            "state": funding.get("state"),
            "score": funding.get("score"),
            "spread_bp": funding.get("spread_bp"),
        }

    _flows_block = {
        "schema": "crossasset_flows.v1",
        "display_only": True,
        "correlation": _corr_block,
        "breadth": snap.get("breadth"),
        "trend_top": _trend_top,
        "intermarket": _intermarket,
        "carry": _carry_block,
        "leadlag": _leadlag_block,
        "global_liquidity": _liq_block,
        "funding_stress": _fund_block,
        "note": _FLOWS_NOTE,
    }

    # ISO asof (NEW — keep "date" display string for backward compat)
    _asof_iso = snap.get("asof")  # already ISO date string from tsmom_panel

    (outdir / "latest.json").write_text(json.dumps({
        # ── LEGACY KEYS (byte-identical to pre-R6 contract; do NOT rename) ──
        "date": snap.get("asof"), "regime": snap.get("regime"),
        "breadth": snap.get("breadth"), "favored": snap.get("favored", []),
        "correlation": (snap.get("correlation") or {}).get("verdict"),
        # ── R6 ADDITIVE FIELDS ──
        "asof": _asof_iso,
        "flows": _flows_block,
    }, indent=2, default=str))
    log.info("wrote data/crossasset/latest.json with flows block")
    return 0


if __name__ == "__main__":
    sys.exit(main())
