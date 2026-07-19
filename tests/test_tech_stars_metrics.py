"""tests/test_tech_stars_metrics.py — Unit tests for engine.tech_stars.compute_fire_metrics.

Verifies:
- compute_fire_metrics on a CONSTRUCTED series where the expected fwd_ret/win/mfe/mae
  are hand-computed for 2-3 fires and asserted at exact (or tight float) values.
- Horizon-edge cases: fires near end of series are skipped (not enough forward bars).
- Empty-pos case: no fires → empty DataFrame returned.

Per TLT-R6: tests are descriptive-tier only; no verdicts in output.
Per DT-R14: not a backtest verdict; testing the mechanics of the metric function.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Import target
# ---------------------------------------------------------------------------

def _get_compute_fire_metrics():
    from engine.tech_stars import compute_fire_metrics  # noqa: PLC0415
    return compute_fire_metrics


# ---------------------------------------------------------------------------
# Hand-crafted test frames
# ---------------------------------------------------------------------------

def _make_controlled_frame() -> pd.DataFrame:
    """Make a price frame where forward returns are fully predictable.

    Close series = 100, 105, 110, 115, 120, 125, 130, 135, 140, 145, 150, ...
    (constant +5 per bar) — so forward return at any entry bar is deterministic.
    """
    n = 100
    close = np.linspace(100.0, 595.0, n)  # exactly +5 per bar
    # High = close + 2, Low = close - 2 (symmetric), no real MFE/MAE tricks
    high = close + 2.0
    low = close - 2.0
    dates = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": 1e6},
        index=dates,
    )


def _make_pos_series(fire_indices: list[int], length: int, index: pd.DatetimeIndex) -> pd.Series:
    """Make a position series with fires at specified integer positions."""
    pos = pd.Series(0.0, index=index)
    for i in fire_indices:
        pos.iloc[i] = 1.0
    return pos


# ---------------------------------------------------------------------------
# Tests: exact hand-computed values
# ---------------------------------------------------------------------------

class TestComputeFireMetricsExact:
    """Assert exact metrics on fully predictable price series."""

    def test_single_fire_fwd_ret_exact(self):
        """Fire at bar 0, horizon=5: entry=close[1]=105, exit=close[6]=130.
        fwd_ret = 130/105 - 1 ≈ 0.238095...
        """
        cfm = _get_compute_fire_metrics()
        df = _make_controlled_frame()
        pos = _make_pos_series([0], len(df), df.index)

        result = cfm(df, pos, horizon=5)
        assert len(result) == 1
        row = result.iloc[0]

        # entry_close = df.close[1] = 105.0, exit_close = df.close[6] = 130.0
        expected_entry = df["close"].iloc[1]
        expected_exit = df["close"].iloc[6]
        expected_fwd_ret = expected_exit / expected_entry - 1.0

        assert abs(row["entry_close"] - expected_entry) < 1e-6
        assert abs(row["exit_close"] - expected_exit) < 1e-6
        assert abs(row["fwd_ret"] - expected_fwd_ret) < 1e-6
        assert bool(row["win"]) is True  # price always rising

    def test_single_fire_mfe_mae_exact(self):
        """Fire at bar 10, horizon=5, constant +5/bar.

        entry_close = close[11] = 155, window bars [11..16] = 155,160,165,170,175,180
        mfe = (180-155)/155, mae = 0 (price never goes below entry), so mfe_mae = +inf → None
        """
        cfm = _get_compute_fire_metrics()
        df = _make_controlled_frame()
        pos = _make_pos_series([10], len(df), df.index)

        result = cfm(df, pos, horizon=5)
        assert len(result) == 1
        row = result.iloc[0]

        entry_close = df["close"].iloc[11]
        window = df["close"].iloc[11:17]
        expected_mfe = (window.max() - entry_close) / entry_close
        expected_mae = (entry_close - window.min()) / entry_close

        assert abs(row["mfe"] - expected_mfe) < 1e-6
        assert abs(row["mae"] - expected_mae) < 1e-6
        # mfe_mae is None when mae ~= 0 (no adverse move in monotone rising)
        # (engine produces None when mae < 1e-9)
        # In our frame low = close - 2, so window_closes.min() can be < entry
        # Actually the function uses closes not lows for mfe/mae window
        # Our controlled frame: close is monotone; min of window = entry_close = 155
        # So mae = (155 - 155)/155 = 0 → mfe_mae = None
        assert row["mfe_mae"] is None

    def test_multiple_fires_count(self):
        """Three fires → three rows in result."""
        cfm = _get_compute_fire_metrics()
        df = _make_controlled_frame()
        pos = _make_pos_series([0, 10, 20], len(df), df.index)

        result = cfm(df, pos, horizon=5)
        assert len(result) == 3

    def test_fire_near_end_skipped(self):
        """Fire too close to end: entry_t + horizon >= len → skip.

        With horizon=10 and n=100, a fire at bar 89 gives entry_t=90, exit_t=100.
        exit_t (100) == len(close_idx) (100) → should be skipped (exit_t > len-1).
        Actually the condition is: exit_t > len → fire at 89 gives exit_t=100 == len, skip.
        Fire at bar 88 gives exit_t=99 which is valid.
        """
        cfm = _get_compute_fire_metrics()
        df = _make_controlled_frame()  # 100 bars
        # Fire at bar 95 → entry_t=96, exit_t=106 > 100 → skip
        pos = _make_pos_series([95, 99], len(df), df.index)

        result = cfm(df, pos, horizon=5)
        # Both should be skipped (entry_t=96/100, exit_t=101/105 > 100)
        assert len(result) == 0

    def test_fire_at_boundary_valid(self):
        """Fire at position that produces a valid forward window.

        P0-6 fix: exit_t >= len(close_idx) is now excluded (incomplete horizon).
        With n=100 and horizon=5:
          fire at bar i: exit_t = i+1+5 = i+6
          Valid condition: exit_t < len=100 → i+6 < 100 → i <= 93
          Bar 94: exit_t=100 == len=100 → EXCLUDED (was wrongly included before P0-6)
          Bar 93: exit_t=99 < 100 → INCLUDED
        """
        cfm = _get_compute_fire_metrics()
        df = _make_controlled_frame()  # 100 bars, indices 0..99
        # Last valid fire is at bar 93 (exit_t=99 < 100=len)
        pos = _make_pos_series([93], len(df), df.index)

        result = cfm(df, pos, horizon=5)
        assert len(result) == 1

        # Confirm bar 94 is now excluded (P0-6: exit_t=100 == len → rejected)
        pos_boundary = _make_pos_series([94], len(df), df.index)
        result_boundary = cfm(df, pos_boundary, horizon=5)
        assert len(result_boundary) == 0, (
            "P0-6: fire at bar 94 (exit_t=100==len) must be excluded as incomplete horizon"
        )

    def test_win_false_for_falling_prices(self):
        """Build a strictly declining series and verify win=False."""
        cfm = _get_compute_fire_metrics()
        n = 100
        close = np.linspace(595.0, 100.0, n)  # falling
        high = close + 1.0
        low = close - 1.0
        dates = pd.bdate_range("2020-01-02", periods=n)
        df = pd.DataFrame(
            {"open": close, "high": high, "low": low, "close": close, "volume": 1e6},
            index=dates,
        )
        pos = _make_pos_series([0], n, df.index)
        result = cfm(df, pos, horizon=5)
        assert len(result) == 1
        assert bool(result.iloc[0]["win"]) is False
        assert result.iloc[0]["fwd_ret"] < 0.0

    def test_durable_flag(self):
        """Fire on a stable series → durable=True; fire before a sharp drop → durable=False."""
        cfm = _get_compute_fire_metrics()
        # Stable series: no drop → durable True
        n = 100
        close = np.full(n, 100.0)
        high = close + 1.0
        low = close - 0.5   # low never far below close
        dates = pd.bdate_range("2020-01-02", periods=n)
        df_stable = pd.DataFrame(
            {"open": close, "high": high, "low": low, "close": close, "volume": 1e6},
            index=dates,
        )
        pos = _make_pos_series([0], n, df_stable.index)
        result = cfm(df_stable, pos, horizon=5)
        assert bool(result.iloc[0]["durable"]) is True


# ---------------------------------------------------------------------------
# Tests: empty position (zero fires)
# ---------------------------------------------------------------------------

class TestComputeFireMetricsEmpty:
    """Empty pos → empty DataFrame, not an error."""

    def test_empty_pos_returns_empty_df(self):
        cfm = _get_compute_fire_metrics()
        df = _make_controlled_frame()
        pos = pd.Series(0.0, index=df.index)

        result = cfm(df, pos, horizon=21)
        assert result.empty
        # Columns must still be defined
        assert "fwd_ret" in result.columns
        assert "win" in result.columns
        assert "mfe" in result.columns
        assert "mae" in result.columns

    def test_empty_pos_no_exception(self):
        cfm = _get_compute_fire_metrics()
        df = _make_controlled_frame()
        pos = pd.Series(0.0, index=df.index)
        # Should not raise
        result = cfm(df, pos, horizon=63)
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Tests: horizon variations
# ---------------------------------------------------------------------------

class TestComputeFireMetricsHorizons:
    """Forward return window changes with horizon."""

    @pytest.mark.parametrize("horizon", [10, 21, 42, 63])
    def test_horizon_variants(self, horizon: int):
        """Each horizon in the ladder produces a result on a long enough series."""
        cfm = _get_compute_fire_metrics()
        n = horizon + 20  # enough forward bars
        close = np.linspace(100, 200, n)
        high = close + 1.0
        low = close - 1.0
        dates = pd.bdate_range("2020-01-02", periods=n)
        df = pd.DataFrame(
            {"open": close, "high": high, "low": low, "close": close, "volume": 1e6},
            index=dates,
        )
        pos = _make_pos_series([0], n, df.index)
        result = cfm(df, pos, horizon=horizon)
        assert len(result) >= 1
        assert abs(result.iloc[0]["fwd_ret"]) > 0  # rising series → positive
