"""W7-B: the single allowlisted Neural Web reader for the operating packet.

Placement note (collision care, deliberate).  PRs #4689 and #4673 own Neural
Web outcome semantics and the edge ledger.  This reader consumes a packet; it
takes no part in outcome accounting, so it is built as a standalone module here
rather than edited into ``engine/neuralweb/``.  The registration seam is
explicit and one-way:

    from engine.biocatalyst.packet_reader import (
        NEURAL_WEB_READER_ID,
        register_operating_packet_reader,
        read_operating_packet,
    )

    register_operating_packet_reader(NEURAL_WEB_READER_ID, consumer="neural_web")
    view = read_operating_packet(packet_bytes, reader_id=NEURAL_WEB_READER_ID,
                                 evaluated_at="...Z")

A future Neural Web module calls those three names at its own import boundary.
Nothing here writes to Neural Web state, and nothing here needs to be edited
when that seam is wired.

Reader invariants, all fail-closed:

* **Allowlist.** Exactly one reader id may exist. An id outside the allowlist is
  refused, and a *second* registration — including re-registering the same id —
  fails. There is no "replace" path.
* **Schema validation before use.** The carrier is validated against
  ``biocatalyst_operating_packet.v1`` and its self-declared ``packet_hash`` is
  recomputed before a single field is exposed.
* **Bounded payloads and counts.** Byte ceilings are checked before parsing;
  source, evidence, fact, and read counts are capped after.
* **Freshness.** A backdated carrier and a carrier older than the hard age
  ceiling are both refused; a non-fresh but in-budget carrier is surfaced as
  non-fresh rather than quietly accepted.
* **Contradiction propagation.** Contradictions and corrections cross the
  boundary verbatim. An unavailable lane stays unavailable; it is never
  smoothed into ``none_known``.
* **Deterministic ordering.** Every exposed sequence is ordered by the carrier's
  own canonical order.
* **No write-back.** The view is a deep-frozen read-only projection; the caller's
  input mapping is never mutated, and the module writes nothing anywhere.
* **No authority escalation.** A requested authority above the carrier's cap is
  refused, granted actions are a subset of the carrier's, and the reader can
  never mark an LLM as able to originate signals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import threading
from types import MappingProxyType
from typing import Any, Mapping

from engine.sector_intelligence import (
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
)

from engine.biocatalyst.packet_producer import CONTRACT_ID


NEURAL_WEB_READER_ID = "neuralweb.biocatalyst_operating_packet_reader.v1"

# Exactly one reader is permitted. The allowlist and the capacity ceiling are
# separate controls on purpose: an unknown id is refused even while the registry
# is empty, and a known id is refused once the single slot is taken.
_ALLOWED_READER_IDS = frozenset({NEURAL_WEB_READER_ID})
_MAX_REGISTERED_READERS = 1

_AUTHORITY_RANK = {"A0_OBSERVE": 0, "A1_EXPLAIN": 1}
_ALLOWED_ACTIONS = frozenset(("observe", "explain"))
_ACTION_ORDER = {"observe": 0, "explain": 1}

_MAX_PACKET_BYTES = 2 * 1024 * 1024
_MAX_SOURCE_REFS = 1000
_MAX_EVIDENCE_REFS = 1000
_MAX_POINT_IN_TIME_FACTS = 1600
_MAX_OWNER_PROJECTION_READS = 32
_MAX_LANE_ITEMS = 64
_MAX_ENTITY_REFS = 100
_MAX_PACKET_AGE_SECONDS = 7_200
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 200_000
_MAX_TIMESTAMP_CHARS = 64
_MAX_CONSUMER_CHARS = 64

_CONSUMER_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_REGISTRY_LOCK = threading.Lock()
_REGISTRY: dict[str, "ReaderRegistration"] = {}


class OperatingPacketReaderError(ValueError):
    """One bounded W7-B refusal code."""


def _reject(code: str) -> None:
    raise OperatingPacketReaderError(code)


@dataclass(frozen=True)
class ReaderRegistration:
    """The immutable record of the single allowlisted reader."""

    reader_id: str
    consumer: str
    max_authority: str


@dataclass(frozen=True)
class OperatingPacketView:
    """A deep-frozen, read-only projection of one operating packet.

    Every container is a ``MappingProxyType`` or a ``tuple``: the view cannot be
    mutated, and mutating it is therefore not a path back into the carrier.
    """

    reader_id: str
    packet_id: str
    packet_hash: str
    sector: str
    generated_at: str
    knowledge_cutoff: str
    evaluated_at: str
    sector_packet_ref: str
    entity_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    owner_projection_reads: tuple[Mapping[str, Any], ...]
    point_in_time_facts: tuple[Mapping[str, Any], ...]
    freshness_state: str
    packet_age_seconds: int
    is_fresh: bool
    coverage: Mapping[str, Any]
    contradiction_state: str
    contradictions: tuple[Mapping[str, Any], ...]
    correction_state: str
    corrections: tuple[Mapping[str, Any], ...]
    identity_state: Mapping[str, Any]
    forecast_references: Mapping[str, Any]
    unavailable_families: tuple[Mapping[str, Any], ...]
    granted_max_authority: str
    granted_actions: tuple[str, ...]
    llm_may_originate_signals: bool
    warnings: tuple[str, ...]


def register_operating_packet_reader(
    reader_id: str, *, consumer: str, max_authority: str = "A1_EXPLAIN"
) -> ReaderRegistration:
    """Register the one permitted reader. A second registration fails."""

    if type(reader_id) is not str or reader_id not in _ALLOWED_READER_IDS:
        _reject("reader_not_allowlisted")
    if (
        type(consumer) is not str
        or len(consumer) > _MAX_CONSUMER_CHARS
        or not _CONSUMER_RE.fullmatch(consumer)
    ):
        _reject("reader_registration_invalid")
    if type(max_authority) is not str or max_authority not in _AUTHORITY_RANK:
        _reject("authority_escalation_forbidden")
    registration = ReaderRegistration(
        reader_id=reader_id, consumer=consumer, max_authority=max_authority
    )
    with _REGISTRY_LOCK:
        if len(_REGISTRY) >= _MAX_REGISTERED_READERS or reader_id in _REGISTRY:
            _reject("reader_allowlist_exhausted")
        _REGISTRY[reader_id] = registration
    return registration


def registered_reader_ids() -> tuple[str, ...]:
    """Return the registered reader ids in deterministic order."""

    with _REGISTRY_LOCK:
        return tuple(sorted(_REGISTRY))


def _reset_reader_registry() -> None:
    """Test/replay seam. Production never clears an allowlist slot."""

    with _REGISTRY_LOCK:
        _REGISTRY.clear()


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


def _preflight(value: Any, *, code: str) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if depth > _MAX_JSON_DEPTH or nodes > _MAX_JSON_NODES:
            _reject(code)
        if isinstance(current, Mapping):
            for key, item in current.items():
                if not isinstance(key, str):
                    _reject(code)
                stack.append((item, depth + 1))
        elif isinstance(current, (list, tuple)):
            for item in current:
                stack.append((item, depth + 1))


def _freeze(value: Any) -> Any:
    """Return a deep, immutable copy. No path from the view back to the input."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _bounded_rows(rows: Any, *, limit: int, code: str) -> tuple[Any, ...]:
    if not isinstance(rows, list) or len(rows) > limit:
        _reject(code)
    return tuple(_freeze(row) for row in rows)


