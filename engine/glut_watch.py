"""Glut watch — exit-risk leg of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md). The mirror image of engine/bottleneck.py.

Every supply-constrained bull market ends the same way: the shortage pulls in a capacity
response, supply catches demand, pricing power fades, and the rerating reverses into a glut.
The 13D HBM thesis itself carries this exit risk (IEEE Spectrum: "new supply may arrive just
as AI demand growth slows"). The desk that catches the bottleneck early MUST also watch for
the glut — buy the bottleneck, exit before the glut.

This inverts the bottleneck legs and adds the distinctive glut precursor (capacity EXPANDING
to chase the shortage), all on the same free FRED series the bottleneck engine already uses:
  leg1 cap-U rolling over   : capacity utilization momentum turning DOWN from a high
  leg2 inventory restocking  : inventories/sales momentum turning UP
  leg3 backlog draining      : unfilled-orders/shipments momentum turning DOWN
  leg4 pricing fading         : industry PPI YoY DECELERATING
  leg5 supply response        : industrial CAPACITY growing fast (new capacity coming online)
  leg6 glut language (text)  : EDGAR capacity-adds phrases ("new fab", "capacity expansion"…)
                               via data/edgar/glut_hits.parquet (§3.6 of the upgrade spec)

Plus a demand cross-check: if the customer-capex pool (engine/demand_capex) is COOLING while
supply expands, the glut is closer. DISPLAY-ONLY; reuses bottleneck's loaders; returns None /
partial cleanly until the FRED series collect. Watchlist/exit-clock, never a sized signal.

Text leg (polarity fallback b): no snippet available from EDGAR FTS endpoint — same fallback
as bottleneck.py. Distinct-filer gate (≥2) applies. Weight PROVISIONAL, shadow-calibration
pending (§3.2).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from engine.bottleneck import INV_SALES, LANG_MIN_FILERS, THEME_MAP, _series, _yoy, _z
from lib import config

log = logging.getLogger(__name__)

MOM = 6                    # months for the momentum (rolling-over) reads
# industrial CAPACITY level series per NAICS (the supply-response leg); only where free
CAPACITY = {"3344": "CAPG3344S"}
UNFILLED, SHIPMENTS = "AMTMUO", "AMTMVS"
# Numeric legs rebalanced to 0.75 total to accommodate leg6_glut_language at 0.25.
# Original: 0.24:0.22:0.22:0.20:0.12 → scaled × (0.75/1.0)
WEIGHTS = {
    "leg1_caputil_rollover":  0.18,
    "leg2_inventory_restock": 0.165,
    "leg3_backlog_drain":     0.165,
    "leg4_pricing_fade":      0.15,
    "leg5_supply_response":   0.09,
    # PROVISIONAL weight — shadow-calibration pending (§3.2 / Wave 3a).
    "leg6_glut_language":     0.25,
}

GLUT_LANG_Z_LIVE = 0.5    # PROVISIONAL live cutoff; accel > 0 = net capacity-adds language


def _glut_language_accel(tickers: list[str]) -> tuple[float | None, int, int]:
    """EDGAR capacity-adds phrase mention acceleration for the theme's filers (last 120d vs
    prior 120d). Reads data/edgar/glut_hits.parquet (§3.6).

    With polarity=null (fallback b), all non-negated hits count.
    Returns (accel_ratio, recent_hits, n_distinct_filers). None if collector hasn't run."""
    p = config.data_dir() / "edgar" / "glut_hits.parquet"
    if not p.exists():
        return None, 0, 0
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None, 0, 0
    if df.empty or "ticker" not in df.columns or "file_date" not in df.columns:
        return None, 0, 0
    df = df[df["ticker"].isin(tickers)].copy()
    if df.empty:
        return 0.0, 0, 0
    # Filter out negated hits when polarity column is available and populated
    if "polarity" in df.columns:
        df = df[df["polarity"] != "negated"]
    df["file_date"] = pd.to_datetime(df["file_date"])
    end = df["file_date"].max()
    recent = df[df["file_date"] > end - pd.Timedelta(days=120)]
    prior = df[(df["file_date"] <= end - pd.Timedelta(days=120)) &
               (df["file_date"] > end - pd.Timedelta(days=240))]
    nr, npq = len(recent), len(prior)
    accel = round((nr - npq) / max(npq, 1), 2)
    n_distinct = recent["ticker"].nunique() if len(recent) else 0
    return accel, nr, n_distinct


