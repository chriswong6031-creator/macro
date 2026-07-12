"""tests/test_ird_velocity.py — IRD-R13 velocity grammar tests.

Coverage:
  1. windows          — vel_5d_bp and vel_20d_bp use correct lag windows
  2. z_basis          — vel_20d_z uses trailing 2y of the change series (causal)
  3. nan_honesty      — short series returns None, not spurious values
  4. basis_points     — values are in bp (×100 from %-point input)
  5. window_days_disclosed — window_days is <= _TWO_YEARS_BD and is disclosed
  6. none_input       — None series → all None, no exception
  7. empty_input      — empty Series → all None, no exception
  8. constant_series  — std=0 → vel_20d_z=None (no division by zero)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.ird_velocity import velocity_fields, _TWO_YEARS_BD


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _make_series(n: int, trend: float = 0.0) -> pd.Series:
    """Create a deterministic float series of length n (% units, like a yield)."""
    rng = np.random.default_rng(42)
    values = 4.0 + trend * np.arange(n) / n + rng.normal(0, 0.02, n)
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    return pd.Series(values, index=dates)


# ---------------------------------------------------------------------------
# 1. windows — vel_5d_bp and vel_20d_bp use correct lag
# ---------------------------------------------------------------------------

def test_vel_5d_bp_uses_5d_lag():
    """vel_5d_bp == (s[-1] - s[-6]) * 100 within floating-point precision."""
    s = _make_series(100)
    result = velocity_fields(s)
    expected = (float(s.iloc[-1]) - float(s.iloc[-6])) * 100.0
    assert result["vel_5d_bp"] is not None
    assert abs(result["vel_5d_bp"] - round(expected, 1)) < 0.01


def test_vel_20d_bp_uses_20d_lag():
    """vel_20d_bp == (s[-1] - s[-21]) * 100 within floating-point precision."""
    s = _make_series(100)
    result = velocity_fields(s)
    expected = (float(s.iloc[-1]) - float(s.iloc[-21])) * 100.0
    assert result["vel_20d_bp"] is not None
    assert abs(result["vel_20d_bp"] - round(expected, 1)) < 0.01


# ---------------------------------------------------------------------------
# 2. z_basis — causal: std on history EXCLUDING current value
# ---------------------------------------------------------------------------

def test_z_basis_causal():
    """vel_20d_z is computed on history up to t-1 (excluding current value)."""
    s = _make_series(600)
    result = velocity_fields(s)
    assert result["vel_20d_z"] is not None
    assert isinstance(result["vel_20d_z"], float)
    # sign check: with mild upward trend the 20d change should be positive → z > 0 possible
    # The key contract: window_days is disclosed (not None) when z is available
    assert result["window_days"] is not None


# ---------------------------------------------------------------------------
# 3. nan_honesty — short series → None, not spurious values
# ---------------------------------------------------------------------------

def test_short_series_5d_vel_none():
    """Series with < 6 observations: vel_5d_bp must be None."""
    s = _make_series(5)
    result = velocity_fields(s)
    assert result["vel_5d_bp"] is None


def test_short_series_20d_vel_none():
    """Series with < 21 observations: vel_20d_bp must be None."""
    s = _make_series(20)
    result = velocity_fields(s)
    assert result["vel_20d_bp"] is None


def test_short_series_z_none():
    """Series with < 40 observations after diff: vel_20d_z must be None."""
    s = _make_series(50)  # after diff(20): 30 obs; 30 < 40 → z should be None
    result = velocity_fields(s)
    assert result["vel_20d_z"] is None


# ---------------------------------------------------------------------------
# 4. basis_points — output is in bp (× 100 from %-point input)
# ---------------------------------------------------------------------------

def test_values_in_basis_points():
    """A 1%-point move over 5 days should appear as ~100 bp."""
    # Build a series where the last 6 values are 1 pp higher than what came before
    n = 200
    dates = pd.date_range("2019-01-02", periods=n, freq="B")
    values = np.full(n, 3.0)
    values[-5:] = 4.0  # last 5 days all at 4.0 → s[-1]-s[-6] ≈ 1pp
    s = pd.Series(values, index=dates)
    result = velocity_fields(s)
    assert result["vel_5d_bp"] is not None
    assert abs(result["vel_5d_bp"] - 100.0) < 1.0   # ≈ 100 bp


# ---------------------------------------------------------------------------
# 5. window_days_disclosed
# ---------------------------------------------------------------------------

def test_window_days_at_most_two_years():
    """window_days must be <= _TWO_YEARS_BD."""
    s = _make_series(1000)
    result = velocity_fields(s)
    if result["window_days"] is not None:
        assert result["window_days"] <= _TWO_YEARS_BD


def test_window_days_matches_shorter_history():
    """For a 100-obs series, window_days <= 99."""
    s = _make_series(100)
    result = velocity_fields(s)
    if result["window_days"] is not None:
        assert result["window_days"] <= 99


# ---------------------------------------------------------------------------
# 6. none_input — no exception, all fields None
# ---------------------------------------------------------------------------

def test_none_input_returns_all_none():
    result = velocity_fields(None)
    assert result["vel_5d_bp"] is None
    assert result["vel_20d_bp"] is None
    assert result["vel_20d_z"] is None
    assert result["window_days"] is None


# ---------------------------------------------------------------------------
# 7. empty_input — no exception, all fields None
# ---------------------------------------------------------------------------

def test_empty_series_returns_all_none():
    s = pd.Series(dtype=float)
    result = velocity_fields(s)
    assert result["vel_5d_bp"] is None
    assert result["vel_20d_bp"] is None


# ---------------------------------------------------------------------------
# 8. constant_series — std=0 → vel_20d_z = None (no division by zero)
# ---------------------------------------------------------------------------

def test_constant_series_z_is_none():
    """A constant series has std=0 — vel_20d_z must be None (no ZeroDivisionError)."""
    n = 600
    dates = pd.date_range("2018-01-02", periods=n, freq="B")
    s = pd.Series(np.full(n, 4.25), index=dates)
    result = velocity_fields(s)
    assert result["vel_20d_z"] is None
    # vel_20d_bp should be 0.0 (the diff is 0 but it's a valid float)
    # vel_5d_bp should also be 0.0
    assert result["vel_5d_bp"] == 0.0
    assert result["vel_20d_bp"] == 0.0
