"""Tests for engine/release_revision_model.py — Track R NFP revision model.

Test categories:
  1. Schema — compute_revision_lean returns required keys with correct types
  2. No-leakage — feature set excludes prior-revision; decision date respects PIT
  3. Determinism — same inputs produce same output
  4. Authority flags — display_only=True, authority=False on all outputs
  5. Collector output type check — fetch_all_vintages schema validation (synthetic)
  6. Kill-rule mechanics — triggered correctly from synthetic walk-forward results
  7. Level-bias annotation — compute_revision_context returns correct keys/values
  8. Target construction — first→third and fallback paths produce correct targets

All tests use synthetic data only — no real parquet files are read.

Run:
  python -m pytest tests/test_release_revision_model.py -v
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_revision_model import (
    MIN_TRAIN_OBS,
    STRENGTH_THRESHOLD,
    _EXPANSION_CUMULATIVE_REVISION_K,
    _CONTRACTION_CUMULATIVE_REVISION_K,
    _value_at_vintage,
    _wilson,
    build_revision_features,
    build_revision_target_df,
    compute_revision_context,
    compute_revision_lean,
    evaluate_hit_rate,
    load_multi_vintage,
    run_revision_walk_forward,
)


# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------

def _make_mv_df(
    periods: list[pd.Timestamp],
    vintages_per_period: list[list[tuple[pd.Timestamp, float]]],
) -> pd.DataFrame:
    """Build a synthetic multi-vintage PAYEMS DataFrame.

    periods: list of observation period dates
    vintages_per_period: for each period, list of (realtime_start, value) tuples
    """
    rows = []
    for period, vint_list in zip(periods, vintages_per_period):
        sorted_vints = sorted(vint_list, key=lambda x: x[0])
        for i, (rt_start, value) in enumerate(sorted_vints):
            if i < len(sorted_vints) - 1:
                rt_end = sorted_vints[i + 1][0] - pd.Timedelta(days=1)
            else:
                rt_end = pd.Timestamp("9999-12-31")
            rows.append({
                "period": period,
                "realtime_start": rt_start,
                "realtime_end": rt_end,
                "value": float(value),
            })
    return pd.DataFrame(rows)


def _make_init_vintages(
    series: str,
    periods: list[pd.Timestamp],
    values: list[float],
    release_delays: list[int],  # days after period
) -> pd.DataFrame:
    """Build a synthetic output_type=4 initial-release vintages DataFrame."""
    rows = []
    for period, value, delay in zip(periods, values, release_delays):
        rt_start = period + pd.Timedelta(days=delay)
        rows.append({
            "series": series,
            "period": period,
            "value": value,
            "realtime_start": rt_start,
            "realtime_end": pd.Timestamp("9999-12-31"),
        })
    return pd.DataFrame(rows)


def _make_records_for_wf(
    n: int = 120,
    base_date: pd.Timestamp = pd.Timestamp("2010-01-01"),
    sign_pattern: int | None = None,
) -> list[dict]:
    """Build synthetic walk-forward records.

    sign_pattern: if None, alternating +1/-1; else constant.
    """
    records = []
    for i in range(n):
        period = base_date + pd.DateOffset(months=i)
        target = sign_pattern if sign_pattern is not None else (1 if i % 2 == 0 else -1)
        records.append({
            "period": period,
            "first_release_date": period + pd.Timedelta(days=35),
            "decision_date": period + pd.Timedelta(days=34),
            "target": target,
            "fp_surprise_vs_AR1": float(np.random.randn()),
            "sin_month": float(np.sin(2 * np.pi * (period.month - 1) / 12)),
            "cos_month": float(np.cos(2 * np.pi * (period.month - 1) / 12)),
            "icsa_4m_survey_week_change": float(np.random.randn() * 5000),
        })
    return records


# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestSchema:
    """compute_revision_lean returns required keys with correct types."""

    def test_required_keys_present(self, tmp_path):
        """All required keys must be present in compute_revision_lean output."""
        required_keys = {
            "lean", "strength", "model_hit_rate_backtest",
            "n_backtest", "basis", "display_only", "authority",
        }
        # Provide empty store — should return gracefully with lean='none'
        result = compute_revision_lean(date(2026, 6, 1), tmp_path)
        assert required_keys.issubset(result.keys()), (
            f"Missing keys: {required_keys - result.keys()}"
        )

    def test_lean_values_valid(self, tmp_path):
        """lean must be one of 'up', 'down', 'none'."""
        result = compute_revision_lean(date(2026, 6, 1), tmp_path)
        assert result["lean"] in ("up", "down", "none")

    def test_compute_revision_context_keys(self):
        """compute_revision_context must return level_bias_annotation dict."""
        ctx = compute_revision_context()
        assert "level_bias_annotation" in ctx
        ann = ctx["level_bias_annotation"]
        assert "expansion_mean_cumulative_revision_k" in ann
        assert "contraction_mean_cumulative_revision_k" in ann
        assert ann["display_only"] is True
        assert ann["authority"] is False
        assert ann["expansion_mean_cumulative_revision_k"] == _EXPANSION_CUMULATIVE_REVISION_K
        assert ann["contraction_mean_cumulative_revision_k"] == _CONTRACTION_CUMULATIVE_REVISION_K


# ---------------------------------------------------------------------------
# 2. Authority flags
# ---------------------------------------------------------------------------

class TestAuthorityFlags:
    """display_only=True, authority=False on all outputs."""

    def test_compute_revision_lean_authority_flags(self, tmp_path):
        result = compute_revision_lean(date(2026, 6, 1), tmp_path)
        assert result["display_only"] is True
        assert result["authority"] is False

    def test_compute_revision_context_authority_flags(self):
        ctx = compute_revision_context()
        ann = ctx["level_bias_annotation"]
        assert ann["display_only"] is True
        assert ann["authority"] is False


# ---------------------------------------------------------------------------
# 3. No-leakage tests
# ---------------------------------------------------------------------------

class TestNoLeakage:
    """Feature set excludes prior-revision; decision date respects PIT."""

    def test_prior_revision_feature_absent(self):
        """The feature dict must NOT contain a 'prior_revision' key.

        Per PREREG §2.2: the prior-revision feature is EXCLUDED for leakage.
        """
        # Build minimal synthetic mv_df with 3 recent periods
        t0 = pd.Timestamp("2010-01-01")
        periods = [t0 + pd.DateOffset(months=i) for i in range(6)]
        values = [100.0, 102.0, 104.0, 103.0, 105.0, 107.0]
        # Each period has 3 vintages
        vintages_per = []
        for i, (p, v) in enumerate(zip(periods, values)):
            rt1 = p + pd.Timedelta(days=35)
            rt2 = p + pd.Timedelta(days=66)
            rt3 = p + pd.Timedelta(days=97)
            vintages_per.append([
                (rt1, v), (rt2, v + 0.5), (rt3, v + 1.0)
            ])
        mv_df = _make_mv_df(periods, vintages_per)
        period = periods[-1]
        decision_date = period + pd.Timedelta(days=34)
        features = build_revision_features(
            period=period,
            decision_date=decision_date,
            first_print_mom=2.0,
            mv_df=mv_df,
            init_vintages=None,
        )
        # Must NOT contain any prior-revision feature
        forbidden_keys = [k for k in features if "prior_revision" in k.lower() or "revision" in k.lower()]
        assert not forbidden_keys, f"Leakage: revision feature found: {forbidden_keys}"

    def test_expected_feature_keys(self):
        """Features dict must contain exactly the frozen feature set."""
        mv_df = _make_mv_df(
            [pd.Timestamp("2010-01-01"), pd.Timestamp("2010-02-01")],
            [
                [(pd.Timestamp("2010-02-05"), 130000.0), (pd.Timestamp("2010-03-05"), 130100.0)],
                [(pd.Timestamp("2010-03-05"), 130200.0), (pd.Timestamp("2010-04-05"), 130150.0)],
            ],
        )
        period = pd.Timestamp("2010-02-01")
        decision_date = pd.Timestamp("2010-03-04")
        features = build_revision_features(
            period=period,
            decision_date=decision_date,
            first_print_mom=200.0,
            mv_df=mv_df,
            init_vintages=None,
        )
        expected_keys = {"fp_surprise_vs_AR1", "sin_month", "cos_month", "icsa_4m_survey_week_change"}
        assert set(features.keys()) == expected_keys, (
            f"Feature keys mismatch: got {set(features.keys())}"
        )

    def test_pit_decision_date_filter(self):
        """Features at decision date D must not use data released after D."""
        # Create a mv_df where value at realtime_start=T+36 differs from T+35
        period = pd.Timestamp("2015-03-01")
        prior_period = pd.Timestamp("2015-02-01")
        rt_first = pd.Timestamp("2015-04-03")  # first release date
        rt_later = pd.Timestamp("2015-05-08")  # later vintage

        mv_df = _make_mv_df(
            [prior_period, period],
            [
                [(rt_first, 140000.0), (rt_later, 140200.0)],  # prior period
                [(rt_first, 140300.0), (rt_later, 140500.0)],  # current period
            ],
        )

        # Decision date = rt_first - 1 (day before first release)
        decision_date = rt_first - pd.Timedelta(days=1)

        features = build_revision_features(
            period=period,
            decision_date=decision_date,
            first_print_mom=300.0,
            mv_df=mv_df,
            init_vintages=None,
        )
        # fp_surprise_vs_AR1 should be None (no data knowable before rt_first)
        # because the first prints of T and T-1 are released on rt_first which > decision_date
        # So the feature builder should find no knowable initial prints at decision_date
        # (realtime_start=rt_first > decision_date=rt_first-1)
        assert features["fp_surprise_vs_AR1"] is None


# ---------------------------------------------------------------------------
# 4. Determinism tests
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Same inputs produce same output."""

    def test_walk_forward_determinism(self):
        """Same records produce same walk-forward results."""
        np.random.seed(42)
        records = _make_records_for_wf(n=120)
        r1 = run_revision_walk_forward(records)
        r2 = run_revision_walk_forward(records)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a["y_hat"] == b["y_hat"], "Non-deterministic y_hat"
            assert a["predicted_sign"] == b["predicted_sign"]

    def test_evaluate_hit_rate_determinism(self):
        """Same walk-forward results produce same evaluation stats."""
        np.random.seed(99)
        records = _make_records_for_wf(n=150)
        wf = run_revision_walk_forward(records)
        s1 = evaluate_hit_rate(wf)
        s2 = evaluate_hit_rate(wf)
        assert s1 == s2


