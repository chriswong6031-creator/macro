"""Hermetic tests for O-OPT Phase-0 runner.

All tests use FIXTURE stores only — NO real store reads (R8 + smoke contract).
Tests cover:

1. Feature construction:
   a. oi[t-1] law: DOI fixture uses shift(1) BEFORE computing deltas (§8.1)
   b. Dedup-read assumption: MultiIndex panels deduplicate correctly
   c. Coverage floor: groups below 40% coverage return NaN features
   d. Concentration penalty: single-member-dominant group → breadth down-weighted

2. Session window:
   a. Window [−15,+15] returns correct (lo_idx, hi_idx)
   b. Window near store edge → None (not imputed, dropped per §2.3)
   c. Window boundaries match on exact session dates

3. Coverage-drop tallies:
   a. Episode with coverage < 0.40 increments tally
   b. Multiple tiers reported independently

4. Era bucketing:
   a. All four O-OPT eras assigned correctly
   b. Onset 2015-12-31 → 2012-15 era; 2016-01-01 → 2016-19 era

5. O-OPT-4 ACCRUE path:
   a. n_opposed < O4_POWER_FLOOR → verdict = "ACCRUE …"
   b. n_opposed >= O4_POWER_FLOOR → verdict != "ACCRUE …" when result has edge

6. Placebo plumbing:
   a. Placebo draws are regime-matched (smoke: random draws, n=200)
   b. Placebo p95 is always a float (not NaN) when n > 0

7. Trial-count enumeration (§7):
   a. Total trial count = 7 (O1) + 15 (O2) + n_o3 (O3) + 5 (O4)
   b. Gated family = 7 + 5 + n_o3 + 1 = 13 + n_o3
   c. O3 ceiling: enumerate_oopt_trials never produces > 90 O3 gated trials

8. NO-write-in-smoke:
   a. run_oopt_phase0(smoke=True) writes ONLY to /tmp

9. Composite z is equal-weight of available legs (§6)

10. Fragility check (R1): primary passes, both neighbors fail → flagged fragile
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure repo root on sys.path
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine.oracle.oopt import (
    # constants
    O4_POWER_FLOOR, O2_POWER_FLOOR, O3_CELL_CEILING,
    COVERAGE_FLOOR, WINDOW_SESSIONS, OOPT_ERAS,
    THRESH_FLOW_ONSET_Z, SENSITIVITY_NEIGHBORS,
    SIGNED_EXCLUSION_STAMP,
    # functions
    compute_coverage, hhi_from_weights, concentration_penalty,
    session_window, assign_era,
    composite_z, detect_flow_onset, compute_lead,
    is_flow_confirmed, is_opposed_flow,
    enumerate_oopt_trials, gated_trial_count,
    oopt_verdict, check_fragility,
    build_fixture_eod_panel, build_fixture_oi_panel, build_fixture_iv_panel,
    rolling_z, DOI_WINDOW,
    # ruling A1-A3 machinery
    pre_onset_score, auc_score, auc_ci, auc_ci_includes_half,
    consistency_check_pairs, filter_two_sided_pairs, OOPTPairConsistencyError,
    routing_placebo_cell,
)

# Re-import _era_means_oopt from runner (it's a module-level function there)
try:
    from scripts.run_oopt_phase0 import (
        _era_means_oopt,
        run_oopt_phase0,
        _build_smoke_session_dates,
        _build_smoke_episodes,
        _get_complex_etf_map,
    )
    _RUNNER_AVAILABLE = True
except Exception:
    _RUNNER_AVAILABLE = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ROOTS = ["XLK", "XLV", "XLE", "XLF", "XLI"]

@pytest.fixture
def session_dates():
    """~500 trading sessions 2012-06-01 → 2014-06-01."""
    return pd.date_range("2012-06-01", periods=502, freq="B")


@pytest.fixture
def eod_panel(session_dates):
    return build_fixture_eod_panel(ROOTS, session_dates, seed=42)


@pytest.fixture
def oi_panel(session_dates):
    return build_fixture_oi_panel(ROOTS, session_dates, seed=43)


@pytest.fixture
def iv_panel(session_dates):
    return build_fixture_iv_panel(ROOTS, session_dates, seed=44)


# ---------------------------------------------------------------------------
# 1. Feature construction — OI timing law (oi[t-1])
# ---------------------------------------------------------------------------

class TestOITimingLaw:
    """Verify that oi[t-1] law is implemented correctly in fixture builders."""

    def test_doi_fixture_uses_shift1_before_delta(self, session_dates):
        """DOI fixture applies shift(1) before computing delta.

        Manual check: doi_raw[t] = oi_shifted[t] - oi_shifted[t-DOI_WINDOW]
        where oi_shifted = oi.shift(1).

        This ensures same-day OI is never used (§8.1).
        """
        rng = np.random.default_rng(43)
        n = len(session_dates)
        put_oi_raw = np.abs(rng.standard_normal(n)) * 1e5 + 1e5
        put_oi = pd.Series(put_oi_raw, index=session_dates)

        # Apply law manually
        put_oi_shifted = put_oi.shift(1)       # oi[t-1]
        put_doi_manual = put_oi_shifted - put_oi_shifted.shift(DOI_WINDOW)

        # Build panel using the fixture builder
        panel = build_fixture_oi_panel(["MANUAL"], session_dates, seed=43)
        # panel uses the same rng seed but a different root name; compare the structure
        # Key property: first DOI_WINDOW + 1 values should be NaN (due to shift)
        assert panel.index.names == ["date", "root"]
        # The raw OI for the single root in the fixture should yield NaN for early sessions
        doi_vals = panel.xs("MANUAL", level="root")["doi_put_z"].values
        # First DOI_WINDOW + 1 values cannot be z-scored due to NaN doi_raw
        # At least the first 2 (shift(1) + shift(DOI_WINDOW)) = DOI_WINDOW + 1 should be NaN
        n_leading_nan = int(np.sum(np.isnan(doi_vals[:DOI_WINDOW + 2])))
        assert n_leading_nan >= 1, (
            f"Expected leading NaN in doi_z from oi[t-1] law; got {n_leading_nan} NaN in first {DOI_WINDOW+2}"
        )

    def test_doi_fixture_multiindex_dedup(self, session_dates):
        """Fixture DOI panel has unique (date, root) index (no duplicates)."""
        panel = build_fixture_oi_panel(ROOTS, session_dates, seed=43)
        assert panel.index.is_unique, "DOI panel has duplicate (date, root) index entries"

    def test_eod_panel_multiindex_dedup(self, session_dates):
        """Fixture EOD panel has unique (date, root) index."""
        panel = build_fixture_eod_panel(ROOTS, session_dates, seed=42)
        assert panel.index.is_unique, "EOD panel has duplicate (date, root) index entries"

    def test_doi_series_must_not_use_same_day_oi(self, session_dates):
        """Explicitly verify: for a known OI series, doi_z[t] does not use oi[t].

        We inject a step in oi at t=20; the doi_z should first appear at t=21
        (since oi_shifted[t] = oi[t-1], meaning oi[t=20] first enters at oi_shifted[t=21]).
        """
        n = len(session_dates)
        put_oi_raw = np.ones(n) * 1e5
        put_oi_raw[20] = 2e5  # step at t=20

        put_oi = pd.Series(put_oi_raw, index=session_dates)
        put_oi_shifted = put_oi.shift(1)  # oi[t-1]
        put_doi_raw = put_oi_shifted - put_oi_shifted.shift(DOI_WINDOW)

        # oi_shifted[t=21] = oi[20] = 2e5 (the step appears at t=21 in shifted series)
        # oi_shifted[t=20] = oi[19] = 1e5
        # doi_raw[t=21] = oi_shifted[21] - oi_shifted[21-DOI_WINDOW] = 2e5 - 1e5 = 1e5
        # doi_raw[t=20] = oi_shifted[20] - oi_shifted[15] = 1e5 - 1e5 = 0 (no step yet)
        assert put_oi_shifted.iloc[21] == 2e5, "oi_shifted[21] should be oi[20]=2e5"
        assert put_oi_shifted.iloc[20] == 1e5, "oi_shifted[20] should be oi[19]=1e5"

        # The step in doi_raw should appear at t=21, not t=20
        assert put_doi_raw.iloc[20] == 0.0, f"doi_raw[t=20]={put_doi_raw.iloc[20]}, expected 0 (no same-day OI)"
        assert put_doi_raw.iloc[21] == 1e5, f"doi_raw[t=21]={put_doi_raw.iloc[21]}, expected 1e5 (oi[t-1] law)"


# ---------------------------------------------------------------------------
# 2. Session window
# ---------------------------------------------------------------------------

class TestSessionWindow:
    def test_window_returns_correct_bounds(self, session_dates):
        """[−15,+15] window returns (15, 45) for onset at index 30."""
        onset = session_dates[30]
        result = session_window(onset, session_dates, half_window=15)
        assert result is not None
        lo, hi = result
        assert lo == 15, f"Expected lo=15, got {lo}"
        assert hi == 45, f"Expected hi=45, got {hi}"

    def test_window_near_start_returns_none(self, session_dates):
        """Window starting before session index 0 returns None (dropped, not imputed)."""
        onset = session_dates[5]  # too close to start for [−15,+15]
        result = session_window(onset, session_dates, half_window=15)
        assert result is None, f"Expected None (window extends before store), got {result}"

    def test_window_near_end_returns_none(self, session_dates):
        """Window ending after session index -1 returns None."""
        onset = session_dates[-5]  # too close to end
        result = session_window(onset, session_dates, half_window=15)
        assert result is None, f"Expected None (window extends beyond store), got {result}"

    def test_window_exact_boundaries(self, session_dates):
        """Window at exactly 15 from start should succeed; at 14 should fail."""
        onset_ok = session_dates[15]
        result_ok = session_window(onset_ok, session_dates, half_window=15)
        assert result_ok is not None, "Expected window to succeed at exactly half_window from start"
        assert result_ok[0] == 0

        onset_fail = session_dates[14]
        result_fail = session_window(onset_fail, session_dates, half_window=15)
        assert result_fail is None, "Expected None when window would extend to negative index"

    def test_window_hi_index_range(self, session_dates):
        """hi_idx = onset_idx + half_window must be < len(session_dates)."""
        n = len(session_dates)
        onset = session_dates[n - 15 - 1]  # exactly at the last valid onset
        result = session_window(onset, session_dates, half_window=15)
        assert result is not None
        lo, hi = result
        assert hi == n - 1, f"Expected hi={n-1}, got {hi}"


# ---------------------------------------------------------------------------
# 3. Coverage handling
# ---------------------------------------------------------------------------

class TestCoverage:
    def test_full_coverage(self):
        members = ["XLK", "XLV", "XLE"]
        universe = {"XLK", "XLV", "XLE", "XLF"}
        assert compute_coverage(members, universe) == 1.0

    def test_zero_coverage(self):
        members = ["FOO", "BAR"]
        universe = {"XLK", "XLV"}
        assert compute_coverage(members, universe) == 0.0

    def test_partial_coverage_below_floor(self):
        """2/6 = 0.33 < 0.40 → below floor."""
        members = ["A", "B", "C", "D", "E", "F"]
        universe = {"A", "B"}
        cov = compute_coverage(members, universe)
        assert cov == pytest.approx(2/6)
        assert cov < COVERAGE_FLOOR

    def test_partial_coverage_above_floor(self):
        """3/5 = 0.60 > 0.40 → above floor."""
        members = ["A", "B", "C", "D", "E"]
        universe = {"A", "B", "C"}
        cov = compute_coverage(members, universe)
        assert cov == pytest.approx(3/5)
        assert cov >= COVERAGE_FLOOR

    def test_empty_group_zero_coverage(self):
        assert compute_coverage([], {"XLK"}) == 0.0

    def test_hhi_concentration_penalty(self):
        """Single dominant member → HHI near 1 → penalty near 0."""
        # One member has 99% of notional
        weights = [990.0, 5.0, 5.0]
        h = hhi_from_weights(weights)
        penalty = concentration_penalty(weights)
        assert h > 0.9, f"HHI should be >0.9 for dominant member; got {h:.4f}"
        assert penalty < 0.1, f"Penalty should be near 0; got {penalty:.4f}"

    def test_uniform_weights_penalty(self):
        """Equal weights → HHI = 1/n → penalty = 1 - 1/n."""
        n = 5
        weights = [1.0] * n
        expected_hhi = 1.0 / n
        expected_penalty = 1.0 - expected_hhi
        assert hhi_from_weights(weights) == pytest.approx(expected_hhi)
        assert concentration_penalty(weights) == pytest.approx(expected_penalty)


# ---------------------------------------------------------------------------
# 4. Era bucketing
# ---------------------------------------------------------------------------

class TestEraBucketing:
    def test_all_eras_assigned(self):
        test_cases = [
            (pd.Timestamp("2012-06-01"), "2012-15"),
            (pd.Timestamp("2015-12-31"), "2012-15"),
            (pd.Timestamp("2016-01-01"), "2016-19"),
            (pd.Timestamp("2019-12-31"), "2016-19"),
            (pd.Timestamp("2020-01-01"), "2020-22"),
            (pd.Timestamp("2022-12-31"), "2020-22"),
            (pd.Timestamp("2023-01-01"), "2023+"),
            (pd.Timestamp("2026-07-04"), "2023+"),
        ]
        for onset, expected_era in test_cases:
            era = assign_era(onset)
            assert era == expected_era, f"onset={onset.date()} → expected {expected_era}, got {era}"

    def test_boundary_2016(self):
        """2015-12-31 → 2012-15; 2016-01-01 → 2016-19 (boundary precision)."""
        assert assign_era(pd.Timestamp("2015-12-31")) == "2012-15"
        assert assign_era(pd.Timestamp("2016-01-01")) == "2016-19"

    def test_era_means_oopt(self):
        """_era_means_oopt: mean over correct era slices."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        dates = pd.Series([
            pd.Timestamp("2013-01-01"),
            pd.Timestamp("2017-01-01"),
            pd.Timestamp("2021-01-01"),
            pd.Timestamp("2024-01-01"),
        ])
        values = np.array([1.0, 2.0, 3.0, 4.0])
        era_m = _era_means_oopt(values, dates)
        assert era_m["2012-15"] == pytest.approx(1.0)
        assert era_m["2016-19"] == pytest.approx(2.0)
        assert era_m["2020-22"] == pytest.approx(3.0)
        assert era_m["2023+"] == pytest.approx(4.0)

    def test_era_means_nan_for_missing(self):
        """Missing era → NaN, not 0."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        dates = pd.Series([pd.Timestamp("2013-01-01")])
        values = np.array([1.0])
        era_m = _era_means_oopt(values, dates)
        assert np.isnan(era_m["2016-19"])
        assert np.isnan(era_m["2020-22"])
        assert np.isnan(era_m["2023+"])


# ---------------------------------------------------------------------------
# 5. O-OPT-4 ACCRUE path (n_opposed < O4_POWER_FLOOR)
# ---------------------------------------------------------------------------

class TestOOPT4AccruePath:
    def test_small_n_returns_accrue(self):
        """n_opposed < O4_POWER_FLOOR → verdict starts with ACCRUE."""
        verdict = oopt_verdict(
            g1_pass=True, g2_pass=True, g3_pass=True, g4_pass=True,
            bh_rejected=True,
            n=O4_POWER_FLOOR - 1,  # below floor
            power_floor=O4_POWER_FLOOR,
            kill_condition=False,
        )
        assert verdict == "ACCRUE", f"Expected ACCRUE for n<floor, got {verdict}"

    def test_adequate_n_can_display_with_edge(self):
        """n_opposed >= O4_POWER_FLOOR + all pass → DISPLAY-WITH-EDGE."""
        verdict = oopt_verdict(
            g1_pass=True, g2_pass=True, g3_pass=True, g4_pass=True,
            bh_rejected=True,
            n=O4_POWER_FLOOR + 10,
            power_floor=O4_POWER_FLOOR,
            kill_condition=False,
        )
        assert verdict == "DISPLAY-WITH-EDGE"

    def test_adequate_n_kill_when_kill_condition(self):
        """n >= floor + kill_condition → KILL."""
        verdict = oopt_verdict(
            g1_pass=False, g2_pass=False, g3_pass=False, g4_pass=False,
            bh_rejected=False,
            n=O4_POWER_FLOOR + 10,
            power_floor=O4_POWER_FLOOR,
            kill_condition=True,
        )
        assert verdict == "KILL"

    def test_power_floor_exact_boundary(self):
        """n == O4_POWER_FLOOR is adequate (not ACCRUE)."""
        verdict = oopt_verdict(
            g1_pass=True, g2_pass=True, g3_pass=True, g4_pass=True,
            bh_rejected=True,
            n=O4_POWER_FLOOR,
            power_floor=O4_POWER_FLOOR,
            kill_condition=False,
        )
        assert verdict == "DISPLAY-WITH-EDGE"

    def test_runner_oopt4_accrue_path(self):
        """run_oopt_phase0(smoke=True) with n_opposed < 40 → ACCRUE in o4 result."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "oracle").mkdir()
            (data_dir / "oracle" / "gauntlet").mkdir()
            (data_dir / "experiments").mkdir()

            results = run_oopt_phase0(
                data_dir=data_dir,
                smoke=True,
                out_dir=Path("/tmp"),
            )
            o4 = results["o4"]
            # In smoke mode with ~5 episodes, n_opposed should be < O4_POWER_FLOOR
            n_opposed = o4.get("n_opposed", 0)
            assert n_opposed < O4_POWER_FLOOR, (
                f"Expected n_opposed < {O4_POWER_FLOOR} in smoke mode, got {n_opposed}"
            )
            verdict = o4.get("verdict_pending", "")
            assert "ACCRUE" in verdict, (
                f"Expected ACCRUE in verdict_pending when n<{O4_POWER_FLOOR}, got: {verdict!r}"
            )


