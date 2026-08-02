"""Pure, precision-first recipient-to-issuer resolution for Government Revenue.

The USAspending recipient query is *discovery*, not attribution.  This module
therefore has no fuzzy-name fallback and never reads a ticker from a query plan.
It resolves only an exact, visible recipient identifier through a versioned
legal-entity / ownership graph.  The two clocks are deliberately separate:

``event_effective_at``
    When the award or action was economically in force.  Ownership must be
    valid on this date.

``known_at`` / ``analysis_as_of``
    When MastermindX knew the source record and graph evidence.  A mapping
    learned later cannot appear in an earlier replay.

All functions accept and return ordinary dictionaries/lists and use only the
standard library.  Collection, persistence, UI, and ticker-facing metrics
remain intentionally outside this foundation.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, time, timezone
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


RESOLUTION_CONTRACT = "government_recipient_resolution.v1"
COVERAGE_CONTRACT = "government_entity_coverage.v1"
RECIPIENT_GRAPH_CONTRACT = "government_recipient_entity_graph.v1"
RECIPIENT_RESOLUTION_COVERAGE_CONTRACT = "government_recipient_resolution_coverage.v1"
SCHEMA_VERSION = "1.0.0"

# A strict graph is loaded into this small wrapper before it is permitted to
# affect issuer attribution.  The raw resolver remains backward compatible for
# the legacy fixture graph, but production callers should pass this load result.
# Importantly, an absent or invalid graph produces unresolved annotations rather
# than preventing source records from flowing through the award/event rail.
_GRAPH_LOAD_RESULT_CONTRACT = "government_recipient_entity_graph_load_result.v1"
_GRAPH_LOAD_SOURCE_KEY = "_strict_source_graph"
_GRAPH_LOAD_STATUSES = {"ready", "absent", "invalid"}
_GRAPH_TOP_LEVEL_FIELDS = {
    "contract",
    "schema_version",
    "graph_id",
    "graph_known_at",
    "graph_effective_at",
    "evidence",
    "companies",
    "legal_entities",
    "identifiers",
    "ownership_edges",
    "blocks",
    "conflicts",
    "overrides",
}
_GRAPH_TEMPORAL_FIELDS = {"known_at", "valid_from", "valid_to", "evidence_refs"}
_GRAPH_ROW_FIELDS = {
    "evidence": {"evidence_id", "source_ref", "known_at", "valid_from", "valid_to"},
    "company": {"company_id", "ticker", "verification_state", *_GRAPH_TEMPORAL_FIELDS},
    "legal_entity": {"entity_id", "canonical_name", "verification_state", *_GRAPH_TEMPORAL_FIELDS},
    "identifier": {"identifier_id", "entity_id", "namespace", "value", "verification_state", *_GRAPH_TEMPORAL_FIELDS},
    "ownership_edge": {
        "edge_id", "child_entity_id", "parent_entity_id", "parent_company_id", "relationship",
        "economic_share", "verification_state", *_GRAPH_TEMPORAL_FIELDS,
    },
    "block": {
        "block_id", "scope", "namespace", "value", "target_edge_id", "child_entity_id",
        "target_entity_id", "target_company_id", "reason_code", "reviewer_state", *_GRAPH_TEMPORAL_FIELDS,
    },
    "conflict": {
        "conflict_id", "scope", "namespace", "value", "child_entity_id", "candidate_entity_ids",
        "candidate_company_ids", "reason_code", "reviewer_state", *_GRAPH_TEMPORAL_FIELDS,
    },
    "override": {
        "override_id", "action", "namespace", "value", "source_record_key", "target_entity_id",
        "target_company_id", "child_entity_id", "target_edge_id", "relationship", "economic_share",
        "reviewer_state", *_GRAPH_TEMPORAL_FIELDS,
    },
}
_GRAPH_ROW_REQUIRED = {
    "evidence": {"evidence_id", "source_ref", "known_at", "valid_from", "valid_to"},
    "company": {"company_id", "ticker", "verification_state", *_GRAPH_TEMPORAL_FIELDS},
    "legal_entity": {"entity_id", "canonical_name", "verification_state", *_GRAPH_TEMPORAL_FIELDS},
    "identifier": {"identifier_id", "entity_id", "namespace", "value", "verification_state", *_GRAPH_TEMPORAL_FIELDS},
    "ownership_edge": {"edge_id", "child_entity_id", "relationship", "economic_share", "verification_state", *_GRAPH_TEMPORAL_FIELDS},
    "block": {"block_id", "scope", "reason_code", "reviewer_state", *_GRAPH_TEMPORAL_FIELDS},
    "conflict": {"conflict_id", "scope", "reason_code", "reviewer_state", *_GRAPH_TEMPORAL_FIELDS},
    "override": {"override_id", "action", "reviewer_state", *_GRAPH_TEMPORAL_FIELDS},
}
_REVIEWED_GRAPH_STATES = {"confirmed", "reviewed", "analyst_approved"}
_GRAPH_IDENTIFIER_NAMESPACES = {"sam_uei", "cage", "usaspending_recipient_id"}
_GRAPH_EDGE_RELATIONSHIPS = {
    "wholly_owned",
    "majority_owned",
    "partial_owned",
    "joint_venture",
}
_GRAPH_OVERRIDE_ACTIONS = {
    "assert_identifier",
    "assert_mapping",
    "assert_ownership",
    "block",
    "block_identifier",
    "block_ownership",
    "reject_identifier",
    "retire_edge",
}

AUTHORITY = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}

_IDENTIFIER_LADDER = (
    ("sam_uei", ("recipient_uei", "uei"), "exact_uei"),
    ("cage", ("recipient_cage", "cage", "cage_code"), "exact_cage"),
    (
        "usaspending_recipient_id",
        ("recipient_source_id", "source_recipient_id", "usaspending_recipient_id"),
        "exact_source_id",
    ),
)
_NAMESPACE_ALIASES = {
    "uei": "sam_uei",
    "recipient_uei": "sam_uei",
    "sam_uei": "sam_uei",
    "cage": "cage",
    "cage_code": "cage",
    "recipient_cage": "cage",
    "source_recipient_id": "usaspending_recipient_id",
    "recipient_source_id": "usaspending_recipient_id",
    "recipient_id": "usaspending_recipient_id",
    "usaspending_recipient_id": "usaspending_recipient_id",
}
_APPROVED_STATES = {"confirmed", "reviewed", "analyst_approved"}
_OVERRIDE_APPROVED = {"analyst_approved", "approved", "confirmed", "reviewed"}
_BLOCK_ACTIONS = {"block", "block_identifier", "reject_identifier"}
_ASSERT_IDENTIFIER_ACTIONS = {"assert_identifier", "assert_mapping"}
_ASSERT_OWNERSHIP_ACTIONS = {"assert_ownership"}
_BLOCK_OWNERSHIP_ACTIONS = {"block_ownership", "retire_edge"}
_FULL_OWNERSHIP_RELATIONSHIPS = {"wholly_owned"}
_ATTRIBUTED_STATES = {"confirmed", "reviewed"}
_ALL_STATES = (
    "confirmed",
    "reviewed",
    "candidate_review",
    "unresolved",
    "rejected",
    "out_of_scope",
    "conflicted",
)
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RFC3339_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _timestamp(value: Any, *, end_of_day: bool = False) -> datetime | None:
    """Parse a date/datetime as UTC; date-only ends are inclusive when requested."""
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, time.max if end_of_day else time.min)
        else:
            raw = str(value).strip()
            if not raw:
                return None
            if _DATE_ONLY.fullmatch(raw):
                parsed = datetime.combine(
                    date.fromisoformat(raw), time.max if end_of_day else time.min
                )
            else:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _graph_error(errors: list[str], code: str) -> None:
    """Add one stable loader code without leaking arbitrary source text."""
    if code not in errors:
        errors.append(code)


def _strict_datetime(value: Any) -> datetime | None:
    """Accept only RFC3339 graph timestamps with an explicit UTC offset."""
    raw = _text(value)
    if raw is None or _RFC3339_DATETIME.fullmatch(raw) is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _graph_rows(
    graph: Mapping[str, Any], field: str, errors: list[str]
) -> list[dict[str, Any]]:
    value = graph.get(field)
    if not isinstance(value, list):
        _graph_error(errors, f"invalid_{field}")
        return []
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            _graph_error(errors, f"invalid_{field}")
            continue
        rows.append(deepcopy(dict(row)))
    return rows


def _graph_unique_ids(
    rows: Iterable[Mapping[str, Any]], field: str, errors: list[str]
) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        value = _text(row.get(field))
        if value is None:
            _graph_error(errors, f"missing_{field}")
            continue
        if value in ids:
            _graph_error(errors, f"duplicate_{field}")
            continue
        ids.add(value)
    return ids


def _assert_graph_row_shape(
    row: Mapping[str, Any], row_kind: str, errors: list[str]
) -> None:
    """Apply the graph contract's closed-world row shape in the runtime loader."""
    allowed = _GRAPH_ROW_FIELDS[row_kind]
    required = _GRAPH_ROW_REQUIRED[row_kind]
    if set(row) - allowed:
        _graph_error(errors, f"unknown_{row_kind}_field")
    if required - set(row):
        _graph_error(errors, f"missing_{row_kind}_field")


