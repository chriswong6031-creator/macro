"""Generation-bound, display-safe trial change tape for BioCatalyst.

This module is a deliberately narrow bridge between the exact-evidence T2b
compiler and the authenticated product read path.  It only accepts the
private, replay-validated B2 history snapshots held at publication time.  It
does not reconstruct classifications from a public history model, and it does
not turn a classified registry edit into a protocol, clinical, issuer,
security, materiality, delivery, Neural Web, or Prophet assertion.

Prospective classifications remain explicitly unavailable here.  T2b requires
two exact, run-bound activation proofs, and the existing prospective
publication seam does not retain those proofs.  Serving a convenient
approximation from the public prospective model would weaken that boundary.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from engine.sector_intelligence import (
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
)
from engine.sector_intelligence.contracts import ContractError

from .change_classification import (
    ChangeClassificationError,
    TrialChangeCompilation,
    compile_retrospective_trial_change,
    validate_retrospective_trial_change_compilation,
)
from .history import HistoryError, build_history_exact_diff


class ChangeTapeError(ValueError):
    """A bounded change-tape invariant failed."""


_CONTRACT_ID = "trial_change_tape_read_model.v1"
_MAX_HISTORY_PAIRS = 128
_MAX_ROWS = 512
_NCT_ID_PREFIX = "NCT"
_AUTHORITY = {
    "classification": "deterministic_registry_change_read_model",
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


def _copy(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except ContractError as exc:
        raise ChangeTapeError("change_tape_value_must_be_canonical_json") from exc


def _with_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    document = _copy(payload)
    if not isinstance(document, dict):
        raise ChangeTapeError("change_tape_payload_must_be_object")
    document["model_payload_sha256"] = canonical_json_sha256(document)
    return document


def _unavailable_history(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "unavailable_reason": reason,
        "classification_count": 0,
        "row_count": 0,
        "rows": [],
    }


def _unavailable_prospective(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "unavailable_reason": reason,
        "classification_count": 0,
        "row_count": 0,
        "rows": [],
    }


def _public_row(
    row: Mapping[str, Any],
    *,
    before_version: int,
    after_version: int,
    observed_at: str,
) -> dict[str, Any]:
    """Strip a T2b row down to its display/context-only semantics.

    In particular this intentionally omits row/diff hashes, references,
    source paths, source-snapshot identities, raw operation values, and any
    activation provenance.  The legacy history endpoint is the separately
    governed surface for public history values.
    """

    expected = {
        "exact_op_index",
        "field_class",
        "review_state",
        "semantic_resolution",
        "op",
        "before_state",
        "after_state",
        "protocol_change_asserted",
        "materiality_assessed",
        "correction_assessed",
    }
    public = {key: row.get(key) for key in expected if key != "exact_op_index"}
    public["exact_operation_index"] = row.get("exact_op_index")
    if set(public) != ((expected - {"exact_op_index"}) | {"exact_operation_index"}):
        raise ChangeTapeError("change_tape_classification_row_invalid")
    public.update(
        {
            "source_versions": {
                "before": before_version + 1,
                "after": after_version + 1,
            },
            "observed_at": observed_at,
        }
    )
    return public


def _history_rows_from_evidence(
    *,
    nct_id: str,
    snapshots: Sequence[Mapping[str, Any]],
) -> tuple[int, list[dict[str, Any]]] | str:
    """Replay every changed adjacent B2 snapshot pair through T2b.

    The caller has already bound these snapshots to the private B2 evidence
    lane.  We nevertheless rebuild each exact diff and re-run the T2b exact
    compilation verifier before a sanitized row is admitted.
    """

    ordered = sorted(snapshots, key=lambda item: item.get("source_version", -1))
    if not ordered or any(item.get("nct_id") != nct_id for item in ordered):
        return "retrospective_evidence_missing"
    for position, snapshot in enumerate(ordered):
        version = snapshot.get("source_version")
        if not isinstance(version, int) or isinstance(version, bool) or version != position:
            return "retrospective_evidence_replay_failed"
    examined_pair_count = 0
    rows: list[dict[str, Any]] = []
    for before, after in zip(ordered, ordered[1:]):
        if before.get("canonical_content_sha256") == after.get("canonical_content_sha256"):
            continue
        examined_pair_count += 1
        if examined_pair_count > _MAX_HISTORY_PAIRS:
            return "classification_limit_exceeded"
        try:
            diff = build_history_exact_diff(
                before,
                after,
                transaction_from=str(after.get("transaction_from") or ""),
            )
            compilation = compile_retrospective_trial_change(diff, before, after)
            validate_retrospective_trial_change_compilation(
                compilation, diff, before, after
            )
        except (ChangeClassificationError, HistoryError, ValueError, TypeError):
            return "retrospective_evidence_replay_failed"
        classification = compilation.classification
        if classification.get("available") is not True:
            return "retrospective_classification_unavailable"
        raw_rows = classification.get("rows")
        observed_at = after.get("retrieved_at")
        before_version = before.get("source_version")
        after_version = after.get("source_version")
        if (
            not isinstance(raw_rows, list)
            or not isinstance(observed_at, str)
            or not isinstance(before_version, int)
            or not isinstance(after_version, int)
        ):
            return "retrospective_evidence_replay_failed"
        try:
            rows.extend(
                _public_row(
                    row,
                    before_version=before_version,
                    after_version=after_version,
                    observed_at=observed_at,
                )
                for row in raw_rows
                if isinstance(row, Mapping)
            )
        except ChangeTapeError:
            return "retrospective_evidence_replay_failed"
        if len(rows) > _MAX_ROWS:
            return "classification_limit_exceeded"
    return len({(row["source_versions"]["before"], row["source_versions"]["after"]) for row in rows}), rows


def build_trial_change_tape_read_model(
    *,
    nct_id: str,
    history_model: Mapping[str, Any],
    history_snapshots: Sequence[Mapping[str, Any]],
    history_carried_forward: bool,
    carried_history_lane: Mapping[str, Any] | None = None,
    prospective_model: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build one safe tape, or state precisely why a lane is unavailable.

    ``history_snapshots`` must be the exact private publication evidence, not
    reconstructed public model fields.  A carried-forward history artifact
    intentionally provides no such inputs; publication must instead use the
    exact prior tape bytes when available.
    """

    if not isinstance(nct_id, str) or not nct_id.startswith(_NCT_ID_PREFIX):
        raise ChangeTapeError("change_tape_nct_id_invalid")
    history: dict[str, Any]
    if history_model.get("available") is not True:
        history = _unavailable_history("history_not_available")
    elif history_carried_forward:
        if not isinstance(carried_history_lane, Mapping):
            history = _unavailable_history("private_replay_evidence_not_present")
        else:
            history = _copy(carried_history_lane)
            if not isinstance(history, dict):
                raise ChangeTapeError("change_tape_carried_history_invalid")
            _validate_lane_semantics(history, name="history", require_versions=True)
    else:
        replayed = _history_rows_from_evidence(
            nct_id=nct_id,
            snapshots=history_snapshots,
        )
        if isinstance(replayed, str):
            history = _unavailable_history(replayed)
        else:
            classification_count, rows = replayed
            history = {
                "available": True,
                "unavailable_reason": None,
                "classification_count": classification_count,
                "row_count": len(rows),
                "rows": rows,
            }
    if prospective_model is None:
        prospective = _unavailable_prospective("prospective_not_collected")
    elif not isinstance(prospective_model, Mapping):
        prospective = _unavailable_prospective("prospective_not_available")
    elif prospective_model.get("available") is not True:
        prospective = _unavailable_prospective("prospective_not_available")
    else:
        # Do not weaken T2b's two proof requirement by trusting a public
        # prospective aggregate, even one produced by a successful poll.
        prospective = _unavailable_prospective("activation_proofs_not_retained")
    payload = {
        "contract_id": _CONTRACT_ID,
        "schema_version": "1.0.0",
        "nct_id": nct_id,
        "history": history,
        "prospective": prospective,
        "chronology_order": "source_version_then_exact_operation_order",
        "interpretation": "registry_record_changed",
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "correction_assessed": False,
        "authority": _copy(_AUTHORITY),
        "capacity": {
            "max_history_pairs": _MAX_HISTORY_PAIRS,
            "max_rows": _MAX_ROWS,
            "overflow_behavior": "unavailable_no_partial_tape",
        },
        "hash_scope": "canonical_payload_excluding_model_payload_sha256",
    }
    model = _with_hash(payload)
    validate_trial_change_tape_read_model(model, nct_id=nct_id)
    return model


