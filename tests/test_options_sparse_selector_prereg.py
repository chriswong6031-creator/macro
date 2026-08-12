from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.build_options_sparse_selector_prereg import (
    ABSTENTION_REASON_CODES,
    BENCHMARK_BASELINE_COMMIT,
    BENCHMARK_DIGEST,
    BENCHMARK_EFFECTIVE_FREEZE_AT,
    BENCHMARK_FILE_BYTES,
    BENCHMARK_FILE_SHA256,
    BENCHMARK_FIRST_MAIN_COMMIT,
    BENCHMARK_FIRST_MAIN_COMMITTED_AT,
    BENCHMARK_PATH,
    BENCHMARK_REGISTERED_AT,
    BENCHMARK_SCHEMA_PATH,
    CAMPAIGN_V2_CONTRACT_RECEIPTS,
    CAMPAIGN_V2_POLICIES,
    CAMPAIGN_V2_RULE_SHA256,
    CONTEXT_REFERENCE_CONTRACT_RECEIPTS,
    LEGACY_CAMPAIGN_PATH,
    LEGACY_CAMPAIGN_SCHEMA_PATH,
    LIFECYCLE_CONTRACT_RECEIPTS,
    NYSE_CLOCK_CONTRACT_RECEIPTS,
    RECEIPT_PATH,
    RECEIPT_SCHEMA_PATH,
    SELECTOR_EFFECTIVE_FREEZE_AT,
    SELECTOR_EFFECTIVE_FREEZE_RULE,
    SELECTOR_EFFECTIVE_FREEZE_SESSION,
    RegistrationError,
    build_receipt,
    canonical_bytes,
    receipt_bytes,
    validate_campaign_v2_context_owner_binding,
    validate_campaign_v2_time_fence,
    validate_proposal_decision_clock,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy(root: Path, relative: Path) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / relative, destination)


def _minimal_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        BENCHMARK_PATH,
        BENCHMARK_SCHEMA_PATH,
        LEGACY_CAMPAIGN_PATH,
        LEGACY_CAMPAIGN_SCHEMA_PATH,
        RECEIPT_SCHEMA_PATH,
        *(Path(item["path"]) for item in CAMPAIGN_V2_CONTRACT_RECEIPTS),
        *(Path(item["path"]) for item in CONTEXT_REFERENCE_CONTRACT_RECEIPTS),
        *(Path(item["path"]) for item in LIFECYCLE_CONTRACT_RECEIPTS),
        *(Path(item["path"]) for item in NYSE_CLOCK_CONTRACT_RECEIPTS),
    ):
        _copy(root, relative)
    return root


def _campaign_rows(root: Path) -> list[dict]:
    return [json.loads(line) for line in (root / LEGACY_CAMPAIGN_PATH).read_text().splitlines()]


def _write_campaign_rows(root: Path, rows: list[dict]) -> None:
    (root / LEGACY_CAMPAIGN_PATH).write_bytes(
        b"".join(canonical_bytes(row) + b"\n" for row in rows)
    )


def _content_id(prefix: str, value: dict, field: str) -> str:
    core = copy.deepcopy(value)
    core[field] = ""
    return prefix + hashlib.sha256(canonical_bytes(core)).hexdigest()