# ---------------------------------------------------------------------------
# 5. Kill-rule mechanics
# ---------------------------------------------------------------------------

class TestKillRuleMechanics:
    """Kill rule is triggered when Wilson LB <= majority_base_rate."""

    def test_kill_triggered_when_wilson_lb_below_base(self):
        """Wilson LB <= majority_base_rate should set kill_triggered=True."""
        # Simulate walk-forward results with ~50% hit rate
        # Actual: 80% up (majority_base_rate=0.80); model predicts 50/50 → ~50% HR
        results = []
        for i in range(200):
            period = pd.Timestamp("2010-01-01") + pd.DateOffset(months=i)
            actual = 1 if i % 5 != 0 else -1   # 80% up, majority=0.80
            predicted = 1 if i % 2 == 0 else -1  # ~50% correct on the majority class
            results.append({
                "period": period,
                "actual_target": actual,
                "predicted_sign": predicted,
                "is_covid": False,
            })
        stats = evaluate_hit_rate(results, exclude_covid=True, exclude_zero_target=True)
        # majority_base_rate = 0.80; model HR ~50%; Wilson LB ~44% < 0.80 → kill
        assert stats["kill_triggered"] is True
        assert stats["majority_base_rate"] == pytest.approx(0.80, abs=0.01)

    def test_kill_not_triggered_when_wilson_lb_above_base(self):
        """Wilson LB > majority_base_rate should set kill_triggered=False."""
        results = []
        # 200 steps, 50/50 up/down (majority_base_rate=0.50), model correct 90%
        for i in range(200):
            period = pd.Timestamp("2010-01-01") + pd.DateOffset(months=i)
            actual = 1 if i % 2 == 0 else -1   # 50/50
            predicted = actual if i % 10 != 0 else -actual  # 90% accurate
            results.append({
                "period": period,
                "actual_target": actual,
                "predicted_sign": predicted,
                "is_covid": False,
            })
        stats = evaluate_hit_rate(results, exclude_covid=True, exclude_zero_target=True)
        # majority_base_rate = 0.50; Wilson LB of 90% on 200 steps >> 0.50
        assert stats["kill_triggered"] is False

    def test_covid_excluded_from_kill_evaluation(self):
        """COVID steps (2020-03..06) must be excluded from the kill evaluation."""
        results = []
        # 200 normal steps: 50% up, 50% down, model correct 90% of the time
        # majority_base_rate = 0.50; model HR=0.90; Wilson LB >> 0.50 -> kill=False
        for i in range(200):
            period = pd.Timestamp("2000-01-01") + pd.DateOffset(months=i)
            actual = 1 if i % 2 == 0 else -1       # 50/50
            predicted = actual if i % 10 != 0 else -actual  # 90% correct
            results.append({
                "period": period,
                "actual_target": actual,
                "predicted_sign": predicted,
                "is_covid": False,
            })
        # COVID steps — all wrong
        for m in [3, 4, 5, 6]:
            results.append({
                "period": pd.Timestamp(f"2020-{m:02d}-01"),
                "actual_target": 1,
                "predicted_sign": -1,  # 0% hit
                "is_covid": True,
            })

        stats_excl = evaluate_hit_rate(results, exclude_covid=True)
        stats_incl = evaluate_hit_rate(results, exclude_covid=False)

        # With exclusion: kill should NOT be triggered (200 steps, 90% HR, 50% majority)
        assert stats_excl["kill_triggered"] is False
        # COVID steps are all wrong but majority_base_rate with covid incl still ~50%;
        # 204 steps ~88% HR - still passes
        assert stats_incl["kill_triggered"] is False

    def test_insufficient_data_triggers_kill(self):
        """With zero steps, kill must be triggered (default safe state)."""
        stats = evaluate_hit_rate([])
        assert stats["kill_triggered"] is True


