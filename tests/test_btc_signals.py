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


def test_allocation_steps_only() -> None:
    cfg = config.load()["vector"]["allocation"]
    n = 400
    mom = pd.Series(np.linspace(-1, 1, n), index=pd.date_range("2021-01-01", periods=n))
    risk = pd.Series(np.linspace(80, 0, n), index=mom.index)
    al = S.allocation(mom, risk, cfg)
    for c in al.columns:
        assert set(al[c].dropna().unique()) <= {0.0, 0.5, 1.0}


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
               test_hysteresis_reduces_flips, test_allocation_steps_only,
               test_no_lookahead_smoke]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all btc signal tests passed")