def _spy_campaign_context_case() -> tuple[dict, bytes, dict]:
    from engine.options_market_memory_context import (
        _reference,
        load_canary_identity_snapshot,
    )

    ledger_raw = (ROOT / "data/options_signal_episode/episodes.jsonl").read_bytes()
    lines = ledger_raw.splitlines(keepends=True)
    selected = next(
        (ordinal, line)
        for ordinal, line in enumerate(lines, start=1)
        if json.loads(line)["ticker"] == "SPY"
    )
    source_row, line_with_newline = selected
    line = line_with_newline.rstrip(b"\n")
    episode = json.loads(line)
    prefix = b"".join(lines[:source_row])
    strike_key = format(episode["contract"]["strike"], "g")
    campaign = {
        "schema": "options.signal_campaign/v2",
        "policies": copy.deepcopy(CAMPAIGN_V2_POLICIES),
        "formed_at": episode["available_at"],
        "group": {
            "session_date": episode["session_date"],
            "ticker": episode["ticker"],
            "right": episode["contract"]["right"],
            "expiration": episode["contract"]["expiration"],
            "strike": episode["contract"]["strike"],
            "strike_key": strike_key,
        },
        "members": [
            {
                "episode_id": episode["episode_id"],
                "available_at": episode["available_at"],
                "source_row": source_row,
                "source_row_sha256": hashlib.sha256(line).hexdigest(),
            }
        ],
        "source_episode_prefix": {
            "path": "data/options_signal_episode/episodes.jsonl",
            "records": source_row,
            "prefix_sha256": hashlib.sha256(prefix).hexdigest(),
        },
    }
    identity = load_canary_identity_snapshot(ROOT / "config/market_memory_canary.v1.json")
    owner = {
        "schema": "options.signal_episode/v1",
        "id": episode["episode_id"],
        "record_sha256": hashlib.sha256(line).hexdigest(),
        "ticker": episode["ticker"],
        "event_time": episode["event_time"],
        "requested_as_of": episode["available_at"],
        "requested_as_of_basis": "durable_available_at",
        "evidence_phase": "decision_time_actual_output",
    }
    context = {
        "context_id": "mmctx_" + "1" * 64,
        "packet_sha256": "2" * 64,
        "capture_id": "mmcapture_" + "3" * 64,
        "capture_schema": "market_memory.capture_receipt.v1",
        "query_id": "mmquery_" + "4" * 64,
        "basis": "exact_requested_as_of_capture",
        "source_receipt_ids": [],
        "source_artifact_sha256s": [],
        "missing_feature_ids": [],
        "domain_coverage_sha256": "5" * 64,
    }
    reference = _reference(
        owner=owner,
        subject=identity.subject,
        identity_config_sha256=identity.config_sha256,
        disposition="bound",
        reason=None,
        context=context,
    )
    return campaign, prefix, reference


def test_contract_and_committed_receipt_are_exact_fresh_build() -> None:
    schema = json.loads((ROOT / RECEIPT_SCHEMA_PATH).read_text())
    Draft202012Validator.check_schema(schema)
    receipt = build_receipt(ROOT)
    Draft202012Validator(schema).validate(receipt)
    assert (ROOT / RECEIPT_PATH).read_bytes() == receipt_bytes(ROOT)


def test_receipt_and_embedded_rule_are_content_identified() -> None:
    receipt = build_receipt(ROOT)
    assert receipt["receipt_id"] == _content_id("ossr_", receipt, "receipt_id")
    assert receipt["registration"]["selector_rule_sha256"] == hashlib.sha256(
        canonical_bytes(receipt["selector_rule"])
    ).hexdigest()
    manifest = receipt["activation_manifest"]
    assert manifest["manifest_id"] == _content_id("ossm_", manifest, "manifest_id")


def test_registration_binds_complete_benchmark_and_every_rule_component() -> None:
    receipt = build_receipt(ROOT)
    registration = receipt["registration"]
    benchmark = registration["benchmark"]
    raw = (ROOT / BENCHMARK_PATH).read_bytes()
    assert len(raw) == benchmark["file_bytes"] == BENCHMARK_FILE_BYTES
    assert hashlib.sha256(raw).hexdigest() == benchmark["file_sha256"] == (
        BENCHMARK_FILE_SHA256
    )
    assert benchmark == {
        "path": BENCHMARK_PATH.as_posix(),
        "schema": "momoedge.completion_benchmark_prereg/v1",
        "file_sha256": BENCHMARK_FILE_SHA256,
        "file_bytes": BENCHMARK_FILE_BYTES,
        "canonicalization": "json_utf8_sort_keys_compact_no_ascii_escape/v1",
        "benchmark_digest_sha256": BENCHMARK_DIGEST,
        "registered_at": BENCHMARK_REGISTERED_AT,
        "baseline_commit": BENCHMARK_BASELINE_COMMIT,
        "effective_freeze_rule": (
            "later_of_registered_at_and_first_origin_main_commit_containing_exact_benchmark_digest"
        ),
        "first_origin_main_commit_containing_digest": BENCHMARK_FIRST_MAIN_COMMIT,
        "first_origin_main_commit_committed_at": BENCHMARK_FIRST_MAIN_COMMITTED_AT,
        "effective_freeze_at": BENCHMARK_EFFECTIVE_FREEZE_AT,
    }
    rule = receipt["selector_rule"]
    components = registration["selector_rule_component_sha256s"]
    assert components == {
        "candidate_manifest_rule_sha256": hashlib.sha256(
            canonical_bytes(rule["candidate_manifest"])
        ).hexdigest(),
        "decision_rule_sha256": hashlib.sha256(
            canonical_bytes(rule["decisions"])
        ).hexdigest(),
        "evidence_rule_sha256": hashlib.sha256(
            canonical_bytes(
                {
                    "exact_contract": rule["exact_contract"],
                    "required_truth_receipts": rule["required_truth_receipts"],
                    "abstention_reason_codes": rule["abstention_reason_codes"],
                }
            )
        ).hexdigest(),
        "source_campaign_rule_sha256": CAMPAIGN_V2_RULE_SHA256,
    }
    assert registration["selector_effective_freeze"] == {
        "rule": SELECTOR_EFFECTIVE_FREEZE_RULE,
        "state": "preregistered_future_nyse_boundary",
        "nyse_session_date": SELECTOR_EFFECTIVE_FREEZE_SESSION,
        "timezone": "America/New_York",
        "boundary": "session_open_lower_inclusive",
        "first_origin_main_commit_containing_rule_digest": None,
        "first_origin_main_commit_committed_at": None,
        "origin_main_hosting_requirement": (
            "exact_rule_digest_must_be_on_origin_main_before_effective_freeze"
        ),
        "origin_main_requirement_failure_action": (
            "global_abstain_new_version_and_future_nyse_boundary_required"
        ),
        "pre_effective_source_policy": (
            "retrospective_global_abstain_permanently_ineligible"
        ),
        "effective_freeze_at": SELECTOR_EFFECTIVE_FREEZE_AT,
    }


