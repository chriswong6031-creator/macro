from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from engine.biocatalyst.history import (
    HistoryError,
    build_history_exact_diff,
    build_history_read_model,
    build_history_receipt,
    build_history_run,
    build_history_source_snapshot,
    build_unavailable_history_read_model,
    derive_history_change_facts,
)
from engine.sector_intelligence import (
    canonical_json_sha256,
    validate_contract,
    validate_ctgov_history_receipt_against_raw_response,
    validate_ctgov_history_run_against_receipts,
    validate_trial_history_diff_against_snapshots,
    validate_trial_history_read_model,
    validate_trial_history_snapshot_against_evidence,
    validate_trial_registry_change_fact_against_diff,
)
from engine.sector_intelligence.contracts import ContractValidationError


NCT_ID = "NCT01234567"
RUN_ID = "ctgov_history_run_NCT01234567_fixture"
RECEIVED_AT = "2026-08-02T00:00:00Z"


def _study(
    *,
    status: str = "RECRUITING",
    enrollment: int = 100,
    start_date: str = "2025-01-01",
    primary_completion_date: str = "2025-09-01",
    completion_date: str = "2025-12-01",
    sponsor: str = "Acme Bio",
    locations: list[dict[str, str]] | None = None,
    outcomes: list[dict[str, str]] | None = None,
    other_outcomes: list[dict[str, str]] | None = None,
    interventions: list[dict[str, str]] | None = None,
) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": NCT_ID},
            "statusModule": {
                "overallStatus": status,
                "startDateStruct": {"date": start_date, "type": "ACTUAL"},
                "primaryCompletionDateStruct": {
                    "date": primary_completion_date,
                    "type": "ESTIMATED",
                },
                "completionDateStruct": {
                    "date": completion_date,
                    "type": "ESTIMATED",
                },
            },
            "designModule": {"enrollmentInfo": {"count": enrollment, "type": "ESTIMATED"}},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor, "class": "INDUSTRY"}},
            "contactsLocationsModule": {
                "locations": locations or [{"facility": "North Hospital", "city": "Boston"}]
            },
            "outcomesModule": {
                "primaryOutcomes": outcomes
                or [{"measure": "Response rate", "timeFrame": "12 weeks", "description": "Baseline"}],
                "secondaryOutcomes": [],
                "otherOutcomes": other_outcomes or [],
            },
            "armsInterventionsModule": {
                "interventions": interventions
                or [{"name": "X-101", "type": "DRUG", "description": "Initial formulation"}]
            },
        }
    }


def _raw_json(payload: dict, *, trailing_newline: bool = False) -> bytes:
    return (
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        + (b"\n" if trailing_newline else b"")
    )


def _rehash(document: dict, field: str) -> None:
    document.pop(field, None)
    document[field] = canonical_json_sha256(document)


