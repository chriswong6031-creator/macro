"""Exact IDV parent/child bridge into prime-award dossiers (display tier).

Wave 10 rail 1.  The IDV rail already publishes receipt-bound, source-native
``CONT_IDV_*`` parents and their ``CONT_AWD_*`` children.  What this module adds
is the *bridge*: which prime-award dossier rows are provably attached to one of
those collected vehicles, and — just as importantly — which are not, and why.

Three states are published, each honestly labelled:

``vehicle_membership``
    The prime dossier's own award record *is* the vehicle: its source-native
    generated award ID is a ``CONT_IDV_*`` that this collection selected and
    count-verified.  This is the only construction that may be called a seat on
    the vehicle, because the source award record itself carries it.
``task_order``
    The prime award is an exact child under a collected parent IDV, proven
    either by an enumerated relationship observation or by USAspending's own
    generated identity for that award naming the parent PIID/agency tuple.
``count_only``
    The source reports a verified child count for a collected vehicle but will
    not enumerate the children under the bounded collection policy, so no child
    award can be named.  Published so a reader sees the coverage instead of an
    unexplained absence.

Every join is an exact match on a source-native identifier.  No recipient name,
agency name, PIID alone, ticker, or similarity score participates.  A prime
award's parent tuple is read out of USAspending's own composite generated award
ID (``CONT_AWD_<piid>_<agency>_<parent piid>_<parent agency>``); any identity
that does not decompose exactly into that canonical form is abstained on, never
guessed at.

Zero is a reportable state.  When nothing bridges, the payload says so in plain
words and prints the omission population that explains it.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from collectors import usaspending_idv_graph as collector
from engine.government_revenue.dossiers import DOSSIER_CONTRACT
from engine.government_revenue.idv_dossiers import IDV_DOSSIER_CONTRACT


IDV_BRIDGE_CONTRACT = "government_idv_bridge.v1"
IDV_BRIDGE_SCHEMA_VERSION = "1.0.0"
IDV_BRIDGE_FILENAME = "idv_bridge.json"
IDV_BRIDGE_CONTENT_ID_PREFIX = "gribr1-"
MAX_BRIDGE_ROWS = 4_000

BRIDGE_STATES = ("count_only", "task_order", "vehicle_membership")
BRIDGE_BASES = (
    "enumerated_child_award",
    "prime_award_record_is_the_vehicle",
    "source_native_parent_tuple",
    "verified_child_count_without_enumeration",
)
OMISSION_CODES = (
    "enumerated_child_outside_prime_dossier",
    "exhausted_enumeration_omits_named_child",
    "prime_award_asserts_no_parent_vehicle",
    "prime_award_identity_not_decomposable",
    "prime_parent_tuple_outside_collection_universe",
    "prime_vehicle_outside_collection_universe",
)
#: Omissions where the bridge *declined* to assert a link it cannot prove.  A
#: source-asserted "this award has no parent vehicle" is a negative fact, not an
#: abstention, and is therefore deliberately excluded.
ABSTAINING_OMISSION_CODES = (
    "enumerated_child_outside_prime_dossier",
    "exhausted_enumeration_omits_named_child",
    "prime_award_identity_not_decomposable",
    "prime_parent_tuple_outside_collection_universe",
    "prime_vehicle_outside_collection_universe",
)

#: Sentinel components USAspending writes when an award has no parent award.
_NO_PARENT_TOKENS = frozenset({"", "-none-", "none", "null", "unknown"})
_GENERATED_IDV_PATTERN = re.compile(r"^CONT_IDV_[A-Za-z0-9_]+$")
_SEAT_LAW = (
    "A relationship is never called a vehicle seat without source proof: a seat is published only when the "
    "prime dossier's own award record is the vehicle itself."
)
_JOIN_LAW = (
    "Every link is an exact match on a source-native USAspending award identifier. No recipient name, agency "
    "name, ticker, or similarity score participates in this join."
)
_SEMANTIC_LAW = (
    "A bridge is relationship context only: it is not vehicle utilization, conversion, award value, revenue, "
    "backlog, public-company attribution, or investment authority."
)
_BOUNDED_LAW = (
    "Absence of a bridge is not evidence that no relationship exists; the collection universe is bounded."
)

#: Display-tier authority, identical in shape to the Government Revenue
#: candidate queue's block.  This rail adds no candidate family and changes no
#: candidate emission.
AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}

_OMISSION_REASONS = {
    "enumerated_child_outside_prime_dossier": (
        "The source listed these child awards under a collected vehicle, but this award cut does not carry them, "
        "so there is no dossier row to attach."
    ),
    "exhausted_enumeration_omits_named_child": (
        "These awards name a vehicle whose child list the source reported as complete without listing them, so "
        "the bridge refused the link and reports the disagreement."
    ),
    "prime_award_asserts_no_parent_vehicle": (
        "The source's own award identity names no parent vehicle for these awards, so there is nothing to link."
    ),
    "prime_award_identity_not_decomposable": (
        "These award identities do not decompose into the publisher's canonical parent form, so the bridge "
        "abstained rather than guessing a parent."
    ),
    "prime_parent_tuple_outside_collection_universe": (
        "These awards name a parent vehicle this bounded collection has not selected, so no vehicle evidence "
        "exists to link them to yet."
    ),
    "prime_vehicle_outside_collection_universe": (
        "These award records are vehicles this bounded collection has not selected, so no seat is published."
    ),
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def idv_bridge_content_id(payload: Mapping[str, Any]) -> str | None:
    """Return the immutable identity, excluding assembly clock and self-ID."""
    try:
        fingerprint = {key: value for key, value in payload.items() if key not in {"content_id", "generated_at"}}
        return IDV_BRIDGE_CONTENT_ID_PREFIX + _canonical_sha256(fingerprint)[:24]
    except (TypeError, ValueError):
        return None


def _text(value: Any, *, limit: int = 1_000) -> str | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    rendered = " ".join(str(value).split())
    return rendered[:limit] or None


def _instant(value: Any) -> str | None:
    """Normalize to a timezone-explicit ISO instant without inventing a clock."""
    raw = _text(value, limit=64)
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _date(value: Any) -> str | None:
    raw = _text(value, limit=32)
    if raw is None:
        return None
    return raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else None


def _bridge_key(state: str, parent: str, bridged: str, award_key: str | None, basis: str) -> str:
    return "idvbr:" + _canonical_sha256([state, parent, bridged, award_key, basis])[:32]


def source_native_parent_idv_id(generated_award_id: Any) -> str | None:
    """Read the parent vehicle out of USAspending's own composite award ID.

    ``generated_unique_award_id`` for a contract award is
    ``CONT_AWD_<piid>_<awarding agency>_<parent piid>_<parent agency>``, and the
    publisher writes ``-NONE-`` in the parent components when the award has no
    parent award.  Decomposing that string reads the source's own identity; it
    does not infer one.  Any value that is not exactly the canonical
    six-component form, or whose reconstructed parent is not a safe
    ``CONT_IDV_*`` identity, returns ``None`` so the caller abstains instead of
    guessing.
    """
    text = _text(generated_award_id, limit=1_000)
    if text is None or not collector._is_generated_definitive_award(text):
        return None
    parts = text.split("_")
    if len(parts) != 6:
        return None
    if any(part.strip().casefold() in _NO_PARENT_TOKENS for part in parts[2:]):
        return None
    candidate = f"CONT_IDV_{parts[4]}_{parts[5]}"
    if _GENERATED_IDV_PATTERN.fullmatch(candidate) is None:
        return None
    return candidate if collector._is_generated_idv(candidate) else None


def _asserts_no_parent_vehicle(generated_award_id: str) -> bool:
    """True when the publisher's identity explicitly carries no parent award."""
    parts = generated_award_id.split("_")
    return len(parts) == 6 and any(part.strip().casefold() in _NO_PARENT_TOKENS for part in parts[4:])


