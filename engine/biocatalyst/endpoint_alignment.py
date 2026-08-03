"""Private, replayable endpoint-alignment review candidates for BioCatalyst.

This deliberately narrow T2a seam consumes only a consecutive pair of
immutable B2 Record History snapshots and their replay-validated exact diff.
It does not write a review queue, classify a protocol change, or resolve an
issuer, security, asset, or clinical meaning.  Its only output is a bounded
``needs_review`` projection of possible same-registry-endpoint candidates.

Complete B2 inputs are refused before copying or replay when their canonical
JSON size or shape exceeds the fixed preflight envelope.  That refusal is the
safe fail-empty boundary: no projection can truthfully cite snapshot/diff
headers whose evidence hashes were too large to replay-validate.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
import json
import unicodedata
from typing import Any, Mapping, Sequence

from engine.sector_intelligence.contracts import (
    ContractError,
    ContractRegistry,
    ContractValidationError,
    ValidationIssue,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_trial_history_diff_against_snapshots,
)


class EndpointAlignmentError(ValueError):
    """A bounded failure while deriving a private alignment projection."""


_CANDIDATE_CONTRACT_ID = "trial_endpoint_alignment_candidate.v1"
_PROJECTION_CONTRACT_ID = "trial_endpoint_alignment_review_projection.v1"
_METHOD = "deterministic_endpoint_alignment_candidate.v1"
_RELATION = "possible_same_registry_endpoint"
_REVIEW_STATE = "needs_review"
_OUTCOME_LISTS = (
    ("other", "/protocolSection/outcomesModule/otherOutcomes"),
    ("primary", "/protocolSection/outcomesModule/primaryOutcomes"),
    ("secondary", "/protocolSection/outcomesModule/secondaryOutcomes"),
)
_OUTCOME_LIST_LOCATORS = frozenset(locator for _role, locator in _OUTCOME_LISTS)
_MAX_RESIDUAL_ROWS_PER_SIDE = 64
_MAX_COMPARISONS = 4096
_MAX_CANDIDATES = 64
_MAX_CANDIDATE_BYTES = 48 * 1024
_MAX_PROJECTION_BYTES = 512 * 1024
_MAX_ENDPOINT_TEXT_BYTES = 16 * 1024
_MAX_ENDPOINT_BYTES = 24 * 1024
_MAX_ENDPOINT_NODES = 1024
_MAX_ENDPOINT_NESTING_DEPTH = 64
_MAX_SOURCE_OUTCOME_ROWS_PER_SIDE = 256
_MAX_HISTORY_INPUT_CANONICAL_BYTES = 2 * 1024 * 1024
_MAX_HISTORY_INPUT_NODES = 65_536
_MAX_HISTORY_INPUT_NESTING_DEPTH = 128
_MAX_HISTORY_INPUT_CONTAINER_ITEMS = 16_384
_AUTHORITY = {
    "classification": "semantic_candidate",
    "decision_authority": False,
    "maximum_authority": "A2_ATTEND",
    "allowed_uses": ["display", "context", "explain", "attend"],
    "forbidden_uses": [
        "originate_signal",
        "issuer_resolution",
        "security_resolution",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "neural_web_authority",
        "all_prophet_uses",
        "raise_authority",
    ],
}


def _canonical_string_byte_length(value: str, limit: int) -> int | None:
    """Return exact canonical JSON string bytes, or ``None`` if not encodable.

    ``canonical_json_bytes`` uses ``ensure_ascii=False``.  Counting here keeps
    the preflight allocation-free even for a multi-megabyte hostile string.
    A result greater than ``limit`` is an early size signal, not an allocation.
    """

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
            total += 1 if codepoint <= 0x7F else 2 if codepoint <= 0x7FF else 3 if codepoint <= 0xFFFF else 4
        if total > limit:
            return total
    return total


def _freeze_history_input(value: Any) -> tuple[Any | None, str | None]:
    """Iteratively preflight and freeze one complete B2 JSON document.

    Keys are visited in canonical order so the refusal reason cannot depend on
    caller insertion order. The node budget counts both object keys and JSON
    values. Container contents are captured only into bounded local arrays; the
    returned plain JSON tree is the sole value later replayed.
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
        if nodes > _MAX_HISTORY_INPUT_NODES:
            return None, "node_limit_exceeded"
        if depth > _MAX_HISTORY_INPUT_NESTING_DEPTH:
            return None, "nesting_limit_exceeded"

        current_type = type(current)
        if current_type is str:
            rendered_size = _canonical_string_byte_length(
                current, _MAX_HISTORY_INPUT_CANONICAL_BYTES - total
            )
            if rendered_size is None:
                return None, "must_be_canonical_json"
            total += rendered_size
            frozen: Any = current
        elif current_type is dict:
            items: list[tuple[Any, Any]] = []
            try:
                for key, child in current.items():
                    if len(items) >= _MAX_HISTORY_INPUT_CONTAINER_ITEMS:
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
            if nodes + len(stack) + pending_nodes > _MAX_HISTORY_INPUT_NODES:
                return None, "node_limit_exceeded"
            if item_count and depth + 1 > _MAX_HISTORY_INPUT_NESTING_DEPTH:
                return None, "nesting_limit_exceeded"
            total += 2 + max(0, item_count - 1) + item_count
            nodes += item_count
            if total > _MAX_HISTORY_INPUT_CANONICAL_BYTES:
                return None, "canonical_byte_limit_exceeded"
            invalid_key = False
            for key, _child in items:
                rendered_size = _canonical_string_byte_length(
                    key, _MAX_HISTORY_INPUT_CANONICAL_BYTES - total
                )
                if rendered_size is None:
                    invalid_key = True
                    continue
                total += rendered_size
                if total > _MAX_HISTORY_INPUT_CANONICAL_BYTES:
                    return None, "canonical_byte_limit_exceeded"
            if invalid_key:
                return None, "must_be_canonical_json"
            # Sorting is safe only after the aggregate key encoding is inside
            # the same 2MiB budget as the complete canonical document.
            items.sort(key=lambda item: item[0])
            frozen = {}
            for key, child in reversed(items):
                stack.append((child, depth + 1, frozen, key))
        elif current_type is list:
            item_count = len(current)
            if item_count > _MAX_HISTORY_INPUT_CONTAINER_ITEMS:
                return None, "container_limit_exceeded"
            items_list: list[Any] = []
            try:
                for index in range(item_count):
                    items_list.append(current[index])
            except IndexError:
                return None, "must_be_canonical_json"
            if len(current) != item_count:
                return None, "must_be_canonical_json"
            if nodes + len(stack) + item_count > _MAX_HISTORY_INPUT_NODES:
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
            # Avoid asking Python to render a hostile arbitrary-precision
            # integer that cannot fit inside the remaining byte budget.
            remaining = _MAX_HISTORY_INPUT_CANONICAL_BYTES - total
            if current.bit_length() > max(1, remaining) * 4:
                return None, "canonical_byte_limit_exceeded"
            try:
                total += len(str(current))
            except ValueError:
                return None, "must_be_canonical_json"
            frozen = current
        elif current_type is float:
            try:
                rendered = json.dumps(current, allow_nan=False, separators=(",", ":"))
            except (TypeError, ValueError):
                return None, "must_be_canonical_json"
            total += len(rendered)
            frozen = current
        else:
            return None, "must_be_canonical_json"

        if total > _MAX_HISTORY_INPUT_CANONICAL_BYTES:
            return None, "canonical_byte_limit_exceeded"
        parent[slot] = frozen
    return root[0], None


