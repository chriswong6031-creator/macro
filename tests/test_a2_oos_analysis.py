"""Unit tests for scripts/research/a2_oos_analysis.py — freeze-anchor harness.

Three categories:
  1. Roster integrity — correct Σ=29, family counts, unique IDs, stamps
  2. Gate refusal logic:
       (a) cluster_count under floor with operator_ack -> REFUSES
       (b) cluster_count at floor without operator_ack -> REFUSES
       (c) cluster_count under floor without operator_ack -> REFUSES
       (d) cluster_count at floor with operator_ack -> PROCEEDS (synthetic only)
  3. BH-FDR machinery — correctness of the program-wide correction

IMPORTANT: tests use ONLY synthetic fixtures. No real label data (OOS-2 contact
freeze — AMENDMENT_A2_G1_RETEST.md §4). No parquet files are read.

Run:
    python -m pytest tests/test_a2_oos_analysis.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.research.a2_oos_analysis import (  # noqa: E402
    CLUSTER_FLOOR,
    EXPECTED_FAMILY_COUNTS,
    EXPECTED_TOTAL,
    ROSTER,
    _bh_fdr,
    _run_outcome_contact_on_data,
    check_no_run_gate,
    roster_sha256,
    run_program_wide_fdr,
)


# ---------------------------------------------------------------------------
# 1. Roster integrity
# ---------------------------------------------------------------------------


class TestRosterIntegrity:
    def test_total_hypothesis_count(self):
        """Σ must equal 29 (pre-registered in AMENDMENT_A2_G1_RETEST.md §2)."""
        assert len(ROSTER) == EXPECTED_TOTAL, (
            f"Expected Σ={EXPECTED_TOTAL}, got {len(ROSTER)}"
        )

    def test_family_hypothesis_counts(self):
        """Each family must have the pre-registered m."""
        from collections import Counter
        counts = Counter(h["family"] for h in ROSTER)
        for fam, expected_m in EXPECTED_FAMILY_COUNTS.items():
            assert counts[fam] == expected_m, (
                f"Family '{fam}': expected m={expected_m}, got {counts[fam]}"
            )

    def test_hypothesis_ids_unique(self):
        """All hypothesis IDs must be unique."""
        from collections import Counter
        ids = [h["hypothesis_id"] for h in ROSTER]
        counts = Counter(ids)
        dupes = [k for k, v in counts.items() if v > 1]
        assert not dupes, f"Duplicate hypothesis IDs: {dupes}"

    def test_f1_fundamental_family_present(self):
        """F1 fundamental family must have m=9."""
        fam = [h for h in ROSTER if h["family"] == "long_hold.fundamental"]
        assert len(fam) == 9

    def test_f2_washout_tf_family_present(self):
        """F2 washout_tf family must have m=10."""
        fam = [h for h in ROSTER if h["family"] == "long_hold.washout_tf"]
        assert len(fam) == 10

    def test_f3_expect_drift_family_present(self):
        """F3 expect_drift family must have m=7."""
        fam = [h for h in ROSTER if h["family"] == "long_hold.expect_drift"]
        assert len(fam) == 7

    def test_f4_insider_sponsor_family_present(self):
        """F4 insider_sponsor_lh family must have m=3."""
        fam = [h for h in ROSTER if h["family"] == "long_hold.insider_sponsor_lh"]
        assert len(fam) == 3

    def test_restricted_range_stamps_correct(self):
        """Only depth features in F2 should carry restricted_range=True."""
        restricted = [h for h in ROSTER if h["restricted_range"]]
        restricted_ids = {h["hypothesis_id"] for h in restricted}
        # Per AMENDMENT_LH_R11_MULTI_FAMILY.md §LH-R11.3:
        # depth-magnitude features: pct_below_200dma, drawdown_from_52wk_high,
        # mtf_washout_count (F2-04, F2-05, F2-06)
        expected_restricted = {"F2-04", "F2-05", "F2-06"}
        assert restricted_ids == expected_restricted, (
            f"restricted_range stamps: expected {expected_restricted}, "
            f"got {restricted_ids}"
        )

    def test_two_sided_depth_features(self):
        """Depth features F2-05/F2-06 must have direction='two-sided' (N2)."""
        depth_ids = {"F2-05", "F2-06"}
        for h in ROSTER:
            if h["hypothesis_id"] in depth_ids:
                assert h["direction"] == "two-sided", (
                    f"{h['hypothesis_id']} must be two-sided per N2 correction"
                )

    def test_binary_features_use_fisher(self):
        """Binary features must use Fisher (or Fisher/chi2), NOT MWU (M2 deviation)."""
        binary_hyps = [h for h in ROSTER if h["type"] == "bin"]
        for h in binary_hyps:
            assert "Fisher" in h["test"] or "chi2" in h["test"], (
                f"{h['hypothesis_id']} is binary but has test={h['test']}; "
                "binary features must use Fisher/chi2 (M2 deviation from §6.4)"
            )

    def test_required_fields_present(self):
        """Every hypothesis must have all required fields."""
        required = {
            "hypothesis_id", "family", "feature", "type", "direction",
            "test", "restricted_range", "feature_provenance", "notes",
        }
        for h in ROSTER:
            missing = required - set(h.keys())
            assert not missing, (
                f"Hypothesis {h.get('hypothesis_id', '?')} missing fields: {missing}"
            )

    def test_feature_provenance_non_empty(self):
        """feature_provenance must be a non-empty string for every hypothesis."""
        for h in ROSTER:
            assert isinstance(h["feature_provenance"], str) and h["feature_provenance"].strip(), (
                f"{h['hypothesis_id']} has empty feature_provenance (LH-R11.3 requirement)"
            )

    def test_roster_sha256_deterministic(self):
        """roster_sha256() must return the same value on repeated calls."""
        h1 = roster_sha256()
        h2 = roster_sha256()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex string

    def test_roster_sha256_is_hex_string(self):
        h = roster_sha256()
        int(h, 16)  # raises ValueError if not hex


# ---------------------------------------------------------------------------
# 2. Gate refusal logic
# ---------------------------------------------------------------------------


class TestGateRefusal:
    """Prove the hard no-run gate behaves correctly.

    The gate must refuse in all cases where EITHER condition is unmet,
    and must proceed (not raise) when BOTH are met.
    Uses ONLY synthetic inputs — never touches real label data.
    """

    def _assert_refuses(
        self,
        cluster_count,
        operator_ack,
        *,
        match_fragment: str = "HARD REFUSAL",
    ):
        """Helper: assert check_no_run_gate raises SystemExit."""
        with pytest.raises(SystemExit) as exc_info:
            check_no_run_gate(
                cluster_count=cluster_count,
                operator_ack=operator_ack,
            )
        assert exc_info.value.code != 0, (
            "Gate must exit with non-zero code on refusal"
        )

    def test_under_floor_with_ack_refuses(self):
        """Under-floor cluster count REFUSES even with --operator-ack.

        Synthetic data: cluster_count = CLUSTER_FLOOR - 1 (floor not met).
        Expected: SystemExit (gate refuses).
        """
        under_floor = CLUSTER_FLOOR - 1  # e.g. 24
        self._assert_refuses(
            cluster_count=under_floor,
            operator_ack=True,
        )

    def test_at_floor_without_ack_refuses(self):
        """Floor-met cluster count REFUSES without --operator-ack.

        Synthetic data: cluster_count = CLUSTER_FLOOR (floor met), no ack.
        Expected: SystemExit (gate refuses).
        """
        self._assert_refuses(
            cluster_count=CLUSTER_FLOOR,
            operator_ack=False,
        )

    def test_under_floor_without_ack_refuses(self):
        """Under-floor AND no-ack: REFUSES.

        Synthetic data: cluster_count = 0, operator_ack = False.
        Expected: SystemExit (gate refuses).
        """
        self._assert_refuses(
            cluster_count=0,
            operator_ack=False,
        )

    def test_none_cluster_count_with_ack_refuses(self):
        """Missing cluster_count REFUSES even with --operator-ack."""
        self._assert_refuses(
            cluster_count=None,
            operator_ack=True,
        )

    def test_none_cluster_count_without_ack_refuses(self):
        """Missing cluster_count AND no-ack REFUSES."""
        self._assert_refuses(
            cluster_count=None,
            operator_ack=False,
        )

    def test_at_floor_with_ack_proceeds(self):
        """BOTH conditions met: cluster_count >= floor AND operator_ack -> proceeds.

        Synthetic data: cluster_count = CLUSTER_FLOOR, operator_ack = True.
        Expected: no exception raised (gate clears).
        """
        # Must not raise
        check_no_run_gate(
            cluster_count=CLUSTER_FLOOR,
            operator_ack=True,
        )

    def test_above_floor_with_ack_proceeds(self):
        """Well above floor with ack: proceeds.

        Synthetic data: cluster_count = 50, operator_ack = True.
        """
        check_no_run_gate(
            cluster_count=50,
            operator_ack=True,
        )

    def test_exit_code_is_nonzero_on_refusal(self):
        """Refusal exit code must be non-zero (CLUSTER_FLOOR - 1, no ack)."""
        with pytest.raises(SystemExit) as exc_info:
            check_no_run_gate(
                cluster_count=CLUSTER_FLOOR - 1,
                operator_ack=False,
            )
        assert exc_info.value.code not in (None, 0)

    def test_synthetic_outcome_contact_after_gate_clears(self):
        """After gate clears, outcome-contact stage runs on synthetic data only.

        Uses synthetic fire_rows and label_rows — never reads real data.
        Verifies the function returns a result dict with required keys.
        """
        # Synthetic fire rows (no real data)
        synthetic_fires = [
            {
                "ticker": "SYNTH_A",
                "fire_date": "2025-03-01",
                "piotroski_f": 7.0,
                "sue": 1.2,
            },
            {
                "ticker": "SYNTH_B",
                "fire_date": "2025-04-01",
                "piotroski_f": 3.0,
                "sue": -0.5,
            },
        ]
        # Synthetic label rows (not OOS-2 real data — purely synthetic for gate test)
        synthetic_labels = [
            {
                "ticker": "SYNTH_A",
                "fire_date": "2025-03-01",
                "label": "compounder",
                "missed_hold": True,
            },
            {
                "ticker": "SYNTH_B",
                "fire_date": "2025-04-01",
                "label": "tactical_only",
                "missed_hold": False,
            },
        ]
        result = _run_outcome_contact_on_data(synthetic_fires, synthetic_labels)
        assert "roster_sha256" in result
        assert "n_joined" in result
        assert result["n_joined"] == 2
        assert result["n_missed_hold"] == 1
        assert result["n_tactical_only"] == 1
        assert result["roster_sha256"] == roster_sha256()


# ---------------------------------------------------------------------------
# 3. BH-FDR machinery
# ---------------------------------------------------------------------------


class TestBHFDR:
    """Unit tests for the program-wide BH-FDR correction."""

    def test_all_null_p_values_fail(self):
        """All p=1.0 -> none survive."""
        p_values = [1.0] * 5
        survive = _bh_fdr(p_values)
        assert not any(survive)

    def test_all_highly_significant_survive(self):
        """All p=0.001 -> all survive (well below any threshold)."""
        p_values = [0.001] * 5
        survive = _bh_fdr(p_values)
        assert all(survive)

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert _bh_fdr([]) == []

    def test_single_hypothesis_significant(self):
        """Single p=0.05 with q=0.10 should survive (0.05 <= 0.10*1/1 = 0.10)."""
        survive = _bh_fdr([0.05], q=0.10)
        assert survive == [True]

    def test_single_hypothesis_not_significant(self):
        """Single p=0.15 with q=0.10 should not survive (0.15 > 0.10*1/1 = 0.10)."""
        survive = _bh_fdr([0.15], q=0.10)
        assert survive == [False]

    def test_bh_step_up_logic(self):
        """Classic BH example: 6 hypotheses, q=0.05.

        p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.450]
        Sorted: 0.001, 0.008, 0.039, 0.041, 0.042, 0.450
        Thresholds: 0.05*1/6=0.00833, 2/6=0.01667, 3/6=0.025, 4/6=0.03333,
                    5/6=0.04167, 6/6=0.05
        Surviving (p[k] <= threshold[k]): 0.001 YES, 0.008 YES, 0.039 NO...
        Largest k where p[k]<=threshold[k]: k=1 (0-indexed).
        So only first 2 survive.
        """
        p_values = [0.001, 0.008, 0.039, 0.041, 0.042, 0.450]
        survive = _bh_fdr(p_values, q=0.05)
        # Only the two smallest p-values should survive
        surviving_p = [p for p, s in zip(p_values, survive) if s]
        assert sorted(surviving_p) == [0.001, 0.008]

    def test_program_wide_fdr_returns_marginal_flag(self):
        """run_program_wide_fdr marks non-surviving hypotheses as marginal."""
        hids = ["H1", "H2", "H3"]
        p_values = [0.001, 0.09, 0.50]
        result = run_program_wide_fdr(hids, p_values)
        assert result["H1"]["survives_program_fdr"] is True
        assert result["H1"]["program_fdr_marginal"] is False
        assert result["H3"]["survives_program_fdr"] is False
        assert result["H3"]["program_fdr_marginal"] is True

    def test_program_wide_fdr_full_roster_size(self):
        """Sanity: run_program_wide_fdr handles all 29 hypotheses."""
        hids = [h["hypothesis_id"] for h in ROSTER]
        # Synthetic p-values: first 5 highly significant, rest nulls
        p_values = [0.001] * 5 + [0.999] * (EXPECTED_TOTAL - 5)
        result = run_program_wide_fdr(hids, p_values)
        assert len(result) == EXPECTED_TOTAL
        # All must have the required keys
        for hid, res in result.items():
            assert "p_value" in res
            assert "survives_program_fdr" in res
            assert "program_fdr_marginal" in res


# ---------------------------------------------------------------------------
# 4. CLI smoke tests (no real data)
# ---------------------------------------------------------------------------


class TestCLI:
    def test_prep_mode_runs(self, capsys):
        """--mode=prep runs without error and prints roster info."""
        from scripts.research.a2_oos_analysis import main
        ret = main(["--mode=prep"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "FROZEN ROSTER" in captured.out
        assert str(EXPECTED_TOTAL) in captured.out

    def test_print_hash_mode(self, capsys):
        """--print-hash prints a 64-char hex string."""
        from scripts.research.a2_oos_analysis import main
        ret = main(["--print-hash"])
        assert ret == 0
        out = capsys.readouterr().out.strip()
        assert len(out) == 64
        int(out, 16)  # must be valid hex

    def test_run_mode_under_floor_refuses(self):
        """--mode=run with cluster count under floor exits non-zero."""
        from scripts.research.a2_oos_analysis import main
        under_floor = str(CLUSTER_FLOOR - 1)
        with pytest.raises(SystemExit) as exc_info:
            main(["--mode=run", "--operator-ack", f"--cluster-count={under_floor}"])
        assert exc_info.value.code != 0

    def test_run_mode_no_ack_refuses(self):
        """--mode=run without --operator-ack exits non-zero even at floor."""
        from scripts.research.a2_oos_analysis import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--mode=run", f"--cluster-count={CLUSTER_FLOOR}"])
        assert exc_info.value.code != 0
