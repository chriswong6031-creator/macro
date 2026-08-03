"""Bounded exact-evidence trial-change classification for BioCatalyst.

This is the backend-only BC-T2b preparatory seam.  It consumes either one
replay-validated adjacent Record History diff or one replay-validated
prospective observation diff.  It emits a deterministic field-class
projection and an explicitly non-canonical, non-deliverable alert projection.

No input diff is trusted on its own.  Retrospective compilation replays the
diff against both immutable source snapshots.  Prospective compilation also
replays both observations and snapshots against their exact archived page
bytes through the existing B1 validator.  Hostile decoded trees and raw bytes
are bounded before canonicalization, schema traversal, or replay.

The prospective activation proofs are pure local consistency checks: callers
must establish the B4E root-owned artifact paths and supply their trusted
activation and target identities.  This compiler freezes the supplied payloads,
replays both source-evidence bundles, and proves each self-hashed gate and
heartbeat live at its corresponding validated run start.  It deliberately does
no filesystem, network, or caller-clock I/O and cannot establish root ownership
itself.

The retrospective entrypoint deliberately treats the already-validated B2
``trial_history_source_snapshot.v1`` contract as its upstream trust boundary.
It proves exact diff replay against those snapshots; it does not claim to
revalidate the earlier history run, receipts, or raw response bytes.  Callers
that need that stronger proof must validate the B2 evidence chain before this
compiler boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping, Sequence

from engine.biocatalyst.activation import (
    ActivationError,
    validate_activation_gate,
    validate_activation_heartbeat,
)
from engine.biocatalyst.prospective import SourceEvidence
from engine.sector_intelligence.contracts import (
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_trial_change_alert_projection,
    validate_trial_change_classification,
    validate_trial_diff_against_snapshots,
    validate_trial_history_diff_against_snapshots,
)


class ChangeClassificationError(ValueError):
    """An internal compiler/output invariant failed."""


@dataclass(frozen=True)
class TrialChangeCompilation:
    """One mutation-isolated classification and its dark alert projection."""

    classification: dict[str, Any]
    projection: dict[str, Any]


@dataclass(frozen=True)
class ProspectiveActivationProof:
    """Exact B4E artifacts and caller-trusted identities for one run side.

    The compiler freezes both documents before passing them to the activation
    validators, then requires both to bind to the caller-supplied expected
    activation and target.  Root-path/root-seal verification stays at the
    caller trust boundary.  Evaluation time is never supplied here: it is
    derived only from the replay-validated source run that this proof guards.
    """

    gate: Mapping[str, Any]
    heartbeat: Mapping[str, Any]
    expected_activation_id: str
    expected_target_binding_sha256: str


_CLASSIFICATION_CONTRACT_ID = "trial_change_classification.v1"
_PROJECTION_CONTRACT_ID = "trial_change_alert_projection.v1"
_HISTORY_DIFF_CONTRACT_ID = "trial_history_exact_diff.v1"
_PROSPECTIVE_DIFF_CONTRACT_ID = "trial_version_diff.v1"
_METHOD = "deterministic_exact_registry_operation_class.v1"

_MAX_INPUT_DOCUMENT_BYTES = 2 * 1024 * 1024
_MAX_RAW_BYTES_PER_SIDE = 8 * 1024 * 1024
_MAX_RAW_BODIES_PER_SIDE = 512
_MAX_RAW_DESCRIPTOR_KEY_BYTES = 512
_MAX_INPUT_NODES = 65_536
_MAX_INPUT_NESTING_DEPTH = 128
_MAX_INPUT_CONTAINER_ITEMS = 16_384
_MAX_OPERATIONS = 4_096
_MAX_ROWS = 4_096
_MAX_CLASSIFICATION_BYTES = 1024 * 1024
_MAX_PROJECTION_BYTES = 1024 * 1024

_CAPACITY = {
    "max_input_document_bytes": _MAX_INPUT_DOCUMENT_BYTES,
    "max_raw_bytes_per_side": _MAX_RAW_BYTES_PER_SIDE,
    "max_raw_bodies_per_side": _MAX_RAW_BODIES_PER_SIDE,
    "max_raw_descriptor_key_bytes": _MAX_RAW_DESCRIPTOR_KEY_BYTES,
    "max_input_nodes": _MAX_INPUT_NODES,
    "max_input_nesting_depth": _MAX_INPUT_NESTING_DEPTH,
    "max_input_container_items": _MAX_INPUT_CONTAINER_ITEMS,
    "max_operations": _MAX_OPERATIONS,
    "max_rows": _MAX_ROWS,
    "max_classification_bytes": _MAX_CLASSIFICATION_BYTES,
    "max_projection_bytes": _MAX_PROJECTION_BYTES,
}

_AUTHORITY = {
    "classification": "deterministic_registry_change_projection",
    "decision_authority": False,
    "maximum_authority": "A1_EXPLAIN",
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "issuer_resolution",
        "security_resolution",
        "asset_resolution",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "neural_web_authority",
        "all_prophet_uses",
        "assess_materiality",
        "assert_protocol_change",
        "assess_correction",
        "deliver_alert",
        "raise_authority",
    ],
}


def _canonical_string_byte_length(value: str, limit: int) -> int | None:
    """Return exact canonical JSON string bytes without allocating an encoding."""

    total = 2
    for character in value:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            return None
        if character in {'"', "\\"} or character in {"\b", "\f", "\n", "\r", "\t"}:
            total += 2
        elif codepoint < 0x20:
            total += 6
        else:
            total += (
                1
                if codepoint <= 0x7F
                else 2
                if codepoint <= 0x7FF
                else 3
                if codepoint <= 0xFFFF
                else 4
            )
        if total > limit:
            return total
    return total


def _freeze_json_input(
    value: Any,
    *,
    max_canonical_bytes: int = _MAX_INPUT_DOCUMENT_BYTES,
    max_nodes: int = _MAX_INPUT_NODES,
    max_nesting_depth: int = _MAX_INPUT_NESTING_DEPTH,
    max_container_items: int = _MAX_INPUT_CONTAINER_ITEMS,
) -> tuple[Any | None, str | None]:
    """Iteratively bound and freeze a finite exact JSON tree.

    Exact ``type`` checks prevent bool-as-int coercion and custom containers
    from running user code during traversal.  Object keys are visited in
    canonical order, making both copies and refusal reasons permutation stable.
    """

    root: list[Any] = [None]
    total = 0
    nodes = 0
    stack: list[tuple[Any, int, list[Any] | dict[str, Any], int | str]] = [
        (value, 0, root, 0)
    ]
    while stack:
        current, depth, parent, slot = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            return None, "node_limit_exceeded"
        if depth > max_nesting_depth:
            return None, "nesting_limit_exceeded"

        current_type = type(current)
        if current_type is str:
            rendered_size = _canonical_string_byte_length(
                current, max_canonical_bytes - total
            )
            if rendered_size is None:
                return None, "must_be_canonical_json"
            total += rendered_size
            frozen: Any = current
        elif current_type is dict:
            items: list[tuple[Any, Any]] = []
            try:
                for key, child in current.items():
                    if len(items) >= max_container_items:
                        return None, "container_limit_exceeded"
                    items.append((key, child))
            except RuntimeError:
                return None, "must_be_canonical_json"
            if len(items) != len(current):
                return None, "must_be_canonical_json"
            if any(type(key) is not str for key, _child in items):
                return None, "must_be_canonical_json"
            item_count = len(items)
            pending_nodes = 2 * item_count
            if nodes + len(stack) + pending_nodes > max_nodes:
                return None, "node_limit_exceeded"
            if item_count and depth + 1 > max_nesting_depth:
                return None, "nesting_limit_exceeded"
            total += 2 + max(0, item_count - 1) + item_count
            nodes += item_count
            if total > max_canonical_bytes:
                return None, "canonical_byte_limit_exceeded"
            invalid_key = False
            for key, _child in items:
                rendered_size = _canonical_string_byte_length(
                    key, max_canonical_bytes - total
                )
                if rendered_size is None:
                    invalid_key = True
                    continue
                total += rendered_size
                if total > max_canonical_bytes:
                    return None, "canonical_byte_limit_exceeded"
            if invalid_key:
                return None, "must_be_canonical_json"
            items.sort(key=lambda item: item[0])
            frozen = {}
            for key, child in reversed(items):
                stack.append((child, depth + 1, frozen, key))
        elif current_type is list:
            item_count = len(current)
            if item_count > max_container_items:
                return None, "container_limit_exceeded"
            items_list: list[Any] = []
            try:
                for index in range(item_count):
                    items_list.append(current[index])
            except IndexError:
                return None, "must_be_canonical_json"
            if len(current) != item_count:
                return None, "must_be_canonical_json"
            if nodes + len(stack) + item_count > max_nodes:
                return None, "node_limit_exceeded"
            total += 2 + max(0, item_count - 1)
            frozen = [None] * item_count
            for index in range(item_count - 1, -1, -1):
                stack.append((items_list[index], depth + 1, frozen, index))
        elif current is None:
            total += 4
            frozen = None
        elif current_type is bool:
            total += 4 if current else 5
            frozen = current
        elif current_type is int:
            remaining = max_canonical_bytes - total
            if current.bit_length() > max(1, remaining) * 4:
                return None, "canonical_byte_limit_exceeded"
            try:
                total += len(str(current))
            except ValueError:
                return None, "must_be_canonical_json"
            frozen = current
        elif current_type is float:
            try:
                rendered = json.dumps(
                    current, allow_nan=False, separators=(",", ":")
                )
            except (TypeError, ValueError):
                return None, "must_be_canonical_json"
            total += len(rendered)
            frozen = current
        else:
            return None, "must_be_canonical_json"

        if total > max_canonical_bytes:
            return None, "canonical_byte_limit_exceeded"
        parent[slot] = frozen
    return root[0], None


def _freeze_document(label: str, value: Any) -> tuple[dict[str, Any] | None, str | None]:
    if value is None:
        return None, "missing_evidence"
    if type(value) is not dict:
        return None, f"input_{label}_must_be_canonical_json"
    frozen, reason = _freeze_json_input(value)
    if reason is not None:
        if reason == "must_be_canonical_json":
            return None, f"input_{label}_must_be_canonical_json"
        return None, f"input_{reason}"
    if type(frozen) is not dict:
        return None, f"input_{label}_must_be_canonical_json"
    return frozen, None


def _freeze_receipts(
    label: str, receipts: Any
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if receipts is None:
        return None, "missing_evidence"
    if type(receipts) not in (list, tuple):
        return None, f"input_{label}_must_be_canonical_json"
    if len(receipts) > _MAX_INPUT_CONTAINER_ITEMS:
        return None, "input_container_limit_exceeded"
    frozen, reason = _freeze_json_input(list(receipts))
    if reason is not None:
        if reason == "must_be_canonical_json":
            return None, f"input_{label}_must_be_canonical_json"
        return None, f"input_{reason}"
    if type(frozen) is not list or any(type(item) is not dict for item in frozen):
        return None, f"input_{label}_must_be_canonical_json"
    return frozen, None


def _freeze_raw_evidence(
    label: str, raw: Any
) -> tuple[dict[str, bytes] | None, str | None]:
    if raw is None:
        return None, "missing_evidence"
    if type(raw) is not dict or len(raw) > _MAX_RAW_BODIES_PER_SIDE:
        return None, f"input_{label}_raw_evidence_invalid"
    try:
        items = list(raw.items())
    except RuntimeError:
        return None, f"input_{label}_raw_evidence_invalid"
    if len(items) != len(raw):
        return None, f"input_{label}_raw_evidence_invalid"
    total = 0
    frozen: dict[str, bytes] = {}
    for key, value in items:
        if type(key) is not str or type(value) not in (bytes, bytearray, memoryview):
            return None, f"input_{label}_raw_evidence_invalid"
        key_size = _canonical_string_byte_length(
            key, _MAX_RAW_DESCRIPTOR_KEY_BYTES
        )
        if key_size is None:
            return None, f"input_{label}_raw_evidence_invalid"
        if key_size > _MAX_RAW_DESCRIPTOR_KEY_BYTES:
            return None, f"input_{label}_raw_key_bytes_limit_exceeded"
        try:
            size = value.nbytes if type(value) is memoryview else len(value)
            frozen_value = bytes(value)
        except (TypeError, ValueError):
            return None, f"input_{label}_raw_evidence_invalid"
        if len(frozen_value) != size:
            return None, f"input_{label}_raw_evidence_invalid"
        total += size
        if total > _MAX_RAW_BYTES_PER_SIDE:
            return None, f"input_{label}_raw_bytes_limit_exceeded"
        frozen[key] = frozen_value
    frozen = dict(sorted(frozen.items()))
    return frozen, None


def _freeze_source_evidence(
    label: str, evidence: Any
) -> tuple[SourceEvidence | None, str | None]:
    if evidence is None:
        return None, "missing_evidence"
    if type(evidence) is not SourceEvidence:
        return None, "schema_profile_mismatch"
    run, reason = _freeze_document(f"{label}_run", evidence.run)
    if reason is not None:
        return None, reason
    snapshot, reason = _freeze_document(f"{label}_snapshot", evidence.snapshot)
    if reason is not None:
        return None, reason
    receipts, reason = _freeze_receipts(f"{label}_receipts", evidence.receipts)
    if reason is not None:
        return None, reason
    raw, reason = _freeze_raw_evidence(label, evidence.raw_page_bodies_by_receipt)
    if reason is not None:
        return None, reason
    assert run is not None and snapshot is not None and receipts is not None and raw is not None
    return SourceEvidence(
        run=run,
        snapshot=snapshot,
        receipts=receipts,
        raw_page_bodies_by_receipt=raw,
    ), None


def _freeze_prospective_activation_proof(
    proof: Any,
) -> tuple[ProspectiveActivationProof | None, str | None]:
    """Freeze one exact B4E proof without I/O or clock reads."""

    if proof is None:
        return None, "prospective_activation_missing"
    if type(proof) is not ProspectiveActivationProof:
        return None, "prospective_activation_invalid"
    if proof.gate is None or proof.heartbeat is None:
        return None, "prospective_activation_missing"
    if (
        type(proof.expected_activation_id) is not str
        or type(proof.expected_target_binding_sha256) is not str
    ):
        return None, "prospective_activation_invalid"
    gate, gate_reason = _freeze_document("prospective_activation_gate", proof.gate)
    heartbeat, heartbeat_reason = _freeze_document(
        "prospective_activation_heartbeat", proof.heartbeat
    )
    if gate_reason is not None or heartbeat_reason is not None:
        return None, "prospective_activation_invalid"
    assert gate is not None and heartbeat is not None
    if (
        gate.get("activation_id") != proof.expected_activation_id
        or heartbeat.get("activation_id") != proof.expected_activation_id
        or gate.get("target_binding_sha256")
        != proof.expected_target_binding_sha256
        or heartbeat.get("target_binding_sha256")
        != proof.expected_target_binding_sha256
    ):
        return None, "prospective_activation_invalid"
    return (
        ProspectiveActivationProof(
            gate,
            heartbeat,
            proof.expected_activation_id,
            proof.expected_target_binding_sha256,
        ),
        None,
    )


def _parse_run_started_at(value: Any) -> datetime | None:
    """Parse one validated source-run start as a UTC instant, fail closed."""

    if type(value) is not str:
        return None
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _activation_provenance_entry(
    *,
    side: str,
    run: Mapping[str, Any],
    proof: ProspectiveActivationProof,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate one proof at its replay-validated run start and bind a receipt."""

    evaluated_at = _parse_run_started_at(run.get("started_at"))
    run_ref = run.get("run_id")
    if evaluated_at is None or type(run_ref) is not str:
        return None, "prospective_activation_invalid"
    try:
        validate_activation_gate(proof.gate, now=evaluated_at)
        validate_activation_heartbeat(proof.heartbeat, proof.gate, now=evaluated_at)
    except (ActivationError, OverflowError) as exc:
        if str(exc) == "BIOCATALYST_R2_ACTIVATION_HEARTBEAT_STALE":
            return None, "prospective_activation_stale"
        return None, "prospective_activation_invalid"
    return {
        "side": side,
        "run_ref": run_ref,
        "evaluated_at": _utc_timestamp(evaluated_at),
        "activation_id": proof.expected_activation_id,
        "gate_payload_sha256": proof.gate.get("gate_payload_sha256"),
        "heartbeat_id": proof.heartbeat.get("heartbeat_id"),
        "heartbeat_payload_sha256": proof.heartbeat.get(
            "heartbeat_payload_sha256"
        ),
        "target_binding_sha256": proof.expected_target_binding_sha256,
    }, None


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except ContractError as exc:
        raise ChangeClassificationError("compiler_value_not_canonical_json") from exc


