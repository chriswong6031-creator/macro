"""Commodity Vector signal-engine tests on synthetic paths — no network.

Run: .venv/bin/python -m tests.test_commodity_signals
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import commodity_signals as S  # noqa: E402
from lib import config  # noqa: E402

CFG = config.load()["commodities"]


def _price(n=800, trend=0.0003, vol=0.015, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(trend, vol, n))), index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": rng.uniform(1, 2, n)}, index=idx)


def _drivers(idx, seed=7) -> dict:
    rng = np.random.default_rng(seed)
    walk = lambda s, scale: pd.Series(np.cumsum(rng.normal(0, scale, len(idx))) + s, index=idx)
    return {
        "real_yield": walk(1.0, 0.02),
        "dxy": pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(idx)))), index=idx),
        "breakeven10": walk(2.2, 0.01),
        "fed_balance": pd.Series(8e6 + np.cumsum(rng.normal(0, 5e3, len(idx))), index=idx),
        "indpro": pd.Series(100 + np.cumsum(rng.normal(0, 0.05, len(idx))), index=idx),
        "us10y": walk(3.0, 0.02),
    }


def test_momentum_bounds_and_direction() -> None:
    up = S.momentum(_price(trend=0.002, seed=2), CFG["momentum"])
    dn = S.momentum(_price(trend=-0.002, seed=3), CFG["momentum"])
    assert up["momentum"].between(-1, 1).all()
    assert up["momentum"].tail(60).mean() > 0.3
    assert dn["momentum"].tail(60).mean() < -0.3


def test_risk_index_range_and_regime() -> None:
    px = _price(trend=-0.003, seed=4)
    mom = S.momentum(px, CFG["momentum"])["momentum"]
    rk = S.risk(px, mom, None, CFG["risk"])
    assert rk["risk_index"].dropna().between(0, 100).all()
    assert rk["risk_oscillator"].dropna().between(0, 1).all()
    assert set(rk["risk_regime"].unique()) <= {"high_risk", "low_risk"}


def test_driver_axis_orientation() -> None:
    # gold rises when real yields AND the dollar FALL -> a steady fall in both
    # must read as a tailwind (positive driver_score).
    idx = pd.date_range("2015-01-01", periods=400, freq="B")
    falling = pd.Series(np.linspace(2.0, 0.0, 400), index=idx)          # real_yield down
    dxy_dn = pd.Series(np.linspace(110, 90, 400), index=idx)            # dollar down
    drivers = {"real_yield": falling, "dxy": dxy_dn,
               "breakeven10": pd.Series(2.0, index=idx), "fed_balance": pd.Series(8e6, index=idx)}
    da = S.driver_axis(_price(n=400), drivers, "gold", CFG["driver_axis"])
    assert da["driver_score"].dropna().between(-1, 1).all()
    assert da["driver_score"].tail(60).mean() > 0.3
    assert "tailwind" in set(da["driver_state"].tail(60))


def test_positioning_states_and_rolling() -> None:
    idx = pd.date_range("2015-01-01", periods=900, freq="B")
    pos = pd.Series(np.r_[np.linspace(-20, 20, 450), np.linspace(20, -20, 450)], index=idx)
    pcfg = {**CFG["positioning"], "pctile_lookback_d": 250}
    out = S.positioning(pos, idx, pcfg)
    assert out["pos_pctile"].dropna().between(0, 100).all()
    assert set(out["pos_state"].dropna().unique()) <= {"crowded_long", "crowded_short", "neutral"}
    assert (out["pos_state"] == "crowded_long").any()


def test_residual_flags_exogenous_bid() -> None:
    # drivers flat-ish; inject a large UNEXPLAINED price run in the tail -> the
    # causal residual must spike positive and flag exogenous_bid.
    n = 700
    px = _price(n=n, trend=0.0, vol=0.008, seed=11)
    idx = px.index
    px = px.copy()
    px.iloc[-40:, px.columns.get_loc("close")] *= np.linspace(1.0, 1.4, 40)  # +40% shock, no driver move
    drivers = _drivers(idx, seed=12)
    rcfg = {**CFG["residual"], "min_train_d": 300, "refit_every_d": 21}
    rs = S.residual_shock(px, drivers, "gold", rcfg)
    assert rs["shock_z"].tail(20).max() > 1.5
    assert (rs["shock_state"].tail(20) == "exogenous_bid").any()


def test_residual_is_causal() -> None:
    # truncating later data must not change earlier residuals (betas use history < i only)
    n = 700
    px = _price(n=n, seed=13)
    drivers = _drivers(px.index, seed=14)
    rcfg = {**CFG["residual"], "min_train_d": 300, "refit_every_d": 21}
    full = S.residual_shock(px, drivers, "gold", rcfg)["resid_ret"]
    tr_px = px.iloc[:600]
    tr_drivers = {k: v.iloc[:600] for k, v in drivers.items()}
    trunc = S.residual_shock(tr_px, tr_drivers, "gold", rcfg)["resid_ret"]
    overlap = full.iloc[320:560].dropna()
    assert np.allclose(overlap.values, trunc.reindex(overlap.index).values, atol=1e-9, equal_nan=True)


def test_ts_momentum_bounds_and_direction() -> None:
    up = S.ts_momentum(_price(n=600, trend=0.0025, vol=0.008, seed=20), CFG["trend"])
    dn = S.ts_momentum(_price(n=600, trend=-0.0025, vol=0.008, seed=21), CFG["trend"])
    assert up["ts_momentum"].dropna().between(-1, 1).all()
    assert up["ts_momentum"].tail(60).mean() > 0.3
    assert dn["ts_momentum"].tail(60).mean() < -0.3
    assert set(up["ts_trend"].dropna().unique()) <= {"up", "down", "flat"}


def test_gsr_and_brent_wti() -> None:
    idx = pd.date_range("2015-01-01", periods=900, freq="B")
    gold = pd.Series(np.linspace(1200, 2000, 900), index=idx)
    silver = pd.Series(np.linspace(20, 25, 900), index=idx)  # GSR rising -> silver cheaper
    gsr = S.gold_silver_ratio(gold, silver, {**CFG["gold_silver_ratio"], "pctile_lookback_d": 250})
    assert gsr["gsr_pctile"].dropna().between(0, 100).all()
    assert set(gsr["gsr_state"].dropna().unique()) <= {"silver_cheap", "silver_rich", "neutral"}
    wti = pd.Series(np.linspace(50, 80, 900), index=idx)
    brent = wti + np.linspace(2, 8, 900)  # spread widening
    bw = S.brent_wti(wti, brent, CFG["brent_wti"])
    assert bw["bw_change"].dropna().gt(0).mean() > 0.8   # widening -> positive change
    assert bw["bw_spread_pctile"].dropna().between(0, 100).all()


def test_complex_regime_labels() -> None:
    results = {a: pd.DataFrame({"close": _price(seed=i)["close"]})
               for i, a in enumerate(["gold", "silver", "copper", "oil"])}
    drivers = _drivers(results["gold"].index)
    cx = S.complex_regime(results, drivers, CFG)
    valid = {"Reflation", "Stagflation", "Goldilocks", "Deflation-scare", "Neutral"}
    assert set(cx["complex_regime"].dropna().unique()) <= valid
    assert {"gold_silver", "copper_gold", "oil_gold"} <= set(cx.columns)


if __name__ == "__main__":
    for fn in [test_momentum_bounds_and_direction, test_risk_index_range_and_regime,
               test_driver_axis_orientation, test_positioning_states_and_rolling,
               test_residual_flags_exogenous_bid, test_residual_is_causal,
               test_ts_momentum_bounds_and_direction, test_gsr_and_brent_wti,
               test_complex_regime_labels]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all commodity signal tests passed")