def _mom_z(s: pd.Series | None, n: int = MOM) -> float | None:
    """z-score of the latest n-month CHANGE vs the history of n-month changes. Captures
    'is the recent momentum unusual', the rolling-over / re-accelerating tell."""
    if s is None or len(s) < (n + 24):
        return None
    d = s.diff(n).dropna()
    return _z(d)


def _backlog_ratio() -> pd.Series | None:
    unf, shp = _series(UNFILLED), _series(SHIPMENTS)
    if unf is None or shp is None:
        return None
    df = pd.concat([unf, shp], axis=1).dropna()
    return (df.iloc[:, 0] / df.iloc[:, 1]).dropna() if not df.empty else None


def _band(score: float | None, n: int, regime: bool) -> str:
    if score is None:
        return "AWAITING_DATA"
    if regime and score > 1.0:
        return "GLUT"
    if score > 0.6:
        return "GLUT_FORMING"
    if score > 0.25:
        return "EARLY_GLUT"
    return "STABLE"


def _theme_glut(spec: dict, name: str, inv_mom: float | None, backlog_mom: float | None,
                demand_band: str | None, tickers: list[str] | None = None) -> dict:
    cap_u = _series(spec["cap_u"])
    ppi = _series(spec["ppi"]) if spec.get("ppi") else None
    cap = _series(CAPACITY.get(spec["naics"])) if CAPACITY.get(spec["naics"]) else None

    leg1 = _mom_z(cap_u)                       # cap-U rolling over -> rising momentum-z is BAD
    leg1 = -leg1 if leg1 is not None else None  # falling cap-U (neg momentum) = + glut
    leg2 = inv_mom                              # inventories/sales rising = + glut (already signed)
    leg3 = -backlog_mom if backlog_mom is not None else None   # backlog draining = + glut
    ppi_yoy = _yoy(ppi)
    leg4 = _mom_z(ppi_yoy, 3)                   # PPI yoy decelerating
    leg4 = -leg4 if leg4 is not None else None
    leg5 = None
    if cap is not None and len(cap) >= 24:
        leg5 = _z(cap.pct_change(12).dropna() * 100.0)   # fast capacity growth = supply response

    # leg6: EDGAR capacity-adds language (§3.6 glut text tier) — PROVISIONAL weight
    lang_accel, lang_hits, lang_filers = _glut_language_accel(tickers or [])
    # Convert accel to a z-like score clipped to [-2, 2] (same approach as bottleneck leg6)
    lang_z: float | None = None
    if lang_accel is not None:
        import numpy as np  # noqa: PLC0415
        lang_z = round(float(np.clip(lang_accel, -2.0, 2.0)), 2)

    legs = {
        "leg1_caputil_rollover":  leg1,
        "leg2_inventory_restock": leg2,
        "leg3_backlog_drain":     leg3,
        "leg4_pricing_fade":      leg4,
        "leg5_supply_response":   leg5,
        "leg6_glut_language":     lang_z,
    }
    avail = {k: v for k, v in legs.items() if v is not None}
    if not avail:
        score, n, regime = None, 0, False
    else:
        wsum = sum(WEIGHTS[k] for k in avail)
        score = round(sum(WEIGHTS[k] * v for k, v in avail.items()) / wsum, 2)
        n = len(avail)
        core = ["leg1_caputil_rollover", "leg2_inventory_restock", "leg3_backlog_drain", "leg4_pricing_fade"]
        regime = all((legs[k] or 0) > 0 for k in core) and all(legs[k] is not None for k in core)

    band = _band(score, n, regime)
    # demand cross-check: a cooling capex pool brings the glut closer (display nuance only)
    if band in ("EARLY_GLUT", "GLUT_FORMING") and demand_band in ("COOLING", "CONTRACTING"):
        band = "GLUT_FORMING" if band == "EARLY_GLUT" else "GLUT"

    # Text-only glut band: language leg alone (no numeric FRED legs available)
    numeric_avail = {k: v for k, v in avail.items() if k != "leg6_glut_language"}
    if not numeric_avail and lang_z is not None:
        # Language-only read; band capped at "GLUT_FORMING (text)"
        if lang_accel is not None and lang_accel > GLUT_LANG_Z_LIVE and lang_filers >= LANG_MIN_FILERS:
            band = "GLUT_FORMING (text)"
        elif band in ("AWAITING_DATA", "STABLE"):
            band = "STABLE"  # no numeric + no strong language → stable

    return {
        "name": name, "naics": spec["naics"], "band": band, "glut_score": score,
        "regime": regime, "n_legs": n, "legs": legs,
        "glut_language_accel": lang_accel, "glut_language_hits": lang_hits,
        "glut_language_filers": lang_filers,
        "glut_language_detail": {"value": lang_z, "accel": lang_accel,
                                 "hits": lang_hits, "n_filers": lang_filers, "provisional": True},
        "weights": {k: WEIGHTS[k] for k in legs},
    }


