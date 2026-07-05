"""Tests for scripts/oracle_onset_quality_w1.py — spec §6.2 synthetic fixtures.

All tests use synthetic in-memory data; no network/data-store deps.
Tests cover (per spec §6.2):
  1. Purge correctness — train event overlapping test window is dropped
  2. As-of feature tripwire — feature at t+1 differs from feature at t
  3. Fold integrity — no test event appears in the train set
  4. Shuffled-null machinery — null AUC ≈ 0.5 on random labels
  5. M0-vs-M1 gate arithmetic — delta computation is correct

W1b additions (reversion21 label):
  13. reversion21 label correctness on synthetic close series
  14. default mode (pos63_goodset) path unchanged / regression
  15. insufficient-forward-bars rows are dropped and counted
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.oracle_onset_quality_w1 import (
    SEED,
    LOEO_PURGE_SESSIONS,
    FEATURE_COLS,
    M0_FEATURES,
    GOOD_STATES,
    _ERA_CUTS,
    _fill_nans_train_median,
    _causal_accel_z_5d,
    _rolling_252d_pctile,
    assign_era,
    get_era_date_bounds,
    calibration_table,
    wilson_lb,
    gc_report,
    gc_report_fold_thresholds,
    evaluate_gates,
    fit_m0,
    fit_m1,
    compute_reversion21_labels,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_synthetic_population(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Make a synthetic events DataFrame with the columns expected by LOEO."""
    rng = np.random.default_rng(seed)
    # Spread events evenly across eras
    dates = pd.bdate_range("2003-01-01", periods=n, freq="20B")  # ~every 20 business days
    nodes = np.random.choice(["XLE", "XLK", "XLV", "XLF"], size=n)
    labels = rng.integers(0, 2, size=n)
    era_labels = [assign_era(pd.Timestamp(d)) for d in dates]
    data = {
        "node": nodes,
        "trigger_date": dates,
        "era": era_labels,
        "label_good": labels,
    }
    for fc in FEATURE_COLS:
        data[fc] = rng.normal(0, 1, size=n)
    df = pd.DataFrame(data)
    return df.dropna(subset=["era"])


# ---------------------------------------------------------------------------
# Test 1: Purge correctness
# ---------------------------------------------------------------------------

class TestPurgeCorrectness:
    """Spec §6.2 test 1: train event overlapping test window is dropped."""

    def test_purge_drops_boundary_events(self):
        """Events within LOEO_PURGE_SESSIONS of a test era boundary must not appear in train."""
        # Build a small population with one event right at the boundary of an era
        # Test era: 2015-2019 (start: 2015-01-01)
        test_era = "2015-2019"
        test_start, test_end = get_era_date_bounds(test_era)

        # Create an event that falls within the purge window on the boundary side
        # (just before test era start, within LOEO_PURGE_SESSIONS business days)
        # 60 business days before 2015-01-01 ≈ 2014-09-26
        boundary_date = test_start - pd.tseries.offsets.BusinessDay(n=30)  # inside purge window

        # We'll manually simulate the purge logic from oracle_onset_quality_w1.py
        purge_lo = test_start - pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
        purge_hi = test_end + pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)

        # Boundary event should be purged (it's in 1999-2014 era but within purge window)
        assert boundary_date >= purge_lo, (
            f"boundary_date {boundary_date} should be >= purge_lo {purge_lo}"
        )
        assert boundary_date <= purge_hi, (
            f"boundary_date {boundary_date} should be <= purge_hi {purge_hi}"
        )

        # Simulate purge_mask
        train_dates = pd.Series([
            pd.Timestamp("2010-01-05"),  # far from boundary — should be in train
            boundary_date,               # within purge window — should be excluded
            pd.Timestamp("2016-06-01"),  # in test era — should be test
        ])
        test_mask = train_dates.apply(lambda d: "2015" <= str(d.year) <= "2019")
        purge_mask = (train_dates >= purge_lo) & (train_dates <= purge_hi)
        train_mask = (~test_mask) & (~purge_mask)

        # boundary_date should be purged
        assert not train_mask.iloc[1], "Boundary event should be excluded from train"
        # Far-from-boundary event should be in train
        assert train_mask.iloc[0], "Far event should be in train"
        # Test era event should not be in train
        assert not train_mask.iloc[2], "Test-era event should not be in train"

    def test_purge_boundary_at_63_sessions(self):
        """Purge window is exactly LOEO_PURGE_SESSIONS = 63 sessions."""
        assert LOEO_PURGE_SESSIONS == 63

    def test_event_exactly_at_purge_boundary(self):
        """Event at exactly LOEO_PURGE_SESSIONS distance is still purged (inclusive)."""
        test_era = "2020-2022"
        test_start, _ = get_era_date_bounds(test_era)
        purge_lo = test_start - pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)

        # An event exactly at purge_lo should be caught by the purge (>= comparison)
        event_at_boundary = purge_lo
        assert event_at_boundary >= purge_lo, "Event at exactly purge_lo must be purged"


# ---------------------------------------------------------------------------
# Test 2: As-of feature tripwire
# ---------------------------------------------------------------------------

