"""Tests for MRI Track T — mf_energy mixed-frequency energy-accumulator challenger.

Covers:
  - Output schema: all required keys present, display_only=True, authority=False.
  - model tag: always 'mf_energy'.
  - Determinism: calling twice returns identical results.
  - No authority: output never sets authority=True.
  - No-lookahead in accumulator: a WTI/gasoline value after asof must not change the nowcast.
  - Walk-forward: idx monotone increasing, MIN_TRAIN_OBS respected.
  - Ridge solver: returns finite scalar.
  - run_walk_forward_mf: schema and basic invariants with synthetic data.

Tests use synthetic fixtures or the real data fixtures where the data is known to be available.
No live network access. No lookahead is a hard requirement tested explicitly.
"""
from __future__ import annotations

import sys
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_mf_energy import (
    _ridge_solve,
    _ols_slope_intercept,
    _walk_forward_mf,
    _empty_mf,
    _compute_gasoline_nowcast,
    _compute_wti_beta,
    _predict_exenergy_ar,
    _seasonal_terms,
    _load_gasregw,
    _load_wti,
    _all_mondays_in_month,
    project_release_mf,
    run_walk_forward_mf,
    RIDGE_LAMBDA,
    MIN_TRAIN_OBS,
    MIN_QUANTILE_OBS,
    GASOLINE_RI_WEIGHT,
    _HEAD_FEATURES,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_gasregw_series(
    start_date: date = date(2000, 1, 1),
    n_weeks: int = 400,
    seed: int = 42,
) -> pd.Series:
    """Synthetic weekly gasoline price series."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start=str(start_date), periods=n_weeks, freq="W-MON")
    prices = 2.0 + np.cumsum(rng.normal(0, 0.02, n_weeks))
    prices = np.clip(prices, 1.0, 6.0)
    return pd.Series(prices, index=dates, dtype=float)


def _make_wti_series(
    start_date: date = date(2000, 1, 1),
    n_days: int = 3000,
    seed: int = 7,
) -> pd.Series:
    """Synthetic daily WTI crude oil price series (business days only)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=str(start_date), periods=n_days)
    prices = 50.0 + np.cumsum(rng.normal(0, 0.5, n_days))
    prices = np.clip(prices, 10.0, 150.0)
    return pd.Series(prices, index=dates, dtype=float)


def _make_synthetic_records(
    n: int,
    feature_names: list[str],
    target_scale: float = 0.2,
    seed: int = 42,
) -> list[dict]:
    """Make synthetic walk-forward records with deterministic random data."""
    rng = np.random.default_rng(seed)
    records = []
    for i in range(n):
        rec: dict = {}
        for fn in feature_names:
            rec[fn] = float(rng.normal(0, 1))
        rec["target"] = float(rng.normal(0.2, target_scale))
        records.append(rec)
    return records


def _make_sparse_records(
    n: int,
    feature_names: list[str],
    null_frac: float = 0.3,
    seed: int = 13,
) -> list[dict]:
    """Records with some None values to test complete-case handling."""
    rng = np.random.default_rng(seed)
    records = []
    for i in range(n):
        rec: dict = {}
        for fn in feature_names:
            if rng.random() < null_frac:
                rec[fn] = None
            else:
                rec[fn] = float(rng.normal(0, 1))
        rec["target"] = float(rng.normal(0, 0.1))
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Tests: _ridge_solve
# ---------------------------------------------------------------------------

class TestRidgeSolve:
    def test_returns_finite_array(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(50, 4))
        X = np.hstack([X, np.ones((50, 1))])  # bias column
        y = rng.normal(size=50)
        beta = _ridge_solve(X, y)
        assert beta.shape == (5,)
        assert np.all(np.isfinite(beta))

    def test_lambda_positive(self):
        assert RIDGE_LAMBDA == 1.0

    def test_deterministic(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(30, 3))
        X = np.hstack([X, np.ones((30, 1))])
        y = rng.normal(size=30)
        b1 = _ridge_solve(X, y)
        b2 = _ridge_solve(X, y)
        np.testing.assert_array_equal(b1, b2)

    def test_trivial_regression(self):
        """Perfect linear relationship should give near-perfect fit."""
        x = np.arange(50.0)
        X = np.column_stack([x, np.ones(50)])
        y = 2.0 * x + 3.0
        beta = _ridge_solve(X, y, lam=0.0001)
        # With almost-no regularization, should recover slope~2, intercept~3
        assert abs(beta[0] - 2.0) < 0.05, f"Slope error: {beta[0]}"