def test_current_eight_legacy_campaigns_are_permanently_ineligible() -> None:
    receipt = build_receipt(ROOT)
    source = receipt["activation_manifest"]["source"]
    rows = _campaign_rows(ROOT)
    assert len(rows) == source["records"] == 8
    assert source["sha256"] == hashlib.sha256(
        (ROOT / LEGACY_CAMPAIGN_PATH).read_bytes()
    ).hexdigest()
    assert {row["schema"] for row in rows} == {"options.signal_campaign/v1"}
    assert {row["evidence_phase"] for row in rows} == {"retrospective_discovery"}
    assert all(row["disposition"] == "abstain" for row in rows)
    assert all(row["training_eligible"] is False for row in rows)
    assert all(not any(row["authority"].values()) for row in rows)
    assert receipt["selector_rule"]["version_fence"]["legacy_campaign_v1_policy"] == (
        "permanently_ineligible"
    )


def test_empty_denominator_is_reconciled_without_claiming_sparse_gate() -> None:
    receipt = build_receipt(ROOT)
    manifest = receipt["activation_manifest"]
    reconciliation = receipt["reconciliation"]
    empty_digest = hashlib.sha256(canonical_bytes([])).hexdigest()
    assert manifest["candidate_count"] == manifest["prospective_source_count"] == 0
    assert manifest["excluded_legacy_source_count"] == 8
    assert manifest["candidate_ids_sha256"] == empty_digest
    assert reconciliation == {
        "candidate_count": 0,
        "decision_count": 0,
        "abstain_decision_count": 0,
        "propose_decision_count": 0,
        "candidate_ids_sha256": empty_digest,
        "decision_candidate_ids_sha256": empty_digest,
        "exactly_one_reconciled": True,
        "coverage_ratio": 1.0,
        "empty_set_policy": "vacuous_one_to_one_not_sparse_gate_evidence",
        "silent_drop_count": 0,
        "minimum_proposals_per_nyse_session": 0,
        "maximum_proposals_per_nyse_session": 3,
    }
    assert receipt["activation_disposition"] == {
        "action": "abstain",
        "reason_codes": ["NO_PROSPECTIVE_CANDIDATES"],
        "selector_active": False,
        "future_rows_policy": "new_governed_implementation_required",
    }
    assert not any(receipt["claim_boundary"].values())


