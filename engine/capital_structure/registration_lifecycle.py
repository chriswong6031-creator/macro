"""Deterministic point-in-time SEC registration lifecycle truth plane.

This compiler sits above the immutable ``capital_structure.event.v1`` and
``capital_structure.event_edge.v1`` ledgers.  It answers one deliberately
narrow question: which filed, amended, effective, or withdrawn registration
state had Mastermind *observed* by a given system-clock cutoff?

Grouping is fail-closed.  A lifecycle exists only when every admitted node can
be bound to one issuer ID, one explicit SEC file number, and one registration
family.  Family-less EFFECT, withdrawal, and post-effective amendment forms
inherit a family only through a unique immutable lifecycle edge.  Missing or
ambiguous linkage is emitted to a deterministic defer ledger; it is never
repaired with ticker, filing-date, name, or nearest-neighbour guesses.

An observed EFFECT transition is not an assertion that an offering is active
or executable.  This module contains no primary/resale classification,
offering terms, pricing, remaining dollars, instruments, risk, financing
probability, trading decision, or Prophet authority.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from engine.capital_structure.event_spine import normalize_form, route_form


BUNDLE_SCHEMA = "capital_structure.registration_lifecycle_bundle.v1"
RECORD_SCHEMA = "capital_structure.registration_lifecycle.v1"
DEFER_SCHEMA = "capital_structure.registration_lifecycle_defer.v1"
COMPILER_VERSION = "capital-structure-registration-lifecycle/1.0.0"

REGISTRATION_FAMILIES = frozenset(
    {
        "registration_s1",
        "registration_f1",
        "registration_s3",
        "registration_f3",
        "registration_f10",
        "registration_reg_a",
    }
)
LIFECYCLE_RELATIONSHIPS = frozenset(
    {"amendment_of", "effectuates", "withdraws"}
)
ALL_EDGE_RELATIONSHIPS = frozenset({*LIFECYCLE_RELATIONSHIPS, "supersedes"})
REGISTRATION_PARENT_FORMS = frozenset(
    {
        "S-1",
        "S-1/A",
        "F-1",
        "F-1/A",
        "S-3",
        "S-3/A",
        "S-3ASR",
        "F-3",
        "F-3/A",
        "F-3ASR",
        "F-10",
        "F-10/A",
        "1-A",
        "1-A/A",
        "1-A POS",
        "POS AM",
        "POSASR",
    }
)

AUTHORITY = {
    "is_context_only": True,
    "rank_authority": False,
    "sizing_authority": False,
    "entry_authority": False,
    "prophet_authority": False,
}

UNAVAILABLE = [
    "active_or_executable_offering_capacity",
    "financing_probability",
    "instrument_terms",
    "offering_pricing",
    "primary_or_resale_classification",
    "remaining_offering_dollars",
    "risk_assessment",
]

SCOPE = {
    "fact_type": "observed_sec_registration_lifecycle",
    "grouping_rule": (
        "issuer_id_plus_provenance_trusted_explicit_sec_file_number_plus_"
        "registration_family"
    ),
    "does_not_establish": [
        *UNAVAILABLE,
        "trade_decision",
    ],
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _hash_rows(rows: Sequence[Mapping[str, Any]], id_field: str) -> str:
    ordered = sorted(
        (deepcopy(dict(row)) for row in rows),
        key=lambda row: str(row.get(id_field) or ""),
    )
    return hashlib.sha256(_canonical_json(ordered)).hexdigest()


def _stable_id(prefix: str, body: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]


def _parse_time(value: Any, field: str, *, nullable: bool = False) -> datetime | None:
    if value is None or str(value).strip() == "":
        if nullable:
            return None
        raise ValueError(f"{field} is required")
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(
            raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        )
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: Any, field: str, *, nullable: bool = False) -> str | None:
    parsed = _parse_time(value, field, nullable=nullable)
    if parsed is None:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _dedupe_rows(
    rows: Sequence[Mapping[str, Any]], *, id_field: str, kind: str
) -> list[dict[str, Any]]:
    by_id: dict[str, bytes] = {}
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ValueError(f"{kind} row {index} must be an object")
        row = deepcopy(dict(raw))
        row_id = str(row.get(id_field) or "").strip()
        if not row_id:
            raise ValueError(f"every {kind} row requires {id_field}")
        encoded = _canonical_json(row)
        prior = by_id.get(row_id)
        if prior is not None:
            if prior != encoded:
                raise ValueError(f"immutable {kind} collision for {row_id}")
            continue
        by_id[row_id] = encoded
        output.append(row)
    return output


def _validate_immutable_identity(
    row: Mapping[str, Any], *, id_field: str, prefix: str, kind: str
) -> None:
    body = deepcopy(dict(row))
    observed = str(body.pop(id_field, ""))
    expected = prefix + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]
    if observed != expected:
        raise ValueError(
            f"{kind} immutable identity digest mismatch: {observed!r} != {expected!r}"
        )


def _logical_key(event: Mapping[str, Any]) -> tuple[str, str]:
    source = event.get("source") or {}
    filing = event.get("filing") or {}
    source_system = str(source.get("source_system") or "").strip()
    source_id = str(filing.get("accession") or source.get("source_id") or "").strip()
    if not source_system or not source_id:
        raise ValueError(
            f"event {event.get('event_id')} lacks a stable logical source key"
        )
    return source_system, source_id


def _registration_key(
    event: Mapping[str, Any], family: str | None
) -> tuple[str, str, str] | None:
    issuer_id = str((event.get("issuer") or {}).get("issuer_id") or "").strip()
    file_number = str((event.get("filing") or {}).get("file_number") or "").strip()
    if not issuer_id or not file_number or family not in REGISTRATION_FAMILIES:
        return None
    assert family is not None
    return issuer_id, file_number, family


def _trusted_file_number_provenance(
    event: Mapping[str, Any], file_number: str
) -> dict[str, Any] | None:
    provenance = (event.get("filing") or {}).get("file_number_provenance")
    if not isinstance(provenance, Mapping):
        return None
    value = provenance.get("value")
    candidates = provenance.get("candidate_values")
    sources = provenance.get("sources")
    if (
        set(provenance) != {"state", "value", "candidate_values", "sources"}
        or provenance.get("state") != "observed"
        or not isinstance(value, str)
        or value != file_number
        or not isinstance(candidates, list)
        or candidates != [value]
        or not isinstance(sources, list)
        or not sources
        or any(
            not isinstance(source, str)
            or source
            not in {
                "legacy_sgml_file_number",
                "sec_header_file_number",
                "effect_xml_file_number",
            }
            for source in sources
        )
        or len(sources) != len(set(sources))
    ):
        return None
    return {
        "state": "observed",
        "value": value,
        "candidate_values": [value],
        "sources": sorted({str(source) for source in sources}),
    }


def _key_object(
    key: tuple[str, str, str] | None = None,
    *,
    event: Mapping[str, Any] | None = None,
    family: str | None = None,
) -> dict[str, str | None]:
    if key is not None:
        return {
            "issuer_id": key[0],
            "file_number": key[1],
            "registration_family": key[2],
        }
    issuer_id = None
    file_number = None
    if event is not None:
        issuer_id = str(
            (event.get("issuer") or {}).get("issuer_id") or ""
        ).strip() or None
        file_number = str(
            (event.get("filing") or {}).get("file_number") or ""
        ).strip() or None
    return {
        "issuer_id": issuer_id,
        "file_number": file_number,
        "registration_family": (
            family if family in REGISTRATION_FAMILIES else None
        ),
    }


def _is_lifecycle_candidate(event: Mapping[str, Any]) -> bool:
    route = route_form((event.get("filing") or {}).get("form"))
    return route.registration_family in REGISTRATION_FAMILIES or (
        route.relationship in LIFECYCLE_RELATIONSHIPS
    )


def _is_registration_parent(event: Mapping[str, Any]) -> bool:
    return normalize_form((event.get("filing") or {}).get("form")) in (
        REGISTRATION_PARENT_FORMS
    )


def _source_receipt(
    visible_events: Sequence[Mapping[str, Any]],
    visible_edges: Sequence[Mapping[str, Any]],
    *,
    source_generation: Mapping[str, Any],
) -> dict[str, Any]:
    status = str(source_generation.get("status") or "unbound")
    verification_state = {
        "ok": "verified_telemetry_last_generation",
        "unbound": "unbound_engine_input",
    }.get(status, "upstream_unavailable")
    body = {
        # Full-generation IDs/hashes are intentionally excluded. They change
        # when a later generation appends future rows and would make an older
        # point-in-time receipt unstable. The disk writer still verifies that
        # generation before calling this pure compiler; this receipt binds the
        # exact visible prefix only.
        "verification_state": verification_state,
        "upstream_status": status,
        "visible_event_version_count": len(visible_events),
        "visible_edge_count": len(visible_edges),
        "visible_event_ids": sorted(
            str(event["event_id"]) for event in visible_events
        ),
        "visible_edge_ids": sorted(str(edge["edge_id"]) for edge in visible_edges),
        "event_set_sha256": _hash_rows(visible_events, "event_id"),
        "edge_set_sha256": _hash_rows(visible_edges, "edge_id"),
    }
    return {
        "receipt_id": _stable_id(
            "receipt:registration-lifecycle:cs:", body
        ),
        **body,
    }


def _derivation_receipt(
    event_ids: set[str],
    edge_ids: set[str],
    *,
    events_by_id: Mapping[str, Mapping[str, Any]],
    edges_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    sorted_event_ids = sorted(event_ids)
    sorted_edge_ids = sorted(edge_ids)
    event_rows = [events_by_id[event_id] for event_id in sorted_event_ids]
    edge_rows = [edges_by_id[edge_id] for edge_id in sorted_edge_ids]
    manifest_ids = sorted(
        {
            str(manifest_id)
            for event in event_rows
            for manifest_id in ((event.get("source") or {}).get("manifest_ids") or [])
            if manifest_id
        }
    )
    body = {
        "event_ids": sorted_event_ids,
        "edge_ids": sorted_edge_ids,
        "manifest_ids": manifest_ids,
        "event_set_sha256": _hash_rows(event_rows, "event_id"),
        "edge_set_sha256": _hash_rows(edge_rows, "edge_id"),
    }
    return {
        "receipt_id": _stable_id("receipt:lifecycle:cs:", body),
        **body,
    }


def compile_registration_lifecycles(
    events: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    as_of: str | datetime,
    generated_at: str | datetime,
    *,
    source_generation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile one deterministic system-clock registration lifecycle bundle.

    Input rows may be supplied in any order. Identical replay rows are
    idempotent; an ID collision with different immutable bytes is a hard
    integrity failure. Semantic uncertainty is kept in ``deferred`` and does
    not enter a lifecycle timeline.
    """

    as_of_iso = _iso(as_of, "as_of")
    generated_iso = _iso(generated_at, "generated_at")
    assert as_of_iso is not None and generated_iso is not None
    cutoff = _parse_time(as_of_iso, "as_of")
    produced = _parse_time(generated_iso, "generated_at")
    assert cutoff is not None and produced is not None
    if produced < cutoff:
        raise ValueError("generated_at cannot precede as_of")

    source = deepcopy(dict(source_generation or {}))
    source.setdefault("generation_id", None)
    source.setdefault("as_of", None)
    source.setdefault("status", "unbound")
    source.setdefault("artifact_hashes", {})
    status = str(source.get("status") or "unbound")
    if status not in {"ok", "unbound", "missing", "degraded", "no_source_manifest"}:
        raise ValueError(f"unsupported upstream generation status: {status!r}")
    upstream_as_of = _iso(
        source.get("as_of"), "source_generation.as_of", nullable=True
    )
    source["as_of"] = upstream_as_of
    if status == "ok":
        generation_id = str(source.get("generation_id") or "")
        artifact_hashes = source.get("artifact_hashes") or {}
        if not re.fullmatch(r"generation:cs:[0-9a-fA-F]{24,64}", generation_id):
            raise ValueError(
                "status=ok source generation requires its bound generation_id"
            )
        if upstream_as_of is None:
            raise ValueError("status=ok source generation requires as_of")
        for artifact in ("event_versions", "event_edges"):
            digest = str(artifact_hashes.get(artifact) or "")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                raise ValueError(
                    "status=ok source generation requires a 64-character "
                    f"{artifact} artifact hash"
                )
    if upstream_as_of is not None:
        upstream_cutoff = _parse_time(upstream_as_of, "source_generation.as_of")
        assert upstream_cutoff is not None
        if cutoff > upstream_cutoff:
            raise ValueError("as_of cannot exceed the upstream generation clock")
        if produced < upstream_cutoff:
            raise ValueError(
                "generated_at cannot precede the upstream generation clock"
            )

    event_rows = _dedupe_rows(events, id_field="event_id", kind="event")
    edge_rows = _dedupe_rows(edges, id_field="edge_id", kind="edge")
    all_events_by_id = {str(row["event_id"]): row for row in event_rows}

    for event in event_rows:
        event_id = str(event["event_id"])
        if event.get("schema") != "capital_structure.event.v1":
            raise ValueError(f"event {event_id} has an unsupported schema")
        if (event.get("version") or {}).get("immutable_record") is not True:
            raise ValueError(f"event {event_id} is not immutable")
        _validate_immutable_identity(
            event,
            id_field="event_id",
            prefix="event:cs:",
            kind="event",
        )
        _logical_key(event)
        _parse_time(
            (event.get("point_in_time") or {}).get("available_at"),
            f"event {event_id} available_at",
        )

    for edge in edge_rows:
        edge_id = str(edge["edge_id"])
        if edge.get("schema") != "capital_structure.event_edge.v1":
            raise ValueError(f"edge {edge_id} has an unsupported schema")
        if edge.get("immutable_record") is not True:
            raise ValueError(f"edge {edge_id} is not immutable")
        _validate_immutable_identity(
            edge,
            id_field="edge_id",
            prefix="edge:cs:",
            kind="edge",
        )
        relationship = str(edge.get("relationship") or "")
        if relationship not in ALL_EDGE_RELATIONSHIPS:
            raise ValueError(f"edge {edge_id} has an unsupported relationship")
        from_id = str(edge.get("from_event_id") or "")
        to_id = str(edge.get("to_event_id") or "")
        if not from_id or not to_id or from_id == to_id:
            raise ValueError(f"edge {edge_id} has invalid endpoints")
        missing = [
            event_id
            for event_id in (from_id, to_id)
            if event_id not in all_events_by_id
        ]
        if missing:
            raise ValueError(
                f"orphan edge {edge_id} references missing events: {sorted(missing)}"
            )
        _parse_time(edge.get("observed_at"), f"edge {edge_id} observed_at")

    visible_events = sorted(
        [
            event
            for event in event_rows
            if _parse_time(
                (event.get("point_in_time") or {}).get("available_at"),
                f"event {event['event_id']} available_at",
            )
            <= cutoff
        ],
        key=lambda row: str(row["event_id"]),
    )
    visible_event_ids = {str(row["event_id"]) for row in visible_events}
    visible_edges = sorted(
        [
            edge
            for edge in edge_rows
            if _parse_time(
                edge.get("observed_at"), f"edge {edge['edge_id']} observed_at"
            )
            <= cutoff
        ],
        key=lambda row: str(row["edge_id"]),
    )
    for edge in visible_edges:
        edge_id = str(edge["edge_id"])
        from_id = str(edge["from_event_id"])
        to_id = str(edge["to_event_id"])
        if from_id not in visible_event_ids or to_id not in visible_event_ids:
            raise ValueError(
                f"visible edge {edge_id} has an endpoint unavailable at as_of"
            )
        observed_at = _parse_time(edge["observed_at"], f"edge {edge_id} observed_at")
        endpoint_times = [
            _parse_time(
                (all_events_by_id[event_id].get("point_in_time") or {}).get(
                    "available_at"
                ),
                f"event {event_id} available_at",
            )
            for event_id in (from_id, to_id)
        ]
        assert observed_at is not None and all(value is not None for value in endpoint_times)
        if observed_at < max(value for value in endpoint_times if value is not None):
            raise ValueError(
                f"edge {edge_id} predates one or more system-visible endpoints"
            )

    visible_by_id = {str(row["event_id"]): row for row in visible_events}
    visible_edges_by_id = {str(row["edge_id"]): row for row in visible_edges}
    source_receipt = _source_receipt(
        visible_events, visible_edges, source_generation=source
    )

    issues: dict[str, dict[str, Any]] = {}

    def add_issue(
        reason: str,
        *,
        event_ids: Sequence[str] = (),
        edge_ids: Sequence[str] = (),
        candidate_event_ids: Sequence[str] = (),
        key: tuple[str, str, str] | None = None,
        event: Mapping[str, Any] | None = None,
        family: str | None = None,
        detail: str,
    ) -> dict[str, Any]:
        body = {
            "schema": DEFER_SCHEMA,
            "as_of": as_of_iso,
            "reason": reason,
            "registration_key": _key_object(key, event=event, family=family),
            "event_ids": sorted({str(value) for value in event_ids if value}),
            "edge_ids": sorted({str(value) for value in edge_ids if value}),
            "candidate_event_ids": sorted(
                {str(value) for value in candidate_event_ids if value}
            ),
            "detail": detail,
        }
        item = {
            "defer_id": _stable_id(
                "defer:registration-lifecycle:cs:", body
            ),
            **body,
        }
        issues[item["defer_id"]] = item
        return item

    if status in {"missing", "degraded", "no_source_manifest"}:
        if event_rows or edge_rows:
            raise ValueError(
                "an unavailable upstream generation cannot supply event or edge rows"
            )
        body: dict[str, Any] = {
            "schema": BUNDLE_SCHEMA,
            "compiler_version": COMPILER_VERSION,
            "generated_at": generated_iso,
            "as_of": as_of_iso,
            "source_receipt": source_receipt,
            "coverage": {
                "state": "unavailable",
                "reason": "upstream_generation_unavailable",
                "candidate_event_count": 0,
                "lifecycle_count": 0,
                "timeline_event_count": 0,
                "deferred_count": 0,
            },
            "records": [],
            "deferred": [],
            "scope": deepcopy(SCOPE),
            "unavailable": list(UNAVAILABLE),
            "authority": dict(AUTHORITY),
        }
        body["generation_id"] = _stable_id(
            "registration-lifecycle:cs:", body
        )
        return body

    lifecycle_edges_by_from: dict[str, list[dict[str, Any]]] = defaultdict(list)
    supersedes_by_from: dict[str, list[dict[str, Any]]] = defaultdict(list)
    supersedes_by_to: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in visible_edges:
        relationship = str(edge["relationship"])
        from_id = str(edge["from_event_id"])
        to_id = str(edge["to_event_id"])
        if relationship == "supersedes":
            supersedes_by_from[from_id].append(edge)
            supersedes_by_to[to_id].append(edge)
        else:
            lifecycle_edges_by_from[from_id].append(edge)

    blocked_corrections: set[str] = set()
    for event in visible_events:
        event_id = str(event["event_id"])
        version = event.get("version") or {}
        correction_version = int(version.get("correction_version") or 1)
        correction_of = str(version.get("correction_of") or "").strip()
        outgoing = supersedes_by_from.get(event_id, [])
        if correction_version > 1:
            matching = [
                edge
                for edge in outgoing
                if str(edge.get("to_event_id") or "") == correction_of
            ]
            if not correction_of or not matching:
                add_issue(
                    "correction_link_missing",
                    event_ids=[event_id, correction_of],
                    edge_ids=[str(edge["edge_id"]) for edge in outgoing],
                    event=event,
                    family=route_form((event.get("filing") or {}).get("form")).registration_family,
                    detail=(
                        "A visible correction version lacks one exact visible "
                        "supersedes edge to version.correction_of."
                    ),
                )
                blocked_corrections.add(event_id)
            elif len(matching) != 1 or len(outgoing) != 1:
                add_issue(
                    "ambiguous_correction_link",
                    event_ids=[event_id, correction_of],
                    edge_ids=[str(edge["edge_id"]) for edge in outgoing],
                    candidate_event_ids=[
                        str(edge.get("to_event_id") or "") for edge in outgoing
                    ],
                    event=event,
                    family=route_form((event.get("filing") or {}).get("form")).registration_family,
                    detail=(
                        "A visible correction version has more than one "
                        "supersession interpretation."
                    ),
                )
                blocked_corrections.add(event_id)
            else:
                correction_target = visible_by_id.get(correction_of)
                current_route = route_form(
                    (event.get("filing") or {}).get("form")
                )
                target_route = (
                    route_form(
                        (correction_target.get("filing") or {}).get("form")
                    )
                    if correction_target is not None
                    else None
                )
                current_candidate = _is_lifecycle_candidate(event)
                target_candidate = (
                    _is_lifecycle_candidate(correction_target)
                    if correction_target is not None
                    else False
                )
                current_issuer = str(
                    (event.get("issuer") or {}).get("issuer_id") or ""
                ).strip()
                target_issuer = str(
                    ((correction_target or {}).get("issuer") or {}).get(
                        "issuer_id"
                    )
                    or ""
                ).strip()
                current_file = str(
                    (event.get("filing") or {}).get("file_number") or ""
                ).strip()
                target_file = str(
                    ((correction_target or {}).get("filing") or {}).get(
                        "file_number"
                    )
                    or ""
                ).strip()
                current_family = current_route.registration_family
                target_family = (
                    target_route.registration_family
                    if target_route is not None
                    else None
                )
                family_proven_same = (
                    current_family == target_family
                    and current_route.relationship
                    == (target_route.relationship if target_route else None)
                    and current_route.lifecycle_state
                    == (target_route.lifecycle_state if target_route else None)
                )
                if (current_candidate or target_candidate) and (
                    not current_candidate
                    or not target_candidate
                    or not current_issuer
                    or not target_issuer
                    or current_issuer != target_issuer
                    or not current_file
                    or not target_file
                    or current_file != target_file
                    or not family_proven_same
                ):
                    issue_family = (
                        target_family
                        if target_family in REGISTRATION_FAMILIES
                        else current_family
                    )
                    add_issue(
                        "correction_group_changed",
                        event_ids=[event_id, correction_of],
                        edge_ids=[str(matching[0]["edge_id"])],
                        candidate_event_ids=[event_id],
                        event=correction_target or event,
                        family=issue_family,
                        detail=(
                            "A correction changed or obscured issuer, explicit "
                            "SEC file number, registration family, or lifecycle "
                            "form role; neither version enters a guessed group."
                        ),
                    )
                    blocked_corrections.update({event_id, correction_of})
        elif outgoing:
            add_issue(
                "ambiguous_correction_link",
                event_ids=[event_id],
                edge_ids=[str(edge["edge_id"]) for edge in outgoing],
                candidate_event_ids=[
                    str(edge.get("to_event_id") or "") for edge in outgoing
                ],
                event=event,
                family=route_form((event.get("filing") or {}).get("form")).registration_family,
                detail=(
                    "An event not declared as a correction has a visible "
                    "supersedes edge."
                ),
            )
            blocked_corrections.add(event_id)

    for to_id, incoming in supersedes_by_to.items():
        if len(incoming) > 1:
            participant_ids = [to_id, *[str(edge["from_event_id"]) for edge in incoming]]
            add_issue(
                "ambiguous_correction_link",
                event_ids=participant_ids,
                edge_ids=[str(edge["edge_id"]) for edge in incoming],
                candidate_event_ids=[str(edge["from_event_id"]) for edge in incoming],
                event=visible_by_id[to_id],
                family=route_form(
                    (visible_by_id[to_id].get("filing") or {}).get("form")
                ).registration_family,
                detail=(
                    "More than one visible correction supersedes the same "
                    "immutable event version."
                ),
            )
            blocked_corrections.update(participant_ids)

    # Supersession must be acyclic. A cycle is immutable graph corruption, not
    # a semantic question that a reviewer can safely adjudicate downstream.
    for start_id in sorted(visible_event_ids):
        seen_path: set[str] = set()
        cursor = start_id
        while supersedes_by_from.get(cursor):
            if cursor in seen_path:
                raise ValueError(f"supersedes graph contains a cycle at {cursor}")
            seen_path.add(cursor)
            candidates = supersedes_by_from[cursor]
            if len(candidates) != 1:
                break
            cursor = str(candidates[0]["to_event_id"])

    superseded_ids = set(supersedes_by_to)
    by_logical: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in visible_events:
        by_logical[_logical_key(event)].append(event)

    current_events: dict[str, dict[str, Any]] = {}
    for logical_key in sorted(by_logical):
        logical_events = by_logical[logical_key]
        if any(str(event["event_id"]) in blocked_corrections for event in logical_events):
            continue
        terminals = [
            event
            for event in logical_events
            if str(event["event_id"]) not in superseded_ids
        ]
        if not terminals:
            continue
        max_version = max(
            int((event.get("version") or {}).get("correction_version") or 1)
            for event in terminals
        )
        latest = [
            event
            for event in terminals
            if int((event.get("version") or {}).get("correction_version") or 1)
            == max_version
        ]
        if len(latest) != 1 or len(terminals) != 1:
            event_ids = [str(event["event_id"]) for event in terminals]
            exemplar = sorted(terminals, key=lambda row: str(row["event_id"]))[0]
            add_issue(
                "ambiguous_current_event_version",
                event_ids=event_ids,
                candidate_event_ids=event_ids,
                event=exemplar,
                family=route_form(
                    (exemplar.get("filing") or {}).get("form")
                ).registration_family,
                detail=(
                    "A logical SEC observation has more than one current "
                    "immutable event version at the requested cutoff."
                ),
            )
            continue
        event = latest[0]
        current_events[str(event["event_id"])] = event

    def resolve_terminal(
        event_id: str,
    ) -> tuple[str | None, set[str], set[str], str | None]:
        """Resolve an old immutable endpoint through unique visible corrections."""
        cursor = event_id
        used_events = {event_id}
        used_edges: set[str] = set()
        seen: set[str] = set()
        while supersedes_by_to.get(cursor):
            if cursor in seen:
                return None, used_events, used_edges, "ambiguous_correction_link"
            seen.add(cursor)
            successors = supersedes_by_to[cursor]
            if len(successors) != 1:
                used_edges.update(str(edge["edge_id"]) for edge in successors)
                used_events.update(str(edge["from_event_id"]) for edge in successors)
                return None, used_events, used_edges, "ambiguous_correction_link"
            edge = successors[0]
            used_edges.add(str(edge["edge_id"]))
            cursor = str(edge["from_event_id"])
            used_events.add(cursor)
        if cursor in blocked_corrections or cursor not in current_events:
            return None, used_events, used_edges, "ambiguous_current_event_version"
        return cursor, used_events, used_edges, None

    node_cache: dict[str, dict[str, Any] | None] = {}
    resolving: set[str] = set()

    def resolve_node(event_id: str) -> dict[str, Any] | None:
        if event_id in node_cache:
            return node_cache[event_id]
        event = current_events.get(event_id)
        if event is None:
            node_cache[event_id] = None
            return None
        if event_id in resolving:
            add_issue(
                "disconnected_registration_graph",
                event_ids=[event_id],
                event=event,
                family=route_form(
                    (event.get("filing") or {}).get("form")
                ).registration_family,
                detail="Lifecycle relationships contain a cycle.",
            )
            node_cache[event_id] = None
            return None
        resolving.add(event_id)
        try:
            filing = event.get("filing") or {}
            route = route_form(filing.get("form"))
            family = route.registration_family
            if not _is_lifecycle_candidate(event):
                node_cache[event_id] = None
                return None
            issuer_id = str(
                (event.get("issuer") or {}).get("issuer_id") or ""
            ).strip()
            raw_file_number = filing.get("file_number")
            file_number = (
                raw_file_number if isinstance(raw_file_number, str) else ""
            )
            if not issuer_id:
                add_issue(
                    "missing_issuer_id",
                    event_ids=[event_id],
                    event=event,
                    family=family,
                    detail=(
                        "Registration lifecycle grouping requires an explicit "
                        "stable issuer ID."
                    ),
                )
                node_cache[event_id] = None
                return None
            if not file_number.strip():
                add_issue(
                    "missing_file_number",
                    event_ids=[event_id],
                    event=event,
                    family=family,
                    detail=(
                        "Registration lifecycle grouping requires the explicit "
                        "SEC file number on every event."
                    ),
                )
                node_cache[event_id] = None
                return None
            if file_number != file_number.strip():
                add_issue(
                    "untrusted_file_number_provenance",
                    event_ids=[event_id],
                    event=event,
                    family=family,
                    detail=(
                        "The SEC file number is not a canonical exact string; "
                        "whitespace-normalized grouping is forbidden."
                    ),
                )
                node_cache[event_id] = None
                return None
            file_number_provenance = _trusted_file_number_provenance(
                event, file_number
            )
            if file_number_provenance is None:
                add_issue(
                    "untrusted_file_number_provenance",
                    event_ids=[event_id],
                    event=event,
                    family=family,
                    detail=(
                        "The SEC file number lacks one observed provenance "
                        "value matching filing.file_number and at least one "
                        "admitted source."
                    ),
                )
                node_cache[event_id] = None
                return None
            accepted_at = _parse_time(
                filing.get("accepted_at"),
                f"event {event_id} filing.accepted_at",
                nullable=True,
            )
            if accepted_at is None:
                add_issue(
                    "missing_sec_accepted_at",
                    event_ids=[event_id],
                    event=event,
                    family=family,
                    detail=(
                        "SEC acceptance time is required for causal lifecycle "
                        "chronology and is never guessed from filing date."
                    ),
                )
                node_cache[event_id] = None
                return None
            available_at = _parse_time(
                (event.get("point_in_time") or {}).get("available_at"),
                f"event {event_id} point_in_time.available_at",
            )
            assert available_at is not None
            if accepted_at > available_at:
                add_issue(
                    "noncausal_event_clock",
                    event_ids=[event_id],
                    event=event,
                    family=family,
                    detail=(
                        "SEC acceptance time cannot follow the system clock at "
                        "which the filing observation became available."
                    ),
                )
                node_cache[event_id] = None
                return None
            if (event.get("classification") or {}).get("state") != "classified":
                add_issue(
                    "registration_observation_not_classified",
                    event_ids=[event_id],
                    event=event,
                    family=family,
                    detail=(
                        "Only deterministically classified registration events "
                        "may enter the lifecycle truth plane."
                    ),
                )
                node_cache[event_id] = None
                return None
            if (event.get("lifecycle") or {}).get("state") != route.lifecycle_state:
                add_issue(
                    "form_lifecycle_state_mismatch",
                    event_ids=[event_id],
                    event=event,
                    family=family,
                    detail=(
                        "The embedded lifecycle state conflicts with the "
                        "deterministic SEC form route."
                    ),
                )
                node_cache[event_id] = None
                return None

            relationship = route.relationship
            group_key = _registration_key(event, family)
            lifecycle_edges = lifecycle_edges_by_from.get(event_id, [])
            relationship_payload: dict[str, Any] | None = None
            target_id: str | None = None
            used_event_ids: set[str] = {event_id}
            used_edge_ids: set[str] = set()
            correction_cursor = event_id
            while supersedes_by_from.get(correction_cursor):
                correction_edges = supersedes_by_from[correction_cursor]
                # Correction graph ambiguity was blocked before current-event
                # selection, so an admitted current node has exactly one edge.
                if len(correction_edges) != 1:
                    add_issue(
                        "ambiguous_correction_link",
                        event_ids=list(used_event_ids),
                        edge_ids=[
                            str(edge["edge_id"]) for edge in correction_edges
                        ],
                        event=event,
                        family=family,
                        detail=(
                            "The current event's own correction ancestry is "
                            "not uniquely receiptable."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                correction_edge = correction_edges[0]
                correction_cursor = str(correction_edge["to_event_id"])
                used_event_ids.add(correction_cursor)
                used_edge_ids.add(str(correction_edge["edge_id"]))

            if relationship is None:
                if lifecycle_edges:
                    add_issue(
                        "unexpected_lifecycle_edge",
                        event_ids=[event_id],
                        edge_ids=[str(edge["edge_id"]) for edge in lifecycle_edges],
                        event=event,
                        family=family,
                        detail=(
                            "An original registration observation cannot carry "
                            "an amendment, effectiveness, or withdrawal edge."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                if group_key is None:
                    # Issuer and file number were checked above, so this can
                    # only be a form without an admitted registration family.
                    add_issue(
                        "edge_target_not_registration",
                        event_ids=[event_id],
                        event=event,
                        family=family,
                        detail=(
                            "The form does not establish an admitted SEC "
                            "registration family."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
            else:
                expected_edges = [
                    edge
                    for edge in lifecycle_edges
                    if edge.get("relationship") == relationship
                ]
                wrong_edges = [
                    edge
                    for edge in lifecycle_edges
                    if edge.get("relationship") != relationship
                ]
                if wrong_edges:
                    add_issue(
                        "unexpected_lifecycle_edge",
                        event_ids=[event_id],
                        edge_ids=[str(edge["edge_id"]) for edge in lifecycle_edges],
                        event=event,
                        family=family,
                        detail=(
                            "The event has a lifecycle edge whose relationship "
                            "does not match its deterministic SEC form route."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                if not expected_edges:
                    add_issue(
                        "missing_lifecycle_edge",
                        event_ids=[event_id],
                        event=event,
                        family=family,
                        detail=(
                            "A non-root registration lifecycle observation "
                            "requires one visible immutable relationship edge."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                if len(expected_edges) != 1:
                    add_issue(
                        "ambiguous_lifecycle_edge",
                        event_ids=[event_id],
                        edge_ids=[str(edge["edge_id"]) for edge in expected_edges],
                        candidate_event_ids=[
                            str(edge["to_event_id"]) for edge in expected_edges
                        ],
                        event=event,
                        family=family,
                        detail=(
                            "A lifecycle observation has more than one visible "
                            "edge for its required relationship."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                edge = expected_edges[0]
                edge_id = str(edge["edge_id"])
                old_target_id = str(edge["to_event_id"])
                old_target = visible_by_id[old_target_id]
                if not _is_registration_parent(old_target):
                    add_issue(
                        "edge_target_not_registration",
                        event_ids=[event_id, old_target_id],
                        edge_ids=[edge_id],
                        event=event,
                        family=family,
                        detail=(
                            "Lifecycle edges may target only registration "
                            "statements or their registration amendments."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                (
                    resolved_target_id,
                    correction_event_ids,
                    correction_edge_ids,
                    correction_error,
                ) = resolve_terminal(old_target_id)
                if correction_error or resolved_target_id is None:
                    add_issue(
                        correction_error or "ambiguous_current_event_version",
                        event_ids=[event_id, *correction_event_ids],
                        edge_ids=[edge_id, *correction_edge_ids],
                        candidate_event_ids=list(correction_event_ids),
                        event=event,
                        family=family,
                        detail=(
                            "The immutable lifecycle target cannot be resolved "
                            "through one visible correction chain."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                resolved_target = current_events[resolved_target_id]
                if not _is_registration_parent(resolved_target):
                    add_issue(
                        "edge_target_not_registration",
                        event_ids=[event_id, old_target_id, resolved_target_id],
                        edge_ids=[edge_id, *correction_edge_ids],
                        event=event,
                        family=family,
                        detail=(
                            "The current corrected lifecycle target is no "
                            "longer a registration statement or amendment."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                target_info = resolve_node(resolved_target_id)
                if target_info is None:
                    add_issue(
                        "disconnected_registration_graph",
                        event_ids=[event_id, old_target_id, resolved_target_id],
                        edge_ids=[edge_id, *correction_edge_ids],
                        event=event,
                        family=family,
                        detail=(
                            "The lifecycle target does not resolve to one "
                            "admitted registration root."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                target_key = target_info["group_key"]
                old_route = route_form(
                    (old_target.get("filing") or {}).get("form")
                )
                old_key = _registration_key(
                    old_target, old_route.registration_family
                )
                if old_target_id != resolved_target_id:
                    old_issuer = str(
                        (old_target.get("issuer") or {}).get("issuer_id") or ""
                    ).strip()
                    old_file = str(
                        (old_target.get("filing") or {}).get("file_number") or ""
                    ).strip()
                    if (
                        not old_issuer
                        or not old_file
                        or old_issuer != target_key[0]
                        or old_file != target_key[1]
                        or (old_key is not None and old_key != target_key)
                    ):
                        add_issue(
                            "correction_group_changed",
                            event_ids=[event_id, old_target_id, resolved_target_id],
                            edge_ids=[edge_id, *correction_edge_ids],
                            candidate_event_ids=[resolved_target_id],
                            event=event,
                            family=family,
                            detail=(
                                "A corrected edge target changed issuer, SEC "
                                "file number, or registration family; the old "
                                "edge is not silently retargeted."
                            ),
                        )
                        node_cache[event_id] = None
                        return None

                if issuer_id != target_key[0]:
                    add_issue(
                        "cross_issuer_link",
                        event_ids=[event_id, old_target_id, resolved_target_id],
                        edge_ids=[edge_id, *correction_edge_ids],
                        event=event,
                        family=family,
                        detail=(
                            "Lifecycle edge endpoints do not share the exact "
                            "stable issuer ID."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                if file_number != target_key[1]:
                    add_issue(
                        "file_number_mismatch",
                        event_ids=[event_id, old_target_id, resolved_target_id],
                        edge_ids=[edge_id, *correction_edge_ids],
                        event=event,
                        family=family,
                        detail=(
                            "Lifecycle edge endpoints do not share the exact "
                            "explicit SEC file number."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                if family is not None and family != target_key[2]:
                    add_issue(
                        "registration_family_mismatch",
                        event_ids=[event_id, old_target_id, resolved_target_id],
                        edge_ids=[edge_id, *correction_edge_ids],
                        event=event,
                        family=family,
                        detail=(
                            "Lifecycle edge endpoints do not share the same "
                            "deterministic registration family."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                target_accepted = target_info["accepted_at_dt"]
                if target_accepted >= accepted_at:
                    add_issue(
                        "noncausal_linkage",
                        event_ids=[event_id, old_target_id, resolved_target_id],
                        edge_ids=[edge_id, *correction_edge_ids],
                        candidate_event_ids=[resolved_target_id],
                        key=target_key,
                        detail=(
                            "A lifecycle edge target must have a strictly "
                            "earlier SEC acceptance timestamp than its child."
                        ),
                    )
                    node_cache[event_id] = None
                    return None
                group_key = target_key
                target_id = resolved_target_id
                used_event_ids.update(correction_event_ids)
                used_event_ids.update(target_info["used_event_ids"])
                used_edge_ids.add(edge_id)
                used_edge_ids.update(correction_edge_ids)
                used_edge_ids.update(target_info["used_edge_ids"])
                relationship_payload = {
                    "edge_id": edge_id,
                    "relationship": relationship,
                    "to_event_id": old_target_id,
                    "resolved_to_event_id": resolved_target_id,
                    "observed_at": str(edge["observed_at"]),
                }

            assert group_key is not None
            transition = str(route.lifecycle_state)
            node = {
                "event": event,
                "event_id": event_id,
                "group_key": group_key,
                "transition": transition,
                "relationship": relationship_payload,
                "target_id": target_id,
                "accepted_at_dt": accepted_at,
                "accepted_at": accepted_at.isoformat().replace("+00:00", "Z"),
                "file_number_provenance": file_number_provenance,
                "used_event_ids": used_event_ids,
                "used_edge_ids": used_edge_ids,
            }
            node_cache[event_id] = node
            return node
        finally:
            resolving.discard(event_id)

    raw_candidate_ids = {
        str(event["event_id"])
        for event in visible_events
        if _is_lifecycle_candidate(event)
    }
    for event_id in sorted(current_events):
        current_event = current_events[event_id]
        if _is_lifecycle_candidate(current_event):
            resolve_node(event_id)
        elif lifecycle_edges_by_from.get(event_id):
            add_issue(
                "unexpected_lifecycle_edge",
                event_ids=[event_id],
                edge_ids=[
                    str(edge["edge_id"])
                    for edge in lifecycle_edges_by_from[event_id]
                ],
                event=current_event,
                detail=(
                    "A current non-registration observation carries a visible "
                    "registration lifecycle edge."
                ),
            )

    valid_nodes = {
        event_id: node
        for event_id, node in node_cache.items()
        if node is not None
    }
    by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for node in valid_nodes.values():
        by_group[node["group_key"]].append(node)

    records: list[dict[str, Any]] = []
    for key in sorted(by_group):
        nodes = by_group[key]
        roots = [node for node in nodes if node["target_id"] is None]
        if len(roots) != 1:
            reason = (
                "missing_registration_root" if not roots else "multiple_registration_roots"
            )
            add_issue(
                reason,
                event_ids=[node["event_id"] for node in nodes],
                candidate_event_ids=[node["event_id"] for node in roots],
                key=key,
                detail=(
                    "A registration lifecycle requires exactly one original "
                    "registration root for its strict grouping key."
                ),
            )
            continue
        root_id = roots[0]["event_id"]
        node_ids = {node["event_id"] for node in nodes}
        disconnected: set[str] = set()
        for node in nodes:
            cursor = node
            visited: set[str] = set()
            while cursor["target_id"] is not None:
                if cursor["event_id"] in visited:
                    disconnected.add(node["event_id"])
                    break
                visited.add(cursor["event_id"])
                target_id = str(cursor["target_id"])
                if target_id not in node_ids:
                    disconnected.add(node["event_id"])
                    break
                cursor = valid_nodes[target_id]
            if cursor["event_id"] != root_id:
                disconnected.add(node["event_id"])
        if disconnected:
            add_issue(
                "disconnected_registration_graph",
                event_ids=sorted(disconnected),
                candidate_event_ids=sorted(node_ids),
                key=key,
                detail=(
                    "One or more lifecycle events do not resolve to the unique "
                    "registration root."
                ),
            )
            continue

        accepted_groups: dict[str, list[str]] = defaultdict(list)
        for node in nodes:
            accepted_groups[node["accepted_at"]].append(node["event_id"])
        ambiguous_times = {
            accepted: event_ids
            for accepted, event_ids in accepted_groups.items()
            if len(event_ids) > 1
        }
        if ambiguous_times:
            ambiguous_ids = sorted(
                event_id
                for event_ids in ambiguous_times.values()
                for event_id in event_ids
            )
            add_issue(
                "ambiguous_sec_chronology",
                event_ids=ambiguous_ids,
                candidate_event_ids=ambiguous_ids,
                key=key,
                detail=(
                    "Two or more lifecycle observations share the same SEC "
                    "acceptance timestamp, so transition order is not guessed."
                ),
            )
            continue

        nodes.sort(key=lambda node: (node["accepted_at_dt"], node["event_id"]))
        if nodes[0]["event_id"] != root_id:
            add_issue(
                "noncausal_linkage",
                event_ids=[node["event_id"] for node in nodes],
                candidate_event_ids=[root_id],
                key=key,
                detail=(
                    "The unique registration root is not the earliest SEC "
                    "acceptance observation in its lifecycle."
                ),
            )
            continue

        state: str | None = None
        timeline: list[dict[str, Any]] = []
        record_event_ids: set[str] = set()
        record_edge_ids: set[str] = set()
        for node in nodes:
            transition = node["transition"]
            if transition == "filed":
                state = "filed"
            elif transition == "amended":
                if state == "withdrawn":
                    add_issue(
                        "post_withdrawal_transition",
                        event_ids=[node["event_id"]],
                        edge_ids=[
                            node["relationship"]["edge_id"]
                        ] if node["relationship"] else [],
                        key=key,
                        detail=(
                            "An amendment observed after withdrawal cannot "
                            "change the compiled registration state."
                        ),
                    )
                    continue
                state = "effective" if state == "effective" else "amended"
            elif transition == "effective":
                if state == "withdrawn":
                    add_issue(
                        "post_withdrawal_transition",
                        event_ids=[node["event_id"]],
                        edge_ids=[
                            node["relationship"]["edge_id"]
                        ] if node["relationship"] else [],
                        key=key,
                        detail=(
                            "An effectiveness notice observed after withdrawal "
                            "cannot change the compiled registration state."
                        ),
                    )
                    continue
                state = "effective"
            elif transition == "withdrawn":
                state = "withdrawn"
            else:
                raise ValueError(
                    f"unsupported registration lifecycle transition: {transition!r}"
                )
            event = node["event"]
            point_in_time = event.get("point_in_time") or {}
            timeline.append(
                {
                    "event_id": node["event_id"],
                    "accession": (event.get("filing") or {}).get("accession"),
                    "form": str((event.get("filing") or {}).get("form") or ""),
                    "transition": transition,
                    "state_after_event": state,
                    "sec_accepted_at": node["accepted_at"],
                    "mastermind_available_at": str(point_in_time.get("available_at") or ""),
                    "correction_version": int(
                        (event.get("version") or {}).get("correction_version") or 1
                    ),
                    "relationship": deepcopy(node["relationship"]),
                    "manifest_ids": sorted(
                        str(value)
                        for value in ((event.get("source") or {}).get("manifest_ids") or [])
                        if value
                    ),
                }
            )
            record_event_ids.update(node["used_event_ids"])
            record_edge_ids.update(node["used_edge_ids"])

        if not timeline or state is None:
            continue
        matching_issue_ids = sorted(
            issue["defer_id"]
            for issue in issues.values()
            if issue["registration_key"] == _key_object(key)
        )
        issuer_events = [node["event"] for node in nodes]
        ciks = sorted(
            {
                str((event.get("issuer") or {}).get("cik"))
                for event in issuer_events
                if (event.get("issuer") or {}).get("cik")
            }
        )
        if len(ciks) > 1:
            add_issue(
                "conflicting_issuer_cik",
                event_ids=[node["event_id"] for node in nodes],
                key=key,
                detail=(
                    "One stable issuer ID carries conflicting explicit CIK "
                    "values inside the lifecycle."
                ),
            )
            continue
        tickers = sorted(
            {
                str((event.get("issuer") or {}).get("ticker"))
                for event in issuer_events
                if (event.get("issuer") or {}).get("ticker")
            }
        )
        latest_ticker = next(
            (
                str((node["event"].get("issuer") or {}).get("ticker"))
                for node in reversed(nodes)
                if (node["event"].get("issuer") or {}).get("ticker")
            ),
            None,
        )
        # CIK validation above may have added a group issue after the first
        # matching-issue snapshot. Refresh it before emitting record coverage.
        matching_issue_ids = sorted(
            issue["defer_id"]
            for issue in issues.values()
            if issue["registration_key"] == _key_object(key)
        )
        lifecycle_identity = {
            "issuer_id": key[0],
            "file_number": key[1],
            "registration_family": key[2],
        }
        records.append(
            {
                "schema": RECORD_SCHEMA,
                "lifecycle_id": _stable_id(
                    "lifecycle:registration:cs:", lifecycle_identity
                ),
                "issuer": {
                    "issuer_id": key[0],
                    "cik": ciks[0] if ciks else None,
                    "ticker": latest_ticker,
                    "observed_tickers": tickers,
                },
                "registration": {
                    "file_number": key[1],
                    "file_number_provenance": {
                        "state": "observed",
                        "value": key[1],
                        "candidate_values": [key[1]],
                        "sources": sorted(
                            {
                                source
                                for node in nodes
                                for source in node[
                                    "file_number_provenance"
                                ]["sources"]
                            }
                        ),
                    },
                    "registration_family": key[2],
                },
                "as_of": as_of_iso,
                "observed_registration_state": state,
                "latest_observed_event_id": timeline[-1]["event_id"],
                "timeline": timeline,
                "derivation_receipt": _derivation_receipt(
                    record_event_ids,
                    record_edge_ids,
                    events_by_id=visible_by_id,
                    edges_by_id=visible_edges_by_id,
                ),
                "coverage": {
                    "state": "partial" if matching_issue_ids else "observed",
                    "reason": (
                        "one_or_more_registration_events_deferred"
                        if matching_issue_ids
                        else "linked_observed_registration_events_only"
                    ),
                    "deferred_ids": matching_issue_ids,
                },
                "scope": deepcopy(SCOPE),
                "unavailable": list(UNAVAILABLE),
                "authority": dict(AUTHORITY),
            }
        )

    records.sort(
        key=lambda record: (
            record["issuer"]["issuer_id"],
            record["registration"]["file_number"],
            record["registration"]["registration_family"],
        )
    )
    deferred = sorted(issues.values(), key=lambda issue: issue["defer_id"])
    if deferred:
        coverage_state = "partial"
        coverage_reason = "deferred_registration_lifecycle_observations_present"
    elif not raw_candidate_ids:
        coverage_state = "unavailable"
        coverage_reason = "no_visible_registration_lifecycle_observations"
    else:
        coverage_state = "observed"
        coverage_reason = "linked_observed_registration_lifecycles_only"
    body = {
        "schema": BUNDLE_SCHEMA,
        "compiler_version": COMPILER_VERSION,
        "generated_at": generated_iso,
        "as_of": as_of_iso,
        "source_receipt": source_receipt,
        "coverage": {
            "state": coverage_state,
            "reason": coverage_reason,
            "candidate_event_count": len(raw_candidate_ids),
            "lifecycle_count": len(records),
            "timeline_event_count": sum(
                len(record["timeline"]) for record in records
            ),
            "deferred_count": len(deferred),
        },
        "records": records,
        "deferred": deferred,
        "scope": deepcopy(SCOPE),
        "unavailable": list(UNAVAILABLE),
        "authority": dict(AUTHORITY),
    }
    body["generation_id"] = _stable_id(
        "registration-lifecycle:cs:", body
    )
    return body


def validate_registration_lifecycle_bundle(
    bundle: Mapping[str, Any], schema_path: Path | None = None
) -> None:
    """Validate a compiled bundle against its closed JSON contract."""
    from jsonschema import Draft202012Validator, FormatChecker

    path = schema_path or (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "capital_structure_registration_lifecycle.schema.json"
    )
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable registration lifecycle schema: {path}") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(dict(bundle)),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "$"
        raise ValueError(
            f"registration lifecycle bundle violates contract at {location}: "
            f"{first.message}"
        )


# Singular alias for call sites that name the returned artifact rather than the
# set of lifecycle records. Both names intentionally share one implementation.
compile_registration_lifecycle_bundle = compile_registration_lifecycles
