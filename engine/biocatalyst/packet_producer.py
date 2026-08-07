"""W7-A deterministic BioCatalyst operating-packet producer.

This module is the missing production caller for the already-shipped BC-N0a
compiler in :mod:`engine.biocatalyst.sector_packet`.  It does not re-implement
that compiler: it binds the compiler's output to the owner projections that are
actually eligible today and emits one bounded ``biocatalyst_operating_packet.v1``
carrier.

Three fences are load-bearing and deliberately fail closed.

*Owner projections only.*  The producer accepts pre-read owner projection
descriptors whose ``projection_id`` must appear in :data:`OWNER_PROJECTION_IDS`
— the private surface behind ``app/biocatalyst.py``.  A raw store behind those
projections (collector state, source snapshots, history/discovery raw artifacts,
the publication generation directory) is not an owner projection and is refused
by name.  The producer also performs no I/O and runs no model: it is a pure
function of its arguments, so a caller cannot smuggle a raw read through it.

*Identity is unavailable, not inferred.*  There is no eligible point-in-time
issuer/security identity bridge.  The identity block therefore always declares
``unavailable`` with its blocker named.  A caller that hands the producer an
identity resolution is refused rather than served: sponsor, ticker, issuer, and
security are never derived from an NCT record.  This is an authority fence, not
a TODO.

*Forecast references are empty by evidence.*  Nothing is ledgered yet.  The
packet distinguishes "empty because the ledger lane was enumerated and holds
nothing" from "empty because the lane could not be read at all"; the enumerated
lane is the compiled sector packet's own ``prediction_refs``.

The carrier emits nothing to R2, exposes no public route, writes no dataset, no
alert, and no ledger accrual.  Authority stays A0/A1 and the packet may not
originate a probability, ranking, signal, score, or escalation.
``DNR:KILL-PHASE3-START-WEIGHT`` is live: Phase-3 START is display/context tier
only and is never carried here as a scored catalyst leg.
"""
from __future__ import annotations

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


CONTRACT_ID = "biocatalyst_operating_packet.v1"
SECTOR = "biopharma"

_PRODUCER = {
    "service": "biocatalyst-operating-packet",
    "code_version": "bc-w7a.v1",
    "owner": "biocatalyst",
}

# Exactly the private trial-projection surface behind ``app/biocatalyst.py``:
# trials, trial detail, milestones, changes, change-tape, prospective-changes,
# trials:screen, trials:screen/facets, trial-peer-sets:resolve, plus the health
# DTO those routes already publish.  Nothing else is an owner projection.
OWNER_PROJECTION_IDS = frozenset(
    {
        "biocatalyst.health.v1",
        "biocatalyst.trial_detail.v1",
        "biocatalyst.trial_peer_sets.resolve.v1",
        "biocatalyst.trials.v1",
        "biocatalyst.trials.change_tape.v1",
        "biocatalyst.trials.changes.v1",
        "biocatalyst.trials.milestones.v1",
        "biocatalyst.trials.prospective_changes.v1",
        "biocatalyst.trials_screen.facets.v1",
        "biocatalyst.trials_screen.v1",
    }
)

# Named for refusal receipts.  These are the raw stores *behind* the owner
# projections; reading one here would bypass the projection boundary that owns
# redaction, authority, and point-in-time semantics.
FORBIDDEN_RAW_STORE_IDS = frozenset(
    {
        "biocatalyst.raw.collector_state.v1",
        "biocatalyst.raw.discovery_run.v1",
        "biocatalyst.raw.history_snapshot.v1",
        "biocatalyst.raw.publication_generation.v1",
        "biocatalyst.raw.storage.v1",
        "biocatalyst.raw.trial_source_snapshot.v1",
    }
)

