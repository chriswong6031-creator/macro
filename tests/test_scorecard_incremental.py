"""Incremental-IC wiring in the production factor scorecard (scripts/factor_ic_scorecard).

The scorecard now reports, per factor, the RAW rank-IC AND the IC after neutralizing
the cross-section against the style we already own (beta / size / 12-1 momentum /
low-vol). These tests pin the two new pieces with no network:
  * _style_basis builds the right loadings (beta<-low_beta, low_vol, size<-log mktcap,
    momentum<-prices) on the table universe;
  * the residualize→re-correlate composition the loop uses collapses a signal that is
    a pure replica of style toward ~0 IC, and preserves a signal orthogonal to style;
  * a factor's own style analog is excluded from its basis (_FACTOR_BASIS_SELF).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.validation import cross_sectional_resid, rank_ic
from scripts.factor_ic_scorecard import _FACTOR_BASIS_SELF, _style_basis


def _table(tickers):
    rng = np.random.default_rng(3)
    n = len(tickers)
    return pd.DataFrame({
        "low_beta": rng.normal(size=n),
        "low_vol": rng.normal(size=n),
        "mktcap_bn": rng.uniform(1, 500, size=n),
    }, index=tickers)


def _closes(tickers, days=300):
    idx = pd.bdate_range("2023-01-01", periods=days)
    rng = np.random.default_rng(4)
    return pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0, 0.01, days)) for t in tickers}, index=idx)


def test_style_basis_columns_and_universe():
    tk = [f"T{i}" for i in range(40)]
    t, closes = _table(tk), _closes(tk)
    b = _style_basis(t, closes, closes.index[-1])
    assert set(b.columns) == {"beta", "low_vol", "size", "mom"}
    assert list(b.index) == tk
    # size is log market cap -> finite, monotone in mktcap
    assert np.isfinite(b["size"]).all()
    big, small = t["mktcap_bn"].idxmax(), t["mktcap_bn"].idxmin()
    assert b.loc[big, "size"] > b.loc[small, "size"]


def test_style_basis_momentum_absent_without_history():
    tk = [f"T{i}" for i in range(20)]
    t = _table(tk)
    short = _closes(tk, days=100)                      # < 253 -> no 12-1 momentum
    b = _style_basis(t, short, short.index[-1])
    assert "mom" not in b.columns
    assert "beta" in b.columns and "low_vol" in b.columns


def test_incremental_collapses_style_replica():
    """A 'factor' that IS a noisy linear combination of the style basis must lose
    almost all of its IC after neutralization — the whole point of incremental IC."""
    tk = [f"T{i}" for i in range(120)]
    t, closes = _table(tk), _closes(tk)
    d = closes.index[-1]
    basis = _style_basis(t, closes, d)
    rng = np.random.default_rng(5)
    # signal = pure style combo (+ tiny noise); forward return driven by the SAME style
    style = basis["beta"].fillna(0) - 0.5 * basis["low_vol"].fillna(0)
    sig = style + rng.normal(0, 0.01, len(tk))
    fwd = pd.Series(style + rng.normal(0, 0.3, len(tk)), index=tk)
    raw = rank_ic(sig, fwd)
    inc = rank_ic(cross_sectional_resid(sig, basis), fwd)
    assert abs(raw) > 0.2                               # raw IC is strong...
    assert abs(inc) < abs(raw) * 0.5                    # ...mostly gone after neutralization


def test_incremental_preserves_orthogonal_signal():
    """A signal orthogonal to style (independent info) must keep its IC."""
    tk = [f"T{i}" for i in range(120)]
    t, closes = _table(tk), _closes(tk)
    d = closes.index[-1]
    basis = _style_basis(t, closes, d)
    rng = np.random.default_rng(6)
    indep = pd.Series(rng.normal(size=len(tk)), index=tk)   # unrelated to basis
    fwd = indep + pd.Series(rng.normal(0, 0.3, len(tk)), index=tk)
    raw = rank_ic(indep, fwd)
    inc = rank_ic(cross_sectional_resid(indep, basis), fwd)
    assert inc > 0.5 * raw                              # independent edge survives


def test_factor_basis_self_map():
    # low_vol neutralizes against beta/size/mom (not itself); low_beta drops 'beta'.
    assert _FACTOR_BASIS_SELF["low_vol"] == "low_vol"
    assert _FACTOR_BASIS_SELF["low_beta"] == "beta"
    assert "value" not in _FACTOR_BASIS_SELF            # fundamentals use the full basis