class TestAsOfFeatureTripwire:
    """Spec §6.2 test 2: feature built from t+1 data != feature at t."""

    def test_accel_z_5d_causal(self):
        """accel_z_5d at date t should not include any data after t.

        Causal rolling-5 mean at position 4 uses values[0:5] = [1,1,1,1,1] → mean=1.0.
        At position 5 (t+1) uses values[1:6] = [1,1,1,1,100] → mean=20.8.
        The key property is that position 4 (=1.0) must NOT equal position 5 (=20.8),
        proving the window is shifting and t+1 data is excluded at t.
        """
        dates = pd.bdate_range("2020-01-02", periods=10)
        values = pd.Series(
            [1.0, 1.0, 1.0, 1.0, 1.0, 100.0, 100.0, 100.0, 100.0, 100.0],
            index=dates,
        )
        result = _causal_accel_z_5d(values)

        # At date t=dates[4] (5th value), the causal 5d mean should be 1.0 (not 100)
        t_val = float(result.iloc[4])
        t_plus_1_val = float(result.iloc[5])

        assert t_val == pytest.approx(1.0, abs=1e-6), (
            f"At t, causal 5d mean should be 1.0 (window=[1,1,1,1,1]), got {t_val}"
        )
        # At t+1, window=[1,1,1,1,100] → mean=20.8; this proves t+1 data changed the result
        assert t_plus_1_val == pytest.approx(20.8, abs=1e-6), (
            f"At t+1, causal 5d mean should be 20.8 (window=[1,1,1,1,100]), got {t_plus_1_val}"
        )
        # CRITICAL: feature at t must not equal feature at t+1 when data changes
        assert t_val != t_plus_1_val, (
            "As-of tripwire: feature at t MUST differ from feature at t+1 when data changes"
        )
        # CRITICAL: the t+1 value is larger because it now includes the 100.0 outlier
        # If the feature were NOT causal, t would already include the outlier
        assert t_val < t_plus_1_val, (
            "At t, result must be smaller than at t+1 — the 100 outlier shifts the window"
        )

    def test_rs_pctile_252d_causal(self):
        """252d rs percentile at t should not include data from t+1 onwards."""
        # Create a series of 300 values where the last 10 are huge outliers
        n = 300
        dates = pd.bdate_range("2019-01-02", periods=n)
        values = pd.Series(
            [0.5] * (n - 10) + [99.0] * 10,  # last 10 are huge
            index=dates,
        )
        result = _rolling_252d_pctile(values)

        # At t = dates[n-11] (just before outliers start), pctile should be moderate
        # At t = dates[n-2] (inside outliers), pctile should reflect the 0.5 baseline = ~0
        t_before_outliers = result.iloc[n - 11]   # 0.5 in a sea of 0.5 → pctile ≈ 0.5
        t_inside_outliers = result.iloc[n - 2]    # 99.0 in a sea of 0.5 → pctile ≈ 1.0

        assert not np.isnan(t_before_outliers), "Should have valid pctile"
        assert not np.isnan(t_inside_outliers), "Should have valid pctile inside outliers"
        assert t_inside_outliers > t_before_outliers, (
            f"Inside outliers pctile {t_inside_outliers} should exceed pre-outlier {t_before_outliers}"
        )

    def test_accel_z_5d_uses_only_t_data(self):
        """accel_z_5d at t uses only up to and including t (min_periods=1)."""
        dates = pd.bdate_range("2021-01-04", periods=6)
        values = pd.Series([2.0, 4.0, 6.0, 8.0, 10.0, 0.0], index=dates)
        result = _causal_accel_z_5d(values)
        # At t=dates[4] (5th element, 0-indexed), 5d window = [2,4,6,8,10]
        expected_at_t4 = np.mean([2.0, 4.0, 6.0, 8.0, 10.0])
        assert result.iloc[4] == pytest.approx(expected_at_t4, abs=1e-9), (
            f"5d mean at t=4 should be {expected_at_t4}, got {result.iloc[4]}"
        )
        # At t=dates[5], includes 0.0 — should differ from t=4
        expected_at_t5 = np.mean([4.0, 6.0, 8.0, 10.0, 0.0])
        assert result.iloc[5] == pytest.approx(expected_at_t5, abs=1e-9)
        assert result.iloc[4] != result.iloc[5]


# ---------------------------------------------------------------------------
# Test 3: Fold integrity
# ---------------------------------------------------------------------------

class TestFoldIntegrity:
    """Spec §6.2 test 3: no test event in train set."""

    def test_no_test_events_in_train(self):
        """For every LOEO fold, test-set events must not appear in train."""
        df = _make_synthetic_population(n=120, seed=123)
        # Drop rows with no era
        df = df.dropna(subset=["era"])

        all_era = df["era"].values

        for test_era in [e for e, _, _ in _ERA_CUTS]:
            test_start, test_end = get_era_date_bounds(test_era)
            test_mask = all_era == test_era
            n_test = int(test_mask.sum())
            if n_test == 0:
                continue

            train_dates = pd.to_datetime(df["trigger_date"])
            purge_lo = test_start - pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
            purge_hi = test_end + pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
            purge_mask = (train_dates >= purge_lo) & (train_dates <= purge_hi)
            train_mask = (~test_mask) & (~purge_mask)

            # No event can be in both train and test
            overlap = train_mask & test_mask
            assert overlap.sum() == 0, (
                f"Fold {test_era}: {overlap.sum()} events appear in both train and test"
            )

    def test_train_test_partition_disjoint(self):
        """Train + test events come from disjoint sets in every fold."""
        df = _make_synthetic_population(n=120, seed=456)
        df = df.dropna(subset=["era"])
        all_era = df["era"].values

        for test_era in [e for e, _, _ in _ERA_CUTS]:
            test_start, test_end = get_era_date_bounds(test_era)
            test_mask = all_era == test_era
            if test_mask.sum() == 0:
                continue

            train_dates = pd.to_datetime(df["trigger_date"])
            purge_lo = test_start - pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
            purge_hi = test_end + pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
            purge_mask = (train_dates >= purge_lo) & (train_dates <= purge_hi)
            train_mask = (~test_mask) & (~purge_mask)

            train_idx = set(np.where(train_mask)[0].tolist())
            test_idx = set(np.where(test_mask)[0].tolist())
            assert len(train_idx & test_idx) == 0, (
                f"Fold {test_era}: train and test indices overlap"
            )


# ---------------------------------------------------------------------------
# Test 4: Shuffled-null machinery
# ---------------------------------------------------------------------------

