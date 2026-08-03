"""Contract-pinned tests for the T1a private-to-public protocol boundary."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

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
from engine.biocatalyst.trials import build_trial_snapshot
from engine.sector_intelligence import (
    ContractValidationError,
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
        "source_json_paths": [
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
        "source_json_paths": [
            "/protocolSection/identificationModule/officialTitle",
            "/protocolSection/identificationModule/briefTitle",
        ],
        "transform": "first_nonblank_then_normalize_whitespace_and_field_cap",
    }
    assert row["field_evidence"]["arm_groups"] == {
        "state": "observed",
        "source_json_paths": [
            "/protocolSection/armsInterventionsModule/armGroups"
        ],
        "transform": "normalize_whitespace_filter_missing_label_cap_100",
    }
    assert "score" not in json.dumps(peer_set, sort_keys=True).casefold()


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