IDENTITY_BLOCKER = "no_eligible_point_in_time_issuer_security_identity_bridge"
IDENTITY_BLOCKER_NOTE = (
    "No eligible point-in-time issuer or security identity bridge exists for "
    "ClinicalTrials.gov records. Sponsor, ticker, issuer, and security are not "
    "inferred from a registry record."
)
_DARK_FAMILY_BLOCKERS = {
    "capital_structure": "no_eligible_point_in_time_capital_structure_projection",
    "identity": IDENTITY_BLOCKER,
    "market": "no_eligible_point_in_time_market_projection",
    "ownership": "no_eligible_point_in_time_ownership_projection",
    "regulatory": "no_eligible_point_in_time_regulatory_projection",
}
_FORECAST_LANE = "sector_intelligence_packet.v1#prediction_refs"
_FORECAST_EMPTY_REASON = (
    "The sector packet's forecast lane was enumerated under a complete compile "
    "and holds no ledgered forecast: empty by evidence, not empty because the "
    "lane was unreadable."
)
_FORECAST_UNAVAILABLE_REASON = (
    "The sector packet compiled degraded, so its empty forecast lane is not "
    "evidence of absence: emptiness here is unavailability."
)

_ALLOWED_AUTHORITIES = frozenset(("A0_OBSERVE", "A1_EXPLAIN"))
_ALLOWED_ACTIONS = frozenset(("observe", "explain"))
_ACTION_ORDER = {"observe": 0, "explain": 1}
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

_MAX_OWNER_PROJECTION_READS = 32
_MAX_READ_PAYLOAD_BYTES = 512 * 1024
_MAX_AGGREGATE_READ_BYTES = 2 * 1024 * 1024
_MAX_TRIAL_PROJECTIONS = 100
_MAX_TRIAL_PROJECTION_BYTES = 256 * 1024
_MAX_POINT_IN_TIME_FACTS = 1600
_MAX_FACT_VALUE_BYTES = 8 * 1024
_MAX_LANE_ITEMS = 64
_MAX_DETAIL_CHARS = 512
_MAX_PACKET_BYTES = 2 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 200_000
_MAX_TIMESTAMP_CHARS = 64

_NCT_ID_RE = re.compile(r"^NCT[0-9]{8}$")
_SECTOR_PACKET_ID_RE = re.compile(r"^packet:biopharma:[a-f0-9]{24}$")
_SOURCE_REF_RE = re.compile(r"^src:ctgov:(NCT[0-9]{8}):sha256:[a-f0-9]{64}$")
_FACT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_LANE_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PROJECTION_ID_RE = re.compile(r"^biocatalyst\.[a-z][a-z0-9_.]{0,63}\.v1$")


class OperatingPacketError(ValueError):
    """One bounded W7-A refusal code."""


def _reject(code: str) -> None:
    raise OperatingPacketError(code)


def _bounded_json(value: Any, *, code: str, max_bytes: int) -> tuple[Any, bytes]:
    """Canonicalize one bounded JSON value after an iterative structural check."""

    _preflight(value, code=code)
    try:
        payload = canonical_json_bytes(value)
        normalized = json.loads(payload)
    except (ContractError, TypeError, ValueError, RecursionError, MemoryError):
        _reject(code)
    if len(payload) > max_bytes:
        _reject(code)
    return normalized, payload


def _preflight(value: Any, *, code: str) -> None:
    """Bound depth and node count iteratively, before recursive machinery runs."""

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
        elif isinstance(current, float) and not math.isfinite(current):
            _reject(code)


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


def _format_utc(value: datetime) -> str:
    rendered = (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d}T"
        f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    )
    if value.microsecond:
        rendered += "." + f"{value.microsecond:06d}".rstrip("0")
    return rendered + "Z"


def _text(value: Any, *, code: str, maximum: int) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _reject(code)
    return value


def _ordered_actions(actions: Sequence[str]) -> list[str]:
    return sorted(actions, key=_ACTION_ORDER.__getitem__)