def test_future_rule_freezes_sparse_no_quota_exactly_one_policy() -> None:
    rule = build_receipt(ROOT)["selector_rule"]
    assert rule["candidate_manifest"]["source_contract_registration"] == {
        "state": "merged_origin_main_dependency_bound",
        "dependency_pull_request": 5362,
        "dependency_merge_commit": "d8e290032710d84e538c32af0d58358a16407c88",
        "required_before_any_candidate": True,
        "exact_schema_full_file_receipt": CAMPAIGN_V2_CONTRACT_RECEIPTS[0],
        "exact_implementation_full_file_receipt": CAMPAIGN_V2_CONTRACT_RECEIPTS[1],
        "dependency_absence_or_failure_action": "abstain",
    }
    assert rule["version_fence"]["effective_freeze_rule"] == (
        SELECTOR_EFFECTIVE_FREEZE_RULE
    )
    assert rule["version_fence"]["selector_effective_freeze_at"] == (
        SELECTOR_EFFECTIVE_FREEZE_AT
    )
    assert rule["version_fence"]["pre_effective_source_policy"] == (
        "retrospective_global_abstain_permanently_ineligible"
    )
    assert rule["candidate_manifest"]["manifest_before_decisions"] is True
    assert rule["candidate_manifest"]["first_observed_revision_frozen"] is True
    assert rule["decisions"]["actions"] == ["abstain", "propose"]
    assert rule["decisions"]["exactly_one_per_candidate"] is True
    assert rule["decisions"]["minimum_proposals_per_nyse_session"] == 0
    assert rule["decisions"]["maximum_proposals_per_nyse_session"] == 3
    assert rule["decisions"]["quota_or_forced_fill"] is False
    assert rule["decisions"]["ranking_or_scoring"] is False
    assert rule["decisions"]["proposal_semantics"] == (
        "private_research_review_only_not_issued_plan"
    )


def test_campaign_v2_dependency_is_the_exact_final_merged_contract() -> None:
    from engine.options_signal_campaign import RULE_FROZEN_AT

    assert RULE_FROZEN_AT == CAMPAIGN_V2_POLICIES["frozen_at"] == (
        SELECTOR_EFFECTIVE_FREEZE_AT
    )
    schema = json.loads(
        (ROOT / CAMPAIGN_V2_CONTRACT_RECEIPTS[0]["path"]).read_text()
    )
    assert schema["properties"]["policies"]["properties"]["frozen_at"] == {
        "const": SELECTOR_EFFECTIVE_FREEZE_AT
    }
    for file_receipt in CAMPAIGN_V2_CONTRACT_RECEIPTS:
        raw = (ROOT / file_receipt["path"]).read_bytes()
        assert len(raw) == file_receipt["file_bytes"]
        assert hashlib.sha256(raw).hexdigest() == file_receipt["file_sha256"]
        assert file_receipt["source_commit"] == (
            "d8e290032710d84e538c32af0d58358a16407c88"
        )


def test_future_rule_requires_exact_contract_and_all_truth_receipts() -> None:
    rule = build_receipt(ROOT)["selector_rule"]
    assert rule["exact_contract"]["campaign_required_fields"] == [
        "ticker",
        "right",
        "expiration",
        "strike",
        "strike_key",
    ]
    assert rule["exact_contract"]["mark_and_lifecycle_required_fields"] == [
        "root",
        "right",
        "expiry",
        "strike",
        "strike_millis",
        "occ_symbol",
    ]
    assert rule["exact_contract"]["fuzzy_or_derived_substitution"] is False
    truth = rule["required_truth_receipts"]
    assert set(truth) == {"options", "konseki", "mark", "lifecycle"}
    assert truth["options"]["missing_action"] == "abstain"
    assert truth["konseki"]["exact_absence_reason"] == (
        "exact_requested_as_of_context_absent"
    )
    assert truth["konseki"]["missing_or_absent_action"] == "abstain"
    assert truth["mark"]["nbbo_or_execution_authority"] is False
    assert truth["mark"]["missing_or_unavailable_action"] == "abstain"
    assert truth["lifecycle"]["candidate_mapping"]["require_open_enrollment"] is True
    assert truth["lifecycle"]["candidate_mapping"]["terminal_action"] == "abstain"
    assert truth["lifecycle"]["missing_drift_or_unavailable_action"] == "abstain"
    assert rule["abstention_reason_codes"] == ABSTENTION_REASON_CODES


def _future_campaign(*, formed_at: str, final_available_at: str) -> dict:
    return {
        "schema": "options.signal_campaign/v2",
        "policies": copy.deepcopy(CAMPAIGN_V2_POLICIES),
        "evidence_phase": "prospective_after_rule_freeze",
        "formed_at": formed_at,
        "members": [{"available_at": final_available_at}],
    }


