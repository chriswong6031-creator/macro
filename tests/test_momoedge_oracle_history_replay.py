from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from scripts.research.momoedge_oracle_history_replay import (
    AGGREGATE_SCHEMA,
    CASE_SCHEMA,
    FEATURE_RECEIPT_SCHEMA,
    INPUT_SCHEMA,
    THETA_REMOTE_INVENTORY_SCHEMA,
    ReplayInputError,
    audit_repo_data,
    build_aggregate_receipt,
    build_feature_receipt_requirements,
    build_replay_cases,
    build_theta_data_plane_summary,
    build_theta_selective_restore_plan,
    capital_constrained_proxy,
    enforce_private_output_boundary,
    load_and_validate_history,
    load_theta_remote_inventory,
    probe_theta_remote_inventory,
    validate_document,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
TRACKED_RECEIPT = ROOT / "research" / "momoedge" / "history_replay_wave0_receipt.json"
COMPLETION_PREREG = (
    ROOT / "research" / "momoedge" / "completion_benchmark_prereg_v1.json"
)
COMPLETION_PREREG_SCHEMA = (
    ROOT
    / "contracts"
    / "research"
    / "momoedge_oracle_completion_benchmark_prereg.v1.schema.json"
)


def _record(
    source_index: int,
    ticker: str,
    issued_date: str,
    closed_date: str | None,
    *,
    instrument: str,
    direction: str,
    underlying_return: float,
    table_status: str = "CLOSED EARLY",
    detail_status: str = "CLOSED EARLY",
) -> dict:
    option = None
    if instrument == "option":
        option = {
            "contract": f"{ticker} 100C",
            "expiration": "Jun 26, 2026",
            "premium_paid": 1.0,
            "premium_exit": 2.0 if underlying_return >= 0 else 0.5,
            "return_pct": 100.0 if underlying_return >= 0 else -50.0,
            "leverage_x": 4.0,
            "contracts": None,
            "dollar_pnl": None,
        }
    return {
        "source_index": source_index,
        "display_ticker": ticker,
        "ticker": ticker,
        "direction": direction,
        "instrument": instrument,
        "issued_date": issued_date,
        "closed_date": closed_date,
        "days_held": 2 if closed_date else None,
        "confidence_pct": 80.0,
        "setup": "Synthetic setup",
        "table_status": table_status,
        "detail_status": detail_status,
        "underlying": {
            "entry": 100.0,
            "exit": 100.0 * (1 + underlying_return / 100),
            "return_pct": underlying_return,
        },
        "option": option,
        "table_row": f"private raw row {source_index} {ticker}",
    }


@pytest.fixture
def history() -> dict:
    records = [
        _record(
            1,
            "SYNPRIVATE1",
            "01-02-2024",
            "01-05-2024",
            instrument="underlying",
            direction="BULL",
            underlying_return=10.0,
        ),
        _record(
            2,
            "SYNPRIVATE2",
            "09-24-2025",
            "09-26-2025",
            instrument="option",
            direction="BEAR",
            underlying_return=-5.0,
            table_status="INVALIDATED",
            detail_status="EXPIRED",
        ),
        _record(
            3,
            "SYNPRIVATE3",
            "05-06-2026",
            "05-06-2026",
            instrument="underlying",
            direction="BULL",
            underlying_return=0.0,
        ),
        _record(
            4,
            "SYNPRIVATE4",
            "05-07-2026",
            "05-08-2026",
            instrument="option",
            direction="BULL",
            underlying_return=20.0,
        ),
    ]
    return {
        "schema": "momoedge.oracle_history_authorized/v1",
        "captured_at": "2026-08-09T03:27:52.187Z",
        "source": {
            "product": "MomoEdge Oracle",
            "url": "https://momoedge.ai/terminal.html",
            "surface": "Performance",
            "method": "Authorized synthetic test fixture",
            "export_button_result": "Synthetic fixture only",
            "scope": "Test",
        },
        "authorization": {
            "basis": "Authorized joint research fixture",
            "permission_receipt_image_sha256": "a" * 64,
            "permission_receipt_image_bytes": 1,
            "excerpt": "private authorization excerpt",
            "handling": "private",
        },
        "displayed_summary": {
            "trades": 4,
            "wins_displayed": 2,
            "win_rate_pct": 50.0,
            "total_alpha_pct": 25.0,
            "total_alpha_definition": "SUM OF PER-TRADE RETURNS",
            "avg_gain_pct": 15.0,
            "avg_loss_pct": -5.0,
            "avg_days": 2.0,
            "max_drawdown_pct": -5.0,
            "bull_win_rate_pct": 66.7,
            "bear_win_rate_pct": 0.0,
            "best_trade": "synthetic best",
            "worst_trade": "synthetic worst",
        },
        "limitations": ["Issue times are not exposed."],
        "records": records,
    }


def _write_history(path: Path, history: dict) -> Path:
    path.write_text(json.dumps(history), encoding="utf-8")
    return path


def test_replay_contracts_are_valid_draft_2020_12_schemas() -> None:
    for path in (
        INPUT_SCHEMA,
        CASE_SCHEMA,
        FEATURE_RECEIPT_SCHEMA,
        AGGREGATE_SCHEMA,
        THETA_REMOTE_INVENTORY_SCHEMA,
        COMPLETION_PREREG_SCHEMA,
    ):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_completion_benchmark_is_digest_frozen_and_separates_catch_up_from_surpass() -> None:
    prereg = json.loads(COMPLETION_PREREG.read_text(encoding="utf-8"))
    validate_document(prereg, COMPLETION_PREREG_SCHEMA)

    canonical = json.dumps(
        prereg["benchmark"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == prereg["registration"][
        "benchmark_digest_sha256"
    ]
    assert prereg["registration"]["effective_freeze_rule"] == (
        "later_of_registered_at_and_first_origin_main_commit_containing_exact_"
        "benchmark_digest"
    )

    benchmark = prereg["benchmark"]
    completion = benchmark["completion_rule"]
    catch_up_ids = [gate["gate_id"] for gate in benchmark["catch_up_gates"]]
    surpass_ids = [gate["gate_id"] for gate in benchmark["surpass_gates"]]
    assert catch_up_ids == [
        "CU_FEATURE_PARITY",
        "CU_CADENCE_TRUTH",
        "CU_LIFECYCLE_AND_RETURN_READINESS",
        "CU_BILINGUAL_MOBILE",
        "CU_AUTHORITY_HONESTY",
    ]
    assert surpass_ids == [
        "SP_POINT_IN_TIME_PROVENANCE",
        "SP_SPARSE_ABSTENTION",
        "SP_PROSPECTIVE_OPTION_SUPERIORITY",
    ]
    assert completion["catch_up_requires"] == catch_up_ids
    assert completion["surpass_requires"] == surpass_ids
    assert completion["surpass_requires_catch_up"] is True
    assert completion["goal_complete_state"] == "surpass"
    assert completion["partial_substitution_allowed"] is False
    assert completion["current_state_at_registration"] == "not_complete"
    assert all(gate["stage"] == "catch_up" for gate in benchmark["catch_up_gates"])
    assert all(gate["stage"] == "surpass" for gate in benchmark["surpass_gates"])

    criterion_ids = [
        criterion["criterion_id"]
        for gate in benchmark["catch_up_gates"] + benchmark["surpass_gates"]
        for criterion in gate["criteria"]
    ]
    assert len(criterion_ids) == len(set(criterion_ids))


def test_completion_benchmark_forbids_retrospective_return_evidence() -> None:
    prereg = json.loads(COMPLETION_PREREG.read_text(encoding="utf-8"))
    benchmark = prereg["benchmark"]
    protocol = benchmark["prospective_return_protocol"]
    fence = protocol["phase_fence"]
    assert fence == {
        "retrospective_phase": "retrospective_discovery",
        "prospective_phase": "prospective_after_benchmark_freeze",
        "prospective_clock_field": "decision_available_at",
        "prospective_digest_field": "benchmark_digest_sha256",
        "retrospective_may_define_features": True,
        "retrospective_may_satisfy_return_gate": False,
        "missing_or_mismatched_phase_action": "exclude_and_count_as_incomplete",
    }
    assert benchmark["baselines"]["momoedge"]["use_policy"] == {
        "feature_definition": True,
        "historical_context": True,
        "prospective_return_gate": False,
    }
    ours = benchmark["baselines"]["mastermindx"]
    assert ours["claim_state"] == "not_complete_no_prospective_return_cohort"
    assert all(row["prospective_row_count"] == 0 for row in ours["ledgers"])
    assert all(
        observation["claim_use"]
        == "registration_baseline_only_not_completion_evidence"
        for observation in ours["live_observations"]
    )

    historical = json.loads(TRACKED_RECEIPT.read_text(encoding="utf-8"))
    source = benchmark["baselines"]["momoedge"]["source_receipt"]
    assert hashlib.sha256(TRACKED_RECEIPT.read_bytes()).hexdigest() == source["sha256"]
    metrics = benchmark["baselines"]["momoedge"]["metrics"]
    additive = historical["displayed_additive_metrics"]
    assert metrics["history_records"] == historical["input"]["record_count"] == 157
    assert metrics["headline_wins"] == additive["headline_wins"] == 103
    assert metrics["headline_win_rate_pct"] == additive["headline_win_rate_pct"] == 65.6
    assert metrics["headline_total_alpha_pct"] == additive["headline_total_alpha_pct"]
    assert metrics["option_return_observed_records"] == additive[
        "option_return_observed_records"
    ]
    assert metrics["reconstruction_is_track_record"] is False


def test_completion_benchmark_pins_same_basis_option_return_and_sparse_selector() -> None:
    benchmark = json.loads(COMPLETION_PREREG.read_text(encoding="utf-8"))["benchmark"]
    protocol = benchmark["prospective_return_protocol"]
    quotes = protocol["quote_basis"]
    cohort = protocol["cohort"]
    stats = protocol["statistics"]

    assert quotes["nbbo_required"] is True
    assert quotes["entry_side"] == "first_valid_ask_at_or_after_trigger"
    assert quotes["exit_side"] == (
        "first_valid_bid_at_or_after_terminal_event_with_1555_et_expiry_liquidation"
    )
    assert quotes["max_quote_available_lag_sec"] == 600
    assert quotes["fee_per_contract_per_side_usd"] == 0.65
    assert quotes["mid_last_eod_substitution_allowed"] is False
    assert cohort["minimum_covered_sessions"] == 63
    assert cohort["minimum_closed_exact_option_outcomes_per_system"] == 60
    assert cohort["minimum_capture_coverage_ratio"] == 0.95
    assert cohort["maximum_authenticated_capture_gap_sec"] == 900
    assert stats["bootstrap_replicates"] == 10_000
    assert stats["random_seed"] == 20_260_811
    assert stats["primary_pass_rule"] == (
        "lower_confidence_bound_strictly_greater_than_zero"
    )
    assert stats["downside_noninferiority_margin_pct_points"] == 5.0
    assert stats["headline_win_rate_role"] == (
        "reported_context_only_not_a_pass_threshold"
    )

    sparse_gate = next(
        gate for gate in benchmark["surpass_gates"] if gate["gate_id"] == "SP_SPARSE_ABSTENTION"
    )
    sparse_text = " ".join(
        criterion["pass_condition"] for criterion in sparse_gate["criteria"]
    )
    assert "exactly one issued or abstained decision" in sparse_text
    assert "may issue zero plans" in sparse_text
    assert "never issue more than three new plans" in sparse_text
    assert "no minimum quota or forced fill" in sparse_text

    authority = benchmark["authority"]
    assert authority["tier"] == "research_only"
    for field in (
        "signal_origination",
        "prophet_promotion",
        "neural_web_promotion",
        "automatic_training",
        "brokerage",
        "completion_receipt_promotes_authority",
    ):
        assert authority[field] is False


def test_tracked_receipt_is_aggregate_only_and_has_no_signal_authority() -> None:
    text = TRACKED_RECEIPT.read_text(encoding="utf-8")
    receipt = json.loads(text)
    validate_document(receipt, AGGREGATE_SCHEMA)
    assert receipt["input"]["record_count"] == 157
    assert receipt["runtime_outputs"]["replay_case_count"] == 157
    assert receipt["runtime_outputs"]["feature_receipt_count"] == 157 * 3 * 5
    assert receipt["privacy"] == {
        "raw_records_included": False,
        "ticker_values_included": False,
        "authorization_payload_included": False,
        "authorization_image_included": False,
        "private_runtime_artifacts_committed": False,
    }
    assert receipt["authority"]["prophet"] == "none"
    assert receipt["authority"]["neural_web"] == "none"
    assert receipt["temporal_source_quality"] == {
        "raw_values_retained": True,
        "corrections_applied": 0,
        "clean_records": 137,
        "missing_close_date_records": 18,
        "issue_close_days_held_year_conflict_records": 2,
        "holding_interval_after_option_expiration_records": 1,
        "max_holding_interval_beyond_option_expiration_days": 28,
        "correction_overlay_required_records": 20,
        "overlap_replay_excluded_records": 20,
        "expiry_return_replay_excluded_option_records": 5,
    }
    theta = receipt["theta_data_plane"]
    assert theta["local_state"] == "unresolved"
    assert theta["r2_state"] == "available_candidate"
    assert theta["current_available_root_count"] == 53
    assert theta["current_available_objects"] == 168
    assert theta["candidate_issue_records"] == 100
    assert theta["object_content_downloaded"] is False
    gex = next(
        row for row in receipt["data_availability"] if row["family"] == "gex_vol_oi"
    )
    assert "thetadata_local_store_unresolved" in gex["blocker_codes"]
    assert "theta_r2_selective_restore_pending" in gex["blocker_codes"]
    assert "thetadata_store_unresolved" not in gex["blocker_codes"]
    assert "table_row" not in text
    assert "permission_receipt_image_sha256" not in text


def test_authorized_input_schema_and_semantics_fail_closed(tmp_path: Path, history: dict) -> None:
    source = _write_history(tmp_path / "history.json", history)
    loaded, fingerprint = load_and_validate_history(source)
    assert loaded["schema"] == "momoedge.oracle_history_authorized/v1"
    assert len(fingerprint) == 64

    extra = copy.deepcopy(history)
    extra["unapproved_extra"] = {"raw": True}
    with pytest.raises(ReplayInputError, match="additionalProperties"):
        load_and_validate_history(_write_history(tmp_path / "extra.json", extra))

    duplicate = copy.deepcopy(history)
    duplicate["records"][1]["source_index"] = duplicate["records"][0]["source_index"]
    with pytest.raises(ReplayInputError, match="not unique"):
        load_and_validate_history(_write_history(tmp_path / "duplicate.json", duplicate))


def test_date_only_cases_keep_cutoff_sensitivity_and_layer_separation(history: dict) -> None:
    cases = build_replay_cases(history, "b" * 64)
    assert [case["cohort"]["cohort_id"] for case in cases] == [
        "pre_option_format",
        "mixed_format_transition",
        "mixed_format_transition",
        "post_underlying_format",
    ]
    assert all(case["issue_time"]["exact_timestamp"] is None for case in cases)
    assert all(case["issue_time"]["state"] == "unknown_date_only" for case in cases)
    assert [
        cutoff["cutoff_id"] for cutoff in cases[0]["issue_time"]["cutoff_sensitivity"]
    ] == ["market_open", "mid_session", "market_close_boundary"]

    disagreement = cases[1]["decision_layers"]["management"]
    assert disagreement["table_status"] == "INVALIDATED"
    assert disagreement["detail_status"] == "EXPIRED"
    assert disagreement["status_disagreement"] is True
    assert "table_row" not in json.dumps(cases[1])
    assert cases[1]["decision_layers"]["contract_construction"]["state"] == "observed_retro_record"
    assert cases[0]["decision_layers"]["contract_construction"]["state"] == "not_applicable"
    for case in cases:
        validate_document(case, CASE_SCHEMA)


def test_feature_receipts_require_asof_clocks_and_never_claim_evidence(history: dict) -> None:
    cases = build_replay_cases(history, "b" * 64)
    receipts = build_feature_receipt_requirements(cases)
    assert len(receipts) == 4 * 3 * 5
    assert {receipt["family"] for receipt in receipts} == {
        "price_technical",
        "macro_regime",
        "options_flow_campaign",
        "gex_vol_oi",
        "news_alt_data",
    }
    for receipt in receipts:
        assert receipt["status"] == "required_unresolved"
        assert receipt["evidence"] == []
        assert receipt["point_in_time_contract"]["event_time_lte"] == receipt["candidate_as_of"]
        assert receipt["point_in_time_contract"]["available_at_lte"] == receipt["candidate_as_of"]
        assert receipt["point_in_time_contract"]["source_vintage_required"] is True
        assert (
            receipt["point_in_time_contract"][
                "unknown_issue_time_uses_prior_session_daily_state"
            ]
            is True
        )
        assert (
            receipt["point_in_time_contract"]["issue_day_eod_not_assumed_available"]
            is True
        )
        validate_document(receipt, FEATURE_RECEIPT_SCHEMA)


def test_additive_headline_is_separate_from_unidentified_portfolio_metrics(
    tmp_path: Path,
    history: dict,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    cases = build_replay_cases(history, "b" * 64)
    features = build_feature_receipt_requirements(cases)
    receipt = build_aggregate_receipt(
        history,
        "b" * 64,
        cases,
        features,
        audit_repo_data(repo, history["records"]),
        build_theta_data_plane_summary(repo, history["records"], None),
        generated_at="2026-08-09T04:00:00Z",
    )
    additive = receipt["displayed_additive_metrics"]
    assert additive["headline_total_alpha_pct"] == 25.0
    assert additive["reconstructed_visible_underlying_sum_pct"] == 25.0
    assert additive["reconstruction_is_track_record"] is False
    assert (
        receipt["capital_constrained_metrics"]["identification_state"]
        == "not_identifiable_from_source"
    )
    assert receipt["capital_constrained_metrics"]["proxy_metrics"] == []
    assert receipt["authority"] == {
        "tier": "research_only",
        "prophet": "none",
        "neural_web": "none",
        "signal_origination": False,
        "automatic_training": False,
    }
    validate_document(receipt, AGGREGATE_SCHEMA)


def test_temporal_anomalies_require_unapplied_overlay_and_are_replay_excluded(
    tmp_path: Path,
    history: dict,
) -> None:
    anomalous = copy.deepcopy(history)
    anomalous["records"][0] = _record(
        1,
        "SYNPRIVATE1",
        "01-02-2025",
        "01-05-2026",
        instrument="option",
        direction="BULL",
        underlying_return=10.0,
    )
    anomalous["records"][1]["days_held"] = 303
    anomalous["records"][2]["closed_date"] = None
    anomalous["records"][2]["days_held"] = None
    cases = build_replay_cases(anomalous, "b" * 64)
    year_case = next(case for case in cases if case["source_record_index"] == 1)
    quality = year_case["temporal_quality"]
    assert quality["raw_source_values"]["issued_date"] == "01-02-2025"
    assert quality["derived_diagnostics"]["issue_year_shift_candidate"] == "2026-01-02"
    assert quality["quality_flags"] == ["issue_close_days_held_year_conflict"]
    assert quality["correction_overlay"] == {
        "state": "required_unresolved",
        "applied": False,
        "raw_source_values_retained": True,
    }
    assert quality["replay_eligibility"]["overlap_allocation"] == (
        "excluded_temporal_quality"
    )
    expiry_case = next(case for case in cases if case["source_record_index"] == 2)
    expiry_quality = expiry_case["temporal_quality"]
    assert expiry_quality["derived_diagnostics"]["close_minus_option_expiration_days"] < 0
    assert (
        expiry_quality["derived_diagnostics"][
            "reported_holding_end_minus_option_expiration_days"
        ]
        == 28
    )
    assert expiry_quality["quality_flags"] == [
        "reported_holding_interval_after_option_expiration"
    ]
    missing_case = next(case for case in cases if case["source_record_index"] == 3)
    assert missing_case["temporal_quality"]["quality_flags"] == ["missing_close_date"]

    proxy = capital_constrained_proxy(
        cases,
        max_slots=4,
        return_basis="reported_instrument",
        same_day_policy="close_before_issue",
    )
    assert proxy["excluded_incomplete"] == 0
    assert proxy["excluded_temporal_quality"] == 3

    repo = tmp_path / "repo"
    repo.mkdir()
    features = build_feature_receipt_requirements(cases)
    receipt = build_aggregate_receipt(
        anomalous,
        "b" * 64,
        cases,
        features,
        audit_repo_data(repo, anomalous["records"]),
        build_theta_data_plane_summary(repo, anomalous["records"], None),
        generated_at="2026-08-09T04:00:00Z",
    )
    quality_counts = receipt["temporal_source_quality"]
    assert quality_counts["missing_close_date_records"] == 1
    assert quality_counts["issue_close_days_held_year_conflict_records"] == 1
    assert quality_counts["holding_interval_after_option_expiration_records"] == 1
    assert quality_counts["max_holding_interval_beyond_option_expiration_days"] == 28
    assert quality_counts["correction_overlay_required_records"] == 3
    assert "temporal_correction_overlays_unresolved" in receipt[
        "capital_constrained_metrics"
    ]["blocker_codes"]


class _MissingHead(Exception):
    response = {"Error": {"Code": "404"}}


class _HeadOnlyR2:
    def __init__(self, available: set[str]) -> None:
        self.available = available
        self.head_keys: list[str] = []

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == "fixture-private-bucket"
        self.head_keys.append(Key)
        if Key == "thetadata_eod/_manifest.json":
            return {"LastModified": "2026-08-08T04:00:00Z", "ContentLength": 100}
        if Key not in self.available:
            raise _MissingHead
        return {
            "LastModified": "2026-08-08T04:00:00Z",
            "ContentLength": 1000,
            "ETag": '"fixture-etag"',
        }


def test_theta_r2_inventory_is_targeted_aggregate_only_and_restore_plan_private(
    tmp_path: Path,
    history: dict,
) -> None:
    private_plan = build_theta_selective_restore_plan(history["records"])
    first_root = history["records"][0]["ticker"]
    first_year = 2024
    available = {
        f"thetadata_eod/{tier}/{first_root}/{first_year}.parquet"
        for tier in ("eod", "oi", "greeks")
    }
    client = _HeadOnlyR2(available)
    inventory, probed_plan = probe_theta_remote_inventory(
        history,
        "b" * 64,
        client=client,
        bucket="fixture-private-bucket",
        generated_at="2026-08-09T04:00:00Z",
    )
    assert len(private_plan) == 4 * 3
    assert len(probed_plan) == 4 * 3
    assert all(".OLD/" not in row["key"] for row in probed_plan)
    assert len(client.head_keys) == 1 + 4 * 3
    assert inventory["all_tiers_available_root_year_pairs"] == 1
    assert inventory["all_tiers_available_root_count"] == 1
    assert inventory["all_tiers_candidate_issue_records"] == 1
    assert inventory["total_available_objects"] == 3
    assert inventory["total_available_bytes"] == 3000
    assert inventory["objects_downloaded"] is False
    inventory_text = json.dumps(inventory)
    assert "SYNPRIVATE" not in inventory_text
    validate_document(inventory, THETA_REMOTE_INVENTORY_SCHEMA)

    inventory_path = tmp_path / "theta-inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    assert load_theta_remote_inventory(
        inventory_path,
        expected_input_sha256="b" * 64,
    ) == inventory
    with pytest.raises(ReplayInputError, match="does not match"):
        load_theta_remote_inventory(
            inventory_path,
            expected_input_sha256="c" * 64,
        )

    repo = tmp_path / "repo"
    repo.mkdir()
    audit = {
        row["family"]: row
        for row in audit_repo_data(
            repo,
            history["records"],
            theta_remote_inventory=inventory,
        )
    }
    gex = audit["gex_vol_oi"]
    assert "thetadata_local_store_unresolved" in gex["blocker_codes"]
    assert "theta_r2_selective_restore_pending" in gex["blocker_codes"]
    assert gex["supporting_counts"]["theta_r2_candidate_issue_records"] == 1
    data_plane = build_theta_data_plane_summary(repo, history["records"], inventory)
    assert data_plane["local_state"] == "unresolved"
    assert data_plane["r2_state"] == "available_candidate"
    assert data_plane["issue_day_eod_policy"] == (
        "prior_session_only_when_issue_time_unknown"
    )


def test_fixed_slot_proxy_exposes_same_day_order_sensitivity(history: dict) -> None:
    cases = build_replay_cases(history, "b" * 64)[:2]
    cases[0]["issue_date"] = "2026-01-02"
    cases[0]["decision_layers"]["management"]["closed_date"] = "2026-01-05"
    cases[0]["decision_layers"]["management"]["underlying_return_pct"] = 10.0
    cases[1]["issue_date"] = "2026-01-05"
    cases[1]["decision_layers"]["management"]["closed_date"] = "2026-01-06"
    cases[1]["decision_layers"]["management"]["underlying_return_pct"] = 20.0

    close_first = capital_constrained_proxy(
        cases,
        max_slots=1,
        return_basis="underlying",
        same_day_policy="close_before_issue",
    )
    issue_first = capital_constrained_proxy(
        cases,
        max_slots=1,
        return_basis="underlying",
        same_day_policy="issue_before_close",
    )
    assert close_first["accepted_records"] == 2
    assert close_first["fixed_initial_capital_return_pct"] == 30.0
    assert issue_first["accepted_records"] == 1
    assert issue_first["skipped_no_slot"] == 1
    assert issue_first["fixed_initial_capital_return_pct"] == 10.0


def test_repo_adapter_audit_reports_partial_not_pit_complete(tmp_path: Path, history: dict) -> None:
    repo = tmp_path / "repo"
    (repo / "data" / "yahoo").mkdir(parents=True)
    (repo / "data" / "regime").mkdir(parents=True)
    (repo / "data" / "options_flow").mkdir(parents=True)
    (repo / "data" / "flow_signals").mkdir(parents=True)
    (repo / "data" / "polygon_gex").mkdir(parents=True)
    (repo / "data" / "options_dislocation").mkdir(parents=True)
    (repo / "data" / "news").mkdir(parents=True)
    (repo / "data" / "desk_grader").mkdir(parents=True)

    first = history["records"][0]
    first_ticker = first["ticker"]
    pd.DataFrame(
        {"close": [100.0], "close_price": [100.0], "volume": [1000]},
        index=pd.DatetimeIndex(["2024-01-02"], name="Date"),
    ).to_parquet(repo / "data" / "yahoo" / f"{first_ticker}.parquet")
    all_issue_dates = pd.to_datetime(
        ["2024-01-02", "2025-09-24", "2026-05-06", "2026-05-07"]
    )
    pd.DataFrame(
        {"quad": ["Q1"] * 4, "vintage_store_asof": ["fixture"] * 4},
        index=all_issue_dates,
    ).to_parquet(repo / "data" / "regime" / "regime_v2_pit.parquet")

    option_ticker = history["records"][1]["ticker"]
    pd.DataFrame(
        {"volume": [100], "premium_mn": [1.0]},
        index=pd.DatetimeIndex(["2025-09-24"]),
    ).to_parquet(repo / "data" / "options_flow" / f"summary_{option_ticker}.parquet")
    pd.DataFrame(
        {
            "root": [option_ticker],
            "session_date": ["2025-09-24"],
            "ts": ["2025-09-24T15:00:00Z"],
            "ingested_at": ["2025-09-24T15:00:01Z"],
        }
    ).to_parquet(repo / "data" / "flow_signals" / "ledger.parquet")
    pd.DataFrame(
        {"net_gex_bn": [1.0]},
        index=pd.DatetimeIndex(["2025-09-24"]),
    ).to_parquet(repo / "data" / "polygon_gex" / f"summary_{option_ticker}.parquet")
    last_ticker = history["records"][3]["ticker"]
    pd.DataFrame(
        {"underlying": [last_ticker], "date": ["2026-05-07"], "iv30": [0.4]}
    ).to_parquet(repo / "data" / "options_dislocation" / "snapshots.parquet")
    pd.DataFrame(
        {
            "first_seen_utc": ["2024-01-02T14:00:00Z"],
            "tickers": [[first_ticker]],
        }
    ).to_parquet(repo / "data" / "news" / "event_log.parquet")
    (repo / "data" / "desk_grader" / "alt_data_snapshots.jsonl").write_text(
        json.dumps({"ticker": last_ticker, "date": "2026-05-07"}) + "\n",
        encoding="utf-8",
    )
    theta_file = (
        repo
        / "data"
        / "thetadata_eod"
        / "eod"
        / option_ticker
        / "2025.parquet"
    )
    theta_file.parent.mkdir(parents=True)
    theta_file.touch()

    audit = {row["family"]: row for row in audit_repo_data(repo, history["records"])}
    assert audit["price_technical"]["exact_issue_date_records"] == 1
    assert audit["price_technical"]["within_day_ready"] is False
    assert audit["macro_regime"]["exact_issue_date_records"] == 4
    assert audit["options_flow_campaign"]["exact_issue_date_records"] == 1
    assert (
        audit["options_flow_campaign"]["supporting_counts"][
            "daily_aggregate_exact_issue_records"
        ]
        == 1
    )
    assert audit["gex_vol_oi"]["exact_issue_date_records"] == 2
    assert audit["gex_vol_oi"]["supporting_counts"]["theta_eod_yearfile_records"] == 1
    assert audit["news_alt_data"]["exact_issue_date_records"] == 2


def test_private_outputs_are_refused_inside_repo_and_aggregate_stays_redacted(
    tmp_path: Path,
    history: dict,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ReplayInputError, match="outside the repository"):
        enforce_private_output_boundary(repo / "private", repo)

    cases = build_replay_cases(history, "b" * 64)
    features = build_feature_receipt_requirements(cases)
    aggregate = build_aggregate_receipt(
        history,
        "b" * 64,
        cases,
        features,
        audit_repo_data(repo, history["records"]),
        build_theta_data_plane_summary(repo, history["records"], None),
        generated_at="2026-08-09T04:00:00Z",
    )
    paths = write_outputs(
        private_output_dir=tmp_path / "private",
        aggregate_receipt_path=repo / "aggregate.json",
        repo_root=repo,
        cases=cases,
        feature_receipts=features,
        aggregate_receipt=aggregate,
        theta_restore_plan=build_theta_selective_restore_plan(history["records"]),
        theta_remote_inventory=None,
    )
    assert os.stat(paths["cases"]).st_mode & 0o777 == 0o600
    assert os.stat(paths["features"]).st_mode & 0o777 == 0o600
    assert sum(1 for _ in paths["cases"].open(encoding="utf-8")) == 4
    assert sum(1 for _ in paths["features"].open(encoding="utf-8")) == 60
    assert sum(1 for _ in paths["theta_restore_plan"].open(encoding="utf-8")) == 12

    aggregate_text = paths["aggregate_receipt"].read_text(encoding="utf-8")
    assert "SYNPRIVATE" not in aggregate_text
    assert "private raw row" not in aggregate_text
    assert "private authorization excerpt" not in aggregate_text
    assert json.loads(aggregate_text)["privacy"]["ticker_values_included"] is False
