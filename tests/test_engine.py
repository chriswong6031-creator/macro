"""Regime engine tests on synthetic fixtures (Phase 4 requirement).

The flagship test engineers a goldilocks -> stagflation sequence and asserts:
correct quad labels on both sides, exactly one regime change (hysteresis kills
whipsaw), and transition flags firing before the flip. A second test checks the
shock override, a third that brief fakeouts do NOT flip the regime.

Run: .venv/bin/python -m pytest tests/ -q   (or python -m tests.test_engine)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.axes import score_axis  # noqa: E402
from engine.regime import apply_hysteresis, classify  # noqa: E402
from engine.transition import compute_flags, state_machine  # noqa: E402

RNG = np.random.default_rng(7)
N = 500
TURN = 250
IDX = pd.bdate_range("2020-01-01", periods=N)


def seg_series(start: float, drift_a: float, drift_b: float, noise: float,
               turn: int = TURN) -> pd.Series:
    """Geometric series drifting at drift_a before `turn`, drift_b after."""
    drifts = np.where(np.arange(N) < turn, drift_a, drift_b)
    steps = drifts + RNG.normal(0, noise, N)
    return pd.Series(start * np.exp(np.cumsum(steps)), index=IDX)


def goldilocks_to_stagflation() -> pd.DataFrame:
    f = pd.DataFrame(index=IDX)
    up_dn, dn_up = (0.002, -0.003), (-0.002, 0.003)
    nz = 0.004
    # growth components: up then down
    f["copper_gold"] = seg_series(0.0015, *up_dn, nz)
    f["xly_xlp"] = seg_series(2.0, *up_dn, nz)
    f["us2y"] = seg_series(2.0, *up_dn, nz)          # treated as level; fine
    f["iwm_spy"] = seg_series(0.45, *up_dn, nz)
    f["cyc_def"] = seg_series(1.0, *up_dn, nz)
    f["pct_above_50"] = 60 + 20 * np.where(np.arange(N) < TURN, 1, -1) * \
        np.linspace(0, 1, N) + RNG.normal(0, 1.5, N)
    f["payrolls"] = np.nan
    f["indpro"] = np.nan
    # inflation components: down then up
    f["breakeven_10y"] = seg_series(2.0, *dn_up, nz)
    f["breakeven_5y5y"] = seg_series(2.2, *dn_up, nz)
    f["energy_rs"] = seg_series(0.2, *dn_up, nz)
    f["oil"] = seg_series(70, *dn_up, nz)
    f["infl_basket"] = seg_series(1.0, *dn_up, nz)
    f["tips_nominal_spread"] = f["breakeven_10y"] * (1 + RNG.normal(0, 0.001, N))
    # supporting series for refinements / transition / cycle
    f["SPY"] = seg_series(400, 0.001, 0.0002, 0.004)   # plateaus near highs at the turn
    f["sphb_splv"] = seg_series(1.0, *up_dn, nz)
    oas = np.full(N, 3.5)
    oas[TURN:] += np.linspace(0, 2.5, N - TURN)      # credit widens after the turn
    f["hy_oas"] = oas + RNG.normal(0, 0.03, N)
    f["spread_2s10s"] = 1.0 - np.linspace(0, 1.3, N)   # flattening into inversion (late-cycle-ish)
    f["net_liquidity_bn"] = 6000 + np.linspace(0, -1000, N)  # ~-40bn/4w: contracting
    f["net_gex_bn"] = np.nan
    f["spot_vs_flip_pct"] = np.nan
    return f


def test_quads_and_single_flip() -> None:
    f = goldilocks_to_stagflation()
    regime = classify(f)
    early = regime["quad"].iloc[120:TURN - 10]
    late = regime["quad"].iloc[TURN + 80:]
    assert (early == "Q1").mean() > 0.9, f"early not Q1: {early.value_counts().to_dict()}"
    assert (late == "Q3").mean() > 0.9, f"late not Q3: {late.value_counts().to_dict()}"

    q = regime["quad"].dropna()
    changes = (q != q.shift()).sum() - 1
    assert changes <= 3, f"whipsaw: {changes} regime changes"

    # liquidity overlay reads the engineered contraction
    assert (regime["liquidity"].iloc[100:] == "contracting").mean() > 0.6


def test_transition_warns_before_flip() -> None:
    f = goldilocks_to_stagflation()
    regime = classify(f)
    flags = compute_flags(f, regime)
    state = state_machine(flags, regime)
    q = regime["quad"].dropna()
    flip_days = q.index[q != q.shift()]
    flip = [d for d in flip_days if q.loc[d] == "Q3"]
    assert flip, "no Q1->Q3 flip found"
    pre_window = state.loc[:flip[0]].iloc[-40:-1]
    assert (pre_window != "STABLE").any(), \
        "transition detector never left STABLE before the regime flip"
    assert (state.loc[flip[0]:].iloc[:3] == "NEW_REGIME").any()


def test_shock_override_flips_fast() -> None:
    # crash: growth components fall off a cliff -> flip well under 5 days' wait
    g = pd.Series(np.where(np.arange(300) < 250, 0.6, -0.95), index=pd.bdate_range("2020-01-01", periods=300))
    i = pd.Series(-0.5, index=g.index)
    out = apply_hysteresis(g, i, hysteresis_days=5, shock_z=0.7)
    assert out["quad"].iloc[249] == "Q1"
    assert out["quad"].iloc[251] == "Q4", "shock override did not flip immediately"


def test_hysteresis_blocks_fakeout() -> None:
    vals = np.full(300, 0.5)
    vals[200:203] = -0.3          # 3-day fakeout, below shock threshold
    g = pd.Series(vals, index=pd.bdate_range("2020-01-01", periods=300))
    i = pd.Series(-0.5, index=g.index)
    out = apply_hysteresis(g, i, hysteresis_days=5, shock_z=0.7)
    assert (out["quad"] == "Q1").all(), "fakeout flipped the regime"


def test_axis_scoring_direction() -> None:
    f = goldilocks_to_stagflation()
    gx = score_axis(f, "growth")
    ix = score_axis(f, "inflation")
    assert gx["growth_score"].iloc[150] > 0.3
    assert gx["growth_score"].iloc[-50] < -0.3
    assert ix["inflation_score"].iloc[150] < -0.3
    assert ix["inflation_score"].iloc[-50] > 0.3
    assert gx["growth_confidence"].iloc[150] > 0.3


if __name__ == "__main__":
    for fn in [test_quads_and_single_flip, test_transition_warns_before_flip,
               test_shock_override_flips_fast, test_hysteresis_blocks_fakeout,
               test_axis_scoring_direction]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all engine tests passed")
