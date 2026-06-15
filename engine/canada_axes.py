"""Growth and inflation axis scoring for Canada — mirror of engine/china_axes.py.

Same machinery (each component scored -1/0/+1, axis = weighted mean over what's
available, confidence = |score| x agreement, monthly econ enters as direction
confirmation). Canada specifics:
  - GDP-by-industry (StatsCan) and CPI (BoC) enter by the direction of their YoY.
  - unemployment enters INVERTED (falling unemployment = growth positive).
  - cyclical/defensive, TSX/SPX, copper/gold and the inflation-beta basket are
    daily price ratios (slope_z). breakeven (10y - RRB) is a daily yield spread.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import score_from_z, slope_z
from lib import config


def _cfg() -> dict:
    return config.load()["canada"]["engine"]


def _trend(f: pd.DataFrame, col: str, use_log: bool = True) -> pd.Series:
    sc = _cfg()["scoring"]
    if col not in f or f[col].isna().all():
        return pd.Series(np.nan, index=f.index)
    return score_from_z(slope_z(f[col], sc["slope_window"], sc["baseline_window"], use_log=use_log),
                        sc["z_threshold"])


def _monthly_sign(f: pd.DataFrame, col: str, periods: int) -> pd.Series:
    if col not in f or f[col].isna().all():
        return pd.Series(np.nan, index=f.index)
    chg = f[col].diff(periods)
    s = pd.Series(np.sign(chg), index=f.index)
    s[chg.isna()] = np.nan
    return s


def _component_scores(f: pd.DataFrame, axis: str) -> pd.DataFrame:
    if axis == "growth":
        return pd.DataFrame({
            "gdp_trend": _monthly_sign(f, "gdp_yoy", 63),
            "unemployment_trend": -1.0 * _monthly_sign(f, "unemployment", 63),  # falling jobless = growth+
            "cyclical_defensive": _trend(f, "cyc_def"),
            "global_growth": _trend(f, "copper_gold"),
            "breadth_direction": _trend(f, "pct_above_50", use_log=False),
            "tsx_spx": _trend(f, "tsx_spx"),
        })
    if axis == "inflation":
        return pd.DataFrame({
            "cpi_direction": _monthly_sign(f, "cpi_yoy", 63),
            "breakeven_direction": _trend(f, "breakeven", use_log=False),
            "inflation_beta_basket": _trend(f, "infl_basket"),
        })
    raise ValueError(axis)


def score_axis(f: pd.DataFrame, axis: str) -> pd.DataFrame:
    ecfg = _cfg()
    comp_cfg = ecfg[f"{axis}_axis"]["components"]
    min_comp = ecfg["scoring"]["min_components"]

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
