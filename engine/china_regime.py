"""China quad classification — mirror of engine/regime.py.

Reuses the growth×inflation quad framework (raw_quad, apply_hysteresis, QUAD_NAMES)
unchanged; supplies a China liquidity overlay (PBoC stance via M2-YoY direction)
and a simplified cycle tag (index-near-high vs breadth divergence). No US macro
(no Fed balance sheet, no HY OAS, no 2s10s) is involved.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.china_axes import score_axis
from engine.regime import apply_hysteresis, raw_quad
from lib import config

# China quad labels — keys must match china.engine.sector_preferences in config.yml
CHINA_QUAD_NAMES = {"Q1": "Goldilocks", "Q2": "Reflation",
                    "Q3": "Stagflation", "Q4": "Growth-scare"}


def liquidity_overlay(f: pd.DataFrame) -> pd.Series:
    """PBoC stance proxy: direction of M2-YoY growth (rising = expanding credit).
    SHIBOR 3M falling adds an easing tilt when present."""
    out = pd.Series("unknown", index=f.index)
    if "m2_yoy" not in f or f["m2_yoy"].isna().all():
        return out
    roc = f["m2_yoy"] - f["m2_yoy"].shift(63)      # ~3-month change in M2 growth
    out[:] = "neutral"
    out[roc > 0.2] = "expanding"
    out[roc < -0.2] = "contracting"
    if "rate_3m" in f and not f["rate_3m"].isna().all():
        easing = f["rate_3m"].diff(20) < -0.05
        out[easing & (out == "neutral")] = "expanding"
    out[roc.isna()] = "unknown"
    return out


def cycle_tag(f: pd.DataFrame) -> pd.Series:
    cfg = config.load()["china"]["engine"]["cycle"]
    idx_col = "market_index" if "market_index" in f else None
    out = pd.Series("mid", index=f.index)
    if idx_col is None or f[idx_col].isna().all():
        out[:] = "unknown"
        return out
    px = f[idx_col]
    near_high = px >= px.rolling(cfg["high_window_d"], min_periods=20).max() * (1 - cfg["index_near_high_pct"] / 100)
    if "pct_above_50" in f and not f["pct_above_50"].isna().all():
        breadth_falling = f["pct_above_50"].diff(20) < 0
        out[near_high & breadth_falling] = "late"          # index high, internals fading
    rising = px.pct_change(60) > 0.05
    low_base = px <= px.rolling(252, min_periods=60).min() * 1.10
    out[rising & low_base] = "early"                       # recovering off a base
    out[px.isna()] = "unknown"
    return out


def classify(f: pd.DataFrame) -> pd.DataFrame:
    qcfg = config.load()["china"]["engine"]["quad"]
    gx = score_axis(f, "growth")
    ix = score_axis(f, "inflation")
    out = pd.concat([gx, ix], axis=1)

    hyst = apply_hysteresis(out["growth_score"], out["inflation_score"],
                            qcfg["hysteresis_days"], qcfg["shock_override_z"])
    out = out.join(hyst)
    out["raw_quad"] = [raw_quad(g, i) for g, i in zip(out["growth_score"], out["inflation_score"])]
    out["quad_name"] = out["quad"].map(lambda q: CHINA_QUAD_NAMES.get(q, q) if q else None)
    out["liquidity"] = liquidity_overlay(f)
    out["cycle"] = cycle_tag(f)
    out["regime_confidence"] = out[["growth_confidence", "inflation_confidence"]].mean(axis=1)
    return out