def _owner_projection_read(read: Any) -> dict[str, Any]:
    """Normalize one owner-projection read, refusing any non-projection source.

    The allowlist is the whole point of this function.  A raw store behind an
    owner projection is refused by name so a caller cannot reach past the
    projection boundary that owns redaction, authority, and point-in-time
    semantics.
    """

    if not isinstance(read, Mapping):
        _reject("owner_projection_unavailable")
    projection_id = read.get("projection_id")
    if not isinstance(projection_id, str) or not _PROJECTION_ID_RE.fullmatch(projection_id):
        _reject("owner_projection_unavailable")
    if projection_id in FORBIDDEN_RAW_STORE_IDS:
        _reject("raw_store_read_forbidden")
    if projection_id not in OWNER_PROJECTION_IDS:
        _reject("raw_store_read_forbidden")
    if set(read) - {
        "projection_id",
        "as_of",
        "row_count",
        "payload",
        "contradictions",
        "corrections",
    }:
        _reject("owner_projection_unavailable")
    as_of = _format_utc(_utc(read.get("as_of"), code="owner_projection_unavailable"))
    row_count = read.get("row_count")
    if isinstance(row_count, bool) or not isinstance(row_count, int) or not 0 <= row_count <= 100_000:
        _reject("owner_projection_unavailable")
    if "payload" not in read:
        _reject("owner_projection_unavailable")
    _, payload_bytes = _bounded_json(
        read["payload"],
        code="owner_projection_unavailable",
        max_bytes=_MAX_READ_PAYLOAD_BYTES,
    )
    payload_sha256 = canonical_json_sha256(json.loads(payload_bytes))
    return {
        "read_id": f"read:{projection_id}:{payload_sha256[:24]}",
        "projection_id": projection_id,
        "as_of": as_of,
        "row_count": row_count,
        "payload_sha256": payload_sha256,
        "_payload_bytes": payload_bytes,
        # ``None`` means the read declared no lane at all.  An explicit empty
        # list means the read looked and found nothing.  Those are different
        # states and are never collapsed into each other.
        "_contradictions": read.get("contradictions"),
        "_corrections": read.get("corrections"),
    }


def _lane_items(raw: Any, *, read_id: str, entity_refs: frozenset[str], code: str) -> list[dict[str, Any]]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        _reject(code)
    items: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {"kind", "entity_ref", "detail"}:
            _reject(code)
        kind = _text(item.get("kind"), code=code, maximum=64)
        if not _LANE_KIND_RE.fullmatch(kind):
            _reject(code)
        entity_ref = _text(item.get("entity_ref"), code=code, maximum=64)
        if entity_ref not in entity_refs:
            _reject(code)
        items.append(
            {
                "kind": kind,
                "entity_ref": entity_ref,
                "detail": _text(item.get("detail"), code=code, maximum=_MAX_DETAIL_CHARS),
                "read_id": read_id,
            }
        )
    return items


def _lane(
    reads: Sequence[Mapping[str, Any]],
    *,
    key: str,
    entity_refs: frozenset[str],
    code: str,
) -> dict[str, Any]:
    """Aggregate one disagreement lane without ever smoothing it away.

    A lane no owner read declares is ``unavailable`` — the honest state for "we
    could not look" — and is never collapsed into ``none_known``.
    """

    declared = False
    items: list[dict[str, Any]] = []
    evidence_refs: list[str] = []
    for read in reads:
        raw = read[key]
        if raw is None:
            continue
        declared = True
        evidence_refs.append(read["read_id"])
        items.extend(
            _lane_items(raw, read_id=read["read_id"], entity_refs=entity_refs, code=code)
        )
    if len(items) > _MAX_LANE_ITEMS:
        _reject(code)
    if not declared:
        return {"state": "unavailable", "items": [], "evidence_refs": []}
    ordered = sorted(
        items, key=lambda row: (row["entity_ref"], row["kind"], row["detail"], row["read_id"])
    )
    return {
        "state": "present" if ordered else "none_known",
        "items": ordered,
        "evidence_refs": sorted(set(evidence_refs)),
    }


