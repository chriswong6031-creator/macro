"""Pure immutable SEC event spine for Capital Structure Intelligence.

This module is intentionally network-free.  Collectors own discovery and raw
document retention; this layer turns already-retained observations into strict
``capital_structure.event.v1`` records, immutable relationship edges, and a
rebuildable review queue.

Point-in-time law
-----------------
``point_in_time.available_at`` is always the system's keep-first observation
time.  Consequently a filing accepted in 2020 but first ingested in 2026 cannot
leak into a canonical 2020 replay.  ``current_events_as_of(..., mode="public")``
is the only explicit escape hatch: it uses the SEC acceptance time for original
source observations, while corrections remain unavailable until the system
actually produced them.

Graph law
---------
Relationships are separate immutable edge observations.  Linking a new
amendment, EFFECT, or withdrawal never writes ``superseded_by`` into an older
event.  A link is emitted only for an explicit accession or for a unique latest
candidate under exact CIK + file number + registration family + chronology.
Ambiguity is a review item, never a nearest-name guess.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


PARSER_VERSION = "capital-structure-event-spine/1.0"
EVENT_SCHEMA = "capital_structure.event.v1"
EDGE_SCHEMA = "capital_structure.event_edge.v1"
REVIEW_SCHEMA = "capital_structure.review_item.v1"

CLASSIFIED = "classified"
DEFERRED_MISSING_DOCUMENT = "deferred_missing_document"
DEFERRED_UNSUPPORTED_MEDIA = "deferred_unsupported_media"
DEFERRED_AMBIGUOUS_CONTENT = "deferred_ambiguous_content"
DEFERRED_CONFLICT = "deferred_conflict"
DEFERRED_LINKAGE = "deferred_linkage"
NOT_APPLICABLE = "not_applicable"
CLASSIFICATION_STATES = frozenset({
    CLASSIFIED,
    DEFERRED_MISSING_DOCUMENT,
    DEFERRED_UNSUPPORTED_MEDIA,
    DEFERRED_AMBIGUOUS_CONTENT,
    DEFERRED_CONFLICT,
    DEFERRED_LINKAGE,
    NOT_APPLICABLE,
})

_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ITEM_RE = re.compile(r"\d\.\d{2}")


@dataclass(frozen=True)
class FormRoute:
    """Deterministic, form-level classification result.

    ``registration_family`` is graph metadata, not an instrument family.  It is
    deliberately specific enough to prevent an S-1 amendment from attaching to
    an unrelated S-3 sharing the same SEC file number.
    """

    form: str
    family: str
    subtype: str | None
    lifecycle_state: str
    classification_state: str
    defer_reason: str | None
    registration_family: str | None
    relationship: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _route(
    form: str,
    family: str,
    subtype: str | None,
    lifecycle: str,
    state: str = CLASSIFIED,
    reason: str | None = None,
    registration_family: str | None = None,
    relationship: str | None = None,
) -> FormRoute:
    return FormRoute(
        form=form,
        family=family,
        subtype=subtype,
        lifecycle_state=lifecycle,
        classification_state=state,
        defer_reason=reason,
        registration_family=registration_family,
        relationship=relationship,
    )


def normalize_form(form: object) -> str:
    """Return the SEC form token in stable upper-case whitespace form."""
    return " ".join(str(form or "").strip().upper().split())


_REGISTRATION_ORIGINALS: dict[str, tuple[str, str]] = {
    "S-1": ("other", "registration_s1"),
    "F-1": ("other", "registration_f1"),
    "S-3": ("shelf", "registration_s3"),
    "S-3ASR": ("shelf", "registration_s3"),
    "F-3": ("shelf", "registration_f3"),
    "F-3ASR": ("shelf", "registration_f3"),
    "F-10": ("shelf", "registration_f10"),
}
_REGISTRATION_AMENDMENTS: dict[str, tuple[str, str]] = {
    "S-1/A": ("other", "registration_s1"),
    "F-1/A": ("other", "registration_f1"),
    "S-3/A": ("shelf", "registration_s3"),
    "F-3/A": ("shelf", "registration_f3"),
    "F-10/A": ("shelf", "registration_f10"),
}
_POST_EFFECTIVE_AMENDMENTS = frozenset({"POS AM", "POSASR", "1-A POS"})
_REGISTRATION_LIFECYCLE_FORMS = frozenset({
    *_REGISTRATION_ORIGINALS,
    *_REGISTRATION_AMENDMENTS,
    "1-A",
    "1-A/A",
    *_POST_EFFECTIVE_AMENDMENTS,
})
_PROSPECTUS_FORMS = frozenset({
    "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424B8",
})
_PROXY_FORMS = frozenset({
    "PRE 14A", "DEF 14A", "PRE 14C", "DEF 14C",
    "PREC14A", "DEFC14A", "PREM14A", "DEFM14A", "DEFA14A",
})
_PERIODIC_FORMS = frozenset({
    "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A",
})
_OWNERSHIP_FORMS = frozenset({
    "3", "3/A", "4", "4/A", "5", "5/A",
    "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "13F-HR", "13F-HR/A",
})


def _items(items: object) -> set[str]:
    if items is None:
        return set()
    if isinstance(items, str):
        return set(_ITEM_RE.findall(items))
    if isinstance(items, Iterable):
        return {m.group(0) for value in items for m in _ITEM_RE.finditer(str(value))}
    return set(_ITEM_RE.findall(str(items)))


def route_form(form: object, items: object = None) -> FormRoute:
    """Route a filing using form metadata only, without guessing semantics.

    Form-safe state transitions are classified directly.  Forms whose financing
    meaning depends on document content remain explicitly deferred.  This is
    especially load-bearing for 424B5, 6-K, and broad 8-K item codes.
    """
    f = normalize_form(form)
    if f in _REGISTRATION_ORIGINALS:
        family, reg_family = _REGISTRATION_ORIGINALS[f]
        subtype = "automatic_shelf_registration" if f.endswith("ASR") else "registration_statement"
        return _route(f, family, subtype, "filed", registration_family=reg_family)
    if f in _REGISTRATION_AMENDMENTS:
        family, reg_family = _REGISTRATION_AMENDMENTS[f]
        return _route(
            f, family, "registration_amendment", "amended",
            registration_family=reg_family, relationship="amendment_of",
        )
    if f in {"POS AM", "POSASR"}:
        return _route(
            f, "other", "post_effective_amendment", "amended",
            relationship="amendment_of",
        )
    if f == "EFFECT":
        return _route(
            f, "other", "effectiveness_notice", "effective",
            relationship="effectuates",
        )
    if f in {"RW", "RW/A", "AW", "AW/A"}:
        subtype = "automatic_shelf_withdrawal" if f.startswith("AW") else "withdrawal_request"
        return _route(
            f, "other", subtype, "withdrawn",
            relationship="withdraws",
        )
    if f in _PROSPECTUS_FORMS:
        return _route(
            f, "other", "prospectus_event", "filed",
            DEFERRED_AMBIGUOUS_CONTENT,
            "prospectus_requires_content_to_distinguish_pricing_atm_resale_or_rights",
        )
    if f in {"8-K", "8-K/A", "6-K", "6-K/A"}:
        codes = _items(items)
        if "5.03" in codes or "5.07" in codes:
            subtype = "charter_amendment_candidate" if "5.03" in codes else "shareholder_vote_candidate"
            family = "corporate_action"
        elif "3.02" in codes:
            subtype, family = "unregistered_equity_sale_candidate", "other"
        elif codes & {"1.01", "1.02", "2.03", "2.04"}:
            subtype, family = "financing_agreement_candidate", "other"
        else:
            subtype, family = "current_report_candidate", "other"
        return _route(
            f, family, subtype, "filed",
            DEFERRED_AMBIGUOUS_CONTENT, "current_report_requires_document_content",
        )
    if f in _PROXY_FORMS:
        return _route(
            f, "corporate_action", "authorization_or_vote_candidate", "filed",
            DEFERRED_AMBIGUOUS_CONTENT, "proxy_requires_content_and_vote_result",
        )
    if f == "1-A":
        return _route(f, "reg_a", "offering_statement", "filed", registration_family="registration_reg_a")
    if f in {"1-A/A", "1-A POS"}:
        return _route(
            f, "reg_a", "offering_statement_amendment", "amended",
            registration_family="registration_reg_a", relationship="amendment_of",
        )
    if f in {"1-U", "253G1", "253G2", "253G3", "253G4"}:
        return _route(
            f, "reg_a", "reg_a_event_candidate", "filed",
            DEFERRED_AMBIGUOUS_CONTENT, "reg_a_event_requires_document_content",
        )
    if f in {"1-K", "1-K/A"}:
        return _route(f, "reg_a", "periodic_reconciliation_source", "unknown", NOT_APPLICABLE,
                      "periodic_source_is_not_a_wave1_semantic_event")
    if f in _PERIODIC_FORMS:
        return _route(f, "other", "periodic_reconciliation_source", "unknown", NOT_APPLICABLE,
                      "periodic_source_is_not_a_wave1_semantic_event")
    if f in _OWNERSHIP_FORMS:
        return _route(f, "other", "ownership_context_source", "unknown", NOT_APPLICABLE,
                      "ownership_context_has_an_existing_authoritative_lane")
    return _route(f, "other", "unsupported_form", "unknown", NOT_APPLICABLE,
                  "form_not_in_wave1_policy")


def make_stable_span(
    manifest_id: str,
    text: str | bytes,
    *,
    locator_type: str = "text_range",
    locator: str,
) -> dict[str, str]:
    """Build a stable evidence span from exact source bytes and a locator.

    The text hash is over the exact supplied UTF-8 bytes; callers must not pass a
    normalized paraphrase.  ``span_id`` binds the manifest, locator, and text hash,
    so changing any coordinate creates a new observation instead of silently
    moving old evidence.
    """
    if not manifest_id or not locator:
        raise ValueError("manifest_id and locator are required")
    if locator_type not in {"document", "page", "table", "dom", "text_range"}:
        raise ValueError(f"unsupported locator_type: {locator_type!r}")
    raw = text if isinstance(text, bytes) else str(text).encode("utf-8")
    text_hash = hashlib.sha256(raw).hexdigest()
    identity = f"{manifest_id}\0{locator_type}\0{locator}\0{text_hash}".encode("utf-8")
    span_id = "span:cs:" + hashlib.sha256(identity).hexdigest()[:24]
    return {
        "manifest_id": str(manifest_id),
        "span_id": span_id,
        "locator_type": locator_type,
        "locator": str(locator),
        "text_sha256": text_hash,
    }


def evidence_from_span(span: Mapping[str, Any]) -> dict[str, str]:
    """Project a full source-manifest span into the strict event evidence shape."""
    required = ("manifest_id", "span_id", "text_sha256")
    if any(not span.get(key) for key in required):
        raise ValueError("span requires manifest_id, span_id, and text_sha256")
    digest = str(span["text_sha256"])
    if not _HASH_RE.fullmatch(digest):
        raise ValueError("span text_sha256 must be a 64-character hexadecimal digest")
    return {key: str(span[key]) for key in required}


def _parse_time(value: object, field: str, *, nullable: bool = False) -> datetime | None:
    if value is None or str(value).strip() == "":
        if nullable:
            return None
        raise ValueError(f"{field} is required")
    raw = str(value).strip()
    try:
        dt = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {raw!r}") from exc
    if dt.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return dt.astimezone(timezone.utc)


def _iso(value: object, field: str, *, nullable: bool = False) -> str | None:
    dt = _parse_time(value, field, nullable=nullable)
    return None if dt is None else dt.isoformat().replace("+00:00", "Z")


def _date(value: object, field: str) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD: {raw!r}") from exc
    return raw


def _unique_strings(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    return sorted({str(value) for value in values if value is not None and str(value)})


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build_event_version(
    observation: Mapping[str, Any],
    spans: Sequence[Mapping[str, Any]],
    *,
    correction_version: int = 1,
    correction_of: str | None = None,
    parser_version: str = PARSER_VERSION,
) -> dict[str, Any]:
    """Build one strict, deterministic, immutable event-version document.

    ``observation`` is collector/compiler metadata and may contain graph-only
    fields such as ``file_number``; only contract fields enter the returned JSON.
    A new correction is a new record and may point backward via ``correction_of``.
    No older record is mutated.
    """
    if not spans:
        raise ValueError("at least one stable evidence span is required")
    if correction_version < 1:
        raise ValueError("correction_version must be >= 1")
    if correction_version > 1 and not correction_of:
        raise ValueError("correction_of is required for correction_version > 1")

    accession = observation.get("accession")
    source_system = str(observation.get("source_system") or "sec_edgar")
    source_id = str(observation.get("source_id") or accession or "")
    manifest_ids = _unique_strings(observation.get("manifest_ids"))
    if observation.get("manifest_id"):
        manifest_ids.append(str(observation["manifest_id"]))
    manifest_ids.extend(str(span.get("manifest_id")) for span in spans if span.get("manifest_id"))
    manifest_ids = sorted(set(manifest_ids))
    if not source_id or not manifest_ids:
        raise ValueError("source_id/accession and at least one manifest_id are required")

    route = route_form(observation.get("form"), observation.get("items"))
    classification_state = str(observation.get("classification_state") or route.classification_state)
    if classification_state not in CLASSIFICATION_STATES:
        raise ValueError(f"unsupported classification_state: {classification_state!r}")
    defer_reason_raw = observation.get("defer_reason", route.defer_reason)
    defer_reason = str(defer_reason_raw).strip() if defer_reason_raw is not None else None
    if classification_state.startswith("deferred_") and not defer_reason:
        raise ValueError("deferred classification requires defer_reason")
    if not classification_state.startswith("deferred_"):
        defer_reason = None
    first_seen = _iso(observation.get("first_seen_at"), "first_seen_at")
    accepted = _iso(observation.get("accepted_at"), "accepted_at", nullable=True)
    cik_raw = observation.get("cik")
    cik = str(cik_raw).lstrip("0") or "0" if cik_raw is not None and str(cik_raw) else None
    issuer_id = str(observation.get("issuer_id") or (f"issuer:{str(cik_raw).zfill(10)}" if cik_raw else ""))
    if not issuer_id:
        raise ValueError("issuer_id or cik is required")
    ticker_raw = observation.get("ticker")
    ticker = str(ticker_raw).upper() if ticker_raw is not None and str(ticker_raw) else None

    hashes = _unique_strings(observation.get("content_hashes") or observation.get("content_sha256"))
    if any(not _HASH_RE.fullmatch(value) for value in hashes):
        raise ValueError("all content_hashes must be 64-character hexadecimal digests")
    evidence = [evidence_from_span(span) for span in spans]
    # Stable dedup without losing source order.
    evidence = list({item["span_id"]: item for item in evidence}.values())

    deferred = classification_state.startswith("deferred_")
    event: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "event_id": "",  # filled after the immutable body is complete
        "source": {
            "source_system": source_system,
            "source_id": source_id,
            "manifest_ids": manifest_ids,
        },
        "issuer": {
            "issuer_id": issuer_id,
            "cik": cik,
            "ticker": ticker,
            "aliases": _unique_strings(observation.get("aliases")),
        },
        "filing": {
            "accession": str(accession) if accession else None,
            "form": route.form or None,
            "file_number": str(observation.get("file_number")) if observation.get("file_number") else None,
            "filing_date": _date(observation.get("filing_date"), "filing_date"),
            "accepted_at": accepted,
            "primary_document_url": observation.get("primary_document_url") or None,
            "exhibit_urls": _unique_strings(observation.get("exhibit_urls")),
            "content_hashes": hashes,
        },
        "event": {
            "family": route.family,
            "subtype": route.subtype,
            "affected_instrument_candidate_ids": _unique_strings(
                observation.get("affected_instrument_candidate_ids")
            ),
        },
        "lifecycle": {"state": route.lifecycle_state},
        "relationships": {
            "amendment_of": None,
            "supersedes": [str(correction_of)] if correction_of else [],
        },
        "classification": {
            "state": classification_state,
            "defer_reason": defer_reason,
        },
        "evidence": evidence,
        "extraction": {
            "method": "deferred" if deferred else "deterministic",
            "parser_version": parser_version,
            "review_status": "deferred" if deferred else "unreviewed",
        },
        "reconciliation": {
            "state": "deferred" if deferred else "unreconciled",
            "contradiction_ids": [],
        },
        "version": {
            "immutable_record": True,
            "correction_version": int(correction_version),
            "correction_of": str(correction_of) if correction_of else None,
        },
        "point_in_time": {
            "first_seen_at": first_seen,
            "public_available_at": accepted,
            "system_available_at": first_seen,
            "available_at": first_seen,
        },
        "authority": {
            "is_context_only": True,
            "rank_authority": False,
            "sizing_authority": False,
            "entry_authority": False,
            "prophet_authority": False,
        },
    }
    identity_body = copy.deepcopy(event)
    identity_body.pop("event_id")
    event["event_id"] = "event:cs:" + hashlib.sha256(_canonical_json(identity_body)).hexdigest()[:24]
    return event


def append_event_versions_strict(
    existing: Sequence[Mapping[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Pure append with idempotency and collision detection.

    An identical event ID may be replayed.  The same ID with different bytes is a
    hard integrity error; keep-first must never silently hide such corruption.
    """
    out: list[dict[str, Any]] = []
    by_id: dict[str, bytes] = {}
    for raw in [*existing, *incoming]:
        row = copy.deepcopy(dict(raw))
        event_id = str(row.get("event_id") or "")
        if not event_id:
            raise ValueError("every event version requires event_id")
        encoded = _canonical_json(row)
        prior = by_id.get(event_id)
        if prior is not None:
            if prior != encoded:
                raise ValueError(f"immutable event collision for {event_id}")
            continue
        by_id[event_id] = encoded
        out.append(row)
    return out