def _graph_temporal_claim(
    row: Mapping[str, Any],
    *,
    errors: list[str],
    evidence: Mapping[str, Mapping[str, Any]],
    graph_known_at: datetime | None,
    graph_effective_at: datetime | None,
    analysis_as_of: datetime | None,
    require_evidence: bool = True,
) -> None:
    """Validate clocks and evidence on one graph claim, never repairing it.

    The graph snapshot is itself point-in-time.  A claim or its evidence that
    post-dates the graph snapshot (or the requested replay) cannot be silently
    retained as a future fact.  This is intentionally stricter than resolver
    filtering: the loader refuses to certify a graph with future leakage.
    """
    known_at = _strict_datetime(row.get("known_at"))
    valid_from = _strict_datetime(row.get("valid_from"))
    valid_to_raw = row.get("valid_to")
    valid_to = None if valid_to_raw is None else _strict_datetime(valid_to_raw)
    if known_at is None:
        _graph_error(errors, "invalid_claim_known_at")
    if valid_from is None:
        _graph_error(errors, "invalid_claim_valid_from")
    if valid_to_raw is not None and valid_to is None:
        _graph_error(errors, "invalid_claim_valid_to")
    if valid_from is not None and valid_to is not None and valid_to < valid_from:
        _graph_error(errors, "claim_validity_window_inverted")
    if known_at is not None and graph_known_at is not None and known_at > graph_known_at:
        _graph_error(errors, "future_known_claim")
    if valid_from is not None and graph_effective_at is not None and valid_from > graph_effective_at:
        _graph_error(errors, "future_effective_claim")
    if analysis_as_of is not None:
        if known_at is not None and known_at > analysis_as_of:
            _graph_error(errors, "future_known_at_analysis_asof")
        if valid_from is not None and valid_from > analysis_as_of:
            _graph_error(errors, "future_effective_at_analysis_asof")

    refs = _evidence_refs(row)
    if require_evidence and not refs:
        _graph_error(errors, "missing_evidence_refs")
    for ref in refs:
        source = evidence.get(ref)
        if source is None:
            _graph_error(errors, "unknown_evidence_ref")
            continue
        evidence_known_at = _strict_datetime(source.get("known_at"))
        evidence_valid_from = _strict_datetime(source.get("valid_from"))
        if evidence_known_at is None or evidence_valid_from is None:
            _graph_error(errors, "invalid_evidence_clock")
            continue
        if known_at is not None and evidence_known_at > known_at:
            _graph_error(errors, "evidence_known_after_claim")
        if graph_known_at is not None and evidence_known_at > graph_known_at:
            _graph_error(errors, "future_known_evidence")
        if graph_effective_at is not None and evidence_valid_from > graph_effective_at:
            _graph_error(errors, "future_effective_evidence")
        if analysis_as_of is not None and (
            evidence_known_at > analysis_as_of or evidence_valid_from > analysis_as_of
        ):
            _graph_error(errors, "future_evidence_at_analysis_asof")


