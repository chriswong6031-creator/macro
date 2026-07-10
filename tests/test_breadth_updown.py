"""Tests for compute_updown (collectors/breadth.py) — W2 accruing up/down store.

All tests use synthetic frames; no network, no disk (updown.parquet absent).
Covers:
- correct up_vol / down_vol / up_pts / down_pts aggregation
- n_reporting floor (< 300 rows dropped)
- combine_first no-regress semantics (newer data appended, older never mutated)
- empty / missing volume input returns empty DataFrame, never raises
- flat days (dpx == 0) are correctly excluded from both up and down buckets
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import compute_updown  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _closes(data: dict[str, list[float]], dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(data, index=dates, dtype=float)


def _volume(data: dict[str, list[float]], dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(data, index=dates, dtype=float)


DATES_10 = pd.bdate_range("2025-01-02", periods=10)

# 500 dummy tickers with known up/down split to satisfy n_reporting >= 300
def _large_panel(n: int = 500, periods: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns closes and volume DataFrames with n tickers and a known structure.

    First half of tickers (n//2): close goes UP each day (dpx > 0 for all rows >= 1).
    Second half: close goes DOWN each day (dpx < 0 for all rows >= 1).
    All volumes = 1.0 per ticker.
    """
    dates = pd.bdate_range("2025-01-02", periods=periods)
    cols = [f"T{i:04d}" for i in range(n)]
    half = n // 2
    up_cols = cols[:half]
    dn_cols = cols[half:]
    # Price: starts at 100; up-tickers gain 1/day, down-tickers lose 1/day
    closes_data = {}
    for c in up_cols:
        closes_data[c] = [100.0 + d for d in range(periods)]
    for c in dn_cols:
        closes_data[c] = [100.0 - d for d in range(periods)]
    closes_df = pd.DataFrame(closes_data, index=dates, dtype=float)
    volume_df = pd.DataFrame(
        {c: [1.0] * periods for c in cols}, index=dates, dtype=float
    )
    return closes_df, volume_df


# ---------------------------------------------------------------------------
# Core aggregation tests
# ---------------------------------------------------------------------------