def _history_evidence_chain(
    before_study: dict | None = None, after_study: dict | None = None
) -> tuple[dict, dict, dict, list[dict], list[dict], dict[str, bytes]]:
    before = before_study or _study()
    after = after_study or _study(status="COMPLETED")
    manifest = [
        {
            "source_version": version,
            "display_version": version + 1,
            "source_submitted_at": f"2025-0{version + 1}-01",
            "source_last_update_submit_qc_at": f"2025-0{version + 1}-02",
            "module_labels": ["Study Status"],
        }
        for version in (0, 1)
    ]
    index_payload = {
        "study": after,
        "history": {
            "changes": [
                {
                    "version": entry["source_version"],
                    "date": entry["source_submitted_at"],
                    "lastUpdateSubmitQcDate": entry["source_last_update_submit_qc_at"],
                    "moduleLabels": entry["module_labels"],
                    "status": "RECRUITING",
                    "studyType": "INTERVENTIONAL",
                }
                for entry in manifest
            ]
        },
    }
    index_raw = _raw_json(index_payload)
    index_post_raw = _raw_json(index_payload, trailing_newline=True)
    index_receipt = build_history_receipt(
        run_id=RUN_ID,
        nct_id=NCT_ID,
        resource_kind="history_index",
        source_version=None,
        raw_response=index_raw,
        received_at=RECEIVED_AT,
        transaction_from="2026-08-02T00:00:01Z",
        receipt_suffix="index_pre",
    )
    index_post_receipt = build_history_receipt(
        run_id=RUN_ID,
        nct_id=NCT_ID,
        resource_kind="history_index",
        source_version=None,
        raw_response=index_post_raw,
        received_at="2026-08-02T00:00:08Z",
        transaction_from="2026-08-02T00:00:09Z",
        receipt_suffix="index_post",
    )
    version_raw_bodies = [
        _raw_json({"studyVersion": version, "study": study})
        for version, study in enumerate((before, after))
    ]
    version_receipts = [
        build_history_receipt(
            run_id=RUN_ID,
            nct_id=NCT_ID,
            resource_kind="history_version",
            source_version=version,
            raw_response=version_raw_bodies[version],
            received_at=f"2026-08-02T00:00:0{version + 2}Z",
            transaction_from=f"2026-08-02T00:00:0{2 * version + 3}Z",
        )
        for version in (0, 1)
    ]
    raw_bodies_by_receipt = {
        index_receipt["receipt_id"]: index_raw,
        index_post_receipt["receipt_id"]: index_post_raw,
        **{
            receipt["receipt_id"]: raw_body
            for receipt, raw_body in zip(version_receipts, version_raw_bodies, strict=True)
        },
    }
    run = build_history_run(
        run_id=RUN_ID,
        nct_id=NCT_ID,
        index_receipt=index_receipt,
        index_post_receipt=index_post_receipt,
        version_receipts=version_receipts,
        version_manifest=manifest,
        raw_bodies_by_receipt=raw_bodies_by_receipt,
        started_at="2026-08-01T23:59:59Z",
        finished_at="2026-08-02T00:00:09Z",
        transaction_from="2026-08-02T00:00:11Z",
    )
    validate_ctgov_history_run_against_receipts(
        run,
        index_receipt,
        index_post_receipt,
        version_receipts,
        raw_bodies_by_receipt=raw_bodies_by_receipt,
    )
    snapshots = [
        build_history_source_snapshot(
            run=run,
            index_receipt=index_receipt,
            index_post_receipt=index_post_receipt,
            version_receipt=receipt,
            all_version_receipts=version_receipts,
            raw_bodies_by_receipt=raw_bodies_by_receipt,
            canonical_study=study,
            transaction_from="2026-08-02T00:00:12Z",
        )
        for receipt, study in zip(
            version_receipts,
            [before_study or _study(), after_study or _study(status="COMPLETED")],
            strict=True,
        )
    ]
    for snapshot, receipt in zip(snapshots, version_receipts, strict=True):
        validate_trial_history_snapshot_against_evidence(
            snapshot,
            run,
            index_receipt,
            index_post_receipt,
            receipt,
            all_version_receipts=version_receipts,
            raw_bodies_by_receipt=raw_bodies_by_receipt,
        )
    return (
        run,
        index_receipt,
        index_post_receipt,
        version_receipts,
        snapshots,
        raw_bodies_by_receipt,
    )


def _history_chain(
    before_study: dict | None = None, after_study: dict | None = None
) -> tuple[dict, list[dict], list[dict]]:
    run, _index_pre, _index_post, receipts, snapshots, _raw_bodies = _history_evidence_chain(
        before_study, after_study
    )
    return run, receipts, snapshots