def _with_hash(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    document = _json_copy(payload)
    if type(document) is not dict:
        raise ChangeClassificationError("compiler_payload_not_object")
    document[field] = canonical_json_sha256(document)
    return document


def _capacity() -> dict[str, int]:
    return _json_copy(_CAPACITY)


def _classification_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    rows = document.get("rows")
    return {
        "evidence_profile": document.get("evidence_profile"),
        "nct_id": document.get("nct_id"),
        "diff_contract_id": document.get("diff_contract_id"),
        "diff_ref": document.get("diff_ref"),
        "diff_payload_sha256": document.get("diff_payload_sha256"),
        "prospective_activation_provenance": document.get(
            "prospective_activation_provenance"
        ),
        "available": document.get("available"),
        "unavailable_reason": document.get("unavailable_reason"),
        "row_ids": [
            row.get("row_id") for row in rows if isinstance(row, Mapping)
        ]
        if isinstance(rows, list)
        else [],
    }


def _projection_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    rows = document.get("rows")
    return {
        "classification_ref": document.get("classification_ref"),
        "classification_payload_sha256": document.get(
            "classification_payload_sha256"
        ),
        "nct_id": document.get("nct_id"),
        "source_clock": document.get("source_clock"),
        "available": document.get("available"),
        "unavailable_reason": document.get("unavailable_reason"),
        "row_ids": [
            row.get("row_id") for row in rows if isinstance(row, Mapping)
        ]
        if isinstance(rows, list)
        else [],
    }


def _row_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: document.get(key)
        for key in (
            "nct_id",
            "field_class",
            "review_state",
            "semantic_resolution",
            "diff_contract_id",
            "diff_ref",
            "diff_payload_sha256",
            "exact_op_index",
            "canonical_op_sha256",
            "op",
            "json_path",
            "before_state",
            "after_state",
            "before_source_snapshot_ref",
            "after_source_snapshot_ref",
            "before_content_sha256",
            "after_content_sha256",
        )
    }