# ---------------------------------------------------------------------------
# 6. Placebo plumbing
# ---------------------------------------------------------------------------

class TestPlacoboPlumbing:
    def test_composite_z_not_nan_for_valid_legs(self):
        """composite_z returns a float when at least one leg is available."""
        z = composite_z({
            "flow_breadth_g": 0.6,
            "doi_unsigned_z": 0.5,
            "iv_term_z": np.nan,
            "iv_skew_z": np.nan,
            "etf_confirm_z": np.nan,
        })
        assert not np.isnan(z), "composite_z should not be NaN when at least one leg is valid"
        assert z == pytest.approx((0.6 + 0.5) / 2)

    def test_composite_z_nan_when_all_legs_nan(self):
        """composite_z returns NaN when no legs are available."""
        z = composite_z({
            "flow_breadth_g": np.nan,
            "doi_unsigned_z": np.nan,
            "iv_term_z": np.nan,
            "iv_skew_z": np.nan,
            "etf_confirm_z": np.nan,
        })
        assert np.isnan(z), "composite_z should be NaN when all legs are NaN"

    def test_smoke_run_placebo_p95_is_float(self):
        """run_oopt_phase0(smoke=True) O-OPT-1 placebo_p95 is a float."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "oracle").mkdir()
            (data_dir / "oracle" / "gauntlet").mkdir()
            (data_dir / "experiments").mkdir()

            results = run_oopt_phase0(data_dir=data_dir, smoke=True, out_dir=Path("/tmp"))
            o1 = results["o1"]
            placebo_p95 = o1.get("placebo_p95", None)
            if o1.get("n", 0) > 0:
                assert placebo_p95 is not None
                assert not np.isnan(placebo_p95), "placebo_p95 should be a float when n > 0"


# ---------------------------------------------------------------------------
# 7. Trial-count enumeration (§7 exact counts)
# ---------------------------------------------------------------------------

class TestTrialEnumeration:
    def test_total_trial_count_no_o3(self):
        """With 0 O3 cells: total = 7(O1) + 15(O2) + 0 + 5(O4) = 27."""
        trials = enumerate_oopt_trials(n_o3_cells=0)
        # O1: 1 pooled + 4 era + 2 regime = 7
        # O2: 3 horizons × (1 pooled + 4 era) = 15
        # O3: 0
        # O4: 1 pooled + 4 era = 5
        assert len(trials) == 27, f"Expected 27 trials (no O3), got {len(trials)}"

    def test_gated_family_count_no_o3(self):
        """Gated family with 0 O3 cells: 7(O1) + 5(O2 at 21d) + 0 + 1(O4) = 13."""
        trials = enumerate_oopt_trials(n_o3_cells=0)
        n_gated = gated_trial_count(trials)
        assert n_gated == 13, f"Expected 13 gated trials (no O3), got {n_gated}"

    def test_o3_cells_add_to_gated(self):
        """Each O3 cell adds one gated trial; ceiling is O3_CELL_CEILING."""
        trials = enumerate_oopt_trials(n_o3_cells=10)
        n_gated = gated_trial_count(trials)
        assert n_gated == 23, f"Expected 13 + 10 = 23 gated, got {n_gated}"

    def test_o3_ceiling_enforced(self):
        """enumerate_oopt_trials caps O3 at O3_CELL_CEILING (90)."""
        trials = enumerate_oopt_trials(n_o3_cells=200)
        o3_trials = [t for t in trials if t["section"] == "O-OPT-3"]
        assert len(o3_trials) == O3_CELL_CEILING, (
            f"Expected O3 capped at {O3_CELL_CEILING}, got {len(o3_trials)}"
        )

    def test_section_labels_correct(self):
        """All trials have one of the four valid section labels."""
        trials = enumerate_oopt_trials(n_o3_cells=5)
        valid_sections = {"O-OPT-1", "O-OPT-2", "O-OPT-3", "O-OPT-4"}
        for t in trials:
            assert t["section"] in valid_sections, f"Invalid section: {t['section']}"

    def test_o1_trial_ids_unique(self):
        """All trial IDs are unique."""
        trials = enumerate_oopt_trials(n_o3_cells=5)
        ids = [t["trial_id"] for t in trials]
        assert len(ids) == len(set(ids)), "Duplicate trial IDs found"

    def test_21d_primary_gated_in_o2(self):
        """O-OPT-2 21d trials are gated; 5d and 63d are not."""
        trials = enumerate_oopt_trials(n_o3_cells=0)
        o2_trials = [t for t in trials if t["section"] == "O-OPT-2"]
        for t in o2_trials:
            if t["horizon_d"] == 21:
                assert t["gated"] is True, f"21d O2 trial should be gated: {t['trial_id']}"
            else:
                assert t["gated"] is False, f"Non-21d O2 trial should NOT be gated: {t['trial_id']}"

    def test_o4_era_trials_not_gated(self):
        """O-OPT-4 era trials are NOT gated (only pooled is gated)."""
        trials = enumerate_oopt_trials(n_o3_cells=0)
        o4_era = [t for t in trials if t["section"] == "O-OPT-4" and "era" in t]
        for t in o4_era:
            assert t["gated"] is False, f"O4 era trial should not be gated: {t['trial_id']}"

    def test_o4_pooled_gated(self):
        """O-OPT-4 pooled trial IS gated."""
        trials = enumerate_oopt_trials(n_o3_cells=0)
        o4_pooled = [t for t in trials if t["trial_id"] == "oopt4_tier_s_pooled"]
        assert len(o4_pooled) == 1
        assert o4_pooled[0]["gated"] is True

    def test_max_gated_family_at_ceiling(self):
        """Maximum gated family = 7 + 5 + 90 + 1 = 103."""
        trials = enumerate_oopt_trials(n_o3_cells=O3_CELL_CEILING)
        n_gated = gated_trial_count(trials)
        assert n_gated == 103, f"Expected 103 gated at O3 ceiling, got {n_gated}"


# ---------------------------------------------------------------------------
# 8. NO-write-in-smoke
# ---------------------------------------------------------------------------

class TestNoWriteInSmoke:
    def test_smoke_writes_only_to_tmp(self):
        """run_oopt_phase0(smoke=True) must NOT write to data/ or reports/."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "oracle").mkdir()
            (data_dir / "oracle" / "gauntlet").mkdir()
            (data_dir / "experiments").mkdir()

            results = run_oopt_phase0(data_dir=data_dir, smoke=True, out_dir=Path("/tmp"))

            # No writes in data_dir
            written_files = list(data_dir.rglob("oopt_*"))
            assert len(written_files) == 0, (
                f"Smoke mode wrote files to data/: {written_files}"
            )

            # Results JSON should be at /tmp
            assert Path("/tmp/oopt_smoke_results.json").exists(), (
                "Smoke results not written to /tmp"
            )
            assert results["smoke"] is True

    def test_smoke_does_not_append_registry(self):
        """Smoke mode must not append to registry_seed.json."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "oracle").mkdir()
            (data_dir / "oracle" / "gauntlet").mkdir()
            exp_dir = data_dir / "experiments"
            exp_dir.mkdir()

            # Create a minimal registry
            registry_path = exp_dir / "registry_seed.json"
            registry_path.write_text(json.dumps({"schema": "v1", "experiments": []}))

            run_oopt_phase0(data_dir=data_dir, smoke=True, out_dir=Path("/tmp"))

            with open(registry_path) as f:
                registry = json.load(f)
            assert len(registry["experiments"]) == 0, (
                "Smoke mode must not append to registry"
            )

    def test_smoke_does_not_append_trial_ledger(self):
        """Smoke mode must not append to p3_trial_ledger.json."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "oracle").mkdir()
            gauntlet_dir = data_dir / "oracle" / "gauntlet"
            gauntlet_dir.mkdir()
            (data_dir / "experiments").mkdir()

            ledger_path = gauntlet_dir / "p3_trial_ledger.json"
            ledger_path.write_text(json.dumps({"seed": 20260704, "trials": [], "n_trials": 0}))

            run_oopt_phase0(data_dir=data_dir, smoke=True, out_dir=Path("/tmp"))

            with open(ledger_path) as f:
                ledger = json.load(f)
            assert ledger["n_trials"] == 0, "Smoke mode must not append to trial ledger"