def test_complete_history_chain_builds_replayable_decision_inert_facts_and_private_safe_model() -> None:
    before = _study()
    after = _study(
        status="COMPLETED",
        enrollment=150,
        start_date="2025-01-03",
        primary_completion_date="2025-09-15",
        completion_date="2026-01-15",
        sponsor="Acme Bio Therapeutics",
        locations=[
            {"facility": "North Hospital", "city": "Boston"},
            {"facility": "West Hospital", "city": "Seattle"},
        ],
        outcomes=[
            {"measure": "Response rate (%)", "timeFrame": "12 weeks", "description": "Updated"}
        ],
        interventions=[{"name": "X-101", "type": "DRUG", "description": "Revised formulation"}],
    )
    _, _, snapshots = _history_chain(before, after)

    diff = build_history_exact_diff(*snapshots, transaction_from=snapshots[1]["transaction_from"])
    validate_trial_history_diff_against_snapshots(diff, *snapshots)
    facts = derive_history_change_facts(*snapshots, diff)
    kinds = [fact["kind"] for fact in facts]

    assert {
        "registry_status_changed",
        "enrollment_changed",
        "study_date_changed",
        "lead_sponsor_text_changed",
        "site_listing_changed",
        "endpoint_measure_changed",
        "endpoint_description_changed",
        "intervention_changed",
    } <= set(kinds)
    assert kinds.count("study_date_changed") == 3
    for fact in facts:
        assert fact["source_fact"] is True
        assert fact["current_only"] is False
        assert fact["authority"]["decision_authority"] is False
        assert fact["interpretation"] == "registry_record_changed"
        assert fact["protocol_change_asserted"] is False
        assert fact["materiality_assessed"] is False

    model = build_history_read_model(snapshots, facts, generated_at="2026-08-02T00:00:14Z")
    validate_trial_history_read_model(model, snapshots, facts)
    assert model["available"] is True
    assert model["coverage_class"] == "record_history_complete"
    assert model["current_only"] is False
    assert len(model["versions"]) == 2
    assert model["authority"]["decision_authority"] is False
    serialized = str(model)
    for private_key in ("receipt_ref", "source_snapshot_ref", "raw_object_key", "diff_ref", "fact_ref"):
        assert private_key not in serialized


def test_history_exact_diff_replay_rejects_a_rehashed_fabrication() -> None:
    _, _, snapshots = _history_chain()
    diff = build_history_exact_diff(*snapshots, transaction_from=snapshots[1]["transaction_from"])
    tampered = deepcopy(diff)
    tampered["operations"][0]["after_value"] = "fabricated registry value"
    del tampered["diff_payload_sha256"]
    tampered["diff_payload_sha256"] = canonical_json_sha256(tampered)

    with pytest.raises(ContractValidationError, match="history_diff.exactness"):
        validate_trial_history_diff_against_snapshots(tampered, *snapshots)

    forged_id = deepcopy(diff)
    forged_id["diff_id"] = f"{diff['diff_id'].rsplit('_', 1)[0]}_{'f' * 24}"
    _rehash(forged_id, "diff_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_diff.deterministic_id"):
        validate_trial_history_diff_against_snapshots(forged_id, *snapshots)

    forged_time = deepcopy(diff)
    forged_time["transaction_from"] = "2026-08-02T00:00:13Z"
    _rehash(forged_time, "diff_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_diff.snapshot_binding"):
        validate_trial_history_diff_against_snapshots(forged_time, *snapshots)


