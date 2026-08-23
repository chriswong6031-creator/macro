from __future__ import annotations

from engine.prophet_voi import DESCRIPTIVE_ONLY, MEASURED, NOT_APPLICABLE, UNAVAILABLE_FIELD
from engine.prophet_voi_eawc import (
    early_actionable_capture_recall,
    eventual_move_consumed_fraction,
    first_surface_actionability_rate,
    paired_surface_lead_sessions,
    realized_r_multiple,
    time_to_payoff_r,
    unusable_or_unknown_at_first_surface_rate,
)


def test_paired_surface_lead_keeps_one_sided_capture_cells_separate() -> None:
    got = paired_surface_lead_sessions(
        challenger_first_session=[5, 6, None, None],
        champion_first_session=[8, None, 9, None],
    )
    assert got["state"] == MEASURED
    assert got["reference_subjects"] == 4
    assert got["paired_subjects"] == 1
    assert got["mean_lead_sessions"] == 3.0
    assert got["median_lead_sessions"] == 3.0
    assert got["challenger_only"] == 1
    assert got["champion_only"] == 1
    assert got["neither"] == 1
    assert got["one_sided_lead_imputed"] is False


def test_early_actionable_capture_recall_keeps_missed_and_blocked_positives() -> None:
    got = early_actionable_capture_recall(
        positive_label=[True, True, True, False],
        surfaced=[True, True, None, True],
        actionable_at_first_surface=[True, None, None, True],
    )
    assert got["state"] == MEASURED
    assert got["positive_reference_subjects"] == 3
    assert got["captured_actionable"] == 1
    assert got["missing_or_blocked_actionability"] == 1
    assert got["missed_surface"] == 1
    assert got["value"] == round(1 / 3, 6)
    assert got["denominator_includes_missed_and_blocked"] is True


def test_early_actionable_capture_refuses_unknown_outcome_labels() -> None:
    got = early_actionable_capture_recall(
        positive_label=[True, None],
        surfaced=[True, True],
        actionable_at_first_surface=[True, True],
    )
    assert got["state"] == UNAVAILABLE_FIELD


def test_first_surface_actionability_missing_stays_in_denominator() -> None:
    got = first_surface_actionability_rate(
        applicable_first_surface=[True, True, True, False],
        actionable=[True, None, False, None],
    )
    assert got["state"] == MEASURED
    assert got["applicable_first_surfaces"] == 3
    assert got["actionable"] == 1
    assert got["missing_or_blocked"] == 1
    assert got["explicit_not_actionable"] == 1
    assert got["value"] == round(1 / 3, 6)
    assert got["missing_in_denominator"] is True


def test_first_surface_actionability_all_not_applicable_is_not_applicable() -> None:
    got = first_surface_actionability_rate(
        applicable_first_surface=[False, False],
        actionable=[None, None],
    )
    assert got["state"] == NOT_APPLICABLE
    assert got["value"] is None


def test_unusable_guardrail_counts_unknown_as_unusable_not_as_success() -> None:
    got = unusable_or_unknown_at_first_surface_rate(
        applicable_first_surface=[True, True, True, False],
        chased_or_closed=[False, None, True, None],
    )
    assert got["state"] == MEASURED
    assert got["applicable_first_surfaces"] == 3
    assert got["chased_or_closed"] == 1
    assert got["unknown_or_blocked"] == 1
    assert got["value"] == round(2 / 3, 6)
    assert got["unknown_counts_as_unusable_guardrail"] is True


def test_realized_r_requires_decision_time_initial_risk() -> None:
    got = realized_r_multiple(
        direction_signed_pnl=10.0,
        entry_price=100.0,
        initial_invalidation_price=95.0,
    )
    assert got["state"] == MEASURED
    assert got["value"] == 2.0
    assert got["retrospective_stop_derived"] is False

    missing = realized_r_multiple(
        direction_signed_pnl=10.0,
        entry_price=100.0,
        initial_invalidation_price=None,
    )
    assert missing["state"] == UNAVAILABLE_FIELD


def test_time_to_payoff_preserves_censoring_and_strict_forward_clock() -> None:
    hit = time_to_payoff_r(strictly_forward_r_path=[-0.2, 0.3, 1.0, 0.8], threshold_r=1.0)
    assert hit["state"] == MEASURED
    assert hit["hit"] is True
    assert hit["time_to_payoff_sessions"] == 3
    assert hit["censored"] is False

    miss = time_to_payoff_r(strictly_forward_r_path=[-0.2, 0.3, 0.9], threshold_r=1.0)
    assert miss["state"] == MEASURED
    assert miss["hit"] is False
    assert miss["censored"] is True
    assert miss["time_to_payoff_sessions"] is None
    assert miss["censor_at_session"] == 3

    broken = time_to_payoff_r(strictly_forward_r_path=[-0.2, None, 1.1], threshold_r=1.0)
    assert broken["state"] == UNAVAILABLE_FIELD


def test_eventual_move_consumed_is_diagnostic_only() -> None:
    got = eventual_move_consumed_fraction(
        favorable_move_at_first_surface=0.06,
        future_mfe=0.10,
    )
    assert got["state"] == DESCRIPTIVE_ONLY
    assert got["value"] == 0.6
    assert got["confirmatory"] is False
    assert got["authority"] == "diagnostic_only_ex_post_denominator"