def test_campaign_time_fence_accepts_only_immutable_post_freeze_source_clocks() -> None:
    campaign = _future_campaign(
        formed_at="2026-08-12T13:30:00Z",
        final_available_at="2026-08-12T13:30:00Z",
    )
    validate_campaign_v2_time_fence(
        campaign,
        first_selector_observed_available_at="2026-08-12T13:30:01Z",
        selector_effective_freeze_at=SELECTOR_EFFECTIVE_FREEZE_AT,
    )


def test_delayed_observation_cannot_admit_a_pre_freeze_campaign() -> None:
    campaign = _future_campaign(
        formed_at="2026-08-12T13:29:59Z",
        final_available_at="2026-08-12T13:29:59Z",
    )
    with pytest.raises(RegistrationError, match="source clocks predate"):
        validate_campaign_v2_time_fence(
            campaign,
            first_selector_observed_available_at="2026-08-12T18:00:00Z",
            selector_effective_freeze_at=SELECTOR_EFFECTIVE_FREEZE_AT,
        )


@pytest.mark.parametrize(
    ("formed_at", "final_available_at", "selector_freeze", "message"),
    [
        (
            "2026-08-12T13:30:00Z",
            "2026-08-12T13:30:01Z",
            SELECTOR_EFFECTIVE_FREEZE_AT,
            "must equal",
        ),
        (
            "2026-08-12T13:30:00Z",
            "2026-08-12T13:30:00Z",
            "2026-08-11T21:00:00Z",
            "cannot predate registration",
        ),
        (
            "2026-08-13T13:30:00Z",
            "2026-08-13T13:30:00Z",
            "2026-08-13T13:30:00Z",
            "differs from the frozen registration",
        ),
    ],
)
def test_campaign_time_fence_rejects_mismatched_or_unregistered_clocks(
    formed_at: str,
    final_available_at: str,
    selector_freeze: str,
    message: str,
) -> None:
    with pytest.raises(RegistrationError, match=message):
        validate_campaign_v2_time_fence(
            _future_campaign(
                formed_at=formed_at,
                final_available_at=final_available_at,
            ),
            first_selector_observed_available_at="2026-08-13T13:31:00Z",
            selector_effective_freeze_at=selector_freeze,
        )


def test_campaign_v2_binds_exactly_through_final_episode_owner_to_existing_pit_reference() -> None:
    campaign, prefix, reference = _spy_campaign_context_case()
    validate_campaign_v2_context_owner_binding(
        campaign,
        episode_prefix_raw=prefix,
        context_reference=reference,
        repo_root=ROOT,
    )
    konsekI = build_receipt(ROOT)["selector_rule"]["required_truth_receipts"][
        "konseki"
    ]
    assert konsekI["reference_schema"] == "options.market_memory_context_reference/v1"
    assert konsekI["reference_owner_schema"] == "options.signal_episode/v1"
    assert konsekI["owner_binding"] == "campaign_v2_final_member_episode/v1"
    assert konsekI["subject_identity"] == {
        "symbol": "SPY",
        "subject_id": (
            "mmsecurity_5fc37e8db34f74314b654c910ea8bacfa7de8b5d2d067f2e5421c9d5745ceb4c"
        ),
        "instrument_id": (
            "mmsecurity_6f361f5bad9f06a3b2ff157585d5728f55f77198420959aadd8922d1045c3fea"
        ),
        "identity_config_sha256": (
            "5e7823e48866b2c0828122b65f684ed5872c6816a6224f61e44db4c03d129b33"
        ),
    }


@pytest.mark.parametrize(
    "defect",
    [
        "non_source_prefix",
        "source_row_sha256",
        "final_available_at",
        "group_strike",
        "reference_owner",
        "reference_subject",
    ],
)
def test_campaign_v2_context_bridge_fails_closed_on_every_exact_join_drift(
    defect: str,
) -> None:
    from engine.options_market_memory_context import _reference

    campaign, prefix, reference = _spy_campaign_context_case()
    if defect == "non_source_prefix":
        forged = bytearray(prefix)
        forged[0] = ord("[")
        prefix = bytes(forged)
        campaign["source_episode_prefix"]["prefix_sha256"] = hashlib.sha256(
            prefix
        ).hexdigest()
    elif defect == "source_row_sha256":
        campaign["members"][-1]["source_row_sha256"] = "0" * 64
    elif defect == "final_available_at":
        campaign["members"][-1]["available_at"] = "2026-08-11T19:00:00Z"
    elif defect == "group_strike":
        campaign["group"]["strike"] += 1
    elif defect == "reference_owner":
        owner = copy.deepcopy(reference["owner"])
        owner["record_sha256"] = "0" * 64
        reference = _reference(
            owner=owner,
            subject=reference["query"]["subject"],
            identity_config_sha256=reference["query"]["identity_config_sha256"],
            disposition="bound",
            reason=None,
            context=reference["context"],
        )
    else:
        reference = _reference(
            owner=reference["owner"],
            subject={"subject_id": "mmsecurity_" + "6" * 64, "instrument_id": "mmsecurity_" + "7" * 64},
            identity_config_sha256="8" * 64,
            disposition="bound",
            reason=None,
            context=reference["context"],
        )
    with pytest.raises(RegistrationError):
        validate_campaign_v2_context_owner_binding(
            campaign,
            episode_prefix_raw=prefix,
            context_reference=reference,
            repo_root=ROOT,
        )