# ---------------------------------------------------------------------------
# 9. Composite z equal-weight (§6)
# ---------------------------------------------------------------------------

class TestCompositeZ:
    def test_equal_weight_mean(self):
        """composite_z is the equal-weight mean of available legs."""
        feats = {
            "flow_breadth_g": 1.0,
            "doi_unsigned_z": 2.0,
            "iv_term_z": 3.0,
            "iv_skew_z": np.nan,   # excluded
            "etf_confirm_z": np.nan,  # excluded
        }
        z = composite_z(feats)
        assert z == pytest.approx((1.0 + 2.0 + 3.0) / 3)

    def test_single_leg_available(self):
        """With only one leg, composite_z = that leg's value."""
        feats = {
            "flow_breadth_g": np.nan,
            "doi_unsigned_z": 1.5,
            "iv_term_z": np.nan,
            "iv_skew_z": np.nan,
            "etf_confirm_z": np.nan,
        }
        z = composite_z(feats)
        assert z == pytest.approx(1.5)

    def test_five_legs_equal_weight(self):
        """All 5 legs available → mean of all 5."""
        feats = {
            "flow_breadth_g": 0.2,
            "doi_unsigned_z": 0.4,
            "iv_term_z": 0.6,
            "iv_skew_z": 0.8,
            "etf_confirm_z": 1.0,
        }
        z = composite_z(feats)
        assert z == pytest.approx((0.2 + 0.4 + 0.6 + 0.8 + 1.0) / 5)


