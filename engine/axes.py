"""Growth and inflation axis scoring.

Each component is scored -1/0/+1 by direction of change: its 20d slope,
z-scored against the trailing 60d distribution of that slope (windows in
config). Axis score = weighted mean of available components in [-1, +1].
Confidence = |score| x agreement ratio (fraction of non-zero components
pointing the axis's way). Monthly econ series enter as sign-of-trend
confirmations at lower weight — markets lead, econ confirms.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import score_from_z, slope_z
from lib import config


def _component_scores(f: pd.DataFrame, axis: str) -> pd.DataFrame:
    cfg = config.load()["engine"]
    sw = cfg["scoring"]["slope_window"]
    bw = cfg["scoring"]["baseline_window"]
    zt = cfg["scoring"]["z_threshold"]

    def trend(col: str, use_log: bool = True) -> pd.Series:
        if col not in f or f[col].isna().all():
            return pd.Series(np.nan, index=f.index)
        return score_from_z(slope_z(f[col], sw, bw, use_log=use_log), zt)

    def monthly_sign(col: str, periods: int) -> pd.Series:
        """Slow confirmation: sign of the n-month change of a monthly series."""
        if col not in f or f[col].isna().all():
            return pd.Series(np.nan, index=f.index)
        chg = f[col].diff(periods)
        s = pd.Series(np.sign(chg), index=f.index)
        s[chg.isna()] = np.nan
        return s

    if axis == "growth":
        return pd.DataFrame({
            "copper_gold": trend("copper_gold"),
            "xly_xlp": trend("xly_xlp"),
            "us2y_direction": trend("us2y", use_log=False),
            "iwm_spy": trend("iwm_spy"),
            "cyclical_defensive": trend("cyc_def"),
            "breadth_direction": trend("pct_above_50", use_log=False),
            "payrolls_trend": monthly_sign("payrolls", 63),   # ~3 months of bdays
            "indpro_trend": monthly_sign("indpro", 252),      # yoy
            "wei_trend": monthly_sign("wei", 65),             # 13-week growth-nowcast direction (2008->)
            "gdpnow_trend": monthly_sign("gdpnow", 63),       # QoQ GDPNow direction (2011->)
        })
    if axis == "inflation":
        return pd.DataFrame({
            "breakeven_10y_direction": trend("breakeven_10y", use_log=False),
            "breakeven_5y5y_direction": trend("breakeven_5y5y", use_log=False),
            "energy_rs": trend("energy_rs"),
            "oil_trend": trend("oil"),
            "inflation_beta_basket": trend("infl_basket"),
            "tips_nominal_momentum": trend("tips_nominal_spread", use_log=False),
            "sticky_cpi_direction": monthly_sign("sticky_cpi_3m", 63),  # persistent-inflation direction
        })
    raise ValueError(axis)


def score_axis(f: pd.DataFrame, axis: str) -> pd.DataFrame:
    """Returns DataFrame: score, confidence, agreement, n_components, plus one
    column per component score (prefixed c_)."""
    cfg = config.load()["engine"]
    comp_cfg = cfg[f"{axis}_axis"]["components"]
    min_comp = cfg["scoring"]["min_components"]

    scores = _component_scores(f, axis)
    weights = pd.Series({k: v["weight"] for k, v in comp_cfg.items()})
    scores = scores[[c for c in scores.columns if c in weights.index]]
    w = weights[scores.columns]

    avail = scores.notna()
    wsum = avail.mul(w, axis=1).sum(axis=1)
    axis_score = scores.fillna(0).mul(w, axis=1).sum(axis=1) / wsum.replace(0, np.nan)

    n_nonzero = ((scores != 0) & avail).sum(axis=1)
    n_pos = (scores > 0).sum(axis=1)
    n_neg = (scores < 0).sum(axis=1)
    agreement = (pd.concat([n_pos, n_neg], axis=1).max(axis=1) / n_nonzero.replace(0, np.nan)).fillna(0)

    n_comp = avail.sum(axis=1)
    confidence = (axis_score.abs() * agreement).where(n_comp >= min_comp, 0.0)

    out = pd.DataFrame({
        f"{axis}_score": axis_score,
        f"{axis}_confidence": confidence,
        f"{axis}_agreement": agreement,
        f"{axis}_n_components": n_comp,
    })
    for c in scores.columns:
        out[f"c_{axis}_{c}"] = scores[c]
    return out