def validate_trial_change_tape_read_model(
    model: Mapping[str, Any],
    *,
    nct_id: str | None = None,
) -> dict[str, Any]:
    """Validate a bounded public read model without opening private evidence."""

    try:
        normalized = _copy(model)
        if not isinstance(normalized, dict):
            raise ValueError("model must be object")
        validate_contract(_CONTRACT_ID, normalized)
    except Exception as exc:
        raise ChangeTapeError("change_tape_contract_invalid") from exc
    if nct_id is not None and normalized.get("nct_id") != nct_id:
        raise ChangeTapeError("change_tape_nct_binding_invalid")
    actual_hash = normalized.get("model_payload_sha256")
    if not isinstance(actual_hash, str) or canonical_json_sha256(
        {key: value for key, value in normalized.items() if key != "model_payload_sha256"}
    ) != actual_hash:
        raise ChangeTapeError("change_tape_hash_mismatch")
    history = normalized.get("history")
    prospective = normalized.get("prospective")
    if not isinstance(history, Mapping) or not isinstance(prospective, Mapping):
        raise ChangeTapeError("change_tape_lane_invalid")
    _validate_lane_semantics(history, name="history", require_versions=True)
    _validate_lane_semantics(prospective, name="prospective", require_versions=False)
    return normalized


