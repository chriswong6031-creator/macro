"""Fail-closed BC-N0a facts-only BioCatalyst sector-packet compiler.

The module is deliberately not a collector, a publisher, a clock, or a
governance writer.  ``plan_sector_packet_binding`` exists solely because the
generic ``lobe_run.v1`` contract records an output artifact hash while the
output packet references that run.  A lobe owner can plan the deterministic
packet binding, write its completed run/manifest, and then call
``prepare_sector_packet_inputs``.  The final preparation step verifies the
attestation; it never fills in an authority or a reference on the caller's
behalf.

``compile_sector_packet`` consumes immutable packet bytes plus the exact
bounded canonical context captured during preparation. It revalidates that
context, reconstructs the packet and binding, requires byte equality, and then
rechecks both the generic packet contract and N0a's stricter facts-only carrier
invariants. The boundary validator uses the repository's existing contract
registry before construction. Current ``trial_snapshot.v1`` has neither an
independently attested claim allowlist nor claim-pair/resolution references.
N0a therefore emits empty evidence/current-fact lanes, and any contradiction
state other than ``none_known`` fails closed rather than being flattened into
an empty packet contradiction list.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
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
_ENTITY_REF_RE = re.compile(r"^trial:(NCT[0-9]{8})$")
_SOURCE_REF_RE = re.compile(r"^src:ctgov:(NCT[0-9]{8}):sha256:[a-f0-9]{64}$")
_EVIDENCE_REF_RE = re.compile(
    r"^claim:trial:(NCT[0-9]{8}):[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}$"
)
_CTGOV_DATA_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})?$"
)
_RUN_ID_RE = re.compile(r"^ctgov_run_[A-Za-z0-9_-]+$")
_PACKET_ID_RE = re.compile(r"^packet:biopharma:[a-f0-9]{24}$")
_PRODUCER = {
    "service": "biocatalyst-sector-packet",
    "code_version": "bc-n0a.v1",
    "owner": "biocatalyst",
}
_MAX_TRIAL_PROJECTIONS = 100
_MAX_TRIAL_PROJECTION_BYTES = 256 * 1024
_MAX_AGGREGATE_PROJECTION_BYTES = 1024 * 1024
_MAX_EVIDENCE_REFS_PER_PROJECTION = 32
_MAX_EVIDENCE_REFS = 1000
_MAX_PACKET_BYTES = 1024 * 1024
_MAX_OPERATIONAL_HEALTH_BYTES = 16 * 1024
_MAX_GOVERNANCE_DOCUMENT_BYTES = 256 * 1024
_MAX_JSON_NODES = 20_000
_MAX_JSON_DEPTH = 32
_MAX_JSON_CONTAINER_ITEMS = 4_096
_MAX_TIMESTAMP_CHARS = 64
# The active ClinicalTrials.gov source row in
# config/biocatalyst_launch_slo_manifest.yml pins maximum_seconds to 7200.
# N0a treats the public health DTO's copy as an attestation to that frozen SLO,
# never as caller-controlled freshness authority.
_CTGOV_FRESHNESS_BUDGET_SECONDS = 7_200
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
    """Immutable canonical material minted by the preparation boundary."""

    packet_bytes: bytes
    trial_projection_bytes: tuple[bytes, ...]
    operational_health_bytes: bytes
    lobe_run_bytes: bytes
    authority_manifest_bytes: bytes
    evaluated_at: str
    _seal: object | None = None


@dataclass(frozen=True)
class _PreparedSectorPacketMaterial:
    """Canonical output plus the exact normalized context that produced it."""

    packet_bytes: bytes
    trial_projection_bytes: tuple[bytes, ...]
    operational_health_bytes: bytes
    lobe_run_bytes: bytes
    authority_manifest_bytes: bytes
    evaluated_at: str


def _reject(code: str) -> None:
    raise SectorPacketError(code)


def _preflight_json_object(value: Any, *, code: str, max_bytes: int) -> int:
    """Bound a JSON-shaped injected object before canonical serialization.

    The byte total is a conservative upper bound: every string character is
    charged as a six-byte JSON escape.  It deliberately refuses some very
    large-but-valid Unicode payloads rather than allocating a potentially
    unbounded canonical serialization at this private boundary.
    """

    if not isinstance(value, Mapping):
        _reject(code)
    estimated_bytes = 0
    node_count = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        node_count += 1
        if node_count > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _reject(code)
        if isinstance(node, Mapping):
            if len(node) > _MAX_JSON_CONTAINER_ITEMS:
                _reject(code)
            estimated_bytes += 2 + max(0, len(node) - 1)
            for key, child in node.items():
                if not isinstance(key, str):
                    _reject(code)
                estimated_bytes += 3 + 6 * len(key)  # quoted key plus colon
                stack.append((child, depth + 1))
        elif isinstance(node, (list, tuple)):
            if len(node) > _MAX_JSON_CONTAINER_ITEMS:
                _reject(code)
            estimated_bytes += 2 + max(0, len(node) - 1)
            stack.extend((child, depth + 1) for child in node)
        elif isinstance(node, str):
            estimated_bytes += 2 + 6 * len(node)
        elif node is None:
            estimated_bytes += 4
        elif isinstance(node, bool):
            estimated_bytes += 5
        elif isinstance(node, int):
            try:
                estimated_bytes += len(str(node))
            except ValueError:
                _reject(code)
        elif isinstance(node, float):
            if not math.isfinite(node):
                _reject(code)
            estimated_bytes += len(repr(node))
        else:
            _reject(code)
        if estimated_bytes > max_bytes:
            _reject(code)
    return estimated_bytes


def _preflight_raw_json_bytes(payload: bytes, *, code: str) -> None:
    """Bound nesting and approximate nodes before the recursive JSON decoder.

    This lexical pass understands JSON strings and escapes well enough to
    ignore structural characters inside strings. The real decoder still owns
    syntax validation; this pass only ensures hostile nesting never reaches it.
    """

    depth = 0
    node_count = 1
    in_string = False
    escaped = False
    for character in payload:
        if in_string:
            if escaped:
                escaped = False
            elif character == 0x5C:  # backslash
                escaped = True
            elif character == 0x22:  # quote
                in_string = False
            continue
        if character == 0x22:
            in_string = True
        elif character in {0x5B, 0x7B}:  # [ or {
            depth += 1
            node_count += 1
            if depth > _MAX_JSON_DEPTH:
                _reject(code)
        elif character in {0x5D, 0x7D}:  # ] or }
            depth -= 1
            if depth < 0:
                _reject(code)
        elif character == 0x2C:  # comma: at least one additional value/member
            node_count += 1
        if node_count > _MAX_JSON_NODES:
            _reject(code)
    if in_string or escaped or depth != 0:
        _reject(code)


def _decode_canonical_json_object_bytes(
    payload: Any, *, code: str, max_bytes: int
) -> tuple[dict[str, Any], int]:
    """Decode one bounded canonical object without trusting recursive parsing."""

    if not isinstance(payload, bytes) or len(payload) > max_bytes:
        _reject(code)
    _preflight_raw_json_bytes(payload, code=code)
    try:
        normalized = json.loads(payload)
    except (TypeError, ValueError, RecursionError, MemoryError):
        _reject(code)
    if not isinstance(normalized, dict):
        _reject(code)
    preflight_bytes = _preflight_json_object(
        normalized, code=code, max_bytes=max_bytes
    )
    try:
        if canonical_json_bytes(normalized) != payload:
            _reject(code)
    except (ContractError, TypeError, ValueError, RecursionError, MemoryError):
        _reject(code)
    return normalized, preflight_bytes


def _ordered_actions(actions: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(actions, key=_ACTION_ORDER.__getitem__))


def _json_object(value: Any, *, code: str, max_bytes: int) -> dict[str, Any]:
    _preflight_json_object(value, code=code, max_bytes=max_bytes)
    try:
        normalized = json.loads(canonical_json_bytes(value))
    except ContractError:
        _reject(code)
    if not isinstance(normalized, dict):
        _reject(code)
    return normalized


def _canonical_json_object_bytes(
    value: Any, *, code: str, max_bytes: int
) -> tuple[dict[str, Any], bytes, int]:
    preflight_bytes = _preflight_json_object(value, code=code, max_bytes=max_bytes)
    try:
        payload = canonical_json_bytes(value)
        normalized = json.loads(payload)
    except (ContractError, TypeError, ValueError):
        _reject(code)
    if not isinstance(normalized, dict):
        _reject(code)
    return normalized, payload, preflight_bytes


def _utc(value: Any, *, code: str) -> datetime:
    if (
        not isinstance(value, str)
        or len(value) > _MAX_TIMESTAMP_CHARS
        or not value.endswith("Z")
    ):
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


def _explicit_source_clock(value: Any, *, code: str) -> datetime | None:
    """Return an explicit-offset ClinicalTrials version clock, or unknown.

    CT.gov has historically emitted timestamps without a timezone.  Those are
    intentionally not coerced to UTC: the caller may retain the fact but N0a
    must expose freshness as unknown until a receipt supplies an explicit
    offset or ``Z``.
    """

    # Keep this lexical contract exactly aligned with the shared
    # ``ctgov-data-timestamp`` format checker.  Do not let
    # ``datetime.fromisoformat`` broaden a representation into a supported
    # source clock merely because Python happens to parse it.
    if not isinstance(value, str) or not _CTGOV_DATA_TIMESTAMP_RE.fullmatch(value):
        _reject(code)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        _reject(code)
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _validate_health(
    health: Mapping[str, Any], *, evaluated_at: datetime, lobe_cutoff: datetime
) -> dict[str, Any]:
    normalized = _json_object(
        health,
        code="operational_health_unavailable",
        max_bytes=_MAX_OPERATIONAL_HEALTH_BYTES,
    )
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
    if normalized["freshness_budget_seconds"] != _CTGOV_FRESHNESS_BUDGET_SECONDS:
        _reject("operational_health_unavailable")
    last_attempt = _utc(normalized.get("last_attempt_at"), code="operational_health_unavailable")
    last_success_value = normalized.get("last_success_at")
    if not isinstance(last_success_value, str):
        _reject("operational_health_unavailable")
    last_success = _utc(last_success_value, code="operational_health_unavailable")
    if (
        last_success > last_attempt
        or last_attempt > lobe_cutoff
        or last_success > lobe_cutoff
        or lobe_cutoff > evaluated_at
    ):
        _reject("knowledge_cutoff_unavailable")
    source_timestamp = normalized.get("source_dataset_timestamp_raw")
    source_clock = _explicit_source_clock(
        source_timestamp, code="operational_health_unavailable"
    )
    if source_clock is not None and (
        source_clock > lobe_cutoff or source_clock > evaluated_at
    ):
        _reject("knowledge_cutoff_unavailable")
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
    if not projections or len(projections) > _MAX_TRIAL_PROJECTIONS:
        _reject("trial_projection_unavailable")
    normalized: list[dict[str, Any]] = []
    nct_ids: set[str] = set()
    aggregate_bytes = 0
    aggregate_preflight_bytes = 0
    aggregate_evidence_refs = 0
    for projection in projections:
        payload, projection_bytes, preflight_bytes = _canonical_json_object_bytes(
            projection,
            code="trial_projection_unavailable",
            max_bytes=_MAX_TRIAL_PROJECTION_BYTES,
        )
        if len(projection_bytes) > _MAX_TRIAL_PROJECTION_BYTES:
            _reject("trial_projection_unavailable")
        aggregate_preflight_bytes += preflight_bytes
        if aggregate_preflight_bytes > _MAX_AGGREGATE_PROJECTION_BYTES:
            _reject("trial_projection_unavailable")
        aggregate_bytes += len(projection_bytes)
        if aggregate_bytes > _MAX_AGGREGATE_PROJECTION_BYTES:
            _reject("trial_projection_unavailable")
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
            or len(evidence_refs) > _MAX_EVIDENCE_REFS_PER_PROJECTION
            or any(not isinstance(ref, str) or not ref for ref in evidence_refs)
        ):
            _reject("trial_projection_unavailable")
        aggregate_evidence_refs += len(evidence_refs)
        if aggregate_evidence_refs > _MAX_EVIDENCE_REFS:
            _reject("trial_projection_unavailable")
        for evidence_ref in evidence_refs:
            match = _EVIDENCE_REF_RE.fullmatch(evidence_ref)
            if match is None or match.group(1) != nct_id:
                _reject("trial_projection_unavailable")
        expected_source_ref = f"src:ctgov:{nct_id}:sha256:{payload.get('canonical_content_sha256')}"
        if payload.get("source_record_ref") != expected_source_ref:
            _reject("trial_projection_unavailable")
        normalized.append(payload)
    return tuple(sorted(normalized, key=lambda item: item["nct_id"]))


def _validate_governance(
    lobe_run: Mapping[str, Any],
    authority_manifest: Mapping[str, Any],
    *,
    evaluated_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    lobe = _json_object(
        lobe_run,
        code="governance_reference_unavailable",
        max_bytes=_MAX_GOVERNANCE_DOCUMENT_BYTES,
    )
    manifest = _json_object(
        authority_manifest,
        code="governance_reference_unavailable",
        max_bytes=_MAX_GOVERNANCE_DOCUMENT_BYTES,
    )
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
    source_clock = _explicit_source_clock(
        health["source_dataset_timestamp_raw"], code="operational_health_unavailable"
    )
    if source_clock is None:
        state = "unknown"
        stale_source_ids: list[str] = []
        unknown_source_ids: list[str] = [_SOURCE_ID]
        oldest_required_source_at: str | None = None
    elif health["state"] == "fresh" and (
        evaluated_at - source_clock
    ).total_seconds() <= health["freshness_budget_seconds"]:
        state = "fresh"
        stale_source_ids: list[str] = []
        unknown_source_ids: list[str] = []
        oldest_required_source_at = health["source_dataset_timestamp_raw"]
    elif health["state"] in {"fresh", "stale"}:
        state = "stale"
        stale_source_ids = [_SOURCE_ID]
        unknown_source_ids = []
        oldest_required_source_at = health["source_dataset_timestamp_raw"]
    else:
        state = "degraded"
        stale_source_ids = []
        unknown_source_ids = [_SOURCE_ID]
        oldest_required_source_at = health["source_dataset_timestamp_raw"]
    return {
        "state": state,
        "oldest_required_source_at": oldest_required_source_at,
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
    # ``trial_snapshot.v1`` contains strings named evidence_claim_refs but no
    # independently attested allowlist binding those strings to claim
    # artifacts. N0a therefore carries none of them as public/current facts.
    evidence_refs: list[str] = []
    completeness = health["observed_nct_count"] / health["configured_nct_count"] if health["configured_nct_count"] else 0.0
    quality_state = "complete" if freshness["state"] == "fresh" and completeness == 1 else "degraded"
    warnings = ["Current-only ClinicalTrials.gov facts; complete prior history is not implied."]
    if freshness["state"] == "unknown":
        warnings.append(
            "ClinicalTrials.gov source dataTimestamp has no declared timezone; freshness is unknown."
        )
    if freshness["state"] != "fresh":
        warnings.append("ClinicalTrials.gov source freshness is not confirmed.")
    return {
        "contract_id": "sector_intelligence_packet.v1",
        "schema_version": "1.0.0",
        "packet_id": packet_id,
        "packet_version": 1,
        "sector": _SECTOR,
        "producer": dict(_PRODUCER),
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
    try:
        packet_bytes = canonical_json_bytes(packet)
    except (ContractError, TypeError, ValueError):
        _reject("packet_contract_unavailable")
    # Receipt planning and final preparation share this hard ceiling.  A lobe
    # must never be asked to attest a packet that the compiler cannot emit.
    if len(packet_bytes) > _MAX_PACKET_BYTES:
        _reject("packet_size_unavailable")
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
) -> _PreparedSectorPacketMaterial:
    evaluated = _utc(evaluated_at, code="evaluated_at_unavailable")
    lobe, manifest, allowed_actions = _validate_governance(
        lobe_run, authority_manifest, evaluated_at=evaluated
    )
    health = _validate_health(
        operational_health,
        evaluated_at=evaluated,
        lobe_cutoff=_utc(lobe["knowledge_cutoff"], code="knowledge_cutoff_unavailable"),
    )
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
    packet = dict(payload)
    packet["packet_hash"] = binding.packet_hash
    try:
        validate_contract("sector_intelligence_packet.v1", packet)
        packet_bytes = canonical_json_bytes(packet)
        projection_bytes = tuple(
            canonical_json_bytes(projection) for projection in projections
        )
        health_bytes = canonical_json_bytes(health)
        lobe_bytes = canonical_json_bytes(lobe)
        manifest_bytes = canonical_json_bytes(manifest)
    except (ContractError, TypeError, ValueError, RecursionError, MemoryError):
        _reject("packet_contract_unavailable")
    if len(packet_bytes) > _MAX_PACKET_BYTES:
        _reject("packet_size_unavailable")
    return _PreparedSectorPacketMaterial(
        packet_bytes=packet_bytes,
        trial_projection_bytes=projection_bytes,
        operational_health_bytes=health_bytes,
        lobe_run_bytes=lobe_bytes,
        authority_manifest_bytes=manifest_bytes,
        evaluated_at=evaluated_at,
    )


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
    health = _validate_health(
        operational_health, evaluated_at=evaluated, lobe_cutoff=cutoff_dt
    )
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
    """Validate inputs and retain their exact immutable normalized context."""

    material = _prepare(
        trial_projections=trial_projections,
        operational_health=operational_health,
        evaluated_at=evaluated_at,
        lobe_run=lobe_run,
        authority_manifest=authority_manifest,
        require_binding=True,
    )
    return _ValidatedSectorPacketInputs(
        packet_bytes=material.packet_bytes,
        trial_projection_bytes=material.trial_projection_bytes,
        operational_health_bytes=material.operational_health_bytes,
        lobe_run_bytes=material.lobe_run_bytes,
        authority_manifest_bytes=material.authority_manifest_bytes,
        evaluated_at=material.evaluated_at,
        _seal=_PREPARATION_SEAL,
    )


def _validated_ref_list(value: Any, *, pattern: re.Pattern[str], code: str) -> list[re.Match[str]]:
    if not isinstance(value, list):
        _reject(code)
    matches: list[re.Match[str]] = []
    for ref in value:
        if not isinstance(ref, str):
            _reject(code)
        match = pattern.fullmatch(ref)
        if match is None:
            _reject(code)
        matches.append(match)
    return matches


def _validate_compiled_packet(packet: Mapping[str, Any], *, packet_bytes: bytes) -> None:
    """Recheck every N0a invariant on the final canonical carrier.

    ``_PREPARATION_SEAL`` is deliberately only misuse friction: Python callers
    can import private names.  The actual security boundary is this complete,
    deterministic validation of a canonical carrier, including the generic
    packet contract, before any result leaves the compiler.
    """

    code = "compiled_packet_unavailable"
    if len(packet_bytes) > _MAX_PACKET_BYTES:
        _reject(code)
    try:
        validate_contract("sector_intelligence_packet.v1", packet)
    except (ContractError, TypeError, ValueError):
        _reject(code)

    if (
        packet.get("contract_id") != "sector_intelligence_packet.v1"
        or packet.get("schema_version") != "1.0.0"
        or packet.get("packet_version") != 1
        or packet.get("sector") != _SECTOR
        or packet.get("producer") != _PRODUCER
        or packet.get("hash_scope") != "canonical_payload_excluding_packet_hash"
        or not isinstance(packet.get("packet_id"), str)
        or _PACKET_ID_RE.fullmatch(packet["packet_id"]) is None
    ):
        _reject(code)

    entity_matches = _validated_ref_list(
        packet.get("entity_refs"), pattern=_ENTITY_REF_RE, code=code
    )
    entity_refs = packet["entity_refs"]
    if (
        not entity_refs
        or len(entity_refs) > _MAX_TRIAL_PROJECTIONS
        or entity_refs != sorted(entity_refs)
    ):
        _reject(code)
    entity_ncts = {match.group(1) for match in entity_matches}
    if len(entity_ncts) != len(entity_refs):
        _reject(code)

    source_matches = _validated_ref_list(
        packet.get("source_record_refs"), pattern=_SOURCE_REF_RE, code=code
    )
    source_refs = packet["source_record_refs"]
    if source_refs != sorted(source_refs) or len(source_refs) != len(entity_refs):
        _reject(code)
    if {match.group(1) for match in source_matches} != entity_ncts:
        _reject(code)

    # No current input contract independently attests a claim allowlist. Any
    # non-empty claim lane is therefore invented provenance, even if its NCT
    # syntax happens to match a packet entity.
    if packet.get("evidence_claim_refs") != [] or packet.get("current_fact_refs") != []:
        _reject(code)

    for lane in (
        "security_refs",
        "portfolio_exposure",
        "material_change_event_refs",
        "upcoming_event_refs",
        "contradictions",
        "feature_snapshot_refs",
        "prediction_refs",
    ):
        if packet.get(lane) != []:
            _reject(code)

    generated_at = _utc(packet.get("generated_at"), code=code)
    knowledge_cutoff = _utc(packet.get("knowledge_cutoff"), code=code)
    if knowledge_cutoff > generated_at:
        _reject(code)
    freshness = packet.get("freshness")
    quality = packet.get("quality")
    if not isinstance(freshness, Mapping) or not isinstance(quality, Mapping):
        _reject(code)
    if freshness.get("evaluated_at") != packet.get("generated_at"):
        _reject(code)
    _utc(freshness.get("evaluated_at"), code=code)
    freshness_state = freshness.get("state")
    oldest = freshness.get("oldest_required_source_at")
    stale_sources = freshness.get("stale_source_ids")
    unknown_sources = freshness.get("unknown_source_ids")
    if oldest is None:
        expected_freshness_state = "unknown"
        if stale_sources != [] or unknown_sources != [_SOURCE_ID]:
            _reject(code)
    elif isinstance(oldest, str):
        source_clock = (
            _explicit_source_clock(oldest, code=code)
        )
        if (
            source_clock is None
            or source_clock > knowledge_cutoff
            or source_clock > generated_at
        ):
            _reject(code)
        age_seconds = (generated_at - source_clock).total_seconds()
        if stale_sources == [_SOURCE_ID] and unknown_sources == []:
            expected_freshness_state = "stale"
        elif stale_sources == [] and unknown_sources == [_SOURCE_ID]:
            expected_freshness_state = "degraded"
        elif (
            stale_sources == []
            and unknown_sources == []
            and age_seconds <= _CTGOV_FRESHNESS_BUDGET_SECONDS
        ):
            expected_freshness_state = "fresh"
        else:
            _reject(code)
    else:
        _reject(code)
    if freshness_state != expected_freshness_state:
        _reject(code)

    completeness = quality.get("completeness")
    if (
        isinstance(completeness, bool)
        or not isinstance(completeness, (int, float))
        or not 0 <= completeness <= 1
        or quality.get("point_in_time_safe") is not True
    ):
        _reject(code)
    expected_quality = (
        "complete" if freshness_state == "fresh" and completeness == 1 else "degraded"
    )
    if quality.get("state") != expected_quality:
        _reject(code)
    warnings = quality.get("warnings")
    expected_warnings = [
        "Current-only ClinicalTrials.gov facts; complete prior history is not implied."
    ]
    if freshness_state == "unknown":
        expected_warnings.append(
            "ClinicalTrials.gov source dataTimestamp has no declared timezone; freshness is unknown."
        )
    if freshness_state != "fresh":
        expected_warnings.append("ClinicalTrials.gov source freshness is not confirmed.")
    if warnings != expected_warnings:
        _reject(code)

    caps = packet.get("authority_caps")
    if not isinstance(caps, Mapping) or caps.get("max_authority") not in {
        "A0_OBSERVE",
        "A1_EXPLAIN",
    }:
        _reject(code)
    actions = caps.get("allowed_actions")
    if (
        not isinstance(actions, list)
        or actions != list(_ordered_actions(actions))
        or not actions
        or "observe" not in actions
        or not set(actions).issubset(_ALLOWED_ACTIONS)
        or (
            caps["max_authority"] == "A0_OBSERVE"
            and actions != ["observe"]
        )
        or caps.get("forbidden_actions") != sorted(_REQUIRED_DENIALS)
        or caps.get("llm_may_originate_signals") is not False
    ):
        _reject(code)


def compile_sector_packet(inputs: _ValidatedSectorPacketInputs) -> dict[str, Any]:
    """Reconstruct and materialize one deterministic packet without side effects."""

    if (
        not isinstance(inputs, _ValidatedSectorPacketInputs)
        or inputs._seal is not _PREPARATION_SEAL
        or not isinstance(inputs.packet_bytes, bytes)
        or len(inputs.packet_bytes) > _MAX_PACKET_BYTES
        or not isinstance(inputs.trial_projection_bytes, tuple)
        or not inputs.trial_projection_bytes
        or len(inputs.trial_projection_bytes) > _MAX_TRIAL_PROJECTIONS
        or not isinstance(inputs.operational_health_bytes, bytes)
        or len(inputs.operational_health_bytes) > _MAX_OPERATIONAL_HEALTH_BYTES
        or not isinstance(inputs.lobe_run_bytes, bytes)
        or len(inputs.lobe_run_bytes) > _MAX_GOVERNANCE_DOCUMENT_BYTES
        or not isinstance(inputs.authority_manifest_bytes, bytes)
        or len(inputs.authority_manifest_bytes) > _MAX_GOVERNANCE_DOCUMENT_BYTES
        or not isinstance(inputs.evaluated_at, str)
        or len(inputs.evaluated_at) > _MAX_TIMESTAMP_CHARS
    ):
        _reject("validated_inputs_required")
    _preflight_raw_json_bytes(inputs.packet_bytes, code="validated_inputs_required")
    try:
        packet = json.loads(inputs.packet_bytes)
    except (TypeError, ValueError, RecursionError, MemoryError):
        _reject("validated_inputs_required")
    if not isinstance(packet, dict):
        _reject("validated_inputs_required")
    # Run the iterative structural bound before calling any recursive
    # canonicalization or schema-validation machinery.
    _preflight_json_object(
        packet,
        code="validated_inputs_required",
        max_bytes=_MAX_PACKET_BYTES * 6,
    )
    try:
        if canonical_json_bytes(packet) != inputs.packet_bytes:
            _reject("validated_inputs_required")
    except (ContractError, TypeError, ValueError, RecursionError, MemoryError):
        _reject("validated_inputs_required")
    declared_hash = packet.get("packet_hash")
    payload = dict(packet)
    payload.pop("packet_hash", None)
    try:
        hash_matches = declared_hash == canonical_json_sha256(payload)
    except (ContractError, TypeError, ValueError, RecursionError, MemoryError):
        _reject("validated_inputs_required")
    if not hash_matches:
        _reject("validated_inputs_required")
    _validate_compiled_packet(packet, packet_bytes=inputs.packet_bytes)

    context_code = "validated_context_required"
    projections: list[dict[str, Any]] = []
    aggregate_bytes = 0
    aggregate_preflight_bytes = 0
    for projection_bytes in inputs.trial_projection_bytes:
        projection, preflight_bytes = _decode_canonical_json_object_bytes(
            projection_bytes,
            code=context_code,
            max_bytes=_MAX_TRIAL_PROJECTION_BYTES,
        )
        aggregate_bytes += len(projection_bytes)
        aggregate_preflight_bytes += preflight_bytes
        if (
            aggregate_bytes > _MAX_AGGREGATE_PROJECTION_BYTES
            or aggregate_preflight_bytes > _MAX_AGGREGATE_PROJECTION_BYTES
        ):
            _reject(context_code)
        projections.append(projection)
    health, _ = _decode_canonical_json_object_bytes(
        inputs.operational_health_bytes,
        code=context_code,
        max_bytes=_MAX_OPERATIONAL_HEALTH_BYTES,
    )
    lobe, _ = _decode_canonical_json_object_bytes(
        inputs.lobe_run_bytes,
        code=context_code,
        max_bytes=_MAX_GOVERNANCE_DOCUMENT_BYTES,
    )
    manifest, _ = _decode_canonical_json_object_bytes(
        inputs.authority_manifest_bytes,
        code=context_code,
        max_bytes=_MAX_GOVERNANCE_DOCUMENT_BYTES,
    )
    _utc(inputs.evaluated_at, code=context_code)
    reconstructed = _prepare(
        trial_projections=projections,
        operational_health=health,
        evaluated_at=inputs.evaluated_at,
        lobe_run=lobe,
        authority_manifest=manifest,
        require_binding=True,
    )
    if (
        reconstructed.packet_bytes != inputs.packet_bytes
        or reconstructed.trial_projection_bytes != inputs.trial_projection_bytes
        or reconstructed.operational_health_bytes != inputs.operational_health_bytes
        or reconstructed.lobe_run_bytes != inputs.lobe_run_bytes
        or reconstructed.authority_manifest_bytes != inputs.authority_manifest_bytes
        or reconstructed.evaluated_at != inputs.evaluated_at
    ):
        _reject("validated_inputs_required")
    return packet


__all__ = [
    "SectorPacketBinding",
    "SectorPacketError",
    "compile_sector_packet",
    "plan_sector_packet_binding",
    "prepare_sector_packet_inputs",
]