class TestComputeUpdown:

    def test_known_up_down_split(self):
        """With 250 up-tickers and 250 down-tickers (each vol=1), we can verify
        up_vol, down_vol, up_pts, down_pts exactly."""
        closes, volume = _large_panel(n=500, periods=3)
        result = compute_updown(closes, volume)
        # Row 0 (first date) has no prior close → dpx is NaN → dropped.
        # Rows 1 and 2 should appear (500 members with both dpx and volume).
        assert len(result) == 2, f"Expected 2 qualifying rows, got {len(result)}"

        for _, row in result.iterrows():
            assert row["n_reporting"] == 500
            # 250 up-tickers each with volume=1
            assert row["up_vol"] == pytest.approx(250.0)
            # 250 down-tickers each with volume=1
            assert row["down_vol"] == pytest.approx(250.0)
            # Each up-ticker gains exactly 1.0 per day → up_pts = 250 * 1.0
            assert row["up_pts"] == pytest.approx(250.0)
            # Each down-ticker loses exactly 1.0 per day → down_pts = 250 * 1.0
            assert row["down_pts"] == pytest.approx(250.0)

    def test_flat_days_excluded(self):
        """Tickers with dpx == 0 contribute to neither up nor down buckets."""
        dates = pd.bdate_range("2025-01-02", periods=3)
        # 300 flat + 100 up + 100 down = 500 total for n_reporting gate
        n_flat, n_up, n_dn = 300, 100, 100
        data_c = {}
        data_v = {}
        for i in range(n_flat):
            data_c[f"F{i}"] = [100.0, 100.0, 100.0]
            data_v[f"F{i}"] = [10.0, 10.0, 10.0]
        for i in range(n_up):
            data_c[f"U{i}"] = [100.0, 101.0, 102.0]
            data_v[f"U{i}"] = [2.0, 2.0, 2.0]
        for i in range(n_dn):
            data_c[f"D{i}"] = [100.0, 99.0, 98.0]
            data_v[f"D{i}"] = [3.0, 3.0, 3.0]
        closes = pd.DataFrame(data_c, index=dates, dtype=float)
        volume = pd.DataFrame(data_v, index=dates, dtype=float)
        result = compute_updown(closes, volume)
        assert not result.empty
        row = result.iloc[0]  # row at dates[1]
        # flat tickers have dpx=0 → neither up_vol nor down_vol
        assert row["up_vol"] == pytest.approx(100 * 2.0)
        assert row["down_vol"] == pytest.approx(100 * 3.0)
        assert row["up_pts"] == pytest.approx(100 * 1.0)
        assert row["down_pts"] == pytest.approx(100 * 1.0)
        # flat tickers still count toward n_reporting (they have both dpx and volume, even if dpx==0)
        assert row["n_reporting"] == 500

    def test_n_reporting_floor_drops_sparse_rows(self):
        """Rows with < 300 members reporting are dropped."""
        dates = pd.bdate_range("2025-01-02", periods=3)
        # Only 10 tickers: well below the 300 floor
        n = 10
        data_c = {f"T{i}": [100.0, 101.0, 102.0] for i in range(n)}
        data_v = {f"T{i}": [1.0, 1.0, 1.0] for i in range(n)}
        closes = pd.DataFrame(data_c, index=dates, dtype=float)
        volume = pd.DataFrame(data_v, index=dates, dtype=float)
        result = compute_updown(closes, volume)
        assert result.empty, "Expected empty result when n_reporting < 300"

    def test_missing_volume_for_some_tickers_excluded(self):
        """Tickers with NaN volume are not included in n_reporting or aggregates."""
        dates = pd.bdate_range("2025-01-02", periods=3)
        # 500 tickers, but only 250 have valid volume; 250 have NaN volume
        closes_data = {f"T{i}": [100.0 + d for d in range(3)] for i in range(500)}
        volume_data = {}
        for i in range(250):
            volume_data[f"T{i}"] = [1.0, 1.0, 1.0]
        for i in range(250, 500):
            volume_data[f"T{i}"] = [np.nan, np.nan, np.nan]
        closes = pd.DataFrame(closes_data, index=dates, dtype=float)
        volume = pd.DataFrame(volume_data, index=dates, dtype=float)
        result = compute_updown(closes, volume)
        # 250 valid → >= 300 check fails → empty
        assert result.empty, (
            "Expected empty when only 250 tickers have volume (below n_reporting=300 floor)"
        )

    def test_first_row_no_dpx_excluded(self):
        """The very first date has no prior close → dpx is all NaN → dropped."""
        closes, volume = _large_panel(n=500, periods=5)
        result = compute_updown(closes, volume)
        # 5 periods → 4 diff rows; all 4 should qualify (500 members)
        assert len(result) == 4
        assert result.index[0] == closes.index[1]


# ---------------------------------------------------------------------------
# Empty / edge-input robustness
# ---------------------------------------------------------------------------

class TestComputeUpdownEdgeCases:

    def test_empty_closes_returns_empty(self):
        empty = pd.DataFrame()
        result = compute_updown(empty, empty)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_none_closes_returns_empty(self):
        result = compute_updown(None, None)  # type: ignore[arg-type]
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_none_volume_returns_empty(self):
        dates = pd.bdate_range("2025-01-02", periods=3)
        closes = pd.DataFrame({"A": [1.0, 2.0, 3.0]}, index=dates)
        result = compute_updown(closes, None)  # type: ignore[arg-type]
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_single_ticker_never_raises(self):
        """Single-ticker panel: n_reporting = 1 < 300 → empty, no exception."""
        dates = pd.bdate_range("2025-01-02", periods=5)
        closes = pd.DataFrame({"SPY": [400.0, 401.0, 402.0, 403.0, 404.0]}, index=dates)
        volume = pd.DataFrame({"SPY": [1e6, 1e6, 1e6, 1e6, 1e6]}, index=dates)
        result = compute_updown(closes, volume)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_all_nan_volume_returns_empty(self):
        closes, _ = _large_panel(n=500, periods=3)
        volume = pd.DataFrame(
            {c: [np.nan] * 3 for c in closes.columns},
            index=closes.index, dtype=float
        )
        result = compute_updown(closes, volume)
        assert result.empty

    def test_output_columns(self):
        """Output always has the expected columns, even when empty."""
        result = compute_updown(pd.DataFrame(), pd.DataFrame())
        for col in ["up_vol", "down_vol", "up_pts", "down_pts", "n_reporting"]:
            assert col in result.columns, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# combine_first no-regress semantics (append-only store contract)