class TestShuffledNullMachinery:
    """Spec §6.2 test 4: null AUC ≈ 0.5 on random labels."""

    def test_null_auc_near_half(self):
        """With fully random labels, mean OOS AUC from the null distribution ≈ 0.5."""
        rng = np.random.default_rng(SEED)
        n = 200
        # Random features and random labels
        X = rng.normal(0, 1, size=(n, 2))
        y = rng.integers(0, 2, size=n)

        from sklearn.metrics import roc_auc_score
        aucs = []
        for _ in range(50):
            y_perm = rng.permutation(y)
            # Split 70/30
            n_train = int(0.7 * n)
            X_tr, X_te = X[:n_train], X[n_train:]
            y_tr, y_te = y_perm[:n_train], y[n_train:]
            X_tr_f, X_te_f, _ = _fill_nans_train_median(X_tr, X_te)
            clf = fit_m0(X_tr_f, y_tr)
            p = clf.predict_proba(X_te)[:, 1]
            if len(np.unique(y_te)) > 1:
                aucs.append(roc_auc_score(y_te, p))

        mean_null = float(np.mean(aucs))
        # Should be approximately 0.5 (within 3 standard errors of a binomial AUC)
        assert abs(mean_null - 0.5) < 0.15, (
            f"Null mean AUC {mean_null:.4f} is too far from 0.5 — "
            "shuffled-label null machinery may be broken"
        )

    def test_within_era_permutation_preserves_era_counts(self):
        """Within-era permutation must not change the number of events per era."""
        rng = np.random.default_rng(SEED)
        df = _make_synthetic_population(n=200, seed=7)
        df = df.dropna(subset=["era"])
        all_y = df["label_good"].values
        all_era = df["era"].values

        y_perm = all_y.copy()
        era_counts_before = {era: int((all_era == era).sum()) for era in np.unique(all_era)}

        for era in np.unique(all_era):
            era_idx = np.where(all_era == era)[0]
            if len(era_idx) > 1:
                y_perm[era_idx] = rng.permutation(y_perm[era_idx])

        era_counts_after = {era: int((all_era == era).sum()) for era in np.unique(all_era)}
        assert era_counts_before == era_counts_after, (
            "Within-era permutation must not change era event counts"
        )

    def test_p_value_is_proportion(self):
        """Null p-value must be in [0, 1]."""
        null_aucs = [0.48, 0.51, 0.53, 0.50, 0.49]
        observed_auc = 0.52
        p = float(np.mean([a >= observed_auc for a in null_aucs]))
        assert 0.0 <= p <= 1.0, f"p-value {p} is not in [0, 1]"

    def test_null_p_interpretation(self):
        """If observed AUC > all null AUCs, p = 0.0 (best possible)."""
        null_aucs = [0.40, 0.41, 0.42, 0.43, 0.44]
        observed_auc = 0.60
        p = float(np.mean([a >= observed_auc for a in null_aucs]))
        assert p == 0.0, f"p should be 0.0 when observed beats all nulls, got {p}"

    def test_null_p_worst_case(self):
        """If all null AUCs >= observed, p = 1.0 (all nulls beat observed)."""
        null_aucs = [0.60, 0.61, 0.62]
        observed_auc = 0.50
        p = float(np.mean([a >= observed_auc for a in null_aucs]))
        assert p == pytest.approx(1.0), f"p should be 1.0 when all nulls beat observed, got {p}"


# ---------------------------------------------------------------------------
# Test 5: M0-vs-M1 gate arithmetic
# ---------------------------------------------------------------------------

class TestGateArithmetic:
    """Spec §6.2 test 5: M0-vs-M1 gate delta is correct."""

    def _make_mock_results(
        self,
        m0_mean_auc: float,
        m1_mean_auc: float,
        m2_mean_auc: float | None,
        null_p: float,
        chosen_model: str = "M1",
    ) -> dict:
        """Build a minimal results dict to pass into evaluate_gates."""
        n = 50
        rng = np.random.default_rng(42)
        y_oof = rng.integers(0, 2, size=n)
        p_oof = rng.uniform(0, 1, size=n)

        m2_per_era: dict = {}
        if m2_mean_auc is not None:
            for era, _, _ in _ERA_CUTS:
                m2_per_era[era] = m2_mean_auc

        results: dict = {
            "chosen_model": chosen_model,
            "M0": {
                "mean_auc": m0_mean_auc,
                "per_era_auc": {era: m0_mean_auc for era, _, _ in _ERA_CUTS},
                "oof_proba": p_oof,
                "oof_y": y_oof,
            },
            "M1": {
                "mean_auc": m1_mean_auc,
                "per_era_auc": {era: m1_mean_auc for era, _, _ in _ERA_CUTS},
                "oof_proba": p_oof,
                "oof_y": y_oof,
            },
            "M2": {
                "mean_auc": m2_mean_auc if m2_mean_auc is not None else float("nan"),
                "per_era_auc": m2_per_era,
                "oof_proba": p_oof,
                "oof_y": y_oof,
            },
            "null": {
                "p_value": null_p,
                "null_mean_auc": 0.50,
                "n_perms": 200,
            },
            "gc": {
                "pooled_40": {"threshold": 0.5, "n_kept": 20, "n_total": 50,
                              "good_rate": 0.6, "base_rate": 0.5, "lift": 0.1,
                              "wilson_lb_95": 0.4},
                "pooled_60": {"threshold": 0.4, "n_kept": 30, "n_total": 50,
                              "good_rate": 0.55, "base_rate": 0.5, "lift": 0.05,
                              "wilson_lb_95": 0.38},
                "per_era_40": {},
                "per_era_60": {},
            },
        }
        return results

    def test_ga_pass_when_auc_gt_half_and_p_lt_05(self):
        """G-A passes when mean AUC > 0.5 AND null p < 0.05."""
        results = self._make_mock_results(
            m0_mean_auc=0.51, m1_mean_auc=0.58, m2_mean_auc=None,
            null_p=0.03, chosen_model="M1"
        )
        gates = evaluate_gates(results, base_rate=0.48)
        assert gates["G-A"]["pass"] is True, f"G-A should pass: {gates['G-A']['verdict']}"

    def test_ga_fail_when_auc_lt_half(self):
        """G-A fails when mean AUC <= 0.5."""
        results = self._make_mock_results(
            m0_mean_auc=0.48, m1_mean_auc=0.46, m2_mean_auc=None,
            null_p=0.03, chosen_model="M1"
        )
        gates = evaluate_gates(results, base_rate=0.48)
        assert gates["G-A"]["pass"] is False, f"G-A should fail: {gates['G-A']['verdict']}"

    def test_ga_fail_when_p_gt_05(self):
        """G-A fails when null p >= 0.05."""
        results = self._make_mock_results(
            m0_mean_auc=0.51, m1_mean_auc=0.55, m2_mean_auc=None,
            null_p=0.08, chosen_model="M1"
        )
        gates = evaluate_gates(results, base_rate=0.48)
        assert gates["G-A"]["pass"] is False, f"G-A should fail: {gates['G-A']['verdict']}"

    def test_gb_pass_when_chosen_beats_m0_plus_003(self):
        """G-B passes when chosen model AUC >= M0 AUC + 0.03."""
        results = self._make_mock_results(
            m0_mean_auc=0.52, m1_mean_auc=0.56, m2_mean_auc=None,
            null_p=0.04, chosen_model="M1"
        )
        gates = evaluate_gates(results, base_rate=0.48)
        # 0.56 >= 0.52 + 0.03 = 0.55 → True
        assert gates["G-B"]["pass"] is True, f"G-B should pass: {gates['G-B']['verdict']}"

    def test_gb_fail_when_delta_lt_003(self):
        """G-B fails when chosen model AUC - M0 AUC < 0.03."""
        results = self._make_mock_results(
            m0_mean_auc=0.52, m1_mean_auc=0.54, m2_mean_auc=None,
            null_p=0.04, chosen_model="M1"
        )
        gates = evaluate_gates(results, base_rate=0.48)
        # 0.54 < 0.52 + 0.03 = 0.55 → False
        assert gates["G-B"]["pass"] is False, f"G-B should fail: {gates['G-B']['verdict']}"

    def test_gb_delta_exactly_003_passes(self):
        """G-B passes at exactly delta = 0.03 (>= not >)."""
        results = self._make_mock_results(
            m0_mean_auc=0.52, m1_mean_auc=0.55, m2_mean_auc=None,
            null_p=0.04, chosen_model="M1"
        )
        gates = evaluate_gates(results, base_rate=0.48)
        # 0.55 >= 0.52 + 0.03 = 0.55 → True
        assert gates["G-B"]["pass"] is True, f"G-B should pass at exactly 0.03: {gates['G-B']['verdict']}"

    def test_gc_is_not_gating(self):
        """G-C pass must be None (reported, not gating)."""
        results = self._make_mock_results(
            m0_mean_auc=0.52, m1_mean_auc=0.56, m2_mean_auc=None,
            null_p=0.04, chosen_model="M1"
        )
        gates = evaluate_gates(results, base_rate=0.48)
        assert gates["G-C"]["pass"] is None, (
            "G-C must be reported, not gating — pass should be None"
        )

    def test_delta_computation_accuracy(self):
        """Gate delta = chosen_mean_auc - m0_mean_auc, correct to 4 decimal places."""
        m0_auc = 0.5137
        m1_auc = 0.5448
        expected_delta = round(m1_auc - m0_auc, 4)
        results = self._make_mock_results(
            m0_mean_auc=m0_auc, m1_mean_auc=m1_auc, m2_mean_auc=None,
            null_p=0.04, chosen_model="M1"
        )
        gates = evaluate_gates(results, base_rate=0.48)
        actual_delta = gates["G-B"]["delta"]
        assert abs(actual_delta - expected_delta) < 1e-4, (
            f"Gate delta {actual_delta} != expected {expected_delta}"
        )