def _intervals_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Return whether two validated inclusive ownership/identifier intervals overlap."""
    left_start = _strict_datetime(left.get("valid_from"))
    right_start = _strict_datetime(right.get("valid_from"))
    left_end = _strict_datetime(left.get("valid_to")) if left.get("valid_to") is not None else None
    right_end = _strict_datetime(right.get("valid_to")) if right.get("valid_to") is not None else None
    if left_start is None or right_start is None:
        return True
    left_upper = left_end or datetime.max.replace(tzinfo=timezone.utc)
    right_upper = right_end or datetime.max.replace(tzinfo=timezone.utc)
    return left_start <= right_upper and right_start <= left_upper


def _graph_fingerprint(graph: Mapping[str, Any]) -> str:
    """Hash the reviewed graph only; source-record identity is deliberately separate."""
    encoded = json.dumps(graph, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _graph_load_result(
    *,
    status: str,
    graph: Mapping[str, Any] | None = None,
    graph_id: str | None = None,
    graph_known_at: datetime | None = None,
    graph_effective_at: datetime | None = None,
    graph_digest: str | None = None,
    errors: Iterable[str] = (),
    source_graph: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assert status in _GRAPH_LOAD_STATUSES
    result = {
        "contract": _GRAPH_LOAD_RESULT_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "graph": deepcopy(dict(graph)) if isinstance(graph, Mapping) else None,
        "graph_id": graph_id,
        "graph_known_at": _iso(graph_known_at),
        "graph_effective_at": _iso(graph_effective_at),
        "graph_digest": graph_digest,
        "error_codes": sorted({code for code in errors if _text(code)}),
    }
    if source_graph is not None:
        # Retain the strict source only for in-memory/replay verification. The
        # resolver re-loads it rather than trusting a caller-supplied normalized
        # graph payload that merely claims to be loader output.
        result[_GRAPH_LOAD_SOURCE_KEY] = deepcopy(dict(source_graph))
    return result


def _is_strict_graph_load_result(graph: Any) -> bool:
    return isinstance(graph, Mapping) and graph.get("contract") == _GRAPH_LOAD_RESULT_CONTRACT


def _graph_for_resolution(
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None = None,
) -> tuple[Mapping[str, Any] | None, str | None]:
    """Unwrap a strict graph result, preserving legacy resolver compatibility."""
    if graph is None:
        return None, "recipient_graph_absent"
    if not isinstance(graph, Mapping):
        return None, "recipient_graph_invalid"
    if _is_strict_graph_load_result(graph):
        status = _text(graph.get("status"))
        if status != "ready" or not isinstance(graph.get("graph"), Mapping):
            return None, (
                "recipient_graph_absent" if status == "absent" else "recipient_graph_invalid"
            )
        source_graph = graph.get(_GRAPH_LOAD_SOURCE_KEY)
        if not isinstance(source_graph, Mapping):
            return None, "recipient_graph_invalid"
        verified = load_recipient_entity_graph(source_graph, as_of=as_of)
        if (
            verified.get("status") != "ready"
            or _text(graph.get("graph_digest")) != _text(verified.get("graph_digest"))
            or not isinstance(verified.get("graph"), Mapping)
        ):
            return None, "recipient_graph_invalid"
        return verified["graph"], None
    if graph.get("contract") == RECIPIENT_GRAPH_CONTRACT:
        loaded = load_recipient_entity_graph(graph, as_of=as_of)
        return _graph_for_resolution(loaded, as_of=as_of)
    return graph, None


def _assert_graph_references(
    *,
    identifiers: Iterable[Mapping[str, Any]],
    ownership_edges: Iterable[Mapping[str, Any]],
    blocks: Iterable[Mapping[str, Any]],
    conflicts: Iterable[Mapping[str, Any]],
    overrides: Iterable[Mapping[str, Any]],
    entity_ids: set[str],
    company_ids: set[str],
    edge_ids: set[str],
    errors: list[str],
) -> None:
    """Ensure every graph pointer names a reviewed node, never a display name."""
    for row in identifiers:
        if _text(row.get("entity_id")) not in entity_ids:
            _graph_error(errors, "identifier_references_unknown_entity")
    for edge in ownership_edges:
        child = _text(edge.get("child_entity_id"))
        parent_entity = _text(edge.get("parent_entity_id"))
        parent_company = _text(edge.get("parent_company_id"))
        if child not in entity_ids:
            _graph_error(errors, "ownership_references_unknown_child_entity")
        if bool(parent_entity) == bool(parent_company):
            _graph_error(errors, "ownership_requires_exactly_one_parent")
        if parent_entity and parent_entity not in entity_ids:
            _graph_error(errors, "ownership_references_unknown_parent_entity")
        if parent_company and parent_company not in company_ids:
            _graph_error(errors, "ownership_references_unknown_company")
    for row in blocks:
        scope = _text(row.get("scope"))
        if scope == "identifier":
            namespace = _normal_namespace(row.get("namespace"))
            if namespace not in _GRAPH_IDENTIFIER_NAMESPACES or not _normal_identifier(namespace or "", row.get("value")):
                _graph_error(errors, "identifier_block_missing_exact_identifier")
        elif scope == "ownership":
            if not any(
                _text(row.get(field))
                for field in ("target_edge_id", "target_entity_id", "target_company_id")
            ):
                _graph_error(errors, "ownership_block_missing_target")
        else:
            _graph_error(errors, "invalid_block_scope")
        if _text(row.get("target_edge_id")) and _text(row.get("target_edge_id")) not in edge_ids:
            _graph_error(errors, "block_references_unknown_edge")
        if _text(row.get("child_entity_id")) and _text(row.get("child_entity_id")) not in entity_ids:
            _graph_error(errors, "block_references_unknown_child_entity")
        if _text(row.get("target_entity_id")) and _text(row.get("target_entity_id")) not in entity_ids:
            _graph_error(errors, "block_references_unknown_entity")
        if _text(row.get("target_company_id")) and _text(row.get("target_company_id")) not in company_ids:
            _graph_error(errors, "block_references_unknown_company")
    for row in conflicts:
        scope = _text(row.get("scope"))
        if scope == "identifier":
            namespace = _normal_namespace(row.get("namespace"))
            if namespace not in _GRAPH_IDENTIFIER_NAMESPACES or not _normal_identifier(namespace or "", row.get("value")):
                _graph_error(errors, "identifier_conflict_missing_exact_identifier")
        elif scope in {"ownership", "issuer"}:
            if _text(row.get("child_entity_id")) not in entity_ids:
                _graph_error(errors, "conflict_references_unknown_child_entity")
        else:
            _graph_error(errors, "invalid_conflict_scope")
        for entity_id in row.get("candidate_entity_ids") or []:
            if _text(entity_id) not in entity_ids:
                _graph_error(errors, "conflict_references_unknown_entity")
        for company_id in row.get("candidate_company_ids") or []:
            if _text(company_id) not in company_ids:
                _graph_error(errors, "conflict_references_unknown_company")
    for row in overrides:
        action = (_text(row.get("action")) or "").lower()
        if action not in _GRAPH_OVERRIDE_ACTIONS:
            _graph_error(errors, "invalid_override_action")
            continue
        namespace = _normal_namespace(row.get("namespace"))
        value = _normal_identifier(namespace or "", row.get("value")) if namespace else None
        target_entity = _text(row.get("target_entity_id"))
        target_company = _text(row.get("target_company_id"))
        if action in _ASSERT_IDENTIFIER_ACTIONS:
            if namespace not in _GRAPH_IDENTIFIER_NAMESPACES or not value or target_entity not in entity_ids:
                _graph_error(errors, "invalid_identifier_override")
        if action in _ASSERT_OWNERSHIP_ACTIONS:
            child = _text(row.get("child_entity_id"))
            if child not in entity_ids or bool(target_entity) == bool(target_company):
                _graph_error(errors, "invalid_ownership_override")
            if target_entity and target_entity not in entity_ids:
                _graph_error(errors, "override_references_unknown_entity")
            if target_company and target_company not in company_ids:
                _graph_error(errors, "override_references_unknown_company")
            relationship = (_text(row.get("relationship")) or "").lower()
            share, share_error = _edge_share(row)
            if relationship not in _GRAPH_EDGE_RELATIONSHIPS or share_error:
                _graph_error(errors, "invalid_ownership_override_economics")
        if action in _BLOCK_ACTIONS and not (
            (namespace in _GRAPH_IDENTIFIER_NAMESPACES and value)
            or _text(row.get("source_record_key"))
            or _text(row.get("target_edge_id"))
            or target_entity
            or target_company
        ):
            _graph_error(errors, "invalid_block_override")
        if _text(row.get("target_edge_id")) and _text(row.get("target_edge_id")) not in edge_ids:
            _graph_error(errors, "override_references_unknown_edge")


def _assert_graph_topology(
    *,
    identifiers: list[dict[str, Any]],
    ownership_edges: list[dict[str, Any]],
    entity_ids: set[str],
    errors: list[str],
) -> None:
    """Reject a graph whose exact joins or ownership walk is ambiguous or cyclic."""
    identifier_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in identifiers:
        namespace = _normal_namespace(row.get("namespace"))
        value = _normal_identifier(namespace or "", row.get("value")) if namespace else None
        if namespace and value:
            identifier_groups[(namespace, value)].append(row)
    for rows in identifier_groups.values():
        for ordinal, left in enumerate(rows):
            for right in rows[ordinal + 1:]:
                if (
                    _text(left.get("entity_id")) != _text(right.get("entity_id"))
                    and _intervals_overlap(left, right)
                ):
                    _graph_error(errors, "ambiguous_exact_identifier_path")

    edges_by_child: dict[str, list[dict[str, Any]]] = defaultdict(list)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in ownership_edges:
        child = _text(edge.get("child_entity_id"))
        if child:
            edges_by_child[child].append(edge)
        parent = _text(edge.get("parent_entity_id"))
        if child and parent:
            adjacency[child].add(parent)
    for rows in edges_by_child.values():
        for ordinal, left in enumerate(rows):
            for right in rows[ordinal + 1:]:
                if _intervals_overlap(left, right):
                    _graph_error(errors, "ambiguous_ownership_path")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            _graph_error(errors, "ownership_cycle")
            return
        if node in visited:
            return
        visiting.add(node)
        for child in adjacency.get(node, set()):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for entity_id in entity_ids:
        visit(entity_id)


def load_recipient_entity_graph(
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    """Validate and normalize a reviewed exact-recipient graph.

    This is the only new v1 graph admission point. It accepts no display-name
    keys or fuzzy candidates, copies rather than mutates the supplied graph,
    and returns a status wrapper so source event collection can continue when
    attribution data is absent or rejected.
    """
    if graph is None:
        return _graph_load_result(status="absent", errors=["recipient_graph_absent"])
    if not isinstance(graph, Mapping):
        return _graph_load_result(status="invalid", errors=["recipient_graph_not_mapping"])

    raw = deepcopy(dict(graph))
    errors: list[str] = []
    if set(raw) != _GRAPH_TOP_LEVEL_FIELDS:
        _graph_error(errors, "graph_shape_invalid")
    if raw.get("contract") != RECIPIENT_GRAPH_CONTRACT:
        _graph_error(errors, "graph_contract_invalid")
    if raw.get("schema_version") != SCHEMA_VERSION:
        _graph_error(errors, "graph_schema_version_invalid")
    graph_id = _text(raw.get("graph_id"))
    if graph_id is None:
        _graph_error(errors, "missing_graph_id")
    graph_known_at = _strict_datetime(raw.get("graph_known_at"))
    graph_effective_at = _strict_datetime(raw.get("graph_effective_at"))
    if graph_known_at is None:
        _graph_error(errors, "invalid_graph_known_at")
    if graph_effective_at is None:
        _graph_error(errors, "invalid_graph_effective_at")
    analysis_as_of = _timestamp(as_of, end_of_day=True) if as_of is not None else None
    if as_of is not None and analysis_as_of is None:
        _graph_error(errors, "invalid_analysis_as_of")
    if analysis_as_of is not None:
        if graph_known_at is not None and graph_known_at > analysis_as_of:
            _graph_error(errors, "future_known_graph")
        if graph_effective_at is not None and graph_effective_at > analysis_as_of:
            _graph_error(errors, "future_effective_graph")

    evidence_rows = _graph_rows(raw, "evidence", errors)
    company_rows = _graph_rows(raw, "companies", errors)
    entity_rows = _graph_rows(raw, "legal_entities", errors)
    identifier_rows = _graph_rows(raw, "identifiers", errors)
    edge_rows = _graph_rows(raw, "ownership_edges", errors)
    block_rows = _graph_rows(raw, "blocks", errors)
    conflict_rows = _graph_rows(raw, "conflicts", errors)
    override_rows = _graph_rows(raw, "overrides", errors)

    evidence_ids = _graph_unique_ids(evidence_rows, "evidence_id", errors)
    company_ids = _graph_unique_ids(company_rows, "company_id", errors)
    entity_ids = _graph_unique_ids(entity_rows, "entity_id", errors)
    _graph_unique_ids(identifier_rows, "identifier_id", errors)
    edge_ids = _graph_unique_ids(edge_rows, "edge_id", errors)
    _graph_unique_ids(block_rows, "block_id", errors)
    _graph_unique_ids(conflict_rows, "conflict_id", errors)
    _graph_unique_ids(override_rows, "override_id", errors)

    evidence_by_id = {
        _text(row.get("evidence_id")): row
        for row in evidence_rows
        if _text(row.get("evidence_id"))
    }
    for row in evidence_rows:
        _assert_graph_row_shape(row, "evidence", errors)
        if _text(row.get("source_ref")) is None:
            _graph_error(errors, "missing_evidence_source_ref")
        _graph_temporal_claim(
            row,
            errors=errors,
            evidence=evidence_by_id,
            graph_known_at=graph_known_at,
            graph_effective_at=graph_effective_at,
            analysis_as_of=analysis_as_of,
            require_evidence=False,
        )
    for row in company_rows:
        _assert_graph_row_shape(row, "company", errors)
        if _text(row.get("ticker")) is None or _TICKER.fullmatch(_text(row.get("ticker")) or "") is None:
            _graph_error(errors, "invalid_company_ticker")
        if (_text(row.get("verification_state")) or "").lower() not in _REVIEWED_GRAPH_STATES:
            _graph_error(errors, "company_not_reviewed")
        _graph_temporal_claim(
            row, errors=errors, evidence=evidence_by_id,
            graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
            analysis_as_of=analysis_as_of,
        )
    for row in entity_rows:
        _assert_graph_row_shape(row, "legal_entity", errors)
        if _text(row.get("canonical_name")) is None:
            _graph_error(errors, "missing_entity_display_name")
        if (_text(row.get("verification_state")) or "").lower() not in _REVIEWED_GRAPH_STATES:
            _graph_error(errors, "entity_not_reviewed")
        _graph_temporal_claim(
            row, errors=errors, evidence=evidence_by_id,
            graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
            analysis_as_of=analysis_as_of,
        )
    for row in identifier_rows:
        _assert_graph_row_shape(row, "identifier", errors)
        namespace = _normal_namespace(row.get("namespace"))
        if namespace not in _GRAPH_IDENTIFIER_NAMESPACES or not _normal_identifier(namespace or "", row.get("value")):
            _graph_error(errors, "invalid_exact_identifier")
        if (_text(row.get("verification_state")) or "").lower() not in _REVIEWED_GRAPH_STATES:
            _graph_error(errors, "identifier_not_reviewed")
        _graph_temporal_claim(
            row, errors=errors, evidence=evidence_by_id,
            graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
            analysis_as_of=analysis_as_of,
        )
    for row in edge_rows:
        _assert_graph_row_shape(row, "ownership_edge", errors)
        relationship = (_text(row.get("relationship")) or "").lower()
        if relationship not in _GRAPH_EDGE_RELATIONSHIPS:
            _graph_error(errors, "invalid_ownership_relationship")
        share, share_error = _edge_share(row)
        if relationship != "wholly_owned" and (share is None or share_error):
            _graph_error(errors, "ownership_economic_share_missing")
        elif share_error:
            _graph_error(errors, "ownership_economic_share_invalid")
        if (_text(row.get("verification_state")) or "").lower() not in _REVIEWED_GRAPH_STATES:
            _graph_error(errors, "ownership_not_reviewed")
        _graph_temporal_claim(
            row, errors=errors, evidence=evidence_by_id,
            graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
            analysis_as_of=analysis_as_of,
        )
    for row in block_rows:
        _assert_graph_row_shape(row, "block", errors)
        if (_text(row.get("reviewer_state")) or "").lower() not in _REVIEWED_GRAPH_STATES:
            _graph_error(errors, "block_not_reviewed")
        _graph_temporal_claim(
            row, errors=errors, evidence=evidence_by_id,
            graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
            analysis_as_of=analysis_as_of,
        )
    for row in conflict_rows:
        _assert_graph_row_shape(row, "conflict", errors)
        if (_text(row.get("reviewer_state")) or "").lower() not in _REVIEWED_GRAPH_STATES:
            _graph_error(errors, "conflict_not_reviewed")
        if _text(row.get("reason_code")) is None:
            _graph_error(errors, "missing_conflict_reason")
        _graph_temporal_claim(
            row, errors=errors, evidence=evidence_by_id,
            graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
            analysis_as_of=analysis_as_of,
        )
    for row in override_rows:
        _assert_graph_row_shape(row, "override", errors)
        if (_text(row.get("reviewer_state")) or "").lower() not in _REVIEWED_GRAPH_STATES:
            _graph_error(errors, "override_not_reviewed")
        _graph_temporal_claim(
            row, errors=errors, evidence=evidence_by_id,
            graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
            analysis_as_of=analysis_as_of,
        )

    _assert_graph_references(
        identifiers=identifier_rows, ownership_edges=edge_rows, blocks=block_rows,
        conflicts=conflict_rows, overrides=override_rows, entity_ids=entity_ids,
        company_ids=company_ids, edge_ids=edge_ids, errors=errors,
    )
    _assert_graph_topology(
        identifiers=identifier_rows, ownership_edges=edge_rows,
        entity_ids=entity_ids, errors=errors,
    )
    if errors:
        return _graph_load_result(
            status="invalid", graph_id=graph_id, graph_known_at=graph_known_at,
            graph_effective_at=graph_effective_at, errors=errors,
        )

    normalized_blocks: list[dict[str, Any]] = []
    for block in block_rows:
        materialized = deepcopy(block)
        materialized["override_id"] = _text(block.get("block_id")) or "block"
        materialized["action"] = (
            "block_identifier" if _text(block.get("scope")) == "identifier" else "block_ownership"
        )
        normalized_blocks.append(materialized)
    normalized = {
        "entities": entity_rows,
        "companies": company_rows,
        "identifiers": identifier_rows,
        "ownership_edges": edge_rows,
        "overrides": override_rows + normalized_blocks,
        "_recipient_entity_graph_loaded_v1": True,
        "_recipient_graph_id": graph_id,
        "_recipient_graph_known_at": _iso(graph_known_at),
        "_recipient_graph_effective_at": _iso(graph_effective_at),
        "_recipient_graph_explicit_conflicts": conflict_rows,
    }
    graph_digest = _graph_fingerprint(raw)
    normalized["_recipient_graph_digest"] = graph_digest
    return _graph_load_result(
        status="ready", graph=normalized, graph_id=graph_id,
        graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
        graph_digest=graph_digest, source_graph=raw,
    )


def _normal_namespace(value: Any) -> str | None:
    raw = _text(value)
    if raw is None:
        return None
    return _NAMESPACE_ALIASES.get(raw.lower().replace("-", "_"), raw.lower())


def _normal_identifier(namespace: str, value: Any) -> str | None:
    raw = _text(value)
    if raw is None:
        return None
    # UEI and CAGE are case-insensitive external identifiers.  Preserve the
    # official source-recipient ID spelling because its source semantics may be
    # case-sensitive.
    return raw.upper() if namespace in {"sam_uei", "cage"} else raw


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        rows: list[dict[str, Any]] = []
        for key, item in value.items():
            if isinstance(item, Mapping):
                row = dict(item)
                row.setdefault("id", str(key))
                rows.append(row)
        return rows
    return []


def _entity_rows(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _list_of_dicts(graph.get("entities"))


def _company_rows(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("companies", "public_companies", "issuers"):
        rows.extend(_list_of_dicts(graph.get(key)))
    return rows


def _entity_index(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entity in _entity_rows(graph):
        entity_id = _text(entity.get("entity_id") or entity.get("id"))
        if entity_id:
            out[entity_id] = entity
    return out


def _company_index(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for company in _company_rows(graph):
        company_id = _text(company.get("company_id") or company.get("id"))
        if company_id:
            out[company_id] = company
    return out


def _evidence_refs(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("evidence_refs") or row.get("evidence_claim_refs") or row.get("source_refs")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, Iterable) or isinstance(raw, (bytes, bytearray, Mapping)):
        return []
    return sorted({value for value in (_text(item) for item in raw) if value})


def _visible_and_active(
    row: Mapping[str, Any],
    *,
    effective_at: datetime,
    knowledge_cutoff: datetime,
    require_known_at: bool = True,
    require_valid_from: bool = False,
    require_evidence: bool = False,
) -> bool:
    """Apply both visibility and economic-validity clocks, fail-closed."""
    known_at = _timestamp(row.get("known_at"))
    if _text(row.get("known_at")) is not None and known_at is None:
        return False
    if require_known_at and known_at is None:
        return False
    if known_at is not None and known_at > knowledge_cutoff:
        return False

    transaction_from = _timestamp(row.get("transaction_from"))
    transaction_to = _timestamp(row.get("transaction_to"), end_of_day=True)
    if (
        (_text(row.get("transaction_from")) is not None and transaction_from is None)
        or (_text(row.get("transaction_to")) is not None and transaction_to is None)
    ):
        return False
    if transaction_from is not None and transaction_from > knowledge_cutoff:
        return False
    if transaction_to is not None and transaction_to <= knowledge_cutoff:
        return False

    valid_from = _timestamp(row.get("valid_from"))
    if _text(row.get("valid_from")) is not None and valid_from is None:
        return False
    if require_valid_from and valid_from is None:
        return False
    if require_evidence and not _evidence_refs(row):
        return False
    valid_to = _timestamp(row.get("valid_to"), end_of_day=True)
    if _text(row.get("valid_to")) is not None and valid_to is None:
        return False
    if valid_from is not None and valid_from > effective_at:
        return False
    if valid_to is not None and valid_to < effective_at:
        return False
    return True


def _mapping_evidence_ready(
    row: Mapping[str, Any],
    *,
    effective_at: datetime,
    knowledge_cutoff: datetime,
) -> bool:
    """Return whether a graph claim has all required point-in-time proof.

    A relationship discovered without a start date or source evidence is not a
    historical fact.  This shared gate is intentionally used for exact
    identifiers, ownership edges, overrides, and terminal public-company
    records so no one path can silently backfill an attribution.
    """
    return _visible_and_active(
        row,
        effective_at=effective_at,
        knowledge_cutoff=knowledge_cutoff,
        require_known_at=True,
        require_valid_from=True,
        require_evidence=True,
    )


def _approved_state(row: Mapping[str, Any]) -> bool:
    value = _text(row.get("verification_state") or row.get("confidence_state") or row.get("reviewer_state"))
    return value is not None and value.lower() in _APPROVED_STATES


def _approved_override(row: Mapping[str, Any]) -> bool:
    value = _text(row.get("reviewer_state") or row.get("approval_state") or row.get("confidence_state"))
    return value is not None and value.lower() in _OVERRIDE_APPROVED


def _identifier_pairs_from_override(row: Mapping[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    source_identifier = row.get("source_identifier")
    candidates: list[Any] = [source_identifier]
    if row.get("namespace") is not None or row.get("value") is not None:
        candidates.append({"namespace": row.get("namespace"), "value": row.get("value")})
    source_ref = _text(row.get("source_entity_ref"))
    if source_ref and ":" in source_ref:
        namespace, value = source_ref.split(":", 1)
        candidates.append({"namespace": namespace, "value": value})
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            namespace = _normal_namespace(candidate.get("namespace"))
            value = _normal_identifier(namespace or "", candidate.get("value")) if namespace else None
        elif isinstance(candidate, str) and ":" in candidate:
            namespace_raw, value_raw = candidate.split(":", 1)
            namespace = _normal_namespace(namespace_raw)
            value = _normal_identifier(namespace or "", value_raw) if namespace else None
        else:
            namespace = value = None
        if namespace and value:
            pairs.add((namespace, value))
    return pairs


def _record_identifier_pairs(record: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for namespace, field_names, rule in _IDENTIFIER_LADDER:
        values: list[Any] = []
        for field in field_names:
            value = record.get(field)
            if isinstance(value, (list, tuple, set)):
                values.extend(value)
            else:
                values.append(value)
        for value in values:
            normalized = _normal_identifier(namespace, value)
            pair = (namespace, normalized or "")
            if normalized and pair not in seen:
                seen.add(pair)
                out.append((namespace, normalized, rule))
    return out


def _source_recipient(record: Mapping[str, Any]) -> dict[str, Any]:
    external_ids = [
        {"namespace": namespace, "value": value}
        for namespace, value, _rule in _record_identifier_pairs(record)
    ]
    return {
        "name": _text(record.get("recipient_name") or record.get("name")),
        "external_ids": external_ids,
    }


def _award_identity(record: Mapping[str, Any]) -> str | None:
    """Return a source-stable award identity, never a bare PIID fallback."""
    for field in (
        "generated_unique_award_id",
        "generated_award_id",
        "source_award_key",
        "award_key",
    ):
        value = _text(record.get(field))
        if value:
            return f"award:{value}"
    return None


def _action_identity(record: Mapping[str, Any]) -> str | None:
    """Return a source action ID only when it can be namespaced by an award."""
    for field in (
        "source_action_id",
        "source_action_key",
        "action_id",
        "action_uid",
        "transaction_unique_id",
        "transaction_id",
        "award_transaction_id",
    ):
        value = _text(record.get(field))
        if value:
            return value
    return None


def _unkeyed_fingerprint(record: Mapping[str, Any]) -> str:
    """Create a diagnostic-only fingerprint; it is never an attribution key."""
    payload = {
        key: record.get(key)
        for key in (
            "award_id",
            "piid",
            "action_id",
            "recipient_uei",
            "recipient_cage",
            "recipient_source_id",
            "effective_at",
            "action_date",
            "known_at",
            "amount",
        )
    }
    return sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]


def _source_identity(record: Mapping[str, Any]) -> tuple[str, bool, str]:
    """Return a key, stability flag, and identity kind for one observation.

    USAspending action IDs are not safe across awards.  An action observation
    therefore takes precedence only as an award-plus-action composite.  A
    generated unique award ID is preferred for award-level observations.  A
    bare PIID, bare action ID, or heuristic payload hash remains explicitly
    unkeyed and cannot support attribution or coverage.
    """
    award = _award_identity(record)
    action = _action_identity(record)
    if action and award:
        return f"action:{award}|{action}", True, "award_action"
    if action:
        return f"unkeyed-action:{_unkeyed_fingerprint(record)}", False, "action_without_award"

    explicit_record_key = _text(record.get("source_record_key"))
    if explicit_record_key and record.get("source_record_identity_stable") is True:
        return f"record:{explicit_record_key}", True, "explicit_record"
    if award:
        return award, True, "award"
    return f"unkeyed:{_unkeyed_fingerprint(record)}", False, "missing_stable_identity"


def source_record_key(record: Mapping[str, Any]) -> str:
    """Return the source key; callers must check stability before using it."""
    return _source_identity(record)[0]


def _source_identity_is_stable(record: Mapping[str, Any]) -> bool:
    return _source_identity(record)[1]


def _record_query_ids(record: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for field in ("discovery_query_ids", "discovery_query_id", "query_ids", "query_id"):
        value = record.get(field)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        else:
            values.append(value)
    return sorted({item for item in (_text(value) for value in values) if item})


def dedupe_source_records(
    records: Iterable[Mapping[str, Any]],
    *,
    as_of: str | datetime | None = None,
) -> list[dict[str, Any]]:
    """Globally dedupe source records and retain every discovery-query provenance.

    The newest known source revision wins.  Same-clock conflicting recipient
    identifiers fail closed downstream through ``_source_identity_conflict``.
    """
    knowledge_cutoff = _timestamp(as_of, end_of_day=True) if as_of is not None else None
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for ordinal, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            continue
        row = deepcopy(dict(raw))
        key, stable, kind = _source_identity(row)
        # An unkeyed fingerprint is diagnostic only.  Never merge two raw
        # observations merely because their incomplete fields happen to hash
        # alike; it could silently discard a real action.
        group_key = key if stable else f"{key}:ordinal:{ordinal}"
        row["_source_identity_stable"] = stable
        row["_source_identity_kind"] = kind
        grouped[group_key].append((ordinal, row))

    out: list[dict[str, Any]] = []
    for key in sorted(grouped):
        all_members = grouped[key]
        members = all_members
        if knowledge_cutoff is not None:
            members = [
                item for item in all_members
                if (known := _timestamp(item[1].get("known_at"))) is not None
                and known <= knowledge_cutoff
            ]
        if not members:
            # A future or clockless source revision cannot be selected into a
            # historical replay, even as an unresolved attribution.
            continue

        def rank(item: tuple[int, dict[str, Any]]) -> tuple[datetime, int]:
            known = _timestamp(item[1].get("known_at"))
            return (known or datetime.min.replace(tzinfo=timezone.utc), item[0])

        _ordinal, latest = max(members, key=rank)
        latest = deepcopy(latest)
        latest["_global_dedupe_key"] = key
        latest["_dedupe_input_count"] = len(members)
        latest["_dedupe_total_input_count"] = len(all_members)
        latest["discovery_query_ids"] = sorted({
            query_id for _ordinal, member in members for query_id in _record_query_ids(member)
        })

        latest_known = _timestamp(latest.get("known_at"))
        identities_by_namespace: dict[str, set[str]] = defaultdict(set)
        for _ordinal, member in members:
            if _timestamp(member.get("known_at")) != latest_known:
                continue
            for namespace, value, _rule in _record_identifier_pairs(member):
                identities_by_namespace[namespace].add(value)
        conflicts = sorted(
            namespace for namespace, values in identities_by_namespace.items() if len(values) > 1
        )
        if conflicts:
            latest["_source_identity_conflict"] = conflicts
        out.append(latest)
    return out


def _graph_identifier_rows(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _list_of_dicts(graph.get("identifiers"))
    for entity in _entity_rows(graph):
        entity_id = _text(entity.get("entity_id") or entity.get("id"))
        if not entity_id:
            continue
        for identifier in _list_of_dicts(entity.get("identifiers")):
            identifier.setdefault("entity_id", entity_id)
            rows.append(identifier)
        for namespace, fields, _rule in _IDENTIFIER_LADDER:
            for field in fields:
                raw = entity.get(field)
                values = raw if isinstance(raw, (list, tuple, set)) else [raw]
                for value in values:
                    if _text(value):
                        rows.append({
                            "entity_id": entity_id,
                            "namespace": namespace,
                            "value": value,
                            "known_at": entity.get("known_at"),
                            "valid_from": entity.get("valid_from"),
                            "valid_to": entity.get("valid_to"),
                            "verification_state": entity.get("verification_state"),
                            "evidence_refs": entity.get("evidence_refs"),
                        })
    return rows


def _active_explicit_conflicts(
    graph: Mapping[str, Any], *, effective_at: datetime, knowledge_cutoff: datetime
) -> list[dict[str, Any]]:
    """Return reviewed graph conflicts that are visible at this exact replay clock."""
    raw = graph.get("_recipient_graph_explicit_conflicts")
    rows = _list_of_dicts(raw if raw is not None else graph.get("conflicts"))
    return [
        row for row in rows
        if _approved_override(row)
        and _mapping_evidence_ready(
            row,
            effective_at=effective_at,
            knowledge_cutoff=knowledge_cutoff,
        )
    ]


def _identifier_conflicts(
    conflicts: Iterable[Mapping[str, Any]],
    identifiers: Iterable[tuple[str, str, str]],
) -> list[Mapping[str, Any]]:
    pairs = {(namespace, value) for namespace, value, _rule in identifiers}
    matches: list[Mapping[str, Any]] = []
    for conflict in conflicts:
        if (_text(conflict.get("scope")) or "").lower() != "identifier":
            continue
        namespace = _normal_namespace(conflict.get("namespace"))
        value = _normal_identifier(namespace or "", conflict.get("value")) if namespace else None
        if namespace and value and (namespace, value) in pairs:
            matches.append(conflict)
    return matches


def _entity_conflicts(
    conflicts: Iterable[Mapping[str, Any]], entity_id: str
) -> list[Mapping[str, Any]]:
    return [
        conflict for conflict in conflicts
        if (_text(conflict.get("scope")) or "").lower() in {"ownership", "issuer"}
        and _text(conflict.get("child_entity_id")) == entity_id
    ]


def _active_overrides(
    graph: Mapping[str, Any], *, effective_at: datetime, knowledge_cutoff: datetime
) -> list[dict[str, Any]]:
    return [
        row for row in _list_of_dicts(graph.get("overrides"))
        if _approved_override(row)
        and _mapping_evidence_ready(
            row,
            effective_at=effective_at,
            knowledge_cutoff=knowledge_cutoff,
        )
    ]


def _override_matches_record(
    override: Mapping[str, Any], record: Mapping[str, Any], identifier_pair: tuple[str, str] | None
) -> bool:
    record_constraint = _text(
        override.get("source_record_key") or override.get("record_key") or override.get("applies_to_record_key")
    )
    if record_constraint and record_constraint != source_record_key(record):
        return False
    pairs = _identifier_pairs_from_override(override)
    if pairs:
        return identifier_pair in pairs
    return bool(record_constraint)


def _identifier_candidates(
    graph: Mapping[str, Any],
    *,
    namespace: str,
    value: str,
    effective_at: datetime,
    knowledge_cutoff: datetime,
    overrides: list[dict[str, Any]],
    record: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    """Return candidates by entity and whether a terminal global block fired."""
    pair = (namespace, value)
    global_block = False
    blocked_entities: set[str] = set()
    for override in overrides:
        action = (_text(override.get("action")) or "").lower()
        if action not in _BLOCK_ACTIONS or not _override_matches_record(override, record, pair):
            continue
        target = _text(override.get("target_entity_id") or override.get("entity_id"))
        if target:
            blocked_entities.add(target)
        else:
            global_block = True
    if global_block:
        return {}, True

    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for identifier in _graph_identifier_rows(graph):
        candidate_namespace = _normal_namespace(identifier.get("namespace"))
        candidate_value = _normal_identifier(candidate_namespace or "", identifier.get("value")) if candidate_namespace else None
        entity_id = _text(identifier.get("entity_id"))
        if (
            candidate_namespace != namespace
            or candidate_value != value
            or not entity_id
            or entity_id in blocked_entities
            or not _approved_state(identifier)
            or not _mapping_evidence_ready(
                identifier,
                effective_at=effective_at,
                knowledge_cutoff=knowledge_cutoff,
            )
        ):
            continue
        candidates[entity_id].append({"row": identifier, "via_override": False})

    for override in overrides:
        action = (_text(override.get("action")) or "").lower()
        if action not in _ASSERT_IDENTIFIER_ACTIONS or not _override_matches_record(override, record, pair):
            continue
        target = _text(override.get("target_entity_id") or override.get("entity_id"))
        if target and target not in blocked_entities:
            candidates[target].append({"row": override, "via_override": True})
    return dict(candidates), False


def _preflight_identifier_blocks(
    overrides: Iterable[Mapping[str, Any]],
    *,
    record: Mapping[str, Any],
    identifiers: Iterable[tuple[str, str, str]],
) -> list[Mapping[str, Any]]:
    """Find terminal analyst blocks before any identifier ladder selection.

    A blocked CAGE/source identifier must not be bypassed simply because a UEI
    appears earlier in the ladder. An approved identifier block is a terminal
    source-policy decision, whether the analyst recorded an entity target for
    audit context or not.
    """
    pairs = [(namespace, value) for namespace, value, _rule in identifiers]
    matching: list[Mapping[str, Any]] = []
    for override in overrides:
        action = (_text(override.get("action")) or "").lower()
        if action not in _BLOCK_ACTIONS:
            continue
        if _override_matches_record(override, record, None) or any(
            _override_matches_record(override, record, pair) for pair in pairs
        ):
            matching.append(override)
    return matching


def _identifier_issuer_claims(row: Mapping[str, Any]) -> set[str]:
    """Extract explicit issuer claims attached to an exact identifier mapping."""
    return {
        value
        for value in (
            _text(row.get("issuer_company_id")),
            _text(row.get("target_company_id")),
            _text(row.get("parent_company_id")),
        )
        if value
    }


def _edge_is_approved(edge: Mapping[str, Any]) -> bool:
    value = _text(edge.get("confidence_state") or edge.get("verification_state") or edge.get("reviewer_state"))
    return value is not None and value.lower() in _APPROVED_STATES


def _ownership_edges(
    graph: Mapping[str, Any],
    *,
    child_entity_id: str,
    effective_at: datetime,
    knowledge_cutoff: datetime,
    overrides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for edge in _list_of_dicts(graph.get("ownership_edges")):
        child = _text(edge.get("child_entity_id"))
        if (
            child == child_entity_id
            and _edge_is_approved(edge)
            and _mapping_evidence_ready(
                edge,
                effective_at=effective_at,
                knowledge_cutoff=knowledge_cutoff,
            )
        ):
            materialized = dict(edge)
            materialized["_via_override"] = False
            rows.append(materialized)

    for override in overrides:
        action = (_text(override.get("action")) or "").lower()
        child = _text(override.get("child_entity_id"))
        if action in _ASSERT_OWNERSHIP_ACTIONS and child == child_entity_id:
            materialized = dict(override)
            materialized.setdefault("edge_id", override.get("override_id"))
            materialized.setdefault("parent_company_id", override.get("target_company_id"))
            materialized.setdefault("parent_entity_id", override.get("target_entity_id"))
            materialized.setdefault("confidence_state", "reviewed")
            materialized["_via_override"] = True
            rows.append(materialized)

    def applies_to_child(override: Mapping[str, Any]) -> bool:
        if _text(override.get("child_entity_id")) == child_entity_id:
            return True
        target_edge_id = _text(override.get("target_edge_id") or override.get("edge_id"))
        target_company_id = _text(override.get("target_company_id"))
        target_entity_id = _text(override.get("target_entity_id"))
        return any(
            (target_edge_id and target_edge_id == _text(edge.get("edge_id")))
            or (target_company_id and target_company_id == _text(edge.get("parent_company_id")))
            or (target_entity_id and target_entity_id == _text(edge.get("parent_entity_id")))
            for edge in rows
        )

    blockers = [
        override for override in overrides
        if (_text(override.get("action")) or "").lower() in _BLOCK_OWNERSHIP_ACTIONS
        and applies_to_child(override)
    ]
    if not blockers:
        return rows

    def blocked(edge: Mapping[str, Any]) -> bool:
        for override in blockers:
            edge_id = _text(override.get("target_edge_id") or override.get("edge_id"))
            if edge_id and edge_id == _text(edge.get("edge_id")):
                return True
            target_company = _text(override.get("target_company_id"))
            if target_company and target_company == _text(edge.get("parent_company_id")):
                return True
            target_entity = _text(override.get("target_entity_id"))
            if target_entity and target_entity == _text(edge.get("parent_entity_id")):
                return True
        return False

    return [edge for edge in rows if not blocked(edge)]


def _edge_share(edge: Mapping[str, Any]) -> tuple[float | None, str | None]:
    raw = edge.get("economic_share")
    if raw is None:
        relationship = (_text(edge.get("relationship")) or "").lower()
        if relationship in _FULL_OWNERSHIP_RELATIONSHIPS:
            return 1.0, None
        return None, "ownership_economic_share_missing"
    try:
        share = float(raw)
    except (TypeError, ValueError):
        return None, "ownership_economic_share_invalid"
    if not math.isfinite(share) or share <= 0 or share > 1:
        return None, "ownership_economic_share_invalid"
    return share, None


def _vetted_issuer(
    company_id: str,
    companies: Mapping[str, Mapping[str, Any]],
    *,
    effective_at: datetime,
    knowledge_cutoff: datetime,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Return only a reviewed, time-valid public-company terminal.

    An ownership edge pointing at a string is not enough to create a listed
    issuer. The terminal must be a separately vetted company record with a
    valid ticker, reviewer approval, evidence, and both clocks.
    """
    company = companies.get(company_id)
    if company is None:
        return None, "parent_company_not_vetted", []
    canonical_company_id = _text(company.get("company_id") or company.get("id"))
    ticker = _text(company.get("ticker"))
    if (
        canonical_company_id != company_id
        or ticker is None
        or _TICKER.fullmatch(ticker) is None
        or not _approved_state(company)
        or not _mapping_evidence_ready(
            company,
            effective_at=effective_at,
            knowledge_cutoff=knowledge_cutoff,
        )
    ):
        return None, "parent_company_not_vetted", []
    return {"company_id": company_id, "ticker": ticker}, None, _evidence_refs(company)


