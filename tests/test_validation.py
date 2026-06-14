"""Honest-validation shared module + per-calibrator cost/DSR wiring.

Covers engine.validation (the factored-out DSR + cost engine the three calibrators
now share) and the commodity / forex backtest functions that grew transaction
costs and a Deflated Sharpe. Pure-numpy, no network — the calibrators' own
signal recompute is network-bound, so we exercise the math on synthetic prices.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.validation import (
    _norm_cdf,
    _norm_ppf,
    backtest_core,
    deflated_sharpe,
    dsr_verdict,
    ret_moments,
)
from scripts.calibrate_commodities import backtest as commodity_backtest
from scripts.calibrate_forex import backtest_conviction, conviction_series


# --------------------------------------------------------------------------- #
# shared module: normal CDF/PPF, DSR, cost engine
# --------------------------------------------------------------------------- #
def test_norm_cdf_ppf_round_trip():
    assert abs(_norm_cdf(0.0) - 0.5) < 1e-9
    assert abs(_norm_ppf(0.975) - 1.959964) < 1e-4
    for p in (0.001, 0.05, 0.5, 0.95, 0.999):
        assert abs(_norm_cdf(_norm_ppf(p)) - p) < 1e-6


def test_deflated_sharpe_haircut_rises_with_trials():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.0010, 0.03, 4000))
    sr, skew, kurt, n = ret_moments(r)
    dsrs = [deflated_sharpe(sr, skew, kurt, n, N)["dsr"] for N in (1, 10, 100, 1000)]
    assert dsrs == sorted(dsrs, reverse=True)
    sr0 = [deflated_sharpe(sr, skew, kurt, n, N)["sr0_annual"] for N in (1, 10, 100, 1000)]
    assert sr0[0] == 0.0 and sr0 == sorted(sr0)


def test_deflated_sharpe_rejects_noise():
    rng = np.random.default_rng(1)
    noise = pd.Series(rng.normal(0.0, 0.03, 4000))
    sr, skew, kurt, n = ret_moments(noise)
    assert deflated_sharpe(sr, skew, kurt, n, n_trials=50)["dsr"] < 0.90


def test_deflated_sharpe_thin_input_returns_none():
    assert deflated_sharpe(None, 0.0, 3.0, 100, 50) is None
    assert deflated_sharpe(0.05, 0.0, 3.0, 2, 50) is None  # T < 3


def test_deflated_sharpe_trading_year_scales_only_annual_fields():
    # The DSR probability is annualization-invariant; only *_annual report fields scale.
    rng = np.random.default_rng(4)
    r = pd.Series(rng.normal(0.0008, 0.02, 3000))
    sr, skew, kurt, n = ret_moments(r)
    d252 = deflated_sharpe(sr, skew, kurt, n, 50, trading_year=252)
    d365 = deflated_sharpe(sr, skew, kurt, n, 50, trading_year=365)
    assert d252["dsr"] == d365["dsr"]                       # probability unchanged
    assert d252["sr_daily"] == d365["sr_daily"]
    # each annualized field is its daily Sharpe × sqrt(trading_year) (within rounding)
    assert abs(d252["sr_annual"] - d252["sr_daily"] * 252 ** 0.5) < 1e-2
    assert abs(d365["sr_annual"] - d365["sr_daily"] * 365 ** 0.5) < 1e-2


def test_dsr_verdict_bands():
    assert "SURVIVES" in dsr_verdict(0.96)
    assert "MARGINAL" in dsr_verdict(0.92)
    assert "FAILS" in dsr_verdict(0.80)


def test_backtest_core_cost_bites_and_default_is_costless():
    rng = np.random.default_rng(2)
    idx = pd.date_range("2018-01-01", periods=2000, freq="D")
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.02, 2000)), index=idx)
    alloc = pd.Series(rng.integers(0, 2, 2000).astype(float), index=idx)
    free = backtest_core(close, alloc, 0.0)
    paid = backtest_core(close, alloc, 20.0)
    assert paid["net"].sum() < free["net"].sum()           # cost lowers net returns
    assert paid["turnover"].sum() > 0
    assert (free["net"] == free["gross"]).all()             # zero cost => net == gross


def test_backtest_core_handles_long_short():
    # long/short alloc in [-1,1]: turnover counts |Δpos| through zero crossings.
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    close = pd.Series(np.linspace(100, 110, 10), index=idx)
    alloc = pd.Series([1, 1, -1, -1, 1, -1, 1, 1, -1, 0], index=idx, dtype=float)
    bt = backtest_core(close, alloc, 10.0)
    assert bt["pos"].min() < 0 and bt["pos"].max() > 0       # genuinely both sides
    assert bt["turnover"].sum() > 0


# --------------------------------------------------------------------------- #
# commodity backtest: hold_* naming preserved + cost reporting
# --------------------------------------------------------------------------- #
def test_commodity_backtest_keeps_hold_keys_and_reports_cost():
    rng = np.random.default_rng(5)
    idx = pd.date_range("2010-01-01", periods=2500, freq="B")
    close = pd.Series(50 * np.cumprod(1 + rng.normal(0, 0.015, 2500)), index=idx)
    alloc = pd.Series(rng.integers(0, 2, 2500).astype(float), index=idx)
    gross = commodity_backtest(close, alloc, cost_bps=0.0)
    net = commodity_backtest(close, alloc, cost_bps=15.0)
    # the dashboard (build_commodities.py / commodities.html.j2) reads these keys:
    for k in ("cagr", "hold_cagr", "sharpe", "hold_sharpe", "maxdd", "hold_maxdd",
              "time_in_market"):
        assert k in net
    # new honest-validation keys present
    for k in ("cagr_gross", "cost_drag_pp", "turnover_annual", "cost_bps",
              "sharpe_daily", "skew", "kurt", "n_obs"):
        assert k in net
    assert net["cagr"] < gross["cagr"]                       # cost lowers the headline
    assert net["cost_bps"] == 15.0
    assert net["cost_drag_pp"] >= 0


def test_commodity_backtest_default_is_costless():
    rng = np.random.default_rng(6)
    idx = pd.date_range("2010-01-01", periods=1200, freq="B")
    close = pd.Series(50 * np.cumprod(1 + rng.normal(0, 0.015, 1200)), index=idx)
    alloc = pd.Series(np.ones(1200), index=idx)             # always-in => no turnover
    run = commodity_backtest(close, alloc)
    assert run["cost_bps"] == 0.0
    assert run["cost_drag_pp"] == 0.0


# --------------------------------------------------------------------------- #
# forex conviction backtest
# --------------------------------------------------------------------------- #
def test_conviction_series_blends_weighted_factors_in_unit_range():
    idx = pd.date_range("2015-01-01", periods=300, freq="B")
    panel = pd.DataFrame({
        "trend": pd.Series(np.linspace(-1, 1, 300), index=idx),
        "carry": pd.Series(np.ones(300), index=idx),
        "ignored": pd.Series(np.ones(300), index=idx),     # weight 0 => excluded
    })
    weights = {"trend": 0.6, "carry": 0.4, "ignored": 0.0, "absent": 0.3}
    conv = conviction_series(panel, weights)
    assert conv is not None
    assert conv.between(-1, 1).all()
    # last row: trend=+1*0.6 + carry=+1*0.4 over mass 1.0 => +1.0
    assert abs(conv.iloc[-1] - 1.0) < 1e-9
    # a negative-weighted factor flips the contribution sign
    neg = conviction_series(panel, {"trend": -1.0})
    assert neg.iloc[0] > 0 and neg.iloc[-1] < 0             # trend rises -> conv falls


def test_conviction_series_none_when_no_weighted_factor():
    idx = pd.date_range("2015-01-01", periods=50, freq="B")
    panel = pd.DataFrame({"trend": pd.Series(np.ones(50), index=idx)})
    assert conviction_series(panel, {"carry": 0.5}) is None  # no overlap
    assert conviction_series(panel, {"trend": 0.0}) is None  # zero weight only


def test_backtest_conviction_cost_bites_and_exposes_dsr_inputs():
    rng = np.random.default_rng(8)
    idx = pd.date_range("2014-01-01", periods=2200, freq="B")
    close = pd.Series(1.2 * np.cumprod(1 + rng.normal(0, 0.006, 2200)), index=idx)
    conv = pd.Series(np.clip(rng.normal(0, 0.6, 2200), -1, 1), index=idx)  # flippy L/S
    gross = backtest_conviction(close, conv, cost_bps=0.0)
    net = backtest_conviction(close, conv, cost_bps=5.0)
    assert net["cagr"] < gross["cagr"]
    assert net["cost_bps"] == 5.0
    assert net["turnover_annual"] > 0
    for k in ("sharpe_daily", "skew", "kurt", "n_obs", "net_long_pct", "avg_exposure"):
        assert k in net
    # the per-period moments must feed the DSR without error
    d = deflated_sharpe(net["sharpe_daily"], net["skew"], net["kurt"], net["n_obs"],
                        n_trials=60, trading_year=252)
    assert d is not None and 0.0 <= d["dsr"] <= 1.0


def test_backtest_conviction_empty_when_flat():
    idx = pd.date_range("2014-01-01", periods=100, freq="B")
    close = pd.Series(np.linspace(1.0, 1.1, 100), index=idx)
    assert backtest_conviction(close, None) == {}
    assert backtest_conviction(close, pd.Series(0.0, index=idx)) == {}  # managed peg => no trades
