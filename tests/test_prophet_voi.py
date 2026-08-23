from __future__ import annotations

import math

import pandas as pd

from engine.prophet_voi import (
    DESCRIPTIVE_ONLY,
    MEASURED,
    NOT_APPLICABLE,
    PROTECTED_OUTCOME,
    UNAVAILABLE_FIELD,
    UNESTIMABLE,
    classify_flagship_lead_gate,
    concentration_effective_count,
    expected_shortfall,
    ndcg_at_k,
    precision_recall_at_k,
    summarize_us_board_frame,
    summarize_w3_status,
)


def test_w3_status_is_protected_before_owner_floor_and_opens_no_outcome_file() -> None:
    status = {
        "schema": "us.prophet_w3_status/v1",
        "authority": "measurement only / none",
        "comparison_surface": "forbidden",
        "first_lawful_comparison_read": "PENDING until 20 matured H=10 sessions",
        "honest_n_floor": 20,
        "matured_h10_sessions": 0,
        "paired_sessions_accrued": 5,
        "unmatured_sessions": 5,
        "n_degraded_or_unpaired": 6,
        "n_missing": 0,
        "structural": {"outcome_blind": True},
    }
    got = summarize_w3_status(status)
    assert got["state"] == PROTECTED_OUTCOME
    assert got["matured_h10_sessions"] == 0
    assert got["honest_n_floor"] == 20
    assert got["outcome_files_opened"] is False
    assert got["promotion_authority"] is False


def test_concentration_effective_count_catches_pseudon_from_four_dates() -> None:
    got = concentration_effective_count(
        ["2026-08-01"] * 125
        + ["2026-08-02"] * 125
        + ["2026-08-03"] * 125
        + ["2026-08-04"] * 125
    )
    assert got["n_rows"] == 500
    assert got["n_groups"] == 4
    assert got["n_eff"] == 4.0
    assert got["top1_share"] == 0.25
    assert got["dominated_gt_50pct"] is False


def test_concentration_effective_count_flags_dominant_group() -> None:
    got = concentration_effective_count(["A"] * 9 + ["B"])
    assert got["n_eff"] < 2
    assert got["top1_share"] == 0.9
    assert got["dominated_gt_50pct"] is True


def test_ndcg_is_one_for_ideal_order() -> None:
    got = ndcg_at_k([3, 2, 1, 0], 4)
    assert got["state"] == MEASURED
    assert got["value"] == 1.0


def test_ndcg_no_relevant_session_is_not_applicable_not_zero_or_one() -> None:
    got = ndcg_at_k([0, 0, 0], 3)
    assert got["state"] == NOT_APPLICABLE
    assert got["value"] is None
    assert got["reason"] == "idcg_zero_no_relevant_items"


def test_ndcg_missing_relevance_is_loud() -> None:
    got = ndcg_at_k([3, None, 1], 3)
    assert got["state"] == UNAVAILABLE_FIELD


def test_precision_requires_reference_denominator_for_recall() -> None:
    got = precision_recall_at_k([True, False, True], 5)
    assert got["state"] == MEASURED
    assert got["precision_presented"] == round(2 / 3, 6)
    assert got["fill_at_k"] == 0.6
    assert got["recall_state"] == UNAVAILABLE_FIELD

    with_ref = precision_recall_at_k([True, False, True], 3, reference_positive_count=4)
    assert with_ref["recall_state"] == MEASURED
    assert with_ref["recall"] == 0.5


def test_flagship_lead_gate_zero_margin_pass_fail_mixed() -> None:
    passed = classify_flagship_lead_gate(
        delta_lead_ci=(0.0, 2.0),
        delta_actionable_ci=(0.0, 0.05),
        delta_unusable_ci=(-0.04, 0.0),
    )
    assert passed["classification"] == "LEAD_PASS"

    failed = classify_flagship_lead_gate(
        delta_lead_ci=(-3.0, -1.0),
        delta_actionable_ci=(-0.01, 0.02),
        delta_unusable_ci=(-0.02, 0.01),
    )
    assert failed["classification"] == "LEAD_FAIL"

    mixed = classify_flagship_lead_gate(
        delta_lead_ci=(-1.0, 1.0),
        delta_actionable_ci=(-0.01, 0.02),
        delta_unusable_ci=(-0.02, 0.01),
    )
    assert mixed["classification"] == "LEAD_MIXED"


def test_expected_shortfall_requires_ten_tail_observations() -> None:
    got = expected_shortfall(range(50))
    assert got["state"] == UNESTIMABLE
    assert got["tail_n"] == 5

    enough = expected_shortfall(range(100))
    assert enough["state"] == MEASURED
    assert enough["tail_n"] == 10
    assert math.isclose(enough["value"], 4.5)