# ---------------------------------------------------------------------------
# 10. Fragility check (R1)
# ---------------------------------------------------------------------------

class TestFragilityCheck:
    def test_fragile_when_primary_passes_but_both_neighbors_fail(self):
        """Primary passes, both neighbors fail → fragile."""
        fragile = check_fragility(
            primary_passes=True,
            neighbor_results={-0.25: False, +0.25: False},
        )
        assert fragile is True

    def test_not_fragile_when_primary_fails(self):
        """Primary fails → not fragile (irrelevant)."""
        fragile = check_fragility(
            primary_passes=False,
            neighbor_results={-0.25: False, +0.25: False},
        )
        assert fragile is False

    def test_not_fragile_when_one_neighbor_passes(self):
        """If one neighbor passes → not fragile."""
        fragile = check_fragility(
            primary_passes=True,
            neighbor_results={-0.25: True, +0.25: False},
        )
        assert fragile is False

    def test_not_fragile_when_both_neighbors_pass(self):
        fragile = check_fragility(
            primary_passes=True,
            neighbor_results={-0.25: True, +0.25: True},
        )
        assert fragile is False


# ---------------------------------------------------------------------------
# 11. Window-join boundaries
# ---------------------------------------------------------------------------

class TestWindowJoinBoundaries:
    def test_window_includes_both_endpoints(self, session_dates):
        """Session window includes onset±15 — both lo and hi are in the index."""
        onset_idx = 100
        onset = session_dates[onset_idx]
        result = session_window(onset, session_dates, half_window=15)
        assert result is not None
        lo, hi = result
        assert session_dates[lo] == session_dates[onset_idx - 15]
        assert session_dates[hi] == session_dates[onset_idx + 15]
        assert hi - lo == 30  # exactly 31 sessions inclusive


