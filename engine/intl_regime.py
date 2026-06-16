"""Uniform per-country regime classification for the International dashboard.

Every economy is scored on the SAME growth × inflation quad (so they compare
directly), reusing the shared hysteresis state machine (engine.regime.raw_quad,
apply_hysteresis) and the shared scoring transforms (engine.indicators). On top of
the quad we add a DISPLAY-ONLY recession-risk composite (history-anchored bands —
no per-country forward edge is claimed) and a central-bank liquidity stance.

Components are fixed (not per-country tuned) and the axis renormalises over
whatever is present, so a thin-macro economy (Taiwan) still produces an honest,
lower-confidence read instead of crashing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import score_from_z, slope_z
from engine.regime import apply_hysteresis, raw_quad
from lib import config

QUAD_NAMES = {"Q1": "Goldilocks", "Q2": "Reflation",
              "Q3": "Stagflation", "Q4": "Growth-scare"}

# component -> weight (uniform across countries)
_GROWTH = {"gdp_trend": 1.0, "unemployment_trend": 1.0, "index_trend": 1.0,
           "global_growth": 0.5}
# cpi_direction leads WHEN FRESH; oil + the long-yield trend are always-current
# proxies so the axis stays meaningful where keyless CPI is stale/discontinued.
_INFLATION = {"cpi_direction": 1.5, "oil_trend": 0.75, "yield_trend": 0.75}


def _scfg() -> dict:
    return config.load()["intl"]["engine"]["scoring"]


def _trend(f: pd.DataFrame, col: str, use_log: bool = True) -> pd.Series:
    sc = _scfg()
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
            "unemployment_trend": -1.0 * _monthly_sign(f, "unemployment", 63),
            "index_trend": _trend(f, "index"),
            "global_growth": _trend(f, "copper_gold"),
        })
    if axis == "inflation":
        return pd.DataFrame({
            "cpi_direction": _monthly_sign(f, "cpi_yoy", 63),
            "oil_trend": _trend(f, "oil"),
            "yield_trend": _trend(f, "yield_10y", use_log=False),  # rising long yields = reflation tilt
        })
    raise ValueError(axis)


def score_axis(f: pd.DataFrame, axis: str) -> pd.DataFrame:
    weights = pd.Series(_GROWTH if axis == "growth" else _INFLATION)
    min_comp = _scfg()["min_components"]
    scores = _component_scores(f, axis)
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

    out = pd.DataFrame({f"{axis}_score": axis_score, f"{axis}_confidence": confidence,
                        f"{axis}_agreement": agreement, f"{axis}_n_components": n_comp})
    for cc in scores.columns:
        out[f"c_{axis}_{cc}"] = scores[cc]
    return out


def liquidity_overlay(f: pd.DataFrame) -> pd.Series:
    """Central-bank stance proxy: direction of the policy rate over ~3 months
    (cuts = expanding, hikes = contracting); a steepening curve adds an easing tilt."""
    out = pd.Series("unknown", index=f.index)
    if "policy_rate" not in f or f["policy_rate"].isna().all():
        return out
    roc = f["policy_rate"].diff(63)
    out[:] = "neutral"
    out[roc < -0.10] = "expanding"
    out[roc > 0.10] = "contracting"
    if "curve" in f and not f["curve"].isna().all():
        out[(f["curve"].diff(20) > 0.05) & (out == "neutral")] = "expanding"
    out[roc.isna()] = "unknown"
    return out


def recession_composite(f: pd.DataFrame) -> pd.Series:
    """DISPLAY-ONLY 0-100 recession-pressure gauge. History-anchored: each leg is
    a bounded 0-1 stress with simple thresholds (yield-curve inversion, a Sahm-lite
    unemployment uptrend, equity drawdown), averaged over the legs present. NOT a
    backtested probability — a descriptive cross-country stress comparator."""
    cfg = config.load()["intl"]["engine"]["recession"]
    legs = pd.DataFrame(index=f.index)
    # 1) yield-curve inversion (10y-3m): 0 at +1.5pp, 1.0 at -1.0pp
    if "curve" in f and not f["curve"].isna().all():
        legs["curve"] = ((1.5 - f["curve"]) / 2.5).clip(0, 1)
    # 2) Sahm-lite: unemployment rise over ~6mo, 0 at <=0, 1.0 at +1.0pp
    if "unemployment" in f and not f["unemployment"].isna().all():
        legs["unemp"] = (f["unemployment"].diff(cfg["unemp_window_d"]) / 1.0).clip(0, 1)
    # 3) equity drawdown from 1y high: 0 at -0%, 1.0 at -25%
    if "drawdown" in f and not f["drawdown"].isna().all():
        legs["dd"] = (-f["drawdown"] / 25.0).clip(0, 1)
    if legs.empty:
        return pd.Series(np.nan, index=f.index)
    return (legs.mean(axis=1) * 100).round(1)


def recession_band(score: float | None) -> str:
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "n/a"
    cfg = config.load()["intl"]["engine"]["recession"]
    if score >= cfg["high_band"]:
        return "elevated"
    if score >= cfg["elevated_band"]:
        return "watch"
    return "low"


def classify(f: pd.DataFrame) -> pd.DataFrame:
    """Full daily regime table for one country's feature frame."""
    qcfg = config.load()["intl"]["engine"]["quad"]
    gx = score_axis(f, "growth")
    ix = score_axis(f, "inflation")
    out = pd.concat([gx, ix], axis=1)
    hyst = apply_hysteresis(out["growth_score"], out["inflation_score"],
                            qcfg["hysteresis_days"], qcfg["shock_override_z"])
    out = out.join(hyst)
    out["raw_quad"] = [raw_quad(g, i) for g, i in zip(out["growth_score"], out["inflation_score"])]
    out["quad_name"] = out["quad"].map(lambda q: QUAD_NAMES.get(q, q) if q else None)
    out["liquidity"] = liquidity_overlay(f)
    out["recession_score"] = recession_composite(f)
    out["regime_confidence"] = out[["growth_confidence", "inflation_confidence"]].mean(axis=1)
    return out