def event_classification(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return explicit classification/defer metadata for a strict event record."""
    filing = event.get("filing") or {}
    route = route_form(filing.get("form"), event.get("items"))
    embedded = event.get("classification") or {}
    return {
        "classification_state": embedded.get("state") or route.classification_state,
        "defer_reason": embedded.get("defer_reason") if "defer_reason" in embedded else route.defer_reason,
        "registration_family": route.registration_family,
        "relationship": route.relationship,
    }


def _event_time(event: Mapping[str, Any], *, mode: str) -> datetime | None:
    if mode == "system":
        return _parse_time((event.get("point_in_time") or {}).get("available_at"), "available_at")
    if mode != "public":
        raise ValueError("mode must be 'system' or 'public'")
    public_at = _parse_time(
        (event.get("point_in_time") or {}).get("public_available_at"),
        "public_available_at",
        nullable=True,
    )
    if public_at is None:
        return None
    version = event.get("version") or {}
    if int(version.get("correction_version") or 1) > 1:
        system_time = _parse_time((event.get("point_in_time") or {}).get("available_at"), "available_at")
        return max(public_at, system_time)  # a parser correction cannot travel back to filing time
    return public_at


def _logical_key(event: Mapping[str, Any]) -> tuple[str, str]:
    source = event.get("source") or {}
    filing = event.get("filing") or {}
    return str(source.get("source_system") or ""), str(filing.get("accession") or source.get("source_id") or "")


def current_events_as_of(
    events: Sequence[Mapping[str, Any]],
    as_of: str | datetime,
    *,
    mode: str = "system",
) -> list[dict[str, Any]]:
    """Return the latest immutable version of each logical event visible at ``as_of``.

    ``mode='system'`` is canonical.  ``mode='public'`` is an explicit historical
    research view based on SEC acceptance time; records lacking that clock are
    excluded rather than guessed from filing date.
    """
    cutoff = _parse_time(as_of, "as_of")
    chosen: dict[tuple[str, str], tuple[int, datetime, str, dict[str, Any]]] = {}
    for raw in events:
        event = copy.deepcopy(dict(raw))
        when = _event_time(event, mode=mode)
        if when is None or when > cutoff:
            continue
        version = int((event.get("version") or {}).get("correction_version") or 1)
        rank = (version, when, str(event.get("event_id") or ""), event)
        key = _logical_key(event)
        if key not in chosen or rank[:3] > chosen[key][:3]:
            chosen[key] = rank
    return [chosen[key][3] for key in sorted(chosen)]


def _linkage_meta(
    event: Mapping[str, Any],
    linkage_by_event_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    meta = dict(linkage_by_event_id.get(str(event.get("event_id") or ""), {}) or {})
    route = route_form((event.get("filing") or {}).get("form"))
    meta.setdefault("file_number", (event.get("filing") or {}).get("file_number"))
    meta.setdefault("registration_family", route.registration_family)
    return meta


def _filing_chronology_time(event: Mapping[str, Any]) -> datetime | None:
    """Return the public filing clock used only for causal graph ordering.

    SEC acceptance time, not our ingestion clock, orders filings inside a
    registration lifecycle.  Missing acceptance clocks are never guessed from
    filing dates or accession numbers.  The system clock still controls whether
    a version was available when an edge observation was produced.
    """
    return _parse_time(
        (event.get("filing") or {}).get("accepted_at"),
        "accepted_at",
        nullable=True,
    )


def _candidate_versions(
    candidates: Sequence[Mapping[str, Any]],
    child: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Collapse visible prior filings to one current version per accession.

    Same-run backfills commonly share one system ``first_seen_at``.  They remain
    linkable because causal chronology uses distinct SEC acceptance timestamps.
    A publicly earlier parent retained after its child is also linkable, but the
    edge becomes available only at the later evidence-retention clock; it never
    leaks into a replay before the parent reached the system.
    """
    child_public = _filing_chronology_time(child)
    if child_public is None or _event_time(child, mode="system") is None:
        return []
    visible = []
    for event in candidates:
        parent_public = _filing_chronology_time(event)
        parent_system = _event_time(event, mode="system")
        if parent_public is None or parent_system is None:
            continue
        if parent_public < child_public:
            visible.append(event)
    grouped: dict[tuple[str, str], Mapping[str, Any]] = {}
    for event in visible:
        key = _logical_key(event)
        prior = grouped.get(key)
        if prior is None:
            grouped[key] = event
            continue
        cur_rank = (
            int((event.get("version") or {}).get("correction_version") or 1),
            _event_time(event, mode="system"),
            str(event.get("event_id") or ""),
        )
        old_rank = (
            int((prior.get("version") or {}).get("correction_version") or 1),
            _event_time(prior, mode="system"),
            str(prior.get("event_id") or ""),
        )
        if cur_rank > old_rank:
            grouped[key] = event
    return list(grouped.values())


def _edge(child: Mapping[str, Any], parent: Mapping[str, Any], relationship: str, method: str) -> dict[str, Any]:
    child_available = _event_time(child, mode="system")
    parent_available = _event_time(parent, mode="system")
    if child_available is None or parent_available is None:
        raise ValueError("registration edge endpoints require system availability clocks")
    observed_at = max(child_available, parent_available).isoformat().replace("+00:00", "Z")
    body = {
        "schema": EDGE_SCHEMA,
        "from_event_id": str(child["event_id"]),
        "to_event_id": str(parent["event_id"]),
        "relationship": relationship,
        "link_method": method,
        "observed_at": observed_at,
        "immutable_record": True,
    }
    body["edge_id"] = "edge:cs:" + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]
    return body


