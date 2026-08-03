"""Contract-pinned tests for the T1a private-to-public protocol boundary."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import engine.biocatalyst.peer_matrix as peer_matrix
import engine.biocatalyst.protocols as protocol_module
from engine.biocatalyst.peer_matrix import (
    TrialPeerSetError,
    build_trial_peer_set,
    public_trial_protocol_row,
)
from engine.biocatalyst.protocols import (
    TrialProtocolProjectionError,
    build_trial_protocol_projection,
    validate_trial_protocol_projection,
    validate_trial_protocol_projection_against_source,
)
from engine.biocatalyst.sector_packet import (
    SectorPacketError,
    compile_sector_packet,
    plan_sector_packet_binding,
    prepare_sector_packet_inputs,
)
from engine.biocatalyst.trials import build_trial_snapshot
from engine.sector_intelligence import (
    ContractValidationError,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = (
    ROOT
    / "data"
    / "biocatalyst"
    / "fixtures"
    / "clinicaltrials"
    / "trial_source_snapshot.after.v1.valid.json"
)
SECTOR_PACKET_HEALTH_FIXTURE = (
    ROOT
    / "data"
    / "biocatalyst"
    / "fixtures"
    / "sector_packet"
    / "operational_health.v1.passed.json"
)


def _source(nct_id: str = "NCT00000001") -> dict:
    source = json.loads(SOURCE_FIXTURE.read_text(encoding="utf-8"))
    protocol = source["canonical_study"]["protocolSection"]
    protocol["identificationModule"]["nctId"] = nct_id
    protocol["identificationModule"]["officialTitle"] = f"Protocol {nct_id}"
    protocol["designModule"].update(
        {
            "studyType": "INTERVENTIONAL",
            "phases": ["PHASE2"],
        }
    )
    protocol["sponsorCollaboratorsModule"] = {
        "leadSponsor": {"name": "Northstar Biopharma", "class": "INDUSTRY"}
    }
    protocol["conditionsModule"] = {"conditions": ["Oncology"]}
    protocol["armsInterventionsModule"] = {
        "interventions": [
            {"name": "NX-101", "type": "DRUG", "description": "Study drug"}
        ],
        "armGroups": [
            {
                "label": "NX-101 arm",
                "type": "EXPERIMENTAL",
                "description": "Active study arm",
                "interventionNames": ["NX-101"],
            }
        ],
    }
    protocol["outcomesModule"] = {
        "primaryOutcomes": [{"measure": "Response rate", "timeFrame": "24 weeks"}],
        "secondaryOutcomes": [{"measure": "Safety", "timeFrame": "36 weeks"}],
    }
    protocol["contactsLocationsModule"] = {
        "locations": [
            {"facility": "Example Hospital", "country": "United States"},
            {"facility": "North Hospital", "country": "Canada"},
        ]
    }
    canonical_sha = canonical_json_sha256(source["canonical_study"])
    source["nct_id"] = nct_id
    source["canonical_content_sha256"] = canonical_sha
    source["source_record_ref"] = f"src:ctgov:{nct_id}:sha256:{canonical_sha}"
    source["raw_object_key"] = f"biocatalyst/raw/clinicaltrials/v2/{nct_id}/{canonical_sha}.json"
    source["source_snapshot_id"] = f"ctgov_snapshot_{nct_id}_fixture_{canonical_sha}"
    source["source_uri"] = f"https://clinicaltrials.gov/study/{nct_id}"
    validate_contract(source, repo_root=ROOT)
    return source


def _protocol(nct_id: str) -> dict:
    source = _source(nct_id)
    snapshot = build_trial_snapshot(source)
    return build_trial_protocol_projection(source, snapshot)


def _sector_health(*, count: int) -> dict:
    health = json.loads(SECTOR_PACKET_HEALTH_FIXTURE.read_text(encoding="utf-8"))
    health["configured_nct_count"] = count
    health["observed_nct_count"] = count
    return health


def _sector_governance(
    projections: list[dict], health: dict, *, evaluated_at: str = "2026-08-01T15:01:00Z"
) -> tuple[dict, dict]:
    lobe_ref = "run:biocatalyst:n0a:20260801T150100Z"
    manifest_ref = "authority:biocatalyst:n0a-display:v1"
    cutoff = "2026-08-01T15:00:05Z"
    binding = plan_sector_packet_binding(
        trial_projections=projections,
        operational_health=health,
        evaluated_at=evaluated_at,
        lobe_run_ref=lobe_ref,
        lobe_knowledge_cutoff=cutoff,
        authority_manifest_ref=manifest_ref,
        max_authority="A1_EXPLAIN",
        allowed_actions=["observe", "explain"],
    )
    manifest = {
        "contract_id": "authority_manifest.v1",
        "schema_version": "1.0.0",
        "manifest_id": manifest_ref,
        "sector": "biopharma",
        "artifact_ref": binding.packet_id,
        "artifact_type": "sector_intelligence_packet.v1",
        "publication_tier": "DISPLAY",
        "max_authority": "A1_EXPLAIN",
        "allowed_actions": ["observe", "explain"],
        "denied_actions": [
            "originate_signal",
            "raise_authority_from_llm",
            "rank_security",
            "select_security",
            "size_position",
            "gate_decision",
            "execute_trade",
        ],
        "consumers": ["neural_web", "mastermind_ai"],
        "issued_by": "external_governance",
        "issued_at": "2026-08-01T15:00:05Z",
        "valid_from": "2026-08-01T15:00:05Z",
        "valid_to": None,
        "expires_at": "2026-08-01T20:00:00Z",
        "promotion_evidence_refs": [],
        "governance_decision_refs": ["governance:biocatalyst:n0a-display:v1"],
        "kill_switch": {"enabled": False, "owner": "external_governance", "reason": None, "activated_at": None},
        "transaction_from": "2026-08-01T15:00:06Z",
        "transaction_to": None,
    }
    lobe = {
        "contract_id": "lobe_run.v1",
        "schema_version": "1.0.0",
        "run_id": lobe_ref,
        "sector": "biopharma",
        "lobe_id": "biocatalyst_context",
        "producer": {"service": "external_lobe", "code_version": "n0a-test", "owner": "governance"},
        "started_at": "2026-08-01T15:00:05Z",
        "finished_at": "2026-08-01T15:00:06Z",
        "knowledge_cutoff": cutoff,
        "source_watermarks": [
            {"source_id": "clinicaltrials_gov_v2", "watermark": cutoff, "observed_at": cutoff, "state": "current"}
        ],
        "input_hashes": sorted(
            [canonical_json_sha256(health)]
            + [projection["projection_sha256"] for projection in projections]
        ),
        "output_artifacts": [
            {"artifact_ref": binding.packet_id, "content_sha256": binding.packet_hash, "row_count": binding.row_count}
        ],
        "warnings": [],
        "failures": [],
        "status": "ok",
        "completeness": 1.0,
        "model_versions": [],
        "authority_manifest_ref": manifest_ref,
    }
    return lobe, manifest


def _sector_packet(projections: list[dict]) -> dict:
    health = _sector_health(count=len(projections))
    lobe, manifest = _sector_governance(projections, health)
    return compile_sector_packet(
        prepare_sector_packet_inputs(
            trial_projections=projections,
            operational_health=health,
            evaluated_at="2026-08-01T15:01:00Z",
            lobe_run=lobe,
            authority_manifest=manifest,
        )
    )


def _sector_inputs(
    projections: list[dict],
    *,
    health: dict | None = None,
    evaluated_at: str = "2026-08-01T15:01:00Z",
) -> tuple[dict, dict, dict]:
    actual_health = _sector_health(count=len(projections)) if health is None else health
    lobe, manifest = _sector_governance(
        projections, actual_health, evaluated_at=evaluated_at
    )
    return actual_health, lobe, manifest


def test_protocol_projection_copies_arm_groups_only_at_the_publication_boundary() -> None:
    source = _source()
    snapshot = build_trial_snapshot(source)

    projection = build_trial_protocol_projection(source, snapshot)

    validate_contract(projection, repo_root=ROOT)
    validate_trial_protocol_projection_against_source(projection, source, snapshot)
    assert projection["facts"]["arm_groups"] == {
        "state": "observed",
        "source_json_path": "/protocolSection/armsInterventionsModule/armGroups",
        "value": [
            {
                "label": "NX-101 arm",
                "type": "EXPERIMENTAL",
                "description": "Active study arm",
                "interventionNames": ["NX-101"],
            }
        ],
    }
    # The source snapshot is a publication-only input.  The protocol artifact
    # contains selected facts and source-facing attribution, never raw archive
    # or worker-state material.
    serialized = json.dumps(projection, sort_keys=True)
    for forbidden in ("canonical_study", "raw_object_key", "page_receipt_ref", "run_ref"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "mutate",
    (
        lambda group: group.update(label="x" * 1001),
        lambda group: group.update(type="x" * 81),
        lambda group: group.update(description="x" * 6001),
        lambda group: group.update(interventionNames=["x" * 513]),
        lambda group: group.update(interventionNames=["NX-101"] * 101),
    ),
)
def test_protocol_projection_rejects_overcap_registered_arm_group_values(mutate) -> None:
    source = _source()
    mutate(
        source["canonical_study"]["protocolSection"]["armsInterventionsModule"]
        ["armGroups"][0]
    )
    canonical_sha = canonical_json_sha256(source["canonical_study"])
    source["canonical_content_sha256"] = canonical_sha
    source["source_record_ref"] = f"src:ctgov:NCT00000001:sha256:{canonical_sha}"
    source["raw_object_key"] = (
        "biocatalyst/raw/clinicaltrials/v2/NCT00000001/"
        f"{canonical_sha}.json"
    )
    validate_contract(source, repo_root=ROOT)

    with pytest.raises(TrialProtocolProjectionError, match="arm_groups_invalid"):
        build_trial_protocol_projection(source, build_trial_snapshot(source))


def test_protocol_projection_rejects_overcap_arm_group_list() -> None:
    source = _source()
    groups = source["canonical_study"]["protocolSection"]["armsInterventionsModule"][
        "armGroups"
    ]
    source["canonical_study"]["protocolSection"]["armsInterventionsModule"][
        "armGroups"
    ] = groups * 101
    canonical_sha = canonical_json_sha256(source["canonical_study"])
    source["canonical_content_sha256"] = canonical_sha
    source["source_record_ref"] = f"src:ctgov:NCT00000001:sha256:{canonical_sha}"
    source["raw_object_key"] = (
        "biocatalyst/raw/clinicaltrials/v2/NCT00000001/"
        f"{canonical_sha}.json"
    )
    validate_contract(source, repo_root=ROOT)

    with pytest.raises(TrialProtocolProjectionError, match="arm_groups_invalid"):
        build_trial_protocol_projection(source, build_trial_snapshot(source))


def test_protocol_projection_is_a_closed_arm_group_allowlist() -> None:
    source = _source()
    source["canonical_study"]["protocolSection"]["armsInterventionsModule"][
        "armGroups"
    ][0]["private_note"] = "must not cross the publication boundary"
    canonical_sha = canonical_json_sha256(source["canonical_study"])
    source["canonical_content_sha256"] = canonical_sha
    source["source_record_ref"] = f"src:ctgov:NCT00000001:sha256:{canonical_sha}"
    source["raw_object_key"] = (
        "biocatalyst/raw/clinicaltrials/v2/NCT00000001/"
        f"{canonical_sha}.json"
    )
    validate_contract(source, repo_root=ROOT)

    arm_group = build_trial_protocol_projection(
        source, build_trial_snapshot(source)
    )["facts"]["arm_groups"]["value"][0]
    assert arm_group == {
        "label": "NX-101 arm",
        "type": "EXPERIMENTAL",
        "description": "Active study arm",
        "interventionNames": ["NX-101"],
    }


def test_protocol_projection_rejects_aggregate_byte_overflow(monkeypatch) -> None:
    source = _source()
    monkeypatch.setattr(protocol_module, "_MAX_PROTOCOL_PROJECTION_BYTES", 1)

    with pytest.raises(TrialProtocolProjectionError, match="protocol_projection_too_large"):
        build_trial_protocol_projection(source, build_trial_snapshot(source))


def test_protocol_projection_is_hash_and_source_transform_bound() -> None:
    source = _source()
    snapshot = build_trial_snapshot(source)
    projection = build_trial_protocol_projection(source, snapshot)
    projection["facts"]["arm_groups"]["value"][0]["label"] = "Relabelled arm"
    projection["protocol_projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in projection.items() if key != "protocol_projection_sha256"}
    )

    with pytest.raises(TrialProtocolProjectionError, match="source_binding"):
        validate_trial_protocol_projection_against_source(projection, source, snapshot)

    projection["protocol_projection_id"] = "trial_protocol_NCT00000001_" + "0" * 24
    projection["protocol_projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in projection.items() if key != "protocol_projection_sha256"}
    )
    with pytest.raises(TrialProtocolProjectionError, match="invalid_trial_protocol_projection"):
        validate_trial_protocol_projection(projection)


def test_protocol_projection_rejects_changed_content_without_rehashing() -> None:
    projection = _protocol("NCT00000001")
    projection["facts"]["arm_groups"]["value"] = []

    with pytest.raises(TrialProtocolProjectionError, match="invalid_trial_protocol_projection"):
        validate_trial_protocol_projection(projection)


def test_protocol_projection_rehashed_identity_and_chronology_tampering_is_rejected() -> None:
    def rehash(projection: dict) -> None:
        projection["protocol_projection_sha256"] = canonical_json_sha256(
            {
                key: value
                for key, value in projection.items()
                if key != "protocol_projection_sha256"
            }
        )

    bad_source_record = _protocol("NCT00000001")
    bad_source_record["source_record_ref"] = (
        "src:ctgov:NCT00000002:sha256:"
        f"{bad_source_record['canonical_content_sha256']}"
    )
    rehash(bad_source_record)
    with pytest.raises(TrialProtocolProjectionError, match="invalid_trial_protocol_projection"):
        validate_trial_protocol_projection(bad_source_record)

    bad_source_uri = _protocol("NCT00000001")
    bad_source_uri["source_attribution"]["source_uri"] = (
        "https://clinicaltrials.gov/study/NCT00000002"
    )
    rehash(bad_source_uri)
    with pytest.raises(TrialProtocolProjectionError, match="invalid_trial_protocol_projection"):
        validate_trial_protocol_projection(bad_source_uri)

    bad_chronology = _protocol("NCT00000001")
    bad_chronology["first_seen_at"] = "2026-08-01T15:00:05Z"
    bad_chronology["knowledge_cutoff"] = "2026-08-01T15:00:03Z"
    rehash(bad_chronology)
    with pytest.raises(TrialProtocolProjectionError, match="invalid_trial_protocol_projection"):
        validate_trial_protocol_projection(bad_chronology)


def test_protocol_row_counts_all_locations_while_capping_country_labels() -> None:
    source = _source("NCT00000001")
    source["canonical_study"]["protocolSection"]["contactsLocationsModule"] = {
        "locations": [
            {"facility": f"Site {index}", "country": f"Country {index:03d}"}
            for index in range(125)
        ]
    }
    canonical_sha = canonical_json_sha256(source["canonical_study"])
    source["canonical_content_sha256"] = canonical_sha
    source["source_record_ref"] = f"src:ctgov:NCT00000001:sha256:{canonical_sha}"
    source["raw_object_key"] = (
        "biocatalyst/raw/clinicaltrials/v2/NCT00000001/"
        f"{canonical_sha}.json"
    )
    validate_contract(source, repo_root=ROOT)

    row = public_trial_protocol_row(
        build_trial_protocol_projection(source, build_trial_snapshot(source)),
        history_model=None,
        as_of="2026-08-01T15:00:04.000000Z",
    )

    assert row["site_count"] == 125
    assert row["countries"] == [f"Country {index:03d}" for index in range(100)]
    assert row["field_evidence"]["site_count"] == {
        "state": "observed",
        "source_field_locators": [
            "/protocolSection/contactsLocationsModule/locations"
        ],
        "transform": "count_mapping_location_rows",
    }


def test_peer_set_is_explicit_sorted_partial_and_facts_only() -> None:
    protocols = {
        "NCT00000003": _protocol("NCT00000003"),
        "NCT00000001": _protocol("NCT00000001"),
    }
    peer_set = build_trial_peer_set(
        cohort_nct_ids=("NCT00000001", "NCT00000002", "NCT00000003"),
        protocols_by_nct=protocols,
        history_models_by_nct={
            "NCT00000001": {
                "available": False,
                "unavailable_reason": "not_collected",
            },
            "NCT00000003": {
                "available": True,
                "coverage_class": "record_history_complete",
            },
        },
        as_of="2026-08-01T15:00:04.000000Z",
        page_limit=1,
        offset=0,
        next_cursor="signed-next-page",
    )

    validate_contract(peer_set, repo_root=ROOT)
    assert peer_set["cohort_nct_ids"] == ["NCT00000001", "NCT00000002", "NCT00000003"]
    assert peer_set["uncovered_nct_ids"] == ["NCT00000002"]
    assert peer_set["coverage"] == {
        "class": "current_only",
        "selection_basis": "explicit_nct_id_cohort",
        "requested_count": 3,
        "covered_count": 2,
        "uncovered_count": 1,
    }
    assert peer_set["pagination"] == {
        "limit": 1,
        "total": 2,
        "next_cursor": "signed-next-page",
    }
    row = peer_set["trials"][0]
    assert row["nct_id"] == "NCT00000001"
    assert row["arm_groups"] == [
        {
            "label": "NX-101 arm",
            "type": "EXPERIMENTAL",
            "description": "Active study arm",
            "intervention_names": ["NX-101"],
        }
    ]
    assert row["dates"]["primary_completion"] == {
        "date": "2026-12",
        "type": "ESTIMATED",
        "precision": "month",
    }
    assert row["history"] == {
        "available": False,
        "state": "unavailable",
        "coverage": None,
        "reason": "not_collected",
    }
    assert row["record_age"] == {
        "seconds": 0,
        "basis": "as_of_minus_retrieved_at_floor_seconds",
    }
    assert row["field_evidence"]["title"] == {
        "state": "observed",
        "source_field_locators": [
            "/protocolSection/identificationModule/officialTitle",
            "/protocolSection/identificationModule/briefTitle",
        ],
        "transform": "first_nonblank_then_normalize_whitespace_and_field_cap",
    }
    assert row["field_evidence"]["arm_groups"] == {
        "state": "observed",
        "source_field_locators": [
            "/protocolSection/armsInterventionsModule/armGroups"
        ],
        "transform": "normalize_whitespace_filter_missing_label_cap_100",
    }
    assert "score" not in json.dumps(peer_set, sort_keys=True).casefold()
    field_evidence_schema = json.loads(
        (ROOT / "contracts" / "biocatalyst" / "trial_peer_set.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )["$defs"]["fieldEvidence"]["properties"]["source_field_locators"]["items"]
    assert set(field_evidence_schema["enum"]) == peer_matrix._PUBLIC_SOURCE_FIELD_LOCATORS


def test_peer_set_rejects_aggregate_response_byte_overflow(monkeypatch) -> None:
    monkeypatch.setattr(peer_matrix, "_MAX_TRIAL_PEER_SET_RESPONSE_BYTES", 1)

    with pytest.raises(TrialPeerSetError, match="peer_set_response_too_large"):
        build_trial_peer_set(
            cohort_nct_ids=("NCT00000001", "NCT00000002"),
            protocols_by_nct={"NCT00000001": _protocol("NCT00000001")},
            history_models_by_nct={},
            as_of="2026-08-01T15:00:04.000000Z",
            page_limit=1,
            offset=0,
            next_cursor=None,
        )


def test_peer_set_pagination_presence_matches_remaining_covered_rows() -> None:
    protocols = {
        "NCT00000001": _protocol("NCT00000001"),
        "NCT00000002": _protocol("NCT00000002"),
    }
    common = {
        "cohort_nct_ids": ("NCT00000001", "NCT00000002"),
        "protocols_by_nct": protocols,
        "history_models_by_nct": {},
        "as_of": "2026-08-01T15:00:04.000000Z",
        "page_limit": 1,
    }
    first_page = build_trial_peer_set(**common, offset=0, next_cursor="signed-next")
    assert first_page["trials"][0]["nct_id"] == "NCT00000001"
    assert first_page["pagination"]["next_cursor"] == "signed-next"

    terminal_page = build_trial_peer_set(**common, offset=1, next_cursor=None)
    assert terminal_page["trials"][0]["nct_id"] == "NCT00000002"
    assert terminal_page["pagination"]["next_cursor"] is None

    empty_terminal_page = build_trial_peer_set(**common, offset=2, next_cursor=None)
    assert empty_terminal_page["trials"] == []
    assert empty_terminal_page["pagination"]["total"] == 2

    with pytest.raises(TrialPeerSetError, match="peer_set_pagination_binding_invalid"):
        build_trial_peer_set(**common, offset=0, next_cursor=None)
    with pytest.raises(TrialPeerSetError, match="peer_set_pagination_binding_invalid"):
        build_trial_peer_set(**common, offset=2, next_cursor="unexpected")


def test_peer_set_rejects_duplicate_rows_misbound_evidence_and_negative_record_age() -> None:
    peer_set = build_trial_peer_set(
        cohort_nct_ids=("NCT00000001", "NCT00000002"),
        protocols_by_nct={
            "NCT00000001": _protocol("NCT00000001"),
            "NCT00000002": _protocol("NCT00000002"),
        },
        history_models_by_nct={},
        as_of="2026-08-01T15:00:04.000000Z",
        page_limit=2,
        offset=0,
        next_cursor=None,
    )

    duplicate = copy.deepcopy(peer_set)
    duplicate["trials"][1]["nct_id"] = "NCT00000001"
    duplicate["trials"][1]["evidence"]["record_id"] = "NCT00000001"
    duplicate["trials"][1]["evidence"]["url"] = (
        "https://clinicaltrials.gov/study/NCT00000001"
    )
    with pytest.raises(ContractValidationError, match="trial_peer_set.trial_unique"):
        validate_contract(duplicate, repo_root=ROOT)

    misbound_evidence = copy.deepcopy(peer_set)
    misbound_evidence["trials"][0]["evidence"]["record_id"] = "NCT00000002"
    misbound_evidence["trials"][0]["evidence"]["url"] = (
        "https://clinicaltrials.gov/study/NCT00000002"
    )
    with pytest.raises(ContractValidationError, match="trial_peer_set.evidence_record"):
        validate_contract(misbound_evidence, repo_root=ROOT)

    negative_age = copy.deepcopy(peer_set)
    negative_age["as_of"] = "2026-08-01T15:00:03.000000Z"
    with pytest.raises(ContractValidationError, match="trial_peer_set.record_age_chronology"):
        validate_contract(negative_age, repo_root=ROOT)


def test_peer_set_rejects_unsorted_or_untrusted_projection_inputs() -> None:
    with pytest.raises(TrialPeerSetError, match="peer_set_cohort_invalid"):
        build_trial_peer_set(
            cohort_nct_ids=("NCT00000002", "NCT00000001"),
            protocols_by_nct={},
            history_models_by_nct={},
            as_of="2026-08-01T15:00:04.000000Z",
            page_limit=1,
            offset=0,
            next_cursor=None,
        )
    invalid = _protocol("NCT00000001")
    invalid["facts"]["arm_groups"]["value"] = []
    with pytest.raises(TrialPeerSetError, match="trial_protocol_projection_invalid"):
        build_trial_peer_set(
            cohort_nct_ids=("NCT00000001", "NCT00000002"),
            protocols_by_nct={"NCT00000001": invalid},
            history_models_by_nct={},
            as_of="2026-08-01T15:00:04.000000Z",
            page_limit=1,
            offset=0,
            next_cursor=None,
        )


def test_n0a_sector_packet_is_permutation_stable_and_facts_only() -> None:
    first = build_trial_snapshot(_source("NCT00000001"))
    second = build_trial_snapshot(_source("NCT00000002"))

    forward = _sector_packet([first, second])
    reverse = _sector_packet([dict(reversed(second.items())), dict(reversed(first.items()))])

    validate_contract("sector_intelligence_packet.v1", forward, repo_root=ROOT)
    assert canonical_json_bytes(forward) == canonical_json_bytes(reverse)
    assert forward["entity_refs"] == ["trial:NCT00000001", "trial:NCT00000002"]
    assert forward["security_refs"] == []
    assert forward["portfolio_exposure"] == []
    assert forward["material_change_event_refs"] == []
    assert forward["upcoming_event_refs"] == []
    assert forward["feature_snapshot_refs"] == []
    assert forward["prediction_refs"] == []
    # Live B1 read projections currently carry no evidence-claim artifact;
    # N0a must retain that exact empty state rather than manufacturing refs.
    assert forward["current_fact_refs"] == []
    assert forward["evidence_claim_refs"] == []
    assert forward["authority_caps"] == {
        "max_authority": "A1_EXPLAIN",
        "allowed_actions": ["observe", "explain"],
        "forbidden_actions": [
            "execute_trade",
            "gate_decision",
            "originate_signal",
            "raise_authority_from_llm",
            "rank_security",
            "select_security",
            "size_position",
        ],
        "llm_may_originate_signals": False,
    }
    serialized = json.dumps(forward, sort_keys=True)
    assert "Northstar Biopharma" not in serialized
    assert "NX-101" not in serialized


def test_n0a_sector_packet_preserves_committed_evidence_and_source_refs_exactly() -> None:
    snapshot = json.loads(
        (
            ROOT
            / "data"
            / "biocatalyst"
            / "fixtures"
            / "clinicaltrials"
            / "trial_snapshot.v1.valid.json"
        ).read_text(encoding="utf-8")
    )

    packet = _sector_packet([snapshot])

    assert packet["current_fact_refs"] == [
        "claim:trial:NCT00000001:overall_status:20260801"
    ]
    assert packet["evidence_claim_refs"] == packet["current_fact_refs"]
    assert packet["source_record_refs"] == [snapshot["source_record_ref"]]


def test_n0a_sector_packet_keeps_a_ticker_like_sponsor_out_of_native_refs() -> None:
    projection = build_trial_snapshot(_source())
    projection["facts"]["sponsor"] = {
        "state": "observed",
        "value": {"name": "ABCD", "class": "INDUSTRY"},
        "source_json_path": "/protocolSection/sponsorCollaboratorsModule/leadSponsor",
    }
    projection["projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in projection.items() if key != "projection_sha256"}
    )

    packet = _sector_packet([projection])

    assert packet["entity_refs"] == ["trial:NCT00000001"]
    assert "ABCD" not in canonical_json_bytes(packet).decode("utf-8")


def test_n0a_sector_packet_rejects_raw_and_unobserved_trial_projection_inputs() -> None:
    raw_store = build_trial_snapshot(_source())
    raw_store["canonical_study"] = {"sentinel": "private"}
    health = _sector_health(count=1)
    lobe, manifest = _sector_governance([build_trial_snapshot(_source())], health)

    with pytest.raises(SectorPacketError, match="trial_projection_unavailable"):
        prepare_sector_packet_inputs(
            trial_projections=[raw_store],
            operational_health=health,
            evaluated_at="2026-08-01T15:01:00Z",
            lobe_run=lobe,
            authority_manifest=manifest,
        )

    unobserved = build_trial_snapshot(_source())
    for fact in unobserved["facts"].values():
        fact["state"] = "source_missing"
        fact["value"] = None
    unobserved["projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in unobserved.items() if key != "projection_sha256"}
    )
    with pytest.raises(SectorPacketError, match="trial_projection_unavailable"):
        prepare_sector_packet_inputs(
            trial_projections=[unobserved],
            operational_health=health,
            evaluated_at="2026-08-01T15:01:00Z",
            lobe_run=lobe,
            authority_manifest=manifest,
        )


@pytest.mark.parametrize(
    ("mutate", "expected"),
    (
        (
            lambda lobe, manifest: lobe["output_artifacts"].clear(),
            "governance_reference_unavailable",
        ),
        (
            lambda lobe, manifest: lobe["output_artifacts"].__setitem__(
                0, {**lobe["output_artifacts"][0], "content_sha256": "0" * 64}
            ),
            "governance_reference_unavailable",
        ),
        (
            lambda lobe, manifest: lobe.update(input_hashes=["1" * 64]),
            "governance_reference_unavailable",
        ),
        (
            lambda lobe, manifest: manifest.update(artifact_ref="packet:biopharma:unplanned"),
            "governance_reference_unavailable",
        ),
        (
            lambda lobe, manifest: manifest.update(max_authority="A2_ATTEND"),
            "governance_reference_unavailable",
        ),
        (
            lambda lobe, manifest: manifest.update(allowed_actions=["observe", "attend"]),
            "governance_reference_unavailable",
        ),
        (
            lambda lobe, manifest: manifest.update(
                denied_actions=[
                    "originate_signal",
                    "raise_authority_from_llm",
                    "select_security",
                    "size_position",
                    "gate_decision",
                    "execute_trade",
                ]
            ),
            "governance_reference_unavailable",
        ),
        (
            lambda lobe, manifest: manifest["kill_switch"].update(enabled=True),
            "governance_reference_unavailable",
        ),
        (
            lambda lobe, manifest: manifest.update(expires_at="2026-08-01T15:00:59Z"),
            "governance_reference_unavailable",
        ),
    ),
)
def test_n0a_sector_packet_rejects_unbound_or_escalated_governance(
    mutate, expected: str
) -> None:
    projection = build_trial_snapshot(_source())
    health, lobe, manifest = _sector_inputs([projection])
    mutate(lobe, manifest)

    with pytest.raises(SectorPacketError, match=expected):
        prepare_sector_packet_inputs(
            trial_projections=[projection],
            operational_health=health,
            evaluated_at="2026-08-01T15:01:00Z",
            lobe_run=lobe,
            authority_manifest=manifest,
        )


def test_n0a_sector_packet_planning_is_not_a_publishable_authority_or_placeholder_bypass() -> None:
    projection = build_trial_snapshot(_source())
    health, lobe, manifest = _sector_inputs([projection])
    binding = plan_sector_packet_binding(
        trial_projections=[projection],
        operational_health=health,
        evaluated_at="2026-08-01T15:01:00Z",
        lobe_run_ref=lobe["run_id"],
        lobe_knowledge_cutoff=lobe["knowledge_cutoff"],
        authority_manifest_ref=manifest["manifest_id"],
        max_authority=manifest["max_authority"],
        allowed_actions=manifest["allowed_actions"],
    )

    assert binding == type(binding)(
        packet_id=manifest["artifact_ref"],
        packet_hash=lobe["output_artifacts"][0]["content_sha256"],
        row_count=1,
    )
    assert not hasattr(binding, "authority_caps")
    lobe["output_artifacts"][0]["content_sha256"] = "f" * 64
    with pytest.raises(SectorPacketError, match="governance_reference_unavailable"):
        prepare_sector_packet_inputs(
            trial_projections=[projection],
            operational_health=health,
            evaluated_at="2026-08-01T15:01:00Z",
            lobe_run=lobe,
            authority_manifest=manifest,
        )


def test_n0a_sector_packet_derives_staleness_from_passed_health_and_evaluated_at() -> None:
    projection = build_trial_snapshot(_source())
    evaluated_at = "2026-08-01T17:01:00Z"
    health = _sector_health(count=1)
    health, lobe, manifest = _sector_inputs(
        [projection], health=health, evaluated_at=evaluated_at
    )

    packet = compile_sector_packet(
        prepare_sector_packet_inputs(
            trial_projections=[projection],
            operational_health=health,
            evaluated_at=evaluated_at,
            lobe_run=lobe,
            authority_manifest=manifest,
        )
    )

    assert packet["freshness"] == {
        "state": "stale",
        "oldest_required_source_at": "2026-08-01T15:00:04Z",
        "evaluated_at": evaluated_at,
        "stale_source_ids": ["clinicaltrials_gov_v2"],
        "unknown_source_ids": [],
    }
    assert packet["quality"]["state"] == "degraded"


def test_n0a_sector_packet_rejects_future_evaluation_and_unresolved_contradictions() -> None:
    projection = build_trial_snapshot(_source())
    health, lobe, manifest = _sector_inputs([projection])
    with pytest.raises(SectorPacketError, match="governance_reference_unavailable"):
        prepare_sector_packet_inputs(
            trial_projections=[projection],
            operational_health=health,
            evaluated_at="2026-08-01T21:00:00Z",
            lobe_run=lobe,
            authority_manifest=manifest,
        )

    unresolved = build_trial_snapshot(_source())
    unresolved["contradiction_state"] = "open"
    unresolved["projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in unresolved.items() if key != "projection_sha256"}
    )
    with pytest.raises(SectorPacketError, match="contradiction_reference_unavailable"):
        prepare_sector_packet_inputs(
            trial_projections=[unresolved],
            operational_health=health,
            evaluated_at="2026-08-01T15:01:00Z",
            lobe_run=lobe,
            authority_manifest=manifest,
        )


def test_n0a_sector_packet_refuses_hash_tampering_and_unsupported_output_lanes() -> None:
    projection = build_trial_snapshot(_source())
    health, lobe, manifest = _sector_inputs([projection])
    prepared = prepare_sector_packet_inputs(
        trial_projections=[projection],
        operational_health=health,
        evaluated_at="2026-08-01T15:01:00Z",
        lobe_run=lobe,
        authority_manifest=manifest,
    )
    tampered = compile_sector_packet(prepared)
    tampered["security_refs"] = ["security:forbidden"]
    tampered["prediction_refs"] = ["prediction:forbidden"]
    tampered["packet_hash"] = canonical_json_sha256(
        {key: value for key, value in tampered.items() if key != "packet_hash"}
    )
    # Generic packet validation alone permits those fields.  The private seal
    # ensures they cannot enter the pure compiler by rehashing a public dict.
    validate_contract("sector_intelligence_packet.v1", tampered, repo_root=ROOT)
    with pytest.raises(SectorPacketError, match="validated_inputs_required"):
        compile_sector_packet(type(prepared)(packet_bytes=canonical_json_bytes(tampered)))
    with pytest.raises(TypeError):
        prepare_sector_packet_inputs(  # type: ignore[call-arg]
            trial_projections=[projection],
            operational_health=health,
            evaluated_at="2026-08-01T15:01:00Z",
            lobe_run=lobe,
            authority_manifest=manifest,
            security_refs=["security:forbidden"],
        )
