"""Public-safe protocol projections for the facts-only peer-matrix lane.

The worker owns the only transition from a validated private source snapshot to
this projection.  API handlers intentionally receive only the emitted public
artifact, never ``canonical_study`` or a private source snapshot.
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

from .trials import TrialProjectionError, validate_trial_snapshot


class TrialProtocolProjectionError(ValueError):
    """A bounded failure at the private-to-public protocol boundary."""


_MISSING = object()
_ARM_GROUPS_PATH = "/protocolSection/armsInterventionsModule/armGroups"
_ARM_GROUP_LIMIT = 100
_ARM_GROUP_LABEL_MAX = 1000
_ARM_GROUP_TYPE_MAX = 80
_ARM_GROUP_DESCRIPTION_MAX = 6000
_ARM_GROUP_INTERVENTION_NAMES_LIMIT = 100
_ARM_GROUP_INTERVENTION_NAME_MAX = 512
# A publication artifact is a bounded public product, not a lossy raw-record
# tunnel.  Keep the ceiling below the serving response ceiling so one normal
# page can never amplify a single protocol arbitrarily.
_MAX_PROTOCOL_PROJECTION_BYTES = 256 * 1024
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


def _public_arm_groups_fact(canonical_study: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a closed, bounded arm-group shape at the publication boundary.

    The public projection deliberately ignores unregistered upstream keys.  It
    rejects oversized or wrongly typed registered values instead of silently
    truncating them, so the worker cannot publish a partial protocol artifact.
    """

    value = _resolve_json_pointer(canonical_study, _ARM_GROUPS_PATH)
    if value is _MISSING:
        return {
            "state": "source_missing",
            "value": None,
            "source_json_path": _ARM_GROUPS_PATH,
        }
    if value is None:
        return {
            "state": "source_null",
            "value": None,
            "source_json_path": _ARM_GROUPS_PATH,
        }
    if not isinstance(value, list) or len(value) > _ARM_GROUP_LIMIT:
        raise TrialProtocolProjectionError("arm_groups_invalid")

    public_groups: list[dict[str, Any]] = []
    for arm_group in value:
        if not isinstance(arm_group, Mapping):
            raise TrialProtocolProjectionError("arm_groups_invalid")
        label = arm_group.get("label")
        arm_type = arm_group.get("type")
        description = arm_group.get("description")
        intervention_names = arm_group.get("interventionNames")
        if (
            not isinstance(label, str)
            or not label
            or len(label) > _ARM_GROUP_LABEL_MAX
            or (arm_type is not None and (not isinstance(arm_type, str) or len(arm_type) > _ARM_GROUP_TYPE_MAX))
            or (
                description is not None
                and (
                    not isinstance(description, str)
                    or len(description) > _ARM_GROUP_DESCRIPTION_MAX
                )
            )
            or (
                intervention_names is not None
                and (
                    not isinstance(intervention_names, list)
                    or len(intervention_names) > _ARM_GROUP_INTERVENTION_NAMES_LIMIT
                    or any(
                        not isinstance(name, str)
                        or not name
                        or len(name) > _ARM_GROUP_INTERVENTION_NAME_MAX
                        for name in intervention_names
                    )
                )
            )
        ):
            raise TrialProtocolProjectionError("arm_groups_invalid")
        public_groups.append(
            {
                "label": label,
                "type": arm_type,
                "description": description,
                "interventionNames": list(intervention_names or []),
            }
        )
    return {
        "state": "observed",
        "value": public_groups,
        "source_json_path": _ARM_GROUPS_PATH,
    }


def _projection_identity(
    *, nct_id: str, source_snapshot_ref: str, canonical_content_sha256: str
) -> str:
    digest = canonical_json_sha256(
        {
            "nct_id": nct_id,
            "source_snapshot_ref": source_snapshot_ref,
            "canonical_content_sha256": canonical_content_sha256,
        }
    )
    return f"trial_protocol_{nct_id}_{digest[:24]}"


