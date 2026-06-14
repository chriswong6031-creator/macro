"""Step-0 honest-validation upgrade: transaction costs + the Deflated Sharpe
Ratio on the Vector allocation backtest (scripts/calibrate_vector.py).

These cover the NOVEL, correctness-critical pieces — the pure-numpy normal
CDF/PPF, the DSR's multiple-testing behaviour, and that turnover cost actually
reduces net CAGR — without needing the (network-bound) full signal recompute.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.calibrate_vector import (
    _norm_cdf,
    _norm_ppf,
    _ret_moments,
    backtest,
    deflated_sharpe,
)


def test_norm_cdf_ppf_are_inverses_and_accurate():
    assert abs(_norm_cdf(0.0) - 0.5) < 1e-9
    assert abs(_norm_cdf(1.959964) - 0.975) < 1e-5
    assert abs(_norm_ppf(0.975) - 1.959964) < 1e-4
    assert abs(_norm_ppf(0.5)) < 1e-9
    # round-trip across the range
    for p in (0.001, 0.05, 0.3, 0.7, 0.95, 0.999):
        assert abs(_norm_cdf(_norm_ppf(p)) - p) < 1e-6


def test_deflated_sharpe_haircut_rises_with_trials():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.0010, 0.03, 4000))  # a genuinely strong daily strat
    sr, skew, kurt, n = _ret_moments(r)
    dsrs = [deflated_sharpe(sr, skew, kurt, n, N)["dsr"] for N in (1, 10, 100, 1000)]
    # more trials => bigger selection-bias haircut => lower probability the edge is real
    assert dsrs == sorted(dsrs, reverse=True)
    sr0 = [deflated_sharpe(sr, skew, kurt, n, N)["sr0_annual"] for N in (1, 10, 100, 1000)]
    assert sr0[0] == 0.0 and sr0 == sorted(sr0)  # N=1 has no haircut; SR0 grows with N


def test_deflated_sharpe_rejects_a_noise_strategy():
    rng = np.random.default_rng(1)
    noise = pd.Series(rng.normal(0.0, 0.03, 4000))  # zero-edge
    sr, skew, kurt, n = _ret_moments(noise)
    d = deflated_sharpe(sr, skew, kurt, n, n_trials=50)
    assert d["dsr"] < 0.90  # must not survive the haircut


def test_deflated_sharpe_degrades_gracefully_on_thin_input():
    assert deflated_sharpe(None, 0.0, 3.0, 100, 50) is None
    assert deflated_sharpe(0.05, 0.0, 3.0, 2, 50) is None  # T < 3


def test_transaction_cost_reduces_net_cagr_and_is_reported():
    # A flippy daily allocation on a flat-drift random price: cost must bite, and
    # gross/net/drag/turnover must all be present and internally consistent.
    rng = np.random.default_rng(2)
    idx = pd.date_range("2018-01-01", periods=2000, freq="D")
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.02, 2000)), index=idx)
    alloc = pd.Series(rng.integers(0, 2, 2000).astype(float), index=idx)  # toggles a lot
    gross_run = backtest(close, alloc, cost_bps=0.0)
    net_run = backtest(close, alloc, cost_bps=20.0)
    assert net_run["cagr"] < gross_run["cagr"]            # cost lowers the headline
    assert net_run["turnover_annual"] > 0
    assert net_run["cost_drag_pp"] >= 0
    assert net_run["cost_bps"] == 20.0
    # the reported gross matches the zero-cost run's net (same path, no friction)
    assert abs(net_run["cagr_gross"] - gross_run["cagr"]) < 0.2


def test_backtest_default_is_costless_for_legacy_callers():
    # backtest_ladder_history.py and others call backtest(close, alloc) — default
    # must stay gross-of-cost so their numbers don't silently shift.
    rng = np.random.default_rng(3)
    idx = pd.date_range("2018-01-01", periods=1000, freq="D")
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.02, 1000)), index=idx)
    alloc = pd.Series(np.ones(1000), index=idx)  # always-in => zero turnover after day 1
    run = backtest(close, alloc)
    assert run["cost_bps"] == 0.0
    assert run["cost_drag_pp"] == 0.0
