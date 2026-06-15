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

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("crossasset.html.j2").render(
        as_of=snap.get("asof"), built=built, regime=snap.get("regime"),
        breadth=snap.get("breadth"), trend=snap.get("trend"), ratios=snap.get("ratios"),
        carry=snap.get("carry"), correlation=snap.get("correlation"), note=snap.get("note"),
        leadlag=leadlag,
        liquidity=liquidity, liq_spark=(_sparkline(liquidity["spark"]) if liquidity else ""),
        funding=funding, fund_spark=(_sparkline(funding["spark"]) if funding else ""))
    site = config.ROOT / config.load()["storage"]["site_dir"]
    (site / "crossasset.html").write_text(html)
    log.info("wrote %s/crossasset.html (%d KB)", site, len(html) // 1024)

    # hub feed (consumed by build_vector's hub card; runs before build_vector)
    outdir = config.data_dir() / "crossasset"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "latest.json").write_text(json.dumps({
        "date": snap.get("asof"), "regime": snap.get("regime"),
        "breadth": snap.get("breadth"), "favored": snap.get("favored", []),
        "correlation": (snap.get("correlation") or {}).get("verdict"),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