def _build_projection(classification: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_id": _PROJECTION_CONTRACT_ID,
        "schema_version": "1.0.0",
        "classification_ref": classification.get("classification_id"),
        "classification_payload_sha256": classification.get(
            "classification_payload_sha256"
        ),
        "nct_id": classification.get("nct_id"),
        "source_clock": _json_copy(classification.get("source_clock")),
        "available": classification.get("available"),
        "unavailable_reason": classification.get("unavailable_reason"),
        "tenant_scope": "tenant_neutral",
        "chronology_order": "source_clock_then_exact_op_index",
        "canonical_alert": False,
        "delivery_eligible": False,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "correction_assessed": False,
        "review_decision_refs": [],
        "row_count": classification.get("row_count"),
        "rows": _json_copy(classification.get("rows")),
        "authority": _json_copy(_AUTHORITY),
        "hash_scope": "canonical_payload_excluding_projection_payload_sha256",
    }
    identity = _projection_identity(payload)
    id_scope = str(payload.get("nct_id") or "unavailable")
    payload["projection_id"] = (
        f"trial_change_alert_projection_{id_scope}_"
        f"{canonical_json_sha256(identity)[:24]}"
    )
    return _with_hash(payload, "projection_payload_sha256")


def _build_unavailable(reason: str) -> TrialChangeCompilation:
    payload: dict[str, Any] = {
        "contract_id": _CLASSIFICATION_CONTRACT_ID,
        "schema_version": "1.0.0",
        "nct_id": None,
        "evidence_profile": "unavailable",
        "diff_contract_id": None,
        "diff_ref": None,
        "diff_payload_sha256": None,
        "before_source_snapshot_ref": None,
        "after_source_snapshot_ref": None,
        "before_content_sha256": None,
        "after_content_sha256": None,
        "source_clock": {"profile": "unavailable"},
        "prospective_activation_provenance": None,
        "available": False,
        "unavailable_reason": reason,
        "capacity": _capacity(),
        "input_operation_count": 0,
        "eligible_operation_count": 0,
        "row_count": 0,
        "row_order": "exact_op_index_ascending",
        "rows": [],
        "classification_method": _METHOD,
        "source_fact": False,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "correction_assessed": False,
        "authority": _json_copy(_AUTHORITY),
        "hash_scope": "canonical_payload_excluding_classification_payload_sha256",
    }
    payload["classification_id"] = (
        "trial_change_classification_unavailable_"
        f"{canonical_json_sha256(_classification_identity(payload))[:24]}"
    )
    classification = _with_hash(payload, "classification_payload_sha256")
    projection = _build_projection(classification)
    try:
        validate_trial_change_classification(classification)
        validate_trial_change_alert_projection(projection, classification)
    except Exception as exc:  # pragma: no cover - compiler/schema drift is fatal.
        raise ChangeClassificationError("unavailable_artifact_contract_drift") from exc
    return TrialChangeCompilation(classification, projection)