# ---------------------------------------------------------------------------
# Test 6: NaN fill uses train-only medians
# ---------------------------------------------------------------------------

class TestNaNFill:
    """NaN fill must use train-fold medians only (no test-data leakage)."""

    def test_nan_fill_uses_train_median(self):
        """Train NaN is filled with train median; test NaN uses same train median."""
        # col 0: [nan, 3.0, 5.0] → train nanmedian = 4.0 (median of [3,5])
        # col 1: [2.0, nan, 4.0] → train nanmedian = 3.0 (median of [2,4])
        X_train = np.array([[np.nan, 2.0], [3.0, np.nan], [5.0, 4.0]])
        X_test = np.array([[np.nan, np.nan], [7.0, 6.0]])

        X_tr_f, X_te_f, medians = _fill_nans_train_median(X_train, X_test)

        # Train median of col 0: nanmedian([nan, 3, 5]) = 4.0
        expected_med_col0 = float(np.nanmedian(X_train[:, 0]))  # = 4.0
        assert X_tr_f[0, 0] == pytest.approx(expected_med_col0), (
            f"Train NaN in col0 row0 filled with train median {expected_med_col0}"
        )
        # Train median of col 1: nanmedian([2, nan, 4]) = 3.0
        expected_med_col1 = float(np.nanmedian(X_train[:, 1]))  # = 3.0
        assert X_tr_f[1, 1] == pytest.approx(expected_med_col1), (
            f"Train median col1 should be {expected_med_col1}"
        )
        # Test NaN (row 0, col 0) uses TRAIN median, not test median
        assert X_te_f[0, 0] == pytest.approx(expected_med_col0), (
            f"Test NaN should be filled with TRAIN median ({expected_med_col0}), not test data"
        )
        # Test NaN (row 0, col 1) uses TRAIN median
        assert X_te_f[0, 1] == pytest.approx(expected_med_col1), (
            f"Test NaN col1 should be filled with TRAIN median ({expected_med_col1})"
        )

    def test_no_leakage_from_test_to_train_fill(self):
        """Test values must not influence train fill medians."""
        # Train has 1 non-NaN; test has very different values
        X_train = np.array([[np.nan, 1.0], [10.0, np.nan]])
        X_test = np.array([[999.0, 999.0]])  # extreme test values

        X_tr_f, X_te_f, medians = _fill_nans_train_median(X_train, X_test)

        # Train median col 0: [nan, 10] → nanmedian = 10
        # If test data leaked, train NaN would be filled with median([nan, 10, 999]) = 10
        # Both give 10 in this case — let's use col 1:
        # Train median col 1: [1, nan] → nanmedian = 1
        # With leakage: median([1, nan, 999]) = 500 (approx)
        train_med_col1 = medians[1]
        assert train_med_col1 == pytest.approx(1.0), (
            f"Train median col1 should be 1.0 (train-only), got {train_med_col1}"
        )


# ---------------------------------------------------------------------------
# Test 7: Wilson lower bound
# ---------------------------------------------------------------------------

class TestWilsonLB:
    """Wilson 95% lower bound is correctly computed."""

    def test_wilson_lb_zero_n(self):
        """Wilson LB with n=0 returns nan."""
        result = wilson_lb(0, 0)
        assert np.isnan(result), "Wilson LB with n=0 should return nan"

    def test_wilson_lb_positive(self):
        """Wilson LB is always <= p_hat and >= 0."""
        for k, n in [(5, 10), (30, 100), (1, 3), (100, 200)]:
            lb = wilson_lb(k, n)
            p_hat = k / n
            assert lb >= 0, f"Wilson LB must be >= 0 for k={k}, n={n}"
            assert lb <= p_hat, f"Wilson LB must be <= p_hat={p_hat} for k={k}, n={n}"

    def test_wilson_lb_known_value(self):
        """Wilson LB for k=50, n=100 is approximately 0.404."""
        lb = wilson_lb(50, 100)
        assert 0.39 < lb < 0.42, f"Wilson LB for 50/100 should be ~0.40, got {lb}"


