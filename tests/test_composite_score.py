"""Tests for engine.composite_score — the decorrelated sector-neutral composite."""
from __future__ import annotations
import numpy as np
import pandas as pd

from engine import composite_score as cs


def _panel(n=200, seed=0):
    rng = np.random.default_rng(seed)
    sectors = {f"T{i}": ("A" if i % 2 else "B") for i in range(n)}
    legs = pd.DataFrame({
        "momentum": rng.normal(0, 1, n),
        "value": rng.normal(0, 1, n),
        "quality": rng.normal(0, 1, n),
        "profitability": rng.normal(0, 1, n),
    }, index=[f"T{i}" for i in range(n)])
    return legs, sectors


def test_composite_is_sector_neutral_and_combines_present_legs():
    legs, sectors = _panel()
    out = cs.build(legs, sectors)
    assert "composite" in out and len(out) == len(legs)
    assert (out["n_legs"] == 4).all()
    # sector-neutral: within each sector the composite mean is ~0
    sec = pd.Series(sectors)
    by_sec = out["composite"].groupby(sec).mean().abs()
    assert (by_sec < 0.2).all()


def test_missing_leg_drops_out_not_imputed():
    legs, sectors = _panel()
    legs.loc[legs.index[:50], "value"] = np.nan      # half missing value
    out = cs.build(legs, sectors)
    assert (out.loc[legs.index[:50], "n_legs"] == 3).all()
    assert (out.loc[legs.index[50:], "n_legs"] == 4).all()


def test_decorrelated_legs_stack_higher_std_than_single():
    # 4 independent legs -> composite has edge contributions from all (n_legs=4 everywhere)
    legs, sectors = _panel(seed=3)
    out = cs.build(legs, sectors)
    corr = cs.leg_correlations(legs, sectors)
    off = corr.where(~np.eye(len(corr), dtype=bool)).abs().stack()
    assert off.mean() < 0.2                           # independent legs -> low pairwise corr


def test_winsor_clamps_outliers():
    legs, sectors = _panel()
    legs.loc["T0", "momentum"] = 1e6                  # a wild outlier
    out = cs.build(legs, sectors)
    assert abs(out.loc["T0", "momentum_z"]) <= 3.5    # clamped, not exploding the z


def test_empty_or_no_legs_safe():
    assert cs.build(pd.DataFrame(), {}).empty
    legs = pd.DataFrame({"unrelated": [1.0, 2.0, 3.0]}, index=["a", "b", "c"])
    assert cs.build(legs, {"a": "X", "b": "X", "c": "X"}).empty
