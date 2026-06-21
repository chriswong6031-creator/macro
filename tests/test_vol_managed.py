"""Tests for vol-managed (volatility-targeted) sizing (engine/vol_managed.py).

Invariants: the scalar is bounded, causal (no look-ahead), and INVERSE to volatility —
a calm series sizes UP toward the cap, a stormy series sizes DOWN."""
import numpy as np
import pandas as pd
import pytest

from engine import vol_managed as VM


def _series(vals, start="2014-01-01"):
    return pd.Series(np.asarray(vals, float), index=pd.bdate_range(start, periods=len(vals)))


def test_scalar_bounded():
    rng = np.random.default_rng(0)
    c = _series(100 * np.cumprod(1 + rng.normal(0, 0.01, 600)))
    s = VM.vol_scalar(c, target=0.15, cap=1.0).dropna()
    assert (s >= 0).all() and (s <= 1.0).all()


def test_scalar_inverse_to_vol():
    # low-vol vs high-vol series → low-vol sizes larger
    rng = np.random.default_rng(1)
    calm = _series(100 * np.cumprod(1 + rng.normal(0, 0.004, 600)))
    storm = _series(100 * np.cumprod(1 + rng.normal(0, 0.03, 600)))
    s_calm = VM.vol_scalar(calm, target=0.15, cap=3.0).dropna().iloc[-1]
    s_storm = VM.vol_scalar(storm, target=0.15, cap=3.0).dropna().iloc[-1]
    assert s_calm > s_storm


def test_scalar_is_causal():
    rng = np.random.default_rng(2)
    c = _series(100 * np.cumprod(1 + rng.normal(0, 0.01, 500)))
    s1 = VM.vol_scalar(c, cap=2.0)
    fut = _series(100 * np.cumprod(1 + rng.normal(0, 0.05, 80)),
                  start=(c.index[-1] + pd.tseries.offsets.BDay(1)).strftime("%Y-%m-%d"))
    s2 = VM.vol_scalar(pd.concat([c, fut]), cap=2.0)
    assert s2.loc[c.index[-1]] == pytest.approx(s1.loc[c.index[-1]], rel=1e-9, abs=1e-9)


def test_live_scalar_shape():
    rng = np.random.default_rng(3)
    c = _series(100 * np.cumprod(1 + rng.normal(0, 0.012, 400)))
    v = VM.live_scalar(c, target=0.15, cap=1.5)
    assert v is not None and 0.0 <= v <= 1.5
    assert VM.live_scalar(_series(np.linspace(100, 110, 40))) is None   # thin history
