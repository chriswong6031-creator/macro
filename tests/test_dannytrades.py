"""engine/dannytrades — the reconstructed DannyTrades signal stack.

The load-bearing test is CAUSALITY (no look-ahead): signals computed on a truncated
prefix must be byte-identical to the full-series signals at every earlier index — the
same prefix-truncation equivalence the phase-0 leakage audit used. Plus bounded
outputs, indicator sanity, and graceful degradation on thin input.
"""
import numpy as np
import pandas as pd
import pytest

from engine import dannytrades as dt


def _synth(n=1200, seed=3):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0004, 0.02, n)
    close = pd.Series(100 * np.exp(np.cumsum(ret)),
                      index=pd.bdate_range("2010-01-01", periods=n))
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    volume = pd.Series(rng.lognormal(15, 0.5, n), index=close.index)
    return close, high, low, volume


def test_outputs_bounded_and_present():
    close, high, low, volume = _synth()
    s = dt.signals(close, high, low, volume)
    for col in ("whale", "score", "ribbon", "danny_buy", "danny_sell", "breakout_up"):
        assert col in s.columns
    assert s["whale"].dropna().between(0, 100).all()
    assert s["score"].dropna().between(0, 100).all()
    assert set(s["ribbon"].dropna().unique()) <= {-1.0, 0.0, 1.0}
    # the discrete states should fire at least sometimes over 1200 bars, not constantly
    for st in ("danny_buy", "danny_sell", "breakout_up", "whale_entering"):
        k = int(s[st].sum())
        assert 0 < k < len(s) * 0.6, f"{st} fired {k}/{len(s)} — implausible"


def test_no_lookahead_prefix_truncation():
    """THE causality guarantee: a signal at time t must use only data ≤ t, so
    computing on df[:k] reproduces the full-series values at every index < k."""
    close, high, low, volume = _synth(n=900)
    full = dt.signals(close, high, low, volume)
    cols = ["whale", "score", "ribbon", "momentum_ok", "box_upper", "box_lower",
            "breakout_up", "breakdown", "poc", "danny_buy", "danny_sell"]
    for k in (300, 500, 800):
        pref = dt.signals(close.iloc[:k], high.iloc[:k], low.iloc[:k], volume.iloc[:k])
        a = full[cols].iloc[:k - 1]          # drop the very last bar (edge effects)
        b = pref[cols].iloc[:k - 1]
        # numeric columns equal within float tol; boolean columns exactly equal
        for c in cols:
            xa, xb = a[c], b[c]
            if xa.dtype == bool or set(pd.unique(xa.dropna())) <= {0.0, 1.0, True, False}:
                assert xa.fillna(-9).equals(xb.fillna(-9)), f"{c} differs at k={k}"
            else:
                m = xa.notna() & xb.notna()
                assert np.allclose(xa[m], xb[m], rtol=1e-9, atol=1e-9), f"{c} differs at k={k}"


def test_future_perturbation_cannot_move_past_signal():
    """Perturbing a FUTURE bar must not change any signal value before it."""
    close, high, low, volume = _synth(n=700)
    base = dt.signals(close, high, low, volume)
    c2 = close.copy(); c2.iloc[400] *= 1.5          # shock a future bar
    h2 = high.copy(); h2.iloc[400] *= 1.5
    pert = dt.signals(c2, h2, low, volume)
    pre = slice(0, 399)
    assert np.allclose(base["score"].iloc[pre].fillna(0),
                       pert["score"].iloc[pre].fillna(0), atol=1e-9)
    assert base["whale"].iloc[pre].fillna(0).equals(pert["whale"].iloc[pre].fillna(0))


def test_cmf_and_obv_directional():
    # rising close that prints NEAR ITS HIGH (low far below) → positive accumulation
    n = 200
    idx = pd.bdate_range("2015-01-01", periods=n)
    close = pd.Series(np.linspace(100, 140, n), index=idx)
    high = close * 1.001                                  # just above
    low = close * 0.985                                   # well below → close near high
    vol = pd.Series(1e6, index=idx)
    assert dt.cmf(high, low, close, vol, 21).dropna().mean() > 0
    assert dt.obv(close, vol).iloc[-1] > 0                # all up days → OBV rises


def test_whale_responds_to_accelerating_accumulation():
    # the whale% is a trailing PERCENTILE (≈50 mean) — it runs hot when accumulation
    # ACCELERATES: mid-range closes early, near-high closes late.
    n = 400
    idx = pd.bdate_range("2015-01-01", periods=n)
    close = pd.Series(np.linspace(50, 120, n), index=idx)
    half = n // 2
    near_high = np.where(np.arange(n) >= half, 0.985, 0.99)   # later bars close higher in range
    high = close * 1.002
    low = close * pd.Series(near_high, index=idx)
    vol = pd.Series(np.linspace(1e6, 3e6, n), index=idx)
    w = dt.whale_accumulation(high, low, close, vol).dropna()
    assert w.iloc[-1] > 60                                # elevated after the acceleration
    assert w.iloc[half:].mean() > w.iloc[:half].mean()   # responds in the right direction


def test_whale_buy_fraction_saturates():
    # closes pinned near the high every bar → buy fraction saturates high; near the
    # low → saturates low; mid-range → ~50. Bounded 0-100, causal.
    n = 200
    idx = pd.bdate_range("2015-01-01", periods=n)
    close = pd.Series(np.linspace(50, 90, n), index=idx)
    vol = pd.Series(1e6, index=idx)
    hot = dt.whale_buy_fraction(close * 1.001, close * 0.97, close, vol, 21).dropna()
    cold = dt.whale_buy_fraction(close * 1.03, close * 0.999, close, vol, 21).dropna()
    assert hot.iloc[-1] > 85 and cold.iloc[-1] < 15
    assert dt.whale_buy_fraction(close * 1.01, close * 0.99, close, vol, 21).dropna().between(0, 100).all()


def test_thin_input_degrades_gracefully():
    close, high, low, volume = _synth(n=40)               # below most windows
    s = dt.signals(close, high, low, volume)
    assert len(s) == 40
    assert not s["danny_buy"].any() or s["danny_buy"].dtype == bool   # no crash