def _edge_payload(edge: Mapping[str, Any], child_entity_id: str, share: float) -> dict[str, Any]:
    return {
        "edge_id": _text(edge.get("edge_id") or edge.get("override_id")) or "unidentified-edge",
        "relationship": _text(edge.get("relationship")) or "unknown",
        "child_entity_id": child_entity_id,
        "parent_entity_id": _text(edge.get("parent_entity_id")),
        "parent_company_id": _text(edge.get("parent_company_id") or edge.get("target_company_id")),
        "economic_share": share,
        "valid_from": _iso(_timestamp(edge.get("valid_from"))),
        "valid_to": _iso(_timestamp(edge.get("valid_to"), end_of_day=True)),
        "known_at": _iso(_timestamp(edge.get("known_at"))),
        "evidence_refs": _evidence_refs(edge),
    }


def _resolve_ownership(
    entity_id: str,
    graph: Mapping[str, Any],
    *,
    effective_at: datetime,
    knowledge_cutoff: datetime,
    overrides: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], float | None, str, list[str], list[str]]:
    """Walk one temporal ownership path; ambiguity and loops fail closed."""
    entities = _entity_index(graph)
    companies = _company_index(graph)
    path: list[dict[str, Any]] = []
    evidence: list[str] = []
    reasons: list[str] = []
    current = entity_id
    allocation = 1.0
    reviewed = False
    visited: set[str] = set()

    for _depth in range(16):
        if current in visited:
            return None, path, None, "unresolved", ["ownership_cycle"], evidence
        visited.add(current)
        entity = entities.get(current)
        if entity is None:
            return None, path, None, "unresolved", ["ownership_entity_missing"], evidence

        # Entity metadata alone cannot create an issuer.  Every terminal
        # attribution must pass through a separately evidenced ownership edge.
        edges = _ownership_edges(
            graph,
            child_entity_id=current,
            effective_at=effective_at,
            knowledge_cutoff=knowledge_cutoff,
            overrides=overrides,
        )
        if not edges:
            return None, path, None, "unresolved", ["ownership_path_missing"], evidence
        if len(edges) > 1:
            return None, path, None, "conflicted", ["multiple_active_ownership_paths"], evidence

        edge = edges[0]
        share, share_error = _edge_share(edge)
        if share_error:
            return None, path, None, "unresolved", [share_error], evidence
        assert share is not None
        allocation *= share
        path.append(_edge_payload(edge, current, share))
        evidence.extend(_evidence_refs(edge))
        confidence = (_text(edge.get("confidence_state") or edge.get("reviewer_state")) or "").lower()
        reviewed = reviewed or confidence in {"reviewed", "analyst_approved"} or bool(edge.get("_via_override"))

        parent_company_id = _text(edge.get("parent_company_id") or edge.get("target_company_id"))
        parent_entity_id = _text(edge.get("parent_entity_id"))
        if parent_company_id and parent_entity_id:
            return None, path, None, "conflicted", ["ownership_edge_has_two_parent_types"], evidence
        if parent_company_id:
            issuer, terminal_error, company_evidence = _vetted_issuer(
                parent_company_id,
                companies,
                effective_at=effective_at,
                knowledge_cutoff=knowledge_cutoff,
            )
            if issuer is None:
                return None, path, None, "unresolved", [terminal_error or "parent_company_not_vetted"], evidence
            evidence.extend(company_evidence)
            return issuer, path, allocation, ("reviewed" if reviewed else "confirmed"), reasons, evidence
        if not parent_entity_id:
            return None, path, None, "unresolved", ["ownership_parent_missing"], evidence
        current = parent_entity_id
    return None, path, None, "unresolved", ["ownership_path_depth_exceeded"], evidence


