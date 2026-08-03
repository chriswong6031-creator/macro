from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from inspect import signature
import json
from pathlib import Path

import pytest

import engine.biocatalyst.change_classification as change_classification
from engine.biocatalyst.change_classification import (
    ChangeClassificationError,
    ProspectiveActivationProof,
    TrialChangeCompilation,
    compile_prospective_trial_change,
    compile_retrospective_trial_change,
    validate_prospective_trial_change_compilation,
    validate_retrospective_trial_change_compilation,
)
from engine.biocatalyst.endpoint_alignment import (
    build_trial_endpoint_alignment_review_projection,
)
from engine.biocatalyst.history import build_history_exact_diff
from engine.biocatalyst.change_tape import (
    ChangeTapeError,
    build_trial_change_tape_read_model,
    validate_trial_change_tape_read_model,
)
from engine.biocatalyst.prospective import SourceEvidence
from engine.sector_intelligence import (
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
    validate_trial_change_alert_projection,
    validate_trial_change_classification,
)
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
)
import engine.sector_intelligence.contracts as sector_contracts


ROOT = Path(__file__).resolve().parents[1]
CTGOV_FIXTURES = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials"
CHANGE_FIXTURES = (
    ROOT / "data" / "biocatalyst" / "fixtures" / "change_classification"
)
NCT_ID = "NCT01234567"
BEFORE_RUN_STARTED_AT = datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)
AFTER_RUN_STARTED_AT = datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)
AUTHORITY = {
    "classification": "source_fact",
    "decision_authority": False,
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "raise_authority",
    ],
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _study(
    *,
    nct_id: str = NCT_ID,
    title: str = "Synthetic exact-history study",
    status: str = "RECRUITING",
    enrollment: int = 100,
    start_date: str = "2025-01-01",
    primary_completion: str = "2025-09-01",
    completion: str = "2025-12-01",
    locations: list[dict] | None = None,
    outcomes: list[dict] | None = None,
    interventions: list[dict] | None = None,
) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": title},
            "statusModule": {
                "overallStatus": status,
                "startDateStruct": {"date": start_date, "type": "ACTUAL"},
                "primaryCompletionDateStruct": {
                    "date": primary_completion,
                    "type": "ESTIMATED",
                },
                "completionDateStruct": {
                    "date": completion,
                    "type": "ESTIMATED",
                },
            },
            "designModule": {
                "enrollmentInfo": {"count": enrollment, "type": "ESTIMATED"}
            },
            "contactsLocationsModule": {
                "locations": locations
                or [{"facility": "North Hospital", "city": "Boston"}]
            },
            "outcomesModule": {
                "primaryOutcomes": outcomes
                or [
                    {
                        "measure": "Response rate",
                        "timeFrame": "12 weeks",
                        "description": "Baseline",
                    }
                ],
                "secondaryOutcomes": [],
                "otherOutcomes": [],
            },
            "armsInterventionsModule": {
                "interventions": interventions
                or [
                    {
                        "name": "X-101",
                        "type": "DRUG",
                        "description": "Initial formulation",
                    }
                ]
            },
        }
    }


def _history_snapshot(
    study: dict,
    *,
    source_version: int,
    retrieved_at: str,
    transaction_from: str,
) -> dict:
    nct_id = study["protocolSection"]["identificationModule"]["nctId"]
    content_hash = canonical_json_sha256(study)
    run_ref = f"ctgov_history_run_{nct_id}_classification_fixture"
    seed = canonical_json_sha256(
        {
            "nct_id": nct_id,
            "source_version": source_version,
            "canonical_content_sha256": content_hash,
            "run_ref": run_ref,
        }
    )
    payload = {
        "contract_id": "trial_history_source_snapshot.v1",
        "schema_version": "1.0.0",
        "source_snapshot_id": f"ctgov_history_snapshot_{nct_id}_{seed[:24]}",
        "nct_id": nct_id,
        "source_id": "clinicaltrials_gov_record_history",
        "run_ref": run_ref,
        "history_index_receipt_ref": f"ctgov_history_receipt_{nct_id}_index",
        "history_version_receipt_ref": (
            f"ctgov_history_receipt_{nct_id}_version_{source_version}"
        ),
        "source_version": source_version,
        "display_version": source_version + 1,
        "source_record_ref": (
            f"src:ctgov-history:{nct_id}:version:{source_version}:sha256:{content_hash}"
        ),
        "source_uri": (
            f"https://clinicaltrials.gov/study/{nct_id}?a={source_version + 1}&tab=history"
        ),
        "source_submitted_at": f"2025-0{source_version + 1}-01",
        "source_last_update_submit_qc_at": f"2025-0{source_version + 1}-02",
        "canonical_study": deepcopy(study),
        "canonical_content_sha256": content_hash,
        "retrieved_at": retrieved_at,
        "source_fact": True,
        "current_only": False,
        "coverage_class": "record_history_complete",
        "authority": deepcopy(AUTHORITY),
        "transaction_from": transaction_from,
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_snapshot_payload_sha256",
    }
    payload["snapshot_payload_sha256"] = canonical_json_sha256(payload)
    validate_contract(payload)
    return payload


def _history_case(before_study: dict, after_study: dict) -> tuple[dict, dict, dict]:
    before = _history_snapshot(
        before_study,
        source_version=0,
        retrieved_at="2026-08-02T00:00:02Z",
        transaction_from="2026-08-02T00:00:04Z",
    )
    after = _history_snapshot(
        after_study,
        source_version=1,
        retrieved_at="2026-08-02T00:00:03Z",
        transaction_from="2026-08-02T00:00:05Z",
    )
    diff = build_history_exact_diff(
        before, after, transaction_from=after["transaction_from"]
    )
    return before, after, diff


def _all_six_history_case() -> tuple[dict, dict, dict]:
    return _history_case(
        _study(),
        _study(
            status="COMPLETED",
            enrollment=144,
            start_date="2025-01-15",
            locations=[
                {"facility": "North Hospital", "city": "Boston"},
                {"facility": "West Hospital", "city": "Seattle"},
            ],
            outcomes=[
                {
                    "measure": "Response rate (%)",
                    "timeFrame": "16 weeks",
                    "description": "Updated formatting",
                }
            ],
            interventions=[
                {
                    "name": "X-101",
                    "type": "DRUG",
                    "description": "Revised formulation",
                }
            ],
        ),
    )