def _validate_lane_semantics(
    lane: Mapping[str, Any],
    *,
    name: str,
    require_versions: bool,
) -> None:
    """Apply the closure and chronology checks JSON Schema cannot express."""

    available = lane.get("available")
    reason = lane.get("unavailable_reason")
    classifications = lane.get("classification_count")
    row_count = lane.get("row_count")
    rows = lane.get("rows")
    if (
        not isinstance(available, bool)
        or not isinstance(classifications, int)
        or isinstance(classifications, bool)
        or not isinstance(row_count, int)
        or isinstance(row_count, bool)
        or not isinstance(rows, list)
        or not 0 <= classifications <= _MAX_HISTORY_PAIRS
        or not 0 <= row_count <= _MAX_ROWS
        or row_count != len(rows)
    ):
        raise ChangeTapeError(f"change_tape_{name}_count_invalid")
    if available:
        if reason is not None:
            raise ChangeTapeError(f"change_tape_{name}_availability_invalid")
    elif reason is None or classifications != 0 or rows:
        raise ChangeTapeError(f"change_tape_{name}_availability_invalid")
    if not require_versions:
        if rows:
            raise ChangeTapeError(f"change_tape_{name}_rows_not_supported")
        return
    seen_rows: set[bytes] = set()
    seen_pairs: set[tuple[int, int]] = set()
    previous_pair: tuple[int, int] | None = None
    previous_index: int | None = None
    previous_observed_at: datetime | None = None
    pair_observed_literal: str | None = None
    expected_states = {
        "add": ("missing", "present"),
        "remove": ("present", "missing"),
        "replace": ("present", "present"),
    }
    for row in rows:
        if not isinstance(row, Mapping):
            raise ChangeTapeError("change_tape_history_row_invalid")
        try:
            row_fingerprint = canonical_json_bytes(row)
        except ContractError as exc:
            raise ChangeTapeError("change_tape_history_row_invalid") from exc
        if row_fingerprint in seen_rows:
            raise ChangeTapeError("change_tape_history_duplicate_row")
        seen_rows.add(row_fingerprint)
        versions = row.get("source_versions")
        if not isinstance(versions, Mapping):
            raise ChangeTapeError("change_tape_history_versions_invalid")
        before = versions.get("before")
        after = versions.get("after")
        if (
            not isinstance(before, int)
            or isinstance(before, bool)
            or not isinstance(after, int)
            or isinstance(after, bool)
            or before < 1
            or after != before + 1
        ):
            raise ChangeTapeError("change_tape_history_versions_invalid")
        pair = (before, after)
        if previous_pair is not None and pair < previous_pair:
            raise ChangeTapeError("change_tape_history_chronology_invalid")
        same_pair = pair == previous_pair
        operation_index = row.get("exact_operation_index")
        if (
            not isinstance(operation_index, int)
            or isinstance(operation_index, bool)
            or not 0 <= operation_index < 4_096
            or (same_pair and previous_index is not None and operation_index <= previous_index)
        ):
            raise ChangeTapeError("change_tape_history_operation_order_invalid")
        observed_literal = row.get("observed_at")
        if not isinstance(observed_literal, str) or not observed_literal.endswith("Z"):
            raise ChangeTapeError("change_tape_history_clock_invalid")
        try:
            observed_at = datetime.fromisoformat(observed_literal.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ChangeTapeError("change_tape_history_clock_invalid") from exc
        if observed_at.tzinfo is None or observed_at.utcoffset() != timezone.utc.utcoffset(observed_at):
            raise ChangeTapeError("change_tape_history_clock_invalid")
        if same_pair and pair_observed_literal is not None and observed_literal != pair_observed_literal:
            raise ChangeTapeError("change_tape_history_clock_invalid")
        if not same_pair and previous_observed_at is not None and observed_at < previous_observed_at:
            raise ChangeTapeError("change_tape_history_chronology_invalid")
        previous_pair = pair
        previous_index = operation_index
        pair_observed_literal = observed_literal
        previous_observed_at = observed_at
        seen_pairs.add(pair)
        op = row.get("op")
        if expected_states.get(op) != (row.get("before_state"), row.get("after_state")):
            raise ChangeTapeError("change_tape_history_operation_invalid")
        if row.get("field_class") == "endpoint_record_delta":
            if (
                row.get("review_state") != "needs_review"
                or row.get("semantic_resolution") != "unresolved"
            ):
                raise ChangeTapeError("change_tape_history_semantic_invalid")
        elif (
            row.get("review_state") != "not_required"
            or row.get("semantic_resolution") != "registry_field_class_only"
        ):
            raise ChangeTapeError("change_tape_history_semantic_invalid")
    if len(seen_pairs) != classifications:
        raise ChangeTapeError("change_tape_history_classification_count_invalid")


__all__ = [
    "ChangeTapeError",
    "build_trial_change_tape_read_model",
    "validate_trial_change_tape_read_model",
]