def _result(
    *,
    record: Mapping[str, Any],
    effective_at: datetime | None,
    record_known_at: datetime | None,
    analysis_as_of: datetime | None,
    state: str,
    rule: str,
    recipient_entity_id: str | None,
    issuer: dict[str, Any] | None,
    ownership_path: list[dict[str, Any]],
    economic_share: float | None,
    evidence_refs: Iterable[str],
    reason_codes: Iterable[str],
) -> dict[str, Any]:
    return {
        "contract": RESOLUTION_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "record_key": _text(record.get("_global_dedupe_key")) or source_record_key(record),
        "source_identity_stable": _source_identity_is_stable(record),
        "source_recipient": _source_recipient(record),
        "event_effective_at": _iso(effective_at),
        "record_known_at": _iso(record_known_at),
        "analysis_as_of": _iso(analysis_as_of),
        "resolution_state": state,
        "resolution_rule": rule,
        "recipient_entity_id": recipient_entity_id,
        "issuer": issuer,
        "ownership_path": ownership_path,
        "economic_share": economic_share,
        "evidence_refs": sorted({value for value in (_text(item) for item in evidence_refs) if value}),
        "reason_codes": sorted({value for value in (_text(item) for item in reason_codes) if value}) or ["unclassified"],
        "authority": dict(AUTHORITY),
    }