def _prospective_case() -> tuple[SourceEvidence, SourceEvidence, dict, dict, dict]:
    before_receipt = _load(
        CTGOV_FIXTURES / "source_page_receipt.before.v1.valid.json"
    )
    after_receipt = _load(CTGOV_FIXTURES / "source_page_receipt.v1.valid.json")
    before = SourceEvidence(
        run=_load(CTGOV_FIXTURES / "ctgov_fetch_run.before.v1.valid.json"),
        snapshot=_load(
            CTGOV_FIXTURES / "trial_source_snapshot.before.v1.valid.json"
        ),
        receipts=[before_receipt],
        raw_page_bodies_by_receipt={
            before_receipt["receipt_id"]: (
                CTGOV_FIXTURES / "source_page_response.before.raw.json"
            ).read_bytes()
        },
    )
    after = SourceEvidence(
        run=_load(CTGOV_FIXTURES / "ctgov_fetch_run.v1.valid.json"),
        snapshot=_load(CTGOV_FIXTURES / "trial_source_snapshot.after.v1.valid.json"),
        receipts=[after_receipt],
        raw_page_bodies_by_receipt={
            after_receipt["receipt_id"]: (
                CTGOV_FIXTURES / "source_page_response.after.raw.json"
            ).read_bytes()
        },
    )
    return (
        before,
        after,
        _load(CTGOV_FIXTURES / "trial_snapshot_observation.before.v1.valid.json"),
        _load(CTGOV_FIXTURES / "trial_snapshot_observation.after.v1.valid.json"),
        _load(CTGOV_FIXTURES / "trial_version_diff.v1.valid.json"),
    )


def _prospective_activation_proof(
    side: str,
    *,
    target_binding_sha256: str = "b" * 64,
    issued_at: datetime | None = None,
    gate_valid_until: datetime | None = None,
    checked_at: datetime | None = None,
    heartbeat_valid_until: datetime | None = None,
) -> ProspectiveActivationProof:
    if side not in {"before", "after"}:
        raise ValueError("side must be before or after")
    run_started_at = (
        BEFORE_RUN_STARTED_AT if side == "before" else AFTER_RUN_STARTED_AT
    )
    identity_character = "a" if side == "before" else "d"
    activation_id = f"r2_activation_{identity_character * 24}"
    receipt_sha256 = ("c" if side == "before" else "e") * 64
    issued_at = issued_at or run_started_at - timedelta(hours=1)
    gate_valid_until = gate_valid_until or run_started_at + timedelta(hours=1)
    checked_at = checked_at or run_started_at - timedelta(minutes=30)
    heartbeat_valid_until = heartbeat_valid_until or run_started_at + timedelta(
        minutes=30
    )
    activation = {
        "source_collection": False,
        "ledger_accrual": False,
        "public_pointer_advanced": False,
    }
    gate = {
        "contract_id": "biocatalyst_activation_gate.v1",
        "schema_version": "1.0.0",
        "activation_id": activation_id,
        "state": "ready",
        "issued_at": _timestamp(issued_at),
        "valid_until": _timestamp(gate_valid_until),
        "preflight_id": f"r2_preflight_{identity_character * 24}",
        "preflight_payload_sha256": ("1" if side == "before" else "2") * 64,
        "target_binding_sha256": target_binding_sha256,
        "receipt_key": (
            "biocatalyst/activation-preflight/"
            f"r2_preflight_{identity_character * 24}.json"
        ),
        "receipt_sha256": receipt_sha256,
        "activation": activation,
        "hash_scope": "canonical_payload_excluding_gate_payload_sha256",
    }
    _rehash(gate, "gate_payload_sha256")
    heartbeat = {
        "contract_id": "biocatalyst_activation_heartbeat.v1",
        "schema_version": "1.0.0",
        "heartbeat_id": f"r2_heartbeat_{identity_character * 24}",
        "activation_id": activation_id,
        "checked_at": _timestamp(checked_at),
        "valid_until": _timestamp(heartbeat_valid_until),
        "state": "ready",
        "target_binding_sha256": target_binding_sha256,
        "receipt_sha256": receipt_sha256,
        "activation": activation,
        "hash_scope": "canonical_payload_excluding_heartbeat_payload_sha256",
    }
    _rehash(heartbeat, "heartbeat_payload_sha256")
    return ProspectiveActivationProof(
        gate,
        heartbeat,
        activation_id,
        target_binding_sha256,
    )


def _prospective_activation_proofs() -> dict[str, ProspectiveActivationProof]:
    return {
        "before_activation_proof": _prospective_activation_proof("before"),
        "after_activation_proof": _prospective_activation_proof("after"),
    }


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rehash(document: dict, field: str) -> None:
    document.pop(field, None)
    document[field] = canonical_json_sha256(document)


def _rehash_classification(document: dict) -> None:
    scope = document.get("nct_id") or "unavailable"
    document["classification_id"] = (
        f"trial_change_classification_{scope}_"
        f"{canonical_json_sha256(change_classification._classification_identity(document))[:24]}"
    )
    _rehash(document, "classification_payload_sha256")


def test_contract_registry_finds_closed_contracts_and_synthetic_fixtures_replay() -> None:
    registry = ContractRegistry(ROOT)
    assert {
        "trial_change_classification.v1",
        "trial_change_alert_projection.v1",
    } <= set(registry.contract_ids)
    classification = _load(
        CHANGE_FIXTURES / "trial_change_classification.v1.valid.json"
    )
    projection = _load(
        CHANGE_FIXTURES / "trial_change_alert_projection.v1.valid.json"
    )
    validate_trial_change_classification(classification, repo_root=ROOT)
    validate_trial_change_alert_projection(
        projection, classification, repo_root=ROOT
    )

    before, after, before_observation, after_observation, diff = _prospective_case()
    proofs = _prospective_activation_proofs()
    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **proofs,
    )
    assert compiled.classification == classification
    assert compiled.projection == projection
    validate_prospective_trial_change_compilation(
        compiled,
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **proofs,
    )
    with pytest.raises(
        ChangeClassificationError,
        match="prospective_compilation_exact_replay_failed",
    ):
        validate_prospective_trial_change_compilation(
            compiled,
            diff,
            before,
            after,
            before_observation,
            after_observation,
        )


