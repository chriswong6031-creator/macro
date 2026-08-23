"""Adversarial tests for engine/prophet_lab/timeparse.py (day-2 temporal
correctness amendment, 2026-08-19).

These pin the ONE canonical instant-parsing/comparison helper the honesty
path (engine/prophet_lab/observation.py + sources.py) now uses instead of
raw lexicographic string compares. See timeparse.py's module docstring for
the measured failure mode this replaces:
``"2026-08-19T09:00:00-04:00"`` (13:00 UTC) sorts lexicographically BEFORE
``"2026-08-19T10:00:00Z"`` (10:00 UTC) even though it names the LATER
instant.
"""
from __future__ import annotations

from datetime import datetime, timezone

from engine.prophet_lab.timeparse import earliest_instant_string, parse_instant


# ---------------------------------------------------------------------------
# parse_instant — normalization and offset-form coverage
# ---------------------------------------------------------------------------
def test_parse_instant_normalizes_z_suffix() -> None:
    parsed = parse_instant("2026-08-19T10:00:00Z")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_instant_normalizes_lowercase_z_suffix() -> None:
    parsed = parse_instant("2026-08-19T10:00:00z")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_instant_accepts_explicit_positive_offset() -> None:
    # 2026-08-19T18:00:00+08:00 -> 10:00:00 UTC
    parsed = parse_instant("2026-08-19T18:00:00+08:00")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_instant_accepts_explicit_negative_offset() -> None:
    # 2026-08-19T06:00:00-04:00 -> 10:00:00 UTC
    parsed = parse_instant("2026-08-19T06:00:00-04:00")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_instant_accepts_explicit_utc_offset_form() -> None:
    parsed = parse_instant("2026-08-19T10:00:00+00:00")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# EQUAL INSTANTS, DIFFERENT OFFSET NOTATION — must compare/classify identically
# ---------------------------------------------------------------------------
def test_parse_instant_equal_instant_different_offset_forms_compare_equal() -> None:
    z_form = parse_instant("2026-08-19T10:00:00Z")
    offset_form = parse_instant("2026-08-19T06:00:00-04:00")
    assert z_form is not None and offset_form is not None
    assert z_form == offset_form


def test_parse_instant_all_four_offset_forms_of_the_same_instant_are_equal() -> None:
    # The SAME instant (10:00:00 UTC) named four different ways.
    forms = [
        "2026-08-19T10:00:00Z",
        "2026-08-19T10:00:00+00:00",
        "2026-08-19T06:00:00-04:00",
        "2026-08-19T18:00:00+08:00",
    ]
    parsed = [parse_instant(f) for f in forms]
    assert all(p is not None for p in parsed)
    assert len(set(parsed)) == 1, "all four forms must parse to the SAME instant"


# ---------------------------------------------------------------------------
# fail-closed: naive and unparseable input
# ---------------------------------------------------------------------------
def test_parse_instant_rejects_naive_timestamp() -> None:
    # No UTC offset at all -> reject, never guess (see timeparse.py DEFEND note).
    assert parse_instant("2026-08-19T10:00:00") is None


def test_parse_instant_rejects_bare_date() -> None:
    assert parse_instant("2026-08-19") is None


def test_parse_instant_rejects_garbage_string() -> None:
    assert parse_instant("not-a-timestamp") is None


def test_parse_instant_rejects_empty_and_none() -> None:
    assert parse_instant("") is None
    assert parse_instant(None) is None
    assert parse_instant("   ") is None


# ---------------------------------------------------------------------------
# before/after across offset forms, on BOTH sides of a reference instant
# ---------------------------------------------------------------------------
def test_parse_instant_before_across_offset_forms() -> None:
    reference = parse_instant("2026-08-19T10:00:00Z")  # 10:00 UTC
    before_forms = [
        "2026-08-19T09:59:59Z",           # 09:59:59 UTC
        "2026-08-19T09:59:59+00:00",      # 09:59:59 UTC
        "2026-08-19T05:59:59-04:00",      # 09:59:59 UTC
        "2026-08-19T17:59:59+08:00",      # 09:59:59 UTC
    ]
    for form in before_forms:
        parsed = parse_instant(form)
        assert parsed is not None
        assert parsed < reference, f"{form} must parse before the reference instant"