def resolve_recipient(
    record: Mapping[str, Any],
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    """Resolve one recipient through exact IDs and temporal ownership only.

    ``as_of`` is an inclusive knowledge cutoff.  When omitted, the record's
    own ``known_at`` is used, which is intentionally conservative for a live
    event and forbids later graph facts from leaking backward.
    """
    raw = dict(record)
    effective_at = _timestamp(raw.get("event_effective_at") or raw.get("effective_at") or raw.get("action_date"))
    record_known_at = _timestamp(raw.get("known_at") or raw.get("first_seen_at"))
    analysis_as_of = _timestamp(as_of, end_of_day=True) if as_of is not None else record_known_at
    graph_view, graph_error = _graph_for_resolution(graph, as_of=as_of)

    if raw.get("_source_identity_conflict"):
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="conflicted", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["duplicate_source_recipient_conflict"],
        )
    if not _source_identity_is_stable(raw):
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["unstable_source_identity"],
        )
    if effective_at is None:
        return _result(
            record=raw, effective_at=None, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["missing_effective_clock"],
        )
    if record_known_at is None:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=None,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["missing_known_clock"],
        )
    if analysis_as_of is None:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=None, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["missing_analysis_clock"],
        )
    if record_known_at > analysis_as_of:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["record_not_known_at_asof"],
        )
    if effective_at > analysis_as_of:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["record_not_effective_at_asof"],
        )
    if graph_error or graph_view is None:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=[graph_error or "recipient_graph_invalid"],
        )

    identifiers = _record_identifier_pairs(raw)
    if not identifiers:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["missing_exact_identifier"],
        )
    overrides = _active_overrides(
        graph_view, effective_at=effective_at, knowledge_cutoff=analysis_as_of
    )
    explicit_conflicts = _active_explicit_conflicts(
        graph_view, effective_at=effective_at, knowledge_cutoff=analysis_as_of
    )
    matching_identifier_conflicts = _identifier_conflicts(explicit_conflicts, identifiers)
    if matching_identifier_conflicts:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="conflicted", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[
                ref for row in matching_identifier_conflicts for ref in _evidence_refs(row)
            ],
            reason_codes=["explicit_identifier_conflict"],
        )
    blocking_overrides = _preflight_identifier_blocks(
        overrides,
        record=raw,
        identifiers=identifiers,
    )
    if blocking_overrides:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="rejected", rule="analyst_override",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[
                ref for row in blocking_overrides for ref in _evidence_refs(row)
            ],
            reason_codes=["blocked_by_analyst_override"],
        )

    mapped_rules: list[str] = []
    matched_entries: list[dict[str, Any]] = []
    mapped_entities: set[str] = set()
    issuer_claims: set[str] = set()
    for namespace, value, default_rule in identifiers:
        candidates, global_block = _identifier_candidates(
            graph_view,
            namespace=namespace,
            value=value,
            effective_at=effective_at,
            knowledge_cutoff=analysis_as_of,
            overrides=overrides,
            record=raw,
        )
        if global_block:
            return _result(
                record=raw, effective_at=effective_at, record_known_at=record_known_at,
                analysis_as_of=analysis_as_of, state="rejected", rule="analyst_override",
                recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
                evidence_refs=[],
                reason_codes=["blocked_by_analyst_override"],
            )
        if not candidates:
            continue
        if len(candidates) > 1:
            evidence = [
                ref for entries in candidates.values() for entry in entries
                for ref in _evidence_refs(entry["row"])
            ]
            return _result(
                record=raw, effective_at=effective_at, record_known_at=record_known_at,
                analysis_as_of=analysis_as_of, state="conflicted", rule=default_rule,
                recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
                evidence_refs=evidence, reason_codes=["exact_identifier_maps_to_multiple_entities"],
            )

        entity_id, matches = next(iter(candidates.items()))
        mapped_rules.append(default_rule)
        mapped_entities.add(entity_id)
        matched_entries.extend(matches)
        for match in matches:
            issuer_claims.update(_identifier_issuer_claims(match["row"]))

    if not mapped_entities:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["exact_identifier_not_mapped"],
        )
    if len(mapped_entities) > 1:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="conflicted", rule=mapped_rules[0],
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[
                ref for match in matched_entries for ref in _evidence_refs(match["row"])
            ],
            reason_codes=["exact_identifiers_map_to_multiple_entities"],
        )
    if len(issuer_claims) > 1:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="conflicted", rule=mapped_rules[0],
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[
                ref for match in matched_entries for ref in _evidence_refs(match["row"])
            ],
            reason_codes=["exact_identifiers_map_to_multiple_issuers"],
        )

    entity_id = next(iter(mapped_entities))
    default_rule = mapped_rules[0]
    matching_entity_conflicts = _entity_conflicts(explicit_conflicts, entity_id)
    if matching_entity_conflicts:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="conflicted", rule=default_rule,
            recipient_entity_id=entity_id, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[
                ref for row in matching_entity_conflicts for ref in _evidence_refs(row)
            ],
            reason_codes=["explicit_ownership_or_issuer_conflict"],
        )
    via_override = any(match["via_override"] for match in matched_entries)
    identity_reviewed = via_override or any(
        (_text(match["row"].get("verification_state") or match["row"].get("reviewer_state")) or "").lower()
        in {"reviewed", "analyst_approved"}
        for match in matched_entries
    )
    issuer, path, share, ownership_state, ownership_reasons, ownership_evidence = _resolve_ownership(
        entity_id,
        graph_view,
        effective_at=effective_at,
        knowledge_cutoff=analysis_as_of,
        overrides=overrides,
    )
    evidence = [
        ref for match in matched_entries for ref in _evidence_refs(match["row"])
    ] + ownership_evidence
    if issuer is None:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state=ownership_state,
            rule="analyst_override" if via_override else default_rule,
            recipient_entity_id=entity_id, issuer=None, ownership_path=path,
            economic_share=None, evidence_refs=evidence, reason_codes=ownership_reasons,
        )
    if issuer_claims and issuer["company_id"] not in issuer_claims:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="conflicted",
            rule="analyst_override" if via_override else default_rule,
            recipient_entity_id=entity_id, issuer=None, ownership_path=path,
            economic_share=None, evidence_refs=evidence,
            reason_codes=["exact_identifier_issuer_conflicts_with_ownership"],
        )
    state = "reviewed" if identity_reviewed or ownership_state == "reviewed" else "confirmed"
    return _result(
        record=raw, effective_at=effective_at, record_known_at=record_known_at,
        analysis_as_of=analysis_as_of, state=state,
        rule="analyst_override" if via_override else default_rule,
        recipient_entity_id=entity_id, issuer=issuer, ownership_path=path,
        economic_share=share, evidence_refs=evidence,
        reason_codes=["exact_identifier_and_temporal_ownership_path"],
    )