def test_exact_requested_asof_context_absence_forces_abstention() -> None:
    from engine.options_market_memory_context import _reference

    campaign, prefix, bound = _spy_campaign_context_case()
    absent = _reference(
        owner=bound["owner"],
        subject=bound["query"]["subject"],
        identity_config_sha256=bound["query"]["identity_config_sha256"],
        disposition="abstained",
        reason="exact_requested_as_of_context_absent",
        context=None,
    )
    with pytest.raises(RegistrationError, match="requires a bound exact context"):
        validate_campaign_v2_context_owner_binding(
            campaign,
            episode_prefix_raw=prefix,
            context_reference=absent,
            repo_root=ROOT,
        )


def test_nyse_proposal_clock_freezes_regular_and_early_close_session_buckets() -> None:
    assert validate_proposal_decision_clock(
        decision_event_at="2026-08-11T13:30:00Z",
        decision_available_at="2026-08-11T13:31:00Z",
    ) == "2026-08-11"
    assert validate_proposal_decision_clock(
        decision_event_at="2026-11-27T17:59:00Z",
        decision_available_at="2026-11-27T17:59:59Z",
    ) == "2026-11-27"


@pytest.mark.parametrize(
    ("event_at", "available_at"),
    [
        ("2026-08-11T13:31:00Z", "2026-08-11T13:30:00Z"),
        ("2026-08-11T19:59:00Z", "2026-08-11T20:00:00Z"),
        ("2026-11-27T17:59:00Z", "2026-11-27T18:00:00Z"),
        ("2026-08-15T14:00:00Z", "2026-08-15T14:01:00Z"),
    ],
)
def test_nyse_proposal_clock_rejects_noncausal_closed_or_non_session_clocks(
    event_at: str,
    available_at: str,
) -> None:
    with pytest.raises(RegistrationError):
        validate_proposal_decision_clock(
            decision_event_at=event_at,
            decision_available_at=available_at,
        )


def test_nyse_cap_counts_only_proposals_in_the_exact_frozen_session_bucket() -> None:
    decisions = build_receipt(ROOT)["selector_rule"]["decisions"]
    clock = decisions["nyse_session_clock"]
    assert decisions["minimum_proposals_per_nyse_session"] == 0
    assert decisions["maximum_proposals_per_nyse_session"] == 3
    assert clock["session_bucket_rule"] == (
        "unique_session_containing_both_event_and_available_clocks"
    )
    assert clock["boundary"] == "lower_inclusive_upper_exclusive"
    assert clock["cap_evaluation_order"] == ["candidate_available_at", "candidate_id"]
    assert clock["fourth_and_later_passing_action"] == "abstain"


def test_lifecycle_rule_binds_the_actual_merged_state_mapping_and_contract_bytes() -> None:
    lifecycle = build_receipt(ROOT)["selector_rule"]["required_truth_receipts"][
        "lifecycle"
    ]
    assert lifecycle["state_required_fields"] == [
        "schema",
        "state_id",
        "activation",
        "lifecycle_head",
        "ledger_cursor",
        "mark_cursor",
        "enrollments",
        "terminals",
        "latest_marks",
    ]
    assert lifecycle["state_mapping"] == {
        "lifecycle_head": "validated_event_chain_head",
        "activation": "validated_event_chain_root_activation_pointer",
        "ledger_cursor": "exact_canonical_main_ledger_prefix_receipt",
        "mark_cursor": "exact_private_mark_chain_head_pointer",
    }
    serialized = json.dumps(lifecycle, sort_keys=True)
    for fictional in (
        "activation_boundary",
        "canonical_ledger_receipt",
        "mark_chain_pointer",
    ):
        assert fictional not in serialized
    for file_receipt in lifecycle["contract_receipts"]:
        raw = (ROOT / file_receipt["path"]).read_bytes()
        assert len(raw) == file_receipt["file_bytes"]
        assert hashlib.sha256(raw).hexdigest() == file_receipt["file_sha256"]


