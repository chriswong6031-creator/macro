"""Contract-pinned tests for the BioCatalyst trial read projection boundary."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.biocatalyst.trials import (
    TrialProjectionError,
    build_trial_snapshot,
    validate_trial_snapshot,
)
from engine.sector_intelligence import canonical_json_sha256, validate_contract


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = (
    ROOT
    / "data"
    / "biocatalyst"
    / "fixtures"
    / "clinicaltrials"
    / "trial_source_snapshot.after.v1.valid.json"
)


def _source() -> dict:
    return json.loads(SOURCE_FIXTURE.read_text(encoding="utf-8"))


def _rehash_source(source: dict) -> None:
    canonical_sha = canonical_json_sha256(source["canonical_study"])
    nct_id = source["nct_id"]
    source["canonical_content_sha256"] = canonical_sha
    source["source_record_ref"] = f"src:ctgov:{nct_id}:sha256:{canonical_sha}"
    source["raw_object_key"] = (
        f"biocatalyst/raw/clinicaltrials/v2/{nct_id}/{canonical_sha}.json"
    )


def _rich_source() -> dict:
    source = _source()
    protocol = source["canonical_study"]["protocolSection"]
    protocol["identificationModule"]["officialTitle"] = "Synthetic Phase 2 Study — Full"
    protocol["statusModule"].update(
        {
            "startDateStruct": {"date": "2025-01-15", "type": "ACTUAL"},
            "completionDateStruct": {"date": "2027-03", "type": "ESTIMATED"},
        }
    )
    protocol["designModule"].update(
        {
            "studyType": "INTERVENTIONAL",
            "phases": ["PHASE2", "PHASE3"],
        }
    )
    protocol["sponsorCollaboratorsModule"] = {
        "leadSponsor": {"name": "Northstar Biopharma", "class": "INDUSTRY"}
    }
    protocol["conditionsModule"] = {"conditions": ["Cancer", "Glioma"]}
    protocol["armsInterventionsModule"] = {
        "interventions": [
            {"type": "DRUG", "name": "NX-101", "description": "Study drug"}
        ]
    }
    protocol["outcomesModule"] = {
        "primaryOutcomes": [
            {"measure": "Response rate", "timeFrame": "24 weeks"}
        ],
        "secondaryOutcomes": [
            {"measure": "Safety", "timeFrame": "36 weeks"}
        ],
    }
    protocol["contactsLocationsModule"] = {
        "locations": [
            {
                "facility": "Example Hospital",
                "city": "Seattle",
                "country": "United States",
            }
        ]
    }
    _rehash_source(source)
    validate_contract(source, repo_root=ROOT)
    return source


def test_build_trial_snapshot_copies_only_registered_rich_source_facts() -> None:
    source = _rich_source()

    snapshot = build_trial_snapshot(source, source_version_ordinal=7)

    validate_contract(snapshot, repo_root=ROOT)
    assert snapshot["source_version_ordinal"] == 7
    assert snapshot["facts"]["official_title"]["value"] == "Synthetic Phase 2 Study — Full"
    assert snapshot["facts"]["phases"]["value"] == ["PHASE2", "PHASE3"]
    assert snapshot["facts"]["sponsor"]["value"] == {
        "name": "Northstar Biopharma",
        "class": "INDUSTRY",
    }
    assert snapshot["facts"]["primary_outcomes"]["value"] == [
        {"measure": "Response rate", "timeFrame": "24 weeks"}
    ]
    assert snapshot["facts"]["locations"]["value"] == [
        {"facility": "Example Hospital", "city": "Seattle", "country": "United States"}
    ]
    assert all(
        fact["source_json_path"].startswith("/protocolSection/")
        for fact in snapshot["facts"].values()
    )
    assert "raw_object_key" not in snapshot
    assert "run_ref" not in snapshot
    assert "page_receipt_ref" not in snapshot
    assert "canonical_study" not in snapshot
    assert snapshot["projection_sha256"] == canonical_json_sha256(
        {key: value for key, value in snapshot.items() if key != "projection_sha256"}
    )


def test_build_trial_snapshot_preserves_missing_and_null_source_states() -> None:
    source = _source()
    source["canonical_study"]["protocolSection"]["identificationModule"][
        "officialTitle"
    ] = None
    _rehash_source(source)
    validate_contract(source, repo_root=ROOT)

    snapshot = build_trial_snapshot(source)

    assert snapshot["facts"]["official_title"] == {
        "state": "source_null",
        "value": None,
        "source_json_path": "/protocolSection/identificationModule/officialTitle",
    }
    assert snapshot["facts"]["study_type"] == {
        "state": "source_missing",
        "value": None,
        "source_json_path": "/protocolSection/designModule/studyType",
    }
    assert snapshot["facts"]["enrollment"] == {
        "state": "observed",
        "value": {"count": 160, "type": "ESTIMATED"},
        "source_json_path": "/protocolSection/designModule/enrollmentInfo",
    }


def test_build_trial_snapshot_fails_closed_for_malformed_source_or_fact_value() -> None:
    malformed_source = _source()
    malformed_source["canonical_study"]["protocolSection"]["identificationModule"][
        "nctId"
    ] = "NCT99999999"
    _rehash_source(malformed_source)
    with pytest.raises(TrialProjectionError, match="invalid_trial_source_snapshot"):
        build_trial_snapshot(malformed_source)

    malformed_fact = _source()
    malformed_fact["canonical_study"]["protocolSection"]["designModule"][
        "enrollmentInfo"
    ] = {"count": True, "type": "ESTIMATED"}
    _rehash_source(malformed_fact)
    validate_contract(malformed_fact, repo_root=ROOT)
    with pytest.raises(TrialProjectionError, match="invalid_trial_snapshot"):
        build_trial_snapshot(malformed_fact)

    with pytest.raises(TrialProjectionError, match="invalid_source_version_ordinal"):
        build_trial_snapshot(_source(), source_version_ordinal=True)


def test_build_trial_snapshot_is_order_independent_and_hash_stable() -> None:
    source = _rich_source()
    reordered = dict(reversed(list(source.items())))

    first = build_trial_snapshot(source, source_version_ordinal=3)
    second = build_trial_snapshot(reordered, source_version_ordinal=3)

    assert first == second
    assert first["projection_sha256"] == second["projection_sha256"]
    assert first["snapshot_id"] == second["snapshot_id"]


def test_validate_trial_snapshot_rejects_forbidden_authority_even_after_rehash() -> None:
    snapshot = build_trial_snapshot(_source())
    snapshot["authority"]["decision_authority"] = True
    snapshot["projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in snapshot.items() if key != "projection_sha256"}
    )

    with pytest.raises(TrialProjectionError, match="invalid_trial_snapshot"):
        validate_trial_snapshot(snapshot)

    assert build_trial_snapshot(_source())["authority"] == {
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


def test_validate_trial_snapshot_returns_a_defensive_normalized_copy() -> None:
    snapshot = build_trial_snapshot(_source())

    normalized = validate_trial_snapshot(snapshot)
    snapshot["facts"]["brief_title"]["value"] = "mutated after validation"

    assert normalized["facts"]["brief_title"]["value"] == "Synthetic Phase 2 Study"