def _field_class(json_path: object) -> str | None:
    if not isinstance(json_path, str):
        return None

    def at_or_below(prefix: str) -> bool:
        return json_path == prefix or json_path.startswith(prefix + "/")

    if json_path == "/protocolSection/statusModule/overallStatus":
        return "registry_status"
    if at_or_below("/protocolSection/designModule/enrollmentInfo"):
        return "enrollment"
    if any(
        at_or_below(f"/protocolSection/statusModule/{field}")
        for field in (
            "startDateStruct",
            "primaryCompletionDateStruct",
            "completionDateStruct",
        )
    ):
        return "milestone_date_constraint"
    if at_or_below("/protocolSection/contactsLocationsModule/locations"):
        return "site_list"
    if at_or_below("/protocolSection/armsInterventionsModule/interventions"):
        return "intervention"
    if any(
        at_or_below(f"/protocolSection/outcomesModule/{field}")
        for field in ("primaryOutcomes", "secondaryOutcomes", "otherOutcomes")
    ):
        return "endpoint_record_delta"
    return None


def _build_row(
    *,
    operation: Mapping[str, Any],
    exact_op_index: int,
    diff: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    field_class: str,
) -> dict[str, Any]:
    endpoint = field_class == "endpoint_record_delta"
    payload: dict[str, Any] = {
        "nct_id": diff.get("nct_id"),
        "field_class": field_class,
        "review_state": "needs_review" if endpoint else "not_required",
        "semantic_resolution": "unresolved" if endpoint else "registry_field_class_only",
        "diff_contract_id": diff.get("contract_id"),
        "diff_ref": diff.get("diff_id"),
        "diff_payload_sha256": diff.get("diff_payload_sha256"),
        "exact_op_index": exact_op_index,
        "canonical_op_sha256": canonical_json_sha256(operation),
        "op": operation.get("op"),
        "json_path": operation.get("json_path"),
        "before_state": operation.get("before_state"),
        "after_state": operation.get("after_state"),
        "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
        "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
        "before_content_sha256": before_snapshot.get("canonical_content_sha256"),
        "after_content_sha256": after_snapshot.get("canonical_content_sha256"),
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "correction_assessed": False,
        "hash_scope": "canonical_payload_excluding_row_payload_sha256",
    }
    payload["row_id"] = (
        f"trial_change_row_{diff.get('nct_id')}_"
        f"{canonical_json_sha256(_row_identity(payload))[:24]}"
    )
    return _with_hash(payload, "row_payload_sha256")


