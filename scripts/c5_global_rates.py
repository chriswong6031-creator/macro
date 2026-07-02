"""C5 builder — the global cost-of-capital de-risk leg, graded vs the US book (W3).

The causal signal the ``scripts/intl_phase0`` harness grades for claim
``c5_global_rates``. It reads the reconstructed GDP-weighted global 10y level +
US-vs-world premium HISTORY from the ``engine.global_rates`` leaf (which mirrors
the ``intl_bonds`` aggregation, since those numbers dead-end in bond_health.json
with no history on disk — INTL-15), turns the RISE of global rates into a de-risk
gate, and returns the harness builder contract so decide() folds it through the
full battery: DSR, orthogonality vs the 5 US MRS legs, crisis-count effective-N,
crisis-independent ES.

THE DECIDING GATE (masterplan §5 C5): orthogonality vs the existing US curve/credit
MRS legs. The global 10y is plausibly ~US 10y + noise — the US 10y IS one of its
seven roster legs (weight 0.42) — so a truthful CONTEXT is the expected, welcome
outcome. Measured, not assumed.

Mechanism (de-risk): a rising global 10y / widening US premium is a global duration
+ growth-beta headwind. Signal = causal trailing percentile of the 63d global-10y
momentum (bp) — high percentile (rates rising fast) = de-risk. Strategy: hold the
US book, go flat when the de-risk percentile is in its top band. Everything is
causal: the aggregate is publication-lag-carried (engine.global_rates), the pctile
window is trailing-only, and the position acts next-bar (backtest_core.shift(1)).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import global_rates
from engine.indicators import pct_rank_window
from lib import store

log = logging.getLogger(__name__)

_MOM_N = 63          # 63-bday (~3m) global-10y momentum, in bp
_PCT_WIN = 504       # ~2y causal trailing percentile (matches risk_radar_intl / C3)
_RISK_THR = 0.70     # top-30% de-risk band (long/flat threshold), aligned with C3


def _us_book_px() -> pd.Series | None:
    """US book price (SPY target) for the C5 grade. _GSPC is the deepest US index on disk."""
    df = store.read("yahoo", "_GSPC")
    if df is None or df.empty or "close" not in df.columns:
        return None
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def _fwd_maxdd(px: pd.Series, h: int) -> pd.Series:
    """Forward max-drawdown over [t, t+h] (<=0). Causal label — looks FORWARD, so it is
    a target, never fed into the signal."""
    vals = px.to_numpy()
    out = np.full(len(px), np.nan)
    for i in range(len(px)):
        w = vals[i:i + h + 1]
        if len(w) < 3:
            continue
        peak = np.maximum.accumulate(w)
        out[i] = float((w / peak - 1.0).min())
    return pd.Series(out, index=px.index)


def build(claim: dict, horizon: int = 42) -> dict:
    """The harness builder contract for c5_global_rates at ONE horizon.

    Signal graded for orthogonality: the causal trailing-percentile of the 63d
    global-10y RISE momentum (high = rates rising fast = de-risk danger). Strategy:
    US book long/flat, flat when the percentile is in its top band (causal, next-bar).
    Basis: the 5 US MRS legs — the orthogonality decider (see module docstring).
    """
    px = _us_book_px()
    if px is None:
        return {"error": "US book (_GSPC) unavailable"}
    idx = px.index
    gr = global_rates.series(idx)
    if not gr:
        return {"error": "global_rates roster unavailable"}
    avg = gr["avg_10y"]
    prem = gr["us_premium_bp"]

    # de-risk driver: 63d RISE of the global 10y (bp) + the premium widening — both are
    # duration/growth headwinds. Combine as a simple sum of their causal percentiles so
    # neither prong is post-hoc weighted (equal-weight, pre-registered).
    mom = ((avg - avg.shift(_MOM_N)) * 100.0).reindex(idx)
    prem_mom = (prem - prem.shift(_MOM_N)).reindex(idx)
    mom_v = mom.dropna()
    prem_v = prem_mom.dropna()
    if len(mom_v) < _PCT_WIN:
        return {"error": "insufficient global-10y history for the pctile window"}
    p_mom = pct_rank_window(mom_v, _PCT_WIN).reindex(idx)
    p_prem = (pct_rank_window(prem_v, _PCT_WIN).reindex(idx)
              if len(prem_v) >= _PCT_WIN else pd.Series(index=idx, dtype=float))
    # equal-weight the two prongs where both are present; fall back to the rate-rise
    # prong alone where the premium pctile hasn't warmed up (never invents a value).
    sig = pd.concat([p_mom, p_prem], axis=1).mean(axis=1).reindex(idx)
    sig = sig.dropna()
    if len(sig) < 200:
        return {"error": "insufficient warmed-up signal"}

    from engine.validation import backtest_core, _sharpe
    pos = (1.0 - (sig > _RISK_THR).astype(float)).shift(1).fillna(1.0).reindex(idx).fillna(1.0)
    strat = backtest_core(px, pos, cost_bps=3.0, cash_yield=None)["net"].reindex(idx)
    bench = px.pct_change().reindex(idx)

    target_dd = _fwd_maxdd(px, horizon).reindex(sig.index)

    # orthogonality basis = the 5 US MRS legs (the C5 decider). Reuse the C2 helper so
    # the basis is built exactly as the live engine does (causal conditions_frame).
    from scripts.intl_phase0 import _us_mrs_basis
    basis = _us_mrs_basis(sig.index)

    # split-half same-sign Sharpe of the de-risk strategy
    r = strat.dropna()
    n = len(r)
    s1 = _sharpe(r.iloc[:n // 2].to_numpy(), 252) if n >= 240 else float("nan")
    s2 = _sharpe(r.iloc[n // 2:].to_numpy(), 252) if n >= 240 else float("nan")
    split_same = bool(np.isfinite(s1) and np.isfinite(s2) and np.sign(s1) == np.sign(s2))

    # IC: Spearman of the de-risk signal vs forward DD (correct de-risk sign = negative,
    # i.e. a higher danger percentile predicts a deeper — more negative — forward DD).
    def _sp(a, b):
        j = pd.concat([pd.Series(a).rename("a"), pd.Series(b).rename("b")], axis=1).dropna()
        return float(j["a"].rank().corr(j["b"].rank())) if len(j) >= 30 else None

    return {
        "signal": sig, "strat_ret": strat, "bench_ret": bench, "target_dd": target_dd,
        "basis": basis, "split_half_same_sign": split_same,
        "ic": _sp(sig, target_dd),
    }


def builder(claim: dict) -> dict:
    """Harness entry point: grade c5_global_rates at its first pre-registered DD horizon
    (42d — the drawdown-relevant window). Both (21,42) are declared in the trial budget;
    this builder reports the 42d cut, the same convention the C1/C2/C3 builders use."""
    return build(claim, horizon=42)