def test_retrospective_all_six_classes_bind_exact_operations_and_separate_clocks() -> None:
    before, after, diff = _all_six_history_case()
    compiled = compile_retrospective_trial_change(diff, before, after)

    assert compiled.classification["available"] is True
    assert {row["field_class"] for row in compiled.classification["rows"]} == {
        "registry_status",
        "enrollment",
        "milestone_date_constraint",
        "site_list",
        "intervention",
        "endpoint_record_delta",
    }
    operations = diff["operations"]
    for row in compiled.classification["rows"]:
        operation = operations[row["exact_op_index"]]
        assert row["canonical_op_sha256"] == canonical_json_sha256(operation)
        assert row["json_path"] == operation["json_path"]
        assert row["diff_ref"] == diff["diff_id"]
        assert row["diff_payload_sha256"] == diff["diff_payload_sha256"]
        assert row["nct_id"] == NCT_ID
        assert row["before_source_snapshot_ref"] == before["source_snapshot_id"]
        assert row["after_source_snapshot_ref"] == after["source_snapshot_id"]
    endpoint_rows = [
        row
        for row in compiled.classification["rows"]
        if row["field_class"] == "endpoint_record_delta"
    ]
    assert all(
        row["review_state"] == "needs_review"
        and row["semantic_resolution"] == "unresolved"
        for row in endpoint_rows
    )
    assert compiled.classification["source_clock"] == {
        "profile": "retrospective_source_versions",
        "before_source_version": 0,
        "after_source_version": 1,
        "before_retrieved_at": before["retrieved_at"],
        "after_retrieved_at": after["retrieved_at"],
        "before_transaction_from": before["transaction_from"],
        "after_transaction_from": after["transaction_from"],
    }
    assert "after" not in compiled.classification["source_clock"]
    validate_retrospective_trial_change_compilation(compiled, diff, before, after)


def test_change_tape_replays_private_history_and_strips_classifier_integrity_fields() -> None:
    before, after, _diff = _all_six_history_case()
    tape = build_trial_change_tape_read_model(
        nct_id=NCT_ID,
        history_model={"available": True},
        history_snapshots=(before, after),
        history_carried_forward=False,
        prospective_model=None,
    )

    validate_trial_change_tape_read_model(tape, nct_id=NCT_ID)
    history = tape["history"]
    assert history["available"] is True
    assert history["classification_count"] == 1
    assert history["row_count"] == len(history["rows"])
    assert all(
        set(row) == {
            "field_class", "review_state", "semantic_resolution", "op",
            "before_state", "after_state", "protocol_change_asserted",
            "materiality_assessed", "correction_assessed", "source_versions",
            "observed_at", "exact_operation_index",
        }
        for row in history["rows"]
    )
    assert all(
        not any(
            fragment in key
            for fragment in ("hash", "ref", "path", "receipt", "raw", "provenance")
        )
        for row in history["rows"]
        for key in row
    )
    assert tape["prospective"] == {
        "available": False,
        "unavailable_reason": "prospective_not_collected",
        "classification_count": 0,
        "row_count": 0,
        "rows": [],
    }


def test_change_tape_rejects_duplicate_or_unordered_sanitized_rows_and_recomputes_prospective_state() -> None:
    before, after, _diff = _all_six_history_case()
    tape = build_trial_change_tape_read_model(
        nct_id=NCT_ID,
        history_model={"available": True},
        history_snapshots=(before, after),
        history_carried_forward=False,
        prospective_model=None,
    )
    carried = build_trial_change_tape_read_model(
        nct_id=NCT_ID,
        history_model={"available": True},
        history_snapshots=(),
        history_carried_forward=True,
        carried_history_lane=tape["history"],
        prospective_model={"available": True},
    )
    assert carried["history"] == tape["history"]
    assert carried["prospective"]["unavailable_reason"] == "activation_proofs_not_retained"

    forged = deepcopy(tape)
    forged["history"]["rows"].append(deepcopy(forged["history"]["rows"][0]))
    forged["history"]["row_count"] += 1
    forged["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in forged.items() if key != "model_payload_sha256"}
    )
    with pytest.raises(ChangeTapeError, match="duplicate_row"):
        validate_trial_change_tape_read_model(forged, nct_id=NCT_ID)

    forged = deepcopy(tape)
    rows = forged["history"]["rows"]
    rows[1]["exact_operation_index"] = rows[0]["exact_operation_index"]
    forged["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in forged.items() if key != "model_payload_sha256"}
    )
    with pytest.raises(ChangeTapeError, match="operation_order"):
        validate_trial_change_tape_read_model(forged, nct_id=NCT_ID)

    forged = deepcopy(tape)
    forged["history"]["classification_count"] = 2
    forged["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in forged.items() if key != "model_payload_sha256"}
    )
    with pytest.raises(ChangeTapeError, match="classification_count"):
        validate_trial_change_tape_read_model(forged, nct_id=NCT_ID)

    forged = deepcopy(tape)
    forged["history"]["rows"][1]["observed_at"] = "2026-08-03T00:00:00Z"
    forged["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in forged.items() if key != "model_payload_sha256"}
    )
    with pytest.raises(ChangeTapeError, match="clock_invalid"):
        validate_trial_change_tape_read_model(forged, nct_id=NCT_ID)

    forged = deepcopy(tape)
    forged["history"]["rows"][0]["observed_at"] = "2026-08-02T00:00:00+00:00"
    forged["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in forged.items() if key != "model_payload_sha256"}
    )
    with pytest.raises(ChangeTapeError, match="clock_invalid"):
        validate_trial_change_tape_read_model(forged, nct_id=NCT_ID)

    forged = deepcopy(tape)
    forged["history"]["rows"] = deepcopy(forged["history"]["rows"][:2])
    forged["history"]["rows"][1]["source_versions"] = {"before": 2, "after": 3}
    forged["history"]["rows"][1]["exact_operation_index"] = 0
    forged["history"]["rows"][1]["observed_at"] = "2026-01-01T00:00:00Z"
    forged["history"]["row_count"] = 2
    forged["history"]["classification_count"] = 2
    forged["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in forged.items() if key != "model_payload_sha256"}
    )
    with pytest.raises(ChangeTapeError, match="chronology_invalid"):
        validate_trial_change_tape_read_model(forged, nct_id=NCT_ID)


