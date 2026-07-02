"""Per-name global-risk beta — the honest per-name China A-share read (C1).

Direct port of engine/hk_global_beta.py to the A-share book. China A couples to
global risk LESS than HK does — global factors drive HK ~2x what they drive the
Mainland (research/CHINA_GLOBAL_FACTORS.md, memory `china-global-factors`). So the
A-share transmission is expected WEAKER than HK's already-modest edge; this module
measures it honestly rather than assuming the HK magnitude.

    global_beta_i = causal rolling beta of A-share i's return to the global-risk
    return factor (S&P 500, lagged one day for the overnight US->Asia transmission,
    EXACTLY the HK convention), 252d window, Vasicek-shrunk toward the cross-section.

High beta = amplifier (bigger drawdown when the global risk state deteriorates);
low beta = cushion / domestic-defensive. The C1 use is DE-RISK-DIRECTION ONLY: when
the global risk state is off AND a name's beta is in the top tercile, its conviction
is dampened (never an add-tilt) — mirroring how hk_global_beta feeds the HK sizing
ctx, but bounded and gated by the intl_bridge ledger weight.

Measured (see the C1 Status-log line in research/INTL_FIX_MASTERPLAN.md): the
A-share high-minus-low global-beta forward-drawdown spread is WEAKER than HK's — a
CONTEXT-tier descriptive exposure, not a return forecast or a buy list. Beta is a
descriptive risk exposure, never alpha.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

NOTE = ("Each A-share name's beta to global risk (S&P 500, overnight) — how much it "
        "amplifies the global risk-on/off regime. Risk context for sizing, not a buy "
        "list. China A couples to global risk less than HK.")


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


def _role(pct: pd.Series) -> pd.Series:
    return np.where(pct >= 66, "amplifier", np.where(pct <= 34, "cushion", "neutral"))


def _f(x, nd: int = 2):
    return round(float(x), nd) if x is not None and np.isfinite(x) else None


def compute_global_betas(closes: pd.DataFrame, factor_ret: pd.Series,
                         risk_state: str | None = None,
                         tkr_name: dict | None = None, tkr_sector: dict | None = None,
                         *, win: int = 252, shrink: float = 0.66, asof=None,
                         top_n: int = 12, min_names: int = 12) -> dict | None:
    """Cross-section of per-name global-risk betas + roles + (optional) risk tilt.

    `factor_ret` is the global-risk return factor ALREADY aligned (e.g. SPY returns
    lagged one day). Best-effort: returns None on missing/short data, never raises.

    The returned ``per_ticker`` map carries each name's shrunk beta, its cross-
    sectional beta percentile, and its role (amplifier / neutral / cushion). The
    dampener consumer reads ``per_ticker[t]['role'] == 'amplifier'`` (top tercile).
    """
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
        log.warning("cn_global_beta: factor series too short")
        return None

    beta = _causal_beta(R, m, win, minp)          # date × ticker, causal
    last = _shrink(beta.iloc[-1].dropna(), shrink)
    if len(last) < min_names:
        log.warning("cn_global_beta: too few names (%d)", len(last))
        return None

    pct = last.rank(pct=True) * 100.0
    d = pd.DataFrame({"beta": last, "beta_pct": pct})
    d["role"] = _role(d["beta_pct"])

    def rec(t: str) -> dict:
        r = d.loc[t]
        return {"ticker": t, "name": tkr_name.get(t, t), "sector": tkr_sector.get(t, "—"),
                "beta": _f(r["beta"]), "beta_pct": _f(r["beta_pct"], 0),
                "role": str(r["role"])}

    order = d.sort_values("beta", ascending=False)
    per_ticker = {t: {"beta": _f(d.at[t, "beta"]), "beta_pct": _f(d.at[t, "beta_pct"], 0),
                      "role": str(d.at[t, "role"])}
                  for t in d.index}
    return {"as_of": str(R.index.max().date()), "n": int(len(d)), "note": NOTE,
            "risk_state": risk_state, "factor": "S&P 500 (overnight)",
            "win": win, "shrink": shrink,
            "amplifiers": [rec(t) for t in order.head(top_n).index],
            "cushions": [rec(t) for t in order.tail(top_n).index][::-1],
            "per_ticker": per_ticker}
