"""Hong Kong quad classification — mirror of engine/china_regime.py.

Reuses the growth×inflation quad framework (raw_quad, apply_hysteresis) unchanged,
then layers the two things that actually move Hong Kong:
  - a DUAL liquidity overlay — PBoC stance (China M2 direction) AND Fed-via-peg
    (HKD distance toward the 7.85 weak-end + Stock-Connect southbound flow). HK has
    two liquidity taps: Mainland credit and US-shadowing rates via the peg.
  - the GLOBAL RISK overlay (engine.hk_global) — HK's primary high-frequency driver,
    attached as risk-on/off state + composite score + HKD peg sub-state.
Plus a simplified cycle tag (HSI near-high vs fading breadth).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import hk_global
from engine.hk_axes import score_axis
from engine.regime import apply_hysteresis, raw_quad
from lib import config

HK_QUAD_NAMES = {"Q1": "Goldilocks", "Q2": "Reflation",
                 "Q3": "Stagflation", "Q4": "Growth-scare"}


def liquidity_overlay(f: pd.DataFrame) -> pd.Series:
    """Dual liquidity: PBoC (China M2 direction) + Fed-via-peg (HKD weak-end
    pressure) + Stock-Connect southbound flow. Weighted net -> expanding/neutral/
    contracting."""
    lcfg = config.load()["hk"]["engine"]["liquidity"]
    w = lcfg["components"]
    parts: list[tuple[pd.Series, float]] = []

    if "m2_yoy" in f and not f["m2_yoy"].isna().all():
        roc = f["m2_yoy"] - f["m2_yoy"].shift(63)         # ~3-month change in M2 growth
        m2 = pd.Series(0.0, index=f.index)
        m2[roc > 0.2] = 1.0
        m2[roc < -0.2] = -1.0
        m2[roc.isna()] = np.nan
        parts.append((m2, w["m2_growth"]["weight"]))

    if "usdhkd" in f and not f["usdhkd"].isna().all():
        peg = hk_global.peg_frame(f["usdhkd"])["peg_pressure"]   # 0 strong .. 1 weak
        ps = pd.Series(0.0, index=f.index)
        ps[peg <= 0.25] = 1.0                              # strong-side = inflow/easing
        ps[peg >= 0.75] = -1.0                             # weak-side = outflow/tightening
        ps[peg.isna()] = np.nan
        parts.append((ps, w["peg_pressure"]["weight"]))

    # NOTE: an HKMA Aggregate-Balance leg was tested here and REMOVED — it inverted
    # the overlay's measured edge (see config hk.engine.liquidity). The Aggregate
    # Balance ships as a descriptive panel only, not a scored liquidity leg.

    if "southbound_cum" in f and not f["southbound_cum"].isna().all():
        sb = f["southbound_cum"].diff(lcfg["roc_window_d"])
        sbs = pd.Series(np.sign(sb), index=f.index)
        sbs[sb.isna()] = np.nan
        parts.append((sbs, w["southbound"]["weight"]))

    out = pd.Series("unknown", index=f.index)
    if not parts:
        return out
    score = pd.DataFrame({i: s for i, (s, _) in enumerate(parts)})
    wt = pd.Series({i: wv for i, (_, wv) in enumerate(parts)})
    avail = score.notna()
    wsum = avail.mul(wt, axis=1).sum(axis=1)
    net = score.fillna(0).mul(wt, axis=1).sum(axis=1) / wsum.replace(0, np.nan)
    out[:] = "neutral"
    out[net > 0.2] = "expanding"
    out[net < -0.2] = "contracting"
    out[net.isna()] = "unknown"
    return out


def cycle_tag(f: pd.DataFrame) -> pd.Series:
    cfg = config.load()["hk"]["engine"]["cycle"]
    idx_col = "market_index" if "market_index" in f else None
    out = pd.Series("mid", index=f.index)
    if idx_col is None or f[idx_col].isna().all():
        out[:] = "unknown"
        return out
    px = f[idx_col]
    near_high = px >= px.rolling(cfg["high_window_d"], min_periods=20).max() * (1 - cfg["index_near_high_pct"] / 100)
    if "pct_above_50" in f and not f["pct_above_50"].isna().all():
        breadth_falling = f["pct_above_50"].diff(20) < 0
        out[near_high & breadth_falling] = "late"
    rising = px.pct_change(60) > 0.05
    low_base = px <= px.rolling(252, min_periods=60).min() * 1.10
    out[rising & low_base] = "early"
    out[px.isna()] = "unknown"
    return out


def classify(f: pd.DataFrame) -> pd.DataFrame:
    qcfg = config.load()["hk"]["engine"]["quad"]
    gx = score_axis(f, "growth")
    ix = score_axis(f, "inflation")
    out = pd.concat([gx, ix], axis=1)

    hyst = apply_hysteresis(out["growth_score"], out["inflation_score"],
                            qcfg["hysteresis_days"], qcfg["shock_override_z"])
    out = out.join(hyst)
    out["raw_quad"] = [raw_quad(g, i) for g, i in zip(out["growth_score"], out["inflation_score"])]
    out["quad_name"] = out["quad"].map(lambda q: HK_QUAD_NAMES.get(q, q) if q else None)
    out["liquidity"] = liquidity_overlay(f)
    out["cycle"] = cycle_tag(f)

    # global risk overlay (HK's primary driver) — attach state + composite + peg
    gov = hk_global.composite(f.index)
    for col in ["global_score", "risk_state", "peg_distance", "peg_pressure", "peg_state"]:
        out[col] = gov[col] if col in gov.columns else np.nan

    out["regime_confidence"] = out[["growth_confidence", "inflation_confidence"]].mean(axis=1)
    return out
