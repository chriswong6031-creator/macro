"""Regression tests for the _apply_liquidity NaN.ge() bug.

On float64, NaN.ge(threshold) returns False (not NA), so the old
`fillna(True)` was a no-op — null-adv rows were silently excluded
instead of passing with liq_unknown=True (spec §3).

Fix: `adv.isna() | adv.ge(_LIQ_ADV_MIN)`.

Run:
    python -m pytest tests/test_pick_lab_liquidity.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pick_lab.candidates import _apply_liquidity


# ---------------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------------- #

def _make_snap(**overrides) -> pd.DataFrame:
    """One-row snapshot with explicit float64 columns; overrides applied per column."""
    base = {
        "close": np.float64(50.0),
        "dollar_adv_20d": np.float64(50e6),
    }
    base.update(overrides)
    df = pd.DataFrame([base], index=["TEST"])
    # Ensure float64 dtype for the columns that matter for the regression pin.
    for col in ("close", "dollar_adv_20d"):
        if col in df.columns:
            df[col] = df[col].astype("float64")
    return df


# ---------------------------------------------------------------------------- #
# The four cases required by the task brief
# ---------------------------------------------------------------------------- #

class TestLiquidityGate:

    def test_null_adv_passes_with_liq_unknown(self):
        """(a) null dollar_adv_20d → row PASSES the filter; liq_unknown=True.

        Regression pin: on float64, NaN.ge(10e6) returns False.  The old
        fillna(True) was a no-op on a non-NA boolean, so null-adv rows were
        wrongly excluded.  The fix uses adv.isna() | adv.ge(...).
        """
        snap = _make_snap(dollar_adv_20d=np.float64("nan"))
        # Confirm dtype is float64 so the regression is actually exercised.
        assert snap["dollar_adv_20d"].dtype == np.float64

        result = _apply_liquidity(snap)
        assert len(result) == 1, "null-adv row must survive the liquidity filter"
        assert bool(result.at["TEST", "liq_unknown"]) is True

    def test_adv_below_threshold_excluded(self):
        """(b) dollar_adv_20d < 10M → row is excluded."""
        snap = _make_snap(dollar_adv_20d=np.float64(5e6))
        result = _apply_liquidity(snap)
        assert len(result) == 0, "sub-threshold adv row must be excluded"

    def test_adv_above_threshold_passes_not_unknown(self):
        """(c) dollar_adv_20d >= 10M → row passes; liq_unknown=False."""
        snap = _make_snap(dollar_adv_20d=np.float64(15e6))
        result = _apply_liquidity(snap)
        assert len(result) == 1, "above-threshold adv row must pass the filter"
        assert bool(result.at["TEST", "liq_unknown"]) is False

    def test_close_below_5_with_null_adv_excluded(self):
        """(d) close < 5 with null adv → excluded (close gate fires first)."""
        snap = _make_snap(close=np.float64(3.0), dollar_adv_20d=np.float64("nan"))
        assert snap["close"].dtype == np.float64
        result = _apply_liquidity(snap)
        assert len(result) == 0, "penny stock must be excluded even with null adv"


# ---------------------------------------------------------------------------- #
# Boundary / edge cases
# ---------------------------------------------------------------------------- #

class TestLiquidityBoundary:

    def test_adv_exactly_at_threshold_passes(self):
        """dollar_adv_20d == 10M exactly passes (ge is >=)."""
        snap = _make_snap(dollar_adv_20d=np.float64(10e6))
        result = _apply_liquidity(snap)
        assert len(result) == 1

    def test_close_exactly_at_5_passes(self):
        """close == 5.0 exactly passes (ge is >=)."""
        snap = _make_snap(close=np.float64(5.0), dollar_adv_20d=np.float64(20e6))
        result = _apply_liquidity(snap)
        assert len(result) == 1

    def test_liq_unknown_false_for_known_adv(self):
        """liq_unknown is False when dollar_adv_20d is not null."""
        snap = _make_snap(dollar_adv_20d=np.float64(50e6))
        result = _apply_liquidity(snap)
        assert bool(result.at["TEST", "liq_unknown"]) is False

    def test_missing_adv_column_all_pass_unknown(self):
        """When dollar_adv_20d column is absent entirely, all rows pass with liq_unknown=True."""
        df = pd.DataFrame([{"close": np.float64(50.0)}], index=["X"])
        result = _apply_liquidity(df)
        assert len(result) == 1
        assert bool(result.at["X", "liq_unknown"]) is True

    def test_multiple_rows_mixed(self):
        """Multi-row frame: null-adv passes, low-adv excluded, high-adv passes."""
        df = pd.DataFrame(
            {
                "close": pd.array([50.0, 50.0, 50.0], dtype="float64"),
                "dollar_adv_20d": pd.array([np.nan, 5e6, 50e6], dtype="float64"),
            },
            index=["NULL_ADV", "LOW_ADV", "HIGH_ADV"],
        )
        result = _apply_liquidity(df)
        assert "NULL_ADV" in result.index, "null-adv row must pass"
        assert "LOW_ADV" not in result.index, "low-adv row must be excluded"
        assert "HIGH_ADV" in result.index, "high-adv row must pass"
        assert bool(result.at["NULL_ADV", "liq_unknown"]) is True
        assert bool(result.at["HIGH_ADV", "liq_unknown"]) is False