def test_unselected_exact_change_is_available_with_no_rows_not_a_truncation() -> None:
    before, after, diff = _history_case(
        _study(title="Original title"), _study(title="Revised title")
    )
    compiled = compile_retrospective_trial_change(diff, before, after)
    assert compiled.classification["available"] is True
    assert compiled.classification["input_operation_count"] == 1
    assert compiled.classification["eligible_operation_count"] == 0
    assert compiled.classification["row_count"] == 0
    assert compiled.classification["rows"] == []
    assert compiled.projection["available"] is True
    assert compiled.projection["rows"] == []


def test_prospective_uses_only_first_observed_interval_and_exact_archived_evidence() -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **_prospective_activation_proofs(),
    )

    assert compiled.classification["available"] is True
    assert compiled.classification["source_clock"] == {
        "profile": "prospective_first_observed_interval",
        "after": diff["observed_interval"]["after"],
        "at_or_before": diff["observed_interval"]["at_or_before"],
    }
    assert "source_version" not in canonical_json_bytes(
        compiled.classification["source_clock"]
    ).decode()
    assert all(
        row["diff_contract_id"] == "trial_version_diff.v1"
        for row in compiled.classification["rows"]
    )


def test_prospective_activation_is_independent_of_record_history() -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    assert {"history_enabled", "retention_gate_open", "activation_proof"}.isdisjoint(
        signature(compile_prospective_trial_change).parameters
    )

    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **_prospective_activation_proofs(),
    )
    assert compiled.classification["available"] is True


def test_prospective_activation_proof_failures_are_closed_and_empty() -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    valid_before = _prospective_activation_proof("before")
    valid_after = _prospective_activation_proof("after")
    wrong_heartbeat_binding = deepcopy(valid_before.heartbeat)
    wrong_heartbeat_binding["target_binding_sha256"] = "0" * 64
    _rehash(wrong_heartbeat_binding, "heartbeat_payload_sha256")
    wrong_activation_id = deepcopy(valid_before.heartbeat)
    wrong_activation_id["activation_id"] = f"r2_activation_{'0' * 24}"
    _rehash(wrong_activation_id, "heartbeat_payload_sha256")

    cases = (
        ({}, "prospective_activation_missing"),
        ({"before_activation_proof": valid_before}, "prospective_activation_missing"),
        ({"after_activation_proof": valid_after}, "prospective_activation_missing"),
        (
            {
                "before_activation_proof": ProspectiveActivationProof(
                    None,
                    None,
                    valid_before.expected_activation_id,
                    valid_before.expected_target_binding_sha256,
                ),
                "after_activation_proof": valid_after,
            },
            "prospective_activation_missing",
        ),
        (
            {
                "before_activation_proof": ProspectiveActivationProof(
                    {"malformed": True},
                    {},
                    valid_before.expected_activation_id,
                    valid_before.expected_target_binding_sha256,
                ),
                "after_activation_proof": valid_after,
            },
            "prospective_activation_invalid",
        ),
        (
            {
                "before_activation_proof": ProspectiveActivationProof(
                    valid_before.gate,
                    valid_before.heartbeat,
                    f"r2_activation_{'0' * 24}",
                    valid_before.expected_target_binding_sha256,
                ),
                "after_activation_proof": valid_after,
            },
            "prospective_activation_invalid",
        ),
        (
            {
                "before_activation_proof": ProspectiveActivationProof(
                    valid_before.gate,
                    valid_before.heartbeat,
                    valid_before.expected_activation_id,
                    "0" * 64,
                ),
                "after_activation_proof": valid_after,
            },
            "prospective_activation_invalid",
        ),
        (
            {
                "before_activation_proof": ProspectiveActivationProof(
                    valid_before.gate,
                    wrong_heartbeat_binding,
                    valid_before.expected_activation_id,
                    valid_before.expected_target_binding_sha256,
                ),
                "after_activation_proof": valid_after,
            },
            "prospective_activation_invalid",
        ),
        (
            {
                "before_activation_proof": ProspectiveActivationProof(
                    valid_before.gate,
                    wrong_activation_id,
                    valid_before.expected_activation_id,
                    valid_before.expected_target_binding_sha256,
                ),
                "after_activation_proof": valid_after,
            },
            "prospective_activation_invalid",
        ),
        (
            {
                "before_activation_proof": valid_before,
                "after_activation_proof": _prospective_activation_proof(
                    "after", target_binding_sha256="0" * 64
                ),
            },
            "prospective_activation_invalid",
        ),
        (
            {"before_activation_proof": True, "after_activation_proof": valid_after},
            "prospective_activation_invalid",
        ),
    )
    for proof_kwargs, reason in cases:
        compiled = compile_prospective_trial_change(
            diff,
            before,
            after,
            before_observation,
            after_observation,
            **proof_kwargs,
        )
        assert compiled.classification["available"] is False
        assert compiled.classification["unavailable_reason"] == reason
        assert compiled.classification["prospective_activation_provenance"] is None
        assert compiled.classification["rows"] == []
        assert compiled.projection["rows"] == []


@pytest.mark.parametrize(
    "proof_kwargs",
    [
        {
            "before_activation_proof": _prospective_activation_proof(
                "before", issued_at=BEFORE_RUN_STARTED_AT + timedelta(seconds=1)
            ),
            "after_activation_proof": _prospective_activation_proof("after"),
        },
        {
            "before_activation_proof": _prospective_activation_proof("before"),
            "after_activation_proof": _prospective_activation_proof(
                "after", checked_at=AFTER_RUN_STARTED_AT + timedelta(seconds=1)
            ),
        },
    ],
    ids=("future_gate_issue", "future_heartbeat_check"),
)
def test_prospective_future_activation_times_are_rejected(
    proof_kwargs: dict[str, ProspectiveActivationProof],
) -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **proof_kwargs,
    )
    assert compiled.classification["available"] is False
    assert compiled.classification["unavailable_reason"] == (
        "prospective_activation_invalid"
    )


@pytest.mark.parametrize(
    ("artifact", "time_field"),
    [
        ("gate", "issued_at"),
        ("gate", "valid_until"),
        ("heartbeat", "checked_at"),
        ("heartbeat", "valid_until"),
    ],
)
def test_activation_extreme_offset_overflow_fails_empty(
    artifact: str, time_field: str
) -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    valid_before = _prospective_activation_proof("before")
    gate = deepcopy(valid_before.gate)
    heartbeat = deepcopy(valid_before.heartbeat)
    mutated = gate if artifact == "gate" else heartbeat
    mutated[time_field] = "0001-01-01T00:00:00+23:59"
    _rehash(
        mutated,
        "gate_payload_sha256"
        if artifact == "gate"
        else "heartbeat_payload_sha256",
    )
    hostile_before = ProspectiveActivationProof(
        gate,
        heartbeat,
        valid_before.expected_activation_id,
        valid_before.expected_target_binding_sha256,
    )

    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        before_activation_proof=hostile_before,
        after_activation_proof=_prospective_activation_proof("after"),
    )

    assert compiled.classification["available"] is False
    assert compiled.classification["unavailable_reason"] == (
        "prospective_activation_invalid"
    )
    assert compiled.classification["prospective_activation_provenance"] is None
    assert compiled.classification["rows"] == []
    assert compiled.projection["rows"] == []