def _prime_identity_map(prime_payload: Mapping[str, Any]) -> dict[str, str]:
    """Index the prime dossier by its exact source-native generated award ID."""
    awards = prime_payload.get("awards")
    if not isinstance(awards, list):
        raise ValueError("prime dossier lacks an award list")
    mapping: dict[str, str] = {}
    for row in awards:
        if not isinstance(row, Mapping):
            raise ValueError("prime dossier award row is invalid")
        identity = row.get("identity")
        generated = identity.get("generated_award_id") if isinstance(identity, Mapping) else None
        if generated is None:
            continue
        source_id = _text(generated, limit=1_000)
        award_key = _text(row.get("award_key"), limit=1_000)
        if source_id is None or award_key is None:
            raise ValueError("prime dossier award identity is invalid")
        previous = mapping.get(source_id)
        if previous is not None and previous != award_key:
            raise ValueError("prime dossier generated award ID is ambiguous")
        mapping[source_id] = award_key
    return mapping


def _require_source_payloads(
    idv_payload: Mapping[str, Any],
    prime_payload: Mapping[str, Any],
) -> tuple[str, str]:
    """Accept only the two content-addressed rails this bridge is defined over."""
    if not isinstance(idv_payload, Mapping) or idv_payload.get("contract") != IDV_DOSSIER_CONTRACT:
        raise ValueError("IDV bridge requires the source-native IDV dossier contract")
    if not isinstance(prime_payload, Mapping) or prime_payload.get("contract") != DOSSIER_CONTRACT:
        raise ValueError("IDV bridge requires the prime award dossier contract")
    idv_content_id = _text(idv_payload.get("content_id"), limit=200)
    prime_content_id = _text(prime_payload.get("content_id"), limit=200)
    if idv_content_id is None or prime_content_id is None:
        raise ValueError("IDV bridge requires both source content identities")
    return idv_content_id, prime_content_id