def resolve_records(
    records: Iterable[Mapping[str, Any]],
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None = None,
) -> list[dict[str, Any]]:
    """Dedupe globally, then resolve each source record exactly once."""
    return [
        {"record": record, "resolution": resolve_recipient(record, graph, as_of=as_of)}
        for record in dedupe_source_records(records, as_of=as_of)
    ]


def attach_recipient_resolution(
    record: Mapping[str, Any],
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None = None,
    field: str = "recipient_resolution",
) -> dict[str, Any]:
    """Return an in-memory source-record copy with a non-authoritative resolution.

    The caller-owned record is never mutated and the source fields are copied
    verbatim. Resolution is annotation-only; a graph change can alter this
    annotation but cannot alter ``source_record_key(record)`` or event identity.
    """
    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping")
    target_field = _text(field)
    if target_field is None:
        raise ValueError("resolution field must be a non-empty string")
    joined = deepcopy(dict(record))
    joined[target_field] = resolve_recipient(record, graph, as_of=as_of)
    return joined


def attach_recipient_resolutions(
    records: Iterable[Mapping[str, Any]],
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None = None,
    field: str = "recipient_resolution",
) -> list[dict[str, Any]]:
    """Attach annotation copies for many raw records without deduping or mutation."""
    return [
        attach_recipient_resolution(record, graph, as_of=as_of, field=field)
        for record in records
        if isinstance(record, Mapping)
    ]