def test_history_change_fact_replay_rejects_rehashed_value_or_kind_forgery() -> None:
    before = _study(status="RECRUITING", enrollment=100)
    after = _study(status="COMPLETED", enrollment=150)
    _run, _receipts, snapshots = _history_chain(before, after)
    diff = build_history_exact_diff(*snapshots, transaction_from=snapshots[1]["transaction_from"])
    facts = derive_history_change_facts(*snapshots, diff)
    status_fact = next(fact for fact in facts if fact["kind"] == "registry_status_changed")

    forged_value = deepcopy(status_fact)
    forged_value["after_value"] = "WITHDRAWN"
    _rehash(forged_value, "fact_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_change_fact.semantic_replay"):
        validate_trial_registry_change_fact_against_diff(
            forged_value, diff, *snapshots
        )

    forged_kind = deepcopy(status_fact)
    forged_kind["kind"] = "enrollment_changed"
    _rehash(forged_kind, "fact_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_change_fact.semantic_replay"):
        validate_trial_registry_change_fact_against_diff(
            forged_kind, diff, *snapshots
        )

    forged_id = deepcopy(status_fact)
    forged_id["change_fact_id"] = f"{status_fact['change_fact_id'].rsplit('_', 1)[0]}_{'f' * 24}"
    _rehash(forged_id, "fact_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_change_fact.deterministic_id"):
        validate_trial_registry_change_fact_against_diff(
            forged_id, diff, *snapshots
        )


def test_history_artifacts_are_deterministic_for_identical_complete_evidence() -> None:
    _, _, first_snapshots = _history_chain()
    _, _, second_snapshots = _history_chain()

    first_diff = build_history_exact_diff(
        *first_snapshots, transaction_from=first_snapshots[1]["transaction_from"]
    )
    second_diff = build_history_exact_diff(
        *second_snapshots, transaction_from=second_snapshots[1]["transaction_from"]
    )
    first_facts = derive_history_change_facts(*first_snapshots, first_diff)
    second_facts = derive_history_change_facts(*second_snapshots, second_diff)
    first_model = build_history_read_model(
        first_snapshots, first_facts, generated_at="2026-08-02T00:00:14Z"
    )
    second_model = build_history_read_model(
        second_snapshots, second_facts, generated_at="2026-08-02T00:00:14Z"
    )

    assert first_snapshots == second_snapshots
    assert first_diff == second_diff
    assert first_facts == second_facts
    assert first_model == second_model


def test_ambiguous_endpoint_matching_stays_exact_diff_only() -> None:
    before = _study(
        outcomes=[
            {"measure": "Response rate", "timeFrame": "12 weeks", "description": "A"},
            {"measure": "Response rate", "timeFrame": "12 weeks", "description": "A"},
        ]
    )
    after = _study(
        outcomes=[
            {"measure": "Response rates", "timeFrame": "12 weeks", "description": "A"},
            {"measure": "Response rates", "timeFrame": "12 weeks", "description": "A"},
        ]
    )
    _, _, snapshots = _history_chain(before, after)
    diff = build_history_exact_diff(*snapshots, transaction_from=snapshots[1]["transaction_from"])

    assert diff["operations"]
    assert derive_history_change_facts(*snapshots, diff) == []


def test_four_way_tied_endpoint_candidates_never_emit_a_false_measure_fact() -> None:
    before = _study(
        outcomes=[
            *[
                {"measure": "Response rate", "timeFrame": "12 weeks", "description": "A"}
                for _ in range(4)
            ],
            {"measure": "Response rate detail one", "timeFrame": "12 weeks", "description": "A"},
            {"measure": "Response rate detail two", "timeFrame": "12 weeks", "description": "A"},
        ]
    )
    after = _study(
        outcomes=[
            *[
                {"measure": "Response rates", "timeFrame": "12 weeks", "description": "A"}
                for _ in range(4)
            ],
            {"measure": "Response rate details one", "timeFrame": "12 weeks", "description": "A"},
            {"measure": "Response rate details two", "timeFrame": "12 weeks", "description": "A"},
        ]
    )
    _run, _receipts, snapshots = _history_chain(before, after)
    diff = build_history_exact_diff(*snapshots, transaction_from=snapshots[1]["transaction_from"])
    facts = derive_history_change_facts(*snapshots, diff)

    assert not any(
        fact["kind"] == "endpoint_measure_changed"
        and fact["before_value"] == "Response rate"
        and fact["after_value"] == "Response rates"
        for fact in facts
    )