def test_gate_issued_at_run_start_is_accepted_and_activation_ids_may_rotate() -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    proofs = {
        "before_activation_proof": _prospective_activation_proof(
            "before",
            issued_at=BEFORE_RUN_STARTED_AT,
            checked_at=BEFORE_RUN_STARTED_AT,
        ),
        "after_activation_proof": _prospective_activation_proof("after"),
    }
    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **proofs,
    )
    assert compiled.classification["available"] is True
    provenance = compiled.classification["prospective_activation_provenance"]
    assert [entry["side"] for entry in provenance] == ["before", "after"]
    assert [entry["run_ref"] for entry in provenance] == [
        before.run["run_id"],
        after.run["run_id"],
    ]
    assert [entry["evaluated_at"] for entry in provenance] == [
        before.run["started_at"],
        after.run["started_at"],
    ]
    assert provenance[0]["activation_id"] != provenance[1]["activation_id"]
    assert provenance[0]["target_binding_sha256"] == provenance[1][
        "target_binding_sha256"
    ]


@pytest.mark.parametrize("lease", ["gate", "heartbeat"])
def test_activation_valid_until_equal_run_start_is_stale(lease: str) -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    kwargs: dict[str, datetime] = {
        f"{lease}_valid_until": BEFORE_RUN_STARTED_AT
    }
    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        before_activation_proof=_prospective_activation_proof("before", **kwargs),
        after_activation_proof=_prospective_activation_proof("after"),
    )
    assert compiled.classification["available"] is False
    assert compiled.classification["unavailable_reason"] == (
        "prospective_activation_stale"
    )


def test_proof_mutation_changes_classification_identity_digest_and_exact_replay() -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    baseline_proofs = _prospective_activation_proofs()
    baseline = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **baseline_proofs,
    )
    mutated_proofs = {
        **baseline_proofs,
        "before_activation_proof": _prospective_activation_proof(
            "before", issued_at=BEFORE_RUN_STARTED_AT - timedelta(minutes=45)
        ),
    }
    mutated = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **mutated_proofs,
    )
    assert mutated.classification["available"] is True
    assert mutated.classification["classification_id"] != baseline.classification[
        "classification_id"
    ]
    assert mutated.classification["classification_payload_sha256"] != baseline.classification[
        "classification_payload_sha256"
    ]
    with pytest.raises(
        ChangeClassificationError,
        match="prospective_compilation_exact_replay_failed",
    ):
        validate_prospective_trial_change_compilation(
            baseline,
            diff,
            before,
            after,
            before_observation,
            after_observation,
            **mutated_proofs,
        )


@pytest.mark.parametrize("target", ["diff_hash", "op", "path", "snapshot_hash", "cross_nct"])
def test_tampered_retrospective_evidence_fails_empty(target: str) -> None:
    before, after, diff = _all_six_history_case()
    before = deepcopy(before)
    after = deepcopy(after)
    diff = deepcopy(diff)
    if target == "diff_hash":
        diff["diff_payload_sha256"] = "0" * 64
    elif target == "op":
        diff["operations"][0]["after_value"] = "forged"
        _rehash(diff, "diff_payload_sha256")
    elif target == "path":
        diff["operations"][0]["json_path"] += "Evil"
        _rehash(diff, "diff_payload_sha256")
    elif target == "snapshot_hash":
        after["canonical_content_sha256"] = "0" * 64
        _rehash(after, "snapshot_payload_sha256")
    else:
        after["nct_id"] = "NCT99999999"
        _rehash(after, "snapshot_payload_sha256")

    compiled = compile_retrospective_trial_change(diff, before, after)
    assert compiled.classification["available"] is False
    assert compiled.classification["unavailable_reason"] == "evidence_replay_failed"
    assert compiled.classification["rows"] == []
    assert compiled.projection["rows"] == []


@pytest.mark.parametrize("target", ["observations", "runs", "receipts", "raw"])
def test_swapped_or_tampered_prospective_evidence_fails_empty(target: str) -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    if target == "observations":
        before_observation, after_observation = after_observation, before_observation
    elif target == "runs":
        before = SourceEvidence(
            after.run,
            before.snapshot,
            before.receipts,
            before.raw_page_bodies_by_receipt,
        )
    elif target == "receipts":
        before = SourceEvidence(
            before.run,
            before.snapshot,
            after.receipts,
            after.raw_page_bodies_by_receipt,
        )
    else:
        key = next(iter(before.raw_page_bodies_by_receipt))
        before = SourceEvidence(
            before.run,
            before.snapshot,
            before.receipts,
            {key: before.raw_page_bodies_by_receipt[key] + b" "},
        )

    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **_prospective_activation_proofs(),
    )
    assert compiled.classification["available"] is False
    assert compiled.classification["unavailable_reason"] == "evidence_replay_failed"
    assert compiled.classification["rows"] == []


@pytest.mark.parametrize(
    "interval",
    [
        {"after": "2026-08-02T00:00:00Z", "at_or_before": "2026-08-01T00:00:00Z"},
        {"after": "2026-08-01T00:00:00Z", "at_or_before": "2026-08-01T00:00:00Z"},
        {"after": "999999999999-01-01T00:00:00Z", "at_or_before": "2026-08-01T00:00:00Z"},
        {"after": "2026-08-01T00:00:00+99:99", "at_or_before": "2026-08-02T00:00:00Z"},
    ],
)
def test_cross_clock_inversion_equality_and_offset_overflow_fail_empty(
    interval: dict,
) -> None:
    before, after, before_observation, after_observation, diff = _prospective_case()
    diff["observed_interval"] = interval
    _rehash(diff, "diff_payload_sha256")
    compiled = compile_prospective_trial_change(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        **_prospective_activation_proofs(),
    )
    assert compiled.classification["available"] is False
    assert compiled.classification["unavailable_reason"] == "evidence_replay_failed"


