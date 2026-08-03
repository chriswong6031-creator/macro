"""Fail-closed BC-N0a facts-only BioCatalyst sector-packet compiler.

The module is deliberately not a collector, a publisher, a clock, or a
governance writer.  ``plan_sector_packet_binding`` exists solely because the
generic ``lobe_run.v1`` contract records an output artifact hash while the
output packet references that run.  A lobe owner can plan the deterministic
packet binding, write its completed run/manifest, and then call
``prepare_sector_packet_inputs``.  The final preparation step verifies the
attestation; it never fills in an authority or a reference on the caller's
behalf.

``compile_sector_packet`` consumes only the immutable, validated preparation
object, so compilation itself has no filesystem, network, or wall-clock
dependency.  The boundary validator uses the repository's existing contract
registry before construction.  Current ``trial_snapshot.v1`` has a scalar
contradiction state but no claim-pair/resolution references; any state other
than ``none_known`` therefore fails closed rather than being flattened into an
empty packet contradiction list.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping, Sequence

from engine.sector_intelligence import (
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
)


_SECTOR = "biopharma"
_SOURCE_ID = "clinicaltrials_gov_v2"
_NCT_ID_RE = re.compile(r"^NCT[0-9]{8}$")
_RUN_ID_RE = re.compile(r"^ctgov_run_[A-Za-z0-9_-]+$")
_REQUIRED_DENIALS = frozenset(
    {
        "originate_signal",
        "raise_authority_from_llm",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
    }
)
_ALLOWED_ACTIONS = frozenset(("observe", "explain"))
_ACTION_ORDER = {"observe": 0, "explain": 1}
_HEALTH_KEYS = frozenset(
    {
        "schema_version",
        "state",
        "enabled",
        "generation_id",
        "configured_nct_count",
        "observed_nct_count",
        "last_attempt_at",
        "last_success_at",
        "source_dataset_timestamp_raw",
        "freshness_budget_seconds",
        "coverage_class",
        "last_error_code",
    }
)
_PREPARATION_SEAL = object()


class SectorPacketError(ValueError):
    """One bounded BC-N0a refusal code."""


@dataclass(frozen=True)
class SectorPacketBinding:
    """The exact output receipt an external lobe run must attest."""

    packet_id: str
    packet_hash: str
    row_count: int


@dataclass(frozen=True)
class _ValidatedSectorPacketInputs:
    """Private canonical bytes minted only by the checked preparation boundary."""

    packet_bytes: bytes
    _seal: object | None = None


def _reject(code: str) -> None:
    raise SectorPacketError(code)


def _ordered_actions(actions: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(actions, key=_ACTION_ORDER.__getitem__))


def _json_object(value: Any, *, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _reject(code)
    try:
        normalized = json.loads(canonical_json_bytes(value))
    except ContractError:
        _reject(code)
    if not isinstance(normalized, dict):
        _reject(code)
    return normalized


def _utc(value: Any, *, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _reject(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _reject(code)
    if parsed.tzinfo is None:
        _reject(code)
    return parsed.astimezone(timezone.utc)


def _canonical_utc(value: Any, *, code: str) -> str:
    _utc(value, code=code)
    assert isinstance(value, str)
    return value


def _validate_health(health: Mapping[str, Any], *, evaluated_at: datetime) -> dict[str, Any]:
    normalized = _json_object(health, code="operational_health_unavailable")
    if set(normalized) != _HEALTH_KEYS:
        _reject("operational_health_unavailable")
    if normalized.get("schema_version") != "biocatalyst_operational_health.v1":
        _reject("operational_health_unavailable")
    if normalized.get("coverage_class") != "current_only":
        _reject("operational_health_unavailable")
    if normalized.get("state") not in {"fresh", "stale", "partial"}:
        _reject("operational_health_unavailable")
    if normalized.get("enabled") is not True:
        _reject("operational_health_unavailable")
    generation_id = normalized.get("generation_id")
    if not isinstance(generation_id, str) or not _RUN_ID_RE.fullmatch(generation_id):
        _reject("operational_health_unavailable")
    for field in ("configured_nct_count", "observed_nct_count", "freshness_budget_seconds"):
        value = normalized.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _reject("operational_health_unavailable")
    if normalized["configured_nct_count"] < normalized["observed_nct_count"]:
        _reject("operational_health_unavailable")
    last_attempt = _utc(normalized.get("last_attempt_at"), code="operational_health_unavailable")
    last_success_value = normalized.get("last_success_at")
    if not isinstance(last_success_value, str):
        _reject("operational_health_unavailable")
    last_success = _utc(last_success_value, code="operational_health_unavailable")
    if last_success > last_attempt or last_attempt > evaluated_at:
        _reject("evaluated_at_unavailable")
    source_timestamp = normalized.get("source_dataset_timestamp_raw")
    if not isinstance(source_timestamp, str) or not source_timestamp:
        _reject("operational_health_unavailable")
    error_code = normalized.get("last_error_code")
    if error_code is not None and (
        not isinstance(error_code, str) or not re.fullmatch(r"[A-Z0-9_]{1,96}", error_code)
    ):
        _reject("operational_health_unavailable")
    if normalized["state"] == "fresh" and error_code is not None:
        _reject("operational_health_unavailable")
    return normalized


def _validate_trial_projections(
    projections: Sequence[Mapping[str, Any]], *, lobe_cutoff: datetime
) -> tuple[dict[str, Any], ...]:
    if isinstance(projections, (str, bytes)) or not isinstance(projections, Sequence):
        _reject("trial_projection_unavailable")
    normalized: list[dict[str, Any]] = []
    nct_ids: set[str] = set()
    for projection in projections:
        payload = _json_object(projection, code="trial_projection_unavailable")
        try:
            validate_contract("trial_snapshot.v1", payload)
        except (ContractError, TypeError, ValueError):
            _reject("trial_projection_unavailable")
        nct_id = payload.get("nct_id")
        if not isinstance(nct_id, str) or not _NCT_ID_RE.fullmatch(nct_id):
            _reject("trial_projection_unavailable")
        if nct_id in nct_ids:
            # There is no claim-pair envelope in this N0a input contract.  A
            # second source cut for the same native entity must never be picked
            # as the "current" fact by implicit ordering.
            _reject("contradiction_reference_unavailable")
        nct_ids.add(nct_id)
        if _utc(payload.get("knowledge_cutoff"), code="trial_projection_unavailable") > lobe_cutoff:
            _reject("knowledge_cutoff_unavailable")
        if _utc(payload.get("transaction_from"), code="trial_projection_unavailable") > lobe_cutoff:
            _reject("knowledge_cutoff_unavailable")
        if payload.get("contradiction_state") != "none_known":
            _reject("contradiction_reference_unavailable")
        facts = payload.get("facts")
        if not isinstance(facts, Mapping) or not any(
            isinstance(fact, Mapping) and fact.get("state") == "observed"
            for fact in facts.values()
        ):
            _reject("trial_projection_unavailable")
        evidence_refs = payload.get("evidence_claim_refs")
        if (
            not isinstance(evidence_refs, list)
            or any(not isinstance(ref, str) or not ref for ref in evidence_refs)
        ):
            _reject("trial_projection_unavailable")
        expected_source_ref = f"src:ctgov:{nct_id}:sha256:{payload.get('canonical_content_sha256')}"
        if payload.get("source_record_ref") != expected_source_ref:
            _reject("trial_projection_unavailable")
        normalized.append(payload)
    if not normalized:
        _reject("trial_projection_unavailable")
    return tuple(sorted(normalized, key=lambda item: item["nct_id"]))


def _validate_governance(
    lobe_run: Mapping[str, Any],
    authority_manifest: Mapping[str, Any],
    *,
    evaluated_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    lobe = _json_object(lobe_run, code="governance_reference_unavailable")
    manifest = _json_object(authority_manifest, code="governance_reference_unavailable")
    try:
        validate_contract("lobe_run.v1", lobe)
        validate_contract("authority_manifest.v1", manifest)
    except (ContractError, TypeError, ValueError):
        _reject("governance_reference_unavailable")
    if lobe.get("sector") != _SECTOR or manifest.get("sector") != _SECTOR:
        _reject("governance_reference_unavailable")
    if lobe.get("status") != "ok" or lobe.get("finished_at") is None:
        _reject("governance_reference_unavailable")
    started = _utc(lobe.get("started_at"), code="governance_reference_unavailable")
    finished = _utc(lobe.get("finished_at"), code="governance_reference_unavailable")
    lobe_cutoff = _utc(lobe.get("knowledge_cutoff"), code="governance_reference_unavailable")
    # A lobe attests completed inputs before this immutable packet is evaluated.
    # The caller may evaluate later (and thereby expose stale operational
    # health), but it may not backdate a packet into an incomplete run.
    if not (lobe_cutoff <= started <= finished <= evaluated_at):
        _reject("evaluated_at_unavailable")
    manifest_id = manifest.get("manifest_id")
    if not isinstance(manifest_id, str) or lobe.get("authority_manifest_ref") != manifest_id:
        _reject("governance_reference_unavailable")
    if manifest.get("artifact_type") != "sector_intelligence_packet.v1":
        _reject("governance_reference_unavailable")
    if manifest.get("publication_tier") != "DISPLAY":
        _reject("governance_reference_unavailable")
    max_authority = manifest.get("max_authority")
    if max_authority not in {"A0_OBSERVE", "A1_EXPLAIN"}:
        _reject("governance_reference_unavailable")
    allowed_actions = manifest.get("allowed_actions")
    if (
        not isinstance(allowed_actions, list)
        or "observe" not in allowed_actions
        or not set(allowed_actions).issubset(_ALLOWED_ACTIONS)
    ):
        _reject("governance_reference_unavailable")
    denials = manifest.get("denied_actions")
    if not isinstance(denials, list) or set(denials) != _REQUIRED_DENIALS:
        _reject("governance_reference_unavailable")
    if not manifest.get("governance_decision_refs"):
        _reject("governance_reference_unavailable")
    kill_switch = manifest.get("kill_switch")
    if not isinstance(kill_switch, Mapping) or kill_switch.get("enabled") is not False:
        _reject("governance_reference_unavailable")
    valid_from = _utc(manifest.get("valid_from"), code="governance_reference_unavailable")
    issued_at = _utc(manifest.get("issued_at"), code="governance_reference_unavailable")
    transaction_from = _utc(manifest.get("transaction_from"), code="governance_reference_unavailable")
    if valid_from > evaluated_at or issued_at > evaluated_at or transaction_from > evaluated_at:
        _reject("governance_reference_unavailable")
    for field in ("valid_to", "expires_at", "transaction_to"):
        value = manifest.get(field)
        if field == "expires_at" and value is None:
            _reject("governance_reference_unavailable")
        if value is not None and _utc(value, code="governance_reference_unavailable") < evaluated_at:
            _reject("governance_reference_unavailable")
    return lobe, manifest, _ordered_actions(allowed_actions)


def _freshness(health: Mapping[str, Any], *, evaluated_at: datetime) -> dict[str, Any]:
    last_success = _utc(health["last_success_at"], code="operational_health_unavailable")
    age_seconds = (evaluated_at - last_success).total_seconds()
    if health["state"] == "fresh" and age_seconds <= health["freshness_budget_seconds"]:
        state = "fresh"
        stale_source_ids: list[str] = []
        unknown_source_ids: list[str] = []
    elif health["state"] in {"fresh", "stale"}:
        state = "stale"
        stale_source_ids = [_SOURCE_ID]
        unknown_source_ids = []
    else:
        state = "degraded"
        stale_source_ids = []
        unknown_source_ids = [_SOURCE_ID]
    return {
        "state": state,
        "oldest_required_source_at": health["last_success_at"],
        "evaluated_at": evaluated_at.isoformat().replace("+00:00", "Z"),
        "stale_source_ids": stale_source_ids,
        "unknown_source_ids": unknown_source_ids,
    }


def _packet_payload(
    *,
    projections: Sequence[Mapping[str, Any]],
    health: Mapping[str, Any],
    evaluated_at: str,
    lobe: Mapping[str, Any],
    manifest: Mapping[str, Any],
    allowed_actions: Sequence[str],
) -> dict[str, Any]:
    evaluated = _utc(evaluated_at, code="evaluated_at_unavailable")
    cutoff = _canonical_utc(lobe["knowledge_cutoff"], code="knowledge_cutoff_unavailable")
    freshness = _freshness(health, evaluated_at=evaluated)
    trial_hashes = sorted(str(projection["projection_sha256"]) for projection in projections)
    identity = {
        "sector": _SECTOR,
        "trial_projection_hashes": trial_hashes,
        "operational_health_sha256": canonical_json_sha256(health),
        "evaluated_at": evaluated_at,
        "knowledge_cutoff": cutoff,
        "lobe_run_ref": lobe["run_id"],
        "authority_manifest_ref": manifest["manifest_id"],
    }
    packet_id = "packet:biopharma:" + canonical_json_sha256(identity)[:24]
    entity_refs = [f"trial:{projection['nct_id']}" for projection in projections]
    source_refs = sorted({str(projection["source_record_ref"]) for projection in projections})
    evidence_refs = sorted(
        {
            str(ref)
            for projection in projections
            for ref in projection["evidence_claim_refs"]
        }
    )
    completeness = health["observed_nct_count"] / health["configured_nct_count"] if health["configured_nct_count"] else 0.0
    quality_state = "complete" if freshness["state"] == "fresh" and completeness == 1 else "degraded"
    warnings = [
        "Current-only ClinicalTrials.gov facts; complete prior history is not implied."
    ]
    if freshness["state"] != "fresh":
        warnings.append("ClinicalTrials.gov operational health is not fresh.")
    return {
        "contract_id": "sector_intelligence_packet.v1",
        "schema_version": "1.0.0",
        "packet_id": packet_id,
        "packet_version": 1,
        "sector": _SECTOR,
        "producer": {
            "service": "biocatalyst-sector-packet",
            "code_version": "bc-n0a.v1",
            "owner": "biocatalyst",
        },
        "generated_at": evaluated_at,
        "knowledge_cutoff": cutoff,
        "entity_refs": entity_refs,
        "security_refs": [],
        "portfolio_exposure": [],
        "current_fact_refs": evidence_refs,
        "material_change_event_refs": [],
        "upcoming_event_refs": [],
        "contradictions": [],
        "freshness": freshness,
        "quality": {
            "state": quality_state,
            "completeness": completeness,
            "point_in_time_safe": True,
            "warnings": warnings,
        },
        "feature_snapshot_refs": [],
        "prediction_refs": [],
        "evidence_claim_refs": evidence_refs,
        "source_record_refs": source_refs,
        "lobe_run_ref": lobe["run_id"],
        "authority_manifest_ref": manifest["manifest_id"],
        "authority_caps": {
            "max_authority": manifest["max_authority"],
            "allowed_actions": list(allowed_actions),
            "forbidden_actions": sorted(_REQUIRED_DENIALS),
            "llm_may_originate_signals": False,
        },
        "hash_scope": "canonical_payload_excluding_packet_hash",
    }


def _binding_for_payload(payload: Mapping[str, Any], *, row_count: int) -> SectorPacketBinding:
    packet = dict(payload)
    packet["packet_hash"] = canonical_json_sha256(packet)
    return SectorPacketBinding(
        packet_id=str(packet["packet_id"]),
        packet_hash=str(packet["packet_hash"]),
        row_count=row_count,
    )


def _validate_lobe_binding(
    lobe: Mapping[str, Any], manifest: Mapping[str, Any], binding: SectorPacketBinding
) -> None:
    if manifest.get("artifact_ref") != binding.packet_id:
        _reject("governance_reference_unavailable")
    matching = [
        item
        for item in lobe.get("output_artifacts", [])
        if isinstance(item, Mapping) and item.get("artifact_ref") == binding.packet_id
    ]
    if len(matching) != 1:
        _reject("governance_reference_unavailable")
    output = matching[0]
    if output.get("content_sha256") != binding.packet_hash or output.get("row_count") != binding.row_count:
        _reject("governance_reference_unavailable")


def _validate_lobe_input_hashes(
    lobe: Mapping[str, Any], projections: Sequence[Mapping[str, Any]], health: Mapping[str, Any]
) -> None:
    expected = sorted(
        [canonical_json_sha256(health)]
        + [str(projection["projection_sha256"]) for projection in projections]
    )
    if lobe.get("input_hashes") != expected:
        _reject("governance_reference_unavailable")


def _prepare(
    *,
    trial_projections: Sequence[Mapping[str, Any]],
    operational_health: Mapping[str, Any],
    evaluated_at: str,
    lobe_run: Mapping[str, Any],
    authority_manifest: Mapping[str, Any],
    require_binding: bool,
) -> tuple[dict[str, Any], SectorPacketBinding]:
    evaluated = _utc(evaluated_at, code="evaluated_at_unavailable")
    lobe, manifest, allowed_actions = _validate_governance(
        lobe_run, authority_manifest, evaluated_at=evaluated
    )
    health = _validate_health(operational_health, evaluated_at=evaluated)
    projections = _validate_trial_projections(
        trial_projections,
        lobe_cutoff=_utc(lobe["knowledge_cutoff"], code="knowledge_cutoff_unavailable"),
    )
    if health["observed_nct_count"] != len(projections):
        _reject("operational_health_unavailable")
    payload = _packet_payload(
        projections=projections,
        health=health,
        evaluated_at=evaluated_at,
        lobe=lobe,
        manifest=manifest,
        allowed_actions=allowed_actions,
    )
    binding = _binding_for_payload(payload, row_count=len(projections))
    if require_binding:
        _validate_lobe_input_hashes(lobe, projections, health)
        _validate_lobe_binding(lobe, manifest, binding)
    return payload, binding


def plan_sector_packet_binding(
    *,
    trial_projections: Sequence[Mapping[str, Any]],
    operational_health: Mapping[str, Any],
    evaluated_at: str,
    lobe_run_ref: str,
    lobe_knowledge_cutoff: str,
    authority_manifest_ref: str,
    max_authority: str,
    allowed_actions: Sequence[str],
) -> SectorPacketBinding:
    """Return a non-authorizing receipt for an external two-pass lobe run.

    This helper deliberately accepts references, not lobe or authority
    documents.  Its return value is neither a packet nor a governance grant;
    it exists only so the external lobe owner can create a *valid*, completed
    ``lobe_run.v1.output_artifacts`` entry.  Final construction independently
    validates the injected documents and exact binding through
    :func:`prepare_sector_packet_inputs`.
    """

    evaluated = _utc(evaluated_at, code="evaluated_at_unavailable")
    if not isinstance(lobe_run_ref, str) or not lobe_run_ref:
        _reject("governance_reference_unavailable")
    if not isinstance(authority_manifest_ref, str) or not authority_manifest_ref:
        _reject("governance_reference_unavailable")
    cutoff = _canonical_utc(lobe_knowledge_cutoff, code="knowledge_cutoff_unavailable")
    cutoff_dt = _utc(cutoff, code="knowledge_cutoff_unavailable")
    if cutoff_dt > evaluated:
        _reject("evaluated_at_unavailable")
    if max_authority not in {"A0_OBSERVE", "A1_EXPLAIN"}:
        _reject("governance_reference_unavailable")
    if (
        isinstance(allowed_actions, (str, bytes))
        or not isinstance(allowed_actions, Sequence)
        or "observe" not in allowed_actions
        or not set(allowed_actions).issubset(_ALLOWED_ACTIONS)
    ):
        _reject("governance_reference_unavailable")
    health = _validate_health(operational_health, evaluated_at=evaluated)
    projections = _validate_trial_projections(
        trial_projections, lobe_cutoff=cutoff_dt
    )
    if health["observed_nct_count"] != len(projections):
        _reject("operational_health_unavailable")
    payload = _packet_payload(
        projections=projections,
        health=health,
        evaluated_at=evaluated_at,
        lobe={"run_id": lobe_run_ref, "knowledge_cutoff": cutoff},
        manifest={
            "manifest_id": authority_manifest_ref,
            "max_authority": max_authority,
        },
        allowed_actions=_ordered_actions(allowed_actions),
    )
    return _binding_for_payload(payload, row_count=len(projections))


def prepare_sector_packet_inputs(
    *,
    trial_projections: Sequence[Mapping[str, Any]],
    operational_health: Mapping[str, Any],
    evaluated_at: str,
    lobe_run: Mapping[str, Any],
    authority_manifest: Mapping[str, Any],
) -> _ValidatedSectorPacketInputs:
    """Validate all external inputs and return immutable compiler input bytes."""

    payload, binding = _prepare(
        trial_projections=trial_projections,
        operational_health=operational_health,
        evaluated_at=evaluated_at,
        lobe_run=lobe_run,
        authority_manifest=authority_manifest,
        require_binding=True,
    )
    packet = dict(payload)
    packet["packet_hash"] = binding.packet_hash
    try:
        validate_contract("sector_intelligence_packet.v1", packet)
        packet_bytes = canonical_json_bytes(packet)
    except (ContractError, TypeError, ValueError):
        _reject("packet_contract_unavailable")
    return _ValidatedSectorPacketInputs(
        packet_bytes=packet_bytes, _seal=_PREPARATION_SEAL
    )


def compile_sector_packet(inputs: _ValidatedSectorPacketInputs) -> dict[str, Any]:
    """Materialize one deterministic packet with no external side effects."""

    if (
        not isinstance(inputs, _ValidatedSectorPacketInputs)
        or inputs._seal is not _PREPARATION_SEAL
    ):
        _reject("validated_inputs_required")
    try:
        packet = json.loads(inputs.packet_bytes)
    except (TypeError, ValueError):
        _reject("validated_inputs_required")
    if not isinstance(packet, dict):
        _reject("validated_inputs_required")
    declared_hash = packet.pop("packet_hash", None)
    if declared_hash != canonical_json_sha256(packet):
        _reject("validated_inputs_required")
    packet["packet_hash"] = declared_hash
    return packet


__all__ = [
    "SectorPacketBinding",
    "SectorPacketError",
    "compile_sector_packet",
    "plan_sector_packet_binding",
    "prepare_sector_packet_inputs",
]