def test_history_run_rejects_missing_or_mismatched_post_index_evidence() -> None:
    run, index_pre, index_post, receipts, _snapshots, raw_bodies = _history_evidence_chain()

    omitted_post = deepcopy(run)
    del omitted_post["history_index_post_receipt_ref"]
    _rehash(omitted_post, "run_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_index_post_receipt_ref"):
        validate_ctgov_history_run_against_receipts(
            omitted_post,
            index_pre,
            index_post,
            receipts,
            raw_bodies_by_receipt=raw_bodies,
        )

    duplicated_post = deepcopy(run)
    duplicated_post["history_index_post_receipt_ref"] = index_pre["receipt_id"]
    _rehash(duplicated_post, "run_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_run.index_receipt"):
        validate_ctgov_history_run_against_receipts(
            duplicated_post,
            index_pre,
            index_post,
            receipts,
            raw_bodies_by_receipt=raw_bodies,
        )

    changed_index = json.loads(raw_bodies[index_post["receipt_id"]])
    changed_index["history"]["changes"][1]["date"] = "2025-02-03"
    changed_post_raw = _raw_json(changed_index)
    changed_index_post = build_history_receipt(
        run_id=RUN_ID,
        nct_id=NCT_ID,
        resource_kind="history_index",
        source_version=None,
        raw_response=changed_post_raw,
        received_at="2026-08-02T00:00:08Z",
        transaction_from="2026-08-02T00:00:10Z",
        receipt_suffix="index_post_changed",
    )
    mismatched_run = deepcopy(run)
    mismatched_run["history_index_post_receipt_ref"] = changed_index_post["receipt_id"]
    _rehash(mismatched_run, "run_payload_sha256")
    mismatched_raw_bodies = dict(raw_bodies)
    del mismatched_raw_bodies[index_post["receipt_id"]]
    mismatched_raw_bodies[changed_index_post["receipt_id"]] = changed_post_raw
    with pytest.raises(ContractValidationError, match="history_run.index_roundtrip"):
        validate_ctgov_history_run_against_receipts(
            mismatched_run,
            index_pre,
            changed_index_post,
            receipts,
            raw_bodies_by_receipt=mismatched_raw_bodies,
        )


def test_history_run_rejects_rehashed_post_receipt_outside_collection_window() -> None:
    run, index_pre, index_post, receipts, _snapshots, raw_bodies = _history_evidence_chain()
    stale_post = deepcopy(index_post)
    stale_post["response"]["received_at"] = "2020-01-01T00:00:00Z"
    stale_post["transaction_from"] = "2020-01-01T00:00:00Z"
    _rehash(stale_post, "receipt_payload_sha256")

    with pytest.raises(ContractValidationError, match="history_run.receipt_chronology"):
        validate_ctgov_history_run_against_receipts(
            run,
            index_pre,
            stale_post,
            receipts,
            raw_bodies_by_receipt=raw_bodies,
        )

    swapped_first_version = deepcopy(receipts[0])
    swapped_first_version["response"]["received_at"] = "2026-08-02T00:00:06Z"
    swapped_first_version["transaction_from"] = "2026-08-02T00:00:07Z"
    _rehash(swapped_first_version, "receipt_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_run.receipt_chronology"):
        validate_ctgov_history_run_against_receipts(
            run,
            index_pre,
            index_post,
            [swapped_first_version, receipts[1]],
            raw_bodies_by_receipt=raw_bodies,
        )


def test_history_receipt_replay_rejects_rehashed_receipt_for_other_raw_bytes() -> None:
    _run, _index_pre, _index_post, receipts, _snapshots, raw_bodies = _history_evidence_chain()
    original = receipts[1]
    forged_raw = _raw_json({"studyVersion": 1, "study": _study(status="WITHDRAWN")})
    forged = deepcopy(original)
    forged_hash = hashlib.sha256(forged_raw).hexdigest()
    forged["response"]["exact_response_sha256"] = forged_hash
    forged["response"]["byte_count"] = len(forged_raw)
    forged["response"]["raw_response_object_key"] = (
        f"biocatalyst/raw/clinicaltrials/history/{NCT_ID}/version-1/{forged_hash}.json"
    )
    _rehash(forged, "receipt_payload_sha256")

    with pytest.raises(ContractValidationError, match="history_receipt.raw_response_hash"):
        validate_ctgov_history_receipt_against_raw_response(
            forged, raw_bodies[original["receipt_id"]]
        )