# ---------------------------------------------------------------------------

class TestCombineFirstNoRegress:
    """Simulate the merge-append pattern used in BreadthAdapter.fetch() for updown.parquet.

    The contract: new rows win (combine_first), old history is NEVER shrunk or rewritten.
    """

    def _make_updown(self, start: str, periods: int, base_val: float) -> pd.DataFrame:
        """Synthetic updown frame with known values for identity checks."""
        dates = pd.bdate_range(start, periods=periods)
        n = 500  # enough to satisfy n_reporting >= 300
        closes = pd.DataFrame(
            {f"T{i}": [100.0 + d * (1 if i < 250 else -1) for d in range(periods)]
             for i in range(n)},
            index=dates, dtype=float
        )
        volume = pd.DataFrame(
            {f"T{i}": [base_val] * periods for i in range(n)},
            index=dates, dtype=float
        )
        return compute_updown(closes, volume)

    def test_append_new_rows_keeps_old(self):
        """Merging a newer batch via combine_first preserves old rows exactly."""
        old = self._make_updown("2025-01-02", periods=5, base_val=1.0)
        new = self._make_updown("2025-01-09", periods=5, base_val=2.0)
        merged = new.combine_first(old).sort_index()
        # All old rows must be present and unchanged
        for dt in old.index:
            assert dt in merged.index, f"Old row {dt} was lost after combine_first"
            assert merged.loc[dt, "up_vol"] == pytest.approx(old.loc[dt, "up_vol"]), (
                f"Old row {dt} up_vol was mutated"
            )
        # New rows must be present
        for dt in new.index:
            assert dt in merged.index, f"New row {dt} missing after combine_first"

    def test_history_never_shrinks(self):
        """Merged frame must contain exactly old_dates | new_dates, and old values must be
        byte-equal post-merge (so a buggy merge that silently mutates history fails)."""
        old = self._make_updown("2025-01-02", periods=10, base_val=1.0)
        new = self._make_updown("2025-01-13", periods=5, base_val=1.0)
        merged = new.combine_first(old).sort_index()
        expected_dates = old.index.union(new.index)
        # Exact row set
        assert set(merged.index) == set(expected_dates), (
            f"Merged index mismatch: expected {sorted(expected_dates)}, got {sorted(merged.index)}"
        )
        # Every old row's values must be byte-equal
        for dt in old.index:
            for col in ["up_vol", "down_vol", "up_pts", "down_pts", "n_reporting"]:
                orig = old.loc[dt, col]
                after = merged.loc[dt, col]
                assert after == pytest.approx(orig), (
                    f"Old row {dt} col {col} was mutated: {orig} -> {after}"
                )

    def test_overlap_new_wins(self):
        """On overlap dates, the new batch value takes precedence."""
        old = self._make_updown("2025-01-02", periods=5, base_val=1.0)
        # new covers same window with different volume → different up_vol
        new = self._make_updown("2025-01-02", periods=5, base_val=3.0)
        merged = new.combine_first(old).sort_index()
        # combine_first: new's non-NaN values win
        for dt in new.index:
            if dt in merged.index:
                assert merged.loc[dt, "up_vol"] == pytest.approx(new.loc[dt, "up_vol"]), (
                    f"On overlap date {dt}, old value was not overridden by new"
                )

    def test_no_regress_on_append_only(self):
        """Pure append (non-overlapping) must not modify any old row value."""
        old = self._make_updown("2025-01-02", periods=5, base_val=1.0)
        new_start = pd.bdate_range("2025-01-02", periods=5)[-1]
        # advance by one business day beyond old's last date
        next_start = (new_start + pd.tseries.offsets.BDay(1)).strftime("%Y-%m-%d")
        new = self._make_updown(next_start, periods=5, base_val=1.0)
        merged = new.combine_first(old).sort_index()
        # Confirm no old row was changed
        old_reindexed = old.reindex(merged.index)
        for dt in old.index:
            orig = old.loc[dt, "down_pts"]
            after = merged.loc[dt, "down_pts"]
            assert after == pytest.approx(orig), (
                f"Row {dt} down_pts changed from {orig} to {after}"
            )