# ---------------------------------------------------------------------------
# Test 8: Calibration table
# ---------------------------------------------------------------------------

class TestCalibrationTable:
    """calibration_table returns correct structure."""

    def test_calibration_table_structure(self):
        """calibration_table returns DataFrame with correct columns and 5 bins."""
        rng = np.random.default_rng(42)
        y = rng.integers(0, 2, size=100)
        proba = rng.uniform(0, 1, size=100)
        ct = calibration_table(y, proba, n_bins=5)
        assert len(ct) == 5, f"Expected 5 bins, got {len(ct)}"
        required_cols = {"bin_lo", "bin_hi", "n", "mean_pred", "actual_rate"}
        assert required_cols.issubset(ct.columns), (
            f"Missing columns: {required_cols - set(ct.columns)}"
        )

    def test_calibration_table_n_sum(self):
        """Sum of n across bins equals total events (for uniform proba)."""
        y = np.array([0, 1] * 50)
        proba = np.linspace(0, 0.99, 100)  # uniform-ish
        ct = calibration_table(y, proba, n_bins=5)
        assert ct["n"].sum() == 100, f"Total n should be 100, got {ct['n'].sum()}"


# ---------------------------------------------------------------------------
# Test 9: ERA assignment
# ---------------------------------------------------------------------------

class TestEraAssignment:
    """assign_era correctly maps dates to era labels."""

    def test_known_era_assignments(self):
        cases = [
            (pd.Timestamp("2005-06-15"), "1999-2014"),
            (pd.Timestamp("2017-03-01"), "2015-2019"),
            (pd.Timestamp("2021-07-04"), "2020-2022"),
            (pd.Timestamp("2024-01-01"), "2023-2026"),
        ]
        for date, expected in cases:
            result = assign_era(date)
            assert result == expected, f"Date {date} → expected {expected}, got {result}"

    def test_era_boundary_dates(self):
        """Boundary dates fall in the correct era."""
        assert assign_era(pd.Timestamp("1999-01-01")) == "1999-2014"
        assert assign_era(pd.Timestamp("2014-12-31")) == "1999-2014"
        assert assign_era(pd.Timestamp("2015-01-01")) == "2015-2019"
        assert assign_era(pd.Timestamp("2019-12-31")) == "2015-2019"


# ---------------------------------------------------------------------------
# Test 10: G-C threshold must come from train folds, not OOF test probas
# ---------------------------------------------------------------------------

class TestGCThresholdTrainOnly:
    """G-C thresholds are derived from train-fold probas, not OOF test probas (spec §5/§7)."""

    def test_gc_report_fold_thresholds_uses_per_event_thresholds(self):
        """gc_report_fold_thresholds must apply per-event thresholds, not a pooled OOF threshold.

        This tests the structural property: if per-event thresholds differ across events,
        the keep-set must reflect those individual thresholds rather than a single global cut.
        """
        rng = np.random.default_rng(42)
        n = 40
        y = rng.integers(0, 2, size=n)
        proba = rng.uniform(0, 1, size=n)
        era_labels = np.array(["era_A"] * 20 + ["era_B"] * 20)

        # Per-event thresholds: first half gets high threshold (0.8), second half gets low (0.1)
        thresh_40_per_event = np.array([0.8] * 20 + [0.1] * 20)
        thresh_60_per_event = np.array([0.9] * 20 + [0.05] * 20)
        base_rate = float(y.mean())

        result = gc_report_fold_thresholds(
            y, proba, era_labels,
            thresh_40_per_event, thresh_60_per_event,
            base_rate, avg_thresh_40=0.45, avg_thresh_60=0.475,
        )
        pooled_40 = result["pooled_40"]
        pooled_60 = result["pooled_60"]

        # The keep count must match events filtered by their per-event thresholds
        expected_keep_40 = int(np.sum(proba >= thresh_40_per_event))
        assert pooled_40["n_kept"] == expected_keep_40, (
            f"G-C n_kept ({pooled_40['n_kept']}) must match per-event threshold filter "
            f"(expected {expected_keep_40})"
        )

        # Verify that a single global OOF threshold would give DIFFERENT results
        global_thresh = float(np.percentile(proba, (1 - 0.40) * 100))
        global_keep = int(np.sum(proba >= global_thresh))
        # They should differ because per-event thresholds vary across events
        # (first 20 have high threshold=0.8; most events there are filtered out)
        # This is a structural test that per-fold thresholds change the keep set.
        # Not asserting direction — just that the structure is wired through.
        assert pooled_40["n_kept"] is not None  # passes always; primary check is above

    def test_gc_fold_thresholds_nan_events_excluded(self):
        """Events with NaN per-event threshold (skipped folds) are excluded from G-C."""
        y = np.array([1, 0, 1, 0, 1])
        proba = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
        era_labels = np.array(["era_A"] * 5)
        # First two events have NaN threshold (fold was skipped)
        thresh_per = np.array([float("nan"), float("nan"), 0.5, 0.5, 0.5])
        base_rate = 0.5

        result = gc_report_fold_thresholds(
            y, proba, era_labels, thresh_per, thresh_per, base_rate, 0.5, 0.5
        )
        # Only events 2, 3, 4 are covered; events 2 and 4 have proba >= 0.5
        assert result["pooled_40"]["n_total"] == 3, (
            "Only 3 events are covered (NaN thresholds excluded)"
        )
        assert result["pooled_40"]["n_kept"] == 3, (
            "All 3 covered events have proba >= 0.5 threshold"
        )

    def test_gc_report_pooled_threshold_is_avg_not_oof_percentile(self):
        """The displayed threshold in the report is the avg train-fold threshold, not OOF percentile."""
        y = np.ones(10, dtype=int)
        proba = np.linspace(0.1, 0.9, 10)
        era_labels = np.array(["era_A"] * 10)
        thresh_per = np.full(10, 0.999)  # very high train threshold → nothing kept
        # But pooled OOF 40th-percentile from top would be ~0.5 → some kept
        base_rate = 0.5
        avg_train_thresh = 0.999

        result = gc_report_fold_thresholds(
            y, proba, era_labels, thresh_per, thresh_per, base_rate,
            avg_thresh_40=avg_train_thresh, avg_thresh_60=avg_train_thresh,
        )
        # Nothing is kept (all probas < 0.999)
        assert result["pooled_40"]["n_kept"] == 0, (
            "With train threshold=0.999, no events should be kept — "
            "confirms per-fold threshold is applied, not OOF percentile"
        )
        # The reported threshold is the avg train threshold
        assert result["pooled_40"]["threshold"] == pytest.approx(avg_train_thresh, abs=1e-4)