def test_history_snapshot_replay_rejects_rehashed_canonical_study_fabrication() -> None:
    run, index_pre, index_post, receipts, snapshots, raw_bodies = _history_evidence_chain()
    fabricated = deepcopy(snapshots[1])
    fabricated["canonical_study"]["protocolSection"]["statusModule"]["overallStatus"] = "WITHDRAWN"
    content_hash = canonical_json_sha256(fabricated["canonical_study"])
    fabricated["canonical_content_sha256"] = content_hash
    fabricated["source_record_ref"] = (
        f"src:ctgov-history:{NCT_ID}:version:1:sha256:{content_hash}"
    )
    _rehash(fabricated, "snapshot_payload_sha256")

    with pytest.raises(ContractValidationError, match="history_snapshot.raw_replay"):
        validate_trial_history_snapshot_against_evidence(
            fabricated,
            run,
            index_pre,
            index_post,
            receipts[1],
            all_version_receipts=receipts,
            raw_bodies_by_receipt=raw_bodies,
        )

    forged_id = deepcopy(snapshots[1])
    forged_id["source_snapshot_id"] = (
        f"{snapshots[1]['source_snapshot_id'].rsplit('_', 1)[0]}_{'f' * 24}"
    )
    _rehash(forged_id, "snapshot_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_snapshot.deterministic_id"):
        validate_trial_history_snapshot_against_evidence(
            forged_id,
            run,
            index_pre,
            index_post,
            receipts[1],
            all_version_receipts=receipts,
            raw_bodies_by_receipt=raw_bodies,
        )


def test_public_history_model_closes_kind_and_private_provenance_keys() -> None:
    _run, _receipts, snapshots = _history_chain()
    diff = build_history_exact_diff(*snapshots, transaction_from=snapshots[1]["transaction_from"])
    facts = derive_history_change_facts(*snapshots, diff)
    model = build_history_read_model(snapshots, facts, generated_at="2026-08-02T00:00:14Z")

    # The two root integrity fields are contract-required and must remain valid.
    validate_contract(model)

    open_ended_kind = deepcopy(model)
    open_ended_kind["changes"][0]["kind"] = "protocol_amendment"
    _rehash(open_ended_kind, "model_payload_sha256")
    with pytest.raises(ContractValidationError):
        validate_contract(open_ended_kind)

    for private_key in ("model_payload_sha256", "rawResponseBody", "receiptId"):
        private_model = deepcopy(model)
        private_model["changes"][0]["before_value"] = {private_key: "fabricated"}
        _rehash(private_model, "model_payload_sha256")
        with pytest.raises(ContractValidationError, match="history_read_model.private_provenance"):
            validate_contract(private_model)


