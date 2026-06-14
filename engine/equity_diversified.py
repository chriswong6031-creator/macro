"""S&P / Macro Vector — Phase 4 (OPTIONAL, gated) diversified-sleeve experiments.

The Phase-1/2/3 engine switches a single index <-> T-bills; the literature is clear
that the only structures that historically BEAT buy & hold on CAGR (Faber GTAA, GEM)
get it from DIVERSIFICATION, not index timing. This module tests two such add-ons,
each judged on its OWN out-of-sample bar vs the Phase-3 strategy (NOT shipped unless
it clears it):

  1. DEFENSIVE sleeve = synthetic constant-maturity Treasury total return (carry minus
     duration x dyield) instead of bills — deeper history than any ETF, built from the
     DGS curve. MUST survive the 2022 stock-bond-correlation breakdown (bonds fell WITH
     stocks) — a duration sleeve that is silently long beta in a rates bear is rejected.
  2. RELATIVE-STRENGTH equity sleeve = hold the strongest of SPX/NDX/DJI/RUT by 12-1
     momentum (monthly) for the risk-on leg, instead of always SPY.

Kept SEPARATE from engine/equity_alloc.py (the shipped core) so the experimental,
default-off sleeve can't touch the validated path. See research/SP_VECTOR_VIABILITY.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import store

TY = 252


def treasury_tr(yield_pct: pd.Series, maturity_years: float = 7.0) -> pd.Series:
    """Synthetic constant-maturity Treasury daily TOTAL return from a CMT yield (%).
    daily TR ~= carry (prev yield/252) - modified_duration * dyield. Modified duration
    from the par-bond approximation MD = (1-(1+y)^-M)/y. An approximation (ignores roll
    + convexity) but captures the dominant carry + duration*dyield that the
    diversification test turns on. Deep history (DGS series back to 1962)."""
    y = (yield_pct / 100.0).clip(lower=1e-4)
    dy = y.diff()
    md = (1.0 - (1.0 + y) ** (-maturity_years)) / y
    carry = y.shift(1) / TY
    return (carry - md.shift(1) * dy).fillna(0.0)


def bill_returns(yield_pct: pd.Series, index: pd.Index) -> pd.Series:
    """Per-calendar-day T-bill return on `index` (matches equity_alloc cash-leg)."""
    days = pd.Series(index, index=index).diff().dt.days.fillna(0).clip(lower=0)
    return (yield_pct.reindex(index, method="ffill").fillna(0.0) / 100.0) * (days / 365.0)


def rs_equity_returns(tickers=("SPY", "QQQ", "_DJI", "_RUT"),
                      lookback: int = 252, skip: int = 21) -> pd.Series:
    """Daily return of a relative-strength equity sleeve: each month hold the index
    with the strongest 12-minus-1-month momentum (act next day). Falls back to SPY
    when momentum is undefined (early history / single name)."""
    closes = {}
    for t in tickers:
        d = store.read("yahoo", t)
        if d is not None and not d.empty:
            closes[t] = d["close"]
    df = pd.DataFrame(closes).sort_index()
    rets = df.pct_change(fill_method=None)
    mom = df.shift(skip) / df.shift(lookback) - 1.0
    monthly = mom.resample("ME").last()
    pick = monthly.apply(lambda r: r.idxmax() if r.notna().any() else np.nan, axis=1)
    held = pick.reindex(df.index, method="ffill").shift(1)
    held = held.where(held.notna(), "SPY")
    out = pd.Series(0.0, index=df.index)
    for t in df.columns:
        m = held == t
        out[m] = rets[t].where(m, 0.0)[m]
    return out.fillna(0.0)


def backtest_sleeves(equity_ret: pd.Series, defensive_ret: pd.Series,
                     alloc: pd.Series, cost_bps: float = 3.0) -> dict:
    """Two-sleeve portfolio: pos in the equity sleeve, (1-pos) in the defensive sleeve,
    next-bar, one-way turnover cost. Generalizes backtest_core's cash-leg (defensive_ret
    = bill carry there) to an arbitrary defensive asset (e.g. Treasury TR)."""
    idx = equity_ret.index
    pos = alloc.shift(1).reindex(idx).ffill().fillna(0.0).clip(0, 1)
    turn = pos.diff().abs().fillna(0.0)
    cost = (cost_bps / 1e4) * turn
    rd = defensive_ret.reindex(idx).fillna(0.0)
    net = pos * equity_ret.fillna(0.0) + (1.0 - pos) * rd - cost
    years = (idx[-1] - idx[0]).days / 365.25
    return {"net": net, "pos": pos, "turnover": turn, "years": years}


# --- summary stats (mirror equity_alloc.summarize, two-sleeve aware) ---
def stats(net: pd.Series, years: float, label: str = "") -> dict:
    eq = (1 + net).cumprod()
    cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else np.nan
    sd = net.std()
    sharpe = float(net.mean() / sd * np.sqrt(TY)) if sd else np.nan
    dn = net[net < 0].std()
    sortino = float(net.mean() / dn * np.sqrt(TY)) if dn else np.nan
    mdd = float((eq / eq.cummax() - 1).min())
    return {"label": label, "cagr": round(100 * cagr, 2), "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2), "maxdd": round(100 * mdd, 1)}