def test_endpoint_reorder_formatting_and_ambiguous_candidates_stay_unresolved() -> None:
    before_outcomes = [
        {
            "measure": "Objective response rate cohort A",
            "timeFrame": "12 weeks",
            "description": "Central review",
        },
        {
            "measure": "Objective response rate cohort B",
            "timeFrame": "12 weeks",
            "description": "Central review",
        },
    ]
    after_outcomes = [
        {
            "measure": "Objective response rate cohort B (%)",
            "timeFrame": "12 weeks",
            "description": "Central review",
        },
        {
            "measure": "Objective response rate cohort A (%)",
            "timeFrame": "12 weeks",
            "description": "Central review",
        },
    ]
    before, after, diff = _history_case(
        _study(outcomes=before_outcomes), _study(outcomes=after_outcomes)
    )
    candidates = build_trial_endpoint_alignment_review_projection(before, after, diff)
    compiled = compile_retrospective_trial_change(diff, before, after)

    assert candidates["candidate_count"] >= 2
    endpoint_rows = [
        row
        for row in compiled.classification["rows"]
        if row["field_class"] == "endpoint_record_delta"
    ]
    assert endpoint_rows
    assert all(row["review_state"] == "needs_review" for row in endpoint_rows)
    assert all(row["semantic_resolution"] == "unresolved" for row in endpoint_rows)
    assert "candidate_id" not in canonical_json_bytes(compiled.classification).decode()


def test_source_reversal_never_becomes_a_correction_label() -> None:
    initial = _study(status="RECRUITING", enrollment=100)
    changed = _study(status="COMPLETED", enrollment=144)
    forward = _history_case(initial, changed)
    reversed_case = _history_case(changed, initial)

    for before, after, diff in (forward, reversed_case):
        compiled = compile_retrospective_trial_change(diff, before, after)
        assert compiled.classification["available"] is True
        assert compiled.classification["correction_assessed"] is False
        assert compiled.projection["correction_assessed"] is False
        assert all(row["correction_assessed"] is False for row in compiled.projection["rows"])
        serialized = canonical_json_bytes(compiled.projection).decode()
        assert '"correction":' not in serialized


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"history_enabled": False}, "history_disabled"),
        ({"retention_gate_open": False}, "retention_gate_closed"),
        ({"history_enabled": 1}, "schema_profile_mismatch"),
    ],
)
def test_disabled_gated_and_bool_as_int_flags_fail_empty(
    kwargs: dict, reason: str
) -> None:
    compiled = compile_retrospective_trial_change(None, None, None, **kwargs)
    assert compiled.classification["available"] is False
    assert compiled.classification["unavailable_reason"] == reason
    assert compiled.classification["nct_id"] is None
    assert compiled.classification["diff_ref"] is None
    assert compiled.classification["rows"] == []
    assert compiled.projection["rows"] == []


def test_missing_evidence_and_profile_mismatch_fail_empty() -> None:
    before, after, diff = _all_six_history_case()
    assert compile_retrospective_trial_change(diff, None, after).classification[
        "unavailable_reason"
    ] == "missing_evidence"

    prospective = _prospective_case()
    assert compile_retrospective_trial_change(
        prospective[4], before, after
    ).classification["unavailable_reason"] == "schema_profile_mismatch"
    assert compile_prospective_trial_change(
        diff,
        prospective[0],
        prospective[1],
        prospective[2],
        prospective[3],
        **_prospective_activation_proofs(),
    ).classification["unavailable_reason"] == "schema_profile_mismatch"


@pytest.mark.parametrize("forgery", ["path", "op", "op_hash", "index", "count", "order"])
def test_replay_validator_rejects_one_field_row_and_projection_forgery(
    forgery: str,
) -> None:
    before, after, diff = _all_six_history_case()
    compiled = compile_retrospective_trial_change(diff, before, after)
    forged_classification = deepcopy(compiled.classification)
    rows = forged_classification["rows"]
    if forgery == "path":
        rows[0]["json_path"] += "/forged"
    elif forgery == "op":
        rows[0]["op"] = "add"
    elif forgery == "op_hash":
        rows[0]["canonical_op_sha256"] = "0" * 64
    elif forgery == "index":
        rows[0]["exact_op_index"] += 1
    elif forgery == "count":
        forged_classification["input_operation_count"] -= 1
    else:
        rows.reverse()
    for row in rows:
        row["row_id"] = (
            f"trial_change_row_{row['nct_id']}_"
            f"{canonical_json_sha256(change_classification._row_identity(row))[:24]}"
        )
        _rehash(row, "row_payload_sha256")
    _rehash_classification(forged_classification)
    forged = TrialChangeCompilation(
        forged_classification,
        change_classification._build_projection(forged_classification),
    )

    with pytest.raises(ChangeClassificationError, match="exact_replay_failed"):
        validate_retrospective_trial_change_compilation(forged, diff, before, after)


def test_projection_consumer_validator_requires_exact_classification_pairing() -> None:
    before, after, diff = _all_six_history_case()
    compiled = compile_retrospective_trial_change(diff, before, after)
    forged = deepcopy(compiled.projection)
    forged["classification_ref"] = (
        f"trial_change_classification_{NCT_ID}_" + "f" * 24
    )
    forged["projection_id"] = (
        f"trial_change_alert_projection_{NCT_ID}_"
        f"{canonical_json_sha256(change_classification._projection_identity(forged))[:24]}"
    )
    _rehash(forged, "projection_payload_sha256")

    validate_contract(forged)
    with pytest.raises(
        ContractValidationError,
        match="trial_change_alert_projection.classification_binding",
    ):
        validate_trial_change_alert_projection(forged, compiled.classification)
    with pytest.raises(TypeError):
        validate_trial_change_alert_projection(forged)  # type: ignore[call-arg]