def test_parse_instant_after_across_offset_forms() -> None:
    reference = parse_instant("2026-08-19T10:00:00Z")  # 10:00 UTC
    after_forms = [
        "2026-08-19T10:00:01Z",           # 10:00:01 UTC
        "2026-08-19T10:00:01+00:00",      # 10:00:01 UTC
        "2026-08-19T06:00:01-04:00",      # 10:00:01 UTC
        "2026-08-19T18:00:01+08:00",      # 10:00:01 UTC
    ]
    for form in after_forms:
        parsed = parse_instant(form)
        assert parsed is not None
        assert parsed > reference, f"{form} must parse after the reference instant"


# ---------------------------------------------------------------------------
# earliest_instant_string
# ---------------------------------------------------------------------------
def test_earliest_instant_string_picks_the_correct_earliest_across_offset_forms() -> None:
    # "2026-08-19T09:00:00-04:00" is 13:00 UTC -- LATER than the other two,
    # despite sorting FIRST lexicographically ('09' < '10' < '18').
    candidates = [
        "2026-08-19T09:00:00-04:00",  # 13:00 UTC
        "2026-08-19T10:00:00Z",       # 10:00 UTC -- the true earliest
        "2026-08-19T18:00:00+08:00",  # 10:00 UTC (ties the Z form at 10:00 UTC)
    ]
    assert earliest_instant_string(candidates) == "2026-08-19T10:00:00Z"


def test_earliest_instant_string_skips_unparseable_and_naive_entries() -> None:
    candidates = [
        "not-a-timestamp",
        "2026-08-19T10:00:00",       # naive -> skipped
        "2026-08-19T09:00:00-04:00",  # 13:00 UTC -- the only valid entry
    ]
    assert earliest_instant_string(candidates) == "2026-08-19T09:00:00-04:00"


def test_earliest_instant_string_all_unparseable_returns_none() -> None:
    assert earliest_instant_string(["garbage", "", None, "2026-08-19"]) is None


def test_earliest_instant_string_empty_input_returns_none() -> None:
    assert earliest_instant_string([]) is None


# ---------------------------------------------------------------------------
# THE REGRESSION CASE — proves the OLD lexicographic bug is gone
# ---------------------------------------------------------------------------
def test_regression_lexicographic_compare_would_have_picked_the_wrong_earliest() -> None:
    """The exact pairing named in the day-2 mandate.

    ``"2026-08-19T10:00:00Z"`` (10:00 UTC) and ``"2026-08-19T09:00:00-04:00"``
    (13:00 UTC) — the second string is LEXICOGRAPHICALLY SMALLER ('09' < '10')
    but names the LATER instant. A raw ``min()``/``<`` over the strings would
    have picked the -04:00 form as "earliest", which is backwards.
    """
    a = "2026-08-19T10:00:00Z"           # 10:00 UTC -- the TRUE earlier instant
    b = "2026-08-19T09:00:00-04:00"      # 13:00 UTC -- actually LATER
    assert b < a, (
        "sanity check: 'b' sorts BEFORE 'a' lexicographically ('09' < '10') "
        "even though 'b' names the later instant -- this is the exact bug"
    )
    assert parse_instant(a) < parse_instant(b), "the TRUE earlier instant is `a`, not `b`"
    assert earliest_instant_string([a, b]) == a, (
        "a raw min()/`<` over the strings would have returned `b` here -- backwards"
    )


# ---------------------------------------------------------------------------
# MAS-123 / Cell G — measurement/refusal laws under the same canonical CI job
# ---------------------------------------------------------------------------
import json

import pandas as pd
import pytest

from engine.prophet_voi import (
    DESCRIPTIVE_ONLY,
    HOLD_INTEGRITY,
    MEASURED,
    PROTECTED_OUTCOME,
    UNAVAILABLE_FIELD,
    classify_flagship_lead_gate,
    concentration_effective_count,
    ndcg_at_k,
    precision_recall_at_k,
    summarize_us_board_frame,
    summarize_w3_status,
)
from engine.prophet_voi_eawc import (
    early_actionable_capture_recall,
    paired_surface_lead_sessions,
    realized_r_multiple,
    time_to_payoff_r,
    unusable_or_unknown_at_first_surface_rate,
)
from scripts import prophet_flagship_voi_report as voi_report


def _cell_g_w3(*, matured: int = 0, blind: bool = True, surface: str = "forbidden") -> dict:
    return {
        "schema": "us.prophet_w3_status/v1",
        "authority": "measurement only / none",
        "comparison_surface": surface,
        "first_lawful_comparison_read": "PENDING until 20 matured H=10 sessions",
        "honest_n_floor": 20,
        "matured_h10_sessions": matured,
        "paired_sessions_accrued": 5,
        "unmatured_sessions": 5,
        "n_degraded_or_unpaired": 6,
        "n_missing": 0,
        "structural": {"outcome_blind": blind},
    }