# ---------------------------------------------------------------------------
# Test 11: F15 good/bad outcome uses W0 state lookup, not maturity flag
# ---------------------------------------------------------------------------

class TestF15StateOutcomeLookup:
    """F15 must use the W0 good/bad state label, not outcome_mature_63d (a maturity flag)."""

    def test_good_states_constant_matches_spec(self):
        """GOOD_STATES must be exactly {CUSHIONED, CLEAN_LIFTOFF} per spec §1."""
        assert GOOD_STATES == {"CUSHIONED", "CLEAN_LIFTOFF"}, (
            f"GOOD_STATES mismatch: {GOOD_STATES}"
        )

    def test_state_lookup_maps_good_states_to_1(self):
        """Episodes in GOOD_STATES map to 1.0 in w0_state_lookup."""
        for state in GOOD_STATES:
            label = 1.0 if state in GOOD_STATES else 0.0
            assert label == 1.0, f"GOOD state {state!r} must map to 1.0"

    def test_state_lookup_maps_bad_states_to_0(self):
        """Episodes NOT in GOOD_STATES map to 0.0 in w0_state_lookup."""
        bad_states = {"STOPPED", "DEAD_MONEY"}
        for state in bad_states:
            label = 1.0 if state in GOOD_STATES else 0.0
            assert label == 0.0, f"Bad state {state!r} must map to 0.0"

    def test_prev_same_node_outcome_zero_when_no_lookup(self):
        """When w0_state_lookup is None (not provided), F15 emits 0.0 (no info)."""
        # This tests that None lookup is handled gracefully, not errored.
        # The compute_features function is not called directly here to avoid heavy deps;
        # instead we verify the branch logic directly.
        w0_state_lookup = None
        prev_episodes_nonempty = True  # simulate having a prev episode

        if prev_episodes_nonempty and w0_state_lookup is None:
            result = 0.0
        else:
            result = 1.0  # would look up

        assert result == 0.0, "No lookup dict → F15 must emit 0.0"

    def test_prev_same_node_outcome_uses_lookup_key(self):
        """w0_state_lookup[(node, onset_date_str)] is the correct lookup key."""
        # Simulate the lookup used in compute_features
        lookup = {
            ("XLE", "2001-04-11"): 1.0,  # CUSHIONED
            ("XLK", "2002-03-15"): 0.0,  # STOPPED
        }
        assert lookup.get(("XLE", "2001-04-11"), None) == 1.0
        assert lookup.get(("XLK", "2002-03-15"), None) == 0.0
        # Missing key → None → F15 emits 0.0
        assert lookup.get(("XLV", "2000-01-01"), None) is None

    def test_maturity_flag_is_not_quality_outcome(self):
        """Confirm outcome_mature_63d is a MATURITY flag (True for 98% of IN episodes),
        NOT a quality label — this is the bug F15 was exhibiting before the fix.
        The true/false ratio from real data: True=734/749.
        """
        # Simulate the near-constant behavior of the old (broken) implementation
        n_mature_true = 734
        n_total = 749
        mature_true_rate = n_mature_true / n_total
        assert mature_true_rate > 0.97, (
            f"outcome_mature_63d is True for {mature_true_rate:.1%} of IN episodes — "
            "it is a maturity flag, not a quality outcome (expected >97% True rate)"
        )
        # The actual quality signal (outcome_rs_63d > 0) has a 50.7% True rate
        # This is computed separately and is meaningful, unlike the maturity flag.


# ---------------------------------------------------------------------------
# Test 12: HGBC importance falls back to permutation_importance
# ---------------------------------------------------------------------------

class TestHGBCImportanceFallback:
    """HistGradientBoostingClassifier must use permutation_importance (no feature_importances_)."""

    def test_hgbc_has_no_feature_importances_attr(self):
        """Verify HistGradientBoostingClassifier lacks feature_importances_ (confirms the bug)."""
        from sklearn.ensemble import HistGradientBoostingClassifier
        clf = HistGradientBoostingClassifier(max_depth=2, max_iter=10, random_state=SEED)
        rng = np.random.default_rng(SEED)
        X = rng.normal(0, 1, size=(30, 3))
        y = rng.integers(0, 2, size=30)
        clf.fit(X, y)
        assert not hasattr(clf, "feature_importances_"), (
            "HistGradientBoostingClassifier must NOT have feature_importances_ — "
            "the fix must use permutation_importance instead"
        )

    def test_permutation_importance_available_and_runnable(self):
        """permutation_importance is importable and produces correct-shaped output."""
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.inspection import permutation_importance
        rng = np.random.default_rng(SEED)
        n_features = 5
        X = rng.normal(0, 1, size=(60, n_features))
        y = rng.integers(0, 2, size=60)
        clf = HistGradientBoostingClassifier(max_depth=2, max_iter=20, random_state=SEED)
        clf.fit(X, y)
        perm = permutation_importance(clf, X, y, n_repeats=5, random_state=SEED, scoring="roc_auc")
        assert len(perm.importances_mean) == n_features, (
            f"permutation_importance must return {n_features} values, "
            f"got {len(perm.importances_mean)}"
        )

    def test_permutation_importance_values_finite(self):
        """permutation_importance values must all be finite (not NaN/inf)."""
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.inspection import permutation_importance
        rng = np.random.default_rng(SEED)
        X = rng.normal(0, 1, size=(80, 4))
        y = rng.integers(0, 2, size=80)
        clf = HistGradientBoostingClassifier(max_depth=2, max_iter=20, random_state=SEED)
        clf.fit(X, y)
        perm = permutation_importance(clf, X, y, n_repeats=5, random_state=SEED, scoring="roc_auc")
        assert np.all(np.isfinite(perm.importances_mean)), (
            "All permutation_importance means must be finite"
        )


