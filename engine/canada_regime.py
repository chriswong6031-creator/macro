"""Canada quad classification — mirror of engine/china_regime.py.

Reuses the growth×inflation quad framework (raw_quad, apply_hysteresis) unchanged;
supplies a Canada liquidity overlay (BoC stance via policy-rate direction + GoC
curve steepening) and a simplified cycle tag (index-near-high vs breadth divergence).
The commodity / CAD / BoC-vs-Fed cross-asset read lives in engine/canada_overlay.py
and is surfaced as the dashboard hero rather than scored into the quad pre-validation.
"""
from __future__ import annotations

import pandas as pd

from engine.canada_axes import score_axis
from engine.regime import apply_hysteresis, raw_quad
from lib import config

# Canada quad labels — keys must match canada.engine.sector_preferences in config.yml
CANADA_QUAD_NAMES = {"Q1": "Goldilocks", "Q2": "Reflation",
                     "Q3": "Stagflation", "Q4": "Growth-scare"}


def liquidity_overlay(f: pd.DataFrame) -> pd.Series:
    """BoC stance proxy: direction of the policy (overnight) rate over ~3 months
    (cuts = expanding credit, hikes = contracting). A steepening GoC 2s10s adds an
    easing tilt (the curve un-inverting ahead of/with cuts)."""
    out = pd.Series("unknown", index=f.index)
    if "policy_rate" not in f or f["policy_rate"].isna().all():
        return out
    roc = f["policy_rate"].diff(63)                 # ~3-month change in the policy rate
    out[:] = "neutral"
    out[roc < -0.10] = "expanding"                  # rate cuts
    out[roc > 0.10] = "contracting"                 # rate hikes
    if "curve_2s10s" in f and not f["curve_2s10s"].isna().all():
        steepening = f["curve_2s10s"].diff(20) > 0.05
        out[steepening & (out == "neutral")] = "expanding"
    out[roc.isna()] = "unknown"
    return out


def cycle_tag(f: pd.DataFrame) -> pd.Series:
    cfg = config.load()["canada"]["engine"]["cycle"]
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
    qcfg = config.load()["canada"]["engine"]["quad"]
    gx = score_axis(f, "growth")
    ix = score_axis(f, "inflation")
    out = pd.concat([gx, ix], axis=1)

    hyst = apply_hysteresis(out["growth_score"], out["inflation_score"],
                            qcfg["hysteresis_days"], qcfg["shock_override_z"])
    out = out.join(hyst)
    out["raw_quad"] = [raw_quad(g, i) for g, i in zip(out["growth_score"], out["inflation_score"])]
    out["quad_name"] = out["quad"].map(lambda q: CANADA_QUAD_NAMES.get(q, q) if q else None)
    out["liquidity"] = liquidity_overlay(f)
    out["cycle"] = cycle_tag(f)
    out["regime_confidence"] = out[["growth_confidence", "inflation_confidence"]].mean(axis=1)
    return out