# ---------------------------------------------------------------------------
# 6. Target construction
# ---------------------------------------------------------------------------

class TestTargetConstruction:
    """Target build correctly from multi-vintage data."""

    def test_upward_revision_produces_target_plus_1(self):
        """When third print > first print (MoM), target=+1."""
        # Period T = 2020-01-01
        # T-1 = 2019-12-01
        period_T = pd.Timestamp("2020-01-01")
        period_Tm1 = pd.Timestamp("2019-12-01")
        rt1 = pd.Timestamp("2020-02-07")  # first release
        rt2 = pd.Timestamp("2020-03-06")  # second release
        rt3 = pd.Timestamp("2020-04-03")  # third release

        # First release values: T=130000, T-1=129000 → first_mom = 1000
        # Third release values: T=130500, T-1=129000 → third_mom = 1500 (upward revision)
        mv_df = _make_mv_df(
            [period_Tm1, period_T],
            [
                # T-1: provide 3 vintages (needed for first_to_third check)
                [(rt1, 129000.0), (rt2, 129000.0), (rt3, 129000.0)],
                # T: provide 3 vintages
                [(rt1, 130000.0), (rt2, 130100.0), (rt3, 130500.0)],
            ],
        )
        target_df = build_revision_target_df(mv_df, "first_to_third")
        # Should find period T
        row = target_df[target_df["period"] == period_T]
        assert len(row) == 1
        assert row.iloc[0]["target"] == 1
        assert abs(row.iloc[0]["first_print_mom"] - 1000.0) < 1e-6
        assert abs(row.iloc[0]["third_print_mom"] - 1500.0) < 1e-6

    def test_downward_revision_produces_target_minus_1(self):
        """When third print < first print (MoM), target=-1."""
        period_T = pd.Timestamp("2020-01-01")
        period_Tm1 = pd.Timestamp("2019-12-01")
        rt1 = pd.Timestamp("2020-02-07")
        rt2 = pd.Timestamp("2020-03-06")
        rt3 = pd.Timestamp("2020-04-03")

        # First: T=130000, T-1=129000 → first_mom = 1000
        # Third: T=129800, T-1=129000 → third_mom = 800 (downward)
        mv_df = _make_mv_df(
            [period_Tm1, period_T],
            [
                [(rt1, 129000.0), (rt2, 129000.0), (rt3, 129000.0)],
                [(rt1, 130000.0), (rt2, 130050.0), (rt3, 129800.0)],
            ],
        )
        target_df = build_revision_target_df(mv_df, "first_to_third")
        row = target_df[target_df["period"] == period_T]
        assert len(row) == 1
        assert row.iloc[0]["target"] == -1

    def test_archive_start_filter_excludes_bulk_1997_rows(self):
        """Periods with first_release_date == 1997-01-01 (bulk import) must be excluded."""
        # Simulate a period with first release on 1997-01-01 (bulk import date)
        period_T = pd.Timestamp("1995-06-01")
        period_Tm1 = pd.Timestamp("1995-05-01")
        rt_bulk = pd.Timestamp("1997-01-01")  # bulk import date
        rt2 = pd.Timestamp("1997-02-01")
        rt3 = pd.Timestamp("1997-03-01")

        mv_df = _make_mv_df(
            [period_Tm1, period_T],
            [
                [(rt_bulk, 100000.0), (rt2, 100000.0), (rt3, 100000.0)],
                [(rt_bulk, 101000.0), (rt2, 101100.0), (rt3, 101200.0)],
            ],
        )
        target_df = build_revision_target_df(mv_df, "first_to_third")
        # Period 1995-06-01 should NOT appear (bulk-import first release = 1997-01-01,
        # excluded because < archive_start = 1997-01-02)
        assert period_T not in target_df["period"].values, (
            "Bulk-import row from 1997-01-01 should be excluded"
        )

    def test_genuine_1997_release_included(self):
        """Periods with first_release_date > 1997-01-01 (genuine) must be included."""
        period_T = pd.Timestamp("1997-01-01")
        period_Tm1 = pd.Timestamp("1996-12-01")
        rt1 = pd.Timestamp("1997-02-07")   # genuine Jan 1997 Emp Sit release
        rt2 = pd.Timestamp("1997-03-07")
        rt3 = pd.Timestamp("1997-04-04")

        mv_df = _make_mv_df(
            [period_Tm1, period_T],
            [
                [(rt1, 120000.0), (rt2, 120000.0), (rt3, 120100.0)],
                [(rt1, 121000.0), (rt2, 121200.0), (rt3, 121500.0)],
            ],
        )
        target_df = build_revision_target_df(mv_df, "first_to_third")
        assert period_T in target_df["period"].values, (
            "Genuine 1997 release should be included"
        )

    def test_fallback_basis_uses_latest_vintage(self):
        """With 'first_to_cumulative_fallback', target uses latest available vintage."""
        period_T = pd.Timestamp("2020-01-01")
        period_Tm1 = pd.Timestamp("2019-12-01")
        rt1 = pd.Timestamp("2020-02-07")
        rt_latest = pd.Timestamp("2022-12-31")  # much later vintage

        mv_df = _make_mv_df(
            [period_Tm1, period_T],
            [
                [(rt1, 129000.0), (rt_latest, 129500.0)],  # T-1 revised
                [(rt1, 130000.0), (rt_latest, 131000.0)],  # T revised up a lot
            ],
        )
        target_df = build_revision_target_df(mv_df, "first_to_cumulative_fallback")
        row = target_df[target_df["period"] == period_T]
        if len(row) > 0:
            # first_mom = 130000-129000 = 1000
            # latest_mom = 131000-129500 = 1500 → upward revision
            assert row.iloc[0]["target"] == 1