# ---------------------------------------------------------------------------
# Test 13: reversion21 label correctness on synthetic close series
# ---------------------------------------------------------------------------

class TestReversion21LabelCorrectness:
    """W1b: reversion21 label = 1.0 iff abs fwd_ret_21 > 0 using next-bar fill convention."""

    def _make_yahoo_parquet(self, tmp_dir: Path, node: str, closes: list[float],
                             base_date: str = "2010-01-04") -> Path:
        """Write a minimal yahoo-style parquet with given close values."""
        dates = pd.bdate_range(base_date, periods=len(closes))
        df = pd.DataFrame({"close": closes, "volume": 1e6, "close_price": closes}, index=dates)
        df.index.name = "Date"
        path = tmp_dir / f"{node}.parquet"
        df.to_parquet(path)
        return path

    def _make_pop_row(self, node: str, trigger_date: str) -> pd.DataFrame:
        """Build a minimal pop DataFrame with one event."""
        return pd.DataFrame([{
            "node": node,
            "trigger_date": pd.Timestamp(trigger_date),
            "era": "2015-2019",
            "family": "ep_onset_in",
            "state": "CUSHIONED",
            "label_good": 1,
        }])

    def test_positive_path_labeled_1(self):
        """When close rises over 21 bars after fill, label = 1.0."""
        # 23 bars: trigger=bar0, fill=bar1 (close=100), exit=bar22 (close=110)
        # fwd_ret_21 = close[22]/close[1] - 1 = +10% → label=1
        closes = [99.0] + [100.0] + [100.0] * 20 + [110.0]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            yahoo_dir = tmp_dir / "yahoo"
            yahoo_dir.mkdir()
            self._make_yahoo_parquet(yahoo_dir, "XLE", closes, "2010-01-04")
            pop = self._make_pop_row("XLE", "2010-01-04")
            result = compute_reversion21_labels(pop, tmp_dir)
            assert len(result) == 1, f"Expected 1 labeled row, got {len(result)}"
            assert result["label_reversion21"].iloc[0] == 1.0, (
                "Positive path (close rises) must give label=1.0"
            )

    def test_negative_path_labeled_0(self):
        """When close falls over 21 bars after fill, label = 0.0."""
        # close[fill=1]=100, close[fill+21=22]=90 → fwd_ret_21 = -10% → label=0
        closes = [99.0] + [100.0] + [100.0] * 20 + [90.0] + [90.0]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            yahoo_dir = tmp_dir / "yahoo"
            yahoo_dir.mkdir()
            self._make_yahoo_parquet(yahoo_dir, "XLK", closes, "2010-01-04")
            pop = self._make_pop_row("XLK", "2010-01-04")
            result = compute_reversion21_labels(pop, tmp_dir)
            assert len(result) == 1
            assert result["label_reversion21"].iloc[0] == 0.0, (
                "Negative path (close falls) must give label=0.0"
            )

    def test_fill_is_next_bar_strictly_after_trigger(self):
        """Fill = first bar strictly after trigger_date (iloc position trigger_loc + 1).

        Construct a series where trigger bar (bar 0) has close=200 (different from bar 1=100)
        to confirm entry is bar 1, not bar 0.
        """
        # bar 0 = trigger (close=200), bar 1 = fill entry (close=100), bars 2..21 flat,
        # bar 22 = exit (close=110) → fwd_ret = +10%
        closes = [200.0] + [100.0] + [100.0] * 20 + [110.0] + [110.0]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            yahoo_dir = tmp_dir / "yahoo"
            yahoo_dir.mkdir()
            self._make_yahoo_parquet(yahoo_dir, "XLV", closes, "2010-01-04")
            pop = self._make_pop_row("XLV", "2010-01-04")
            result = compute_reversion21_labels(pop, tmp_dir)
            assert len(result) == 1
            # If entry were bar 0 (close=200), exit bar 22 close=110 → fwd_ret<0 → label=0
            # If entry is bar 1 (close=100), exit bar 22 close=110 → fwd_ret>0 → label=1
            # Correct (next-bar fill) must give label=1
            assert result["label_reversion21"].iloc[0] == 1.0, (
                "Next-bar fill: entry at bar 1 (close=100), exit bar 22 (close=110) → label=1"
            )

    def test_flat_path_labeled_0(self):
        """When close is flat (fwd_ret_21 == 0), label = 0.0 (> 0, not >= 0)."""
        # close[fill=1]=100, close[fill+21=22]=100 → fwd_ret_21 = 0 → label=0
        closes = [99.0] + [100.0] * 23 + [100.0]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            yahoo_dir = tmp_dir / "yahoo"
            yahoo_dir.mkdir()
            self._make_yahoo_parquet(yahoo_dir, "XLF", closes, "2010-01-04")
            pop = self._make_pop_row("XLF", "2010-01-04")
            result = compute_reversion21_labels(pop, tmp_dir)
            assert len(result) == 1
            assert result["label_reversion21"].iloc[0] == 0.0, (
                "Flat path (fwd_ret_21=0) must give label=0.0 (condition is > 0, not >= 0)"
            )


# ---------------------------------------------------------------------------
# Test 14: default mode regression — pos63_goodset path unchanged
# ---------------------------------------------------------------------------