def _coverage_resolution_items(
    records: Iterable[Mapping[str, Any]],
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None,
    force_withheld: bool,
) -> list[dict[str, Any]]:
    """Coerce raw, attached, and resolver rows into isolated coverage inputs."""
    raw_records: list[Mapping[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, Mapping):
            continue
        nested_record = item.get("record")
        nested_resolution = item.get("resolution")
        if isinstance(nested_record, Mapping) and isinstance(nested_resolution, Mapping):
            if force_withheld:
                raw_records.append(nested_record)
            else:
                resolved.append({
                    "record": deepcopy(dict(nested_record)),
                    "resolution": deepcopy(dict(nested_resolution)),
                })
            continue
        attached = item.get("recipient_resolution")
        if isinstance(attached, Mapping):
            source = deepcopy(dict(item))
            source.pop("recipient_resolution", None)
            if force_withheld:
                raw_records.append(source)
            else:
                resolved.append({"record": source, "resolution": deepcopy(dict(attached))})
            continue
        raw_records.append(item)
    if raw_records:
        resolved.extend(resolve_records(raw_records, graph, as_of=as_of))
    return resolved


def _coverage_graph_result(
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None,
) -> dict[str, Any]:
    if _is_strict_graph_load_result(graph):
        return deepcopy(dict(graph))
    return load_recipient_entity_graph(graph, as_of=as_of)


def _coverage_graph_metadata(loaded: Mapping[str, Any]) -> dict[str, Any]:
    status = _text(loaded.get("status"))
    return {
        "load_status": status if status in _GRAPH_LOAD_STATUSES else "invalid",
        "graph_id": _text(loaded.get("graph_id")),
        "graph_known_at": _text(loaded.get("graph_known_at")),
        "graph_effective_at": _text(loaded.get("graph_effective_at")),
        "graph_digest": _text(loaded.get("graph_digest")),
        "error_codes": sorted({
            value for value in (_text(code) for code in loaded.get("error_codes", [])) if value
        }),
    }


def build_recipient_resolution_coverage(
    snapshots: Iterable[Mapping[str, Any]],
    actions: Iterable[Mapping[str, Any]],
    graph: Mapping[str, Any] | None,
    *,
    as_of: str | datetime | None = None,
    snapshot_collection: Mapping[str, Any] | None = None,
    action_collection: Mapping[str, Any] | None = None,
    snapshot_amount_field: str = "amount",
    action_amount_field: str = "amount",
) -> dict[str, Any]:
    """Report returned-scope recipient coverage independently for snapshots/actions.

    Both denominator rails use absolute values through ``build_entity_coverage``.
    If the strict graph is absent or invalid, source rows remain visible and are
    re-resolved as unresolved; pre-attached issuer annotations are never trusted.
    """
    loaded = _coverage_graph_result(graph, as_of=as_of)
    metadata = _coverage_graph_metadata(loaded)
    graph_ready = metadata["load_status"] == "ready"
    snapshot_items = _coverage_resolution_items(
        snapshots, loaded, as_of=as_of, force_withheld=not graph_ready
    )
    action_items = _coverage_resolution_items(
        actions, loaded, as_of=as_of, force_withheld=not graph_ready
    )
    snapshot = build_entity_coverage(
        snapshot_items,
        amount_field=snapshot_amount_field,
        amount_basis="absolute",
        collection=snapshot_collection,
        as_of=as_of,
    )
    action = build_entity_coverage(
        action_items,
        amount_field=action_amount_field,
        amount_basis="absolute",
        collection=action_collection,
        as_of=as_of,
    )
    as_of_stamp = _timestamp(as_of, end_of_day=True) if as_of is not None else None
    if as_of_stamp is None:
        report_stamps = [
            _timestamp(snapshot.get("as_of")),
            _timestamp(action.get("as_of")),
        ]
        present = [stamp for stamp in report_stamps if stamp is not None]
        as_of_stamp = max(present) if present else None
    known_stamps = [
        _timestamp(snapshot.get("known_at")),
        _timestamp(action.get("known_at")),
        _timestamp(metadata.get("graph_known_at")),
    ]
    known_at = max((stamp for stamp in known_stamps if stamp is not None), default=None)
    withheld = (
        graph_ready
        or (
            snapshot["records"]["issuer_attributed_records"] == 0
            and action["records"]["issuer_attributed_records"] == 0
        )
    )
    limitations = [
        "Snapshot and action coverage are independent returned-scope reports; neither is corpus coverage.",
        "Absolute amounts keep unresolved and conflicted de-obligations in each denominator.",
    ]
    if not graph_ready:
        limitations.append("Recipient graph is absent or invalid; issuer impacts are withheld while source records remain available.")
    return {
        "contract": RECIPIENT_RESOLUTION_COVERAGE_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "as_of": _iso(as_of_stamp),
        "known_at": _iso(known_at),
        "resolution_graph": metadata,
        "snapshot": snapshot,
        "action": action,
        "invariants": {
            "snapshot_independent": True,
            "action_independent": True,
            "absolute_denominators": True,
            "graph_withheld_when_not_ready": withheld,
        },
        "limitations": limitations,
    }


def _amount(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _unpack_resolution(item: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    resolution = item.get("resolution")
    record = item.get("record")
    if isinstance(resolution, Mapping) and isinstance(record, Mapping):
        return record, resolution
    return item, item


def _collection_summary(collection: Mapping[str, Any] | None) -> dict[str, Any]:
    source = collection or {}
    requested = int(source.get("queries_requested", source.get("requested_queries", 0)) or 0)
    complete = int(source.get("queries_complete", source.get("complete_queries", 0)) or 0)
    partial = int(source.get("queries_partial", source.get("partial_queries", 0)) or 0)
    failed = int(source.get("queries_failed", source.get("failed_queries", 0)) or 0)
    requested, complete, partial, failed = (
        max(0, requested), max(0, complete), max(0, partial), max(0, failed)
    )
    counts_are_coherent = requested > 0 and complete + partial + failed <= requested
    ratio = complete / requested if counts_are_coherent else None
    return {
        "queries_requested": requested,
        "queries_complete": complete,
        "queries_partial": partial,
        "queries_failed": failed,
        "query_completion_ratio": ratio,
        "complete_scope": bool(counts_are_coherent and complete == requested and partial == 0 and failed == 0),
    }


def build_entity_coverage(
    resolved_records: Iterable[Mapping[str, Any]],
    *,
    amount_field: str = "amount",
    amount_basis: str = "absolute",
    collection: Mapping[str, Any] | None = None,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    """Calculate coverage over globally unique returned source records.

    The denominator is deliberately the observed query-result scope.  It is
    never described as all USAspending spending.  ``absolute`` is the default
    for action coverage so positive and de-obligation records cannot cancel
    the denominator.
    """
    if amount_basis != "absolute":
        raise ValueError("coverage denominators must use the 'absolute' amount basis")

    inputs = [item for item in resolved_records if isinstance(item, Mapping)]
    requested_asof = _timestamp(as_of, end_of_day=True) if as_of is not None else None
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for ordinal, item in enumerate(inputs):
        _record, resolution = _unpack_resolution(item)
        key = _text(resolution.get("record_key")) or source_record_key(_record)
        # A diagnostic fallback may never merge two unkeyed observations.
        if resolution.get("source_identity_stable") is not True:
            key = f"{key}:unstable:{ordinal}"
        grouped[key].append(item)

    unique_items: list[Mapping[str, Any]] = []
    for key in sorted(grouped):
        members = grouped[key]

        def rank(item: Mapping[str, Any]) -> datetime:
            _record, resolution = _unpack_resolution(item)
            return _timestamp(resolution.get("record_known_at") or _record.get("known_at")) or datetime.min.replace(tzinfo=timezone.utc)

        # If a cutoff was requested, never let a newer resolution displace an
        # exact-cutoff resolution for the same source record.
        exact_cutoff_members = [
            item for item in members
            if requested_asof is not None
            and _timestamp(_unpack_resolution(item)[1].get("analysis_as_of")) == requested_asof
        ]
        unique_items.append(max(exact_cutoff_members or members, key=rank))

    states = {state: 0 for state in _ALL_STATES}
    amounts_present = 0
    amounts_missing = 0
    candidate_amount = 0.0
    mapped_amount = 0.0
    mapped_unallocated_amount = 0.0
    unmapped_amount = 0.0
    identity_resolved = 0
    issuer_attributed = 0
    single_issuer_rows = True
    allocation_within_bounds = True
    known_stamps: list[datetime] = []
    resolved_asof_stamps = [
        _timestamp(_unpack_resolution(item)[1].get("analysis_as_of"))
        for item in unique_items
    ]
    observed_asof_stamps = {
        stamp for stamp in resolved_asof_stamps if stamp is not None
    }
    homogeneous_analysis_clock = (
        not unique_items
        or (
            len(observed_asof_stamps) == 1
            and all(stamp is not None for stamp in resolved_asof_stamps)
        )
    )
    shared_analysis_asof = (
        next(iter(observed_asof_stamps)) if homogeneous_analysis_clock and observed_asof_stamps else None
    )
    eligible_records = 0
    excluded_unstable_identity = 0
    excluded_asof_mismatch = 0

    for item in unique_items:
        record, resolution = _unpack_resolution(item)
        state = _text(resolution.get("resolution_state")) or "unresolved"
        if state not in states:
            state = "unresolved"
        states[state] += 1
        stable_identity = resolution.get("source_identity_stable") is True
        resolution_asof = _timestamp(resolution.get("analysis_as_of"))
        cutoff_matches = (
            resolution_asof == requested_asof
            if requested_asof is not None
            else homogeneous_analysis_clock and resolution_asof == shared_analysis_asof
        )
        if not stable_identity:
            excluded_unstable_identity += 1
        if not cutoff_matches:
            excluded_asof_mismatch += 1
        if not stable_identity or not cutoff_matches:
            continue
        eligible_records += 1
        if _text(resolution.get("recipient_entity_id")):
            identity_resolved += 1
        issuer = resolution.get("issuer")
        share = _amount(resolution.get("economic_share"))
        attributable = (
            state in _ATTRIBUTED_STATES
            and isinstance(issuer, Mapping)
            and bool(_text(issuer.get("company_id")))
            and share is not None
            and 0 < share <= 1
        )
        if state in _ATTRIBUTED_STATES and not attributable:
            single_issuer_rows = False
        if share is not None and not (0 < share <= 1):
            allocation_within_bounds = False
        if attributable:
            issuer_attributed += 1
        known = _timestamp(resolution.get("record_known_at") or record.get("known_at"))
        if known:
            known_stamps.append(known)

        raw_amount = _amount(record.get(amount_field))
        if raw_amount is None:
            amounts_missing += 1
            continue
        amounts_present += 1
        measure = abs(raw_amount)
        candidate_amount += measure
        if attributable:
            assert share is not None
            mapped_amount += measure * share
            mapped_unallocated_amount += measure * (1.0 - share)
        else:
            unmapped_amount += measure

    candidate_value: float | None = candidate_amount if amounts_present else None
    mapped_value: float | None = mapped_amount if amounts_present else None
    unallocated_value: float | None = mapped_unallocated_amount if amounts_present else None
    unmapped_value: float | None = unmapped_amount if amounts_present else None
    coverage_ratio = (mapped_amount / candidate_amount) if candidate_amount > 0 else None
    query = _collection_summary(collection)
    coverage_asof = requested_asof or shared_analysis_asof
    known_at = max(known_stamps) if known_stamps else None
    input_count = sum(
        int((_unpack_resolution(item)[0]).get("_dedupe_input_count") or 1)
        for item in inputs
    )
    records_total = len(unique_items)
    duplicates_removed = max(0, input_count - records_total)
    state_balances = sum(states.values()) == records_total
    mapped_not_greater = (
        candidate_value is None
        or mapped_value is None
        or mapped_value <= candidate_value + 1e-9
    )
    limitations = [
        "Coverage denominator is unique returned source records, not the full USAspending corpus.",
        "Discovery queries and fuzzy recipient names do not create issuer attribution.",
        "Unresolved, rejected, conflicted, and partial-allocation records remain visible in coverage.",
    ]
    if not query["complete_scope"]:
        limitations.append("At least one query is incomplete, unknown, partial, or failed; returned-scope coverage is not corpus coverage.")
    if amounts_missing:
        limitations.append("Some unique source records have no usable value for the selected amount denominator.")
    if excluded_unstable_identity:
        limitations.append("Unkeyed or unstable source records were excluded from attribution and coverage denominators.")
    if excluded_asof_mismatch:
        limitations.append("Resolutions with an absent, mixed, or mismatched analysis cutoff were excluded from coverage.")
    return {
        "contract": COVERAGE_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "as_of": _iso(coverage_asof),
        "known_at": _iso(known_at),
        "collection": query,
        "records": {
            "input_records": input_count,
            "unique_source_records": records_total,
            "duplicates_removed": duplicates_removed,
            "records_eligible_for_coverage": eligible_records,
            "records_excluded_unstable_identity": excluded_unstable_identity,
            "records_excluded_asof_mismatch": excluded_asof_mismatch,
            "records_with_usable_amount": amounts_present,
            "records_without_usable_amount": amounts_missing,
            "recipient_identity_resolved_records": identity_resolved,
            "issuer_attributed_records": issuer_attributed,
            "unresolved_records": states["unresolved"],
            "conflicted_records": states["conflicted"],
            "rejected_records": states["rejected"],
        },
        "states": states,
        "amounts": {
            "field": amount_field,
            "basis": amount_basis,
            "candidate_amount": candidate_value,
            "mapped_attributable_amount": mapped_value,
            "mapped_unallocated_amount": unallocated_value,
            "unmapped_amount": unmapped_value,
            "mapping_coverage_ratio": coverage_ratio,
            "recipient_identity_resolution_ratio": (
                identity_resolved / eligible_records if eligible_records else None
            ),
            "issuer_attribution_count_ratio": (
                issuer_attributed / eligible_records if eligible_records else None
            ),
        },
        "invariants": {
            "global_source_dedupe": len(grouped) == records_total,
            "state_count_balances": state_balances,
            "mapped_amount_not_greater_than_candidate": mapped_not_greater,
            "attributed_rows_have_single_issuer": single_issuer_rows,
            "allocation_within_bounds": allocation_within_bounds,
            "stable_source_identity_only": excluded_unstable_identity == 0,
            "analysis_cutoff_matches_requested": excluded_asof_mismatch == 0,
        },
        "limitations": limitations,
    }


def coverage_invariants(coverage: Mapping[str, Any]) -> bool:
    """Return whether all serialized coverage invariants pass."""
    invariants = coverage.get("invariants")
    return bool(isinstance(invariants, Mapping) and invariants and all(invariants.values()))


@lru_cache(maxsize=1)
def _recipient_resolution_coverage_validator() -> Any:
    """Load the strict coverage contract with its local nested dependency."""

    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource

    contract_dir = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "government_revenue"
    )
    entity_schema = json.loads(
        (contract_dir / "government_entity_coverage.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    coverage_schema = json.loads(
        (
            contract_dir
            / "government_recipient_resolution_coverage.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(
        entity_schema["$id"], Resource.from_contents(entity_schema)
    )
    return Draft202012Validator(
        coverage_schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def is_valid_recipient_resolution_coverage(value: Any) -> bool:
    """Validate the complete coverage object and every declared invariant.

    Schema validity alone is insufficient at a publication boundary: a
    syntactically valid report may explicitly disclose that attribution or
    accounting invariants failed. Such a generation remains useful for local
    diagnosis, but it is not eligible to replace the canonical artifact.
    """

    if not isinstance(value, Mapping):
        return False
    try:
        if any(_recipient_resolution_coverage_validator().iter_errors(value)):
            return False
    except Exception:  # noqa: BLE001 - an unavailable validator is not a pass
        return False
    if not coverage_invariants(value):
        return False
    for rail in ("snapshot", "action"):
        report = value.get(rail)
        invariants = report.get("invariants") if isinstance(report, Mapping) else None
        if not isinstance(invariants, Mapping) or not invariants or not all(
            item is True for item in invariants.values()
        ):
            return False
    return True


__all__ = [
    "AUTHORITY",
    "COVERAGE_CONTRACT",
    "RECIPIENT_GRAPH_CONTRACT",
    "RECIPIENT_RESOLUTION_COVERAGE_CONTRACT",
    "RESOLUTION_CONTRACT",
    "SCHEMA_VERSION",
    "attach_recipient_resolution",
    "attach_recipient_resolutions",
    "build_entity_coverage",
    "build_recipient_resolution_coverage",
    "coverage_invariants",
    "dedupe_source_records",
    "load_recipient_entity_graph",
    "is_valid_recipient_resolution_coverage",
    "resolve_recipient",
    "resolve_records",
    "source_record_key",
]