def _build_available(
    *,
    evidence_profile: str,
    diff: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    source_clock: Mapping[str, Any],
    prospective_activation_provenance: Sequence[Mapping[str, Any]] | None = None,
) -> TrialChangeCompilation:
    operations = diff.get("operations")
    if not isinstance(operations, list):
        return _build_unavailable("evidence_replay_failed")
    if len(operations) > _MAX_OPERATIONS:
        return _build_unavailable("operation_count_limit_exceeded")

    rows: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            return _build_unavailable("evidence_replay_failed")
        field_class = _field_class(operation.get("json_path"))
        if field_class is None:
            continue
        rows.append(
            _build_row(
                operation=operation,
                exact_op_index=index,
                diff=diff,
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
                field_class=field_class,
            )
        )
        if len(rows) > _MAX_ROWS:
            return _build_unavailable("row_count_limit_exceeded")

    payload: dict[str, Any] = {
        "contract_id": _CLASSIFICATION_CONTRACT_ID,
        "schema_version": "1.0.0",
        "nct_id": diff.get("nct_id"),
        "evidence_profile": evidence_profile,
        "diff_contract_id": diff.get("contract_id"),
        "diff_ref": diff.get("diff_id"),
        "diff_payload_sha256": diff.get("diff_payload_sha256"),
        "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
        "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
        "before_content_sha256": before_snapshot.get("canonical_content_sha256"),
        "after_content_sha256": after_snapshot.get("canonical_content_sha256"),
        "source_clock": _json_copy(source_clock),
        "prospective_activation_provenance": _json_copy(
            prospective_activation_provenance
        ),
        "available": True,
        "unavailable_reason": None,
        "capacity": _capacity(),
        "input_operation_count": len(operations),
        "eligible_operation_count": len(rows),
        "row_count": len(rows),
        "row_order": "exact_op_index_ascending",
        "rows": rows,
        "classification_method": _METHOD,
        "source_fact": False,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "correction_assessed": False,
        "authority": _json_copy(_AUTHORITY),
        "hash_scope": "canonical_payload_excluding_classification_payload_sha256",
    }
    payload["classification_id"] = (
        f"trial_change_classification_{diff.get('nct_id')}_"
        f"{canonical_json_sha256(_classification_identity(payload))[:24]}"
    )
    classification = _with_hash(payload, "classification_payload_sha256")
    if len(canonical_json_bytes(classification)) > _MAX_CLASSIFICATION_BYTES:
        return _build_unavailable("classification_byte_limit_exceeded")
    projection = _build_projection(classification)
    if len(canonical_json_bytes(projection)) > _MAX_PROJECTION_BYTES:
        return _build_unavailable("projection_byte_limit_exceeded")
    try:
        validate_trial_change_classification(classification)
        validate_trial_change_alert_projection(projection, classification)
    except Exception as exc:
        raise ChangeClassificationError("compiled_artifact_contract_drift") from exc
    return TrialChangeCompilation(classification, projection)