def test_permutation_determinism_toctou_freeze_and_mutation_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after, diff = _all_six_history_case()
    baseline = compile_retrospective_trial_change(diff, before, after)
    reordered = compile_retrospective_trial_change(
        dict(reversed(tuple(diff.items()))),
        dict(reversed(tuple(before.items()))),
        dict(reversed(tuple(after.items()))),
    )
    assert reordered == baseline

    caller_diff = deepcopy(diff)
    original_replay = change_classification.validate_trial_history_diff_against_snapshots

    def mutate_caller_then_replay(
        frozen_diff: dict, frozen_before: dict, frozen_after: dict
    ) -> None:
        caller_diff["operations"][0]["json_path"] = "/caller/mutated"
        original_replay(frozen_diff, frozen_before, frozen_after)

    monkeypatch.setattr(
        change_classification,
        "validate_trial_history_diff_against_snapshots",
        mutate_caller_then_replay,
    )
    raced = compile_retrospective_trial_change(caller_diff, before, after)
    assert raced == baseline
    before["canonical_study"].clear()
    after["canonical_study"].clear()
    caller_diff.clear()
    assert raced == baseline
    with pytest.raises(FrozenInstanceError):
        raced.classification = {}  # type: ignore[misc]


@pytest.mark.parametrize(
    ("hostile", "expected_reason"),
    [
        (float("nan"), "must_be_canonical_json"),
        (float("inf"), "must_be_canonical_json"),
        ("\ud800", "must_be_canonical_json"),
        (10 ** 10000, "canonical_byte_limit_exceeded"),
    ],
    ids=("nan", "infinity", "surrogate", "huge_integer"),
)
def test_nonfinite_surrogate_and_huge_integer_preflight(
    hostile: object, expected_reason: str
) -> None:
    frozen, reason = change_classification._freeze_json_input(
        hostile, max_canonical_bytes=256
    )
    assert frozen is None
    assert reason == expected_reason


def test_exact_decoded_byte_node_depth_and_container_cap_boundaries() -> None:
    limit = 64
    frozen, reason = change_classification._freeze_json_input(
        "x" * (limit - 2), max_canonical_bytes=limit
    )
    assert frozen == "x" * (limit - 2)
    assert reason is None
    assert change_classification._freeze_json_input(
        "x" * (limit - 1), max_canonical_bytes=limit
    )[1] == "canonical_byte_limit_exceeded"

    exact_nodes = [None, None]
    assert change_classification._freeze_json_input(exact_nodes, max_nodes=3)[1] is None
    assert change_classification._freeze_json_input(exact_nodes, max_nodes=2)[1] == (
        "node_limit_exceeded"
    )
    assert change_classification._freeze_json_input(
        [None, None], max_container_items=2
    )[1] is None
    assert change_classification._freeze_json_input(
        [None, None, None], max_container_items=2
    )[1] == "container_limit_exceeded"

    nested: object = "leaf"
    for _ in range(128):
        nested = [nested]
    assert change_classification._freeze_json_input(
        nested, max_nesting_depth=128
    )[1] is None
    nested = [nested]
    assert change_classification._freeze_json_input(
        nested, max_nesting_depth=128
    )[1] == "nesting_limit_exceeded"


def test_cycles_and_custom_containers_fail_without_recursion_leak() -> None:
    cycle: dict = {}
    cycle["self"] = cycle
    assert change_classification._freeze_json_input(cycle)[1] == (
        "nesting_limit_exceeded"
    )

    class CustomDict(dict):
        pass

    assert change_classification._freeze_json_input(CustomDict(a=1))[1] == (
        "must_be_canonical_json"
    )