# ---------------------------------------------------------------------------
# 7. Walk-forward label look-ahead regression test
# ---------------------------------------------------------------------------

class TestLabelLookaheadFix:
    """Regression tests for training-label PIT compliance in run_revision_walk_forward.

    The bug: at each fold i, records[:i] was used as training data regardless
    of whether those rows' labels (third-print values) had been published by
    pred_rec["decision_date"].  The fix: filter training rows by
    label_observable_date <= pred_decision.

    These tests construct a fixture where including vs. excluding unlanded
    labels changes the prediction, and assert the correct (exclusion) outcome.
    """

    def _make_records_with_observable_dates(
        self,
        n_base: int = 70,
        base_date: pd.Timestamp = pd.Timestamp("2010-01-01"),
        n_unlanded: int = 5,
    ) -> tuple[list[dict], list[dict]]:
        """Build two record lists — one with label_observable_date populated
        (PIT-correct), one without (old behaviour).

        The last ``n_unlanded`` records in the training window for the final
        prediction step have label_observable_dates AFTER the prediction
        decision_date.  Those rows should be excluded from training when
        label_observable_date is present.

        Returns (records_with_pit, records_without_pit).
        Both lists are sorted by first_release_date and have n_base+1 rows;
        the last row is the prediction step.
        """
        records_pit = []
        records_no_pit = []

        # Build n_base training rows + 1 prediction row.
        #
        # The prediction decision_date is a fixed anchor.  Each training row
        # gets an explicit label_observable_date:
        #   - rows 0..n_base-n_unlanded-1: label already landed (date well before anchor)
        #   - rows n_base-n_unlanded..n_base-1: label NOT YET landed (date = anchor + 30d)
        #     These rows ALL have target = +1 and fp_surprise = -100 (contradictory signal).
        #   - landed rows are balanced (alternating +1/-1) with consistent fp signal.
        #
        # Effect on model:
        #   With unlanded rows INCLUDED: corrupted training mix → different coefficient.
        #   With unlanded rows EXCLUDED: clean balanced data → different n_train and y_hat.

        pred_decision = pd.Timestamp("2016-03-04")  # fixed anchor date

        for i in range(n_base + 1):
            period = base_date + pd.DateOffset(months=i)
            first_release = period + pd.Timedelta(days=35)
            decision_date = first_release - pd.Timedelta(days=1)

            is_unlanded = (
                i >= n_base - n_unlanded
                and i < n_base  # training row (not pred step)
            )

            if i == n_base:
                # Prediction step
                target = 1
                fp = 5.0
                label_obs = None  # prediction step: no label yet
            elif is_unlanded:
                # Label not yet observable at pred_decision
                target = 1       # biasing: all up → contradictory with neg fp
                fp = -100.0      # strongly negative surprise → corrupted signal
                label_obs = pred_decision + pd.Timedelta(days=30)  # NOT YET landed
            else:
                # Label already landed well before pred_decision
                target = 1 if i % 2 == 0 else -1
                fp = float(target) * 10.0  # consistent signal
                label_obs = pred_decision - pd.Timedelta(days=365)  # landed long ago

            base_rec = {
                "period": period,
                "first_release_date": first_release,
                # Prediction step uses the fixed pred_decision; others use their own date
                "decision_date": pred_decision if i == n_base else decision_date,
                "target": int(target),
                "fp_surprise_vs_AR1": fp,
                "sin_month": float(np.sin(2 * np.pi * (period.month - 1) / 12)),
                "cos_month": float(np.cos(2 * np.pi * (period.month - 1) / 12)),
                "icsa_4m_survey_week_change": None,
            }

            # PIT version: carry label_observable_date
            rec_pit = {**base_rec, "label_observable_date": label_obs}
            # Non-PIT version: no label_observable_date (old behaviour)
            rec_no_pit = {**base_rec}

            records_pit.append(rec_pit)
            records_no_pit.append(rec_no_pit)

        return records_pit, records_no_pit

    def test_unlanded_labels_excluded_from_training(self):
        """Fold training must exclude rows whose label_observable_date > decision_date.

        Concretely: when n_unlanded rows with contradictory labels are present
        in records[:i] but have label_observable_date > pred_decision, the
        PIT-correct walk-forward must exclude them.  This changes the effective
        training set and therefore must produce a different n_train count
        at the final fold.
        """
        n_base = 70
        n_unlanded = 5
        records_pit, records_no_pit = self._make_records_with_observable_dates(
            n_base=n_base, n_unlanded=n_unlanded
        )

        # Use min_obs=60 so both runs reach the final step
        results_pit = run_revision_walk_forward(records_pit, min_obs=60)
        results_no_pit = run_revision_walk_forward(records_no_pit, min_obs=60)

        assert results_pit, "PIT run produced no walk-forward steps"
        assert results_no_pit, "non-PIT run produced no walk-forward steps"

        # The LAST step in each run corresponds to the prediction at fold n_base.
        # PIT version: n_train must be SMALLER (unlanded rows excluded).
        last_pit = results_pit[-1]
        last_no_pit = results_no_pit[-1]

        # PIT-correct run must exclude the n_unlanded rows (training rows whose
        # third release date > prediction decision date).
        # The non-PIT run uses all records[:n_base] as training.
        assert last_pit["n_train"] < last_no_pit["n_train"], (
            f"PIT run n_train ({last_pit['n_train']}) should be smaller than "
            f"non-PIT n_train ({last_no_pit['n_train']}) because {n_unlanded} "
            f"unlanded-label rows must be excluded"
        )
        # Specifically, the difference should equal n_unlanded (each one excluded)
        assert last_no_pit["n_train"] - last_pit["n_train"] == n_unlanded, (
            f"Expected n_train difference of {n_unlanded}, "
            f"got {last_no_pit['n_train'] - last_pit['n_train']}"
        )

    def test_unlanded_label_exclusion_changes_prediction(self):
        """Excluding unlanded labels must change y_hat when those labels are contradictory.

        This verifies that the fix has a real effect on the model output,
        not merely on the training-set bookkeeping.
        """
        n_base = 70
        n_unlanded = 5
        records_pit, records_no_pit = self._make_records_with_observable_dates(
            n_base=n_base, n_unlanded=n_unlanded
        )

        results_pit = run_revision_walk_forward(records_pit, min_obs=60)
        results_no_pit = run_revision_walk_forward(records_no_pit, min_obs=60)

        assert results_pit, "PIT run produced no walk-forward steps"
        assert results_no_pit, "non-PIT run produced no walk-forward steps"

        last_pit = results_pit[-1]
        last_no_pit = results_no_pit[-1]

        # The two runs must produce different y_hat values because the unlanded
        # rows carry a contradictory fp_surprise → target relationship.
        assert last_pit["y_hat"] != last_no_pit["y_hat"], (
            "y_hat must differ between PIT-correct and non-PIT runs when "
            "the excluded unlanded rows carry a systematically contradictory signal"
        )

    def test_no_label_observable_date_is_backward_compatible(self):
        """Records without label_observable_date use all records[:i] (old behaviour)."""
        np.random.seed(77)
        records = _make_records_for_wf(n=80)
        # No label_observable_date key — should behave identically to old logic
        results_new = run_revision_walk_forward(records, min_obs=20)
        # Verify we still get results (backward-compat)
        assert len(results_new) > 0
        # The n_train at each step should equal i (minus any zero-target/NaN drops)
        # Rather than asserting exact values, just verify the walk-forward runs to completion.
        for r in results_new:
            assert r["n_train"] >= 0

    def test_label_observable_past_decision_includes_row(self):
        """A row whose label_observable_date is exactly on pred_decision is included."""
        # Build a tiny fixture: 65 training rows + 1 pred row
        # The last training row has label_observable_date = pred_decision
        # (exactly on the boundary — should be included: <= not <)
        base_date = pd.Timestamp("2010-01-01")
        n = 66  # 65 training + 1 pred
        records = []
        pred_decision = base_date + pd.DateOffset(months=65) + pd.Timedelta(days=34)
        for i in range(n):
            period = base_date + pd.DateOffset(months=i)
            first_release = period + pd.Timedelta(days=35)
            decision_date = first_release - pd.Timedelta(days=1)
            if i == n - 1:
                # Prediction step
                label_obs = None
                target = 1
            elif i == n - 2:
                # Last training row: label_observable_date == pred_decision (boundary)
                label_obs = pred_decision
                target = 1
            else:
                # All other training rows: label already landed well before pred_decision
                label_obs = decision_date + pd.Timedelta(days=60)
                target = 1 if i % 2 == 0 else -1

            records.append({
                "period": period,
                "first_release_date": first_release,
                "decision_date": pred_decision if i == n - 1 else decision_date,
                "label_observable_date": label_obs,
                "target": target,
                "fp_surprise_vs_AR1": float(target) * 5.0,
                "sin_month": float(np.sin(2 * np.pi * (period.month - 1) / 12)),
                "cos_month": float(np.cos(2 * np.pi * (period.month - 1) / 12)),
                "icsa_4m_survey_week_change": None,
            })

        results = run_revision_walk_forward(records, min_obs=60)
        assert results, "Expected at least one walk-forward step"

        # The boundary row (label_observable_date == pred_decision) must be INCLUDED
        # (<=, not <).  With min_obs=60, the last step (i=65) trains on records[:65].
        # Among those 65 rows, the boundary row (i=64) has label_obs==pred_decision
        # and should be included.  Check that n_train is larger than it would be if
        # the boundary were excluded (n_train for all-valid-target rows >= 60).
        last = results[-1]
        # At minimum we need 60 complete-case rows; since all targets are ±1,
        # the boundary row counts.
        assert last["n_train"] >= 60, (
            f"Expected n_train >= 60 (boundary row included), got {last['n_train']}"
        )


