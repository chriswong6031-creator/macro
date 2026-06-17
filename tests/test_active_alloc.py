"""Unit guards for engine.active_alloc — the leverage-aware active-allocation engine.

Pure-math checks on synthetic series so they run with no data cache: leverage/financing
accounting, vol-targeting caps, the scorecard contract (keys the detail template needs),
the multi-asset portfolio book, and the split-half OOS panel.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import active_alloc as aa


def _ramp(n=600, drift=0.0004, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    ret = rng.normal(drift, 0.012, n)
    return pd.Series(100 * np.cumprod(1 + ret), index=idx)


def test_backtest_lev_financing_and_scorecard():
    px = _ramp(drift=0.0010)                            # clean uptrend so 2x reliably out-earns 1x
    bill = pd.Series(4.0, index=px.index)              # 4% cash/borrow base
    # full 2x leverage the whole time -> ~2x the asset return minus financing on the 1x borrow
    size = pd.Series(2.0, index=px.index)
    r = aa.backtest_lev(px, size, bill, cost_bps=0.0, borrow_spread=1.0)
    assert set(["cagr", "hodl_cagr", "sharpe", "hodl_sharpe", "maxdd", "hodl_maxdd",
                "sortino", "time_in_market", "turnover_annual", "avg_leverage",
                "max_leverage", "years"]).issubset(r)
    assert abs(r["avg_leverage"] - 2.0) < 0.01 and abs(r["max_leverage"] - 2.0) < 1e-6  # day-1 ramps from 0
    # levered book is ~2x the asset's excess path: its CAGR exceeds buy-&-hold in an uptrend
    assert r["cagr"] > r["hodl_cagr"]
    # a flat (cash) book earns ~the bill, never the asset
    flat = aa.backtest_lev(px, pd.Series(0.0, index=px.index), bill)
    assert flat["time_in_market"] == 0.0 and 2.5 < flat["cagr"] < 4.5


def test_vol_target_size_caps_and_scales():
    px = _ramp()
    conv = pd.Series(1.0, index=px.index)               # full bullish conviction
    size = aa.vol_target_size(conv, px, target_vol=0.15, max_lev=2.0)
    assert size.dropna().max() <= 2.0 + 1e-9 and size.dropna().min() >= 0.0
    # higher target vol -> larger average position
    hi = aa.vol_target_size(conv, px, target_vol=0.30, max_lev=3.0)
    assert hi.dropna().mean() >= size.dropna().mean()


def test_blend_renormalizes_missing_legs():
    idx = pd.bdate_range("2015-01-01", periods=300)
    a = pd.Series(1.0, index=idx)
    b = pd.Series(-1.0, index=idx); b.iloc[:150] = np.nan      # warms up halfway
    out = aa.blend({"a": (a, 1.0), "b": (b, 1.0)}, idx)
    assert abs(out.iloc[0] - 1.0) < 1e-9                       # only 'a' active early
    assert abs(out.iloc[-1] - 0.0) < 1e-9                      # +1 and -1 cancel later
    assert out.between(-1, 1).all()


def test_backtest_portfolio_levers_and_scores():
    idx = pd.bdate_range("2015-01-01", periods=600)
    rng = np.random.default_rng(3)
    closes = pd.DataFrame({
        "SPY": 100 * np.cumprod(1 + rng.normal(0.0004, 0.011, 600)),
        "IEF": 100 * np.cumprod(1 + rng.normal(0.0001, 0.004, 600)),
    }, index=idx)
    bill = pd.Series(3.0, index=idx)
    w = pd.DataFrame({"SPY": 0.6, "IEF": 0.6}, index=idx)      # 1.2x gross
    p = aa.backtest_portfolio(w, closes, bill, cost_bps=0.0)
    assert abs(p["gross_lev"].mean() - 1.2) < 0.01            # day-1 ramps from 0
    assert "cagr" in p and "sharpe" in p and "net" in p
    # diversified levered book has a higher Sharpe than the equity sleeve alone here
    assert p["sharpe"] >= p["hodl_sharpe"] - 0.05


def test_split_half_oos_flags_non_robust():
    idx = pd.bdate_range("2010-01-01", periods=1000)
    # net beats hodl in the first half, loses in the second -> robust must be False
    net = pd.Series(np.r_[np.full(500, 0.0010), np.full(500, -0.0002)], index=idx)
    hodl = pd.Series(np.r_[np.full(500, 0.0005), np.full(500, 0.0006)], index=idx)
    oos = aa.split_half_oos(net, hodl)
    assert oos["first"]["beats_cagr"] is True and oos["second"]["beats_cagr"] is False
    assert oos["robust"] is False