def test_cell_g_w3_status_stays_protected_before_owner_floor() -> None:
    got = summarize_w3_status(_cell_g_w3())
    assert got["state"] == PROTECTED_OUTCOME
    assert got["outcome_files_opened"] is False
    assert got["promotion_authority"] is False


def test_cell_g_w3_status_fails_closed_on_malformed_gate_metadata() -> None:
    status = _cell_g_w3()
    del status["honest_n_floor"]
    got = summarize_w3_status(status)
    assert got["state"] == HOLD_INTEGRITY
    assert got["outcome_files_opened"] is False


def test_cell_g_effective_n_rejects_row_count_pseudon() -> None:
    got = concentration_effective_count(
        ["d1"] * 125 + ["d2"] * 125 + ["d3"] * 125 + ["d4"] * 125
    )
    assert got["n_rows"] == 500
    assert got["n_eff"] == 4.0


def test_cell_g_ndcg_ideal_uses_full_fixed_population() -> None:
    got = ndcg_at_k([3, 0, 2], 2)
    assert got["state"] == MEASURED
    assert got["n_candidates"] == 3
    assert 0 < got["value"] < 1


def test_cell_g_recall_requires_independent_reference_denominator() -> None:
    got = precision_recall_at_k([True, False, True], 3)
    assert got["recall_state"] == UNAVAILABLE_FIELD
    with_ref = precision_recall_at_k([True, False, True], 3, reference_positive_count=4)
    assert with_ref["recall"] == 0.5


def test_cell_g_lead_gate_is_zero_degradation_margin() -> None:
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


def _cell_g_board_fixture() -> pd.DataFrame:
    return pd.DataFrame([
        {"as_of": "2026-07-01", "ticker": "AAA", "horizon": 10, "lane": "buy", "position": 0,
         "excess_spy": 0.04, "entry_status": "buy_now", "entry_status_reason": None,
         "fwd_mfe_10": 0.08, "mae_close_excess_spy": -0.01, "price_basis": "adjusted", "rank_by": "alpha"},
        {"as_of": "2026-07-01", "ticker": "BBB", "horizon": 10, "lane": "buy", "position": 1,
         "excess_spy": -0.02, "entry_status": None, "entry_status_reason": "short_history",
         "fwd_mfe_10": 0.01, "mae_close_excess_spy": -0.05, "price_basis": "adjusted", "rank_by": "alpha"},
        {"as_of": "2026-07-02", "ticker": "AAA", "horizon": 10, "lane": "buy", "position": 1,
         "excess_spy": -0.01, "entry_status": "watch", "entry_status_reason": None,
         "fwd_mfe_10": 0.02, "mae_close_excess_spy": -0.04, "price_basis": "adjusted", "rank_by": "alpha"},
        {"as_of": "2026-07-02", "ticker": "BBB", "horizon": 10, "lane": "buy", "position": 0,
         "excess_spy": 0.03, "entry_status": "partial", "entry_status_reason": None,
         "fwd_mfe_10": 0.07, "mae_close_excess_spy": -0.02, "price_basis": "adjusted", "rank_by": "alpha"},
    ])


def test_cell_g_board_refuses_first_surface_and_keeps_missing_coverage_denominator() -> None:
    got = summarize_us_board_frame(_cell_g_board_fixture(), horizon=10, lane="buy")
    assert got["state"] == DESCRIPTIVE_ONLY
    assert got["promotion_authority"] is False
    assert got["first_eligible_surface"]["state"] == UNAVAILABLE_FIELD
    assert got["lead_vs_champion"]["state"] == UNAVAILABLE_FIELD
    coverage = got["entry_status_coverage"]
    assert coverage["applicable_rows"] == 4
    assert coverage["covered_rows"] == 3
    assert coverage["coverage"] == 0.75


def test_cell_g_paired_lead_never_imputes_one_sided_capture() -> None:
    got = paired_surface_lead_sessions(
        challenger_first_session=[1, 5, None, 4],
        champion_first_session=[3, None, 7, 4],
    )
    assert got["paired_subjects"] == 2
    assert got["challenger_only"] == 1
    assert got["champion_only"] == 1
    assert got["one_sided_lead_imputed"] is False
    assert got["mean_lead_sessions"] == 1.0


def test_cell_g_actionable_capture_keeps_misses_and_blocked_in_positive_denominator() -> None:
    got = early_actionable_capture_recall(
        positive_label=[True, True, True, False],
        surfaced=[True, False, True, True],
        actionable_at_first_surface=[True, None, None, True],
    )
    assert got["positive_reference_subjects"] == 3
    assert got["captured_actionable"] == 1
    assert got["value"] == round(1 / 3, 6)
    assert got["missed_surface"] == 1
    assert got["missing_or_blocked_actionability"] == 1