@pytest.mark.parametrize("receipt_index", [0, 1])
def test_campaign_v2_dependency_byte_drift_fails_closed(
    tmp_path: Path, receipt_index: int
) -> None:
    root = _minimal_repo(tmp_path)
    path = root / CAMPAIGN_V2_CONTRACT_RECEIPTS[receipt_index]["path"]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(RegistrationError, match="full-file receipt drift"):
        build_receipt(root)


def test_every_authority_and_promotion_claim_is_false() -> None:
    receipt = build_receipt(ROOT)
    assert not any(receipt["authority"].values())
    assert not any(receipt["selector_rule"]["authority"].values())
    assert not any(receipt["claim_boundary"].values())


def test_prospective_relabel_of_legacy_row_fails_closed(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    rows = _campaign_rows(root)
    rows[0]["evidence_phase"] = "prospective_after_rule_freeze"
    _write_campaign_rows(root, rows)
    with pytest.raises(RegistrationError, match="frozen benchmark baseline|retrospective"):
        build_receipt(root)


def test_authority_mutation_fails_closed(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    rows = _campaign_rows(root)
    rows[0]["authority"]["may_select"] = True
    _write_campaign_rows(root, rows)
    with pytest.raises(RegistrationError, match="schema validation|benchmark baseline"):
        build_receipt(root)


def test_duplicate_campaign_identity_fails_closed(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    rows = _campaign_rows(root)
    rows.append(copy.deepcopy(rows[0]))
    _write_campaign_rows(root, rows)
    with pytest.raises(RegistrationError, match="duplicate legacy campaign identity"):
        build_receipt(root)


@pytest.mark.parametrize("defect", ["torn", "blank", "noncanonical", "duplicate_key"])
def test_ledger_serialization_defects_fail_closed(tmp_path: Path, defect: str) -> None:
    root = _minimal_repo(tmp_path)
    path = root / LEGACY_CAMPAIGN_PATH
    raw = path.read_bytes()
    if defect == "torn":
        path.write_bytes(raw.rstrip(b"\n"))
    elif defect == "blank":
        path.write_bytes(raw.replace(b"\n", b"\n\n", 1))
    elif defect == "noncanonical":
        first, *rest = raw.splitlines()
        path.write_bytes(json.dumps(json.loads(first), indent=2).encode() + b"\n" + b"\n".join(rest) + b"\n")
    else:
        first, *rest = raw.splitlines()
        forged = first[:-1] + b',"schema":"options.signal_campaign/v1"}'
        path.write_bytes(forged + b"\n" + b"\n".join(rest) + b"\n")
    with pytest.raises(RegistrationError):
        build_receipt(root)


def test_benchmark_digest_mutation_fails_closed(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    path = root / BENCHMARK_PATH
    benchmark = json.loads(path.read_text())
    benchmark["benchmark"]["completion_rule"]["current_state_at_registration"] = "surpass"
    path.write_text(json.dumps(benchmark))
    with pytest.raises(RegistrationError, match="full-file receipt|schema validation|digest drift"):
        build_receipt(root)


def test_benchmark_byte_rewrite_fails_even_when_canonical_object_digest_is_unchanged(
    tmp_path: Path,
) -> None:
    root = _minimal_repo(tmp_path)
    path = root / BENCHMARK_PATH
    original = json.loads(path.read_text())
    assert hashlib.sha256(canonical_bytes(original["benchmark"])).hexdigest() == (
        BENCHMARK_DIGEST
    )
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"schema": ', b'"schema" : ', 1))
    assert hashlib.sha256(
        canonical_bytes(json.loads(path.read_text())["benchmark"])
    ).hexdigest() == BENCHMARK_DIGEST
    with pytest.raises(RegistrationError, match="full-file receipt drift"):
        build_receipt(root)


def test_cli_check_proves_tracked_bytes() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_options_sparse_selector_prereg.py"),
            "--check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "OK research/options_estate/sparse_selector_preregistration_receipt_v1.json" in (
        completed.stdout
    )