def _board_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "as_of": "2026-07-01", "ticker": "AAA", "horizon": 10, "lane": "buy",
                "position": 0, "excess_spy": 0.04, "entry_status": "buy_now",
                "entry_status_reason": None, "fwd_mfe_10": 0.08,
                "mae_close_excess_spy": -0.01, "price_basis": "adjusted", "rank_by": "alpha",
            },
            {
                "as_of": "2026-07-01", "ticker": "BBB", "horizon": 10, "lane": "buy",
                "position": 1, "excess_spy": -0.02, "entry_status": None,
                "entry_status_reason": "short_history", "fwd_mfe_10": 0.01,
                "mae_close_excess_spy": -0.05, "price_basis": "adjusted", "rank_by": "alpha",
            },
            {
                "as_of": "2026-07-02", "ticker": "AAA", "horizon": 10, "lane": "buy",
                "position": 1, "excess_spy": -0.01, "entry_status": "watch",
                "entry_status_reason": None, "fwd_mfe_10": 0.02,
                "mae_close_excess_spy": -0.04, "price_basis": "adjusted", "rank_by": "alpha",
            },
            {
                "as_of": "2026-07-02", "ticker": "BBB", "horizon": 10, "lane": "buy",
                "position": 0, "excess_spy": 0.03, "entry_status": "partial",
                "entry_status_reason": None, "fwd_mfe_10": 0.07,
                "mae_close_excess_spy": -0.02, "price_basis": "adjusted", "rank_by": "alpha",
            },
            {
                "as_of": "2026-07-03", "ticker": "AAA", "horizon": 10, "lane": "buy",
                "position": 0, "excess_spy": 0.01, "entry_status": None,
                "entry_status_reason": "unstamped_at_publish", "fwd_mfe_10": 0.03,
                "mae_close_excess_spy": -0.03, "price_basis": "adjusted", "rank_by": "alpha",
            },
            {
                "as_of": "2026-07-03", "ticker": "BBB", "horizon": 10, "lane": "buy",
                "position": 1, "excess_spy": 0.02, "entry_status": "buy_now",
                "entry_status_reason": None, "fwd_mfe_10": 0.05,
                "mae_close_excess_spy": -0.01, "price_basis": "adjusted", "rank_by": "alpha",
            },
        ]
    )


def test_board_summary_keeps_first_surface_and_issuer_fields_unavailable() -> None:
    got = summarize_us_board_frame(_board_fixture(), horizon=10, lane="buy")
    assert got["state"] == DESCRIPTIVE_ONLY
    assert got["promotion_authority"] is False
    assert got["n_matured_excess_spy"] == 6
    assert got["decision_dates"]["n_eff"] == 3.0
    assert got["ticker_proxy_concentration"]["n_eff"] == 2.0
    assert got["economic_issuer_concentration"]["state"] == UNAVAILABLE_FIELD
    assert got["first_eligible_surface"]["state"] == UNAVAILABLE_FIELD
    assert got["actionable_at_first_surface"]["state"] == UNAVAILABLE_FIELD
    assert got["lead_vs_champion"]["state"] == UNAVAILABLE_FIELD


def test_board_actionability_coverage_keeps_missing_rows_in_denominator() -> None:
    got = summarize_us_board_frame(_board_fixture(), horizon=10, lane="buy")
    coverage = got["entry_status_coverage"]
    assert coverage["applicable_rows"] == 6
    assert coverage["covered_rows"] == 4
    assert coverage["coverage"] == round(4 / 6, 6)
    assert coverage["broad_claim_coverage_eligible"] is False
    assert coverage["null_reason_counts"] == {"short_history": 1, "unstamped_at_publish": 1}


def test_board_path_uses_native_basis_and_refuses_r_and_payoff_time() -> None:
    got = summarize_us_board_frame(_board_fixture(), horizon=10, lane="buy")
    path = got["path"]
    assert path["mfe"]["state"] == DESCRIPTIVE_ONLY
    assert path["mae_close_excess_spy"]["state"] == DESCRIPTIVE_ONLY
    assert path["r_multiple"]["state"] == UNAVAILABLE_FIELD
    assert path["time_to_payoff"]["state"] == UNAVAILABLE_FIELD
    assert path["tail_loss_es10_excess_spy"]["state"] == UNESTIMABLE


def test_board_precision_uses_published_position_without_backfill() -> None:
    frame = _board_fixture()
    # Remove the published #1 outcome on one day.  The #2 row must not be promoted into P@1.
    frame.loc[(frame["as_of"] == "2026-07-02") & (frame["position"] == 0), "excess_spy"] = None
    got = summarize_us_board_frame(frame, horizon=10, lane="buy")
    p1 = got["ranking"]["precision_at_k"]["1"]
    assert p1["basis"] == "published_rank_position_lt_k_no_survivor_backfill"
    assert p1["published_capacity_rows"] == 3
    assert p1["graded_topk_rows"] == 2
    assert p1["fill_at_k"] == round(2 / 3, 6)
