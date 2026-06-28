"""engine/validation paired-difference primitives + the vol-overlay backtest's causal core."""
import numpy as np
import pandas as pd

from engine import validation as V


def test_calmar_sign_and_scale():
    rng = np.random.default_rng(0)
    up = rng.normal(0.0008, 0.01, 1500)        # positive-drift series
    c = V._calmar(up, 252)
    assert np.isfinite(c) and c > 0
    flat = np.zeros(500)
    assert not np.isfinite(V._calmar(flat, 252))   # no drawdown -> nan (guarded)


def test_paired_delta_ci_detects_a_real_edge():
    # A strictly dominates B (same path + a positive constant) -> Δsharpe CI should exclude 0
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2010-01-01", periods=1500)
    b = pd.Series(rng.normal(0.0002, 0.012, len(idx)), index=idx)
    a = b + 0.0006
    r = V.paired_delta_ci(a, b, block=21, B=1500)
    assert r["sharpe_better"] is True and r["delta_sharpe_ci"][0] > 0
    # symmetric: B does NOT beat A
    r2 = V.paired_delta_ci(b, a, block=21, B=1500)
    assert r2["sharpe_better"] is False


def test_paired_delta_ci_no_edge_includes_zero():
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2010-01-01", periods=1500)
    a = pd.Series(rng.normal(0.0003, 0.012, len(idx)), index=idx)
    b = pd.Series(rng.normal(0.0003, 0.012, len(idx)), index=idx)   # independent, same dist
    r = V.paired_delta_ci(a, b, block=21, B=1500)
    assert r and r["delta_sharpe_ci"][0] <= 0 <= r["delta_sharpe_ci"][2]   # CI straddles 0


def test_overlay_scalars_are_causal_and_subtract_only():
    from scripts.backtest_vol_overlay import overlay_scalars
    s = overlay_scalars()
    assert {"mech", "L2", "L3"} <= set(s.columns) and len(s) > 4000
    # subtract-only: every rung's scalar in (0, 1]; nesting L3 <= L2 <= mech
    for c in ("mech", "L2", "L3"):
        v = s[c].dropna()
        assert (v > 0).all() and (v <= 1.0 + 1e-9).all()
    nn = s.dropna()
    assert (nn["L2"] <= nn["mech"] + 1e-9).all()      # regime caution only deepens
    assert (nn["L3"] <= nn["L2"] + 1e-9).all()        # scored only deepens