def test_preflight_rejection_never_replays_or_canonicalizes_hostile_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after, diff = _all_six_history_case()
    hostile = deepcopy(before)
    hostile["canonical_study"]["hostile"] = "x" * (
        change_classification._MAX_INPUT_DOCUMENT_BYTES + 1
    )
    sentinel = compile_retrospective_trial_change(None, None, None, history_enabled=False)
    reached = {"canonical": 0, "hash": 0, "replay": 0}

    def forbidden(stage: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            reached[stage] += 1
            raise AssertionError(f"{stage} must not run on rejected hostile evidence")

        return fail

    monkeypatch.setattr(change_classification, "canonical_json_bytes", forbidden("canonical"))
    monkeypatch.setattr(change_classification, "canonical_json_sha256", forbidden("hash"))
    monkeypatch.setattr(
        change_classification,
        "validate_trial_history_diff_against_snapshots",
        forbidden("replay"),
    )
    monkeypatch.setattr(
        change_classification, "_build_unavailable", lambda _reason: sentinel
    )

    assert compile_retrospective_trial_change(diff, hostile, after) is sentinel
    assert reached == {"canonical": 0, "hash": 0, "replay": 0}


def test_raw_body_and_descriptor_key_caps_are_exact_boundary_plus_one() -> None:
    raw_limit = change_classification._MAX_RAW_BYTES_PER_SIDE
    frozen, reason = change_classification._freeze_raw_evidence(
        "before", {"receipt": b"x" * raw_limit}
    )
    assert reason is None
    assert frozen == {"receipt": b"x" * raw_limit}
    assert change_classification._freeze_raw_evidence(
        "before", {"receipt": b"x" * (raw_limit + 1)}
    )[1] == "input_before_raw_bytes_limit_exceeded"

    key_limit = change_classification._MAX_RAW_DESCRIPTOR_KEY_BYTES
    exact_key = "k" * (key_limit - 2)
    one_over_key = exact_key + "k"
    assert change_classification._freeze_raw_evidence(
        "before", {exact_key: b""}
    )[1] is None
    assert change_classification._freeze_raw_evidence(
        "before", {one_over_key: b""}
    )[1] == "input_before_raw_key_bytes_limit_exceeded"

    released = memoryview(b"raw")
    released.release()
    assert change_classification._freeze_raw_evidence(
        "before", {"receipt": released}
    )[1] == "input_before_raw_evidence_invalid"


def test_operation_and_output_caps_fail_empty_without_partial_truncation() -> None:
    before, after, diff = _all_six_history_case()
    skeleton = deepcopy(diff)
    skeleton["operations"] = [
        {
            "op": "replace",
            "json_path": f"/unselected/{index:04d}",
            "change_family": "other",
            "before_state": "present",
            "before_value": 0,
            "after_state": "present",
            "after_value": 1,
        }
        for index in range(change_classification._MAX_OPERATIONS)
    ]
    exact = change_classification._build_available(
        evidence_profile="retrospective_record_history",
        diff=skeleton,
        before_snapshot=before,
        after_snapshot=after,
        source_clock={
            "profile": "retrospective_source_versions",
            "before_source_version": 0,
            "after_source_version": 1,
            "before_retrieved_at": before["retrieved_at"],
            "after_retrieved_at": after["retrieved_at"],
            "before_transaction_from": before["transaction_from"],
            "after_transaction_from": after["transaction_from"],
        },
    )
    assert exact.classification["available"] is True
    assert exact.classification["input_operation_count"] == 4096
    skeleton["operations"].append(deepcopy(skeleton["operations"][-1]))
    one_over = change_classification._build_available(
        evidence_profile="retrospective_record_history",
        diff=skeleton,
        before_snapshot=before,
        after_snapshot=after,
        source_clock=exact.classification["source_clock"],
    )
    assert one_over.classification["unavailable_reason"] == (
        "operation_count_limit_exceeded"
    )
    assert one_over.classification["rows"] == []

    wide = deepcopy(diff)
    wide["operations"] = [
        {
            "op": "replace",
            "json_path": (
                "/protocolSection/designModule/enrollmentInfo/"
                + f"field_{index:04d}_"
                + "x" * 1800
            ),
            "change_family": "enrollment",
            "before_state": "present",
            "before_value": 0,
            "after_state": "present",
            "after_value": 1,
        }
        for index in range(700)
    ]
    over_output = change_classification._build_available(
        evidence_profile="retrospective_record_history",
        diff=wide,
        before_snapshot=before,
        after_snapshot=after,
        source_clock=exact.classification["source_clock"],
    )
    assert over_output.classification["available"] is False
    assert over_output.classification["unavailable_reason"] in {
        "classification_byte_limit_exceeded",
        "projection_byte_limit_exceeded",
    }
    assert over_output.classification["rows"] == []
    assert over_output.projection["rows"] == []


def test_generic_contract_preflight_enforces_exact_byte_node_depth_and_container_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = 1024 * 1024
    base_size = len(canonical_json_bytes({"padding": ""}))
    exact = {"padding": "x" * (limit - base_size)}
    one_over = {"padding": exact["padding"] + "x"}
    assert sector_contracts._trial_change_envelope_issues(
        "trial_change_classification.v1", exact
    ) == []
    assert sector_contracts._trial_change_envelope_issues(
        "trial_change_classification.v1", one_over
    )[0].code == "trial_change_classification.byte_limit"

    too_many_nodes = {"hostile": [[None] * 32 for _ in range(2048)]}
    assert sector_contracts._trial_change_envelope_issues(
        "trial_change_classification.v1", too_many_nodes
    )[0].code == "trial_change_classification.node_limit"
    too_deep: object = "leaf"
    for _ in range(129):
        too_deep = [too_deep]
    assert sector_contracts._trial_change_envelope_issues(
        "trial_change_alert_projection.v1", {"hostile": too_deep}
    )[0].code == "trial_change_alert_projection.nesting_limit"
    assert sector_contracts._trial_change_envelope_issues(
        "trial_change_alert_projection.v1", {"hostile": [None] * 16_385}
    )[0].code == "trial_change_alert_projection.container_limit"

    reached = 0

    def forbidden_hash(*_args: object, **_kwargs: object) -> None:
        nonlocal reached
        reached += 1
        raise AssertionError("semantic hashing must not run after envelope refusal")

    monkeypatch.setattr(sector_contracts, "_content_hash_issue", forbidden_hash)
    issues = ContractRegistry(ROOT).issues(
        "trial_change_classification.v1", one_over
    )
    assert issues[0].code == "trial_change_classification.byte_limit"
    assert reached == 0


def test_non_packet_ctgov_extreme_offset_overflow_is_bounded_validation() -> None:
    run = _load(CTGOV_FIXTURES / "ctgov_fetch_run.v1.valid.json")
    run["started_at"] = "0001-01-01T00:00:00+23:59"

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(run, repo_root=ROOT)

    assert any(
        issue.code == "schema.invalid_in_memory_document"
        for issue in caught.value.issues
    )


def test_lookalike_json_path_segments_cannot_spoof_a_closed_field_class() -> None:
    lookalikes = (
        "/protocolSection/designModule/enrollmentInfoEvil/count",
        "/protocolSection/statusModule/startDateStructEvil/date",
        "/protocolSection/contactsLocationsModule/locationsEvil",
        "/protocolSection/armsInterventionsModule/interventionsEvil",
        "/protocolSection/outcomesModule/primaryOutcomesEvil",
    )
    assert all(change_classification._field_class(path) is None for path in lookalikes)


def test_no_authority_identity_ranking_or_delivery_leakage() -> None:
    before, after, diff = _all_six_history_case()
    compiled = compile_retrospective_trial_change(diff, before, after)
    projection = compiled.projection
    assert projection["tenant_scope"] == "tenant_neutral"
    assert projection["canonical_alert"] is False
    assert projection["delivery_eligible"] is False
    assert projection["protocol_change_asserted"] is False
    assert projection["materiality_assessed"] is False
    assert projection["correction_assessed"] is False
    assert projection["review_decision_refs"] == []

    banned_keys = {
        "rank",
        "ranking",
        "priority",
        "score",
        "confidence",
        "issuer",
        "security",
        "asset",
        "ticker",
    }

    def keys(value: object) -> set[str]:
        found: set[str] = set()
        stack = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                found.update(current)
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
        return found

    assert not (banned_keys & keys(compiled.classification))
    assert not (banned_keys & keys(compiled.projection))
    forged = deepcopy(projection)
    forged["priority"] = 1
    with pytest.raises(ContractValidationError):
        validate_trial_change_alert_projection(forged, compiled.classification)


def test_retrospective_boundary_is_snapshot_replay_not_a_raw_history_claim() -> None:
    source = (
        ROOT / "engine" / "biocatalyst" / "change_classification.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "compile_retrospective_trial_change"
    )
    parameter_names = {argument.arg for argument in function.args.args}
    assert parameter_names == {"diff", "before_snapshot", "after_snapshot"}
    assert "does not claim to\nrevalidate the earlier history run" in source
    assert "validate_trial_history_diff_against_snapshots" in source


def test_backend_compiler_has_no_io_public_model_or_authority_plane_imports() -> None:
    source = (
        ROOT / "engine" / "biocatalyst" / "change_classification.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert not any(
        name.startswith(("app", "requests", "boto3", "engine.neuralweb"))
        for name in imported
    )
    assert not ({"open", "read_text", "read_bytes", "write_text", "write_bytes"} & calls)
    assert "trial_history_read_model.v1" not in source
    assert "trial_prospective_change_read_model.v1" not in source
    assert "publication" not in source
    assert "prophet" not in {name.casefold() for name in imported}
