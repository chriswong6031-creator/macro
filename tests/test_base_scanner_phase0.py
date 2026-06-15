"""Harness-correctness tests for the base-scanner Phase-0 (price-only; no network).

Proves the confirmer machinery has power + specificity, and pins the base-pattern
signal definitions (so the NO-GO verdict reflects the data, not a harness bug).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.base_scanner_phase0 import conditional_split_ic, ls_net, signals  # noqa: E402


def test_confirmer_detects_planted_uplift():
    rng = np.random.default_rng(0)
    n = 400
    base = pd.Series(rng.normal(size=n))
    cond = pd.Series(rng.normal(size=n))
    hi = cond >= cond.median()
    fwd = pd.Series(rng.normal(scale=0.5, size=n))
    fwd[hi] += 1.2 * base[hi]                       # base predicts only where cond is high
    ic_hi, ic_lo = conditional_split_ic(base, cond, fwd)
    assert ic_hi > 0.20 and ic_hi - ic_lo > 0.15


def test_confirmer_no_false_uplift_on_null():
    rng = np.random.default_rng(1)
    n = 400
    base = pd.Series(rng.normal(size=n))
    cond = pd.Series(rng.normal(size=n))            # unrelated condition
    fwd = 0.8 * base + pd.Series(rng.normal(scale=0.5, size=n))
    ic_hi, ic_lo = conditional_split_ic(base, cond, fwd)
    assert abs(ic_hi - ic_lo) < 0.15


def test_signal_definitions():
    idx = pd.bdate_range("2015-01-01", periods=400)
    rng = np.random.default_rng(2)
    R = pd.DataFrame(rng.normal(scale=0.01, size=(400, 8)), index=idx,
                     columns=[f"T{i}" for i in range(8)])
    close = (1 + R).cumprod() * 100
    _, sig = signals(close)
    pp = sig["pivot_prox"].stack().dropna()
    assert (pp <= 1.0001).all() and (pp > 0).all()            # close / running-max ∈ (0, 1]
    assert (sig["tight"].stack().dropna() <= 0).all()         # tight = -realized-vol ≤ 0
    assert sig["base"].notna().any().any()


def test_ls_net_runs_and_finite():
    idx = pd.bdate_range("2020-01-01", periods=120)
    cols = [f"T{i}" for i in range(30)]
    rng = np.random.default_rng(3)
    R = pd.DataFrame(rng.normal(scale=0.01, size=(120, 30)), index=idx, columns=cols)
    net = ls_net(R, R.rolling(20).sum(), [idx[40], idx[60], idx[80]])
    assert isinstance(net, pd.Series) and len(net) == 120 and net.notna().all()