def _parent_coverage(idv_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    coverage: dict[str, dict[str, Any]] = {}
    for envelope in idv_payload.get("idvs") or []:
        if not isinstance(envelope, Mapping):
            raise ValueError("IDV parent envelope is invalid")
        parent = _text(envelope.get("idv_generated_award_id"), limit=1_000)
        row = envelope.get("coverage")
        if parent is None or not collector._is_generated_idv(parent) or not isinstance(row, Mapping):
            raise ValueError("IDV parent envelope identity or coverage is invalid")
        if parent in coverage:
            raise ValueError("IDV parent envelope is duplicated")
        coverage[parent] = dict(row)
    return coverage


def _relationship_rows(idv_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in idv_payload.get("relationships") or []:
        if not isinstance(row, Mapping):
            raise ValueError("IDV relationship row is invalid")
        identity = row.get("identity")
        if not isinstance(identity, Mapping):
            raise ValueError("IDV relationship identity is invalid")
        parent = _text(identity.get("idv_generated_award_id"), limit=1_000)
        child = _text(identity.get("child_generated_award_id"), limit=1_000)
        if (
            parent is None
            or child is None
            or not collector._is_generated_idv(parent)
            or not collector._is_generated_definitive_award(child)
        ):
            raise ValueError("IDV relationship identity is not source-native")
        rows.append(dict(row))
    return rows


def _row_clocks(row: Mapping[str, Any], *, observed_at: str | None) -> dict[str, Any]:
    """Keep the four clocks separate: source fact, source capture, read, knowledge."""
    dates = row.get("dates") if isinstance(row.get("dates"), Mapping) else {}
    provenance = row.get("provenance") if isinstance(row.get("provenance"), Mapping) else {}
    known_at = _instant(dates.get("known_at"))
    if known_at is None:
        raise ValueError("IDV relationship lacks a knowledge clock")
    return {
        "source_effective_date": _date(dates.get("start_date")),
        "source_observed_at": _instant(provenance.get("known_at")) or known_at,
        "observed_at": observed_at,
        "known_at": known_at,
        "first_seen_at": _instant(dates.get("first_seen_at")) or known_at,
    }


def _vehicle_clocks(idv_payload: Mapping[str, Any], *, observed_at: str | None) -> dict[str, Any]:
    """Clocks for a vehicle-scoped reading, which carries no child action date."""
    known_at = _instant(idv_payload.get("known_at")) or observed_at
    if known_at is None:
        raise ValueError("IDV generation lacks a knowledge clock")
    return {
        "source_effective_date": None,
        "source_observed_at": observed_at or known_at,
        "observed_at": observed_at,
        "known_at": known_at,
        "first_seen_at": None,
    }


def _evidence(
    *,
    basis: str,
    coverage: Mapping[str, Any],
    relationship: Mapping[str, Any] | None,
    source_proof: str,
) -> dict[str, Any]:
    provenance = relationship.get("provenance") if isinstance(relationship, Mapping) else None
    provenance = provenance if isinstance(provenance, Mapping) else {}
    receipt_id = _text(provenance.get("receipt_id"), limit=400)
    response_sha = _text(provenance.get("response_sha256"), limit=64)
    if response_sha is not None:
        response_sha = response_sha.lower()
        if re.fullmatch(r"[a-f0-9]{64}", response_sha) is None:
            raise ValueError("IDV relationship response hash is invalid")
    reported = coverage.get("reported_count")
    return {
        "basis": basis,
        "relationship_key": _text(relationship.get("relationship_key"), limit=200) if relationship else None,
        "receipt_id": receipt_id,
        "response_sha256": response_sha,
        "parent_collection_state": _text(coverage.get("collection_state"), limit=80),
        "parent_count_verified": coverage.get("count_verified") is True,
        "parent_reported_child_count": reported if isinstance(reported, int) and not isinstance(reported, bool) else None,
        "parent_source_exhausted": coverage.get("source_exhausted") is True,
        "source_proof": source_proof,
    }


def _bridge_row(
    *,
    state: str,
    award_key: str | None,
    parent: str,
    bridged: str | None,
    depth: str | None,
    parent_piid: str | None,
    child_piid: str | None,
    evidence: Mapping[str, Any],
    clocks: Mapping[str, Any],
) -> dict[str, Any]:
    basis = str(evidence["basis"])
    return {
        "bridge_key": _bridge_key(state, parent, bridged or parent, award_key, basis),
        "state": state,
        "award_key": award_key,
        "identity": {
            "idv_generated_award_id": parent,
            "bridged_generated_award_id": bridged,
            "relationship_depth": depth,
            "parent_piid": parent_piid,
            "child_piid": child_piid,
        },
        "evidence": dict(evidence),
        "clocks": dict(clocks),
        "limitations": [_SEAT_LAW, _JOIN_LAW, _SEMANTIC_LAW],
    }


def _omission(code: str, count: int) -> dict[str, Any]:
    if code not in OMISSION_CODES:
        raise ValueError("IDV bridge omission code is not registered")
    return {"code": code, "count": int(count), "reason": _OMISSION_REASONS[code]}


def _last_good(previous: Mapping[str, Any] | None) -> dict[str, Any]:
    """Carry a previous complete reading forward without restating it as new."""
    none_state = {
        "status": "none",
        "content_id": None,
        "known_at": None,
        "counts": None,
        "reason": "No previous complete bridge reading was supplied, so there is nothing to keep.",
    }
    if previous is None:
        return none_state
    if not isinstance(previous, Mapping) or previous.get("contract") != IDV_BRIDGE_CONTRACT:
        raise ValueError("previous IDV bridge generation must use this contract")
    content_id = _text(previous.get("content_id"), limit=200)
    if content_id is None or idv_bridge_content_id(previous) != content_id:
        raise ValueError("previous IDV bridge generation identity is invalid")
    retained_reason = "The last complete bridge reading is kept so a source failure cannot erase it."
    if previous.get("status") == "observed":
        counts = previous.get("counts")
        clocks = previous.get("clocks")
        if not isinstance(counts, Mapping) or not isinstance(clocks, Mapping):
            raise ValueError("previous IDV bridge generation lacks counts or clocks")
        return {
            "status": "retained",
            "content_id": content_id,
            "known_at": _instant(clocks.get("known_at")),
            "counts": {key: int(counts[key]) for key in sorted(counts)},
            "reason": retained_reason,
        }
    # An unavailable predecessor forwards ITS retained reading, never its zeros.
    retained = previous.get("last_good")
    if not isinstance(retained, Mapping) or retained.get("status") != "retained":
        return none_state
    counts = retained.get("counts")
    return {
        "status": "retained",
        "content_id": _text(retained.get("content_id"), limit=200),
        "known_at": _instant(retained.get("known_at")),
        "counts": {key: int(counts[key]) for key in sorted(counts)} if isinstance(counts, Mapping) else None,
        "reason": retained_reason,
    }


def _baseline(previous: Mapping[str, Any] | None, *, known_at: str | None) -> dict[str, Any]:
    """A first baseline may not synthesize history it never observed."""
    if previous is None:
        return {
            "status": "first_baseline",
            "history_synthesized": False,
            "prior_content_id": None,
            "prior_known_at": None,
            "reason": (
                "This is the first bridge reading. No earlier bridge history is asserted or back-filled: the "
                "counts describe this one generation only."
            ),
        }
    prior_content_id = _text(previous.get("content_id"), limit=200)
    if prior_content_id is None:
        raise ValueError("previous IDV bridge generation lacks a content identity")
    clocks = previous.get("clocks") if isinstance(previous.get("clocks"), Mapping) else {}
    prior_known_at = _instant(clocks.get("known_at"))
    if prior_known_at is not None and known_at is not None and prior_known_at > known_at:
        raise ValueError("IDV bridge knowledge clock cannot regress behind its predecessor")
    return {
        "status": "continuing",
        "history_synthesized": False,
        "prior_content_id": prior_content_id,
        "prior_known_at": prior_known_at,
        "reason": (
            "This reading follows one named predecessor. Only the current generation was observed; no "
            "intermediate bridge history was reconstructed."
        ),
    }


def _selection_manifest_id(idv_payload: Mapping[str, Any]) -> str | None:
    selection = idv_payload.get("selection_provenance")
    selection = selection if isinstance(selection, Mapping) else {}
    return _text(selection.get("selection_manifest_id"), limit=200)


def _finalize(
    *,
    status: str,
    as_of: str,
    clocks: Mapping[str, Any],
    source_bindings: Mapping[str, Any],
    collection_universe: Mapping[str, Any],
    counts: Mapping[str, int],
    omissions: list[dict[str, Any]],
    bridges: list[dict[str, Any]],
    awards: list[dict[str, Any]],
    previous: Mapping[str, Any] | None,
    disclosure: str,
    reason: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract": IDV_BRIDGE_CONTRACT,
        "schema_version": IDV_BRIDGE_SCHEMA_VERSION,
        "content_id": "",
        "status": status,
        "as_of": as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": AUTHORITY.copy(),
        "clocks": dict(clocks),
        "baseline": _baseline(previous, known_at=_instant(clocks.get("known_at"))),
        "last_good": _last_good(previous),
        "source_bindings": dict(source_bindings),
        "join_policy": {
            "identity_bases": list(BRIDGE_BASES),
            "semantic_similarity_join": False,
            "name_join": False,
            "piid_only_join": False,
            "reason": _JOIN_LAW,
        },
        "collection_universe": dict(collection_universe),
        "counts": {key: int(counts[key]) for key in sorted(counts)},
        "omissions": omissions,
        "disclosure": disclosure,
        "limitations": [_SEAT_LAW, _JOIN_LAW, _SEMANTIC_LAW, _BOUNDED_LAW, reason],
        "bridges": bridges,
        "awards": awards,
    }
    content_id = idv_bridge_content_id(payload)
    if content_id is None:
        raise ValueError("IDV bridge cannot be canonically represented")
    payload["content_id"] = content_id
    if not is_valid_idv_bridge_payload(payload):
        raise ValueError("IDV bridge failed strict public validation")
    return payload


def _unavailable_payload(
    *,
    as_of: str,
    idv_payload: Mapping[str, Any],
    prime_payload: Mapping[str, Any],
    idv_content_id: str,
    prime_content_id: str,
    previous: Mapping[str, Any] | None,
    reason: str,
) -> dict[str, Any]:
    """Publish an explicit no-reading generation, preserving last-good evidence."""
    freshness = idv_payload.get("freshness") if isinstance(idv_payload.get("freshness"), Mapping) else {}
    source_coverage = (
        idv_payload.get("source_coverage") if isinstance(idv_payload.get("source_coverage"), Mapping) else {}
    )
    return _finalize(
        status="unavailable",
        as_of=as_of,
        clocks={
            "source_effective_at": None,
            "source_observed_at": _instant(freshness.get("observed_at")),
            "observed_at": _instant(freshness.get("observed_at")),
            "known_at": _instant(idv_payload.get("known_at")),
        },
        source_bindings={
            "idv_content_id": idv_content_id,
            "idv_source_status": _text(source_coverage.get("status"), limit=40) or "unavailable",
            "idv_freshness_status": _text(freshness.get("status"), limit=40) or "unavailable",
            "idv_selection_manifest_id": _selection_manifest_id(idv_payload),
            "prime_content_id": prime_content_id,
            "prime_as_of": _date(prime_payload.get("as_of")),
        },
        collection_universe={
            "status": "unavailable",
            "selected_parent_count": 0,
            "selected_parent_ids": [],
            "enumerable_parent_count": 0,
            "count_only_parent_count": 0,
            "zero_child_parent_count": 0,
            "enumerated_child_count": 0,
            "prime_award_count": 0,
            "prime_awards_naming_a_parent_vehicle": 0,
            "prime_awards_asserting_no_parent_vehicle": 0,
            "reason": reason,
        },
        counts={
            "count_only": 0,
            "task_order": 0,
            "vehicle_membership": 0,
            "bridged": 0,
            "bridged_award_count": 0,
            "abstained": 0,
        },
        omissions=[],
        bridges=[],
        awards=[],
        previous=previous,
        disclosure=(
            "The vehicle relationship source is unavailable in this generation, so no link was checked. The "
            "zeros here are not an observation of zero; the last complete reading is kept as last-good."
        ),
        reason=reason,
    )


def build_idv_bridge_payload(
    *,
    idv_payload: Mapping[str, Any],
    prime_payload: Mapping[str, Any],
    as_of: str | None = None,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one deterministic bridge generation from two published rails.

    Both inputs are already content-addressed and contract-validated by their own
    projectors; this function performs no IO and never mutates them.  A source
    generation that is not publication eligible produces an explicit unavailable
    reading that preserves ``previous`` as last-good evidence rather than
    publishing zeros as an observation.
    """
    idv_content_id, prime_content_id = _require_source_payloads(idv_payload, prime_payload)
    freshness = idv_payload.get("freshness") if isinstance(idv_payload.get("freshness"), Mapping) else {}
    source_coverage = (
        idv_payload.get("source_coverage") if isinstance(idv_payload.get("source_coverage"), Mapping) else {}
    )
    selection = (
        idv_payload.get("selection_provenance")
        if isinstance(idv_payload.get("selection_provenance"), Mapping)
        else {}
    )
    resolved_as_of = _date(as_of) or _date(prime_payload.get("as_of")) or _date(idv_payload.get("as_of"))
    if resolved_as_of is None:
        raise ValueError("IDV bridge requires a resolvable as_of date")
    if source_coverage.get("status") != "ok" or selection.get("status") != "verified":
        return _unavailable_payload(
            as_of=resolved_as_of,
            idv_payload=idv_payload,
            prime_payload=prime_payload,
            idv_content_id=idv_content_id,
            prime_content_id=prime_content_id,
            previous=previous,
            reason="No publication-eligible bounded IDV generation is active, so no bridge was checked.",
        )

    prime_by_generated = _prime_identity_map(prime_payload)
    coverage = _parent_coverage(idv_payload)
    relationships = _relationship_rows(idv_payload)
    observed_at = _instant(freshness.get("observed_at"))
    bridges: list[dict[str, Any]] = []
    omission_counts = dict.fromkeys(OMISSION_CODES, 0)

    # (a) Vehicle membership — the prime award record IS the collected vehicle.
    for parent in sorted(coverage):
        award_key = prime_by_generated.get(parent)
        if award_key is None:
            continue
        bridges.append(_bridge_row(
            state="vehicle_membership",
            award_key=award_key,
            parent=parent,
            bridged=parent,
            depth=None,
            parent_piid=None,
            child_piid=None,
            evidence=_evidence(
                basis="prime_award_record_is_the_vehicle",
                coverage=coverage[parent],
                relationship=None,
                source_proof=(
                    "USAspending publishes this award record under the vehicle's own generated award ID, and "
                    "this vehicle's child count was independently receipt-verified."
                ),
            ),
            clocks=_vehicle_clocks(idv_payload, observed_at=observed_at),
        ))

    # (b) Task orders — an enumerated child award the prime dossier also carries.
    enumerated: set[tuple[str, str]] = set()
    for row in relationships:
        identity = row["identity"]
        parent = str(identity["idv_generated_award_id"])
        child = str(identity["child_generated_award_id"])
        parent_row = coverage.get(parent)
        if parent_row is None:
            raise ValueError("IDV relationship names a parent outside its own coverage envelope")
        enumerated.add((parent, child))
        award_key = prime_by_generated.get(child)
        if award_key is None:
            omission_counts["enumerated_child_outside_prime_dossier"] += 1
            continue
        bridges.append(_bridge_row(
            state="task_order",
            award_key=award_key,
            parent=parent,
            bridged=child,
            depth=_text(identity.get("relationship_depth"), limit=40),
            parent_piid=_text(identity.get("parent_piid"), limit=2_000),
            child_piid=_text(identity.get("child_piid"), limit=2_000),
            evidence=_evidence(
                basis="enumerated_child_award",
                coverage=parent_row,
                relationship=row,
                source_proof=(
                    "The official IDV activity response for this vehicle enumerated this exact child award ID, "
                    "bound to a stored collection receipt."
                ),
            ),
            clocks=_row_clocks(row, observed_at=observed_at),
        ))

    # Universe facts, counted over the whole award cut and independent of any
    # bridge attempt: how many awards the publisher's own identity says have a
    # parent vehicle, and how many it says have none.
    naming_parent_count = 0
    no_parent_count = 0
    for source_id in prime_by_generated:
        if source_native_parent_idv_id(source_id) is not None:
            naming_parent_count += 1
        elif collector._is_generated_definitive_award(source_id) and _asserts_no_parent_vehicle(source_id):
            no_parent_count += 1
    omission_counts["prime_award_asserts_no_parent_vehicle"] = no_parent_count

    # (b, second basis) Task orders proven by the award's own composite identity.
    enumerated_children = {child for _, child in enumerated}
    published_pairs = {(row["identity"]["idv_generated_award_id"], row["award_key"]) for row in bridges}
    for source_id, award_key in sorted(prime_by_generated.items()):
        if collector._is_generated_idv(source_id):
            if source_id not in coverage:
                omission_counts["prime_vehicle_outside_collection_universe"] += 1
            continue
        if source_id in enumerated_children:
            # The source's own enumeration already settled this award's parent;
            # its composite identity adds nothing and cannot contradict it.
            continue
        parent = source_native_parent_idv_id(source_id)
        if parent is None:
            if not _asserts_no_parent_vehicle(source_id):
                omission_counts["prime_award_identity_not_decomposable"] += 1
            continue
        parent_row = coverage.get(parent)
        if parent_row is None:
            omission_counts["prime_parent_tuple_outside_collection_universe"] += 1
            continue
        if (parent, source_id) in enumerated:
            continue  # already published on the stronger enumerated basis
        if parent_row.get("source_exhausted") is True:
            # The source exhausted this vehicle's children and did not list this
            # award. Refuse the link and report the disagreement instead.
            omission_counts["exhausted_enumeration_omits_named_child"] += 1
            continue
        if (parent, award_key) in published_pairs:
            continue
        published_pairs.add((parent, award_key))
        bridges.append(_bridge_row(
            state="task_order",
            award_key=award_key,
            parent=parent,
            bridged=source_id,
            depth=None,
            parent_piid=None,
            child_piid=None,
            evidence=_evidence(
                basis="source_native_parent_tuple",
                coverage=parent_row,
                relationship=None,
                source_proof=(
                    "USAspending's own generated award ID for this award names this vehicle's PIID and agency as "
                    "its parent award, and this vehicle's child count was receipt-verified."
                ),
            ),
            clocks=_vehicle_clocks(idv_payload, observed_at=observed_at),
        ))

    # (c) Count-only coverage — a verified count the source will not enumerate.
    count_only_parents = sorted(
        parent for parent, row in coverage.items() if row.get("truncated_by_collection_policy") is True
    )
    for parent in count_only_parents:
        bridges.append(_bridge_row(
            state="count_only",
            award_key=None,
            parent=parent,
            bridged=None,
            depth=None,
            parent_piid=None,
            child_piid=None,
            evidence=_evidence(
                basis="verified_child_count_without_enumeration",
                coverage=coverage[parent],
                relationship=None,
                source_proof=(
                    "The source reported and receipt-verified this vehicle's child count, but the bounded "
                    "collection policy withheld the child rows, so no child award can be named."
                ),
            ),
            clocks=_vehicle_clocks(idv_payload, observed_at=observed_at),
        ))

    if len(bridges) > MAX_BRIDGE_ROWS:
        raise ValueError("IDV bridge exceeds the public artifact cap")
    bridges.sort(key=lambda row: (row["state"], row["identity"]["idv_generated_award_id"], row["bridge_key"]))

    grouped: dict[str, list[str]] = {}
    states_by_award: dict[str, set[str]] = {}
    for row in bridges:
        award_key = row["award_key"]
        if award_key is None:
            continue
        grouped.setdefault(award_key, []).append(row["bridge_key"])
        states_by_award.setdefault(award_key, set()).add(row["state"])
    award_list = [
        {
            "award_key": award_key,
            "bridge_keys": sorted(grouped[award_key]),
            "bridge_count": len(grouped[award_key]),
            "states": sorted(states_by_award[award_key]),
        }
        for award_key in sorted(grouped)
    ]

    state_counts = {state: sum(1 for row in bridges if row["state"] == state) for state in BRIDGE_STATES}
    counts = {
        **state_counts,
        "bridged": state_counts["vehicle_membership"] + state_counts["task_order"],
        "bridged_award_count": len(award_list),
        "abstained": sum(omission_counts[code] for code in ABSTAINING_OMISSION_CODES),
    }
    omissions = [_omission(code, omission_counts[code]) for code in OMISSION_CODES if omission_counts[code]]
    effective_dates = [
        row["clocks"]["source_effective_date"] for row in bridges if row["clocks"].get("source_effective_date")
    ]
    enumerable = sum(1 for row in coverage.values() if row.get("collection_state") == "complete")
    zero_children = sum(1 for row in coverage.values() if row.get("collection_state") == "zero")
    universe_reason = (
        f"{len(coverage)} vehicles were selected and count-verified in this bounded generation: {enumerable} "
        f"with enumerable children, {len(count_only_parents)} count-only, {zero_children} reporting none."
    )
    return _finalize(
        status="observed",
        as_of=resolved_as_of,
        clocks={
            "source_effective_at": max(effective_dates) if effective_dates else None,
            "source_observed_at": observed_at,
            "observed_at": observed_at,
            "known_at": _instant(idv_payload.get("known_at")) or observed_at,
        },
        source_bindings={
            "idv_content_id": idv_content_id,
            "idv_source_status": _text(source_coverage.get("status"), limit=40),
            "idv_freshness_status": _text(freshness.get("status"), limit=40),
            "idv_selection_manifest_id": _selection_manifest_id(idv_payload),
            "prime_content_id": prime_content_id,
            "prime_as_of": _date(prime_payload.get("as_of")),
        },
        collection_universe={
            "status": "verified",
            "selected_parent_count": len(coverage),
            "selected_parent_ids": sorted(coverage),
            "enumerable_parent_count": enumerable,
            "count_only_parent_count": len(count_only_parents),
            "zero_child_parent_count": zero_children,
            "enumerated_child_count": len(relationships),
            "prime_award_count": len(prime_by_generated),
            "prime_awards_naming_a_parent_vehicle": naming_parent_count,
            "prime_awards_asserting_no_parent_vehicle": no_parent_count,
            "reason": universe_reason,
        },
        counts=counts,
        omissions=omissions,
        bridges=bridges,
        awards=award_list,
        previous=previous,
        disclosure=_disclosure(
            counts=counts,
            selected_parent_count=len(coverage),
            prime_count=len(prime_by_generated),
            omission_counts=omission_counts,
        ),
        reason=universe_reason,
    )


def _disclosure(
    *,
    counts: Mapping[str, int],
    selected_parent_count: int,
    prime_count: int,
    omission_counts: Mapping[str, int],
) -> str:
    """State the reading in plain words, including an honest zero."""
    if counts["bridged"] or counts["count_only"]:
        parts: list[str] = []
        if counts["bridged"]:
            parts.append(
                f"{counts['bridged_award_count']} awards in this cut are linked to a collected vehicle by exact "
                f"source identity: {counts['vehicle_membership']} hold the vehicle itself and "
                f"{counts['task_order']} sit under one as task orders."
            )
        if counts["count_only"]:
            parts.append(
                f"{counts['count_only']} vehicles report child counts the source will not list, so their orders "
                "cannot be named here."
            )
        return " ".join(parts)
    return (
        f"No award in this {prime_count}-award cut links to any of the {selected_parent_count} collected vehicles "
        "by exact source identity. That is a reported zero, not a hidden gap: "
        f"{omission_counts['enumerated_child_outside_prime_dossier']} listed child awards sit outside this award "
        f"cut and {omission_counts['prime_parent_tuple_outside_collection_universe']} awards name a vehicle this "
        "collection has not selected."
    )


def unavailable_award_bridge_view(award_key: str, reason: str) -> dict[str, Any]:
    """State plainly that the derived bridge view could not be built.

    The receipt-bound relationship rail keeps serving when this display-tier
    join cannot be projected; a silent omission would read as "no link", which
    is a different claim from "not checked".
    """
    return {
        "status": "unavailable",
        "content_id": None,
        "as_of": None,
        "clocks": None,
        "authority": AUTHORITY.copy(),
        "baseline": None,
        "last_good": None,
        "join_policy": None,
        "collection_universe": None,
        "counts": None,
        "omissions": None,
        "disclosure": reason,
        "limitations": [_SEAT_LAW, _JOIN_LAW, _SEMANTIC_LAW, _BOUNDED_LAW],
        "award_key": award_key,
        "bridges": [],
        "total": 0,
    }


def award_bridge_view(payload: Mapping[str, Any], award_key: str) -> dict[str, Any]:
    """Return one award's bridge state, keeping zero an explicit reported state.

    The published universe is projected as counts plus the selection receipt.
    The raw selection-manifest parent list stays out of the request contract by
    Wave 8's design; each published link still names its own vehicle ID.
    """
    if not isinstance(payload, Mapping) or payload.get("contract") != IDV_BRIDGE_CONTRACT:
        raise ValueError("award bridge view requires the IDV bridge contract")
    rows = [
        row for row in payload.get("bridges") or [] if isinstance(row, Mapping) and row.get("award_key") == award_key
    ]
    rows.sort(key=lambda row: str(row.get("bridge_key") or ""))
    stored = payload.get("collection_universe") if isinstance(payload.get("collection_universe"), Mapping) else {}
    universe = {key: item for key, item in stored.items() if key != "selected_parent_ids"}
    if payload.get("status") != "observed":
        status = "unavailable"
        disclosure = payload.get("disclosure")
    elif rows:
        vehicles = len({row["identity"]["idv_generated_award_id"] for row in rows})
        status = "bridged"
        disclosure = (
            f"This award is linked to {vehicles} collected vehicle(s) by exact source identity; every link names "
            "the source record that proves it."
        )
    else:
        status = "no_exact_link"
        disclosure = (
            f"No exact source-native link was found between this award and the "
            f"{universe.get('selected_parent_count', 0)} collected vehicles. That is a reported zero, not "
            "evidence that no vehicle relationship exists."
        )
    return {
        "status": status,
        "content_id": payload.get("content_id"),
        "as_of": payload.get("as_of"),
        "clocks": payload.get("clocks"),
        "authority": payload.get("authority"),
        "baseline": payload.get("baseline"),
        "last_good": payload.get("last_good"),
        "join_policy": payload.get("join_policy"),
        "collection_universe": universe,
        "counts": payload.get("counts"),
        "omissions": payload.get("omissions"),
        "disclosure": disclosure,
        "limitations": payload.get("limitations"),
        "award_key": award_key,
        "bridges": rows,
        "total": len(rows),
    }


@lru_cache(maxsize=1)
def _validator() -> Any:
    from jsonschema import Draft202012Validator, FormatChecker

    path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "government_revenue"
        / "government_idv_bridge.v1.schema.json"
    )
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")), format_checker=FormatChecker())


def is_valid_idv_bridge_payload(value: Any) -> bool:
    """Validate schema, immutable identity, state pairing, and honest zeros."""
    try:
        if not isinstance(value, dict) or any(_validator().iter_errors(value)):
            return False
        if idv_bridge_content_id(value) != value.get("content_id"):
            return False
        bridges, awards, counts = value["bridges"], value["awards"], value["counts"]
        universe, baseline, last_good = value["collection_universe"], value["baseline"], value["last_good"]
        if baseline["history_synthesized"] is not False:
            return False
        if (baseline["status"] == "first_baseline") != (baseline["prior_content_id"] is None):
            return False
        if len({row["bridge_key"] for row in bridges}) != len(bridges):
            return False
        selected = universe["selected_parent_ids"]
        expected: dict[str, list[str]] = {}
        for row in bridges:
            state, award_key, identity = row["state"], row["award_key"], row["identity"]
            parent = identity["idv_generated_award_id"]
            bridged = identity["bridged_generated_award_id"]
            evidence = row["evidence"]
            basis = evidence["basis"]
            if row["bridge_key"] != _bridge_key(state, parent, bridged or parent, award_key, basis):
                return False
            if parent not in selected:
                return False
            if state == "count_only":
                # A count-only reading names no award and no child: publishing
                # the coverage without a child is exactly its purpose.
                if (
                    award_key is not None
                    or bridged is not None
                    or basis != "verified_child_count_without_enumeration"
                    or evidence["parent_count_verified"] is not True
                    or evidence["parent_source_exhausted"] is not False
                    or not isinstance(evidence["parent_reported_child_count"], int)
                ):
                    return False
                continue
            if award_key is None or bridged is None:
                return False
            if state == "vehicle_membership" and (bridged != parent or basis != "prime_award_record_is_the_vehicle"):
                return False
            if state == "task_order" and (
                bridged == parent
                or not bridged.startswith("CONT_AWD_")
                or basis not in {"enumerated_child_award", "source_native_parent_tuple"}
            ):
                return False
            if basis == "enumerated_child_award" and (
                evidence["receipt_id"] is None or evidence["response_sha256"] is None
            ):
                return False
            if basis == "source_native_parent_tuple" and source_native_parent_idv_id(bridged) != parent:
                return False
            expected.setdefault(award_key, []).append(row["bridge_key"])
        by_award = {envelope["award_key"]: envelope for envelope in awards}
        if len(by_award) != len(awards) or set(by_award) != set(expected):
            return False
        for award_key, envelope in by_award.items():
            if envelope["bridge_keys"] != sorted(expected[award_key]) or envelope["bridge_count"] != len(
                expected[award_key]
            ):
                return False
        states = {state: sum(1 for row in bridges if row["state"] == state) for state in BRIDGE_STATES}
        omissions = value["omissions"]
        codes = [item["code"] for item in omissions]
        by_code = {item["code"]: item["count"] for item in omissions}
        if by_code.get("prime_award_asserts_no_parent_vehicle", 0) != universe[
            "prime_awards_asserting_no_parent_vehicle"
        ]:
            return False
        if (
            any(counts.get(state) != states[state] for state in BRIDGE_STATES)
            or counts.get("bridged") != states["vehicle_membership"] + states["task_order"]
            or counts.get("bridged_award_count") != len(awards)
            or counts.get("abstained")
            != sum(item["count"] for item in omissions if item["code"] in ABSTAINING_OMISSION_CODES)
            or len(set(codes)) != len(codes)
            or any(item["count"] < 1 for item in omissions)
        ):
            return False
        if value["status"] == "unavailable":
            # Zeros in a no-reading generation must never read as an observation.
            return bool(
                not bridges
                and not awards
                and all(int(count) == 0 for count in counts.values())
                and universe["status"] == "unavailable"
                and last_good["status"] in {"retained", "none"}
                and "not an observation of zero" in value["disclosure"]
            )
        return bool(
            universe["status"] == "verified"
            and universe["selected_parent_count"] == len(selected)
            and len(set(selected)) == len(selected)
            and (counts["bridged"] or counts["count_only"] or "reported zero" in value["disclosure"])
        )
    except Exception:  # noqa: BLE001 - public validation must fail closed
        return False