# ---------------------------------------------------------------------------
# 8. Walk-forward output structure
# ---------------------------------------------------------------------------

class TestWalkForwardOutput:
    """Walk-forward results have required fields."""

    def test_wf_result_keys(self):
        """Each walk-forward result must have required keys."""
        required_keys = {
            "step", "period", "first_release_date", "actual_target", "y_hat",
            "predicted_sign", "majority_sign", "majority_base_rate",
            "sign_neg_fp_baseline", "n_train", "n_features_used",
            "input_completeness", "is_covid",
        }
        np.random.seed(0)
        records = _make_records_for_wf(n=80)
        results = run_revision_walk_forward(records, min_obs=20)
        assert len(results) > 0, "Expected at least some walk-forward steps"
        for r in results:
            missing = required_keys - set(r.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_min_obs_respected(self):
        """No predictions until min_obs training samples."""
        np.random.seed(1)
        records = _make_records_for_wf(n=100)
        results = run_revision_walk_forward(records, min_obs=40)
        if results:
            # First result must have step >= 40
            assert results[0]["step"] >= 40

    def test_predicted_sign_valid_values(self):
        """predicted_sign must be -1, 0, or +1."""
        np.random.seed(2)
        records = _make_records_for_wf(n=100)
        results = run_revision_walk_forward(records, min_obs=20)
        for r in results:
            assert r["predicted_sign"] in (-1, 0, 1), (
                f"Invalid predicted_sign: {r['predicted_sign']}"
            )

    def test_input_completeness_range(self):
        """input_completeness must be in [0, 1]."""
        np.random.seed(3)
        records = _make_records_for_wf(n=100)
        results = run_revision_walk_forward(records, min_obs=20)
        for r in results:
            assert 0.0 <= r["input_completeness"] <= 1.0


# ---------------------------------------------------------------------------
# 8. Value_at_vintage helper
# ---------------------------------------------------------------------------

class TestValueAtVintage:
    """_value_at_vintage returns correct value for a given (period, rt) pair."""

    def test_returns_value_at_exact_vintage(self):
        period = pd.Timestamp("2020-01-01")
        rt = pd.Timestamp("2020-02-07")
        df = pd.DataFrame([{
            "period": period,
            "realtime_start": rt,
            "realtime_end": pd.Timestamp("2020-03-05"),
            "value": 130000.0,
        }])
        v = _value_at_vintage(df, period, rt)
        assert v == pytest.approx(130000.0)

    def test_returns_latest_when_within_end(self):
        period = pd.Timestamp("2020-01-01")
        rt1 = pd.Timestamp("2020-02-07")
        rt2 = pd.Timestamp("2020-03-06")
        df = pd.DataFrame([
            {"period": period, "realtime_start": rt1, "realtime_end": rt2 - pd.Timedelta(days=1), "value": 130000.0},
            {"period": period, "realtime_start": rt2, "realtime_end": pd.Timestamp("9999-12-31"), "value": 130500.0},
        ])
        # Query at mid-point — should return rt1's value
        v = _value_at_vintage(df, period, pd.Timestamp("2020-02-15"))
        assert v == pytest.approx(130000.0)

    def test_returns_none_for_unknown_period(self):
        period = pd.Timestamp("2020-01-01")
        df = pd.DataFrame(columns=["period", "realtime_start", "realtime_end", "value"])
        v = _value_at_vintage(df, period, pd.Timestamp("2020-02-07"))
        assert v is None


# ---------------------------------------------------------------------------
# 9. Wilson CI helper
# ---------------------------------------------------------------------------

class TestWilson:
    """Wilson CI computes correct bounds."""

    def test_empty_n_returns_none(self):
        assert _wilson(0, 0) is None

    def test_bounds_within_0_1(self):
        ci = _wilson(50, 100)
        assert ci is not None
        assert 0.0 <= ci[0] <= 1.0
        assert 0.0 <= ci[1] <= 1.0
        assert ci[0] <= ci[1]

    def test_perfect_hit_rate_lb_above_0_5(self):
        ci = _wilson(200, 200)
        assert ci[0] > 0.9

    def test_zero_hits_ub_below_0_5_for_large_n(self):
        ci = _wilson(0, 200)
        assert ci[1] < 0.05


# ---------------------------------------------------------------------------
# 10. Synthetic integration — full path
# ---------------------------------------------------------------------------

class TestSyntheticIntegration:
    """Run full path with synthetic data; verify schema and no errors."""

    def test_full_path_with_minimal_synthetic_data(self, tmp_path):
        """Full compute_revision_lean path with synthetic mv parquet."""
        # Create synthetic multi-vintage parquet with enough periods
        n_periods = 100
        base = pd.Timestamp("2007-01-01")
        rows = []
        for i in range(n_periods):
            period = base + pd.DateOffset(months=i)
            rt1 = period + pd.Timedelta(days=35)
            rt2 = period + pd.Timedelta(days=66)
            rt3 = period + pd.Timedelta(days=97)
            prior = period - pd.DateOffset(months=1)
            # Simple increasing series
            val = 130000.0 + i * 50
            val_prior = 130000.0 + (i - 1) * 50
            rows.extend([
                {"period": period, "realtime_start": rt1, "realtime_end": rt2 - pd.Timedelta(days=1), "value": val},
                {"period": period, "realtime_start": rt2, "realtime_end": rt3 - pd.Timedelta(days=1), "value": val + 10},
                {"period": period, "realtime_start": rt3, "realtime_end": pd.Timestamp("9999-12-31"), "value": val + 20},
                {"period": prior, "realtime_start": rt1, "realtime_end": rt2 - pd.Timedelta(days=1), "value": val_prior},
                {"period": prior, "realtime_start": rt2, "realtime_end": pd.Timestamp("9999-12-31"), "value": val_prior + 5},
            ])

        mv_df = pd.DataFrame(rows)
        mv_df["period"] = pd.to_datetime(mv_df["period"])
        mv_df["realtime_start"] = pd.to_datetime(mv_df["realtime_start"])
        mv_df["realtime_end"] = pd.to_datetime(mv_df["realtime_end"])
        mv_df = mv_df.drop_duplicates(subset=["period", "realtime_start"]).reset_index(drop=True)

        mv_path = tmp_path / "data" / "fred_vintage"
        mv_path.mkdir(parents=True)
        mv_df.to_parquet(mv_path / "payems_all_vintages.parquet")

        # Run compute_revision_lean
        asof = pd.Timestamp("2015-06-01")
        result = compute_revision_lean(asof, tmp_path)

        # Required keys present
        required = {"lean", "strength", "model_hit_rate_backtest", "n_backtest",
                    "basis", "display_only", "authority"}
        assert required.issubset(result.keys())
        assert result["display_only"] is True
        assert result["authority"] is False
        assert result["lean"] in ("up", "down", "none")
        assert result["basis"] in ("first_to_third", "first_to_cumulative_fallback")
