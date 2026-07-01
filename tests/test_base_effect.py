"""Unit guards for engine.base_effect — the comparative base-effect forward projection.

Pure-math checks on synthetic level series (no data cache): the sign convention that the
axis measures ACCELERATION of the YoY rate (first difference of the YoY path = the Hedgeye
Quad axis), not the noisy second difference; plus the grading-row contract.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import base_effect as be


def _const_growth(n=72, mom=0.002):
    idx = pd.date_range("2020-01-01", periods=n, freq="MS")
    return pd.Series(100.0 * (1.0 + mom) ** np.arange(n), index=idx)


def test_constant_growth_is_flat():
    """A pure exponential level has a constant YoY -> no acceleration in any quarter."""
    q = be._quarter_signs(be._project(_const_growth())["accel"])
    assert q == {"q1": 0, "q2": 0, "q3": 0}


def test_easy_base_forces_acceleration():
    """Depressing the forward base window (the denominators for h=1..9) makes the forward YoY
    RISE -> the rate accelerates -> +1. Anchor is index n-1=71, base month for h is 60+h."""
    lvl = _const_growth().to_numpy().astype(float)
    for j, i in enumerate(range(61, 70)):
        lvl[i] *= 1.0 - 0.002 * (j + 1)      # deeper dip for later base months
    q = be._quarter_signs(be._project(pd.Series(lvl, index=_const_growth().index))["accel"])
    assert q["q1"] == 1 and q["q2"] == 1


def test_tough_base_forces_deceleration():
    """Raising the forward base window makes the forward YoY FALL -> the rate decelerates -> -1."""
    lvl = _const_growth().to_numpy().astype(float)
    for j, i in enumerate(range(61, 70)):
        lvl[i] *= 1.0 + 0.002 * (j + 1)
    q = be._quarter_signs(be._project(pd.Series(lvl, index=_const_growth().index))["accel"])
    assert q["q1"] == -1 and q["q2"] == -1


def test_project_short_series_returns_none():
    idx = pd.date_range("2024-01-01", periods=10, freq="MS")
    assert be._project(pd.Series(np.arange(1, 11.0), index=idx)) is None


def test_level_from_yoy_is_smooth():
    """Reconstruct a level from an OSCILLATING YoY: it must be smooth (no fabricated within-year
    jumps like the naive exact chain) and monotone up for a positive average YoY."""
    idx = pd.date_range("2015-01-01", periods=120, freq="MS")
    yoy = pd.Series(2.0 + 1.5 * np.sin(np.arange(120) / 12 * 2 * np.pi), index=idx)  # 0.5..3.5%
    lvl = be.level_from_yoy(yoy)
    assert not lvl.empty and lvl.is_monotonic_increasing
    mom = np.log(lvl).diff().dropna()
    assert mom.abs().max() < 0.02  # <2%/month — smooth, no ±20pp reconstruction blowup


def test_compute_from_levels_generic():
    """The generalized entry works on arbitrary level dicts (the path China reuses)."""
    idx = pd.date_range("2010-01-01", periods=180, freq="MS")
    lvl = pd.Series(100 * (1.002 ** np.arange(180)), index=idx)
    out = be.compute_from_levels({"g": (lvl, True)}, {"i": (lvl, True)})
    assert out is not None and "growth" in out and "inflation" in out
    assert out["revised"] is True


def test_grading_row_contract():
    """The forward-grading row must carry the two q1 signs + realized placeholders (null now)."""
    res = {"growth": {"q1": -1, "forcing_intensity": 1.0},
           "inflation": {"q1": 1, "forcing_intensity": 0.4}, "revised": True}
    row = be.grading_row(res, "2026-06-29")
    assert row["asof"] == "2026-06-29"
    assert row["be_growth_2d_q1"] == -1 and row["be_infl_2d_q1"] == 1
    assert row["realized_growth_2d_at_63d"] is None and row["realized_infl_2d_at_63d"] is None
    assert row["revised"] is True