def _point_in_time_facts(projections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for projection in projections:
        nct_id = projection["nct_id"]
        entity_ref = f"trial:{nct_id}"
        source_ref = projection["source_record_ref"]
        knowledge_cutoff = _format_utc(
            _utc(projection.get("knowledge_cutoff"), code="trial_projection_unavailable")
        )
        # ClinicalTrials.gov frequently declares no effective instant. That
        # absence is carried as null, never backfilled from the retrieval clock:
        # ``knowledge_cutoff`` already records when the fact was observed.
        observed_at = projection.get("source_effective_at")
        if observed_at is not None and (
            not isinstance(observed_at, str)
            or not observed_at
            or len(observed_at) > _MAX_TIMESTAMP_CHARS
        ):
            _reject("trial_projection_unavailable")
        raw_facts = projection.get("facts")
        if not isinstance(raw_facts, Mapping):
            _reject("trial_projection_unavailable")
        for fact_key in sorted(raw_facts):
            fact = raw_facts[fact_key]
            if not isinstance(fact, Mapping) or fact.get("state") != "observed":
                continue
            if not _FACT_KEY_RE.fullmatch(fact_key):
                _reject("trial_projection_unavailable")
            value, value_bytes = _bounded_json(
                fact.get("value"),
                code="trial_projection_unavailable",
                max_bytes=_MAX_READ_PAYLOAD_BYTES,
            )
            omitted = len(value_bytes) > _MAX_FACT_VALUE_BYTES
            facts.append(
                {
                    "entity_ref": entity_ref,
                    "fact_key": fact_key,
                    "state": "observed",
                    "source_json_path": _text(
                        fact.get("source_json_path"),
                        code="trial_projection_unavailable",
                        maximum=256,
                    ),
                    "source_ref": source_ref,
                    "observed_at": observed_at,
                    "knowledge_cutoff": knowledge_cutoff,
                    # An oversized value is declared omitted, never silently
                    # truncated: the hash still binds the exact source value.
                    "value": None if omitted else value,
                    "value_sha256": canonical_json_sha256(value),
                    "value_omitted_reason": "fact_value_exceeds_packet_budget" if omitted else None,
                }
            )
    if len(facts) > _MAX_POINT_IN_TIME_FACTS:
        _reject("point_in_time_facts_unavailable")
    return sorted(facts, key=lambda row: (row["entity_ref"], row["fact_key"]))


def _validate_sector_packet(sector_packet: Any) -> dict[str, Any]:
    packet, _ = _bounded_json(
        sector_packet, code="sector_packet_unavailable", max_bytes=_MAX_PACKET_BYTES
    )
    if not isinstance(packet, dict):
        _reject("sector_packet_unavailable")
    try:
        validate_contract("sector_intelligence_packet.v1", packet)
    except (ContractError, TypeError, ValueError):
        _reject("sector_packet_unavailable")
    if packet.get("sector") != SECTOR:
        _reject("sector_packet_unavailable")
    packet_id = packet.get("packet_id")
    if not isinstance(packet_id, str) or not _SECTOR_PACKET_ID_RE.fullmatch(packet_id):
        _reject("sector_packet_unavailable")
    declared_hash = packet.get("packet_hash")
    payload = {key: value for key, value in packet.items() if key != "packet_hash"}
    if declared_hash != canonical_json_sha256(payload):
        _reject("sector_packet_unavailable")
    caps = packet.get("authority_caps")
    if not isinstance(caps, Mapping):
        _reject("authority_cap_unavailable")
    if caps.get("max_authority") not in _ALLOWED_AUTHORITIES:
        _reject("authority_cap_unavailable")
    actions = caps.get("allowed_actions")
    if (
        not isinstance(actions, list)
        or not actions
        or len(set(actions)) != len(actions)
        or not set(actions).issubset(_ALLOWED_ACTIONS)
        or "observe" not in actions
        or (caps.get("max_authority") == "A0_OBSERVE" and set(actions) != {"observe"})
    ):
        _reject("authority_cap_unavailable")
    denials = caps.get("forbidden_actions")
    if not isinstance(denials, list) or not _REQUIRED_DENIALS.issubset(set(denials)):
        _reject("authority_cap_unavailable")
    if caps.get("llm_may_originate_signals") is not False:
        _reject("authority_cap_unavailable")
    return packet


def _forecast_references(sector_packet: Mapping[str, Any]) -> dict[str, Any]:
    """Distinguish enumerated-and-empty from unreadable, never conflate them."""

    lane = sector_packet.get("prediction_refs")
    if not isinstance(lane, list):
        _reject("sector_packet_unavailable")
    if lane:
        # Nothing is ledgered yet.  A non-empty lane means the caller's world
        # moved past this producer's evidence; refuse instead of publishing an
        # unbacked forecast reference.
        _reject("forecast_reference_unavailable")
    quality = sector_packet.get("quality")
    if not isinstance(quality, Mapping) or quality.get("state") != "complete":
        # A degraded compile may simply not have seen the ledger.  Its empty
        # lane is therefore unavailability, not evidence of absence.
        return {
            "availability": "unavailable",
            "refs": [],
            "reason": _FORECAST_UNAVAILABLE_REASON,
            "enumerated_lane": _FORECAST_LANE,
            "evidence_ref": None,
        }
    return {
        "availability": "available_enumerated_empty",
        "refs": [],
        "reason": _FORECAST_EMPTY_REASON,
        "enumerated_lane": _FORECAST_LANE,
        "evidence_ref": sector_packet["packet_id"],
    }


def _identity_state(identity_resolutions: Any) -> dict[str, Any]:
    """Return the only admissible identity block: unavailable, blocker named.

    A caller that supplies an identity resolution is refused.  The producer has
    no eligible bridge, so accepting one would be an inference dressed as a
    fact.
    """

    if isinstance(identity_resolutions, (str, bytes)) or not isinstance(
        identity_resolutions, Sequence
    ):
        _reject("identity_bridge_unavailable")
    if len(identity_resolutions) != 0:
        _reject("identity_bridge_unavailable")
    return {
        "availability": "unavailable",
        "blocker": IDENTITY_BLOCKER,
        "blocker_note": IDENTITY_BLOCKER_NOTE,
        "issuer_refs": [],
        "security_refs": [],
        "inference_from_registry_record": "forbidden",
    }


def _trial_projections(projections: Any, *, entity_refs: Sequence[str]) -> tuple[dict[str, Any], ...]:
    if isinstance(projections, (str, bytes)) or not isinstance(projections, Sequence):
        _reject("trial_projection_unavailable")
    if not projections or len(projections) > _MAX_TRIAL_PROJECTIONS:
        _reject("trial_projection_unavailable")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for projection in projections:
        payload, _ = _bounded_json(
            projection,
            code="trial_projection_unavailable",
            max_bytes=_MAX_TRIAL_PROJECTION_BYTES,
        )
        if not isinstance(payload, dict):
            _reject("trial_projection_unavailable")
        try:
            validate_contract("trial_snapshot.v1", payload)
        except (ContractError, TypeError, ValueError):
            _reject("trial_projection_unavailable")
        nct_id = payload.get("nct_id")
        if not isinstance(nct_id, str) or not _NCT_ID_RE.fullmatch(nct_id) or nct_id in seen:
            _reject("trial_projection_unavailable")
        seen.add(nct_id)
        source_ref = payload.get("source_record_ref")
        match = _SOURCE_REF_RE.fullmatch(source_ref) if isinstance(source_ref, str) else None
        if match is None or match.group(1) != nct_id:
            _reject("trial_projection_unavailable")
        if payload.get("contradiction_state") != "none_known":
            _reject("trial_projection_unavailable")
        normalized.append(payload)
    if sorted(f"trial:{payload['nct_id']}" for payload in normalized) != sorted(entity_refs):
        _reject("trial_projection_unavailable")
    return tuple(sorted(normalized, key=lambda item: item["nct_id"]))


def build_operating_packet(
    *,
    sector_packet: Mapping[str, Any],
    trial_projections: Sequence[Mapping[str, Any]],
    owner_projection_reads: Sequence[Mapping[str, Any]],
    evaluated_at: str,
    identity_resolutions: Sequence[Any] = (),
) -> dict[str, Any]:
    """Return one deterministic ``biocatalyst_operating_packet.v1`` document.

    The function performs no I/O, runs no model, and has no side effects: the
    same inputs always produce a byte-identical packet.
    """

    evaluated = _utc(evaluated_at, code="evaluated_at_unavailable")
    canonical_evaluated_at = _format_utc(evaluated)

    packet = _validate_sector_packet(sector_packet)
    generated = _utc(packet.get("generated_at"), code="sector_packet_unavailable")
    cutoff = _utc(packet.get("knowledge_cutoff"), code="sector_packet_unavailable")
    if not (cutoff <= generated <= evaluated):
        _reject("evaluated_at_unavailable")

    entity_refs = packet.get("entity_refs")
    if not isinstance(entity_refs, list) or not entity_refs:
        _reject("sector_packet_unavailable")
    projections = _trial_projections(trial_projections, entity_refs=entity_refs)

    if isinstance(owner_projection_reads, (str, bytes)) or not isinstance(
        owner_projection_reads, Sequence
    ):
        _reject("owner_projection_unavailable")
    if not owner_projection_reads or len(owner_projection_reads) > _MAX_OWNER_PROJECTION_READS:
        _reject("owner_projection_unavailable")
    reads: list[dict[str, Any]] = []
    aggregate_bytes = 0
    for read in owner_projection_reads:
        normalized = _owner_projection_read(read)
        aggregate_bytes += len(normalized.pop("_payload_bytes"))
        if aggregate_bytes > _MAX_AGGREGATE_READ_BYTES:
            _reject("owner_projection_unavailable")
        if _utc(normalized["as_of"], code="owner_projection_unavailable") > evaluated:
            _reject("evaluated_at_unavailable")
        reads.append(normalized)
    if len({read["read_id"] for read in reads}) != len(reads):
        _reject("owner_projection_unavailable")
    reads.sort(key=lambda row: (row["projection_id"], row["payload_sha256"]))

    known_entity_refs = frozenset(entity_refs)
    lane_reads = [
        {
            "read_id": read["read_id"],
            "contradictions": read.pop("_contradictions"),
            "corrections": read.pop("_corrections"),
        }
        for read in reads
    ]
    contradictions = _lane(
        lane_reads,
        key="contradictions",
        entity_refs=known_entity_refs,
        code="contradiction_reference_unavailable",
    )
    corrections = _lane(
        lane_reads,
        key="corrections",
        entity_refs=known_entity_refs,
        code="correction_reference_unavailable",
    )

    freshness = packet.get("freshness")
    if not isinstance(freshness, Mapping):
        _reject("sector_packet_unavailable")
    quality = packet.get("quality")
    if not isinstance(quality, Mapping):
        _reject("sector_packet_unavailable")
    completeness = quality.get("completeness")
    if isinstance(completeness, bool) or not isinstance(completeness, (int, float)):
        _reject("sector_packet_unavailable")

    caps = packet["authority_caps"]
    warnings = ["Current-only ClinicalTrials.gov facts; complete prior history is not implied."]
    if freshness.get("state") != "fresh":
        warnings.append("ClinicalTrials.gov source freshness is not confirmed.")
    if contradictions["state"] == "unavailable":
        warnings.append("No owner projection declared a contradiction lane; contradictions are unknown, not absent.")
    if corrections["state"] == "unavailable":
        warnings.append("No owner projection declared a correction lane; corrections are unknown, not absent.")
    warnings.append(
        "Identity is unavailable: issuer, security, ticker, and sponsor are never inferred from a registry record."
    )

    payload: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "schema_version": "1.0.0",
        "packet_version": 1,
        "sector": SECTOR,
        "producer": dict(_PRODUCER),
        "generated_at": canonical_evaluated_at,
        "knowledge_cutoff": _format_utc(cutoff),
        "sector_packet_ref": packet["packet_id"],
        "sector_packet_sha256": packet["packet_hash"],
        "entity_refs": sorted(entity_refs),
        "source_refs": sorted({str(item["source_record_ref"]) for item in projections}),
        "evidence_refs": sorted(set(packet.get("evidence_claim_refs") or [])),
        "owner_projection_reads": reads,
        "point_in_time_facts": _point_in_time_facts(projections),
        "freshness": {
            "state": freshness.get("state"),
            "oldest_required_source_at": freshness.get("oldest_required_source_at"),
            "evaluated_at": canonical_evaluated_at,
            "stale_source_ids": sorted(freshness.get("stale_source_ids") or []),
            "unknown_source_ids": sorted(freshness.get("unknown_source_ids") or []),
        },
        # ``completeness`` is carried verbatim from the compiled sector packet
        # (observed/configured at compile time).  A configured count is not
        # re-derived here: dividing back out of a float would invent a number
        # this producer never observed.
        "coverage": {
            "class": "current_only",
            "observed": len(projections),
            "completeness": completeness,
        },
        "contradictions": contradictions,
        "corrections": corrections,
        "identity_state": _identity_state(identity_resolutions),
        "forecast_references": _forecast_references(packet),
        "unavailable_families": [
            {"family": family, "availability": "unavailable", "blocker": blocker}
            for family, blocker in sorted(_DARK_FAMILY_BLOCKERS.items())
        ],
        "authority_caps": {
            "max_authority": caps["max_authority"],
            "allowed_actions": _ordered_actions(caps["allowed_actions"]),
            "forbidden_actions": sorted(set(caps["forbidden_actions"])),
            "llm_may_originate_signals": False,
            "authority_manifest_ref": _text(
                packet.get("authority_manifest_ref"),
                code="authority_cap_unavailable",
                maximum=256,
            ),
        },
        "warnings": warnings,
        "hash_scope": "canonical_payload_excluding_packet_hash",
    }
    payload["packet_id"] = "biocatalyst_operating_packet:" + canonical_json_sha256(
        {
            "sector": SECTOR,
            "sector_packet_ref": payload["sector_packet_ref"],
            "sector_packet_sha256": payload["sector_packet_sha256"],
            "owner_projection_read_ids": [read["read_id"] for read in reads],
            "generated_at": canonical_evaluated_at,
        }
    )[:24]
    payload["packet_hash"] = canonical_json_sha256(payload)
    try:
        packet_bytes = canonical_json_bytes(payload)
    except (ContractError, TypeError, ValueError):
        _reject("operating_packet_unavailable")
    if len(packet_bytes) > _MAX_PACKET_BYTES:
        _reject("packet_size_unavailable")
    try:
        validate_contract(CONTRACT_ID, payload)
    except (ContractError, TypeError, ValueError):
        _reject("operating_packet_unavailable")
    return json.loads(packet_bytes)


def operating_packet_bytes(packet: Mapping[str, Any]) -> bytes:
    """Return the canonical carrier bytes a reader may consume."""

    _, payload = _bounded_json(
        packet, code="operating_packet_unavailable", max_bytes=_MAX_PACKET_BYTES
    )
    return payload


__all__ = [
    "CONTRACT_ID",
    "FORBIDDEN_RAW_STORE_IDS",
    "IDENTITY_BLOCKER",
    "OWNER_PROJECTION_IDS",
    "OperatingPacketError",
    "build_operating_packet",
    "operating_packet_bytes",
]