class TestExtremedays:
    """Extreme (all-up / all-down) day handling — regression for MAJOR finding.

    On an all-down day min_count=1 previously left up_vol=NaN instead of 0.0,
    making down_vol/(up_vol+down_vol) evaluate to NaN on exactly the 90%-down
    days that Lowry/Desmond metrics exist to detect.  After the fillna(0.0) fix
    these must be 0.0, not NaN.
    """

    def _panel(self, n: int = 400) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return 2-row closes + volume where row 0 = flat (diff=NaN), row 1 = all-down."""
        dates = pd.bdate_range("2025-03-03", periods=2)
        closes = pd.DataFrame(
            {f"T{i}": [100.0, 99.0] for i in range(n)},  # all tickers fall on day 1
            index=dates, dtype=float,
        )
        volume = pd.DataFrame(
            {f"T{i}": [1_000_000.0, 1_000_000.0] for i in range(n)},
            index=dates, dtype=float,
        )
        return closes, volume

    def test_all_down_day_up_vol_is_zero_not_nan(self):
        """An all-down day must produce up_vol==0.0, not NaN."""
        closes, volume = self._panel()
        result = compute_updown(closes, volume)
        # day index 1 is the all-down day (day 0 is dropped because diff() gives NaN)
        assert len(result) == 1, f"Expected 1 row, got {len(result)}"
        row = result.iloc[0]
        assert row["up_vol"] == pytest.approx(0.0), (
            f"All-down day: up_vol={row['up_vol']!r}, expected 0.0 (not NaN)"
        )
        assert not np.isnan(row["up_vol"]), "up_vol is NaN on all-down day"
        assert row["down_vol"] > 0, "down_vol should be positive on all-down day"

    def test_all_up_day_down_vol_is_zero_not_nan(self):
        """An all-up day must produce down_vol==0.0, not NaN."""
        dates = pd.bdate_range("2025-03-03", periods=2)
        n = 400
        closes = pd.DataFrame(
            {f"T{i}": [100.0, 101.0] for i in range(n)},  # all tickers rise
            index=dates, dtype=float,
        )
        volume = pd.DataFrame(
            {f"T{i}": [1_000_000.0, 1_000_000.0] for i in range(n)},
            index=dates, dtype=float,
        )
        result = compute_updown(closes, volume)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["down_vol"] == pytest.approx(0.0), (
            f"All-up day: down_vol={row['down_vol']!r}, expected 0.0 (not NaN)"
        )
        assert not np.isnan(row["down_vol"]), "down_vol is NaN on all-up day"
        assert row["up_vol"] > 0, "up_vol should be positive on all-up day"

    def test_ratio_valid_on_extreme_day(self):
        """down_vol/(up_vol+down_vol) must be finite (0 or 1) on extreme days."""
        closes, volume = self._panel()
        result = compute_updown(closes, volume)
        row = result.iloc[0]
        ratio = row["down_vol"] / (row["up_vol"] + row["down_vol"])
        assert np.isfinite(ratio), f"Ratio is not finite: {ratio}"
        assert ratio == pytest.approx(1.0), f"All-down ratio should be 1.0, got {ratio}"