def test_cell_g_unknown_actionability_is_conservative_guardrail() -> None:
    got = unusable_or_unknown_at_first_surface_rate(
        applicable_first_surface=[True, True, True],
        chased_or_closed=[False, None, True],
    )
    assert got["value"] == round(2 / 3, 6)
    assert got["unknown_counts_as_unusable_guardrail"] is True


def test_cell_g_r_requires_frozen_initial_risk_and_payoff_preserves_censoring() -> None:
    r = realized_r_multiple(direction_signed_pnl=6.0, entry_price=100.0, initial_invalidation_price=97.0)
    assert r["state"] == MEASURED and r["value"] == 2.0
    assert r["retrospective_stop_derived"] is False
    missing = realized_r_multiple(direction_signed_pnl=6.0, entry_price=100.0, initial_invalidation_price=None)
    assert missing["state"] == UNAVAILABLE_FIELD
    censored = time_to_payoff_r(strictly_forward_r_path=[0.1, 0.3, 0.7], threshold_r=1.0)
    assert censored["hit"] is False and censored["censored"] is True
    assert censored["censor_at_session"] == 3


def test_cell_g_report_cli_has_no_arbitrary_source_path_override() -> None:
    with pytest.raises(SystemExit):
        voi_report._args(["--w3-status", "some/outcome.json"])


def test_cell_g_qledger_clock_inventory_is_metadata_only(tmp_path, monkeypatch) -> None:
    clock = {
        "claim_family": "demand_chain",
        "declared_horizon_d": 126,
        "first_prospective_registration_utc": "2026-08-19T08:10:37.995754+00:00",
        "git_sha": "34899ec5235884e183be86088ab01f81e34a693f",
        "horizon_unit": "trading_days",
    }
    (tmp_path / "demand_chain.json").write_text(json.dumps(clock), encoding="utf-8")
    monkeypatch.setattr(voi_report, "DEFAULT_QLEDGER_CLOCK_DIR", tmp_path)
    got = voi_report._qledger_clock_inventory()
    assert got["state"] == MEASURED
    assert got["registration_count"] == 1
    assert got["outcome_files_opened"] is False
    assert got["promotion_authority"] is False


def test_cell_g_real_committed_metadata_smoke_is_zero_authority(capsys) -> None:
    rc = voi_report.main(["--no-board"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["promotion_authority"] is False
    assert payload["writes_evaluation_store"] is False
    assert payload["w3"]["outcome_files_opened"] is False
    assert payload["promotion"]["authorized"] is False


def test_cell_g_recall_refuses_impossible_reference_denominator() -> None:
    got = precision_recall_at_k([True, True, False], 3, reference_positive_count=1)
    assert got["state"] == HOLD_INTEGRITY
    assert got["recall_state"] == HOLD_INTEGRITY
    assert got["recall"] is None
    assert got["recall_reason"] == "topk_positives_exceed_reference_population_positives"


def test_cell_g_w3_status_rejects_malformed_count_without_crashing() -> None:
    status = _cell_g_w3()
    status["paired_sessions_accrued"] = "five"
    got = summarize_w3_status(status)
    assert got["state"] == HOLD_INTEGRITY
    assert got["outcome_files_opened"] is False
    assert got["reason"] == "missing_or_invalid_w3_count:paired_sessions_accrued"


def test_cell_g_eawc_rejects_truthy_string_positive_label() -> None:
    got = early_actionable_capture_recall(
        positive_label=[True, "False"],
        surfaced=[True, True],
        actionable_at_first_surface=[True, True],
    )
    assert got["state"] == HOLD_INTEGRITY
    assert got["invalid_positive_labels"] == 1


def test_cell_g_eawc_rejects_malformed_actionability_state() -> None:
    got = early_actionable_capture_recall(
        positive_label=[True, True],
        surfaced=[True, True],
        actionable_at_first_surface=[True, "blocked"],
    )
    assert got["state"] == HOLD_INTEGRITY
    assert got["invalid_actionability_states"] == 1


def test_cell_g_report_sources_are_repo_root_pinned_outside_working_directory(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = voi_report.main(["--no-board"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["w3"]["outcome_files_opened"] is False
    assert payload["w3"]["state"] == PROTECTED_OUTCOME
    assert payload["qledger_evidence_clocks"]["registration_count"] >= 1