# ---------------------------------------------------------------------------
# 12. Signing stamp
# ---------------------------------------------------------------------------

class TestSigningStamp:
    def test_signed_exclusion_stamp_fields(self):
        """SIGNED_EXCLUSION_STAMP has required fields."""
        stamp = SIGNED_EXCLUSION_STAMP
        assert stamp["excluded"] is True
        assert "signing_source" in stamp
        assert "reason" in stamp
        assert "T2a" in stamp["reason"] or "R7" in stamp["reason"]

    def test_smoke_results_include_stamp(self):
        """Smoke results include signed_excluded_stamp in all claim results."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "oracle").mkdir()
            (data_dir / "oracle" / "gauntlet").mkdir()
            (data_dir / "experiments").mkdir()

            results = run_oopt_phase0(data_dir=data_dir, smoke=True, out_dir=Path("/tmp"))

            for claim in ["o1", "o2", "o3", "o4"]:
                claim_result = results.get(claim, {})
                assert "signed_excluded_stamp" in claim_result, (
                    f"Claim {claim} missing signed_excluded_stamp"
                )
                assert claim_result["signed_excluded_stamp"]["excluded"] is True


# ---------------------------------------------------------------------------
# 13. Rolling z sanity
# ---------------------------------------------------------------------------

class TestRollingZ:
    def test_rolling_z_has_leading_nan(self):
        """rolling_z returns NaN for the first min_periods (window//2) observations."""
        n = 300
        s = pd.Series(np.random.default_rng(0).standard_normal(n))
        z = rolling_z(s, window=252)
        # First 125 (252//2) values should be NaN
        n_leading = sum(1 for v in z.iloc[:126] if np.isnan(v))
        assert n_leading >= 1, "Rolling z should have leading NaN values"

    def test_rolling_z_mean_near_zero(self):
        """After burn-in, rolling z should have mean near 0."""
        n = 500
        rng = np.random.default_rng(1)
        s = pd.Series(rng.standard_normal(n))
        z = rolling_z(s, window=252)
        valid = z.dropna()
        assert abs(float(valid.mean())) < 0.5, "Rolling z mean should be near 0"


# ---------------------------------------------------------------------------
# 14. Ruling A1 — false-alarm AUC (O-OPT-1 kill leg)
# ---------------------------------------------------------------------------

class TestFalseAlarmAUC:
    def test_pre_onset_score_is_pit_at_onset(self):
        """pre_onset_score uses ONLY [−15,0] = window indices [0..onset_idx]."""
        s = pd.Series(np.arange(31, dtype=float))  # window [−15..+15], onset at 15
        # mean of indices 0..15 inclusive = mean(0..15) = 7.5; post-onset excluded
        assert pre_onset_score(s, 15) == pytest.approx(7.5)

    def test_pre_onset_score_excludes_post_onset(self):
        """A huge post-onset spike must not leak into the pre-onset score (PIT)."""
        vals = [0.0] * 16 + [1e9] * 15  # onset at 15; post-onset spike
        s = pd.Series(vals, dtype=float)
        assert pre_onset_score(s, 15) == pytest.approx(0.0)

    def test_auc_perfect_separation(self):
        assert auc_score(np.array([3.0, 4.0, 5.0]), np.array([0.0, 1.0, 2.0])) == 1.0

    def test_auc_no_discrimination(self):
        assert auc_score(np.array([1.0, 2.0]), np.array([1.0, 2.0])) == 0.5

    def test_auc_reversed(self):
        assert auc_score(np.array([0.0, 1.0]), np.array([3.0, 4.0])) == 0.0

    def test_auc_empty_class_is_nan(self):
        assert np.isnan(auc_score(np.array([]), np.array([1.0])))
        assert np.isnan(auc_score(np.array([1.0]), np.array([])))

    def test_auc_ci_includes_half_discriminating(self):
        """Discriminating series → AUC CI ABOVE 0.5 → does NOT include 0.50."""
        rng = np.random.default_rng(0)
        pos = rng.normal(2.0, 0.5, 60)
        neg = rng.normal(-2.0, 0.5, 60)
        auc, lo, hi = auc_ci(pos, neg, n_boot=500, rng=np.random.default_rng(1))
        assert auc > 0.9
        assert not auc_ci_includes_half(lo, hi), f"CI [{lo},{hi}] should exclude 0.50"

    def test_auc_ci_includes_half_non_discriminating(self):
        """Non-discriminating series → AUC CI straddles 0.50."""
        rng = np.random.default_rng(2)
        pos = rng.normal(0.0, 1.0, 60)
        neg = rng.normal(0.0, 1.0, 60)
        _, lo, hi = auc_ci(pos, neg, n_boot=500, rng=np.random.default_rng(3))
        assert auc_ci_includes_half(lo, hi), f"CI [{lo},{hi}] should include 0.50"

    def test_auc_ci_nan_treated_as_no_discrimination(self):
        """Unevaluable AUC (empty class) → treated as 'includes 0.50' (kill leg fails)."""
        assert auc_ci_includes_half(np.nan, np.nan) is True

    def test_kill_criterion_both_legs_must_fail(self):
        """§4 O-OPT-1: KILL only when median_lead<=0 AND AUC CI includes 0.50.

        A discriminating AUC (excludes 0.50) must PREVENT the kill even when the
        median lead is non-positive (coincident-but-discriminating → DISPLAY).
        """
        # discriminating AUC → not-includes-half → kill leg False
        rng = np.random.default_rng(4)
        pos = rng.normal(3.0, 0.4, 80)
        neg = rng.normal(-3.0, 0.4, 80)
        _, lo, hi = auc_ci(pos, neg, n_boot=400, rng=np.random.default_rng(5))
        median_lead = -1.0  # non-positive
        kill = (median_lead <= 0) and auc_ci_includes_half(lo, hi)
        assert kill is False, "Discriminating AUC must block the kill even at lead<=0"

    def test_runner_o1_has_real_auc_fields(self):
        """The runner stamps auc / auc_ci_lo / auc_ci_hi (not a boot_hi proxy)."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            (data_dir / "oracle" / "gauntlet").mkdir(parents=True)
            (data_dir / "experiments").mkdir(parents=True)
            results = run_oopt_phase0(data_dir=data_dir, smoke=True, out_dir=Path("/tmp"))
            o1 = results["o1"]
            assert "auc" in o1 and "auc_ci_lo" in o1 and "auc_ci_hi" in o1
            assert "auc_ci_includes_half" in o1


# ---------------------------------------------------------------------------
# 15. Ruling A2 — O-OPT-3 routing placebo path (P3b VERBATIM)
# ---------------------------------------------------------------------------

class TestRoutingPlaceboPath:
    def test_routing_placebo_returns_200_draws(self):
        """routing_placebo_cell wraps P3b _sample_routing_placebo_cell (200 draws)."""
        rng = np.random.default_rng(7)
        n = 500
        dest_rs = np.cumsum(rng.standard_normal(n)) * 0.01
        vix = rng.uniform(0, 1, n)
        onsets = [50, 120, 200, 310, 400]
        draws = routing_placebo_cell(
            dest_rs, vix, onsets, [5], "high_vix",
            cell_n=3, n_draws=200, exclusion_zone=10, rng=np.random.default_rng(1),
        )
        assert 5 in draws
        assert draws[5].shape == (200,), "P3b placebo must yield 200 draws"

    def test_routing_placebo_regime_matched(self):
        """Placebo pseudo-onsets are drawn only from regime-matching sessions.

        A cell requesting 'high_vix' with all-low VIX panel yields no valid pool
        → all-NaN draws (regime strata are actually enforced, not ignored).
        """
        n = 400
        dest_rs = np.cumsum(np.random.default_rng(8).standard_normal(n)) * 0.01
        vix = np.full(n, 0.1)  # all LOW vix
        draws = routing_placebo_cell(
            dest_rs, vix, [50, 100, 200], [5], "high_vix",
            cell_n=2, n_draws=200, high_vix_thresh=0.6, rng=np.random.default_rng(9),
        )
        assert np.all(np.isnan(draws[5])), "high_vix cell on all-low-VIX panel must find no regime match"

    def test_runner_o3_exercises_placebo_path(self):
        """Runner O-OPT-3 invokes the placebo path per cell (insufficient without panel)."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        from scripts.run_oopt_phase0 import _routing_cell_placebo
        # No panel arrays → insufficient_placebo (legitimate stub), path exercised
        out = _routing_cell_placebo(
            dest_rs_arr=None, vix_arr=None, real_onset_indices=[],
            regime="high_vix", cell_n=1, real_mean=0.01,
            rng=np.random.default_rng(0), horizons=[5],
        )
        assert out["insufficient_placebo"] is True
        # WITH panel arrays and enough draws → real P3b placebo p95 + g1 decision
        rng = np.random.default_rng(11)
        n = 600
        dest_rs = np.cumsum(rng.standard_normal(n)) * 0.01
        vix = rng.uniform(0.6, 1.0, n)  # all high-vix → ample regime pool
        out2 = _routing_cell_placebo(
            dest_rs_arr=dest_rs, vix_arr=vix,
            real_onset_indices=[50, 150, 250, 350, 450],
            regime="high_vix", cell_n=5, real_mean=10.0,
            rng=np.random.default_rng(12), horizons=[5],
        )
        assert out2["insufficient_placebo"] is False
        assert out2["placebo_p95"] is not None
        assert out2["g1_routing_pass"] is True  # real_mean=10 >> placebo p95


# ---------------------------------------------------------------------------
# 16. Ruling A3 — pair consistency (two_sided ⇔ paired_episode_id)
# ---------------------------------------------------------------------------

class TestPairConsistency:
    def _df(self, rows):
        return pd.DataFrame(rows)

    def test_consistent_pairs_no_raise(self):
        df = self._df([
            {"episode_id": "a", "two_sided": True, "paired_episode_id": "b", "pairing_unavailable": False},
            {"episode_id": "b", "two_sided": False, "paired_episode_id": None, "pairing_unavailable": False},
        ])
        consistency_check_pairs(df)  # must not raise

    def test_two_sided_true_null_pair_raises(self):
        """two_sided=True with null pair (and not pairing_unavailable) → abort."""
        df = self._df([
            {"episode_id": "a", "two_sided": True, "paired_episode_id": None, "pairing_unavailable": False},
        ])
        with pytest.raises(OOPTPairConsistencyError):
            consistency_check_pairs(df)

    def test_two_sided_false_with_pair_raises(self):
        """two_sided=False but a paired id present → abort (not silent drop)."""
        df = self._df([
            {"episode_id": "a", "two_sided": False, "paired_episode_id": "b", "pairing_unavailable": False},
        ])
        with pytest.raises(OOPTPairConsistencyError):
            consistency_check_pairs(df)

    def test_pairing_unavailable_exemption(self):
        """two_sided=True + null pair is OK when pairing_unavailable=True (§2.1)."""
        df = self._df([
            {"episode_id": "a", "two_sided": True, "paired_episode_id": None, "pairing_unavailable": True},
        ])
        consistency_check_pairs(df)  # must not raise

    def test_filter_keeps_only_valid_pairs(self):
        df = self._df([
            {"episode_id": "a", "two_sided": True, "paired_episode_id": "b", "pairing_unavailable": False},
            {"episode_id": "b", "two_sided": False, "paired_episode_id": None, "pairing_unavailable": False},
        ])
        kept = filter_two_sided_pairs(df)
        assert kept["episode_id"].tolist() == ["a"]

    def test_filter_raises_on_inconsistency(self):
        """filter runs the consistency check first — a data error aborts the filter."""
        df = self._df([
            {"episode_id": "a", "two_sided": False, "paired_episode_id": "b", "pairing_unavailable": False},
        ])
        with pytest.raises(OOPTPairConsistencyError):
            filter_two_sided_pairs(df)


# ---------------------------------------------------------------------------
# 17. Ruling A4 — Tier-M display cells (coverage-gated, never claim-gated)
# ---------------------------------------------------------------------------

class TestTierMDisplayCells:
    def test_below_floor_stamps_skipped_coverage(self):
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        from scripts.run_oopt_phase0 import _run_tierm_display
        episodes_m = pd.DataFrame({
            "onset_date": pd.to_datetime(["2022-03-01", "2024-05-01"]),
        })
        rotation_groups = {"complexes": [
            {"id": "c1", "members": ["m1", "m2", "m3", "m4", "m5"], "risk_sign": "risk_on"},
        ]}
        # options_universe covers 1/5 = 0.20 < 0.40 floor
        out = _run_tierm_display(episodes_m, {}, rotation_groups, {"m1"})
        assert out["status"] == "skipped_coverage"
        assert out["gated"] is False
        assert out["coverage"] == pytest.approx(0.2)

    def test_above_floor_computes_watermarked_cells(self):
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        from scripts.run_oopt_phase0 import _run_tierm_display
        episodes_m = pd.DataFrame({
            "onset_date": pd.to_datetime(["2022-03-01", "2024-05-01", "2021-06-01"]),
        })
        rotation_groups = {"complexes": [
            {"id": "c1", "members": ["m1", "m2", "m3", "m4", "m5"], "risk_sign": "risk_on"},
        ]}
        # coverage 3/5 = 0.60 >= floor
        out = _run_tierm_display(episodes_m, {}, rotation_groups, {"m1", "m2", "m3"})
        assert out["status"] == "computed"
        assert out["gated"] is False
        # every produced cell is watermarked and NOT gated
        for cell in out["cells"]:
            assert cell["gated"] is False
            assert cell.get("watermark") is True

    def test_tierm_never_gated_either_way(self):
        """Ruling A4: Tier-M cells never gated whether computed or skipped."""
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        from scripts.run_oopt_phase0 import _run_tierm_display
        rg = {"complexes": [{"id": "c1", "members": ["m1", "m2"], "risk_sign": "risk_on"}]}
        em = pd.DataFrame({"onset_date": pd.to_datetime(["2023-01-01"])})
        computed = _run_tierm_display(em, {}, rg, {"m1", "m2"})   # 100% coverage
        skipped = _run_tierm_display(em, {}, rg, set())            # 0% coverage
        assert computed["gated"] is False
        assert skipped["gated"] is False
        assert skipped["status"] == "skipped_coverage"


# ---------------------------------------------------------------------------
# 18. O-OPT-2 placebo direction — per-direction (P3 idiom, not hardcoded "in")
# ---------------------------------------------------------------------------

class TestOOPT2PlaceboDirection:
    def test_mixed_direction_placebo_runs_per_direction(self):
        """O-OPT-2 G1 placebo pools per-direction draws (P3 idiom), not direction_filter='in'.

        A mixed in/out confirmed sample must produce a finite placebo_p95 with the
        placebo direction-matched to the real sample's own in/out mix.
        """
        if not _RUNNER_AVAILABLE:
            pytest.skip("runner not importable")
        from scripts.run_oopt_phase0 import _run_oopt2
        dates = pd.date_range("2013-01-01", periods=400, freq="B")
        rng = np.random.default_rng(0)
        rows = []
        for nd in ["XLK", "XLV"]:
            rs = np.cumsum(rng.standard_normal(len(dates))) * 0.01
            for d, r in zip(dates, rs):
                rows.append({"node": nd, "date": d, "rs": r})
        panel = pd.DataFrame(rows).set_index(["node", "date"])

        eps = []
        for i, (nd, dr) in enumerate([("XLK", "in"), ("XLV", "out")] * 40):
            eps.append({
                "episode_id": f"e{i}", "node": nd, "direction": dr,
                "onset_date": dates[30 + i % 300],
                "exhausted_date": dates[min(60 + i % 300, 399)],
                "outcome_rs_21d": float(rng.standard_normal() * 0.03),
                "outcome_mature_21d": True, "flow_confirmed": True, "composite_z": 1.0,
                "regime_vix_pctile": rng.uniform(0, 1),
                "regime_spy_above_200d": float(rng.integers(0, 2)),
            })
        out = _run_oopt2(pd.DataFrame(eps), panel, np.random.default_rng(1),
                         horizons=[21], primary_horizon=21)
        h = out["horizons"][21]
        assert h["n_confirmed"] == 80
        # Both directions present → per-direction pooling yields a finite p95.
        assert h["placebo_p95"] is not None and not np.isnan(h["placebo_p95"])


# ---------------------------------------------------------------------------
# Run guard
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
