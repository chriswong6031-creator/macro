"""Exact actual-output playback catalog over published W1 generations.

W3A prepares a catalog; it does not execute playback or emit playback evidence.
It does not reconstruct history.  It enumerates only owner-validated
``operational_pit`` captures already published by the W1A missingness store and
the W1B.1 trusted canary store.  The independently published generation pair
is pinned explicitly for deterministic pagination and is never described as an
atomic cross-store snapshot or a complete opportunity population.

This module performs no writes, reads no private source-evidence roots, exposes
no feature values, and contains no nearest/latest/reconstruction fallback.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from itertools import pairwise
from typing import Any, NoReturn

from engine.neuralweb import market_memory, market_memory_pit, market_memory_trusted

OPERATIONAL_PLAYBACK_CATALOG_SCHEMA = "market_memory.operational_playback_catalog.v1"
ACTUAL_OUTPUT_MODE = "actual_output_operational_pit"

_CATALOG_ID = re.compile(r"mmplayback_[a-f0-9]{64}\Z")
_CATALOG_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z\Z"
)
_MAX_CATALOG_BYTES = 512 * 1024
_MAX_JSON_DEPTH = 18
_MAX_JSON_NODES = 16_384
_MAX_STRING_BYTES = 4 * 1024
_MAX_PAGE_SIZE = 100
_MAX_OFFSET = 2 * market_memory_pit._MAX_GENERATION_CAPTURES
_MAX_SCAN_RECEIPT_BYTES = 64 * 1024 * 1024
_MAX_SCAN_RECEIPTS = 2 * market_memory_pit._MAX_GENERATION_CAPTURES
_MAX_RETURNED_PACKET_BYTES = 128 * 1024 * 1024
_ORDERING = "as_known_at_desc.event_time_desc.query_id_asc.context_id_asc.v1"
_PROFILE_ORDER = (
    market_memory_pit.STORE_PROFILE,
    market_memory_trusted.TRUSTED_STORE_PROFILE,
)
_CATALOG_FIELDS = frozenset(
    {
        "schema",
        "catalog_id",
        "mode",
        "subject",
        "generations",
        "selection",
        "entries",
        "coverage",
        "replay_policy",
        "authority",
    }
)
_GENERATION_FIELDS = frozenset(
    {
        "profile",
        "store_id",
        "generation_id",
        "generation_sha256",
        "capture_count",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "offset",
        "limit",
        "ordering",
        "total_matching",
        "returned",
        "truncated",
        "continuation",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "ordinal",
        "capture_provenance",
        "query_id",
        "context_id",
        "packet_sha256",
        "event_time",
        "as_known_at",
        "domain_states",
    }
)
_PROVENANCE_FIELDS = frozenset({"profile", "capture_id", "captured_at"})
_CONTINUATION_FIELDS = frozenset(
    {
        "subject",
        "w1a_generation_id",
        "trusted_generation_id",
        "offset",
        "limit",
    }
)
_DOMAIN_STATE_FIELDS = frozenset({"domain", "status"})
_COVERAGE = {
    "receipt_index_scan_complete": True,
    "returned_entries_packet_closure_validated": True,
    "off_page_packets_validated": False,
    "captured_opportunity_population_complete": False,
    "historical_coverage_complete": False,
    "cross_store_atomic_snapshot": False,
}
_REPLAY_POLICY = {
    "catalog_only": True,
    "playback_execution_performed": False,
    "playback_evidence_included": False,
    "exact_captured_contexts_only": True,
    "reconstruction_performed": False,
    "nearest_fallback": False,
    "latest_fallback": False,
    "request_time_materialization": False,
    "private_evidence_read": False,
    "labels_outcomes_scores_included": False,
    "identical_query_deduplication": "dual_capture_provenance",
    "catalog_content_addressed": True,
    "origin_signature_authenticated": False,
    "capture_clock_externally_authenticated": False,
    "generation_pin_order": list(_PROFILE_ORDER),
}


class MarketMemoryPlaybackContractError(ValueError):
    """A caller input or catalog payload violates the frozen W3A contract."""


@dataclass(frozen=True)
class _Candidate:
    profile: str
    query_id: str
    receipt: dict[str, Any]
    provenance: tuple[tuple[str, str, str], ...]


def _fail(message: str) -> NoReturn:
    raise MarketMemoryPlaybackContractError(message)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryPlaybackContractError(
            "playback catalog is not canonical finite JSON"
        ) from exc


def _content_id(value: Mapping[str, Any]) -> str:
    core = copy.deepcopy(dict(value))
    core["catalog_id"] = ""
    return "mmplayback_" + sha256(_canonical_bytes(core)).hexdigest()


def _exact_int(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        _fail(f"{field} must be an integer from {minimum} through {maximum}")
    return value


def _timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not _CATALOG_TIMESTAMP.fullmatch(value):
        _fail(f"{field} must be canonical RFC3339 UTC with terminal Z")
    try:
        parsed, clean = market_memory_pit._parse_exact_utc(value, field=field)
    except market_memory_pit.MarketMemoryQueryError as exc:
        raise MarketMemoryPlaybackContractError(str(exc)) from exc
    if clean != value:
        _fail(f"{field} is not in canonical UTC form")
    return parsed


def _subject(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "subject_id",
        "instrument_id",
    }:
        _fail("subject must contain exactly subject_id and instrument_id")
    try:
        return {
            "subject_id": market_memory_pit._security_id(
                value.get("subject_id"), field="subject_id"
            ),
            "instrument_id": market_memory_pit._security_id(
                value.get("instrument_id"), field="instrument_id"
            ),
        }
    except market_memory_pit.MarketMemoryQueryError as exc:
        raise MarketMemoryPlaybackContractError(str(exc)) from exc


def _pagination(*, offset: object, limit: object) -> tuple[int, int]:
    return (
        _exact_int(offset, field="offset", minimum=0, maximum=_MAX_OFFSET),
        _exact_int(limit, field="limit", minimum=1, maximum=_MAX_PAGE_SIZE),
    )


def _generation_ref(
    snapshot: market_memory_pit.PinnedGenerationSnapshot,
) -> dict[str, Any]:
    return {
        "profile": snapshot.profile,
        "store_id": snapshot.store_id,
        "generation_id": snapshot.generation_id,
        "generation_sha256": snapshot.generation_sha256,
        "capture_count": len(snapshot.captures),
    }


def _reader_for_profile(
    reader: market_memory_trusted.CompositeAsKnownAtReader, profile: str
) -> (
    market_memory_pit.FileAsKnownAtReader
    | market_memory_trusted.TrustedFileAsKnownAtReader
):
    if profile == market_memory_pit.STORE_PROFILE:
        return reader.w1a
    if profile == market_memory_trusted.TRUSTED_STORE_PROFILE:
        return reader.trusted
    raise market_memory_pit.MarketMemoryStoreError(
        "playback generation profile is not registered"
    )


def _stored_profile_candidate(
    *,
    reader: market_memory_trusted.CompositeAsKnownAtReader,
    snapshots: Mapping[str, market_memory_pit.PinnedGenerationSnapshot],
    profile: str,
    query_id: str,
) -> market_memory_pit.StoredMarketMemoryContext:
    owner = _reader_for_profile(reader, profile)
    return owner.read_stored_from_pinned_generation(
        snapshots[profile], query_id=query_id
    )


def _candidate_sort_key(candidate: _Candidate) -> tuple[datetime, datetime, str, str]:
    clocks = candidate.receipt["clocks"]
    return (
        _timestamp(clocks["as_known_at"], field="entry.as_known_at"),
        _timestamp(clocks["event_time"], field="entry.event_time"),
        candidate.query_id,
        str(candidate.receipt["context_id"]),
    )


def build_operational_playback_catalog(
    *,
    reader: market_memory_trusted.CompositeAsKnownAtReader,
    w1a_generation: market_memory_pit.PinnedGenerationSnapshot,
    trusted_generation: market_memory_pit.PinnedGenerationSnapshot,
    subject: Mapping[str, str],
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Build one deterministic page from two authenticated generation indexes."""

    if not isinstance(reader, market_memory_trusted.CompositeAsKnownAtReader):
        _fail("reader must be a CompositeAsKnownAtReader")
    if not isinstance(
        w1a_generation, market_memory_pit.PinnedGenerationSnapshot
    ) or not isinstance(trusted_generation, market_memory_pit.PinnedGenerationSnapshot):
        _fail("both generations must be PinnedGenerationSnapshot values")
    clean_subject = _subject(subject)
    clean_offset, clean_limit = _pagination(offset=offset, limit=limit)

    # Accept only reader-sealed snapshot identity; an equal caller-created
    # dataclass is re-resolved through current HEAD ancestry.  This prevents a
    # crash-orphan object from being laundered into the catalog while avoiding
    # a second ancestry walk inside the same read/build operation.
    authenticated_w1a = reader.w1a._authenticate_pinned_snapshot(w1a_generation)
    authenticated_trusted = reader.trusted._authenticate_pinned_snapshot(
        trusted_generation
    )
    if authenticated_w1a != w1a_generation:
        raise market_memory_pit.MarketMemoryStoreError(
            "W1A playback generation differs from published bytes"
        )
    if authenticated_trusted != trusted_generation:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted playback generation differs from published bytes"
        )
    if authenticated_w1a.profile != _PROFILE_ORDER[0]:
        raise market_memory_pit.MarketMemoryStoreError(
            "W1A playback generation profile mismatch"
        )
    if authenticated_trusted.profile != _PROFILE_ORDER[1]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted playback generation profile mismatch"
        )
    snapshots = {
        authenticated_w1a.profile: authenticated_w1a,
        authenticated_trusted.profile: authenticated_trusted,
    }

    candidates: dict[str, _Candidate] = {}
    scan_bytes = 0
    scan_receipts = 0
    for snapshot in (authenticated_w1a, authenticated_trusted):
        owner = _reader_for_profile(reader, snapshot.profile)
        for index_entry in snapshot.captures:
            scan_receipts += 1
            if scan_receipts > _MAX_SCAN_RECEIPTS:
                raise market_memory_pit.MarketMemoryStoreError(
                    "playback receipt scan exceeds its entry bound"
                )
            receipt = owner.read_pinned_capture_receipt(
                snapshot, query_id=index_entry.query_id
            )
            scan_bytes += len(_canonical_bytes(receipt))
            if scan_bytes > _MAX_SCAN_RECEIPT_BYTES:
                raise market_memory_pit.MarketMemoryStoreError(
                    "playback receipt scan exceeds its aggregate byte bound"
                )
            if receipt["subject"] != clean_subject:
                continue
            candidate = _Candidate(
                profile=snapshot.profile,
                query_id=index_entry.query_id,
                receipt=receipt,
                provenance=(
                    (
                        snapshot.profile,
                        str(receipt["capture_id"]),
                        str(receipt["captured_at"]),
                    ),
                ),
            )
            existing = candidates.get(candidate.query_id)
            if existing is None:
                candidates[candidate.query_id] = candidate
                continue
            if (
                existing.receipt["packet_sha256"] != candidate.receipt["packet_sha256"]
                or existing.receipt["context_id"] != candidate.receipt["context_id"]
            ):
                raise market_memory_pit.MarketMemoryStoreError(
                    "exact playback query is ambiguously published by both stores"
                )
            provenance_by_profile = {
                profile: (capture_id, captured_at)
                for profile, capture_id, captured_at in (
                    *existing.provenance,
                    *candidate.provenance,
                )
            }
            provenance = tuple(
                (profile, *provenance_by_profile[profile])
                for profile in _PROFILE_ORDER
                if profile in provenance_by_profile
            )
            selected = (
                candidate
                if candidate.profile == market_memory_trusted.TRUSTED_STORE_PROFILE
                else existing
            )
            candidates[candidate.query_id] = _Candidate(
                profile=selected.profile,
                query_id=selected.query_id,
                receipt=selected.receipt,
                provenance=provenance,
            )

    ordered = list(candidates.values())
    # Stable passes preserve ascending opaque IDs while making clocks descending.
    ordered.sort(key=lambda row: (row.query_id, row.receipt["context_id"]))
    ordered.sort(
        key=lambda row: _candidate_sort_key(row)[1],
        reverse=True,
    )
    ordered.sort(
        key=lambda row: _candidate_sort_key(row)[0],
        reverse=True,
    )
    total = len(ordered)
    page = ordered[clean_offset : clean_offset + clean_limit]
    entries: list[dict[str, Any]] = []
    returned_packet_bytes = 0
    for page_index, candidate in enumerate(page):
        stored_by_profile: dict[str, market_memory_pit.StoredMarketMemoryContext] = {}
        canonical_packet: bytes | None = None
        for profile, capture_id, captured_at in candidate.provenance:
            stored_for_profile = _stored_profile_candidate(
                reader=reader,
                snapshots=snapshots,
                profile=profile,
                query_id=candidate.query_id,
            )
            stored_receipt = stored_for_profile.capture_receipt
            if (
                stored_receipt["capture_id"] != capture_id
                or stored_receipt["captured_at"] != captured_at
                or stored_receipt["query_id"] != candidate.query_id
                or stored_receipt["context_id"] != candidate.receipt["context_id"]
                or stored_receipt["packet_sha256"] != candidate.receipt["packet_sha256"]
            ):
                raise market_memory_pit.MarketMemoryStoreError(
                    "playback provenance differs from its stored packet receipt"
                )
            packet_body = _canonical_bytes(stored_for_profile.packet)
            returned_packet_bytes += len(packet_body)
            if returned_packet_bytes > _MAX_RETURNED_PACKET_BYTES:
                raise market_memory_pit.MarketMemoryStoreError(
                    "playback returned packets exceed their aggregate byte bound"
                )
            if canonical_packet is None:
                canonical_packet = packet_body
            elif packet_body != canonical_packet:
                raise market_memory_pit.MarketMemoryStoreError(
                    "dual-provenance playback packets differ in canonical bytes"
                )
            stored_by_profile[profile] = stored_for_profile

        stored = stored_by_profile[candidate.profile]
        receipt = stored.capture_receipt
        packet = stored.packet
        domain_states = [
            {"domain": row["domain"], "status": row["status"]}
            for row in packet["domain_coverage"]
        ]
        entries.append(
            {
                "ordinal": clean_offset + page_index,
                "capture_provenance": [
                    {
                        "profile": profile,
                        "capture_id": capture_id,
                        "captured_at": captured_at,
                    }
                    for profile, capture_id, captured_at in candidate.provenance
                ],
                "query_id": receipt["query_id"],
                "context_id": receipt["context_id"],
                "packet_sha256": receipt["packet_sha256"],
                "event_time": receipt["clocks"]["event_time"],
                "as_known_at": receipt["clocks"]["as_known_at"],
                "domain_states": domain_states,
            }
        )

    returned = len(entries)
    has_more = clean_offset + returned < total
    continuation = (
        {
            "subject": copy.deepcopy(clean_subject),
            "w1a_generation_id": authenticated_w1a.generation_id,
            "trusted_generation_id": authenticated_trusted.generation_id,
            "offset": clean_offset + returned,
            "limit": clean_limit,
        }
        if has_more
        else None
    )
    catalog: dict[str, Any] = {
        "schema": OPERATIONAL_PLAYBACK_CATALOG_SCHEMA,
        "catalog_id": "",
        "mode": ACTUAL_OUTPUT_MODE,
        "subject": clean_subject,
        "generations": [
            _generation_ref(authenticated_w1a),
            _generation_ref(authenticated_trusted),
        ],
        "selection": {
            "offset": clean_offset,
            "limit": clean_limit,
            "ordering": _ORDERING,
            "total_matching": total,
            "returned": returned,
            "truncated": has_more,
            "continuation": continuation,
        },
        "entries": entries,
        "coverage": copy.deepcopy(_COVERAGE),
        "replay_policy": copy.deepcopy(_REPLAY_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    catalog["catalog_id"] = _content_id(catalog)
    return validate_operational_playback_catalog(catalog)


def validate_operational_playback_catalog(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly validate and detach one W3A catalog page."""

    if not isinstance(value, Mapping) or set(value) != _CATALOG_FIELDS:
        _fail("playback catalog fields are not canonical")
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != OPERATIONAL_PLAYBACK_CATALOG_SCHEMA:
        _fail("playback catalog schema mismatch")
    catalog_id = clean.get("catalog_id")
    if not isinstance(catalog_id, str) or not _CATALOG_ID.fullmatch(catalog_id):
        _fail("catalog_id must be mmplayback_<sha256>")
    if clean.get("mode") != ACTUAL_OUTPUT_MODE:
        _fail("playback catalog supports actual_output_operational_pit only")
    clean["subject"] = _subject(clean.get("subject"))

    generations = clean.get("generations")
    if not isinstance(generations, list) or len(generations) != 2:
        _fail("generations must contain exactly W1A then trusted")
    clean_generations: list[dict[str, Any]] = []
    for index, generation in enumerate(generations):
        if not isinstance(generation, Mapping) or set(generation) != _GENERATION_FIELDS:
            _fail("generation reference fields are not canonical")
        row = copy.deepcopy(dict(generation))
        if row.get("profile") != _PROFILE_ORDER[index]:
            _fail("generation references must preserve the frozen pin order")
        if not isinstance(
            row.get("store_id"), str
        ) or not market_memory_pit._STORE_ID.fullmatch(row["store_id"]):
            _fail("generation store_id is malformed")
        if not isinstance(
            row.get("generation_id"), str
        ) or not market_memory_pit._GENERATION_ID.fullmatch(row["generation_id"]):
            _fail("generation_id is malformed")
        if not isinstance(
            row.get("generation_sha256"), str
        ) or not market_memory_pit._SHA256.fullmatch(row["generation_sha256"]):
            _fail("generation_sha256 is malformed")
        row["capture_count"] = _exact_int(
            row.get("capture_count"),
            field="generation.capture_count",
            minimum=0,
            maximum=market_memory_pit._MAX_GENERATION_CAPTURES,
        )
        clean_generations.append(row)
    clean["generations"] = clean_generations

    selection = clean.get("selection")
    if not isinstance(selection, Mapping) or set(selection) != _SELECTION_FIELDS:
        _fail("selection fields are not canonical")
    clean_selection = copy.deepcopy(dict(selection))
    offset, limit = _pagination(
        offset=clean_selection.get("offset"), limit=clean_selection.get("limit")
    )
    if clean_selection.get("ordering") != _ORDERING:
        _fail("selection ordering semantics drift")
    total = _exact_int(
        clean_selection.get("total_matching"),
        field="selection.total_matching",
        minimum=0,
        maximum=_MAX_OFFSET,
    )
    if total > sum(row["capture_count"] for row in clean_generations):
        _fail("selection.total_matching exceeds pinned generation indexes")
    returned = _exact_int(
        clean_selection.get("returned"),
        field="selection.returned",
        minimum=0,
        maximum=_MAX_PAGE_SIZE,
    )
    expected_returned = min(limit, max(0, total - offset))
    if returned != expected_returned:
        _fail("selection.returned does not match its deterministic page")
    has_more = offset + returned < total
    if (
        type(clean_selection.get("truncated")) is not bool
        or clean_selection["truncated"] is not has_more
    ):
        _fail("selection.truncated does not match the page boundary")
    continuation = clean_selection.get("continuation")
    if has_more:
        if (
            not isinstance(continuation, Mapping)
            or set(continuation) != _CONTINUATION_FIELDS
        ):
            _fail("selection continuation recipe is not canonical")
        clean_continuation = copy.deepcopy(dict(continuation))
        if clean_continuation.get("subject") != clean["subject"]:
            _fail("selection continuation changes subject")
        if (
            clean_continuation.get("w1a_generation_id")
            != clean_generations[0]["generation_id"]
            or clean_continuation.get("trusted_generation_id")
            != clean_generations[1]["generation_id"]
        ):
            _fail("selection continuation changes pinned generations")
        if clean_continuation.get("offset") != offset + returned:
            _fail("selection continuation offset does not follow this page")
        if clean_continuation.get("limit") != limit:
            _fail("selection continuation changes page limit")
        clean_selection["continuation"] = clean_continuation
    elif continuation is not None:
        _fail("terminal selection continuation must be null")
    clean_selection.update(
        {
            "offset": offset,
            "limit": limit,
            "total_matching": total,
            "returned": returned,
        }
    )
    clean["selection"] = clean_selection

    entries = clean.get("entries")
    if not isinstance(entries, list) or len(entries) != returned:
        _fail("entries must equal selection.returned")
    clean_entries: list[dict[str, Any]] = []
    ordering: list[tuple[datetime, datetime, str, str]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != _ENTRY_FIELDS:
            _fail("playback entry fields are not canonical")
        row = copy.deepcopy(dict(entry))
        ordinal = _exact_int(
            row.get("ordinal"), field="entry.ordinal", minimum=0, maximum=_MAX_OFFSET
        )
        if ordinal != offset + index:
            _fail("entry ordinal does not match selection offset")
        provenance = row.get("capture_provenance")
        if not isinstance(provenance, list) or not 1 <= len(provenance) <= 2:
            _fail("entry capture_provenance must contain one or two receipts")
        clean_provenance: list[dict[str, str]] = []
        for provenance_index, capture in enumerate(provenance):
            if not isinstance(capture, Mapping) or set(capture) != _PROVENANCE_FIELDS:
                _fail("entry capture provenance fields are not canonical")
            profile = capture.get("profile")
            if profile not in _PROFILE_ORDER:
                _fail("entry capture provenance profile is not registered")
            if provenance_index > 0 and _PROFILE_ORDER.index(
                str(profile)
            ) <= _PROFILE_ORDER.index(str(provenance[provenance_index - 1]["profile"])):
                _fail("entry capture provenance is not in canonical profile order")
            capture_id = capture.get("capture_id")
            if not isinstance(
                capture_id, str
            ) or not market_memory_pit._CAPTURE_ID.fullmatch(capture_id):
                _fail("entry capture provenance capture_id is malformed")
            clean_provenance.append(
                {
                    "profile": str(profile),
                    "capture_id": capture_id,
                    "captured_at": str(capture.get("captured_at")),
                }
            )
        row["capture_provenance"] = clean_provenance
        for field, pattern in (
            ("query_id", market_memory_pit._QUERY_ID),
            ("context_id", market_memory_pit._CONTEXT_ID),
            ("packet_sha256", market_memory_pit._SHA256),
        ):
            if not isinstance(row.get(field), str) or not pattern.fullmatch(row[field]):
                _fail(f"entry {field} is malformed")
        event_dt = _timestamp(row.get("event_time"), field="entry.event_time")
        cutoff_dt = _timestamp(row.get("as_known_at"), field="entry.as_known_at")
        if event_dt > cutoff_dt:
            _fail("entry event_time follows as_known_at")
        expected_query_id = market_memory_pit._query_id(
            {
                "subject": clean["subject"],
                "event_time": row["event_time"],
                "as_known_at": row["as_known_at"],
                "mode": "operational_pit",
            }
        )
        if row["query_id"] != expected_query_id:
            _fail("entry query_id does not bind subject and exact clocks")
        for capture in clean_provenance:
            captured_dt = _timestamp(
                capture["captured_at"],
                field="entry.capture_provenance.captured_at",
            )
            if captured_dt + timedelta(seconds=5) < cutoff_dt:
                _fail("entry captured_at precedes its cutoff")
            if captured_dt - cutoff_dt > timedelta(minutes=15):
                _fail("entry captured_at is not contemporaneous")
        states = row.get("domain_states")
        if not isinstance(states, list) or len(states) != len(
            market_memory.CANONICAL_CONTEXT_DOMAINS
        ):
            _fail("entry domain_states must cover all canonical domains")
        clean_states: list[dict[str, str]] = []
        for domain_index, state in enumerate(states):
            if not isinstance(state, Mapping) or set(state) != _DOMAIN_STATE_FIELDS:
                _fail("entry domain state fields are not canonical")
            expected_domain = market_memory.CANONICAL_CONTEXT_DOMAINS[domain_index]
            if state.get("domain") != expected_domain:
                _fail("entry domain_states are not in canonical order")
            if state.get("status") not in {
                "observed",
                "partial",
                "degraded",
                "missing",
            }:
                _fail("entry domain status is invalid")
            clean_states.append(
                {"domain": expected_domain, "status": str(state["status"])}
            )
        row["domain_states"] = clean_states
        ordering.append(
            (cutoff_dt, event_dt, str(row["query_id"]), str(row["context_id"]))
        )
        clean_entries.append(row)
    for previous, current in pairwise(ordering):
        if previous[0] < current[0]:
            _fail("entries are not ordered by descending as_known_at")
        if previous[0] == current[0] and previous[1] < current[1]:
            _fail("entries are not ordered by descending event_time")
        if previous[:2] == current[:2] and previous[2:] > current[2:]:
            _fail("entries are not ordered by ascending opaque identity")
    if len({row["query_id"] for row in clean_entries}) != len(clean_entries):
        _fail("entries contain duplicate query_id values")
    clean["entries"] = clean_entries

    if _canonical_bytes(clean.get("coverage")) != _canonical_bytes(_COVERAGE):
        _fail("playback coverage claims drift")
    if _canonical_bytes(clean.get("replay_policy")) != _canonical_bytes(_REPLAY_POLICY):
        _fail("playback policy drift")
    if _canonical_bytes(clean.get("authority")) != _canonical_bytes(
        dict(market_memory.AUTHORITY)
    ):
        _fail("playback authority drift")
    if _content_id(clean) != catalog_id:
        _fail("catalog_id does not bind the complete catalog page")
    return clean


def _measure_json(value: object, *, depth: int = 0) -> int:
    if depth > _MAX_JSON_DEPTH:
        _fail("playback catalog exceeds its JSON depth bound")
    if isinstance(value, str) and len(value.encode("utf-8")) > _MAX_STRING_BYTES:
        _fail("playback catalog string exceeds its byte bound")
    nodes = 1
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                _fail("playback catalog JSON keys must be strings")
            nodes += _measure_json(nested, depth=depth + 1)
    elif isinstance(value, list):
        for nested in value:
            nodes += _measure_json(nested, depth=depth + 1)
    if nodes > _MAX_JSON_NODES:
        _fail("playback catalog exceeds its JSON node bound")
    return nodes


def load_operational_playback_catalog_json(payload: bytes) -> dict[str, Any]:
    """Load one bounded, duplicate-free, canonical JSON catalog page."""

    if type(payload) is not bytes or not payload or len(payload) > _MAX_CATALOG_BYTES:
        _fail("playback catalog bytes are empty or exceed the safe bound")

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON token {value}")

    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_nonfinite,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise MarketMemoryPlaybackContractError(
            "playback catalog is not strict JSON"
        ) from exc
    if not isinstance(parsed, dict):
        _fail("playback catalog JSON root must be an object")
    _measure_json(parsed)
    if _canonical_bytes(parsed) != payload:
        _fail("playback catalog JSON bytes are not canonical")
    return validate_operational_playback_catalog(parsed)


def read_operational_playback_catalog(
    *,
    reader: market_memory_trusted.CompositeAsKnownAtReader,
    subject: Mapping[str, str],
    w1a_generation_id: str | None = None,
    trusted_generation_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Pin a generation pair and return one exact preparation catalog page.

    Supplying just one generation ID is forbidden.  A first page omits both and
    pins W1A then trusted HEAD; every stable continuation supplies both returned
    IDs.  Syntactically valid but unpublished IDs raise
    :class:`MarketMemoryContextNotFound`; store corruption remains
    :class:`MarketMemoryStoreError`.
    """

    if not isinstance(reader, market_memory_trusted.CompositeAsKnownAtReader):
        _fail("reader must be a CompositeAsKnownAtReader")
    clean_subject = _subject(subject)
    clean_offset, clean_limit = _pagination(offset=offset, limit=limit)
    if (w1a_generation_id is None) != (trusted_generation_id is None):
        _fail("both generation IDs must be supplied together")
    if w1a_generation_id is None and clean_offset != 0:
        _fail("an unpinned first request must use offset zero")
    w1a_generation = reader.w1a.read_pinned_generation(generation_id=w1a_generation_id)
    trusted_generation = reader.trusted.read_pinned_generation(
        generation_id=trusted_generation_id
    )
    return build_operational_playback_catalog(
        reader=reader,
        w1a_generation=w1a_generation,
        trusted_generation=trusted_generation,
        subject=clean_subject,
        offset=clean_offset,
        limit=clean_limit,
    )


__all__ = [
    "ACTUAL_OUTPUT_MODE",
    "OPERATIONAL_PLAYBACK_CATALOG_SCHEMA",
    "MarketMemoryPlaybackContractError",
    "build_operational_playback_catalog",
    "load_operational_playback_catalog_json",
    "read_operational_playback_catalog",
    "validate_operational_playback_catalog",
]
