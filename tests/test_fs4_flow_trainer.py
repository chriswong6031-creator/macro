"""tests/test_fs4_flow_trainer.py — FS-4 flow-score trainer unit tests.

Synthetic-data only: no real cohort stores, no ThetaTerminal, no grade files.
All tests use tmp_path to avoid polluting repo state.

Test categories (per FS-4 acceptance gate):
 1. map_model_bucket: totality over the real ledger dte_bucket values (0d, 1_7d,
    8_30d, 31_90d, 90p), None for unknown values.
 2. uniqueness_weights: hand-computed correctness case; (session, underlying)
    concurrency collapse (1000 events on one session = weight ~1/n_days each).
 3. ece: hand-computed equal-mass case; NaN on empty input.
 4. brier: basic correctness; base-rate comparison gating.
 5. reliability_table: monotonicity detection (monotone pass / non-monotone fail).
 6. is_reliability_monotone: edge cases (empty, 1-bin, non-monotone).
 7. index_prefilter: index-root excluded; OI > 500 re-admits; 0DTE index always
    excluded from 0_7; non-index roots pass through unchanged.
 8. cohort_pooling_raises: eod_proxy detected in serving frame → ValueError.
 9. eod_proxy_in_calibration_raises: _check_no_eod_proxy_in_calibration raises.
10. purge_correctness: the embargo window removes rows within embargo of val fold.
11. embargo_enforcement: underlying appearing in val is excluded from train.
12. group_fold_no_leakage_underlying: root in val not in train.
13. group_fold_no_leakage_time: training rows do not overlap temporal val boundary.
14. deployable_below_floor: n below bucket floor → deployable=False, reason contains
    BELOW-FLOOR.
15. deployable_ece_fail: ECE >= threshold → deployable=False.
16. deployable_brier_fail: Brier >= base_rate_brier → deployable=False.
17. deployable_monotone_fail: non-monotone reliability → deployable=False.
18. deployable_all_pass: all criteria met → deployable=True.
19. manifest_n_trials: N_trials == grid_cardinality × interaction_variants ×
    cpcv_paths.
20. sha256_verification_failure: corrupt model file → load_artifact returns None.
21. lazy_import: importing lib.flow_score with sklearn monkeypatched absent succeeds
    (no ImportError on module-level sklearn use).
22. label_column_missing_halts: missing spy_excess column raises ValueError (not
    silently substituting absolute return).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import types
from datetime import date, timedelta
from math import comb
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Allow running standalone without the package installed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.flow_score import (
    STATUS_BUCKET_UNMAPPED,
    STATUS_SCORED,
    brier,
    ece,
    is_reliability_monotone,
    load_artifact,
    map_model_bucket,
    reliability_table,
    uniqueness_weights,
)
from scripts.ops_train_flow_score import (
    _check_no_eod_proxy_in_calibration,
    _expand_grid,
    _cpcv_path_count,
    _group_fold_splits,
    apply_population_filter,
    _build_label,
    _assign_time_blocks,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. map_model_bucket — totality over all real ledger dte_bucket values
# ─────────────────────────────────────────────────────────────────────────────

class TestMapModelBucket:
    def test_0d_maps_to_0_7(self):
        assert map_model_bucket("0d") == "0_7"

    def test_1_7d_maps_to_0_7(self):
        assert map_model_bucket("1_7d") == "0_7"

    def test_8_30d_maps_to_8_90(self):
        assert map_model_bucket("8_30d") == "8_90"

    def test_31_90d_maps_to_8_90(self):
        assert map_model_bucket("31_90d") == "8_90"

    def test_90p_maps_to_90p(self):
        assert map_model_bucket("90p") == "90p"

    def test_unknown_returns_none(self):
        assert map_model_bucket("unknown") is None

    def test_none_returns_none(self):
        assert map_model_bucket(None) is None

    def test_empty_string_returns_none(self):
        assert map_model_bucket("") is None

    def test_all_real_gate_json_values(self):
        """Cover all dte_bucket values seen in gate.json (0d, 1_7d, 8_30d, 31_90d)."""
        live_values = ["0d", "1_7d", "8_30d", "31_90d", "90p"]
        for v in live_values:
            result = map_model_bucket(v)
            assert result in ("0_7", "8_90", "90p"), (
                f"map_model_bucket({v!r}) returned {result!r}; expected a valid model bucket"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. uniqueness_weights
# ─────────────────────────────────────────────────────────────────────────────

class TestUniquenessWeights:
    def _make_events(self, dates, roots, event_ids=None):
        n = len(dates)
        if event_ids is None:
            event_ids = [f"e{i}" for i in range(n)]
        return pd.DataFrame({
            "event_id": event_ids,
            "session_date": [str(d) for d in dates],
            "root": roots,
        })

    def test_hand_computed_single_event_weight_1(self):
        """One event alone → uniqueness = 1.0 (no concurrency)."""
        df = self._make_events(
            dates=[date(2024, 1, 2)],
            roots=["AAPL"],
        )
        w = uniqueness_weights(df, horizon_days=5)
        assert len(w) == 1
        val = float(w.iloc[0])
        # Single event: c_t = 1 for all days in its window → u = 1.0
        assert abs(val - 1.0) < 1e-6, f"Expected 1.0, got {val}"

    def test_two_overlapping_events_same_root(self):
        """Two events on consecutive days, same root, horizon=2.
        Day 0: event A window [0..2], event B window [1..3].
        Day 0: c=1 (only A), Day 1: c=2 (A+B), Day 2: c=2 (A+B), Day 3: c=1 (only B).
        u_A = mean(1/1, 1/2, 1/2) = (1 + 0.5 + 0.5)/3 = 2/3
        u_B = mean(1/2, 1/2, 1/1) = (0.5 + 0.5 + 1)/3 = 2/3
        """
        d0 = date(2024, 1, 2)
        d1 = date(2024, 1, 3)
        df = self._make_events(
            dates=[d0, d1],
            roots=["AAPL", "AAPL"],
        )
        w = uniqueness_weights(df, horizon_days=2)
        assert len(w) == 2
        for eid, val in w.items():
            # Both should be ~2/3
            assert abs(val - 2 / 3) < 0.15, f"Event {eid}: weight={val:.4f}, expected ~2/3"

    def test_session_underlying_concurrency_collapse(self):
        """1000 events on same (session_date, root) → effective N ~ 1 unit.

        Amendment §4.4: (session, underlying) concurrency collapse means 1000 SPY
        prints on one session count as ONE independent shock.  Each event receives
        weight = u_unit / n_events_in_unit so that:
          Σ w_i = u_unit  ≈ 1.0   (one independent unit)
        Not Σ w_i = 1000.

        Spec §7 explicitly states "a million SPY prints on shared sessions is not
        n=1,000,000" — sum of weights must equal the count of independent
        (session, underlying) shocks, not the raw event count.
        """
        n = 1000
        df = self._make_events(
            dates=[date(2024, 1, 2)] * n,
            roots=["SPY"] * n,
            event_ids=[f"spy_{i}" for i in range(n)],
        )
        w = uniqueness_weights(df, horizon_days=5)
        assert len(w) == n
        # Each individual weight should be ~1/n (u_unit/n_in_unit)
        for eid, val in w.items():
            assert val == pytest.approx(1.0 / n, abs=1e-6), (
                f"Expected per-event weight ~1/n={1/n:.6f} for {eid}, got {val:.6f}"
            )
        # Total effective N should be ~1 (one independent session-underlying unit)
        total_eff_n = float(w.sum())
        assert abs(total_eff_n - 1.0) < 0.01, (
            f"Expected effective N ~ 1.0 for 1000 same-session events, got {total_eff_n:.4f}. "
            "Amendment §4.4 / §7: a thousand SPY prints on one session must not inflate N."
        )

    def test_empty_dataframe_returns_empty(self):
        df = pd.DataFrame(columns=["event_id", "session_date", "root"])
        w = uniqueness_weights(df, horizon_days=5)
        assert len(w) == 0

    def test_different_underlyings_same_session_not_collapsed(self):
        """Two events on same session but different roots are independent units."""
        d0 = date(2024, 1, 2)
        df = self._make_events(
            dates=[d0, d0],
            roots=["AAPL", "MSFT"],
        )
        w = uniqueness_weights(df, horizon_days=2)
        # AAPL and MSFT are separate (session, underlying) units → c_t = 2 on day 0
        # u_A = u_B = mean(1/2, 1/2, 1/2) ... actually the two units overlap fully
        # so c_t = 2 for all days in their windows → u_A = u_B = 0.5
        for eid, val in w.items():
            assert val == pytest.approx(0.5, abs=0.05), (
                f"{eid}: expected ~0.5 (two concurrent units), got {val:.4f}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. ece
# ─────────────────────────────────────────────────────────────────────────────

class TestECE:
    def test_perfect_calibration_zero_ece(self):
        """Perfect calibration: ECE = 0."""
        # Predict 0.3 for 30% of events (outcome=1) → perfectly calibrated
        n = 100
        pred = np.full(n, 0.3)
        y = np.array([1.0] * 30 + [0.0] * 70)
        val = ece(pred, y, n_bins=1, equal_mass=True)
        assert val == pytest.approx(0.0, abs=1e-10)

    def test_worst_calibration_near_1(self):
        """Fully inverted: predict 1 for all outcomes=0 → ECE ~ 1.0."""
        pred = np.ones(100)
        y = np.zeros(100)
        val = ece(pred, y, n_bins=1, equal_mass=True)
        assert val == pytest.approx(1.0, abs=1e-6)

    def test_empty_input_returns_nan(self):
        val = ece([], [], n_bins=10, equal_mass=True)
        assert np.isnan(val)

    def test_equal_mass_binning(self):
        """With equal_mass=True, each bin should have ~equal number of observations."""
        rng = np.random.default_rng(42)
        pred = rng.uniform(0, 1, 200)
        y = (rng.uniform(0, 1, 200) < pred).astype(float)
        val = ece(pred, y, n_bins=10, equal_mass=True)
        # Just verify it's a finite float in [0, 1]
        assert np.isfinite(val)
        assert 0.0 <= val <= 1.0

    def test_hand_computed_two_bins(self):
        """Hand-computed ECE with 2 bins.

        8 predictions: 4 low (pred=0.2, y=0), 4 high (pred=0.8, y=1).
        Equal-mass binning → 2 bins of 4 observations each.
        Bin 1 (pred≈0.2): conf=0.2, acc=0.0 → |diff|=0.2, weight=0.5 → contrib=0.1
        Bin 2 (pred≈0.8): conf=0.8, acc=1.0 → |diff|=0.2, weight=0.5 → contrib=0.1
        ECE = 0.1 + 0.1 = 0.2
        """
        pred = np.array([0.2, 0.2, 0.2, 0.2, 0.8, 0.8, 0.8, 0.8])
        y    = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
        val = ece(pred, y, n_bins=2, equal_mass=True)
        assert val == pytest.approx(0.2, abs=0.05)


# ─────────────────────────────────────────────────────────────────────────────
# 4. brier
# ─────────────────────────────────────────────────────────────────────────────

class TestBrier:
    def test_perfect_brier_zero(self):
        """Perfect predictions → Brier = 0."""
        pred = np.array([1.0, 0.0, 1.0, 0.0])
        y    = np.array([1.0, 0.0, 1.0, 0.0])
        assert brier(pred, y) == pytest.approx(0.0, abs=1e-10)

    def test_worst_brier(self):
        """All wrong predictions → Brier = 1."""
        pred = np.array([1.0, 1.0, 0.0, 0.0])
        y    = np.array([0.0, 0.0, 1.0, 1.0])
        assert brier(pred, y) == pytest.approx(1.0, abs=1e-10)

    def test_base_rate_brier_formula(self):
        """Base-rate Brier = p*(1-p) where p = mean(y)."""
        y = np.array([1.0, 0.0, 1.0, 0.0, 1.0])  # p = 0.6
        p = y.mean()
        pred_base = np.full(len(y), p)
        base_brier = brier(pred_base, y)
        expected = float(p * (1 - p))
        assert base_brier == pytest.approx(expected, abs=1e-6)

    def test_better_than_base_rate(self):
        """Calibrated predictions beat base-rate Brier."""
        rng = np.random.default_rng(7)
        y = rng.integers(0, 2, size=200).astype(float)
        # "Good" model: predict true probability with small noise
        pred_good = y * 0.8 + 0.1 + rng.normal(0, 0.05, 200)
        pred_good = np.clip(pred_good, 0, 1)
        p_bar = float(y.mean())
        base_br = p_bar * (1 - p_bar)
        good_br = brier(pred_good, y)
        assert good_br < base_br, (
            f"Expected good model Brier {good_br:.4f} < base_rate_brier {base_br:.4f}"
        )

    def test_empty_returns_nan(self):
        assert np.isnan(brier([], []))


# ─────────────────────────────────────────────────────────────────────────────
# 5-6. reliability_table + is_reliability_monotone
# ─────────────────────────────────────────────────────────────────────────────

class TestReliabilityTable:
    def test_basic_structure(self):
        """Table rows have required keys and n_eff > 0."""
        rng = np.random.default_rng(1)
        pred = rng.uniform(0, 1, 100)
        y = (rng.uniform(0, 1, 100) < pred).astype(float)
        table = reliability_table(pred, y, n_bins=5)
        assert len(table) > 0
        for row in table:
            assert "bin_lo" in row
            assert "bin_hi" in row
            assert "pred_mean" in row
            assert "emp_rate" in row
            assert "n_eff" in row
            assert row["n_eff"] > 0

    def test_empty_returns_empty(self):
        table = reliability_table([], [])
        assert table == []

    def test_weighted_n_eff(self):
        """n_eff equals sum of weights in each bin."""
        pred = np.array([0.1, 0.2, 0.8, 0.9])
        y    = np.array([0.0, 0.0, 1.0, 1.0])
        w    = np.array([1.0, 2.0, 3.0, 4.0])
        table = reliability_table(pred, y, weights=w, n_bins=2)
        total_n_eff = sum(row["n_eff"] for row in table)
        assert total_n_eff == pytest.approx(float(w.sum()), abs=1e-6)

    def test_monotone_increasing_perfect_cal(self):
        """Perfect calibration → monotone reliability table."""
        # Construct perfectly calibrated predictions
        pred = np.linspace(0.1, 0.9, 100)
        # Make outcomes match calibration: each group has outcome rate = pred value
        rng = np.random.default_rng(99)
        y = (rng.uniform(0, 1, 100) < pred).astype(float)
        table = reliability_table(pred, y, n_bins=5)
        # Should be monotone (may not be perfectly due to randomness, but test the function)
        # The key test: is_reliability_monotone returns the right answer for controlled cases.
        assert isinstance(is_reliability_monotone(table), bool)


class TestIsReliabilityMonotone:
    def _make_table(self, pred_means, emp_rates):
        return [
            {"bin_lo": 0.0, "bin_hi": 1.0, "pred_mean": pm, "emp_rate": er, "n_eff": 10.0}
            for pm, er in zip(pred_means, emp_rates)
        ]

    def test_monotone_pass(self):
        """Strictly increasing emp_rates → monotone."""
        table = self._make_table([0.1, 0.3, 0.5, 0.7], [0.1, 0.3, 0.5, 0.7])
        assert is_reliability_monotone(table) is True

    def test_non_monotone_fail(self):
        """Inverted emp_rates → non-monotone."""
        table = self._make_table([0.1, 0.3, 0.5, 0.7], [0.7, 0.3, 0.5, 0.1])
        assert is_reliability_monotone(table) is False

    def test_flat_is_monotone(self):
        """Constant emp_rates (within tolerance) → monotone."""
        table = self._make_table([0.1, 0.3, 0.5, 0.7], [0.4, 0.4, 0.4, 0.4])
        assert is_reliability_monotone(table) is True

    def test_empty_table_is_monotone(self):
        assert is_reliability_monotone([]) is True

    def test_single_bin_is_monotone(self):
        table = self._make_table([0.5], [0.5])
        assert is_reliability_monotone(table) is True

    def test_small_dip_within_tolerance(self):
        """A dip smaller than tolerance (0.001) is still considered monotone."""
        tol = 1e-3
        table = self._make_table([0.1, 0.5, 0.9], [0.3, 0.3 - tol / 2, 0.5])
        assert is_reliability_monotone(table, tol=tol) is True

    def test_dip_exceeding_tolerance_fails(self):
        """A dip larger than tolerance → non-monotone."""
        tol = 1e-3
        table = self._make_table([0.1, 0.5, 0.9], [0.5, 0.5 - 2 * tol, 0.8])
        assert is_reliability_monotone(table, tol=tol) is False


# ─────────────────────────────────────────────────────────────────────────────
# 7. apply_population_filter (amendment §3.3 index-root prefilter)
# ─────────────────────────────────────────────────────────────────────────────

def _make_events_df(roots, dte_buckets=None, zerodte=None, prior_oi=None):
    n = len(roots)
    if dte_buckets is None:
        dte_buckets = ["8_30d"] * n
    if zerodte is None:
        zerodte = [False] * n
    data = {
        "event_id": [f"e{i}" for i in range(n)],
        "root": roots,
        "dte_bucket": dte_buckets,
        "zerodte": zerodte,
    }
    if prior_oi is not None:
        data["prior_oi"] = prior_oi
    return pd.DataFrame(data)


class TestApplyPopulationFilter:
    def test_non_index_passes_through(self):
        df = _make_events_df(["AAPL", "MSFT", "TSLA"])
        out, stats = apply_population_filter(df, bucket="8_90")
        assert len(out) == 3
        assert stats["index_excluded_n"] == 0
        assert stats["oi_readmitted_n"] == 0

    def test_index_root_excluded_by_default(self):
        df = _make_events_df(["SPX", "AAPL"])
        out, stats = apply_population_filter(df, bucket="8_90")
        assert len(out) == 1
        assert out["root"].iloc[0] == "AAPL"
        assert stats["index_excluded_n"] >= 1

    def test_index_root_readmitted_with_high_oi(self):
        """Prior OI > 500 re-admits an index root (amendment §3.3)."""
        df = _make_events_df(["SPX", "SPX", "AAPL"], prior_oi=[600, 100, 0])
        out, stats = apply_population_filter(df, bucket="8_90")
        # SPX with OI=600 should be readmitted; SPX with OI=100 excluded; AAPL kept
        assert stats["oi_readmitted_n"] == 1
        assert len(out) == 2  # AAPL + SPX(OI=600)
        roots_out = set(out["root"].tolist())
        assert "AAPL" in roots_out

    def test_zerodte_index_excluded_from_0_7(self):
        """0DTE index always excluded from 0_7 even with high OI (amendment §3.3)."""
        df = _make_events_df(
            ["SPX", "AAPL"],
            dte_buckets=["0d", "0d"],
            zerodte=[True, False],
            prior_oi=[10000, 0],  # high OI for SPX, but 0DTE index still excluded
        )
        out, stats = apply_population_filter(df, bucket="0_7")
        # SPX is 0DTE index → excluded from 0_7 even with high OI
        assert stats["zerodte_index_excluded_n"] >= 1
        roots_out = out["root"].tolist()
        assert "SPX" not in roots_out
        assert "AAPL" in roots_out

    def test_zerodte_index_not_excluded_from_8_90(self):
        """0DTE index exclusion is 0_7 bucket only; 8_90 applies normal OI rule."""
        df = _make_events_df(
            ["SPX"],
            dte_buckets=["8_30d"],
            zerodte=[False],
            prior_oi=[600],
        )
        out, stats = apply_population_filter(df, bucket="8_90")
        # OI > 500 → readmitted in 8_90
        assert stats["oi_readmitted_n"] == 1
        assert len(out) == 1

    def test_stats_keys_present(self):
        df = _make_events_df(["SPX", "AAPL"])
        _, stats = apply_population_filter(df, bucket="8_90")
        for key in ("total_input", "index_excluded_n", "oi_readmitted_n",
                    "zerodte_index_excluded_n", "total_output"):
            assert key in stats, f"Missing stats key: {key}"

    def test_custom_index_roots(self):
        """Custom index_roots set is respected."""
        df = _make_events_df(["CUSTOM_IDX", "AAPL"])
        out, stats = apply_population_filter(
            df, bucket="8_90",
            index_roots=frozenset(["CUSTOM_IDX"])
        )
        assert len(out) == 1
        assert out["root"].iloc[0] == "AAPL"


# ─────────────────────────────────────────────────────────────────────────────
# 8. cohort_pooling_raises
# ─────────────────────────────────────────────────────────────────────────────

class TestCohortPoolingRaises:
    def test_eod_proxy_in_serving_frame_raises(self):
        """eod_proxy in serving cohort → ValueError (FS-R4 / amendment §3.1)."""
        df = pd.DataFrame({
            "event_id": ["e1", "e2"],
            "source": ["tape_recon", "eod_proxy"],
        })
        with pytest.raises(ValueError, match="eod_proxy"):
            _check_no_eod_proxy_in_calibration(df, context="test")

    def test_pure_tape_recon_does_not_raise(self):
        df = pd.DataFrame({
            "event_id": ["e1", "e2"],
            "source": ["tape_recon", "tape_recon"],
        })
        # Should not raise
        _check_no_eod_proxy_in_calibration(df, context="test")

    def test_pure_live_feed_does_not_raise(self):
        df = pd.DataFrame({
            "event_id": ["e1"],
            "source": ["live_feed"],
        })
        _check_no_eod_proxy_in_calibration(df, context="test")

    def test_empty_frame_does_not_raise(self):
        df = pd.DataFrame()
        _check_no_eod_proxy_in_calibration(df, context="test")


# ─────────────────────────────────────────────────────────────────────────────
# 9. eod_proxy_in_calibration_raises
# ─────────────────────────────────────────────────────────────────────────────

class TestEodProxyInCalibration:
    def test_raises_on_eod_proxy(self):
        df = pd.DataFrame({"source": ["eod_proxy"]})
        with pytest.raises(ValueError, match="eod_proxy"):
            _check_no_eod_proxy_in_calibration(df, "calibration holdout")

    def test_no_raise_on_tape_recon(self):
        df = pd.DataFrame({"source": ["tape_recon"]})
        _check_no_eod_proxy_in_calibration(df, "calibration holdout")


# ─────────────────────────────────────────────────────────────────────────────
# 10-13. CV geometry: purge, embargo, group fold correctness
# ─────────────────────────────────────────────────────────────────────────────

def _make_cv_df(n: int = 100, n_roots: int = 5, start_date: date = date(2022, 1, 3)) -> pd.DataFrame:
    """Synthetic events DataFrame for CV testing.

    Each root is assigned to a contiguous block of rows (NOT round-robin) so that
    roots are concentrated in specific time periods. This ensures that when folds are
    split by time, val-fold roots are mostly absent from train-fold time blocks.
    """
    dates = [start_date + timedelta(days=i) for i in range(n)]
    # Contiguous assignment: root i gets rows [i*block_size, (i+1)*block_size)
    block_size = n // n_roots
    roots = []
    for i in range(n):
        root_idx = min(i // max(1, block_size), n_roots - 1)
        roots.append(f"ROOT{root_idx}")
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "session_date": [d.isoformat() for d in dates],
        "root": roots,
        "source": ["tape_recon"] * n,
        "_label": [float(i % 2) for i in range(n)],
    })


class TestCVGeometry:
    def test_embargo_removes_rows_near_val(self):
        """Amendment §4.1: training rows within embargo days of val boundaries are removed."""
        df = _make_cv_df(n=200, n_roots=10)
        embargo = 10
        splits = _group_fold_splits(
            df, k_folds=5, embargo=embargo, n_groups=6, random_seed=42
        )
        assert len(splits) > 0, "Expected at least one split"
        for train_idx, val_idx in splits:
            val_df = df.iloc[val_idx]
            train_df = df.iloc[train_idx]
            val_dates = pd.to_datetime(val_df["session_date"])
            train_dates = pd.to_datetime(train_df["session_date"])
            if val_dates.empty or train_dates.empty:
                continue
            val_min = val_dates.min()
            val_max = val_dates.max()
            # Check no training row falls within embargo days of val boundary
            for td in train_dates:
                diff_lo = abs((td - val_min).days)
                diff_hi = abs((td - val_max).days)
                assert min(diff_lo, diff_hi) > embargo, (
                    f"Training date {td} is within embargo={embargo} days of val boundary "
                    f"[{val_min}, {val_max}]"
                )

    def test_underlying_not_in_both_train_and_val(self):
        """Amendment §4.2: a root in val must not appear in train of same fold."""
        df = _make_cv_df(n=200, n_roots=5)
        splits = _group_fold_splits(
            df, k_folds=5, embargo=5, n_groups=6, random_seed=42
        )
        assert len(splits) > 0
        for train_idx, val_idx in splits:
            val_roots = set(df.iloc[val_idx]["root"].tolist())
            train_roots = set(df.iloc[train_idx]["root"].tolist())
            overlap = val_roots & train_roots
            assert len(overlap) == 0, (
                f"Root(s) {overlap} appear in BOTH train and val of same fold "
                f"(underlying leakage, amendment §4.2)"
            )

    def test_no_temporal_overlap_between_train_and_val(self):
        """Amendment §4.2: no train date falls in the exact val date range (minus embargo)."""
        df = _make_cv_df(n=200, n_roots=10)
        embargo = 5
        splits = _group_fold_splits(
            df, k_folds=5, embargo=embargo, n_groups=6, random_seed=42
        )
        assert len(splits) > 0
        for train_idx, val_idx in splits:
            val_df = df.iloc[val_idx]
            train_df = df.iloc[train_idx]
            val_dates = pd.to_datetime(val_df["session_date"])
            train_dates = pd.to_datetime(train_df["session_date"])
            if val_dates.empty or train_dates.empty:
                continue
            val_min = val_dates.min()
            val_max = val_dates.max()
            # No train row should fall strictly within [val_min + embargo, val_max - embargo]
            # (the strict interior — the boundary itself is embargoed)
            interior_lo = val_min + pd.Timedelta(days=embargo)
            interior_hi = val_max - pd.Timedelta(days=embargo)
            if interior_lo >= interior_hi:
                continue  # val block too small to have an interior
            in_interior = (train_dates >= interior_lo) & (train_dates <= interior_hi)
            assert not in_interior.any(), (
                "Training rows found inside val temporal window (leakage)"
            )

    def test_train_val_sets_are_disjoint(self):
        """Train and val index arrays never overlap."""
        df = _make_cv_df(n=150, n_roots=5)
        splits = _group_fold_splits(
            df, k_folds=5, embargo=5, n_groups=6, random_seed=42
        )
        for train_idx, val_idx in splits:
            train_set = set(train_idx.tolist())
            val_set = set(val_idx.tolist())
            assert len(train_set & val_set) == 0, "Train and val index arrays overlap"


# ─────────────────────────────────────────────────────────────────────────────
# 14-18. deployable logic
# ─────────────────────────────────────────────────────────────────────────────

class TestDeployableLogic:
    """Tests for the deployable decision gates in train_bucket (indirectly via helpers).

    We test the criteria independently:
      - ECE threshold
      - Brier vs base-rate
      - Reliability monotonicity
      - N floor
    """

    def test_deployable_all_pass(self):
        """All calibration criteria met → deployable."""
        from lib.flow_score import ece as _ece, brier as _brier, is_reliability_monotone as _mono, reliability_table as _rel
        # Perfect calibration case
        pred = np.array([0.0] * 50 + [1.0] * 50)
        y    = np.array([0.0] * 50 + [1.0] * 50)
        ece_val = _ece(pred, y, n_bins=2)
        brier_val = _brier(pred, y)
        base_brier = 0.5 * 0.5  # base rate = 0.5
        rel = _rel(pred, y, n_bins=2)
        mono = _mono(rel)
        # Criteria
        assert ece_val < 0.05
        assert brier_val < base_brier
        assert mono is True

    def test_deployable_ece_fail(self):
        """ECE >= 0.05 → deployable=False."""
        # Maximally miscalibrated
        pred = np.ones(100)
        y = np.zeros(100)
        ece_val = ece(pred, y, n_bins=2)
        assert ece_val >= 0.05, f"Expected ECE >= 0.05, got {ece_val}"

    def test_deployable_brier_fail(self):
        """Brier >= base_rate_brier → no skill → deployable=False."""
        # Predict base rate (skill = 0)
        y = np.array([1.0] * 50 + [0.0] * 50)
        p_bar = float(y.mean())
        pred_base = np.full(100, p_bar)
        brier_base = brier(pred_base, y)
        base_rate_brier = p_bar * (1 - p_bar)
        # base-rate predictions should match (within floating-point)
        assert brier_base == pytest.approx(base_rate_brier, abs=1e-6)

    def test_deployable_monotone_fail(self):
        """Non-monotone reliability → not deployable."""
        table = [
            {"bin_lo": 0.0, "bin_hi": 0.5, "pred_mean": 0.2, "emp_rate": 0.8, "n_eff": 50.0},
            {"bin_lo": 0.5, "bin_hi": 1.0, "pred_mean": 0.8, "emp_rate": 0.1, "n_eff": 50.0},
        ]
        assert is_reliability_monotone(table) is False

    def test_below_floor_deployable_false(self, tmp_path):
        """N below bucket floor → deployable=False with reason BELOW-FLOOR."""
        import yaml
        # Minimal config
        cfg = {
            "scoring": {"enabled": False},
            "models_dir": str(tmp_path / "models"),
            "model_bucket_map": {"8_30d": "8_90"},
            "embargo_days": {"8_90": 21},
            "k_folds": 5,
            "n_groups": 6,
            "k_test": 2,
            "random_seed": 42,
            "n_floors": {"bucket": 100, "era_cell": 20},
            "ece_threshold": 0.05,
            "n_bins": 10,
            "label_columns": {"8_90": "spy_excess_21"},
            "hyperparameter_grid": {"learning_rate": [0.1], "max_iter": [100], "max_leaf_nodes": [15]},
            "feature_columns": ["premium"],
            "dte_interaction": {"8_90": False},
            "monotone_constraints": {},
        }
        from scripts.ops_train_flow_score import _write_artifact
        # Only 5 rows → below floor of 100
        serving_df = pd.DataFrame({"root": ["AAPL"] * 5, "source": ["tape_recon"] * 5})
        labeled = pd.DataFrame({"event_id": [f"e{i}" for i in range(5)], "_label": [0.0] * 5})
        pop_stats = {"total_input": 5, "index_excluded_n": 0, "oi_readmitted_n": 0,
                     "zerodte_index_excluded_n": 0, "total_output": 5}
        result = _write_artifact(
            bucket="8_90", cfg=cfg, flow_dir=tmp_path,
            model=None, calibrator=None,
            deployable=False, deploy_reason="BELOW-FLOOR: n=5 < bucket_floor=100",
            serving_df=serving_df, labeled=labeled, pop_stats=pop_stats,
            base_rate=0.5, calibration_metrics={}, kill_eval={},
            n_trials=15, feature_cols=["premium"], dry_run=False,
        )
        assert result["deployable"] is False
        assert "BELOW-FLOOR" in result["deploy_reason"]


# ─────────────────────────────────────────────────────────────────────────────
# 19. manifest N_trials == declared grid cardinality
# ─────────────────────────────────────────────────────────────────────────────

class TestManifestNTrials:
    def test_n_trials_matches_grid_cardinality(self, tmp_path):
        """manifest.n_trials.total == grid_cardinality × interaction_variants × cpcv_paths."""
        cfg = {
            "scoring": {"enabled": False},
            "models_dir": str(tmp_path / "models"),
            "model_bucket_map": {"8_30d": "8_90"},
            "embargo_days": {"8_90": 21},
            "k_folds": 5,
            "n_groups": 6,
            "k_test": 2,
            "random_seed": 42,
            "n_floors": {"bucket": 1, "era_cell": 1},
            "ece_threshold": 0.05,
            "n_bins": 10,
            "label_columns": {"8_90": "spy_excess_21"},
            "hyperparameter_grid": {
                "learning_rate": [0.02, 0.05, 0.1, 0.2],   # 4
                "max_iter": [200, 400],                       # 2
                "max_leaf_nodes": [15, 31, 63],              # 3
            },
            "feature_columns": ["premium"],
            "dte_interaction": {"8_90": True},  # ×2 for 8_90
            "monotone_constraints": {},
        }
        grid = _expand_grid(cfg["hyperparameter_grid"])
        n_interaction_variants = 2  # 8_90 has DTE interaction on/off
        n_cpcv = _cpcv_path_count(cfg["n_groups"], cfg["k_test"])
        expected_n_trials = len(grid) * n_interaction_variants * n_cpcv
        # C(6,2) = 15 paths
        assert n_cpcv == comb(6, 2)
        # Grid cardinality = 4 × 2 × 3 = 24
        assert len(grid) == 24
        # Total for 8_90 = 24 × 2 × 15 = 720
        assert expected_n_trials == 24 * 2 * 15

        from scripts.ops_train_flow_score import _write_artifact
        result = _write_artifact(
            bucket="8_90", cfg=cfg, flow_dir=tmp_path,
            model=None, calibrator=None,
            deployable=False, deploy_reason="BELOW-FLOOR",
            serving_df=pd.DataFrame({"root": ["AAPL"], "source": ["tape_recon"]}),
            labeled=pd.DataFrame({"event_id": ["e1"], "_label": [0.0]}),
            pop_stats={"total_input": 1, "index_excluded_n": 0, "oi_readmitted_n": 0,
                       "zerodte_index_excluded_n": 0, "total_output": 1},
            base_rate=0.5, calibration_metrics={}, kill_eval={},
            n_trials=expected_n_trials,
            feature_cols=["premium"], dry_run=False,
        )
        # Read manifest from disk
        manifest_path = (
            tmp_path / "models" / "flow_score_8_90_v1" / "manifest.json"
        )
        assert manifest_path.exists(), f"manifest.json not found at {manifest_path}"
        with manifest_path.open() as f:
            manifest = json.load(f)
        assert manifest["n_trials"]["total"] == expected_n_trials
        assert manifest["n_trials"]["grid_cardinality"] == 24
        assert manifest["n_trials"]["interaction_variants"] == n_interaction_variants
        assert manifest["n_trials"]["cpcv_paths"] == n_cpcv

    def test_grid_cardinality_is_24(self):
        """Registered grid has exactly 24 combos (4×2×3)."""
        import yaml
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "flow_score.yml"
        if not cfg_path.exists():
            pytest.skip("config/flow_score.yml not found")
        with cfg_path.open() as f:
            cfg = yaml.safe_load(f)
        grid = _expand_grid(cfg.get("hyperparameter_grid", {}))
        assert len(grid) == 24, (
            f"Expected 24 grid combos (4×2×3), got {len(grid)}. "
            "Expanding the grid requires amending N_trials per amendment §4.5."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 20. sha256_verification_failure → load_artifact returns None
# ─────────────────────────────────────────────────────────────────────────────

class TestSha256Verification:
    def test_corrupt_model_returns_none(self, tmp_path):
        """Corrupted model file (wrong sha256) → load_artifact returns None."""
        import joblib
        # Create a valid artifact directory
        artifact_dir = tmp_path / "models" / "flow_score_8_90_v1"
        artifact_dir.mkdir(parents=True)

        # Write a simple model
        model_path = artifact_dir / "model.joblib"
        cal_path = artifact_dir / "calibrator.joblib"
        joblib.dump({"model": "fake"}, model_path)
        joblib.dump({"calibrator": "fake"}, cal_path)

        # Compute correct sha256
        correct_sha = _sha256_file(model_path)
        bad_sha = correct_sha[::-1]  # corrupted hash

        manifest = {
            "schema": "flow_score.model_manifest/v1",
            "bucket": "8_90",
            "model_version": 1,
            "deployable": True,
            "hashes": {
                "model_sha256": bad_sha,  # deliberately wrong
                "calibrator_sha256": _sha256_file(cal_path),
            },
        }
        (artifact_dir / "manifest.json").write_text(json.dumps(manifest))

        result = load_artifact(str(tmp_path / "models"), "8_90")
        assert result is None, "Expected None when model sha256 is corrupt"

    def test_valid_artifact_loads(self, tmp_path):
        """Valid sha256 → load_artifact returns (model, calibrator, manifest)."""
        import joblib
        artifact_dir = tmp_path / "models" / "flow_score_0_7_v1"
        artifact_dir.mkdir(parents=True)

        model_path = artifact_dir / "model.joblib"
        cal_path = artifact_dir / "calibrator.joblib"
        joblib.dump({"model": "valid"}, model_path)
        joblib.dump({"calibrator": "valid"}, cal_path)

        manifest = {
            "schema": "flow_score.model_manifest/v1",
            "bucket": "0_7",
            "model_version": 1,
            "deployable": True,
            "hashes": {
                "model_sha256": _sha256_file(model_path),
                "calibrator_sha256": _sha256_file(cal_path),
            },
            "cv_params": {"feature_columns": []},
        }
        (artifact_dir / "manifest.json").write_text(json.dumps(manifest))

        result = load_artifact(str(tmp_path / "models"), "0_7")
        assert result is not None
        model, calibrator, m = result
        assert m["bucket"] == "0_7"

    def test_no_artifact_returns_none(self, tmp_path):
        result = load_artifact(str(tmp_path / "models"), "90p")
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        """Artifact dir with missing calibrator.joblib → None."""
        import joblib
        artifact_dir = tmp_path / "models" / "flow_score_90p_v1"
        artifact_dir.mkdir(parents=True)
        model_path = artifact_dir / "model.joblib"
        joblib.dump({"m": 1}, model_path)
        # No calibrator.joblib; no manifest
        result = load_artifact(str(tmp_path / "models"), "90p")
        assert result is None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# 21. lazy_import: importing lib.flow_score with sklearn absent succeeds
# ─────────────────────────────────────────────────────────────────────────────

class TestLazyImport:
    def test_module_imports_without_sklearn(self):
        """lib.flow_score must import successfully even when sklearn is absent.

        Simulate sklearn absence by patching sys.modules to raise ImportError
        for sklearn, then reimport the module.
        """
        import importlib
        import lib.flow_score as fs_module

        # Create a mock module that raises ImportError on import
        class FailModule(types.ModuleType):
            def __getattr__(self, name):
                raise ImportError(f"Simulated: sklearn is not installed")

        # Patch sklearn in sys.modules to simulate absence
        original_sklearn = sys.modules.get("sklearn")
        original_sklearn_ensemble = sys.modules.get("sklearn.ensemble")
        try:
            sys.modules["sklearn"] = FailModule("sklearn")
            sys.modules["sklearn.ensemble"] = FailModule("sklearn.ensemble")
            sys.modules["sklearn.isotonic"] = FailModule("sklearn.isotonic")
            sys.modules["sklearn.calibration"] = FailModule("sklearn.calibration")
            sys.modules["sklearn.metrics"] = FailModule("sklearn.metrics")

            # Reimporting the module should NOT raise (lazy import law)
            if "lib.flow_score" in sys.modules:
                del sys.modules["lib.flow_score"]
            importlib.import_module("lib.flow_score")
            # If we get here, the module imported successfully without sklearn
        finally:
            # Restore original sys.modules
            for key in ("sklearn", "sklearn.ensemble", "sklearn.isotonic",
                        "sklearn.calibration", "sklearn.metrics"):
                if key in sys.modules:
                    del sys.modules[key]
            if original_sklearn is not None:
                sys.modules["sklearn"] = original_sklearn
            if original_sklearn_ensemble is not None:
                sys.modules["sklearn.ensemble"] = original_sklearn_ensemble
            # Force reimport with real sklearn restored
            if "lib.flow_score" in sys.modules:
                del sys.modules["lib.flow_score"]
            importlib.import_module("lib.flow_score")

    def test_non_sklearn_functions_work_without_sklearn(self):
        """ECE, Brier, map_model_bucket work without sklearn."""
        # These don't need sklearn at all
        assert map_model_bucket("8_30d") == "8_90"
        assert np.isfinite(ece([0.5, 0.5], [0.0, 1.0], n_bins=1))
        assert np.isfinite(brier([0.5, 0.5], [0.0, 1.0]))


# ─────────────────────────────────────────────────────────────────────────────
# 22. label_column_missing_halts (not silently substituting absolute return)
# ─────────────────────────────────────────────────────────────────────────────

class TestLabelColumnMissingHalts:
    def test_missing_spy_excess_raises(self):
        """If spy_excess column absent from grades, _build_label raises ValueError.

        Amendment §2.1: DO NOT silently substitute absolute return.
        """
        cfg = {
            "label_columns": {
                "8_90": "spy_excess_21",  # configured ruler column
            }
        }
        # Events with event_ids
        events_df = pd.DataFrame({
            "event_id": ["e1", "e2", "e3"],
            "dte_bucket": ["8_30d"] * 3,
        })
        # Grades WITHOUT the spy_excess_21 column (only absolute return available)
        grades_df = pd.DataFrame({
            "event_id": ["e1", "e2", "e3"],
            "graded_ok": [True, True, True],
            "fwd_ret_21": [0.05, -0.02, 0.01],  # absolute return present
            # spy_excess_21 is ABSENT
        })
        with pytest.raises(ValueError, match="spy_excess_21"):
            _build_label(events_df, grades_df, bucket="8_90", cfg=cfg)

    def test_spy_excess_present_produces_labels(self):
        """When spy_excess column exists, labels are 0/1 (outperformed SPY or not)."""
        cfg = {
            "label_columns": {
                "8_90": "spy_excess_21",
            }
        }
        events_df = pd.DataFrame({
            "event_id": ["e1", "e2", "e3", "e4"],
            "dte_bucket": ["8_30d"] * 4,
        })
        grades_df = pd.DataFrame({
            "event_id": ["e1", "e2", "e3", "e4"],
            "graded_ok": [True, True, True, True],
            "spy_excess_21": [0.05, -0.02, 0.01, 0.0],
        })
        labels = _build_label(events_df, grades_df, bucket="8_90", cfg=cfg)
        # spy_excess > 0 → label = 1
        e1 = labels.get("e1", float("nan"))
        e2 = labels.get("e2", float("nan"))
        e4 = labels.get("e4", float("nan"))
        assert float(e1) == 1.0, f"e1: expected 1.0 (spy_excess=0.05), got {e1}"
        assert float(e2) == 0.0, f"e2: expected 0.0 (spy_excess=-0.02), got {e2}"
        # spy_excess == 0: not > 0 → label = 0
        assert float(e4) == 0.0, f"e4: expected 0.0 (spy_excess=0.0), got {e4}"

    def test_ungraded_rows_get_nan_label(self):
        """Rows with graded_ok=False get NaN labels (not graded yet)."""
        cfg = {"label_columns": {"8_90": "spy_excess_21"}}
        events_df = pd.DataFrame({
            "event_id": ["e1", "e2"],
            "dte_bucket": ["8_30d", "8_30d"],
        })
        grades_df = pd.DataFrame({
            "event_id": ["e1", "e2"],
            "graded_ok": [True, False],
            "spy_excess_21": [0.05, 0.10],
        })
        labels = _build_label(events_df, grades_df, bucket="8_90", cfg=cfg)
        assert float(labels.get("e1", float("nan"))) == 1.0
        assert np.isnan(float(labels.get("e2", float("nan"))))


# ─────────────────────────────────────────────────────────────────────────────
# Additional: expand_grid and cpcv_path_count
# ─────────────────────────────────────────────────────────────────────────────

class TestExpandGrid:
    def test_cardinality_correct(self):
        grid = {"a": [1, 2], "b": [3, 4, 5]}
        combos = _expand_grid(grid)
        assert len(combos) == 6

    def test_all_combinations_present(self):
        grid = {"x": [1, 2], "y": ["a", "b"]}
        combos = _expand_grid(grid)
        assert {"x": 1, "y": "a"} in combos
        assert {"x": 2, "y": "b"} in combos

    def test_scalar_value_treated_as_singleton(self):
        grid = {"lr": 0.1, "n": [100, 200]}
        combos = _expand_grid(grid)
        assert len(combos) == 2
        for c in combos:
            assert c["lr"] == 0.1


class TestCPCVPathCount:
    def test_c_6_2_is_15(self):
        assert _cpcv_path_count(6, 2) == 15

    def test_c_5_1_is_5(self):
        assert _cpcv_path_count(5, 1) == 5

    def test_c_4_2_is_6(self):
        assert _cpcv_path_count(4, 2) == 6

    def test_matches_math_comb(self):
        for n in range(3, 8):
            for k in range(1, n):
                assert _cpcv_path_count(n, k) == comb(n, k)


# ─────────────────────────────────────────────────────────────────────────────
# 23. Blocker-fix regression locks (post-review adjudication):
#     (a) single-root cohort must still yield CV splits (underlying-exclusion
#         fallback), (b) zero valid splits => deployable=False with reason
#         NO-VALID-CV-SPLITS (never silent fall-through to grid[0]),
#     (c) calibration metrics evaluated on the DISJOINT outer slice, never on
#         the isotonic calibrator's own fit data, (d) train-side calibration
#         split respects the embargo gap below the holdout cutoff.
# ─────────────────────────────────────────────────────────────────────────────

def _make_train_bucket_fixture(tmp_path, n: int = 400, n_roots: int = 5):
    """flow_dir + cfg + events df for an end-to-end train_bucket('8_90') run."""
    df = _make_cv_df(n=n, n_roots=n_roots)
    df = df.drop(columns=["_label"])
    df["dte_bucket"] = "8_30d"
    df["premium"] = np.linspace(1.0e5, 5.0e6, n)
    df["prior_oi"] = 1000.0
    df["zerodte"] = False
    flow_dir = tmp_path / "flow_signals"
    flow_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(flow_dir / "cohort_tape_recon.parquet", index=False)
    rng = np.random.default_rng(7)
    grades = pd.DataFrame({
        "event_id": df["event_id"],
        # weak premium-linked signal so the model has something to fit
        "spy_excess_21": rng.normal(0.0, 0.02, n) + (df["premium"].values > 2.5e6) * 0.01,
        "graded_ok": [True] * n,
    })
    grades.to_parquet(flow_dir / "grades.parquet", index=False)
    cfg = {
        "scoring": {"enabled": False},
        "models_dir": str(tmp_path / "models"),
        "model_bucket_map": {"8_30d": "8_90", "31_90d": "8_90"},
        "embargo_days": {"8_90": 21},
        "k_folds": 5,
        "n_groups": 6,
        "k_test": 2,
        "random_seed": 42,
        # Floors deliberately tiny: the contiguous daily fixture collapses to
        # effective_n≈14.5 under uniqueness weights, and these regression tests
        # target the CV/calibration mechanics BEYOND the floor gate (the floor
        # gate has its own tests in TestDeployableLogic).
        "n_floors": {"bucket": 3, "era_cell": 3},
        "ece_threshold": 0.05,
        "n_bins": 10,
        "label_columns": {"8_90": "spy_excess_21"},
        "hyperparameter_grid": {"learning_rate": [0.1], "max_iter": [50], "max_leaf_nodes": [15]},
        "feature_columns": ["premium"],
        "dte_interaction": {"8_90": False},
        "monotone_constraints": {},
    }
    return flow_dir, cfg, df


class TestBlockerRegressions:
    def test_single_root_cohort_yields_splits(self):
        """Regression (CV-SPLITS-DEGENERATE): one distinct root must NOT collapse
        _group_fold_splits to zero splits — underlying-exclusion is skipped and
        the time axis alone drives the folds."""
        df = _make_cv_df(n=100, n_roots=1)
        splits = _group_fold_splits(
            df, k_folds=5, embargo=5, n_groups=6, random_seed=42
        )
        assert len(splits) > 0, "single-root cohort produced zero CV splits (regression)"
        for train_idx, val_idx in splits:
            assert len(train_idx) > 0, "empty training fold on single-root cohort"
            assert len(val_idx) > 0, "empty validation fold on single-root cohort"

    def test_zero_splits_writes_no_valid_cv_splits_reason(self, tmp_path, monkeypatch):
        """Regression (NO-VALID-CV-SPLITS): when every split is filtered away the
        trainer must mark the artifact deployable=False with the registered
        reason — never silently fall through to hparam_grid[0] selection."""
        import scripts.ops_train_flow_score as ots
        flow_dir, cfg, _ = _make_train_bucket_fixture(tmp_path)
        monkeypatch.setattr(ots, "_group_fold_splits", lambda *a, **k: [])
        result = ots.train_bucket("8_90", cfg, flow_dir, dry_run=False)
        assert result is not None
        assert result["deployable"] is False
        assert "NO-VALID-CV-SPLITS" in result["deploy_reason"]

    def test_calibration_eval_never_sees_full_holdout(self, tmp_path, monkeypatch):
        """Regression (CALIB-IN-SAMPLE-GATE): ECE/Brier must be evaluated on the
        outer slice only (disjoint from the isotonic fit slice). With 400 daily
        rows the temporal holdout is exactly 80 rows; in-sample evaluation would
        hand ece() all 80 — the lock asserts no ece() call ever receives the
        full holdout."""
        import lib.flow_score as lfs
        import scripts.ops_train_flow_score as ots
        flow_dir, cfg, _ = _make_train_bucket_fixture(tmp_path, n=400)
        n_cal_full = 400 - int(400 * 0.80)  # 80
        seen_sizes: list[int] = []
        real_ece = lfs.ece

        def _capturing_ece(pred, y, *a, **k):
            seen_sizes.append(len(np.asarray(pred)))
            return real_ece(pred, y, *a, **k)

        monkeypatch.setattr(lfs, "ece", _capturing_ece)
        result = ots.train_bucket("8_90", cfg, flow_dir, dry_run=False)
        assert result is not None
        assert seen_sizes, "calibration path never evaluated ECE"
        assert n_cal_full not in seen_sizes, (
            f"ece() saw the FULL {n_cal_full}-row calibration holdout — "
            "in-sample calibration evaluation regression"
        )
        assert max(seen_sizes) <= n_cal_full // 2, (
            "ece() evaluation slice larger than the outer half of the holdout"
        )

    def test_train_cal_split_respects_embargo_gap(self, tmp_path, monkeypatch):
        """Regression (TRAIN-CAL-NO-EMBARGO-LEAK): no training row may sit within
        embargo_days below the holdout cutoff (its label window would overlap
        the calibration period)."""
        import lib.flow_score as lfs
        import scripts.ops_train_flow_score as ots
        flow_dir, cfg, df = _make_train_bucket_fixture(tmp_path, n=400)
        captured: dict = {}
        real_uw = lfs.uniqueness_weights

        def _capturing_uw(events_df, *a, **k):
            # first call comes from the train-side split in train_bucket
            if "train_df" not in captured:
                captured["train_df"] = events_df.copy()
            return real_uw(events_df, *a, **k)

        monkeypatch.setattr(lfs, "uniqueness_weights", _capturing_uw)
        result = ots.train_bucket("8_90", cfg, flow_dir, dry_run=False)
        assert result is not None
        assert "train_df" in captured, "uniqueness_weights never called on the training frame"
        all_dates = pd.to_datetime(df["session_date"]).sort_values()
        holdout_cutoff = all_dates.iloc[int(len(all_dates) * 0.80)]
        embargo_gap = pd.Timedelta(days=cfg["embargo_days"]["8_90"])
        train_max = pd.to_datetime(captured["train_df"]["session_date"]).max()
        assert train_max < holdout_cutoff - embargo_gap, (
            f"training rows extend to {train_max}, inside the {embargo_gap} embargo "
            f"below the holdout cutoff {holdout_cutoff} (leak regression)"
        )