def compute_glut_watch(demand: dict | None = None, write_ledger: bool = True) -> dict | None:
    """Per-theme exit-risk read over the mapped themes. DISPLAY-ONLY. None until FRED collects.

    leg6_glut_language (§3.6): EDGAR capacity-adds phrases swept from glut_hits.parquet.
    Weight PROVISIONAL (shadow-calibration pending). For mapped themes only; unmapped themes
    remain outside the glut engine (no physical NAICS anchor).
    """
    inv_mom = _mom_z(_series(INV_SALES))           # inventories/sales rising = restocking
    backlog_mom = _mom_z(_backlog_ratio())
    if demand is None:
        try:
            from engine.demand_capex import compute_demand_capex
            demand = compute_demand_capex()
        except Exception:  # noqa: BLE001
            demand = None
    dm_themes = (demand or {}).get("themes") or {}

    themes = (config.load() or {}).get("themes") or {}
    out: dict[str, dict] = {}
    for key, spec in themes.items():
        m = THEME_MAP.get(key)
        if m is None:
            continue
        try:
            dband = (dm_themes.get(key) or {}).get("demand_band")
            tickers = spec.get("tickers") or []
            out[key] = _theme_glut(m, spec.get("name", key), inv_mom, backlog_mom, dband,
                                   tickers=tickers)
        except Exception as e:  # noqa: BLE001 — one theme failing never blocks the rest
            log.warning("glut_watch[%s] failed: %s", key, e)
    if not out:
        return None

    payload = {
        "asof": None,
        "n_themes": len(out),
        "themes": out,
        "note": ("display-only; exit-risk mirror of the bottleneck. Buy the bottleneck, exit "
                 "before the glut. GLUT_FORMING/GLUT = trim / exit clock, never a sized signal."),
    }
    dates = []
    for key in out:
        s = _series(THEME_MAP[key]["cap_u"])
        if s is not None:
            dates.append(s.index.max())
    if dates:
        payload["asof"] = str(pd.to_datetime(max(dates)).date())

    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("glut_watch ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict) -> None:
    """Append-only forward-grading: one row per (theme, asof) where a glut is forming —
    graded forward against the beneficiary basket's subsequent drawdown."""
    d = config.data_dir() / "glut_watch"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("theme"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue
    ts = datetime.now(timezone.utc).isoformat()
    asof = payload.get("asof")
    cfg_themes = (config.load() or {}).get("themes") or {}     # PIT membership snapshot for the grader
    lines = []
    for key, t in payload["themes"].items():
        if t["band"] not in ("GLUT_FORMING", "GLUT") or (key, asof) in seen:
            continue
        lines.append(json.dumps({"theme": key, "asof": asof, "ts": ts, "band": t["band"],
                                 "glut_score": t["glut_score"], "regime": t["regime"],
                                 "members": (cfg_themes.get(key) or {}).get("tickers") or []},
                                separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