def _gate_reason(history_enabled: Any, retention_gate_open: Any) -> str | None:
    if type(history_enabled) is not bool or type(retention_gate_open) is not bool:
        return "schema_profile_mismatch"
    if not history_enabled:
        return "history_disabled"
    if not retention_gate_open:
        return "retention_gate_closed"
    return None


def compile_retrospective_trial_change(
    diff: Any,
    before_snapshot: Any,
    after_snapshot: Any,
    *,
    history_enabled: bool = True,
    retention_gate_open: bool = True,
) -> TrialChangeCompilation:
    """Compile one adjacent Record History exact diff, or fail empty."""

    reason = _gate_reason(history_enabled, retention_gate_open)
    if reason is not None:
        return _build_unavailable(reason)
    before, reason = _freeze_document("before_snapshot", before_snapshot)
    if reason is not None:
        return _build_unavailable(reason)
    after, reason = _freeze_document("after_snapshot", after_snapshot)
    if reason is not None:
        return _build_unavailable(reason)
    exact_diff, reason = _freeze_document("diff", diff)
    if reason is not None:
        return _build_unavailable(reason)
    assert before is not None and after is not None and exact_diff is not None
    if exact_diff.get("contract_id") != _HISTORY_DIFF_CONTRACT_ID:
        return _build_unavailable("schema_profile_mismatch")
    try:
        validate_trial_history_diff_against_snapshots(exact_diff, before, after)
    except Exception:
        return _build_unavailable("evidence_replay_failed")
    source_clock = {
        "profile": "retrospective_source_versions",
        "before_source_version": before.get("source_version"),
        "after_source_version": after.get("source_version"),
        "before_retrieved_at": before.get("retrieved_at"),
        "after_retrieved_at": after.get("retrieved_at"),
        "before_transaction_from": before.get("transaction_from"),
        "after_transaction_from": after.get("transaction_from"),
    }
    return _build_available(
        evidence_profile="retrospective_record_history",
        diff=exact_diff,
        before_snapshot=before,
        after_snapshot=after,
        source_clock=source_clock,
    )