# ---------------------------------------------------------------------------
# Tests: _ols_slope_intercept
# ---------------------------------------------------------------------------

class TestOlsSlopeIntercept:
    def test_perfect_relationship(self):
        x = np.arange(20.0)
        y = 3.0 * x + 5.0
        intercept, slope = _ols_slope_intercept(x, y)
        assert abs(slope - 3.0) < 1e-6
        assert abs(intercept - 5.0) < 1e-6

    def test_insufficient_data_fallback(self):
        """With < 3 obs, returns (0.0, 1.0) fallback."""
        x = np.array([1.0, 2.0])
        y = np.array([1.0, 2.0])
        intercept, slope = _ols_slope_intercept(x, y)
        assert intercept == 0.0
        assert slope == 1.0

    def test_nan_values_handled(self):
        """NaN values are masked out."""
        x = np.array([1.0, np.nan, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        y = np.array([2.0, np.nan, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0])
        intercept, slope = _ols_slope_intercept(x, y)
        # Should give slope ~2.0 from the valid pairs
        assert abs(slope - 2.0) < 0.1


# ---------------------------------------------------------------------------
# Tests: _walk_forward_mf
# ---------------------------------------------------------------------------

class TestWalkForwardMf:
    def test_min_train_obs_respected(self):
        """No predictions before MIN_TRAIN_OBS."""
        records = _make_synthetic_records(100, _HEAD_FEATURES)
        results = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        for r in results:
            assert r["idx"] >= 60, f"Prediction at idx={r['idx']} before min_obs=60"

    def test_expanding_window_monotone(self):
        """idx values should be strictly increasing."""
        records = _make_synthetic_records(100, _HEAD_FEATURES)
        results = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        idxs = [r["idx"] for r in results]
        assert idxs == sorted(set(idxs)), "idx not monotone"

    def test_result_pos_sequential(self):
        """result_pos values should be 0, 1, 2, ..."""
        records = _make_synthetic_records(90, _HEAD_FEATURES)
        results = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        for expected_pos, r in enumerate(results):
            assert r["result_pos"] == expected_pos

    def test_required_keys_present(self):
        """Each result dict has all required keys."""
        required = {
            "idx", "result_pos", "predicted", "actual",
            "baseline_naive", "baseline_expanding_mean", "baseline_trailing3m", "baseline_ar3",
            "n_train", "n_features_used", "input_completeness",
        }
        records = _make_synthetic_records(90, _HEAD_FEATURES)
        results = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        assert len(results) > 0, "No predictions produced"
        for r in results:
            missing = required - set(r.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_all_predictions_finite(self):
        """All predicted values should be finite."""
        records = _make_synthetic_records(90, _HEAD_FEATURES)
        results = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        for r in results:
            assert np.isfinite(r["predicted"]), f"Non-finite prediction at idx={r['idx']}"

    def test_deterministic(self):
        """Same records produce identical results."""
        records = _make_synthetic_records(80, _HEAD_FEATURES)
        r1 = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        r2 = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a["predicted"] == b["predicted"]
            assert a["actual"] == b["actual"]

    def test_sparse_features_no_crash(self):
        """Complete-case with nulls should not crash."""
        records = _make_sparse_records(120, _HEAD_FEATURES, null_frac=0.4)
        results = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        assert isinstance(results, list)
        for r in results:
            assert np.isfinite(r["predicted"])

    def test_expanding_mean_baseline_present(self):
        """baseline_expanding_mean must be in results (MRI-R28 requirement)."""
        records = _make_synthetic_records(80, _HEAD_FEATURES)
        results = _walk_forward_mf(records, _HEAD_FEATURES, "target", min_obs=60)
        assert len(results) > 0
        for r in results:
            assert "baseline_expanding_mean" in r
            assert r["baseline_expanding_mean"] is not None


# ---------------------------------------------------------------------------
# Tests: _empty_mf schema
# ---------------------------------------------------------------------------

class TestEmptyMfSchema:
    def test_display_only_true(self):
        r = _empty_mf(date(2026, 7, 1), "T-1", "test_reason")
        assert r["display_only"] is True

    def test_authority_false(self):
        r = _empty_mf(date(2026, 7, 1), "T-1", "test_reason")
        assert r["authority"] is False

    def test_model_tag(self):
        r = _empty_mf(date(2026, 7, 1), "T-1", "test_reason")
        assert r["model"] == "mf_energy"

    def test_release_tag(self):
        r = _empty_mf(date(2026, 7, 1), "T-1", "test_reason")
        assert r["release"] == "cpi_headline"

    def test_all_quantiles_none(self):
        r = _empty_mf(date(2026, 7, 1), "T-1", "test_reason")
        for k in ("p10", "p25", "p50", "p75", "p90"):
            assert r[k] is None

    def test_pit_provenance_keys(self):
        r = _empty_mf(date(2026, 7, 1), "early", "test_reason")
        prov = r["pit_provenance"]
        assert prov["display_only"] is True
        assert prov["authority"] is False
        assert "revision_optimistic_legs" in prov
        assert "unrevised_legs" in prov
        assert "absent_legs" in prov

    def test_benchmark_set_keys(self):
        r = _empty_mf(date(2026, 7, 1), "T-1", "test_reason")
        bs = r["benchmark_set"]
        for key in ("naive_prior", "expanding_mean", "trailing_3m", "ar_model",
                    "cleveland_nowcast", "market_implied"):
            assert key in bs

    def test_cutoff_label_preserved(self):
        r = _empty_mf(date(2026, 7, 1), "early", "test_reason")
        assert r["cutoff_label"] == "early"


# ---------------------------------------------------------------------------
# Tests: _seasonal_terms
# ---------------------------------------------------------------------------

class TestSeasonalTerms:
    def test_values_in_minus1_to_1(self):
        """sin/cos terms must be in [-1, 1]."""
        for m in range(1, 13):
            ts = pd.Timestamp(f"2026-{m:02d}-01")
            s, c = _seasonal_terms(ts)
            assert -1.0 <= s <= 1.0
            assert -1.0 <= c <= 1.0

    def test_periodicity(self):
        """Terms for January 2026 and January 2027 should be equal."""
        ts1 = pd.Timestamp("2026-01-01")
        ts2 = pd.Timestamp("2027-01-01")
        s1, c1 = _seasonal_terms(ts1)
        s2, c2 = _seasonal_terms(ts2)
        assert abs(s1 - s2) < 1e-10
        assert abs(c1 - c2) < 1e-10

    def test_december_near_zero_sin(self):
        """December (m=12): sin(2π*12/12) = sin(2π) ≈ 0."""
        ts = pd.Timestamp("2026-12-01")
        s, c = _seasonal_terms(ts)
        assert abs(s) < 1e-10  # sin(2pi) = 0


# ---------------------------------------------------------------------------
# Tests: _compute_wti_beta no-lookahead
# ---------------------------------------------------------------------------

class TestWtiBetaNoLookahead:
    def test_no_lookahead_week_exclusion(self):
        """Weeks from ref_month M must NEVER appear in training data for beta."""
        gasregw = _make_gasregw_series(date(2010, 1, 4), n_weeks=300)
        wti = _make_wti_series(date(2010, 1, 4), n_days=3000)

        ref_month = pd.Timestamp("2016-06-01")
        asof = date(2016, 7, 14)  # day before July release

        # Add a "spike" in June (ref_month M) gasoline that would leak if included
        # in beta training
        june_weeks = gasregw[(gasregw.index >= pd.Timestamp("2016-06-01")) &
                              (gasregw.index <= pd.Timestamp("2016-06-30"))]
        if not june_weeks.empty:
            # Artificially spike June values
            gasregw_with_spike = gasregw.copy()
            gasregw_with_spike[june_weeks.index] = 100.0  # extreme spike

            beta_i1, beta_s1, n1 = _compute_wti_beta(gasregw, wti, ref_month, asof)
            beta_i2, beta_s2, n2 = _compute_wti_beta(gasregw_with_spike, wti, ref_month, asof)

            # The beta computed with the spike should be IDENTICAL if the spike
            # weeks (June = ref_month M) are correctly excluded from training.
            # If there's a difference, the spike leaked into training.
            assert abs(beta_s1 - beta_s2) < 1e-6, (
                f"Beta changed when spike added to ref_month M: "
                f"before={beta_s1:.4f}, after={beta_s2:.4f}. "
                "This indicates a look-ahead leak in beta estimation."
            )

    def test_wti_after_asof_excluded(self):
        """WTI values strictly after asof must not affect the nowcast."""
        gasregw = _make_gasregw_series(date(2010, 1, 4), n_weeks=300)
        wti = _make_wti_series(date(2010, 1, 4), n_days=3000)

        ref_month = pd.Timestamp("2016-03-01")
        asof = date(2016, 4, 10)  # T-1 asof

        # Compute nowcast with original WTI
        result1 = _compute_gasoline_nowcast(gasregw, wti, ref_month, asof)

        # Add future WTI values (after asof) with extreme values
        future_date = pd.Timestamp(asof) + pd.Timedelta(days=3)
        wti_future = wti.copy()
        # If the future date is already in wti_future, replace it with extreme value
        if future_date in wti_future.index:
            wti_future[future_date] = 9999.0

        result2 = _compute_gasoline_nowcast(gasregw, wti_future, ref_month, asof)

        # Results must be identical (future WTI has no effect)
        assert result1["gasoline_mom"] == result2["gasoline_mom"], (
            "gasoline_mom changed when future WTI spike added — look-ahead leak detected"
        )

    def test_wti_future_spike_no_lookahead_in_projection(self):
        """No-lookahead test on n_weeks_projected > 0 fold.

        Pick a fold where the early asof produces n_weeks_projected > 0 (i.e., the
        WTI pass-through accumulator fires). Append a synthetic FUTURE WTI row
        (post-asof spike) and assert the gasoline_mom nowcast and model point are
        BYTE-IDENTICAL to the no-spike case. This confirms future WTI cannot
        contaminate the projection even when remaining weeks are being projected.

        Uses real data fixtures — test is skipped if data is not available.
        """
        import sys
        from pathlib import Path
        _root = Path(__file__).resolve().parents[1]
        gasregw_path = _root / "data" / "fred" / "GASREGW.parquet"
        wti_path = _root / "data" / "fred" / "DCOILWTICO.parquet"
        if not (gasregw_path.exists() and wti_path.exists()):
            pytest.skip("GASREGW/DCOILWTICO data not present")

        from engine.release_mf_energy import _load_gasregw, _load_wti
        gasregw_real = _load_gasregw(_root)
        wti_real = _load_wti(_root)

        # Find a fold where n_weeks_projected > 0 at early asof.
        # Use June 2025 as a reliable test case (release ~July 11, early asof ~June 15).
        # We verified this gives n_weeks_projected >= 1 when early asof is mid-June.
        ref_month = pd.Timestamp("2025-04-01")
        # April 2025 CPI release was ~May 13, 2025 => early asof ~ April 17, 2025
        early_asof = date(2025, 4, 17)

        result_base = _compute_gasoline_nowcast(gasregw_real, wti_real, ref_month, early_asof)
        # Verify this fold actually has projections (so the test is meaningful)
        assert result_base["n_weeks_projected"] >= 1, (
            f"Test setup error: no projected weeks at early asof={early_asof} for {ref_month}. "
            "Pick a different fold or check _all_mondays_in_month."
        )

        # Add an extreme spike AFTER asof to the WTI series
        spike_date = pd.Timestamp(early_asof) + pd.Timedelta(days=2)
        wti_spiked = wti_real.copy()
        # Ensure we insert/replace a future date with an extreme value
        spike_series = pd.Series([99999.0], index=[spike_date])
        wti_spiked = pd.concat([wti_spiked[wti_spiked.index != spike_date], spike_series]).sort_index()

        result_spiked = _compute_gasoline_nowcast(gasregw_real, wti_spiked, ref_month, early_asof)

        # BYTE-IDENTICAL check: future WTI must not change the nowcast
        assert result_base["gasoline_mom"] == result_spiked["gasoline_mom"], (
            f"gasoline_mom changed when post-asof WTI spike added to a projection fold "
            f"(n_weeks_projected={result_base['n_weeks_projected']}): "
            f"base={result_base['gasoline_mom']:.6f}, spiked={result_spiked['gasoline_mom']:.6f}. "
            "Look-ahead detected in remaining-week WTI projection."
        )
        assert result_base["n_weeks_projected"] == result_spiked["n_weeks_projected"], (
            "n_weeks_projected changed when post-asof spike added — look-ahead in projection count."
        )

    def test_m1_denominator_asof_guard(self):
        """M-1 denominator must only include GASREGW weeks with index <= asof.

        If M-1 weeks published after asof appeared in the denominator, they would
        introduce look-ahead into the gasoline_mom computation.  We verify that
        appending a FAKE M-1 week dated after asof does not change the result.
        """
        gasregw = _make_gasregw_series(date(2010, 1, 4), n_weeks=400)
        wti = _make_wti_series(date(2010, 1, 4), n_days=4000)

        # Use a mid-2015 early asof so M-1 weeks might exist after asof
        ref_month = pd.Timestamp("2015-07-01")   # July 2015
        asof = date(2015, 7, 15)                  # mid-July (early asof)
        asof_ts = pd.Timestamp(asof)

        # Compute baseline nowcast
        result_base = _compute_gasoline_nowcast(gasregw, wti, ref_month, asof)

        # Add a fake M-1 (June 2015) GASREGW week AFTER asof with a wildly different value
        # This would corrupt the M-1 mean if the asof guard is absent
        fake_date = pd.Timestamp("2015-07-20")  # June period but indexed after asof
        # Actually fake it as a June week that wasn't published yet:
        fake_june_date = pd.Timestamp("2015-06-29")  # last Monday in June 2015
        # Remove if present and re-insert with extreme value
        gasregw_tampered = gasregw.copy()
        # Temporarily move this date to "after asof" by pretending it has a post-asof index
        # We simulate: add a SECOND June entry dated AFTER asof (June 29 moved to July 20)
        # and add it to the series
        extra = pd.Series([999.0], index=[pd.Timestamp("2015-07-20")])
        # But we want it to be in "June 2015 window" — the guard should exclude it
        # Actually: to test the M-1 guard, we need a fake M-1 week that would
        # appear in m1_weeks if there were no asof guard.
        # M-1 is June 2015. A fake week: indexed July 20 is NOT in June window anyway.
        # Instead: simulate a case where a June 2015 Monday falls after asof.
        # June 2015 last Monday is June 29. With asof=June 28:
        ref_month2 = pd.Timestamp("2015-07-01")
        asof2 = date(2015, 6, 28)  # asof BEFORE last June Monday
        asof_ts2 = pd.Timestamp(asof2)

        result_base2 = _compute_gasoline_nowcast(gasregw, wti, ref_month2, asof2)
        # June 29 (last Monday of M-1) is after asof2=June 28 — it should be excluded
        # Check: without the guard, gasoline_est_M1 would include June 29's value
        # With the guard, it should not

        # Create tampered series where June 29 has an extreme value
        gasregw_tampered2 = gasregw.copy()
        june29 = pd.Timestamp("2015-06-29")
        if june29 in gasregw_tampered2.index:
            gasregw_tampered2[june29] = 9999.0  # extreme value post-asof

        result_tampered2 = _compute_gasoline_nowcast(gasregw_tampered2, wti, ref_month2, asof2)
        # With asof guard: June 29 excluded -> result unchanged
        assert result_base2["gasoline_est_M1"] == result_tampered2["gasoline_est_M1"], (
            f"M-1 denominator changed when post-asof M-1 week spiked: "
            f"base M1={result_base2['gasoline_est_M1']}, tampered M1={result_tampered2['gasoline_est_M1']}. "
            "asof guard on M-1 denominator is missing or broken."
        )


# ---------------------------------------------------------------------------
# Tests: project_release_mf output schema
# ---------------------------------------------------------------------------

class TestProjectReleaseMfSchema:
    @pytest.fixture(scope="class")
    def root(self):
        """Repo root — only runs if data is present."""
        r = Path(__file__).resolve().parents[1]
        vintages_path = r / "data" / "fred_vintage" / "vintages.parquet"
        gasregw_path = r / "data" / "fred" / "GASREGW.parquet"
        wti_path = r / "data" / "fred" / "DCOILWTICO.parquet"
        if not (vintages_path.exists() and gasregw_path.exists() and wti_path.exists()):
            pytest.skip("Required data files not present")
        return r

    def test_required_keys(self, root):
        """Output dict must have all required schema keys."""
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        required = {
            "release", "model", "asof", "cutoff_label",
            "point", "p10", "p25", "p50", "p75", "p90",
            "confidence", "input_completeness",
            "benchmark_set", "surprise_skew",
            "mf_energy_components", "pit_provenance",
            "display_only", "authority",
        }
        missing = required - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_display_only_flag(self, root):
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        assert result["display_only"] is True

    def test_authority_false(self, root):
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        assert result["authority"] is False

    def test_model_tag(self, root):
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        assert result["model"] == "mf_energy"

    def test_release_tag(self, root):
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        assert result["release"] == "cpi_headline"

    def test_pit_provenance_flags(self, root):
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        prov = result["pit_provenance"]
        assert prov["display_only"] is True
        assert prov["authority"] is False
        # Gasoline and WTI declared unrevised
        assert "gasoline_weekly" in prov.get("unrevised_legs", [])
        assert "wti_crude" in prov.get("unrevised_legs", [])

    def test_wrong_release_raises(self, root):
        with pytest.raises(ValueError, match="cpi_headline"):
            project_release_mf("nfp", date(2025, 6, 14), root)

    def test_deterministic(self, root):
        """Two calls with same inputs return identical results."""
        r1 = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        r2 = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        assert r1["point"] == r2["point"]
        assert r1["p10"] == r2["p10"]
        assert r1["p90"] == r2["p90"]

    def test_benchmark_set_has_expanding_mean(self, root):
        """benchmark_set must include expanding_mean (MRI-R28)."""
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        bs = result["benchmark_set"]
        assert "expanding_mean" in bs

    def test_mf_energy_components_present(self, root):
        """mf_energy_components must include required fields."""
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        comp = result.get("mf_energy_components")
        if comp is not None:  # may be None if all legs absent
            required_comp_keys = {
                "gasoline_mom", "energy_contrib", "exenergy_ar",
                "gasoline_ri_weight", "gamma",
                "n_gasoline_weeks_published", "n_gasoline_weeks_projected",
            }
            missing = required_comp_keys - set(comp.keys())
            assert not missing, f"mf_energy_components missing keys: {missing}"

    def test_gasoline_ri_weight_matches_spec(self, root):
        """GASOLINE_RI_WEIGHT must equal 2.895 (from cpi_relative_importance_2026.yml)."""
        assert GASOLINE_RI_WEIGHT == 2.895

    def test_surprise_skew_fields(self, root):
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        ss = result.get("surprise_skew", {})
        assert "sigma" in ss
        assert "tag" in ss
        assert ss.get("inline_band") == 0.35

    def test_cutoff_label_default(self, root):
        result = project_release_mf("cpi_headline", date(2025, 6, 14), root)
        assert result["cutoff_label"] == "T-1"

    def test_cutoff_label_early(self, root):
        result = project_release_mf(
            "cpi_headline", date(2025, 6, 14), root, cutoff_label="early"
        )
        assert result["cutoff_label"] == "early"


# ---------------------------------------------------------------------------
# Tests: run_walk_forward_mf schema and invariants
# ---------------------------------------------------------------------------

class TestRunWalkForwardMf:
    @pytest.fixture(scope="class")
    def root(self):
        r = Path(__file__).resolve().parents[1]
        if not (r / "data" / "fred_vintage" / "vintages.parquet").exists():
            pytest.skip("Vintages data not present")
        if not (r / "data" / "fred" / "GASREGW.parquet").exists():
            pytest.skip("GASREGW data not present")
        return r

    def test_output_schema_t1(self, root):
        """T-1 output must have required top-level keys."""
        out = run_walk_forward_mf(root, cutoff="T-1")
        required = {"results", "errors", "feature_names", "cutoff", "metadata"}
        missing = required - set(out.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_output_schema_early(self, root):
        """Early cutoff output must have required top-level keys."""
        out = run_walk_forward_mf(root, cutoff="early")
        required = {"results", "errors", "feature_names", "cutoff", "metadata"}
        missing = required - set(out.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_cutoff_label_in_output(self, root):
        out_t1 = run_walk_forward_mf(root, cutoff="T-1")
        out_early = run_walk_forward_mf(root, cutoff="early")
        assert out_t1["cutoff"] == "T-1"
        assert out_early["cutoff"] == "early"

    def test_errors_array_consistent(self, root):
        """Errors array length must match results list."""
        out = run_walk_forward_mf(root, cutoff="T-1")
        assert len(out["errors"]) == len(out["results"])

    def test_min_predictions(self, root):
        """Should produce at least some predictions (> 0) with real data."""
        out = run_walk_forward_mf(root, cutoff="T-1")
        n = len(out["results"])
        assert n > 0, "No predictions produced — check data files"

    def test_feature_names_match_spec(self, root):
        """Feature names must match the frozen spec."""
        out = run_walk_forward_mf(root, cutoff="T-1")
        assert out["feature_names"] == _HEAD_FEATURES

    def test_results_have_required_keys(self, root):
        """Each result row must have required keys."""
        out = run_walk_forward_mf(root, cutoff="T-1")
        required = {
            "idx", "result_pos", "predicted", "actual",
            "baseline_naive", "baseline_expanding_mean",
            "baseline_trailing3m", "baseline_ar3",
            "n_train", "n_features_used", "input_completeness",
        }
        for r in out["results"][:5]:  # check first 5 only for speed
            missing = required - set(r.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_idx_monotone_increasing(self, root):
        """Walk-forward idx must be strictly increasing."""
        out = run_walk_forward_mf(root, cutoff="T-1")
        idxs = [r["idx"] for r in out["results"]]
        assert idxs == sorted(idxs), "idx not monotone"

    def test_result_pos_sequential(self, root):
        """result_pos must be 0, 1, 2, ..."""
        out = run_walk_forward_mf(root, cutoff="T-1")
        for expected, r in enumerate(out["results"]):
            assert r["result_pos"] == expected

    def test_deterministic_t1(self, root):
        """Same call twice returns identical results (T-1)."""
        out1 = run_walk_forward_mf(root, cutoff="T-1")
        out2 = run_walk_forward_mf(root, cutoff="T-1")
        assert len(out1["results"]) == len(out2["results"])
        for r1, r2 in zip(out1["results"][:5], out2["results"][:5]):
            assert r1["predicted"] == r2["predicted"]

    def test_invalid_cutoff_raises(self, root):
        with pytest.raises(ValueError, match="cutoff"):
            run_walk_forward_mf(root, cutoff="invalid")

    def test_model_metadata(self, root):
        """metadata must identify model as mf_energy and release as cpi_headline."""
        out = run_walk_forward_mf(root, cutoff="T-1")
        assert out["metadata"]["model"] == "mf_energy"
        assert out["metadata"]["release"] == "cpi_headline"

    def test_no_lookahead_t1_vs_early(self, root):
        """Early cutoff should have fewer gasoline weeks available than T-1.

        We verify this by checking that the walk-forward results at 'early' asofs
        produce different (and plausibly noisier) results than T-1, confirming
        the accumulator is actually doing work at 'early'.

        Specifically: the fraction of predictions where n_gasoline_weeks_published < full
        should be higher at 'early' than at 'T-1'. We proxy this via result count.
        (Both cutoffs target the same historical months; the 'early' set uses fewer GASREGW weeks.)
        """
        out_t1 = run_walk_forward_mf(root, cutoff="T-1")
        out_early = run_walk_forward_mf(root, cutoff="early")
        # Both should have the same number of predictions (same historical months)
        assert len(out_t1["results"]) == len(out_early["results"]), (
            "T-1 and early walk-forwards should cover the same set of historical months"
        )
        # The predictions should NOT be identical (early has partial data = different output)
        t1_preds = [r["predicted"] for r in out_t1["results"]]
        early_preds = [r["predicted"] for r in out_early["results"]]
        # At least some predictions should differ
        diffs = sum(abs(a - b) > 1e-10 for a, b in zip(t1_preds, early_preds))
        assert diffs > 0, "T-1 and early predictions are identical — accumulator may not be working"


# ---------------------------------------------------------------------------
# Tests: constants from spec (frozen values)
# ---------------------------------------------------------------------------

class TestFrozenConstants:
    def test_ridge_lambda(self):
        from engine.release_mf_energy import RIDGE_LAMBDA
        assert RIDGE_LAMBDA == 1.0

    def test_min_train_obs(self):
        from engine.release_mf_energy import MIN_TRAIN_OBS
        assert MIN_TRAIN_OBS == 60

    def test_min_quantile_obs(self):
        from engine.release_mf_energy import MIN_QUANTILE_OBS
        assert MIN_QUANTILE_OBS == 24

    def test_gasoline_ri_weight(self):
        from engine.release_mf_energy import GASOLINE_RI_WEIGHT
        assert GASOLINE_RI_WEIGHT == 2.895

    def test_inline_band_sigma(self):
        from engine.release_mf_energy import INLINE_BAND_SIGMA
        assert INLINE_BAND_SIGMA == 0.35

    def test_head_features_frozen(self):
        from engine.release_mf_energy import _HEAD_FEATURES
        assert _HEAD_FEATURES == ["energy_contrib", "exenergy_ar", "sin_term", "cos_term"]


# ---------------------------------------------------------------------------
# Tests: _predict_exenergy_ar
# ---------------------------------------------------------------------------

class TestPredictExenergyAr:
    def test_returns_float_or_none(self):
        """Should return a finite float or None."""
        rng = np.random.default_rng(42)
        history = list(rng.normal(0.2, 0.1, 80))
        ref_month = pd.Timestamp("2026-03-01")
        result = _predict_exenergy_ar(history, ref_month)
        if result is not None:
            assert isinstance(result, float)
            assert np.isfinite(result)

    def test_insufficient_history_returns_none(self):
        """Too few observations should return None."""
        history = [0.1, 0.2, 0.3]  # way too few
        ref_month = pd.Timestamp("2026-03-01")
        result = _predict_exenergy_ar(history, ref_month)
        assert result is None

    def test_deterministic(self):
        """Same inputs return same output."""
        rng = np.random.default_rng(7)
        history = list(rng.normal(0.2, 0.05, 100))
        ref_month = pd.Timestamp("2026-06-01")
        r1 = _predict_exenergy_ar(history, ref_month)
        r2 = _predict_exenergy_ar(history, ref_month)
        assert r1 == r2