def _is_registration_lifecycle_parent(event: Mapping[str, Any]) -> bool:
    """Return whether ``event`` can be the target of a registration-state edge.

    File number and inferred registration family are not enough: prospectuses
    commonly share both with the shelf they use.  Only registration statements
    and their pre/post-effective amendments are lifecycle nodes.  EFFECT,
    withdrawal, and prospectus observations can never become amendment,
    effectiveness, or withdrawal targets merely because they are newer.
    """
    return normalize_form((event.get("filing") or {}).get("form")) in _REGISTRATION_LIFECYCLE_FORMS


def link_registration_graph(
    events: Sequence[Mapping[str, Any]],
    linkage_by_event_id: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    existing_edges: Sequence[Mapping[str, Any]] = (),
) -> dict[str, list[dict[str, Any]]]:
    """Build immutable registration edges without modifying event records.

    Linkage metadata is separate because the strict Wave-0 event schema does not
    own SEC file-number mechanics.  Supported fields per event are
    ``explicit_accession``, ``file_number``, and ``registration_family``.
    Once an immutable child version has a lifecycle edge, that edge is locked.
    A later correction to its parent is reached through ``supersedes`` edges and
    cannot silently retarget the already-published child relationship. A later
    correction to the child is a new event version and may receive its own edge.
    """
    linkage = linkage_by_event_id or {}
    event_copies = [copy.deepcopy(dict(event)) for event in events]
    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    locked_lifecycle: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_edge in existing_edges:
        relationship = str(raw_edge.get("relationship") or "")
        if relationship not in {"amendment_of", "effectuates", "withdraws"}:
            continue
        key = (str(raw_edge.get("from_event_id") or ""), relationship)
        prior = locked_lifecycle.get(key)
        edge_copy = copy.deepcopy(dict(raw_edge))
        if prior is not None and _canonical_json(prior) != _canonical_json(edge_copy):
            raise ValueError(
                f"immutable child relationship has multiple lifecycle targets: {key}"
            )
        locked_lifecycle[key] = edge_copy

    # Correction links are exact by event ID and require no filing inference.
    by_id = {str(event.get("event_id") or ""): event for event in event_copies}
    for child in event_copies:
        correction_of = (child.get("version") or {}).get("correction_of")
        if correction_of and str(correction_of) in by_id:
            edges.append(_edge(child, by_id[str(correction_of)], "supersedes", "explicit_event_id"))

    for child in event_copies:
        route = route_form((child.get("filing") or {}).get("form"))
        relationship = route.relationship
        if relationship is None:
            continue
        child_id = str(child.get("event_id") or "")
        locked = locked_lifecycle.get((child_id, relationship))
        if locked is not None:
            edges.append(locked)
            continue
        child_meta = _linkage_meta(child, linkage)
        cik = str((child.get("issuer") or {}).get("cik") or "")
        prior = _candidate_versions(event_copies, child)
        explicit = str(child_meta.get("explicit_accession") or "").strip()

        if explicit:
            candidates = [
                event for event in prior
                if str((event.get("filing") or {}).get("accession") or "") == explicit
                and _is_registration_lifecycle_parent(event)
                and (not cik or not str((event.get("issuer") or {}).get("cik") or "")
                     or str((event.get("issuer") or {}).get("cik") or "") == cik)
            ]
            method = "explicit_accession"
        else:
            file_number = str(child_meta.get("file_number") or "").strip()
            reg_family = str(child_meta.get("registration_family") or "").strip()
            if not (cik and file_number and reg_family):
                unresolved.append({
                    "event_id": child_id,
                    "classification_state": DEFERRED_LINKAGE,
                    "defer_reason": "missing_exact_linkage_keys",
                    "candidate_event_ids": [],
                })
                continue
            candidates = []
            for event in prior:
                event_meta = _linkage_meta(event, linkage)
                if str((event.get("issuer") or {}).get("cik") or "") != cik:
                    continue
                if str(event_meta.get("file_number") or "").strip() != file_number:
                    continue
                if str(event_meta.get("registration_family") or "").strip() != reg_family:
                    continue
                if not _is_registration_lifecycle_parent(event):
                    continue
                candidates.append(event)
            method = "exact_cik_file_number_family_chronology"

        # Chronology is part of the exact key: choose the unique latest prior
        # SEC acceptance observation. Equal or absent public clocks stay
        # deferred, even when the system observed the records in one batch.
        if candidates:
            latest_time = max(_filing_chronology_time(event) for event in candidates)
            latest = [
                event for event in candidates
                if _filing_chronology_time(event) == latest_time
            ]
        else:
            latest = []
        if len(latest) != 1:
            unresolved.append({
                "event_id": child_id,
                "classification_state": DEFERRED_LINKAGE,
                "defer_reason": "no_unique_link_target" if not latest else "ambiguous_link_target",
                "candidate_event_ids": sorted(str(event.get("event_id") or "") for event in latest),
            })
            continue
        edges.append(_edge(child, latest[0], relationship, method))

    dedup = {edge["edge_id"]: edge for edge in edges}
    return {
        "edges": [dedup[key] for key in sorted(dedup)],
        "unresolved": sorted(unresolved, key=lambda row: row["event_id"]),
    }


