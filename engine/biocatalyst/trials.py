"""Deterministic ClinicalTrials.gov read projections for BioCatalyst.

This is intentionally a narrow translation boundary.  It accepts a validated
``trial_source_snapshot.v1`` source record and emits only the bounded
``trial_snapshot.v1`` source-fact projection.  It never reads an archive,
derives a clinical conclusion, or carries private receipt/object provenance
into the product projection.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from engine.sector_intelligence import (
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
)
from engine.sector_intelligence.contracts import ContractError


class TrialProjectionError(ValueError):
    """A bounded, fail-closed trial-projection construction failure."""


_MISSING = object()

_FACT_JSON_PATHS: dict[str, str] = {
    "brief_title": "/protocolSection/identificationModule/briefTitle",
    "official_title": "/protocolSection/identificationModule/officialTitle",
    "overall_status": "/protocolSection/statusModule/overallStatus",
    "study_type": "/protocolSection/designModule/studyType",
    "phases": "/protocolSection/designModule/phases",
    "sponsor": "/protocolSection/sponsorCollaboratorsModule/leadSponsor",
    "enrollment": "/protocolSection/designModule/enrollmentInfo",
    "start_date": "/protocolSection/statusModule/startDateStruct",
    "primary_completion_date": (
        "/protocolSection/statusModule/primaryCompletionDateStruct"
    ),
    "completion_date": "/protocolSection/statusModule/completionDateStruct",
    "conditions": "/protocolSection/conditionsModule/conditions",
    "interventions": "/protocolSection/armsInterventionsModule/interventions",
    "primary_outcomes": "/protocolSection/outcomesModule/primaryOutcomes",
    "secondary_outcomes": "/protocolSection/outcomesModule/secondaryOutcomes",
    "locations": "/protocolSection/contactsLocationsModule/locations",
}

_SUBMITTER_RESPONSIBILITY_NOTE = (
    "Study sponsors or investigators supply the registry information; a listing "
    "is not government validation of the study's science or safety."
)
_MODIFICATION_NOTE = (
    "BioCatalyst parsed and normalized selected source fields without changing "
    "the archived source record."
)
_AUTHORITY = {
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


def _json_copy(value: Any) -> Any:
    """Return a defensive JSON-only copy, rejecting non-canonical values."""

    return json.loads(canonical_json_bytes(value))


def _resolve_json_pointer(document: Mapping[str, Any], json_pointer: str) -> Any:
    current: Any = document
    for encoded in json_pointer.removeprefix("/").split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _source_fact(canonical_study: Mapping[str, Any], json_pointer: str) -> dict[str, Any]:
    value = _resolve_json_pointer(canonical_study, json_pointer)
    if value is _MISSING:
        return {
            "state": "source_missing",
            "value": None,
            "source_json_path": json_pointer,
        }
    if value is None:
        return {
            "state": "source_null",
            "value": None,
            "source_json_path": json_pointer,
        }
    return {
        "state": "observed",
        "value": _json_copy(value),
        "source_json_path": json_pointer,
    }


def _snapshot_id(
    source_snapshot: Mapping[str, Any], source_version_ordinal: int
) -> str:
    """Create a stable, content-addressed projection identifier.

    A current-only source snapshot has no complete-history claim.  The ordinal
    is therefore caller-supplied and retained as explicit ordering metadata;
    the source snapshot ID and canonical content hash make the projection ID
    stable across equivalent mapping orderings.
    """

    nct_id = source_snapshot["nct_id"]
    canonical_sha = source_snapshot["canonical_content_sha256"]
    source_snapshot_id = source_snapshot["source_snapshot_id"]
    identity = canonical_json_sha256(
        {
            "nct_id": nct_id,
            "source_snapshot_id": source_snapshot_id,
            "canonical_content_sha256": canonical_sha,
            "source_version_ordinal": source_version_ordinal,
        }
    )
    return f"trial_snapshot_{nct_id}_{identity[:24]}"


def validate_trial_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and defensively normalize one bounded trial read projection.

    This validates the public contract, including the self-hash and
    source-fact/authority constraints.  Exact source-evidence binding remains
    the responsibility of the collector publication boundary, which has the
    source snapshot, run, and receipt evidence available together.
    """

    if not isinstance(snapshot, Mapping):
        raise TrialProjectionError("trial_snapshot_must_be_a_mapping")
    try:
        normalized = _json_copy(snapshot)
        if not isinstance(normalized, dict):  # Defensive: JSON object required.
            raise TrialProjectionError("trial_snapshot_must_be_a_json_object")
        validate_contract("trial_snapshot.v1", normalized)
    except TrialProjectionError:
        raise
    except (ContractError, TypeError, ValueError) as exc:
        raise TrialProjectionError("invalid_trial_snapshot") from exc
    return normalized


