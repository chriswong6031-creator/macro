"""Hostile tests for the read-only China Prophet R0 replay."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research/cn_prophet_recovery/r0_current_safety_replay.py"
RESULT = ROOT / "research/cn_prophet_recovery/r0_current_safety_replay_results.json"
SPEC = importlib.util.spec_from_file_location("cn_prophet_r0", SCRIPT)
assert SPEC and SPEC.loader
r0 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r0
SPEC.loader.exec_module(r0)


def test_carry_forward_rows_are_one_episode_not_independent_trials():
    episodes = r0.build_episode_memberships(
        {
            "2026-08-18": {"A", "B"},
            "2026-08-19": {"A", "B"},
            "2026-08-20": {"A"},
            "2026-08-21": {"A", "B"},
        }
    )
    assert [(row["entry_date"], row["ticker"]) for row in episodes] == [
        ("2026-08-18", "A"),
        ("2026-08-18", "B"),
        ("2026-08-21", "B"),
    ]
    assert sum(row["daily_materializations"] for row in episodes) == 7
    assert sum(row["carry_forward_materializations"] for row in episodes) == 4


def test_daily_order_comparison_detects_population_and_rank_mismatch():
    live = pd.DataFrame(
        [
            {"date": "2026-08-18", "ticker": "A", "board_rank": 1},
            {"date": "2026-08-18", "ticker": "B", "board_rank": 2},
        ]
    )
    control = pd.DataFrame(
        [
            {"date": "2026-08-18", "ticker": "A", "board_rank": 2},
            {"date": "2026-08-18", "ticker": "C", "board_rank": 1},
        ]
    )
    compared = r0.compare_daily_orders(live, control)
    assert compared["live_only_n"] == 1
    assert compared["control_only_n"] == 1
    assert compared["rank_delta_n"] == 1
    assert compared["identical_post_cap_sets_and_ranks"] is False


def test_missing_r4_artifact_is_not_coerced_to_no_breach():
    evaluated = r0.evaluate_r4(
        treatment_values=[], control_values=[], metric_present_in_audit=False
    )
    assert evaluated["state"] == "R4_SOURCE_MISSING_OR_MALFORMED"
    assert evaluated["treatment_median_excess_pct"] is None
    assert evaluated["serving_effect"] == "NONE"


def test_r4_needs_sixty_comparable_treatment_rows():
    immature = r0.evaluate_r4(
        treatment_values=[-1.0] * 59,
        control_values=[0.0] * 59,
        metric_present_in_audit=True,
    )
    assert immature["state"] == "INSUFFICIENT_MATURITY"
    breach = r0.evaluate_r4(
        treatment_values=[-1.0] * 60,
        control_values=[0.0] * 60,
        metric_present_in_audit=True,
    )
    assert breach["state"] == "BREACH_WARNING_PROPOSAL"
    assert breach["treatment_minus_control_median_excess_pct"] == -1.0


def test_future_candidate_clock_is_explicit_chronology_defect():
    row = {
        "stamp_date": "2026-08-18",
        "signal_asof": "2026-08-17",
        "signal_bar_asof": "2026-08-19",
        "micro_asof": None,
        "micro_batch_asof": None,
        "board_asof": "2026-08-18",
        "sector_turn_asof": None,
        "narrative_asof": None,
    }
    assert r0.chronology_violations(row) == ["signal_bar_asof"]


def test_null_intelligence_stays_null_in_group_decomposition():
    frame = pd.DataFrame(
        [
            {
                "intel_coverage": None, "admission_date": "2026-08-18",
                "replay_excess": -2.0, "replay_pnl": -1.0,
            },
            {
                "intel_coverage": "measured", "admission_date": "2026-08-19",
                "replay_excess": 1.0, "replay_pnl": 2.0,
            },
        ]
    )
    groups = r0._group_metrics(frame, "intel_coverage")
    unavailable = next(row for row in groups if row["value"] == "(unavailable)")
    assert unavailable["n"] == 1
    assert unavailable["mean_excess_pct"] == -2.0


def test_committed_receipt_is_fail_closed_and_no_effect():
    receipt = json.loads(RESULT.read_text(encoding="utf-8"))
    assert receipt["schema"] == r0.SCHEMA
    assert receipt["scope"]["read_only"] is True
    assert receipt["scope"]["live_effect"] == "NONE"
    assert receipt["identity_and_materialization"]["ledger_row_n"] == 172
    assert receipt["identity_and_materialization"]["live_episode_n"] == 172
    assert receipt["outcome_replay"]["matured_n"] == 65
    assert receipt["outcome_replay"]["independent_cohort_n"] == 4
    assert receipt["ordering_reconstruction"]["classification"] == "V3_FALLBACK"
    assert receipt["ordering_reconstruction"]["treatment_daily_rows"] == 0
    assert receipt["r4_safety"]["state"] == "R4_SOURCE_MISSING_OR_MALFORMED"
    assert receipt["verdict"]["serving_change_authority"] == "NONE"


def test_receipt_reconciles_every_published_mature_outcome():
    receipt = json.loads(RESULT.read_text(encoding="utf-8"))
    counts = receipt["outcome_replay"]["validation_counts"]
    assert counts["fill_date_match"] == 172
    assert counts["entry_match"] == 172
    assert counts["matured"] == 65
    assert counts["exit_match"] == 65
    assert counts["pnl_match"] == 65
    assert counts["excess_match"] == 65


def test_result_exposes_effective_basis_before_any_r4_conclusion():
    receipt = json.loads(RESULT.read_text(encoding="utf-8"))
    ordering = receipt["ordering_reconstruction"]
    assert ordering["fallback_daily_rows"] == ordering["actual_post_cap"]["live_daily_rows"]
    assert ordering["actual_effective_pre_cap"]["effective_vs_v3_rank_delta_n"] == 0
    assert ordering["requested_v4_pre_cap_delta"] is None
    assert ordering["actual_post_cap"]["identical_post_cap_sets_and_ranks"] is True


def test_negative_outcome_is_not_mislabeled_v4_ordering_failure():
    receipt = json.loads(RESULT.read_text(encoding="utf-8"))
    assert receipt["verdict"]["current_outcome"] == "NEGATIVE_REAL_IMMATURE"
    assert receipt["verdict"]["v4_ordering_effect"] == "NOT_ESTIMABLE_ZERO_TREATMENT"
    cause = {row["classification"]: row["ruling"] for row in receipt["cause_ledger"]}
    assert cause["V4_ORDERING_FAILURE"] == "NOT_ESTIMABLE_ZERO_TREATMENT"
    assert cause["ADVERSE_SAMPLE / NOT_IDENTIFIED"] == "SUPPORTED_CURRENT_RULING"