def build_review_queue(
    events: Sequence[Mapping[str, Any]],
    unresolved_links: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    *,
    resolved_edges: Sequence[Mapping[str, Any]] | None = None,
    as_of: str | datetime | None = None,
) -> list[dict[str, Any]]:
    """Materialize the current deterministic defer queue.

    This queue is rebuildable and does not mutate event truth.  Linkage failures
    take precedence over form-level defer reasons because they identify the next
    concrete review action.
    """
    current = (
        current_events_as_of(events, as_of, mode="system")
        if as_of is not None else current_events_as_of(events, "9999-12-31T23:59:59Z", mode="system")
    )
    if isinstance(unresolved_links, Mapping):
        graph = unresolved_links
        unresolved_rows = graph.get("unresolved") or []
        if resolved_edges is None:
            resolved_edges = graph.get("edges") or []
    else:
        unresolved_rows = unresolved_links or []
    unresolved = {str(row.get("event_id") or ""): dict(row) for row in unresolved_rows}
    resolved_relationships = {
        (str(edge.get("from_event_id") or ""), str(edge.get("relationship") or ""))
        for edge in (resolved_edges or [])
    }
    out: list[dict[str, Any]] = []
    for event in current:
        event_id = str(event.get("event_id") or "")
        route = route_form((event.get("filing") or {}).get("form"))
        embedded = event.get("classification") or {}
        link_issue = unresolved.get(event_id)
        state = str(
            (link_issue or {}).get("classification_state")
            or embedded.get("state")
            or route.classification_state
        )
        reason = (
            (link_issue or {}).get("defer_reason")
            or embedded.get("defer_reason")
            or route.defer_reason
        )
        if (
            state == DEFERRED_LINKAGE
            and route.relationship
            and (event_id, route.relationship) in resolved_relationships
            and link_issue is None
        ):
            continue
        if not state.startswith("deferred_"):
            continue
        body = {
            "schema": REVIEW_SCHEMA,
            "event_id": event_id,
            "accession": (event.get("filing") or {}).get("accession"),
            "issuer_id": (event.get("issuer") or {}).get("issuer_id"),
            "form": (event.get("filing") or {}).get("form"),
            "classification_state": state,
            "defer_reason": reason,
            "candidate_event_ids": sorted((link_issue or {}).get("candidate_event_ids") or []),
            "source_manifest_ids": sorted((event.get("source") or {}).get("manifest_ids") or []),
            "first_queued_at": (event.get("point_in_time") or {}).get("available_at"),
            "review_state": "pending",
            "immutable_source": True,
        }
        body["queue_id"] = "review:cs:" + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]
        out.append(body)
    return sorted(out, key=lambda row: (str(row["first_queued_at"]), row["event_id"]))
