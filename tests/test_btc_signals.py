"""Bitcoin Vector signal-engine tests on synthetic price paths — no network.

Run: .venv/bin/python -m tests.test_btc_signals
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_signals as S  # noqa: E402
from lib import config  # noqa: E402


def _synthetic(n=600, trend=0.002, vol=0.02, seed=1) -> dict:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    rets = rng.normal(trend, vol, n)
    close = pd.Series(100 * np.exp(np.cumsum(rets)), index=idx)
    px = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": rng.uniform(1, 2, n)}, index=idx)
    return {"price": px, "hourly": None, "intraday_vol": None}


def test_momentum_bounds_and_direction() -> None:
    cfg = config.load()["vector"]["momentum"]
    up = S.momentum(_synthetic(trend=0.004, seed=2), cfg)
    dn = S.momentum(_synthetic(trend=-0.004, seed=3), cfg)
    assert up["momentum"].between(-1, 1).all()
    assert up["momentum"].tail(60).mean() > 0.3   # sustained uptrend -> bullish
    assert dn["momentum"].tail(60).mean() < -0.3  # sustained downtrend -> bearish


def test_risk_index_range_and_regime() -> None:
    inp = _synthetic(trend=-0.006, seed=4)
    mom = S.momentum(inp, config.load()["vector"]["momentum"])["momentum"]
    rk = S.risk(inp, mom, config.load()["vector"]["risk"])
    assert rk["risk_index"].dropna().between(0, 100).all()
    assert rk["risk_oscillator"].dropna().between(0, 1).all()
    assert set(rk["risk_regime"].unique()) <= {"high_risk", "low_risk"}


def test_hysteresis_reduces_flips() -> None:
    # a score that dithers right around the trigger should NOT flip every bar
    idx = pd.date_range("2021-01-01", periods=200, freq="D")
    rng = np.random.default_rng(5)
    score = pd.Series(0.5 + rng.normal(0, 0.05, 200), index=idx)  # hovering at +0.5
    naive = pd.Series(np.where(score > 0.5, "bull", "neutral"), index=idx)
    hyst = S._hysteresis_tri(score, 0.5, 0.25)
    naive_flips = (naive != naive.shift()).sum()
    hyst_flips = (hyst != hyst.shift()).sum()
    assert hyst_flips < naive_flips


def test_allocation_base_grid_preserved() -> None:
    # with Point-4 sizing OFF the base grid is exactly the legacy {0, 0.5, 1.0} steps —
    # conviction/brake are layered ON TOP of this, never replacing it.
    cfg = {**config.load()["vector"]["allocation"],
           "conviction_sizing": False, "drawdown_brake": False}
    n = 400
    mom = pd.Series(np.linspace(-1, 1, n), index=pd.date_range("2021-01-01", periods=n))
    risk = pd.Series(np.linspace(80, 0, n), index=mom.index)
    al = S.allocation(mom, risk, cfg)
    for c in al.columns:
        assert set(al[c].dropna().unique()) <= {0.0, 0.5, 1.0}


def test_conviction_multiplier_monotone_in_tier() -> None:
    # the size multiplier must be MONOTONE in conviction: EDGE >= LEAN >= TOSS-UP,
    # and continuous (non-decreasing) in the underlying directional-confidence score.
    cfg = config.load()["vector"]["allocation"]
    floor = float(cfg.get("conviction_floor", 0.5))
    scores = np.linspace(0.5, 1.0, 200)
    mult = S.conviction_multiplier(scores, cfg)
    assert np.all((mult >= floor - 1e-9) & (mult <= 1.0 + 1e-9))   # bounded [floor, 1]
    assert np.all(np.diff(mult) >= -1e-12)                          # monotone non-decreasing
    # one representative score per tier -> strictly ordered multipliers
    toss = 0.5 + cfg.get("conviction_toss", 0.05) / 2              # inside TOSS-UP band
    lean = 0.5 + (cfg.get("conviction_toss", 0.05) + cfg.get("conviction_edge", 0.30)) / 2
    edge = 0.5 + cfg.get("conviction_edge", 0.30) + 0.05          # past EDGE band
    assert S.conviction_tier(toss, cfg) == "TOSS-UP"
    assert S.conviction_tier(lean, cfg) == "LEAN"
    assert S.conviction_tier(edge, cfg) == "EDGE"
    m_toss = S.conviction_multiplier(toss, cfg)
    m_lean = S.conviction_multiplier(lean, cfg)
    m_edge = S.conviction_multiplier(edge, cfg)
    assert m_toss < m_lean < m_edge
    assert abs(m_toss - floor) < 1e-9 and abs(m_edge - 1.0) < 1e-9  # TOSS-UP=floor, EDGE=full


def test_drawdown_brake_reduces_exposure_when_underwater() -> None:
    # a flat-1.0 allocation through a rising-then-crashing path: the brake leaves
    # exposure untouched while at a high-water mark, then tightens once underwater.
    cfg = config.load()["vector"]["allocation"]
    floor = float(cfg.get("dd_floor", 0.30))
    n = 120
    idx = pd.date_range("2021-01-01", periods=n)
    alloc = pd.Series(1.0, index=idx)
    rets = np.concatenate([np.full(50, 0.01), np.full(n - 50, -0.03)])  # rally, then bleed
    ret = pd.Series(rets, index=idx)
    braked = S.drawdown_brake(alloc, ret, cfg)
    assert braked.between(0.0, 1.0).all()
    assert (braked <= alloc + 1e-12).all()                # never adds exposure
    assert np.allclose(braked.iloc[:50].values, 1.0)      # no brake at the high-water mark
    assert braked.iloc[-1] < 1.0                          # tightened while deep underwater
    assert braked.min() >= floor - 1e-9                   # never below the configured floor
    assert braked.iloc[-1] <= braked.iloc[60]             # tightens as drawdown deepens


def test_allocation_conviction_and_brake_unit_range() -> None:
    # the full path (grid -> conviction -> brake) stays in [0,1] AND actually produces
    # CONTINUOUS sizes (a thin setup no longer sizes the same as a strong one).
    cfg = config.load()["vector"]["allocation"]
    inp = _synthetic(n=500, trend=0.003, seed=11)
    close = inp["price"]["close"]
    mom = S.momentum(inp, config.load()["vector"]["momentum"])["momentum"]
    risk = S.risk(inp, mom, config.load()["vector"]["risk"])["risk_index"]
    al = S.allocation(mom, risk, cfg, close=close)
    for c in al.columns:
        col = al[c].dropna()
        assert col.between(0.0, 1.0).all()
        # sizing is no longer pinned to the three legacy steps
        assert not set(col.round(6).unique()) <= {0.0, 0.5, 1.0}


def test_no_lookahead_smoke() -> None:
    # truncating the series must not change earlier signal values
    inp = _synthetic(n=500, seed=6)
    cfg = config.load()["vector"]["momentum"]
    full = S.momentum(inp, cfg)["momentum"]
    trunc_inp = {"price": inp["price"].iloc[:400], "hourly": None, "intraday_vol": None}
    trunc = S.momentum(trunc_inp, cfg)["momentum"]
    # EMA is causal -> overlapping region should match closely
    overlap = full.iloc[100:390]
    assert np.allclose(overlap.values, trunc.reindex(overlap.index).values, atol=1e-6)


if __name__ == "__main__":
    for fn in [test_momentum_bounds_and_direction, test_risk_index_range_and_regime,
               test_hysteresis_reduces_flips, test_allocation_base_grid_preserved,
               test_conviction_multiplier_monotone_in_tier,
               test_drawdown_brake_reduces_exposure_when_underwater,
               test_allocation_conviction_and_brake_unit_range,
               test_no_lookahead_smoke]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all btc signal tests passed")
