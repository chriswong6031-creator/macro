"""Square-root market-impact / capacity model (engine/validation, roadmap Phase 3).

Invariants:
  * BYTE-IDENTICAL legacy — with the impact params omitted, backtest_core returns
    exactly the old flat-cost path (every existing caller is unaffected).
  * Impact ADDS cost and grows with deployed AUM (√participation), so net Sharpe is
    monotone non-increasing in AUM.
  * capacity_curve's verdict is unambiguous: no_edge (gross < buy&hold) vs a finite
    capped AUM vs exceeds_grid — the None ambiguity that conflated "no edge" with
    "uncapped" is gone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.validation import backtest_core, capacity_curve, dollar_adv


def _series(n=600, seed=0):
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(seed)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.012, n)), index=idx)
    vol = pd.Series(rng.uniform(5e5, 2e6, n), index=idx)
    # a signal that turns over: long when 20d>60d trend
    alloc = (close.rolling(20).mean() > close.rolling(60).mean()).astype(float)
    return close, vol, alloc


def test_legacy_path_byte_identical():
    close, _vol, alloc = _series()
    base = backtest_core(close, alloc, cost_bps=5.0)
    # impact params omitted -> must be identical
    again = backtest_core(close, alloc, cost_bps=5.0)
    for k in ("net", "gross", "turnover", "cost" if "cost" in base else "net"):
        if k in base:
            pd.testing.assert_series_equal(base[k], again[k])
    # passing dollar_adv but aum_usd=None also stays on the legacy path
    adv = dollar_adv(close, _vol)
    legacy = backtest_core(close, alloc, cost_bps=5.0, dollar_adv=adv, aum_usd=None)
    pd.testing.assert_series_equal(base["net"], legacy["net"])


def test_impact_adds_cost_and_scales_with_aum():
    close, vol, alloc = _series()
    adv = dollar_adv(close, vol)
    flat = backtest_core(close, alloc, cost_bps=5.0)["net"].sum()
    small = backtest_core(close, alloc, cost_bps=5.0, dollar_adv=adv, aum_usd=1e6)["net"].sum()
    big = backtest_core(close, alloc, cost_bps=5.0, dollar_adv=adv, aum_usd=1e9)["net"].sum()
    assert small < flat                      # impact only adds cost
    assert big < small                       # more AUM -> more impact -> lower net
    # zero turnover -> impact cannot bite (always-long alloc)
    flatpos = pd.Series(1.0, index=close.index)
    a = backtest_core(close, flatpos, cost_bps=5.0)["net"].sum()
    b = backtest_core(close, flatpos, cost_bps=5.0, dollar_adv=adv, aum_usd=1e9)["net"].sum()
    assert abs(a - b) < 1e-9


def test_dollar_adv_is_rolling_median_dollar_volume():
    idx = pd.bdate_range("2021-01-01", periods=30)
    close = pd.Series(np.full(30, 10.0), index=idx)
    vol = pd.Series(np.arange(1, 31, dtype=float), index=idx)
    adv = dollar_adv(close, vol, window=5)
    # last window dollar-vol = 10 * [26..30]; median = 10*28 = 280
    assert adv.iloc[-1] == 280.0


def test_capacity_curve_monotone_and_verdict():
    close, vol, alloc = _series(seed=1)
    adv = dollar_adv(close, vol)
    grid = [1e5, 1e6, 1e7, 1e8, 1e9, 1e10]
    cap = capacity_curve(close, alloc, adv, grid, cost_bps=3.0)
    ns = [r["net_sharpe"] for r in cap["curve"]]
    # net Sharpe is monotone non-increasing in AUM (allow tiny float noise)
    assert all(ns[i] >= ns[i + 1] - 1e-9 for i in range(len(ns) - 1))
    assert cap["verdict"] in ("no_edge", "capped", "exceeds_grid")
    if cap["verdict"] == "no_edge":
        assert cap["capacity_usd"] is None and not cap["economic"]
    else:
        assert cap["economic"] and cap["capacity_usd"] in grid


def test_capacity_no_edge_when_gross_below_buyhold():
    # an inverted/contrarian alloc on an uptrend underperforms buy&hold gross -> no_edge
    idx = pd.bdate_range("2020-01-01", periods=500)
    close = pd.Series(100 * np.cumprod(1 + np.full(500, 0.0005)), index=idx)  # steady uptrend
    vol = pd.Series(1e6, index=idx)
    alloc = pd.Series(np.tile([0.0, 1.0], 250), index=idx)                    # half-invested churn
    cap = capacity_curve(close, alloc, dollar_adv(close, vol), [1e6, 1e8, 1e10], cost_bps=3.0)
    assert cap["verdict"] == "no_edge"
    assert cap["capacity_usd"] is None
