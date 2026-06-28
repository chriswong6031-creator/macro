"""Net-exposure timing overlay (engine v2) — the validated TIME-SERIES risk dial.

How much LONG the book runs, kept DISTINCT from `engine.dispersion` (which sizes the
cross-sectional SELECTION gross): a book uses both — dispersion decides how much
stock-picking gross to take, this decides net market exposure. It is a DRAWDOWN lever,
not a return edge: `scripts/validate_timing_overlay.py` (S&P 500, 1927-2026, net of cost)
showed it lifts Sharpe 0.42→0.58 and cuts max drawdown -86%→-52% with ZERO selection
alpha — the same risk-not-return character as `engine.risk_sizing`.

Legs (only the two the validation found NON-redundant; a Zweig breadth-thrust leg and a
breadth-participation leg were tested and dropped — breadth is redundant with trend):
  * trend   — S&P 500 above its 200-day MA (the deep, robust de-risk-in-downtrends leg)
  * net-liq — Fed net liquidity expanding (net_liquidity_bn 63d-RoC > 0); 2014+ only, and
              the validation's one INCREMENTAL leg (Sharpe 0.821→0.856 in 2014-block).

exposure = mean of the legs KNOWABLE today (so the net-liq leg simply joins when present),
clipped to [0, 1]. Discrete 0/1 legs + fixed thresholds (a fitted continuous curve is the
classic market-timing overfit trap). Point-in-time; the caller lags it before trading.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_STATE = {"risk_on": ("Risk-on — full exposure", "风险偏好 — 满仓敞口"),
          "neutral": ("Mixed — partial exposure", "中性 — 部分敞口"),
          "risk_off": ("Risk-off — de-gross to cash", "风险规避 — 降敞口至现金")}


def _trend_leg(spx_close: pd.Series) -> float | None:
    c = spx_close.dropna()
    if len(c) < 200:
        return None
    return 1.0 if float(c.iloc[-1]) > float(c.tail(200).mean()) else 0.0


def _netliq_leg(net_liquidity_bn: pd.Series | None, roc_window: int = 63) -> float | None:
    if net_liquidity_bn is None:
        return None
    nl = pd.Series(net_liquidity_bn).dropna()
    if len(nl) < roc_window + 1:
        return None
    return 1.0 if float(nl.iloc[-1]) > float(nl.iloc[-roc_window - 1]) else 0.0


def assess(spx_close: pd.Series, net_liquidity_bn: pd.Series | None = None) -> dict | None:
    """Latest net-exposure read. `spx_close` = the S&P 500 close series; `net_liquidity_bn`
    = the Fed net-liquidity series (optional — the leg joins when supplied). Returns the
    exposure scalar in [0,1], a 3-state label, and the per-leg breakdown, or None when even
    the trend leg can't be computed."""
    legs = {"trend": _trend_leg(spx_close), "netliq": _netliq_leg(net_liquidity_bn)}
    present = {k: v for k, v in legs.items() if v is not None}
    if "trend" not in present:                       # trend is the load-bearing deep leg
        return None
    exposure = float(np.clip(np.mean(list(present.values())), 0.0, 1.0))
    state = "risk_on" if exposure >= 0.99 else "risk_off" if exposure <= 0.01 else "neutral"
    en, zh = _STATE[state]
    return {"exposure": round(exposure, 2), "state": state, "label": en, "label_zh": zh,
            "legs": present, "n_legs": len(present)}