def build_trial_snapshot(
    source_snapshot: Mapping[str, Any], *, source_version_ordinal: int = 1
) -> dict[str, Any]:
    """Build one strict ``trial_snapshot.v1`` from a source snapshot.

    Only exact registered paths in the validated canonical study are copied.
    Missing and explicit-null source values remain distinct; no field is
    inferred, relabelled, or filled from surrounding source data.
    """

    if isinstance(source_version_ordinal, bool) or not isinstance(
        source_version_ordinal, int
    ) or source_version_ordinal < 1:
        raise TrialProjectionError("invalid_source_version_ordinal")
    if not isinstance(source_snapshot, Mapping):
        raise TrialProjectionError("trial_source_snapshot_must_be_a_mapping")

    try:
        source = _json_copy(source_snapshot)
        if not isinstance(source, dict):  # Defensive: JSON object required.
            raise TrialProjectionError("trial_source_snapshot_must_be_a_json_object")
        validate_contract("trial_source_snapshot.v1", source)
        canonical_study = source["canonical_study"]
        if not isinstance(canonical_study, Mapping):
            raise TrialProjectionError("canonical_study_must_be_a_mapping")

        projection: dict[str, Any] = {
            "contract_id": "trial_snapshot.v1",
            "schema_version": "1.0.0",
            "snapshot_id": _snapshot_id(source, source_version_ordinal),
            "source_version_ordinal": source_version_ordinal,
            "nct_id": source["nct_id"],
            "source_snapshot_ref": source["source_snapshot_id"],
            "source_record_ref": source["source_record_ref"],
            "canonical_content_sha256": source["canonical_content_sha256"],
            "coverage_class": "current_only",
            "source_attribution": {
                "source_name": "ClinicalTrials.gov",
                "source_uri": source["source_uri"],
                "source_processed_at_raw": source["source_dataset_timestamp_raw"],
                "source_processed_timestamp_timezone": "not_declared_by_source_value",
                "source_last_update_posted_at": source[
                    "source_last_update_posted_at"
                ],
                "submitter_responsibility_note": _SUBMITTER_RESPONSIBILITY_NOTE,
                "modification_note": _MODIFICATION_NOTE,
            },
            "source_published_at": source["source_published_at"],
            "source_effective_at": source["source_effective_at"],
            "retrieved_at": source["retrieved_at"],
            "first_seen_at": source["first_seen_at"],
            "knowledge_cutoff": source["retrieved_at"],
            "valid_from": source["valid_from"],
            "valid_to": source["valid_to"],
            "parser_version": "clinicaltrials_v2_parser.v1",
            "source_schema_version": source["source_schema_version"],
            "license_class": source["license_class"],
            "confidence": {
                "value": 1.0,
                "method": "deterministic_source_parse",
                "meaning": "parser_fidelity_not_real_world_truth",
                "calibrated": False,
            },
            "contradiction_state": "none_known",
            "analyst_review_state": "machine_checked",
            "facts": {
                fact_name: _source_fact(canonical_study, json_path)
                for fact_name, json_path in _FACT_JSON_PATHS.items()
            },
            # A source snapshot carries no evidence-claim identifier.  Emitting
            # an empty list preserves that absence instead of inventing a claim.
            "evidence_claim_refs": [],
            "authority": _json_copy(_AUTHORITY),
            "transaction_from": source["transaction_from"],
            "transaction_to": source["transaction_to"],
            "hash_scope": "canonical_payload_excluding_projection_sha256",
        }
        projection["projection_sha256"] = canonical_json_sha256(projection)
        return validate_trial_snapshot(projection)
    except TrialProjectionError:
        raise
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        raise TrialProjectionError("invalid_trial_source_snapshot") from exc


__all__ = [
    "TrialProjectionError",
    "build_trial_snapshot",
    "validate_trial_snapshot",
]