def _lane(lane: Any, *, code: str) -> tuple[str, tuple[Mapping[str, Any], ...]]:
    """Propagate one disagreement lane verbatim; never smooth it."""

    if not isinstance(lane, Mapping):
        _reject(code)
    state = lane.get("state")
    if state not in {"none_known", "present", "unavailable"}:
        _reject(code)
    items = _bounded_rows(lane.get("items"), limit=_MAX_LANE_ITEMS, code=code)
    if state == "present" and not items:
        _reject(code)
    if state in {"none_known", "unavailable"} and items:
        _reject(code)
    return state, items


def read_operating_packet(
    packet: Mapping[str, Any] | bytes,
    *,
    reader_id: str,
    evaluated_at: str,
    max_authority: str = "A1_EXPLAIN",
) -> OperatingPacketView:
    """Validate one operating packet and return a frozen, non-escalating view."""

    with _REGISTRY_LOCK:
        registration = _REGISTRY.get(reader_id) if isinstance(reader_id, str) else None
    if registration is None or registration.reader_id not in _ALLOWED_READER_IDS:
        _reject("reader_not_registered")

    if type(max_authority) is not str or max_authority not in _AUTHORITY_RANK:
        _reject("authority_escalation_forbidden")
    if _AUTHORITY_RANK[max_authority] > _AUTHORITY_RANK[registration.max_authority]:
        _reject("authority_escalation_forbidden")

    if isinstance(packet, bytes):
        if len(packet) > _MAX_PACKET_BYTES:
            _reject("packet_size_unavailable")
        try:
            decoded = json.loads(packet)
        except (TypeError, ValueError, RecursionError, MemoryError):
            _reject("operating_packet_unavailable")
        _preflight(decoded, code="operating_packet_unavailable")
        packet_bytes = packet
    elif isinstance(packet, Mapping):
        _preflight(packet, code="operating_packet_unavailable")
        try:
            packet_bytes = canonical_json_bytes(packet)
            decoded = json.loads(packet_bytes)
        except (ContractError, TypeError, ValueError, RecursionError, MemoryError):
            _reject("operating_packet_unavailable")
        if len(packet_bytes) > _MAX_PACKET_BYTES:
            _reject("packet_size_unavailable")
    else:
        _reject("operating_packet_unavailable")
    if not isinstance(decoded, dict):
        _reject("operating_packet_unavailable")
    try:
        if canonical_json_bytes(decoded) != packet_bytes:
            _reject("operating_packet_unavailable")
    except (ContractError, TypeError, ValueError):
        _reject("operating_packet_unavailable")

    if decoded.get("contract_id") != CONTRACT_ID:
        _reject("operating_packet_unavailable")
    try:
        validate_contract(CONTRACT_ID, decoded)
    except (ContractError, TypeError, ValueError):
        _reject("operating_packet_unavailable")
    payload = {key: value for key, value in decoded.items() if key != "packet_hash"}
    if decoded.get("packet_hash") != canonical_json_sha256(payload):
        _reject("operating_packet_unavailable")

    entity_refs = _bounded_rows(
        decoded.get("entity_refs"), limit=_MAX_ENTITY_REFS, code="claim_budget_exceeded"
    )
    source_refs = _bounded_rows(
        decoded.get("source_refs"), limit=_MAX_SOURCE_REFS, code="claim_budget_exceeded"
    )
    evidence_refs = _bounded_rows(
        decoded.get("evidence_refs"), limit=_MAX_EVIDENCE_REFS, code="claim_budget_exceeded"
    )
    facts = _bounded_rows(
        decoded.get("point_in_time_facts"),
        limit=_MAX_POINT_IN_TIME_FACTS,
        code="claim_budget_exceeded",
    )
    reads = _bounded_rows(
        decoded.get("owner_projection_reads"),
        limit=_MAX_OWNER_PROJECTION_READS,
        code="claim_budget_exceeded",
    )
    if not reads:
        _reject("operating_packet_unavailable")

    evaluated = _utc(evaluated_at, code="evaluated_at_unavailable")
    generated = _utc(decoded.get("generated_at"), code="operating_packet_unavailable")
    if generated > evaluated:
        _reject("evaluated_at_unavailable")
    age_seconds = int((evaluated - generated).total_seconds())
    if age_seconds > _MAX_PACKET_AGE_SECONDS:
        _reject("packet_freshness_unavailable")
    freshness = decoded.get("freshness")
    if not isinstance(freshness, Mapping):
        _reject("operating_packet_unavailable")
    freshness_state = freshness.get("state")
    if freshness_state not in {"fresh", "stale", "unknown", "degraded"}:
        _reject("operating_packet_unavailable")

    contradiction_state, contradictions = _lane(
        decoded.get("contradictions"), code="contradiction_reference_unavailable"
    )
    correction_state, corrections = _lane(
        decoded.get("corrections"), code="correction_reference_unavailable"
    )

    identity_state = decoded.get("identity_state")
    if (
        not isinstance(identity_state, Mapping)
        or identity_state.get("availability") != "unavailable"
        or identity_state.get("inference_from_registry_record") != "forbidden"
        or identity_state.get("issuer_refs")
        or identity_state.get("security_refs")
    ):
        _reject("identity_bridge_unavailable")

    caps = decoded.get("authority_caps")
    if not isinstance(caps, Mapping):
        _reject("authority_escalation_forbidden")
    packet_authority = caps.get("max_authority")
    if packet_authority not in _AUTHORITY_RANK:
        _reject("authority_escalation_forbidden")
    if caps.get("llm_may_originate_signals") is not False:
        _reject("authority_escalation_forbidden")
    packet_actions = caps.get("allowed_actions")
    if (
        not isinstance(packet_actions, list)
        or not packet_actions
        or not set(packet_actions).issubset(_ALLOWED_ACTIONS)
    ):
        _reject("authority_escalation_forbidden")
    # The grant is the floor of what was requested and what the carrier caps —
    # never the maximum, and never the request alone.
    granted_authority = (
        max_authority
        if _AUTHORITY_RANK[max_authority] <= _AUTHORITY_RANK[packet_authority]
        else packet_authority
    )
    granted_actions = set(packet_actions)
    if granted_authority == "A0_OBSERVE":
        granted_actions &= {"observe"}

    return OperatingPacketView(
        reader_id=registration.reader_id,
        packet_id=str(decoded["packet_id"]),
        packet_hash=str(decoded["packet_hash"]),
        sector=str(decoded["sector"]),
        generated_at=str(decoded["generated_at"]),
        knowledge_cutoff=str(decoded["knowledge_cutoff"]),
        evaluated_at=evaluated_at,
        sector_packet_ref=str(decoded["sector_packet_ref"]),
        entity_refs=entity_refs,
        source_refs=source_refs,
        evidence_refs=evidence_refs,
        owner_projection_reads=reads,
        point_in_time_facts=facts,
        freshness_state=str(freshness_state),
        packet_age_seconds=age_seconds,
        is_fresh=freshness_state == "fresh",
        coverage=_freeze(decoded.get("coverage")),
        contradiction_state=contradiction_state,
        contradictions=contradictions,
        correction_state=correction_state,
        corrections=corrections,
        identity_state=_freeze(identity_state),
        forecast_references=_freeze(decoded.get("forecast_references")),
        unavailable_families=_bounded_rows(
            decoded.get("unavailable_families"), limit=16, code="operating_packet_unavailable"
        ),
        granted_max_authority=granted_authority,
        granted_actions=tuple(sorted(granted_actions, key=_ACTION_ORDER.__getitem__)),
        llm_may_originate_signals=False,
        warnings=_bounded_rows(
            decoded.get("warnings"), limit=32, code="operating_packet_unavailable"
        ),
    )


__all__ = [
    "NEURAL_WEB_READER_ID",
    "OperatingPacketReaderError",
    "OperatingPacketView",
    "ReaderRegistration",
    "read_operating_packet",
    "register_operating_packet_reader",
    "registered_reader_ids",
]