def test_public_history_model_rejects_omitted_or_duplicated_private_facts() -> None:
    _run, _receipts, snapshots = _history_chain(
        _study(status="RECRUITING", enrollment=100),
        _study(status="COMPLETED", enrollment=150),
    )
    diff = build_history_exact_diff(*snapshots, transaction_from=snapshots[1]["transaction_from"])
    facts = derive_history_change_facts(*snapshots, diff)
    model = build_history_read_model(snapshots, facts, generated_at="2026-08-02T00:00:14Z")

    def model_for(supplied_facts: list[dict]) -> dict:
        candidate = deepcopy(model)
        ordered = sorted(
            supplied_facts,
            key=lambda fact: (
                fact["after_source_version"], fact["kind"], fact["change_fact_id"]
            ),
        )
        candidate["changes"] = [
            {
                "kind": fact["kind"],
                "before_display_version": fact["before_source_version"] + 1,
                "after_display_version": fact["after_source_version"] + 1,
                "before_value": fact["before_value"],
                "after_value": fact["after_value"],
            }
            for fact in ordered
        ]
        _rehash(candidate, "model_payload_sha256")
        return candidate

    omitted = facts[1:]
    with pytest.raises(ContractValidationError, match="history_read_model.fact_completeness"):
        validate_trial_history_read_model(model_for(omitted), snapshots, omitted)

    duplicated = [*facts, facts[0]]
    with pytest.raises(ContractValidationError, match="history_read_model.fact_completeness"):
        validate_trial_history_read_model(model_for(duplicated), snapshots, duplicated)

    with pytest.raises(ContractValidationError, match="history_read_model.snapshot_sequence"):
        build_history_read_model(
            snapshots[1:],
            [],
            generated_at="2026-08-02T00:00:14Z",
        )

    suffix_only = deepcopy(model)
    suffix_only["versions"] = [model["versions"][1]]
    suffix_only["changes"] = []
    _rehash(suffix_only, "model_payload_sha256")
    with pytest.raises(ContractValidationError, match="history_read_model.snapshot_sequence"):
        validate_trial_history_read_model(suffix_only, [snapshots[1]], [])


def test_other_outcome_paths_and_ambiguity_never_use_secondary_labels() -> None:
    before = _study(
        other_outcomes=[
            {"measure": "Device durability", "timeFrame": "24 weeks", "description": "Baseline"}
        ]
    )
    after = _study(
        other_outcomes=[
            {"measure": "Device durability", "timeFrame": "24 weeks", "description": "Updated"}
        ]
    )
    _run, _receipts, snapshots = _history_chain(before, after)
    diff = build_history_exact_diff(*snapshots, transaction_from=snapshots[1]["transaction_from"])
    facts = derive_history_change_facts(*snapshots, diff)
    other_facts = [fact for fact in facts if "otherOutcomes" in str(fact["source_json_paths"])]
    assert other_facts
    assert all("secondaryOutcomes" not in str(fact["source_json_paths"]) for fact in other_facts)

    ambiguous_before = _study(
        other_outcomes=[
            {"measure": "Durability", "timeFrame": "24 weeks", "description": "A"},
            {"measure": "Durability", "timeFrame": "24 weeks", "description": "A"},
        ]
    )
    ambiguous_after = _study(
        other_outcomes=[
            {"measure": "Durabilities", "timeFrame": "24 weeks", "description": "A"},
            {"measure": "Durabilities", "timeFrame": "24 weeks", "description": "A"},
        ]
    )
    _run, _receipts, ambiguous_snapshots = _history_chain(ambiguous_before, ambiguous_after)
    ambiguous_diff = build_history_exact_diff(
        *ambiguous_snapshots, transaction_from=ambiguous_snapshots[1]["transaction_from"]
    )
    assert derive_history_change_facts(*ambiguous_snapshots, ambiguous_diff) == []


def test_unavailable_model_is_explicit_and_uses_the_closed_reason_set() -> None:
    model = build_unavailable_history_read_model(
        NCT_ID,
        unavailable_reason="incomplete_chain",
        generated_at="2026-08-02T00:00:14Z",
    )

    validate_trial_history_read_model(model, [], [])
    assert model["available"] is False
    assert model["coverage_class"] == "unavailable"
    assert model["retrieved_at"] is None
    assert model["versions"] == []
    assert model["changes"] == []
    assert model["authority"]["decision_authority"] is False
    with pytest.raises(HistoryError, match="invalid_history_unavailable_reason"):
        build_unavailable_history_read_model(
            NCT_ID,
            unavailable_reason="unknown",
            generated_at="2026-08-02T00:00:14Z",
        )
