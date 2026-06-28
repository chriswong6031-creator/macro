"""Canada conditions — a display-only RORO + slowdown + drawdown-fragility bundle for
the TSX, assembled in the SAME shape as engine/china_conditions.py & hk_conditions.py
(conditions.roro{roro_state, roro, legs, ca_roro_vix}, conditions.recession{score,label},
conditions.drawdown_risk{score,band}) so engine/market_state_ca.py can reuse the same
reader pattern as China/HK.

Unlike China/HK, Canada had no conditions layer, so this BUILDS one from pieces that
already exist:
  - RORO        : engine/canada_overlay.py's cross-asset commodity/CAD/BoC gauge (already a
                  risk-on/off state + per-factor z-legs incl. a VIX leg used for the vol read)
  - recession   : a light slowdown gauge from the macro frame (GDP trend, the unemployment
                  rate of change, the GoC 2s10s curve inversion)
  - drawdown    : a stress-fragility percentile from TSX drawdown depth + breadth weakness +
                  curve inversion

DISPLAY-ONLY and uncalibrated (no forward-return edge claimed); the Market State board
carries an honest caveat. Pure functions, never raise — any shortfall degrades the leg to
None and the gauge renormalises over what remains.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_Z_WIN = 252

_OV_LEG = {  # canada_overlay factor key -> bilingual label for the RORO leg list
    "oil": ("WTI crude", "WTI 原油"),
    "gold": ("Gold", "黄金"),
    "copper_gold": ("Copper / Gold", "铜／金 比"),
    "usdcad": ("USD/CAD", "美元／加元"),
    "spy": ("S&P 500", "标普500"),
    "vix": ("Volatility (VIX)", "波动率（VIX）"),
    "dxy": ("US Dollar (DXY)", "美元指数"),
}


def _clamp(x, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return None


def _last(f, col):
    if col not in getattr(f, "columns", []):
        return None
    s = f[col].dropna()
    return float(s.iloc[-1]) if len(s) else None


def _roro_from_overlay(overlay: dict) -> dict:
    state = {"Risk-on": "risk-on", "Risk-off": "risk-off", "Neutral": "neutral"}.get(
        (overlay or {}).get("state"))
    legs, vix_z = [], None
    for fac in (overlay or {}).get("factors") or []:
        k = fac.get("key")
        en, zh = _OV_LEG.get(k, (fac.get("label", k), fac.get("label", k)))
        lean = {"on": "risk-on", "off": "risk-off", "neutral": "neutral"}.get(fac.get("risk"), "neutral")
        legs.append({"key": k, "name_en": en, "name_zh": zh,
                     "value": fac.get("z"), "lean": lean})
        if k == "vix":
            z = fac.get("z")
            vix_z = -float(z) if z is not None else None      # negate: + = calm (low VIX)
    return {"roro_state": state, "roro": (overlay or {}).get("score"),
            "legs": legs, "ca_roro_vix": vix_z}


def _recession(f: pd.DataFrame) -> dict:
    """A light 0-100 slowdown gauge: GDP trend, the rise in the unemployment rate, and the
    GoC 2s10s inversion. Higher = more slowdown."""
    legs, parts = [], []

    def leg(key, en, zh, weight, v01, raw=None):
        ok = v01 is not None and np.isfinite(v01)
        legs.append({"key": key, "label": en, "label_zh": zh, "weight": weight,
                     "active": bool(ok), "value": round(v01 * 100, 1) if ok else None})
        if ok:
            parts.append((v01, weight))

    gdp = _last(f, "gdp_yoy")
    leg("gdp", "GDP trend", "GDP 趋势", 1.2,
        _clamp((2.0 - gdp) / 4.0) if gdp is not None else None)        # <2% slowing, <-2% recession

    unemp_chg = None
    if "unemployment" in getattr(f, "columns", []):
        u = f["unemployment"].dropna()
        if len(u) > 253:
            unemp_chg = float(u.iloc[-1] - u.iloc[-253])
    leg("unemp", "Unemployment ↑ (12m)", "失业率 ↑（12月）", 1.0,
        _clamp(unemp_chg / 1.5) if unemp_chg is not None else None)    # +1.5pp y/y = max

    curve = _last(f, "curve_2s10s")
    leg("curve", "Yield-curve inversion", "收益率曲线倒挂", 1.0,
        _clamp(-curve / 0.8) if curve is not None else None)          # inverted (negative) = recession

    if not parts:
        return {"score": None, "label": None, "legs": legs, "calibrated": False}
    score = 100.0 * sum(v * w for v, w in parts) / sum(w for _, w in parts)
    label = "high" if score >= 55 else "elevated" if score >= 35 else "low"
    return {"score": round(score, 1), "label": label, "legs": legs, "calibrated": False}


def _drawdown(f: pd.DataFrame) -> dict:
    """A 0-100 stress-fragility percentile: TSX drawdown depth + breadth weakness + curve
    inversion, z-meaned over history then expanding-rank-percentiled. Uncalibrated."""
    cols = getattr(f, "columns", [])
    legs = []
    idx_col = "market_index" if "market_index" in cols else ("^GSPTSE" if "^GSPTSE" in cols else None)
    if idx_col is not None:
        px = f[idx_col].astype(float)
        dd = (px / px.cummax() - 1.0)                                 # ≤ 0 ; deeper = more stress
        legs.append((-dd).rename("dd"))                              # negate so higher = stress
    if "pct_above_200" in cols:
        legs.append((-f["pct_above_200"].astype(float)).rename("breadth"))   # low breadth = stress
    elif "pct_above_50" in cols:
        legs.append((-f["pct_above_50"].astype(float)).rename("breadth"))
    if "curve_2s10s" in cols:
        legs.append((-f["curve_2s10s"].astype(float)).rename("curve"))       # inversion = stress
    if not legs:
        return {"score": None, "band": None, "calibrated": False}

    def _z(s):
        s = s.dropna()
        m = s.rolling(_Z_WIN, min_periods=60).mean()
        sd = s.rolling(_Z_WIN, min_periods=60).std()
        return ((s - m) / sd).replace([np.inf, -np.inf], np.nan)

    zmean = pd.concat([_z(s) for s in legs], axis=1).mean(axis=1).dropna()
    if zmean.empty:
        return {"score": None, "band": None, "calibrated": False}
    rank = zmean.expanding(min_periods=60).apply(lambda w: (w <= w.iloc[-1]).mean(), raw=False)
    score = float(rank.iloc[-1] * 100)
    band = ("extreme" if score >= 90 else "high" if score >= 75
            else "elevated" if score >= 50 else "low")
    return {"score": round(score, 1), "band": band, "calibrated": False}


def snapshot(f: pd.DataFrame, overlay: dict | None = None) -> dict:
    """The display-only conditions bundle for latest['conditions'] — RORO (from the
    cross-asset overlay) + slowdown + drawdown-fragility gauges. Never scored into the
    regime / axes / playbook."""
    return {
        "roro": _roro_from_overlay(overlay or {}),
        "recession": _recession(f),
        "drawdown_risk": _drawdown(f),
        "display_only": True,
        "note": ("display-only conditioning lens — cross-asset RORO + uncalibrated "
                 "slowdown/drawdown gauges; never feeds the Canada regime."),
    }
