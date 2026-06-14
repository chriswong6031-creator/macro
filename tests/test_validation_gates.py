"""Stability-gate primitives (engine.validation) — purged folds, block-bootstrap CI,
probability calibration, collinearity. Pure functions, synthetic data, no network.

Run: .venv/bin/python -m tests.test_validation_gates
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import validation as V  # noqa: E402


def test_purged_folds_embargo():
    idx = pd.date_range("2015-01-01", periods=1000, freq="D")
    folds = V.purged_folds(idx, k=5, embargo=90)
    assert len(folds) == 5
    sizes = [len(f) for f in folds.values()]
    # each fold drops the trailing 90 (embargo) rows from its ~200-row block
    assert all(100 <= s <= 130 for s in sizes), sizes
    # folds are ordered and non-overlapping in time (right edge of fold i < left of i+1 block)
    fl = list(folds.values())
    for i in range(len(fl) - 1):
        assert fl[i][-1] < fl[i + 1][0]
    # short series -> one embargoed block
    short = V.purged_folds(idx[:120], k=5, embargo=90)
    assert len(short) == 1 and len(short["fold1"]) == 30


def test_block_bootstrap_ci():
    rng = np.random.default_rng(0)
    # positive-drift series -> Sharpe CI should sit above 0
    r = pd.Series(rng.normal(0.002, 0.03, 1500))
    ci = V.block_bootstrap_ci(r, block=21, B=1000, seed=1)
    assert ci["sharpe_ci"][0] < ci["sharpe_ci"][1] < ci["sharpe_ci"][2]   # ordered
    assert ci["sharpe_gt0_prob"] > 0.8
    assert ci["maxdd_ci_pct"][0] < 0                                       # drawdown negative
    assert V.block_bootstrap_ci(pd.Series(rng.normal(0, 0.01, 20))) == {}  # too short


def test_brier_and_platt_calibrated():
    rng = np.random.default_rng(2)
    # well-calibrated: outcome drawn with prob = p
    p = rng.uniform(0.2, 0.8, 4000)
    y = (rng.uniform(size=4000) < p).astype(float)
    br = V.brier_reliability(p, y)
    assert br["skill_score"] > 0                       # beats climatology
    assert br["reliability"][0]["n"] >= 10
    pf = V.platt_fit(p, y)
    assert 0.7 <= pf["a"] <= 1.3 and abs(pf["b"]) < 0.4  # near identity when calibrated


def test_brier_detects_miscalibration():
    rng = np.random.default_rng(3)
    p = rng.uniform(0, 1, 3000)
    y = (rng.uniform(size=3000) < (0.5 + 0.5 * (p - 0.5))).astype(float)  # overconfident p
    pf = V.platt_fit(p, y)
    assert pf["a"] < 0.95   # Platt shrinks the overconfident slope below 1


def test_vif_and_pairs_catch_collinearity():
    rng = np.random.default_rng(4)
    base = rng.normal(size=500)
    df = pd.DataFrame({
        "a": base,
        "b": base + rng.normal(0, 0.05, 500),    # ~clone of a -> high VIF
        "c": rng.normal(size=500),               # independent
    })
    v = V.vif(df)
    assert v["a"] > 5 and v["b"] > 5 and v["c"] < 3
    pairs = V.top_correlated_pairs(df, thresh=0.6)
    assert any({"a", "b"} == {pr["a"], pr["b"]} for pr in pairs)


def test_resid_z_removes_correlation_causally():
    rng = np.random.default_rng(5)
    idx = pd.date_range("2015-01-01", periods=1500, freq="D")
    b = pd.Series(rng.normal(size=1500), index=idx)
    z = 0.8 * b + 0.6 * pd.Series(rng.normal(size=1500), index=idx)   # z carries a b-component
    r = V.resid_z(z, [b], win=252, min_p=252)
    warm = slice(400, None)                                            # after betas are estimable
    assert abs(z[warm].corr(b[warm])) > 0.6                           # z was correlated with b
    assert abs(r[warm].corr(b[warm])) < 0.2                           # residual de-correlated
    # causal: residual at t uses only prior-window betas -> no look-ahead (raw until estimable)
    assert r.iloc[:252].equals(z.iloc[:252]) or r.iloc[:10].equals(z.iloc[:10])


if __name__ == "__main__":
    for fn in [test_purged_folds_embargo, test_block_bootstrap_ci, test_brier_and_platt_calibrated,
               test_brier_detects_miscalibration, test_vif_and_pairs_catch_collinearity,
               test_resid_z_removes_correlation_causally]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all validation-gate tests passed")
