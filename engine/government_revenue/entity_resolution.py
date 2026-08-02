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
from hashlib import sha256
import json
import math
import re
from typing import Any, Iterable, Mapping


RESOLUTION_CONTRACT = "government_recipient_resolution.v1"
COVERAGE_CONTRACT = "government_entity_coverage.v1"
SCHEMA_VERSION = "1.0.0"

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

    blockers = [
        override for override in overrides
        if (_text(override.get("action")) or "").lower() in _BLOCK_OWNERSHIP_ACTIONS
        and _text(override.get("child_entity_id")) == child_entity_id
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
    graph: Mapping[str, Any],
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

    identifiers = _record_identifier_pairs(raw)
    if not identifiers:
        return _result(
            record=raw, effective_at=effective_at, record_known_at=record_known_at,
            analysis_as_of=analysis_as_of, state="unresolved", rule="none",
            recipient_entity_id=None, issuer=None, ownership_path=[], economic_share=None,
            evidence_refs=[], reason_codes=["missing_exact_identifier"],
        )
    overrides = _active_overrides(
        graph, effective_at=effective_at, knowledge_cutoff=analysis_as_of
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
            graph,
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
    via_override = any(match["via_override"] for match in matched_entries)
    identity_reviewed = via_override or any(
        (_text(match["row"].get("verification_state") or match["row"].get("reviewer_state")) or "").lower()
        in {"reviewed", "analyst_approved"}
        for match in matched_entries
    )
    issuer, path, share, ownership_state, ownership_reasons, ownership_evidence = _resolve_ownership(
        entity_id,
        graph,
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
    graph: Mapping[str, Any],
    *,
    as_of: str | datetime | None = None,
) -> list[dict[str, Any]]:
    """Dedupe globally, then resolve each source record exactly once."""
    return [
        {"record": record, "resolution": resolve_recipient(record, graph, as_of=as_of)}
        for record in dedupe_source_records(records, as_of=as_of)
    ]


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


__all__ = [
    "AUTHORITY",
    "COVERAGE_CONTRACT",
    "RESOLUTION_CONTRACT",
    "SCHEMA_VERSION",
    "build_entity_coverage",
    "coverage_invariants",
    "dedupe_source_records",
    "resolve_recipient",
    "resolve_records",
    "source_record_key",
]