def _preflight_history_inputs(
    before_snapshot: Any, after_snapshot: Any, diff: Any
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Refuse unsafe evidence before copying it or invoking exact B2 replay.

    No unavailable projection is minted here.  Doing so would publish
    unvalidated source references and hashes from the very inputs that could
    not be safely replayed.
    """

    frozen_documents: list[dict[str, Any]] = []
    for label, document in (
        ("before_snapshot", before_snapshot),
        ("after_snapshot", after_snapshot),
        ("diff", diff),
    ):
        if type(document) is not dict:
            raise EndpointAlignmentError("endpoint_alignment_history_inputs_must_be_objects")
        frozen, reason = _freeze_history_input(document)
        if reason is not None:
            raise EndpointAlignmentError(f"endpoint_alignment_{label}_{reason}")
        if type(frozen) is not dict:
            raise EndpointAlignmentError("endpoint_alignment_history_inputs_must_be_objects")
        frozen_documents.append(frozen)
    return frozen_documents[0], frozen_documents[1], frozen_documents[2]


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except ContractError as exc:
        raise EndpointAlignmentError("endpoint_alignment_value_must_be_canonical_json") from exc


def _with_hash(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    document = _json_copy(payload)
    if not isinstance(document, dict):
        raise EndpointAlignmentError("endpoint_alignment_payload_must_be_object")
    document[field] = canonical_json_sha256(document)
    return document


def _resolve_pointer(document: Any, pointer: str) -> Any | None:
    current = document
    if not pointer.startswith("/"):
        return None
    for encoded in pointer[1:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and key in current:
            current = current[key]
        else:
            return None
    return current


def _row_sort_key(row: Mapping[str, Any]) -> tuple[str, int]:
    return (str(row["list_locator"]), int(row["outcome_index"]))


def _outcome_rows(study: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role, locator in _OUTCOME_LISTS:
        values = _resolve_pointer(study, locator)
        if not isinstance(values, list):
            continue
        for index, endpoint in enumerate(values):
            if isinstance(endpoint, Mapping):
                rows.append(
                    {
                        "outcome_role": role,
                        "outcome_index": index,
                        "list_locator": locator,
                        # Do not serialize or copy an unbounded source object
                        # before the input-cap pass in _derive_candidates.
                        "endpoint": endpoint,
                    }
                )
    return sorted(rows, key=_row_sort_key)


def _source_outcome_row_count(study: Mapping[str, Any]) -> int:
    """Count raw source-array entries without copying endpoint objects."""

    count = 0
    for _role, locator in _OUTCOME_LISTS:
        values = _resolve_pointer(study, locator)
        if isinstance(values, list):
            count += len(values)
    return count


def _utf8_byte_count_exceeds(value: str, limit: int) -> bool:
    """Check UTF-8 length without allocating a second unbounded byte string."""

    total = 0
    for character in value:
        codepoint = ord(character)
        total += 1 if codepoint <= 0x7F else 2 if codepoint <= 0x7FF else 3 if codepoint <= 0xFFFF else 4
        if total > limit:
            return True
    return False


def _endpoint_input_limit_reason(endpoint: Any) -> str | None:
    """Bound source objects before canonicalization or lexical comparison.

    This is deliberately a simple JSON-byte upper bound, not a normalizer. It
    counts every string (keys included), escaped control punctuation, container
    punctuation, and scalar rendering while stopping as soon as a fixed limit
    is crossed. It also bounds recursive node traversal.
    """

    total = 0
    nodes = 0
    stack: list[tuple[Any, int]] = [(endpoint, 0)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_ENDPOINT_NODES:
            return "endpoint_complexity_limit_exceeded"
        if depth > _MAX_ENDPOINT_NESTING_DEPTH:
            return "endpoint_nesting_limit_exceeded"
        if isinstance(value, str):
            if _utf8_byte_count_exceeds(value, _MAX_ENDPOINT_TEXT_BYTES):
                return "endpoint_text_limit_exceeded"
            total += 2
            for character in value:
                codepoint = ord(character)
                if character in {'"', "\\"}:
                    total += 2
                elif codepoint < 0x20:
                    total += 6
                else:
                    total += 1 if codepoint <= 0x7F else 2 if codepoint <= 0x7FF else 3 if codepoint <= 0xFFFF else 4
        elif isinstance(value, Mapping):
            total += 2
            if len(stack) + 2 * len(value) > _MAX_ENDPOINT_NODES - nodes:
                return "endpoint_complexity_limit_exceeded"
            for key, child in value.items():
                if not isinstance(key, str):
                    return "endpoint_complexity_limit_exceeded"
                stack.append((child, depth + 1))
                stack.append((key, depth + 1))
                total += 1
        elif isinstance(value, list):
            total += 2 + max(0, len(value) - 1)
            if len(stack) + len(value) > _MAX_ENDPOINT_NODES - nodes:
                return "endpoint_complexity_limit_exceeded"
            stack.extend((child, depth + 1) for child in value)
        elif value is None or isinstance(value, bool):
            total += 4 if value is None else 5
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            # Source JSON scalar values are already finite JSON; this bounded
            # rendering is only an input guard, never an identity hash.
            total += len(str(value))
        else:
            return "endpoint_complexity_limit_exceeded"
        if total > _MAX_ENDPOINT_BYTES:
            return "endpoint_byte_limit_exceeded"
    return None


def _syntactic_value(value: Any) -> Any:
    """Normalize only NFC/case/whitespace for conservative equivalence.

    Deliberately no punctuation, number, unit, abbreviation, spelling,
    ontology, or synonym rewrite exists in this method.
    """

    if isinstance(value, str):
        return " ".join(unicodedata.normalize("NFC", value).casefold().split())
    if isinstance(value, Mapping):
        return {key: _syntactic_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_syntactic_value(child) for child in value]
    return value


def _signature(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _remove_exact_and_unique_syntactic_equivalents(
    before_rows: Sequence[Mapping[str, Any]], after_rows: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return residual endpoint rows without making any semantic equivalence.

    Exact JSON objects are removed as multisets.  Of the remaining rows, only
    a *unique one-to-one* NFC/casefold/whitespace representation is suppressed.
    Ambiguous duplicate representations intentionally remain for review.
    """

    before = [_json_copy(row) for row in before_rows]
    after = [_json_copy(row) for row in after_rows]
    after_by_exact: dict[bytes, deque[int]] = defaultdict(deque)
    for index, row in enumerate(after):
        after_by_exact[_signature(row["endpoint"])].append(index)

    removed_before: set[int] = set()
    removed_after: set[int] = set()
    for index, row in enumerate(before):
        matches = after_by_exact[_signature(row["endpoint"])]
        if matches:
            removed_before.add(index)
            removed_after.add(matches.popleft())

    before_residual = [row for index, row in enumerate(before) if index not in removed_before]
    after_residual = [row for index, row in enumerate(after) if index not in removed_after]
    before_by_syntax: dict[bytes, list[int]] = defaultdict(list)
    after_by_syntax: dict[bytes, list[int]] = defaultdict(list)
    for index, row in enumerate(before_residual):
        before_by_syntax[_signature(_syntactic_value(row["endpoint"]))].append(index)
    for index, row in enumerate(after_residual):
        after_by_syntax[_signature(_syntactic_value(row["endpoint"]))].append(index)

    syntactic_before: set[int] = set()
    syntactic_after: set[int] = set()
    for signature, before_indexes in before_by_syntax.items():
        after_indexes = after_by_syntax.get(signature, [])
        if len(before_indexes) == len(after_indexes) == 1:
            syntactic_before.add(before_indexes[0])
            syntactic_after.add(after_indexes[0])
    return (
        [row for index, row in enumerate(before_residual) if index not in syntactic_before],
        [row for index, row in enumerate(after_residual) if index not in syntactic_after],
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _bigram_dice_bps(before: object, after: object) -> int:
    """A transparent literal-character feature, not a confidence score."""

    left = unicodedata.normalize("NFC", _text(before))
    right = unicodedata.normalize("NFC", _text(after))
    if not left or not right:
        return 0
    if left == right:
        return 10_000
    left_units = [left] if len(left) == 1 else [left[index : index + 2] for index in range(len(left) - 1)]
    right_units = [right] if len(right) == 1 else [right[index : index + 2] for index in range(len(right) - 1)]
    common = sum((Counter(left_units) & Counter(right_units)).values())
    return (20_000 * common) // (len(left_units) + len(right_units))


def _lexical_features(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_frame = before.get("timeFrame", before.get("time_frame"))
    after_frame = after.get("timeFrame", after.get("time_frame"))
    return {
        "method": "literal_unicode_bigram_dice.v1",
        "measure_similarity_bps": _bigram_dice_bps(before.get("measure"), after.get("measure")),
        "time_frame_similarity_bps": _bigram_dice_bps(before_frame, after_frame),
        "description_similarity_bps": _bigram_dice_bps(before.get("description"), after.get("description")),
    }


def _eligible(features: Mapping[str, Any]) -> bool:
    measure = features.get("measure_similarity_bps")
    timeframe = features.get("time_frame_similarity_bps")
    description = features.get("description_similarity_bps")
    return bool(
        isinstance(measure, int)
        and isinstance(timeframe, int)
        and isinstance(description, int)
        and measure >= 8000
        and (timeframe >= 8000 or description >= 8000)
    )


def _exact_list_operation_hashes(
    before_study: Mapping[str, Any], after_study: Mapping[str, Any], diff: Mapping[str, Any]
) -> dict[str, str]:
    """Return only exact list operations whose complete values replay.

    A broad module replacement is intentionally unsupported: a candidate must
    attach to the precise changed outcomes-list operation, never an inferred
    child path or B2 descriptor.
    """

    hashes: dict[str, str] = {}
    for operation in diff.get("operations", []):
        if not isinstance(operation, Mapping):
            continue
        locator = operation.get("json_path")
        if locator not in _OUTCOME_LIST_LOCATORS or operation.get("op") != "replace":
            continue
        before_value = _resolve_pointer(before_study, locator)
        after_value = _resolve_pointer(after_study, locator)
        if (
            isinstance(before_value, list)
            and isinstance(after_value, list)
            and _signature(operation.get("before_value")) == _signature(before_value)
            and _signature(operation.get("after_value")) == _signature(after_value)
        ):
            hashes[str(locator)] = canonical_json_sha256(operation)
    return hashes


def _candidate_locator(snapshot: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    endpoint = _json_copy(row["endpoint"])
    return {
        "source_snapshot_ref": snapshot.get("source_snapshot_id"),
        "source_version": snapshot.get("source_version"),
        "source_record_ref": snapshot.get("source_record_ref"),
        "content_sha256": snapshot.get("canonical_content_sha256"),
        "outcome_role": row["outcome_role"],
        "outcome_index": row["outcome_index"],
        "list_locator": row["list_locator"],
        "endpoint": endpoint,
        "endpoint_sha256": canonical_json_sha256(endpoint),
    }


def _candidate_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "semantic_method": payload.get("semantic_method"),
        "nct_id": payload.get("nct_id"),
        "diff_ref": payload.get("diff_ref"),
        "before": payload.get("before"),
        "after": payload.get("after"),
        "supporting_exact_op_sha256": payload.get("supporting_exact_op_sha256"),
    }


def _make_candidate(
    *,
    diff: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    before_row: Mapping[str, Any],
    after_row: Mapping[str, Any],
    operation_hashes: Mapping[str, str],
) -> tuple[dict[str, Any] | None, bool]:
    before_locator = _candidate_locator(before_snapshot, before_row)
    after_locator = _candidate_locator(after_snapshot, after_row)
    before_operation = operation_hashes.get(before_locator["list_locator"])
    after_operation = operation_hashes.get(after_locator["list_locator"])
    if before_operation is None or after_operation is None:
        return None, False
    features = _lexical_features(before_locator["endpoint"], after_locator["endpoint"])
    if not _eligible(features):
        return None, False
    supporting = sorted({before_operation, after_operation})
    payload: dict[str, Any] = {
        "contract_id": _CANDIDATE_CONTRACT_ID,
        "schema_version": "1.0.0",
        "nct_id": diff.get("nct_id"),
        "diff_ref": diff.get("diff_id"),
        "before": before_locator,
        "after": after_locator,
        "supporting_exact_op_sha256": supporting,
        "lexical_features": features,
        "candidate_relation": _RELATION,
        "review_state": _REVIEW_STATE,
        "persistence_state": "projection_only",
        "canonical_queue": False,
        "semantic_method": _METHOD,
        "source_fact": False,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "authority": _json_copy(_AUTHORITY),
        "hash_scope": "canonical_payload_excluding_candidate_payload_sha256",
    }
    seed = canonical_json_sha256(_candidate_identity(payload))
    payload["candidate_id"] = f"trial_endpoint_alignment_candidate_{diff.get('nct_id')}_{seed[:24]}"
    candidate = _with_hash(payload, "candidate_payload_sha256")
    if len(canonical_json_bytes(candidate)) > _MAX_CANDIDATE_BYTES:
        return None, True
    return candidate, False


def _capacity(
    *,
    source_before_count: int,
    source_after_count: int,
    residual_before_count: int,
    residual_after_count: int,
    comparison_count: int,
) -> dict[str, int]:
    return {
        "max_residual_rows_per_side": _MAX_RESIDUAL_ROWS_PER_SIDE,
        "max_comparisons": _MAX_COMPARISONS,
        "max_candidates": _MAX_CANDIDATES,
        "max_candidate_bytes": _MAX_CANDIDATE_BYTES,
        "max_projection_bytes": _MAX_PROJECTION_BYTES,
        "max_endpoint_text_bytes": _MAX_ENDPOINT_TEXT_BYTES,
        "max_endpoint_bytes": _MAX_ENDPOINT_BYTES,
        "max_endpoint_nodes": _MAX_ENDPOINT_NODES,
        "max_endpoint_nesting_depth": _MAX_ENDPOINT_NESTING_DEPTH,
        "max_source_outcome_rows_per_side": _MAX_SOURCE_OUTCOME_ROWS_PER_SIDE,
        "source_before_count": source_before_count,
        "source_after_count": source_after_count,
        "residual_before_count": residual_before_count,
        "residual_after_count": residual_after_count,
        "comparison_count": comparison_count,
    }


def _derive_candidates(
    before_snapshot: Mapping[str, Any], after_snapshot: Mapping[str, Any], diff: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int], str | None]:
    before_study = before_snapshot.get("canonical_study")
    after_study = after_snapshot.get("canonical_study")
    if not isinstance(before_study, Mapping) or not isinstance(after_study, Mapping):
        raise EndpointAlignmentError("endpoint_alignment_missing_canonical_study")
    source_before_count = _source_outcome_row_count(before_study)
    source_after_count = _source_outcome_row_count(after_study)
    if source_before_count > _MAX_SOURCE_OUTCOME_ROWS_PER_SIDE:
        return [], _capacity(
            source_before_count=source_before_count,
            source_after_count=source_after_count,
            residual_before_count=0,
            residual_after_count=0,
            comparison_count=0,
        ), "source_before_row_limit_exceeded"
    if source_after_count > _MAX_SOURCE_OUTCOME_ROWS_PER_SIDE:
        return [], _capacity(
            source_before_count=source_before_count,
            source_after_count=source_after_count,
            residual_before_count=0,
            residual_after_count=0,
            comparison_count=0,
        ), "source_after_row_limit_exceeded"
    before_source_rows = _outcome_rows(before_study)
    after_source_rows = _outcome_rows(after_study)
    for row in [*before_source_rows, *after_source_rows]:
        reason = _endpoint_input_limit_reason(row["endpoint"])
        if reason is not None:
            return [], _capacity(
                source_before_count=source_before_count,
                source_after_count=source_after_count,
                residual_before_count=len(before_source_rows),
                residual_after_count=len(after_source_rows),
                comparison_count=0,
            ), reason
    before_rows, after_rows = _remove_exact_and_unique_syntactic_equivalents(
        before_source_rows, after_source_rows
    )
    comparison_count = len(before_rows) * len(after_rows)
    capacity = _capacity(
        source_before_count=source_before_count,
        source_after_count=source_after_count,
        residual_before_count=len(before_rows),
        residual_after_count=len(after_rows),
        comparison_count=comparison_count,
    )
    if len(before_rows) > _MAX_RESIDUAL_ROWS_PER_SIDE:
        return [], capacity, "residual_before_limit_exceeded"
    if len(after_rows) > _MAX_RESIDUAL_ROWS_PER_SIDE:
        return [], capacity, "residual_after_limit_exceeded"
    if comparison_count > _MAX_COMPARISONS:
        return [], capacity, "comparison_limit_exceeded"
    operation_hashes = _exact_list_operation_hashes(before_study, after_study, diff)
    candidates: list[dict[str, Any]] = []
    for before_row in before_rows:
        for after_row in after_rows:
            candidate, oversized = _make_candidate(
                diff=diff,
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
                before_row=before_row,
                after_row=after_row,
                operation_hashes=operation_hashes,
            )
            if oversized:
                return [], capacity, "candidate_byte_limit_exceeded"
            if candidate is None:
                # An absent exact list operation simply makes this pair
                # ineligible. Oversized eligible candidates returned above
                # fail the whole projection empty rather than being omitted.
                continue
            candidates.append(candidate)
            # Fixed-priority early exit: once the complete Cartesian result
            # exceeds its cap, the projection is unavailable. We intentionally
            # do not scan or retain a truncated tail.
            if len(candidates) > _MAX_CANDIDATES:
                return [], capacity, "candidate_limit_exceeded"
    candidates.sort(
        key=lambda item: (
            item["before"]["list_locator"],
            item["before"]["outcome_index"],
            item["after"]["list_locator"],
            item["after"]["outcome_index"],
            item["candidate_id"],
        )
    )
    return candidates, capacity, None


def _projection_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "semantic_method": payload.get("semantic_method"),
        "nct_id": payload.get("nct_id"),
        "diff_ref": payload.get("diff_ref"),
        "before_source_snapshot_ref": payload.get("before_source_snapshot_ref"),
        "after_source_snapshot_ref": payload.get("after_source_snapshot_ref"),
        "available": payload.get("available"),
        "unavailable_reason": payload.get("unavailable_reason"),
        "candidate_ids": [candidate.get("candidate_id") for candidate in payload.get("candidates", [])],
    }


def _projection_payload(
    before_snapshot: Mapping[str, Any], after_snapshot: Mapping[str, Any], diff: Mapping[str, Any]
) -> dict[str, Any]:
    candidates, capacity, unavailable_reason = _derive_candidates(
        before_snapshot, after_snapshot, diff
    )

    def make_payload(reason: str | None, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        available = reason is None
        payload: dict[str, Any] = {
            "contract_id": _PROJECTION_CONTRACT_ID,
            "schema_version": "1.0.0",
            "nct_id": diff.get("nct_id"),
            "diff_ref": diff.get("diff_id"),
            "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
            "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
            "before_source_version": before_snapshot.get("source_version"),
            "after_source_version": after_snapshot.get("source_version"),
            "before_source_record_ref": before_snapshot.get("source_record_ref"),
            "after_source_record_ref": after_snapshot.get("source_record_ref"),
            "before_content_sha256": before_snapshot.get("canonical_content_sha256"),
            "after_content_sha256": after_snapshot.get("canonical_content_sha256"),
            "available": available,
            "unavailable_reason": reason,
            "persistence_state": "projection_only",
            "canonical_queue": False,
            "candidate_order": "source_locator_ascending",
            "capacity": _json_copy(capacity),
            "candidate_count": len(rows),
            "candidates": [_json_copy(row) for row in rows],
            "semantic_method": _METHOD,
            "source_fact": False,
            "protocol_change_asserted": False,
            "materiality_assessed": False,
            "authority": _json_copy(_AUTHORITY),
            "generated_at": after_snapshot.get("transaction_from"),
            "hash_scope": "canonical_payload_excluding_projection_payload_sha256",
        }
        seed = canonical_json_sha256(_projection_identity(payload))
        payload["projection_id"] = (
            f"trial_endpoint_alignment_review_projection_{diff.get('nct_id')}_{seed[:24]}"
        )
        return _with_hash(payload, "projection_payload_sha256")

    projection = make_payload(unavailable_reason, candidates if unavailable_reason is None else [])
    if unavailable_reason is None and len(canonical_json_bytes(projection)) > _MAX_PROJECTION_BYTES:
        projection = make_payload("projection_byte_limit_exceeded", [])
    if len(canonical_json_bytes(projection)) > _MAX_PROJECTION_BYTES:
        raise EndpointAlignmentError("endpoint_alignment_unavailable_projection_too_large")
    return projection


def build_trial_endpoint_alignment_review_projection(
    before_snapshot: Mapping[str, Any], after_snapshot: Mapping[str, Any], diff: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a bounded, deterministic private projection for one version pair."""

    before, after, exact_diff = _preflight_history_inputs(
        before_snapshot, after_snapshot, diff
    )
    validate_trial_history_diff_against_snapshots(exact_diff, before, after)
    projection = _projection_payload(before, after, exact_diff)
    validate_trial_endpoint_alignment_review_projection_against_history(
        projection, before, after, exact_diff
    )
    return projection


def validate_trial_endpoint_alignment_candidate_against_history(
    candidate: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    diff: Mapping[str, Any],
    *,
    repo_root: str | None = None,
) -> None:
    """Replay one candidate against immutable snapshots and the exact diff."""

    before, after, exact_diff = _preflight_history_inputs(
        before_snapshot, after_snapshot, diff
    )
    validate_trial_history_diff_against_snapshots(
        exact_diff, before, after, repo_root=repo_root
    )
    registry = ContractRegistry(repo_root)
    registry.validate(_CANDIDATE_CONTRACT_ID, candidate)
    expected, _capacity_state, unavailable_reason = _derive_candidates(
        before, after, exact_diff
    )
    expected_by_id = {item["candidate_id"]: item for item in expected}
    actual_id = candidate.get("candidate_id")
    if unavailable_reason is not None or expected_by_id.get(actual_id) != candidate:
        raise ContractValidationError(
            _CANDIDATE_CONTRACT_ID,
            (
                ValidationIssue(
                    "$",
                    "endpoint_alignment_candidate.exact_replay",
                    "candidate must equal one bounded, exact-diff-anchored residual pair",
                ),
            ),
        )


def validate_trial_endpoint_alignment_review_projection_against_history(
    projection: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    diff: Mapping[str, Any],
    *,
    repo_root: str | None = None,
) -> None:
    """Replay a projection completely; omitted or fabricated rows fail closed."""

    before, after, exact_diff = _preflight_history_inputs(
        before_snapshot, after_snapshot, diff
    )
    validate_trial_history_diff_against_snapshots(
        exact_diff, before, after, repo_root=repo_root
    )
    registry = ContractRegistry(repo_root)
    registry.validate(_PROJECTION_CONTRACT_ID, projection)
    expected = _projection_payload(before, after, exact_diff)
    if expected != projection:
        raise ContractValidationError(
            _PROJECTION_CONTRACT_ID,
            (
                ValidationIssue(
                    "$",
                    "endpoint_alignment_projection.exact_replay",
                    "projection must be the complete deterministic result for one exact adjacent version pair",
                ),
            ),
        )
