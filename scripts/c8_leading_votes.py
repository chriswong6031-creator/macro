"""C8 builder — cross-asset leading-votes → fractional MRS booster, graded vs the US book (W3).

The causal signal the ``scripts/intl_phase0`` harness grades for claim
``c8_crossasset_leading_votes``. The live ``engine.cross_asset_confirm`` computes
``to_brain.leading_caution_votes`` (0..3) + a verdict, but only as a same-day
snapshot (INTL-46) — no vote HISTORY exists on disk. This builder RECONSTRUCTS the
three votes causally from their ACTUAL on-disk input series, exactly matching the
live definitions in cross_asset_confirm._risk_leg, using only same-day-available
data (no look-ahead):

  * credit  vote — HY OAS band in {elevated, distress, crisis} OR 20d-widening
                   (config knots engine.bonds.credit; matches bonds._hy_band).
  * rates-vol vote — MOVE band in {elevated, crisis} OR MOVE leads VIX (move_z > vix_z)
                   (config knots engine.bonds.rates_vol; matches bonds._move_band).
  * dollar  vote — a risk-off dollar bid: 21d broad-dollar momentum z-score > 1
                   (the same-day-available proxy for the forex risk-off / dollar-smile
                   haven-bid leg; the live fx vote reads forex/latest.json which has
                   no committed history).

The C8 CLAIM: leading_caution_votes >= 2 while verdict == 'diverge' (fast-family
caution the equity gauges don't yet show) → does the booster predict SPY forward
DRAWDOWN, ORTHOGONALLY to the 5 US MRS legs? The credit/curve votes may be near-
duplicates of the nfci/recession legs — that is the decider. The booster's de-risk
strategy holds the US book and goes flat while the booster fires (causal, next-bar).

Returns the harness builder contract so decide() folds it through DSR, orthogonality,
crisis-count, crisis-independent ES. Wire only on CONFIRMED/DIRECTIONAL, else graveyard.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# equities "calm" (verdict='diverge' precondition) = SPY within this drawdown of its
# trailing peak. cross_asset_confirm's 'diverge' fires when a medium/high fast-family
# caution flag is present while the equity gauges are still benign; a shallow equity
# drawdown from the peak is the same-day-available proxy for that benign equity read.
_EQ_CALM_DD = -0.05
_HY_WIDEN_N = 20        # OAS change window (config engine.bonds.credit.widening_window_d)
_Z_WIN = 252            # move/vix/dollar z-score window (matches bonds.rates_vol.z_window_d)
_DXY_MOM_N = 21         # ~1m broad-dollar momentum for the risk-off dollar bid
_DXY_Z_THR = 1.0        # dollar-surge z threshold (haven-bid flavor)


def _s(group: str, name: str, close: bool = False) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty:
        return None
    col = "close" if (close and "close" in df.columns) else df.columns[0]
    s = df[col].astype(float).dropna()
    if s.empty:
        return None
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _carry(s: pd.Series | None, idx: pd.DatetimeIndex, limit: int = 5) -> pd.Series:
    if s is None:
        return pd.Series(index=idx, dtype=float)
    return s.reindex(idx.union(s.index)).ffill(limit=limit).reindex(idx)


def _z(s: pd.Series, win: int = _Z_WIN) -> pd.Series:
    return (s - s.rolling(win, min_periods=60).mean()) / s.rolling(win, min_periods=60).std()


def votes(idx: pd.DatetimeIndex) -> pd.Series:
    """The reconstructed daily leading-caution vote count (0..3), causal — matches
    the live cross_asset_confirm._risk_leg definition from the on-disk input series."""
    bcfg = (config.load().get("engine", {}) or {}).get("bonds", {}) or {}
    cred = bcfg.get("credit", {}) or {}
    rv = bcfg.get("rates_vol", {}) or {}
    hy_elev = float(cred.get("hy_elevated", 5.0))
    move_elev = float(rv.get("move_elevated", 120))
    move_crisis = float(rv.get("move_crisis", 150))

    # credit vote — HY OAS band >= elevated OR widening
    hy = _carry(_s("fred", "BAMLH0A0HYM2"), idx)
    credit_vote = (hy >= hy_elev) | ((hy - hy.shift(_HY_WIDEN_N)) > 0)

    # rates-vol vote — MOVE band >= elevated OR MOVE leads VIX
    move = _carry(_s("yahoo", "_MOVE", close=True), idx)
    vix = _s("yahoo", "_VIX", close=True)
    if vix is None:
        vix = _s("fred", "VIXCLS")
    vix = _carry(vix, idx)
    move_leads = (_z(move) > _z(vix)).fillna(False)
    vol_vote = (move >= move_elev) | move_leads

    # dollar vote — risk-off dollar bid (broad-dollar 21d momentum z > 1)
    dxy = _carry(_s("fred", "DTWEXBGS"), idx)
    fx_vote = (_z(dxy.pct_change(_DXY_MOM_N)) > _DXY_Z_THR).fillna(False)

    v = (credit_vote.astype(float).fillna(0.0)
         + vol_vote.astype(float).fillna(0.0)
         + fx_vote.astype(float).fillna(0.0))
    return v.reindex(idx)


def _us_book_px() -> pd.Series | None:
    return _s("yahoo", "_GSPC", close=True)


def _fwd_maxdd(px: pd.Series, h: int) -> pd.Series:
    vals = px.to_numpy()
    out = np.full(len(px), np.nan)
    for i in range(len(px)):
        w = vals[i:i + h + 1]
        if len(w) < 3:
            continue
        peak = np.maximum.accumulate(w)
        out[i] = float((w / peak - 1.0).min())
    return pd.Series(out, index=px.index)


def diverge_fire(idx: pd.DatetimeIndex, px: pd.Series) -> pd.Series:
    """The C8 booster condition: votes >= 2 while the equity read is still benign
    (the 'diverge' precondition), reconstructed causally. Boolean series."""
    v = votes(idx)
    eq_dd = (px / px.cummax() - 1.0).reindex(idx)
    eq_calm = eq_dd > _EQ_CALM_DD
    return ((v >= 2) & eq_calm).fillna(False)


def build(claim: dict, horizon: int = 42) -> dict:
    """The harness builder contract for c8_crossasset_leading_votes at ONE horizon.

    Signal graded for orthogonality: the continuous vote count (higher = more fast-
    family caution). Strategy: US book long/flat, flat while the booster fires
    (votes>=2 + equities calm), causal next-bar. Basis: the 5 US MRS legs — the
    orthogonality decider (are the credit/curve votes near-duplicates of nfci/recession?).
    """
    px = _us_book_px()
    if px is None:
        return {"error": "US book (_GSPC) unavailable"}
    idx = px.index
    v = votes(idx)
    if v.dropna().empty:
        return {"error": "vote inputs unavailable"}
    fire = diverge_fire(idx, px)

    from engine.validation import backtest_core, _sharpe
    pos = (1.0 - fire.astype(float)).shift(1).fillna(1.0).reindex(idx).fillna(1.0)
    strat = backtest_core(px, pos, cost_bps=3.0, cash_yield=None)["net"].reindex(idx)
    bench = px.pct_change().reindex(idx)

    target_dd = _fwd_maxdd(px, horizon).reindex(idx)

    from scripts.intl_phase0 import _us_mrs_basis
    basis = _us_mrs_basis(idx)

    r = strat.dropna()
    n = len(r)
    s1 = _sharpe(r.iloc[:n // 2].to_numpy(), 252) if n >= 240 else float("nan")
    s2 = _sharpe(r.iloc[n // 2:].to_numpy(), 252) if n >= 240 else float("nan")
    split_same = bool(np.isfinite(s1) and np.isfinite(s2) and np.sign(s1) == np.sign(s2))

    def _sp(a, b):
        j = pd.concat([pd.Series(a).rename("a"), pd.Series(b).rename("b")], axis=1).dropna()
        return float(j["a"].rank().corr(j["b"].rank())) if len(j) >= 30 else None

    # grade the continuous votes (the leg's information); the strategy uses the fire event.
    return {
        "signal": v, "strat_ret": strat, "bench_ret": bench, "target_dd": target_dd,
        "basis": basis, "split_half_same_sign": split_same, "ic": _sp(v, target_dd),
    }


def builder(claim: dict) -> dict:
    """Harness entry point: grade c8 at its first pre-registered DD horizon (42d). Both
    (21,42) are declared in the trial budget; this builder reports the 42d cut."""
    return build(claim, horizon=42)