def compile_prospective_trial_change(
    diff: Any,
    before_evidence: Any,
    after_evidence: Any,
    before_observation: Any,
    after_observation: Any,
    *,
    before_activation_proof: ProspectiveActivationProof | None = None,
    after_activation_proof: ProspectiveActivationProof | None = None,
) -> TrialChangeCompilation:
    """Compile one first-observed exact diff with complete archived evidence."""

    frozen_before_proof, reason = _freeze_prospective_activation_proof(
        before_activation_proof
    )
    if reason is not None:
        return _build_unavailable(reason)
    frozen_after_proof, reason = _freeze_prospective_activation_proof(
        after_activation_proof
    )
    if reason is not None:
        return _build_unavailable(reason)
    before, reason = _freeze_source_evidence("before", before_evidence)
    if reason is not None:
        return _build_unavailable(reason)
    after, reason = _freeze_source_evidence("after", after_evidence)
    if reason is not None:
        return _build_unavailable(reason)
    before_obs, reason = _freeze_document("before_observation", before_observation)
    if reason is not None:
        return _build_unavailable(reason)
    after_obs, reason = _freeze_document("after_observation", after_observation)
    if reason is not None:
        return _build_unavailable(reason)
    exact_diff, reason = _freeze_document("diff", diff)
    if reason is not None:
        return _build_unavailable(reason)
    assert (
        before is not None
        and after is not None
        and before_obs is not None
        and after_obs is not None
        and exact_diff is not None
        and frozen_before_proof is not None
        and frozen_after_proof is not None
    )
    if exact_diff.get("contract_id") != _PROSPECTIVE_DIFF_CONTRACT_ID:
        return _build_unavailable("schema_profile_mismatch")
    try:
        validate_trial_diff_against_snapshots(
            exact_diff,
            before.snapshot,
            after.snapshot,
            before_obs,
            after_obs,
            before_run=before.run,
            before_receipts=before.receipts,
            before_raw_page_bodies_by_receipt=before.raw_page_bodies_by_receipt,
            after_run=after.run,
            after_receipts=after.receipts,
            after_raw_page_bodies_by_receipt=after.raw_page_bodies_by_receipt,
        )
    except Exception:
        return _build_unavailable("evidence_replay_failed")
    before_provenance, reason = _activation_provenance_entry(
        side="before", run=before.run, proof=frozen_before_proof
    )
    if reason is not None:
        return _build_unavailable(reason)
    after_provenance, reason = _activation_provenance_entry(
        side="after", run=after.run, proof=frozen_after_proof
    )
    if reason is not None:
        return _build_unavailable(reason)
    assert before_provenance is not None and after_provenance is not None
    if (
        before_provenance["target_binding_sha256"]
        != after_provenance["target_binding_sha256"]
    ):
        return _build_unavailable("prospective_activation_invalid")
    return _build_available(
        evidence_profile="prospective_first_observed",
        diff=exact_diff,
        before_snapshot=before.snapshot,
        after_snapshot=after.snapshot,
        source_clock={
            "profile": "prospective_first_observed_interval",
            "after": exact_diff.get("observed_interval", {}).get("after"),
            "at_or_before": exact_diff.get("observed_interval", {}).get(
                "at_or_before"
            ),
        },
        prospective_activation_provenance=[before_provenance, after_provenance],
    )


