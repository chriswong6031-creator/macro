"""Per-stock global-risk beta — the honest per-name Hong Kong read.

HK lacks idiosyncratic stock-selection alpha: residual momentum is DEAD here (its
long-short Sharpe is negative on a 40-year panel — research/CHINA_HK_STOCK_SIGNALS.md,
reports/hk-residual-alpha-phase0.md). HK's validated edge is the GLOBAL-RISK OVERLAY
(engine/hk_global.py — HK is ~2x global-beta, the transmission of US risk into China).
So the right per-stock signal is NOT selection alpha but RISK EXPOSURE: how much each
name AMPLIFIES the global risk-on/off regime.

    global_beta_i = causal rolling beta of stock i's return to the global-risk return
    factor (S&P 500, lagged one day for the overnight US->HK transmission), 252d,
    Vasicek-shrunk toward the cross-section.

High beta = amplifier (bigger up in Risk-on, bigger drawdown in Risk-off); low beta =
cushion / domestic-defensive. Conditioned on the current `risk_state` (from
hk_global) into an actionable tilt: in Risk-on amplifiers are the leveraged play and
cushions lag; in Risk-off amplifiers are the most exposed and cushions defend.

Measured (deep 73-name panel, lagged SPY, monthly): high-minus-low global-beta
forward-21d return is +0.41% in Risk-on (t 0.7) and -0.74% in Risk-off (t -1.3) —
directionally correct, MODEST, the risk-off signal the cleaner one. This is risk
CONTEXT (position sizing within the validated regime), NOT a return forecast or a
buy list. Beta is a descriptive exposure, not an alpha.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

NOTE = ("Each HK name's beta to global risk (S&P 500, overnight) — how much it "
        "amplifies the risk-on/off regime. Risk context for sizing, not a buy list.")


def _causal_beta(y: pd.DataFrame, x: pd.Series, win: int, minp: int) -> pd.DataFrame:
    """Rolling cov(y,x)/var(x), lagged one day (prior-window data only)."""
    return (y.rolling(win, min_periods=minp).cov(x)
            .div(x.rolling(win, min_periods=minp).var(), axis=0)).shift(1)


def _shrink(beta: pd.Series, w: float) -> pd.Series:
    """Vasicek-lite: pull each noisy beta toward the cross-sectional mean (w*raw +
    (1-w)*prior). Keeps a handful of badly-estimated betas from distorting the ranks."""
    if w is None or w >= 1.0:
        return beta
    return beta.mul(w).add(beta.mean() * (1.0 - w))


def _tilt(role: str, risk_state: str) -> str:
    """Regime-conditioned read: what the current risk_state implies for this role."""
    if risk_state == "Risk-on":
        return {"amplifier": "favored", "cushion": "lag"}.get(role, "neutral")
    if risk_state == "Risk-off":
        return {"amplifier": "exposed", "cushion": "favored"}.get(role, "neutral")
    return "neutral"


def _f(x, nd: int = 2):
    return round(float(x), nd) if x is not None and np.isfinite(x) else None


def compute_global_betas(closes: pd.DataFrame, factor_ret: pd.Series, risk_state: str,
                         tkr_name: dict | None = None, tkr_sector: dict | None = None,
                         *, win: int = 252, shrink: float = 0.66, asof=None,
                         top_n: int = 12, min_names: int = 12) -> dict | None:
    """Cross-section of per-stock global-risk betas + the regime-conditioned tilt.
    `factor_ret` is the global-risk return factor ALREADY aligned (e.g. SPY returns
    lagged one day). Best-effort: returns None on missing/short data, never raises."""
    if closes is None or closes.empty:
        return None
    tkr_name = tkr_name or {}
    tkr_sector = tkr_sector or {}
    minp = max(win // 2, 60)
    R = closes.pct_change(fill_method=None)
    if asof is not None:
        R = R.loc[:pd.Timestamp(asof)]
    m = factor_ret.reindex(R.index)
    if m.notna().sum() < minp:
        log.warning("hk_global_beta: factor series too short")
        return None

    beta = _causal_beta(R, m, win, minp)          # date × ticker, causal
    last = _shrink(beta.iloc[-1].dropna(), shrink)
    if len(last) < min_names:
        log.warning("hk_global_beta: too few names (%d)", len(last))
        return None

    pct = last.rank(pct=True) * 100.0
    d = pd.DataFrame({"beta": last, "beta_pct": pct})
    d["role"] = np.where(d["beta_pct"] >= 66, "amplifier",
                         np.where(d["beta_pct"] <= 34, "cushion", "neutral"))

    def rec(t: str) -> dict:
        r = d.loc[t]
        role = str(r["role"])
        return {"ticker": t, "name": tkr_name.get(t, t), "sector": tkr_sector.get(t, "—"),
                "beta": _f(r["beta"]), "beta_pct": _f(r["beta_pct"], 0),
                "role": role, "tilt": _tilt(role, risk_state)}

    order = d.sort_values("beta", ascending=False)
    per_ticker = {t: {"beta": _f(d.at[t, "beta"]), "beta_pct": _f(d.at[t, "beta_pct"], 0),
                      "role": str(d.at[t, "role"]),
                      "tilt": _tilt(str(d.at[t, "role"]), risk_state)}
                  for t in d.index}
    return {"as_of": str(R.index.max().date()), "n": int(len(d)), "note": NOTE,
            "risk_state": risk_state, "factor": "S&P 500 (overnight)",
            "win": win, "shrink": shrink,
            "amplifiers": [rec(t) for t in order.head(top_n).index],
            "cushions": [rec(t) for t in order.tail(top_n).index][::-1],
            "per_ticker": per_ticker}
