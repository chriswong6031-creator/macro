"""
Tests for MRI PR-E: Release Playbook v1

Covers:
1. Surprise standardization is PIT (uses only prior events)
2. Bucket edge correctness at ±0.5σ
3. Event-date alignment to next trading session when release falls on non-trading day
4. Bootstrap determinism (seed=7 reproduces)
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import helpers from the playbook script
# ---------------------------------------------------------------------------
PLAYBOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / "research" / "release_playbook" / "run_release_playbook.py"
)

# Load the module without executing __main__
import importlib.util

spec = importlib.util.spec_from_file_location("run_release_playbook", PLAYBOOK_PATH)
rp = importlib.util.module_from_spec(spec)
# Prevent the if __name__ == '__main__' block from running during import
spec.loader.exec_module(rp)


# ---------------------------------------------------------------------------
# 1. Surprise standardization is PIT
# ---------------------------------------------------------------------------

class TestSurprisePIT:
    """Verify that trailing_sigma at event t uses ONLY prior t events.

    Data note: realized_surprise is NaN for indices 0 and 1 because:
      - mom[0] = NaN (no prior period for diff)
      - naive_prior[1] = shift(1) of mom[0] = NaN
    So the first event with 24 non-NaN prior surprises is index 26
    (surprises are non-NaN from index 2 onward; need 24 of them => index 26).
    Tests that check sigma correctness use index 30+ to be safely in-range.
    """

    def _make_prints(self, n: int) -> pd.DataFrame:
        """Synthetic initial prints with varying MoM (non-constant to get nonzero sigma)."""
        rng = np.random.default_rng(42)
        periods = pd.date_range("2000-01-01", periods=n, freq="MS")
        release_dates = periods + pd.Timedelta(days=14)
        # Use cumsum of non-zero increments so MoM varies
        increments = rng.normal(0.2, 0.05, n)
        values = np.cumsum(increments)
        df = pd.DataFrame({
            "period": periods,
            "release_date": release_dates,
            "initial_value": values,
        })
        df = rp.compute_mom(df)
        df = rp.compute_surprises(df)
        return df

    def test_first_sigma_index_26_is_non_nan(self) -> None:
        """Index 26 is the first event with 24 valid prior surprises (non-NaN).
        (Indices 0-1 have NaN realized_surprise; surprises begin at index 2.)
        """
        df = self._make_prints(50)
        assert not np.isnan(df["trailing_sigma"].iloc[26]), (
            f"Expected non-NaN sigma at index 26, got {df['trailing_sigma'].iloc[26]}"
        )

    def test_index_25_has_nan_sigma(self) -> None:
        """Index 25 has only 23 valid prior surprises (indices 2-24) — still warm-up."""
        df = self._make_prints(50)
        assert np.isnan(df["trailing_sigma"].iloc[25]), (
            f"Index 25 should still be NaN (23 prior valid surprises < 24)"
        )

    def test_warmup_events_have_nan_sigma(self) -> None:
        """Indices 0-25 must have NaN trailing_sigma (fewer than 24 valid prior surprises)."""
        df = self._make_prints(50)
        for i in range(26):
            assert np.isnan(df["trailing_sigma"].iloc[i]), (
                f"Event {i} should have NaN sigma (warm-up), got {df['trailing_sigma'].iloc[i]}"
            )

    def test_sigma_does_not_use_future_events(self) -> None:
        """Sigma at event t = std(realized_surprise[t-24:t], ddof=1), no look-ahead."""
        df = self._make_prints(55)
        # Check only events where sigma is expected to be non-NaN (index 26+)
        for i in range(26, len(df)):
            window = df["realized_surprise"].iloc[i - 24: i].values
            # The window must be all non-NaN at this point (indices 2+ have surprises)
            if np.any(np.isnan(window)):
                continue  # skip edge cases near the NaN boundary
            expected_sigma = float(np.std(window, ddof=1))
            actual_sigma = float(df["trailing_sigma"].iloc[i])
            assert abs(actual_sigma - expected_sigma) < 1e-10, (
                f"At event {i}: expected sigma {expected_sigma:.6f}, got {actual_sigma:.6f}"
            )

    def test_std_surprise_excludes_current_event(self) -> None:
        """Sigma at event t excludes realized_surprise[t] — PIT compliance."""
        df = self._make_prints(55)
        i = 30  # safely past warmup with all non-NaN window
        window_excl = df["realized_surprise"].iloc[i - 24: i].values
        sigma_excl = float(np.std(window_excl, ddof=1))
        window_incl = df["realized_surprise"].iloc[i - 23: i + 1].values
        sigma_incl = float(np.std(window_incl, ddof=1))
        actual_sigma = float(df["trailing_sigma"].iloc[i])
        assert abs(actual_sigma - sigma_excl) < 1e-10, (
            f"Sigma at {i} should match excluding-current: {sigma_excl:.6f}, got {actual_sigma:.6f}"
        )
        # Non-vacuity: with the synthetic random data the excluding and
        # including windows must genuinely differ, otherwise the PIT
        # assertion above proves nothing.
        assert sigma_excl != sigma_incl


# ---------------------------------------------------------------------------
# 2. Bucket edge correctness
# ---------------------------------------------------------------------------

class TestBucketEdges:
    """Verify bucket assignment at and around ±0.5σ thresholds."""

    def test_hot_above_threshold(self) -> None:
        assert rp.assign_bucket(0.51) == "hot"

    def test_cold_below_threshold(self) -> None:
        assert rp.assign_bucket(-0.51) == "cold"

    def test_inline_exactly_at_positive_threshold(self) -> None:
        assert rp.assign_bucket(0.5) == "inline"

    def test_inline_exactly_at_negative_threshold(self) -> None:
        assert rp.assign_bucket(-0.5) == "inline"

    def test_inline_zero(self) -> None:
        assert rp.assign_bucket(0.0) == "inline"

    def test_hot_just_above(self) -> None:
        assert rp.assign_bucket(0.500001) == "hot"

    def test_cold_just_below(self) -> None:
        assert rp.assign_bucket(-0.500001) == "cold"

    def test_nan_returns_none(self) -> None:
        assert rp.assign_bucket(float("nan")) is None

    def test_large_positive(self) -> None:
        assert rp.assign_bucket(3.0) == "hot"

    def test_large_negative(self) -> None:
        assert rp.assign_bucket(-3.0) == "cold"


# ---------------------------------------------------------------------------
# 3. Event-date alignment to next trading session
# ---------------------------------------------------------------------------

class TestHolidayAlignment:
    """If release date is not a trading day, align_to_trading_day returns next."""

    def _make_trading_days(self) -> pd.DatetimeIndex:
        """Simple Mon-Fri trading days (no holidays for simplicity)."""
        dates = pd.bdate_range("2020-01-01", "2020-12-31")
        return pd.DatetimeIndex(dates)

    def test_release_on_trading_day_is_unchanged(self) -> None:
        trading_days = self._make_trading_days()
        # 2020-01-02 is a Thursday (trading day)
        date = pd.Timestamp("2020-01-02")
        result = rp.align_to_trading_day(date, trading_days)
        assert result == date

    def test_release_on_weekend_advances_to_monday(self) -> None:
        trading_days = self._make_trading_days()
        # 2020-01-04 is a Saturday
        saturday = pd.Timestamp("2020-01-04")
        monday = pd.Timestamp("2020-01-06")
        result = rp.align_to_trading_day(saturday, trading_days)
        assert result == monday

    def test_release_on_sunday_advances_to_monday(self) -> None:
        trading_days = self._make_trading_days()
        sunday = pd.Timestamp("2020-01-05")
        monday = pd.Timestamp("2020-01-06")
        result = rp.align_to_trading_day(sunday, trading_days)
        assert result == monday

    def test_release_after_last_trading_day_returns_none(self) -> None:
        trading_days = self._make_trading_days()
        future_date = pd.Timestamp("2025-01-01")
        result = rp.align_to_trading_day(future_date, trading_days)
        assert result is None

    def test_get_session_close_h0_is_event_day(self) -> None:
        trading_days = self._make_trading_days()
        event_day = pd.Timestamp("2020-01-02")  # Thursday
        result = rp.get_session_close(event_day, 0, trading_days)
        assert result == event_day

    def test_get_session_close_h1(self) -> None:
        trading_days = self._make_trading_days()
        event_day = pd.Timestamp("2020-01-02")  # Thursday
        result = rp.get_session_close(event_day, 1, trading_days)
        assert result == pd.Timestamp("2020-01-03")  # Friday

    def test_get_session_close_skips_weekend(self) -> None:
        trading_days = self._make_trading_days()
        event_day = pd.Timestamp("2020-01-03")  # Friday
        # h1 should be Monday 2020-01-06
        result = rp.get_session_close(event_day, 1, trading_days)
        assert result == pd.Timestamp("2020-01-06")

    def test_event_day_not_in_trading_days_returns_none(self) -> None:
        trading_days = self._make_trading_days()
        # Saturday is not a trading day; get_session_close requires it to be
        result = rp.get_session_close(pd.Timestamp("2020-01-04"), 1, trading_days)
        assert result is None


# ---------------------------------------------------------------------------
# 4. Bootstrap determinism
# ---------------------------------------------------------------------------

class TestBootstrapDeterminism:
    """Seed=7 must reproduce the same CI on repeated calls."""

    def test_same_seed_same_result(self) -> None:
        values = np.array([1.0, 2.0, 3.0, -1.0, 0.5, 2.5, -0.5, 1.5])
        ci1 = rp.bootstrap_ci(values, n_draws=800, seed=7)
        ci2 = rp.bootstrap_ci(values, n_draws=800, seed=7)
        assert ci1 == ci2, f"Same seed gave different results: {ci1} vs {ci2}"

    def test_different_seed_different_result(self) -> None:
        """Different seeds should (with overwhelming probability) give different results."""
        values = np.array([1.0, 2.0, 3.0, -1.0, 0.5, 2.5, -0.5, 1.5, 0.0, 4.0])
        ci_7 = rp.bootstrap_ci(values, n_draws=800, seed=7)
        ci_42 = rp.bootstrap_ci(values, n_draws=800, seed=42)
        # They should differ (probability of being identical is astronomically low)
        assert ci_7 != ci_42

    def test_single_value_returns_value_as_ci(self) -> None:
        values = np.array([5.0])
        lo, hi = rp.bootstrap_ci(values, n_draws=800, seed=7)
        assert lo == 5.0
        assert hi == 5.0

    def test_empty_values_returns_nan(self) -> None:
        values = np.array([])
        lo, hi = rp.bootstrap_ci(values, n_draws=800, seed=7)
        assert np.isnan(lo)
        assert np.isnan(hi)

    def test_ci_bounds_ordered(self) -> None:
        """lo must be <= hi."""
        rng = np.random.default_rng(99)
        values = rng.standard_normal(50)
        lo, hi = rp.bootstrap_ci(values, n_draws=800, seed=7)
        assert lo <= hi

    def test_same_seed_reproduces(self) -> None:
        """Same values, seed, and draw count must reproduce the CI exactly."""
        values = np.array([1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 1.5, -1.5, 0.1, -0.1])
        ci_a = rp.bootstrap_ci(values, n_draws=800, seed=7)
        ci_b = rp.bootstrap_ci(values, n_draws=800, seed=7)
        assert ci_a == ci_b


# ---------------------------------------------------------------------------
# 5. Integration sanity: results file was produced (if available)
# ---------------------------------------------------------------------------

class TestResultsFileProduced:
    """If the results JSON was produced, spot-check its schema."""

    def test_json_schema(self) -> None:
        results_path = (
            Path(__file__).resolve().parents[1]
            / "research" / "release_playbook" / "results" / "playbook_v1.json"
        )
        if not results_path.exists():
            pytest.skip("playbook_v1.json not yet produced; run run_release_playbook.py first")

        import json
        with open(results_path) as f:
            records = json.load(f)

        assert isinstance(records, list), "Root must be a JSON array"
        assert len(records) > 0, "Expected at least one cell record"

        required_keys = {"release", "bucket", "outcome", "horizon", "era", "n", "mean", "median", "ci_lo", "ci_hi"}
        for rec in records[:10]:
            assert required_keys.issubset(rec.keys()), f"Missing keys in record: {rec}"
            assert rec["release"] in ("cpi", "nfp")
            assert rec["bucket"] in ("hot", "inline", "cold")
            assert rec["outcome"] in ("dgs10_bp", "t10y2y_bp", "dollar_pct", "spy_pct")
            assert rec["horizon"] in ("h0", "h1", "h5", "h21")
            assert isinstance(rec["n"], int) and rec["n"] >= 8  # MIN_N enforced
            assert rec["ci_lo"] <= rec["ci_hi"], "CI bounds must be ordered"