def validate_retrospective_trial_change_compilation(
    compilation: TrialChangeCompilation,
    diff: Any,
    before_snapshot: Any,
    after_snapshot: Any,
) -> None:
    """Replay an emitted retrospective pair from exact source snapshots."""

    expected = compile_retrospective_trial_change(
        diff, before_snapshot, after_snapshot
    )
    if canonical_json_bytes(compilation.classification) != canonical_json_bytes(
        expected.classification
    ) or canonical_json_bytes(compilation.projection) != canonical_json_bytes(
        expected.projection
    ):
        raise ChangeClassificationError("retrospective_compilation_exact_replay_failed")


def validate_prospective_trial_change_compilation(
    compilation: TrialChangeCompilation,
    diff: Any,
    before_evidence: Any,
    after_evidence: Any,
    before_observation: Any,
    after_observation: Any,
    *,
    before_activation_proof: ProspectiveActivationProof | None = None,
    after_activation_proof: ProspectiveActivationProof | None = None,
) -> None:
    """Replay an emitted prospective pair from archived source bytes."""

    expected = compile_prospective_trial_change(
        diff,
        before_evidence,
        after_evidence,
        before_observation,
        after_observation,
        before_activation_proof=before_activation_proof,
        after_activation_proof=after_activation_proof,
    )
    if canonical_json_bytes(compilation.classification) != canonical_json_bytes(
        expected.classification
    ) or canonical_json_bytes(compilation.projection) != canonical_json_bytes(
        expected.projection
    ):
        raise ChangeClassificationError("prospective_compilation_exact_replay_failed")


__all__ = [
    "ChangeClassificationError",
    "ProspectiveActivationProof",
    "TrialChangeCompilation",
    "compile_prospective_trial_change",
    "compile_retrospective_trial_change",
    "validate_prospective_trial_change_compilation",
    "validate_retrospective_trial_change_compilation",
]