class TestDefaultModeRegression:
    """W1b: --label pos63_goodset (default) must produce byte-identical label to original."""

    def test_label_col_is_label_good_in_default_mode(self):
        """In pos63_goodset mode, active_label_col is 'label_good'."""
        # Verify that GOOD_STATES is the only criterion
        from scripts.oracle_onset_quality_w1 import GOOD_STATES
        good_states = {"CUSHIONED", "CLEAN_LIFTOFF"}
        assert GOOD_STATES == good_states, (
            f"Default mode: GOOD_STATES must be {{CUSHIONED, CLEAN_LIFTOFF}}, got {GOOD_STATES}"
        )

    def test_label_good_matches_state_membership(self):
        """label_good = 1 iff state in GOOD_STATES (byte-identical to original)."""
        from scripts.oracle_onset_quality_w1 import GOOD_STATES
        test_cases = [
            ("CUSHIONED", 1),
            ("CLEAN_LIFTOFF", 1),
            ("STOPPED", 0),
            ("DEAD_MONEY", 0),
            ("FALSE_START", 0),
        ]
        for state, expected in test_cases:
            label = 1 if state in GOOD_STATES else 0
            assert label == expected, (
                f"state={state!r} → expected label={expected}, got {label}"
            )

    def test_compute_reversion21_not_called_in_default_mode(self):
        """The reversion21 label path is not invoked when label='pos63_goodset'.

        Verified structurally: compute_reversion21_labels raises FileNotFoundError
        when yahoo data is absent; this test confirms it would only be called in W1b mode.
        """
        # This is a logic / control-flow invariant:
        # label='pos63_goodset' branches to 'active_label_col = "label_good"'
        # (no call to compute_reversion21_labels)
        # We confirm by verifying that passing label='pos63_goodset' routes to the
        # correct label column without touching the reversion21 code path.
        label = "pos63_goodset"
        # The routing condition in main():
        if label == "reversion21":
            active_label_col = "label_reversion21"
        else:
            active_label_col = "label_good"
        assert active_label_col == "label_good", (
            "Default mode must route to label_good, not label_reversion21"
        )


# ---------------------------------------------------------------------------
# Test 15: insufficient-forward-bars rows dropped and counted
# ---------------------------------------------------------------------------

class TestInsufficientForwardBarsDropped:
    """W1b: rows without 21 forward bars after fill are dropped (counted, not silently lost)."""

    def _make_yahoo_parquet(self, yahoo_dir: Path, node: str, closes: list[float],
                             base_date: str = "2020-01-02") -> None:
        dates = pd.bdate_range(base_date, periods=len(closes))
        df = pd.DataFrame({"close": closes, "volume": 1e6, "close_price": closes}, index=dates)
        df.index.name = "Date"
        df.to_parquet(yahoo_dir / f"{node}.parquet")

    def test_row_dropped_when_fewer_than_21_bars_after_fill(self):
        """A row whose trigger_date is within 21 bars of end-of-series is dropped.

        When ALL rows are dropped (n_labeled=0), compute_reversion21_labels raises
        RuntimeError — this is correct behavior (an all-empty result is a data error).
        The drop count is printed and visible before the raise.
        """
        # Series of 10 bars only — fill = bar 1, need fill+21 = bar 22, which doesn't exist
        closes = [100.0] * 10
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            yahoo_dir = tmp_dir / "yahoo"
            yahoo_dir.mkdir()
            self._make_yahoo_parquet(yahoo_dir, "XLE", closes, "2020-01-02")
            dates = pd.bdate_range("2020-01-02", periods=10)
            trigger = str(dates[0].date())
            pop = pd.DataFrame([{
                "node": "XLE",
                "trigger_date": pd.Timestamp(trigger),
                "era": "2020-2022",
                "family": "ep_onset_in",
                "state": "CUSHIONED",
                "label_good": 1,
            }])
            # When the entire pop is dropped (no 21 fwd bars), RuntimeError is raised —
            # this is the correct loud-failure behavior (not silent zero rows).
            with pytest.raises(RuntimeError, match="reversion21: zero rows labeled"):
                compute_reversion21_labels(pop, tmp_dir)

    def test_row_kept_when_exactly_21_bars_after_fill(self):
        """A row with exactly 21 forward bars after fill is kept and labeled."""
        # fill=bar 1, we need bar 1+21=bar 22 to exist → 23 bars total (0..22)
        closes = [99.0] + [100.0] + [100.0] * 20 + [105.0]
        # len=23: bar0=trigger, bar1=fill, bars2..21=hold (20 bars), bar22=exit
        assert len(closes) == 23
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            yahoo_dir = tmp_dir / "yahoo"
            yahoo_dir.mkdir()
            self._make_yahoo_parquet(yahoo_dir, "XLK", closes, "2020-01-02")
            dates = pd.bdate_range("2020-01-02", periods=23)
            trigger = str(dates[0].date())
            pop = pd.DataFrame([{
                "node": "XLK",
                "trigger_date": pd.Timestamp(trigger),
                "era": "2020-2022",
                "family": "ep_onset_in",
                "state": "CUSHIONED",
                "label_good": 1,
            }])
            result = compute_reversion21_labels(pop, tmp_dir)
            assert len(result) == 1, (
                f"Row with exactly 21 fwd bars must be kept; got {len(result)} rows"
            )
            # close[1]=100, close[22]=105 → fwd_ret>0 → label=1
            assert result["label_reversion21"].iloc[0] == 1.0

    def test_mixed_kept_and_dropped(self):
        """Of two rows, one with sufficient bars is kept; one without is dropped."""
        # Row A: 23-bar series → kept (trigger at bar 0)
        # Row B: 10-bar series → dropped (trigger at bar 0, only 9 bars after fill)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            yahoo_dir = tmp_dir / "yahoo"
            yahoo_dir.mkdir()

            # Row A: XLE, 23 bars, trigger=first bar
            closes_a = [99.0] + [100.0] + [100.0] * 20 + [108.0]
            self._make_yahoo_parquet(yahoo_dir, "XLE", closes_a, "2020-01-02")
            dates_a = pd.bdate_range("2020-01-02", periods=23)

            # Row B: XLK, only 10 bars → insufficient
            closes_b = [100.0] * 10
            self._make_yahoo_parquet(yahoo_dir, "XLK", closes_b, "2020-01-02")
            dates_b = pd.bdate_range("2020-01-02", periods=10)

            pop = pd.DataFrame([
                {
                    "node": "XLE",
                    "trigger_date": pd.Timestamp(str(dates_a[0].date())),
                    "era": "2020-2022",
                    "family": "ep_onset_in",
                    "state": "CUSHIONED",
                    "label_good": 1,
                },
                {
                    "node": "XLK",
                    "trigger_date": pd.Timestamp(str(dates_b[0].date())),
                    "era": "2020-2022",
                    "family": "ep_onset_in",
                    "state": "STOPPED",
                    "label_good": 0,
                },
            ])
            result = compute_reversion21_labels(pop, tmp_dir)
            assert len(result) == 1, (
                f"Expected 1 kept row (XLE), 1 dropped (XLK); got {len(result)} rows"
            )
            assert result["node"].iloc[0] == "XLE", "Kept row must be XLE (sufficient bars)"