def validate_trial_protocol_projection(
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one immutable, public-safe protocol projection and its hash."""

    if not isinstance(projection, Mapping):
        raise TrialProtocolProjectionError("protocol_projection_must_be_a_mapping")
    try:
        normalized = _json_copy(projection)
        if not isinstance(normalized, dict):
            raise TrialProtocolProjectionError("protocol_projection_must_be_a_json_object")
        validate_contract("trial_protocol_projection.v1", normalized)
    except TrialProtocolProjectionError:
        raise
    except (ContractError, TypeError, ValueError) as exc:
        raise TrialProtocolProjectionError("invalid_trial_protocol_projection") from exc
    return normalized


def build_trial_protocol_projection(
    source_snapshot: Mapping[str, Any],
    trial_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Project protocol facts during publication from one validated source cut.

    ``trial_snapshot`` supplies the already allowlisted public fact fields.
    ``armGroups`` is separately copied here from the private source snapshot,
    because it was deliberately absent from the original list/detail product
    projection.  No caller may pass a loose arm-group object.
    """

    if not isinstance(source_snapshot, Mapping) or not isinstance(
        trial_snapshot, Mapping
    ):
        raise TrialProtocolProjectionError("protocol_projection_inputs_invalid")
    try:
        source = _json_copy(source_snapshot)
        if not isinstance(source, dict):
            raise TrialProtocolProjectionError("trial_source_snapshot_must_be_a_json_object")
        validate_contract("trial_source_snapshot.v1", source)
        trial = validate_trial_snapshot(trial_snapshot)
        canonical_study = source.get("canonical_study")
        if not isinstance(canonical_study, Mapping):
            raise TrialProtocolProjectionError("canonical_study_must_be_a_mapping")
        for key in (
            "nct_id",
            "source_snapshot_ref",
            "source_record_ref",
            "canonical_content_sha256",
            "coverage_class",
        ):
            source_key = "source_snapshot_id" if key == "source_snapshot_ref" else key
            if trial.get(key) != source.get(source_key):
                raise TrialProtocolProjectionError("trial_snapshot_source_binding_mismatch")
        source_attribution = trial.get("source_attribution")
        facts = trial.get("facts")
        if not isinstance(source_attribution, Mapping) or not isinstance(facts, Mapping):
            raise TrialProtocolProjectionError("trial_snapshot_projection_invalid")
        protocol_facts = _json_copy(facts)
        if not isinstance(protocol_facts, dict):
            raise TrialProtocolProjectionError("trial_snapshot_projection_invalid")
        protocol_facts["arm_groups"] = _public_arm_groups_fact(canonical_study)
        nct_id = source["nct_id"]
        projection: dict[str, Any] = {
            "contract_id": "trial_protocol_projection.v1",
            "schema_version": "1.0.0",
            "protocol_projection_id": _projection_identity(
                nct_id=nct_id,
                source_snapshot_ref=source["source_snapshot_id"],
                canonical_content_sha256=source["canonical_content_sha256"],
            ),
            "nct_id": nct_id,
            "source_snapshot_ref": source["source_snapshot_id"],
            "source_record_ref": source["source_record_ref"],
            "canonical_content_sha256": source["canonical_content_sha256"],
            "coverage_class": "current_only",
            "source_attribution": {
                "source_name": source_attribution["source_name"],
                "source_uri": source_attribution["source_uri"],
                "source_last_update_posted_at": source_attribution[
                    "source_last_update_posted_at"
                ],
            },
            "retrieved_at": source["retrieved_at"],
            "first_seen_at": source["first_seen_at"],
            "knowledge_cutoff": source["retrieved_at"],
            "facts": protocol_facts,
            "authority": _json_copy(_AUTHORITY),
            "hash_scope": "canonical_payload_excluding_protocol_projection_sha256",
        }
        projection["protocol_projection_sha256"] = canonical_json_sha256(projection)
        if len(canonical_json_bytes(projection)) > _MAX_PROTOCOL_PROJECTION_BYTES:
            raise TrialProtocolProjectionError("protocol_projection_too_large")
        return validate_trial_protocol_projection(projection)
    except TrialProtocolProjectionError:
        raise
    except (ContractError, KeyError, TypeError, ValueError, TrialProjectionError) as exc:
        raise TrialProtocolProjectionError("invalid_protocol_projection_source") from exc


def validate_trial_protocol_projection_against_source(
    projection: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    trial_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay the exact publication transformation without exposing raw source data."""

    normalized = validate_trial_protocol_projection(projection)
    expected = build_trial_protocol_projection(source_snapshot, trial_snapshot)
    if normalized != expected:
        raise TrialProtocolProjectionError("protocol_projection_source_binding_mismatch")
    return normalized


__all__ = [
    "TrialProtocolProjectionError",
    "build_trial_protocol_projection",
    "validate_trial_protocol_projection",
    "validate_trial_protocol_projection_against_source",
]
