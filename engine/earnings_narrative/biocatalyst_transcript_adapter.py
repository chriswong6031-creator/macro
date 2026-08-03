"""Private, transcript-only evidence adapter for the BioCatalyst plane.

This is deliberately a *reader wrapper*, not a second transcript store.  It
uses the already integrity-checked earnings context reader once, projects only
receipt-bound transcript spans, and never performs issuer, security, sponsor,
asset, or trial resolution.  Its output remains source/context evidence: it
cannot originate, rank, gate, or alter any signal.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from hashlib import sha256
import re
from pathlib import Path
from typing import Any, Mapping

from engine.earnings_narrative.public_wire import (
    PublicWireContractError,
    verify_public_wire_fact_projection,
)
from engine.sector_intelligence.contracts import canonical_json_sha256


READ_CONTRACT_ID = "earnings_transcript_span_read.v1"
BUNDLE_CONTRACT_ID = "biocatalyst_transcript_context_bundle.v1"
SELECTION_SCOPE = "latest_selected_context_packet_in_receipted_generation_only"
LEXICAL_METHOD = "deterministic_transcript_lexical_candidate.v1"
MAX_SPANS = 48
MAX_CANDIDATES = 192

_INTEGRITY_SCOPE = {
    "validation": "self_consistent_receipt_bound_projection",
    "source_authenticity": "trusted_upstream_reader_required_not_independently_attested",
    "authorized_transport": "private_in_process_only",
    "persistence_authorized": False,
}

_TICKER = re.compile(r"^[A-Z0-9.\-]{1,16}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_AS_OF_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SOURCE_AUTHORITY = {
    "classification": "source_fact",
    "decision_authority": False,
    "maximum_authority": "A1_EXPLAIN",
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "issuer_resolution",
        "security_resolution",
        "sponsor_resolution",
        "trial_resolution",
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
_CANDIDATE_AUTHORITY = {
    "classification": "semantic_candidate",
    "decision_authority": False,
    "maximum_authority": "A1_EXPLAIN",
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "issuer_resolution",
        "security_resolution",
        "sponsor_resolution",
        "trial_resolution",
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
_BUNDLE_AUTHORITY = {
    "classification": "context_bundle",
    "decision_authority": False,
    "maximum_authority": "A1_EXPLAIN",
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "issuer_resolution",
        "security_resolution",
        "sponsor_resolution",
        "trial_resolution",
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

# Terms are deliberately a small, explainable allowlist.  A hit is only a
# lexical review cue, never an assertion that a program, catalyst, partner, or
# financing event exists.
_MENTION_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "clinical_trial_mention",
        ("clinical trial", "phase 1", "phase 2", "phase 3", "phase i", "phase ii", "phase iii", "endpoint", "enrollment"),
    ),
    (
        "regulatory_mention",
        ("fda", "pdufa", "nda", "bla", "ind", "advisory committee", "approval"),
    ),
    (
        "partnering_mention",
        ("collaboration", "license agreement", "licensing", "partner", "royalty", "milestone payment", "upfront payment"),
    ),
    (
        "financing_mention",
        ("financing", "offering", "atm", "cash runway"),
    ),
)
_MENTION_PATTERNS = {
    term: re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", re.IGNORECASE)
    for _mention_class, terms in _MENTION_TERMS
    for term in terms
}


class BioCatalystTranscriptAdapterError(ValueError):
    """The narrow adapter cannot safely project the upstream context."""


def _read_earnings_evidence(params: Mapping[str, Any], *, root: Path | None) -> dict[str, Any]:
    """Load the single canonical reader lazily, keeping this module non-serving."""
    from engine.neuralweb.earnings_context_reader import read_earnings_evidence

    return read_earnings_evidence(params, root=root)


def _canonical_as_of(value: object) -> str | None:
    """Normalize accepted PIT inputs without expanding the upstream contract."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise BioCatalystTranscriptAdapterError("invalid_as_of")
    raw = value.strip()
    try:
        if _AS_OF_DATE.fullmatch(raw):
            return date.fromisoformat(raw).isoformat()
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BioCatalystTranscriptAdapterError("invalid_as_of") from exc
    if parsed.tzinfo is None:
        raise BioCatalystTranscriptAdapterError("invalid_as_of")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unavailable_reason(reader: Mapping[str, Any]) -> str:
    note = str(reader.get("note") or "").casefold()
    if "invalid ticker" in note:
        return "invalid_ticker"
    if "not covered" in note:
        return "ticker_not_covered"
    if "point-in-time" in note:
        return "no_evidence_known_at_as_of"
    return "integrity_failure"


def _empty_coverage() -> dict[str, Any]:
    return {
        "document_classes": {
            "release": "unavailable",
            "filing": "unavailable",
            "transcript": "unavailable",
            "slides": "unavailable",
            "consensus": "unavailable",
        },
        "history_scope": "latest_selected_context_packet_only",
        "absence_conclusion": False,
    }


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + canonical_json_sha256(payload)[:24]


def _span_id(document_revision_id: str, span: Mapping[str, Any]) -> str:
    return _stable_id(
        "earnings_transcript_span_",
        {
            "document_revision_id": document_revision_id,
            "claim_id": span.get("claim_id"),
            "kind": span.get("kind"),
            "text_sha256": span.get("text_sha256"),
            "receipt": span.get("receipt"),
        },
    )


def _read_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    document = payload.get("document")
    generation = payload.get("generation")
    spans = payload.get("spans")
    return {
        "query": payload.get("query"),
        "available": payload.get("available"),
        "unavailable_reason": payload.get("unavailable_reason"),
        "document_revision_id": (
            document.get("document_revision_id") if isinstance(document, Mapping) else None
        ),
        "generation": generation,
        "span_ids": [span.get("span_id") for span in spans] if isinstance(spans, list) else [],
    }


def _with_read_identity_and_hash(payload: dict[str, Any]) -> dict[str, Any]:
    query = payload.get("query")
    ticker = query.get("ticker") if isinstance(query, Mapping) else None
    prefix_ticker = ticker if isinstance(ticker, str) else "unavailable"
    payload["read_id"] = _stable_id(
        f"earnings_transcript_span_read_{prefix_ticker}_", _read_identity(payload)
    )
    payload["read_payload_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"read_id", "read_payload_sha256"}
        }
    )
    return payload


def _finish_read(payload: dict[str, Any]) -> dict[str, Any]:
    result = _with_read_identity_and_hash(payload)
    validate_transcript_span_read(result)
    return result


def _base_payload(*, ticker: str | None, as_of: str | None) -> dict[str, Any]:
    return {
        "contract_id": READ_CONTRACT_ID,
        "schema_version": "1.0.0",
        "query": {
            "ticker": ticker,
            "as_of": as_of,
            "selection_scope": SELECTION_SCOPE,
        },
        "available": False,
        "unavailable_reason": "integrity_failure",
        "coverage": _empty_coverage(),
        "document": None,
        "generation": None,
        "span_count": 0,
        "spans": [],
        "integrity_scope": dict(_INTEGRITY_SCOPE),
        "authority": dict(_SOURCE_AUTHORITY),
        "hash_scope": "canonical_payload_excluding_read_id_and_read_payload_sha256",
    }


def _fact_spans(reader: Mapping[str, Any], *, document_revision_id: str) -> list[dict[str, Any]]:
    receipts = reader.get("receipts")
    if not isinstance(receipts, Mapping):
        raise BioCatalystTranscriptAdapterError("missing_receipts")
    source_sha256 = receipts.get("source_sha256")
    if not isinstance(source_sha256, str) or not _SHA256.fullmatch(source_sha256):
        raise BioCatalystTranscriptAdapterError("invalid_source_receipt")
    facts = reader.get("facts")
    try:
        verify_public_wire_fact_projection(facts, source_sha256=source_sha256, max_facts=6)
    except PublicWireContractError as exc:
        raise BioCatalystTranscriptAdapterError("invalid_exact_fact_projection") from exc

    spans: list[dict[str, Any]] = []
    for fact in facts:
        if not isinstance(fact, Mapping):
            raise BioCatalystTranscriptAdapterError("invalid_exact_fact_projection")
        raw_spans = [fact.get("quote"), *(fact.get("numeric") or [])]
        for raw_span in raw_spans:
            if not isinstance(raw_span, Mapping):
                raise BioCatalystTranscriptAdapterError("invalid_exact_fact_projection")
            receipt = raw_span.get("receipt")
            text = raw_span.get("text")
            text_sha256 = receipt.get("text_sha256") if isinstance(receipt, Mapping) else None
            if (
                not isinstance(text, str)
                or not isinstance(text_sha256, str)
                or sha256(text.encode("utf-8")).hexdigest() != text_sha256
            ):
                raise BioCatalystTranscriptAdapterError("invalid_exact_span")
            coordinates = (
                receipt.get("span_start_byte"),
                receipt.get("span_end_byte"),
                receipt.get("segment_bytes"),
            )
            if (
                any(isinstance(value, bool) or not isinstance(value, int) for value in coordinates)
                or not (0 <= coordinates[0] < coordinates[1] <= coordinates[2])
                or coordinates[1] - coordinates[0] != len(text.encode("utf-8"))
            ):
                raise BioCatalystTranscriptAdapterError("invalid_exact_span_coordinates")
            span = {
                "claim_id": raw_span.get("claim_id"),
                "kind": raw_span.get("kind"),
                "text": text,
                "text_sha256": text_sha256,
                "receipt": dict(receipt),
            }
            span["span_id"] = _span_id(document_revision_id, span)
            spans.append(span)
    spans.sort(
        key=lambda item: (
            int(item["receipt"]["segment_index"]),
            int(item["receipt"]["span_start_byte"]),
            str(item["claim_id"]),
            str(item["kind"]),
        )
    )
    if not spans or len(spans) > MAX_SPANS or len({span["span_id"] for span in spans}) != len(spans):
        raise BioCatalystTranscriptAdapterError("span_capacity_or_identity_failure")
    return spans


def read_earnings_transcript_spans(
    params: Mapping[str, Any], *, root: Path | None = None
) -> dict[str, Any]:
    """Project one caller-supplied ticker into bounded exact transcript spans.

    ``root`` exists only for the existing reader's controlled replay fixture.
    It does not designate a new store, and this function performs exactly one
    upstream reader call on valid input.
    """
    raw_ticker = str(params.get("ticker") or "").strip().upper()
    ticker = raw_ticker if _TICKER.fullmatch(raw_ticker) else None
    try:
        as_of = _canonical_as_of(params.get("as_of", params.get("asof")))
    except BioCatalystTranscriptAdapterError:
        payload = _base_payload(ticker=ticker, as_of=None)
        payload["unavailable_reason"] = "invalid_as_of"
        return _finish_read(payload)
    if ticker is None:
        payload = _base_payload(ticker=None, as_of=as_of)
        payload["unavailable_reason"] = "invalid_ticker"
        return _finish_read(payload)

    reader = _read_earnings_evidence({"ticker": ticker, "as_of": as_of}, root=root)
    if not isinstance(reader, Mapping) or reader.get("available") is not True:
        payload = _base_payload(ticker=ticker, as_of=as_of)
        payload["unavailable_reason"] = _unavailable_reason(reader) if isinstance(reader, Mapping) else "integrity_failure"
        return _finish_read(payload)

    try:
        event = reader.get("event")
        receipts = reader.get("receipts")
        completeness = reader.get("source_completeness")
        if not isinstance(event, Mapping) or not isinstance(receipts, Mapping) or not isinstance(completeness, Mapping):
            raise BioCatalystTranscriptAdapterError("reader_shape")
        source_sha256 = receipts.get("source_sha256")
        known_at = receipts.get("known_at")
        correction_status = receipts.get("correction_status")
        if (
            event.get("ticker") != ticker
            or not isinstance(event.get("transcript_id"), str)
            or not isinstance(event.get("period"), str)
            or not isinstance(event.get("date"), str)
            or not isinstance(source_sha256, str)
            or not _SHA256.fullmatch(source_sha256)
            or not isinstance(known_at, str)
            or correction_status not in {"current", "corrected"}
        ):
            raise BioCatalystTranscriptAdapterError("reader_identity")
        document_id = _stable_id(
            "earnings_transcript_",
            {"ticker": ticker, "transcript_id": event["transcript_id"], "period": event["period"]},
        )
        document_revision_id = _stable_id(
            "earnings_transcript_revision_",
            {
                "document_id": document_id,
                "source_sha256": source_sha256,
                "known_at": known_at,
                "correction_status": correction_status,
            },
        )
        document = {
            "document_id": document_id,
            "document_revision_id": document_revision_id,
            "source_kind": "transcript",
            "ticker": ticker,
            "transcript_id": event["transcript_id"],
            "period": event["period"],
            "event_date": event["date"],
            "known_at": known_at,
            "correction_status": correction_status,
            "source_sha256": source_sha256,
        }
        spans = _fact_spans(reader, document_revision_id=document_revision_id)
        payload = _base_payload(ticker=ticker, as_of=as_of)
        payload.update(
            {
                "available": True,
                "unavailable_reason": None,
                "coverage": {
                    "document_classes": dict(completeness),
                    "history_scope": "latest_selected_context_packet_only",
                    "absence_conclusion": False,
                },
                "document": document,
                "generation": {
                    "generation_id": reader.get("generation_id"),
                    "knowledge_cutoff": reader.get("knowledge_cutoff"),
                    "context_id": receipts.get("context_id"),
                    "context_object_sha256": receipts.get("object_sha256"),
                },
                "span_count": len(spans),
                "spans": spans,
            }
        )
        return _finish_read(payload)
    except Exception:
        payload = _base_payload(ticker=ticker, as_of=as_of)
        payload["unavailable_reason"] = "integrity_failure"
        return _finish_read(payload)


def _candidate_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_read": payload.get("source_read"),
        "document_id": payload.get("document_id"),
        "document_revision_id": payload.get("document_revision_id"),
        "source_span": payload.get("source_span"),
        "mention_class": payload.get("mention_class"),
        "matched_terms": payload.get("matched_terms"),
        "extraction_method": payload.get("extraction_method"),
    }


def _with_candidate_identity_and_hash(payload: dict[str, Any]) -> dict[str, Any]:
    payload["candidate_id"] = _stable_id(
        "biocatalyst_transcript_mention_", _candidate_identity(payload)
    )
    payload["candidate_payload_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"candidate_id", "candidate_payload_sha256"}
        }
    )
    return payload


def _read_semantic_messages(payload: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Replay the non-schema bindings without touching a store or reader."""
    issues: list[tuple[str, str, str]] = []
    expected_hash = canonical_json_sha256(
        {key: value for key, value in payload.items() if key not in {"read_id", "read_payload_sha256"}}
    )
    if payload.get("read_payload_sha256") != expected_hash:
        issues.append(("$.read_payload_sha256", "transcript_read.hash", "payload hash must bind the complete read payload"))
    query = payload.get("query")
    ticker = query.get("ticker") if isinstance(query, Mapping) else None
    expected_prefix = ticker if isinstance(ticker, str) else "unavailable"
    expected_id = _stable_id(f"earnings_transcript_span_read_{expected_prefix}_", _read_identity(payload))
    if payload.get("read_id") != expected_id:
        issues.append(("$.read_id", "transcript_read.deterministic_id", "read ID must bind the query, selected revision, and exact span ids"))

    available = payload.get("available")
    coverage = payload.get("coverage")
    expected_coverage = (
        {
            "document_classes": {
                "release": "not_ingested", "filing": "not_ingested", "transcript": "present",
                "slides": "not_ingested", "consensus": "unlicensed_absent",
            },
            "history_scope": "latest_selected_context_packet_only",
            "absence_conclusion": False,
        }
        if available is True else _empty_coverage()
    )
    if coverage != expected_coverage:
        issues.append(("$.coverage", "transcript_read.coverage", "coverage must remain the exact transcript-only reader scope"))
    if payload.get("authority") != _SOURCE_AUTHORITY:
        issues.append(("$.authority", "transcript_read.authority", "read authority must remain source/context only"))
    if payload.get("integrity_scope") != _INTEGRITY_SCOPE:
        issues.append(("$.integrity_scope", "transcript_read.integrity_scope", "read validation proves only a private, self-consistent receipt-bound projection; it carries no independent source-authenticity attestation"))

    spans = payload.get("spans")
    if not isinstance(spans, list) or payload.get("span_count") != len(spans):
        issues.append(("$.span_count", "transcript_read.span_count", "span_count must equal the exact span list length"))
    if available is not True:
        return issues

    document = payload.get("document")
    generation = payload.get("generation")
    if not isinstance(document, Mapping) or not isinstance(generation, Mapping) or not isinstance(query, Mapping):
        return issues
    document_id = _stable_id(
        "earnings_transcript_",
        {"ticker": document.get("ticker"), "transcript_id": document.get("transcript_id"), "period": document.get("period")},
    )
    if document.get("document_id") != document_id or query.get("ticker") != document.get("ticker"):
        issues.append(("$.document", "transcript_read.document_identity", "document identity must bind the explicit caller ticker and transcript event"))
    document_revision_id = _stable_id(
        "earnings_transcript_revision_",
        {
            "document_id": document_id,
            "source_sha256": document.get("source_sha256"),
            "known_at": document.get("known_at"),
            "correction_status": document.get("correction_status"),
        },
    )
    if document.get("document_revision_id") != document_revision_id:
        issues.append(("$.document.document_revision_id", "transcript_read.document_revision", "document revision must bind source hash, known_at, and correction state"))
    event_date: date | None = None
    try:
        event_date = date.fromisoformat(str(document.get("event_date")))
    except ValueError:
        pass  # Structural date validation reports this independently.
    known_at_value: datetime | None = None
    cutoff_value: datetime | None = None
    if generation.get("knowledge_cutoff") is not None and document.get("known_at") is not None:
        try:
            cutoff_value = datetime.fromisoformat(str(generation["knowledge_cutoff"]).replace("Z", "+00:00"))
            known_at_value = datetime.fromisoformat(str(document["known_at"]).replace("Z", "+00:00"))
            if cutoff_value.tzinfo is None or known_at_value.tzinfo is None or known_at_value.astimezone(timezone.utc) > cutoff_value.astimezone(timezone.utc):
                issues.append(("$.generation.knowledge_cutoff", "transcript_read.knowledge_cutoff", "knowledge cutoff must not precede the selected source known_at"))
        except ValueError:
            pass  # Structural date-time validation reports this independently.
    if event_date is not None and known_at_value is not None and event_date > known_at_value.astimezone(timezone.utc).date():
        issues.append(("$.document.event_date", "transcript_read.event_clock", "event date must not follow the selected source known_at"))
    if event_date is not None and cutoff_value is not None and event_date > cutoff_value.astimezone(timezone.utc).date():
        issues.append(("$.document.event_date", "transcript_read.generation_clock", "event date must not follow the selected generation cutoff"))
    as_of = query.get("as_of")
    if isinstance(as_of, str) and isinstance(document.get("known_at"), str):
        try:
            cutoff = (
                datetime.combine(date.fromisoformat(as_of), time.max, tzinfo=timezone.utc)
                if _AS_OF_DATE.fullmatch(as_of)
                else datetime.fromisoformat(as_of.replace("Z", "+00:00")).astimezone(timezone.utc)
            )
            known_at = datetime.fromisoformat(document["known_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
            if known_at > cutoff or (event_date is not None and event_date > cutoff.date()):
                issues.append(("$.query.as_of", "transcript_read.point_in_time", "selected evidence must be known by as_of"))
        except ValueError:
            pass
    if not isinstance(spans, list):
        return issues
    seen_ids: set[str] = set()
    prior_sort: tuple[int, int, str, str] | None = None
    for index, span in enumerate(spans):
        if not isinstance(span, Mapping):
            continue
        receipt = span.get("receipt")
        text = span.get("text")
        if not isinstance(receipt, Mapping) or not isinstance(text, str):
            continue
        if span.get("text_sha256") != sha256(text.encode("utf-8")).hexdigest() or receipt.get("text_sha256") != span.get("text_sha256"):
            issues.append((f"$.spans[{index}]", "transcript_read.text_receipt", "span text and both text hashes must agree"))
        if receipt.get("source_sha256") != document.get("source_sha256"):
            issues.append((f"$.spans[{index}].receipt.source_sha256", "transcript_read.source_receipt", "every span must bind this document revision source"))
        try:
            span_start = receipt["span_start_byte"]
            span_end = receipt["span_end_byte"]
            segment_bytes = receipt["segment_bytes"]
            if (
                any(isinstance(value, bool) or not isinstance(value, int) for value in (span_start, span_end, segment_bytes))
                or not (0 <= span_start < span_end <= segment_bytes)
                or span_end - span_start != len(text.encode("utf-8"))
            ):
                issues.append((f"$.spans[{index}].receipt", "transcript_read.receipt_coordinates", "receipt byte coordinates must exactly cover this span within its segment"))
        except KeyError:
            pass  # JSON Schema reports missing receipt fields independently.
        expected_span_id = _span_id(str(document.get("document_revision_id") or ""), span)
        if span.get("span_id") != expected_span_id:
            issues.append((f"$.spans[{index}].span_id", "transcript_read.span_id", "span ID must bind its exact receipt and document revision"))
        if span.get("span_id") in seen_ids:
            issues.append((f"$.spans[{index}].span_id", "transcript_read.span_unique", "span IDs must be unique"))
        seen_ids.add(str(span.get("span_id")))
        try:
            sort_key = (
                int(receipt["segment_index"]), int(receipt["span_start_byte"]),
                str(span.get("claim_id")), str(span.get("kind")),
            )
            if prior_sort is not None and sort_key <= prior_sort:
                issues.append((f"$.spans[{index}]", "transcript_read.span_order", "spans must use deterministic receipt order"))
            prior_sort = sort_key
        except (KeyError, TypeError, ValueError):
            pass
    return issues


def _candidate_semantic_messages(payload: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    expected_hash = canonical_json_sha256(
        {key: value for key, value in payload.items() if key not in {"candidate_id", "candidate_payload_sha256"}}
    )
    if payload.get("candidate_payload_sha256") != expected_hash:
        issues.append(("$.candidate_payload_sha256", "transcript_candidate.hash", "candidate hash must bind the complete review-only payload"))
    expected_id = _stable_id("biocatalyst_transcript_mention_", _candidate_identity(payload))
    if payload.get("candidate_id") != expected_id:
        issues.append(("$.candidate_id", "transcript_candidate.deterministic_id", "candidate ID must bind its exact span and lexical method"))
    if payload.get("authority") != _CANDIDATE_AUTHORITY:
        issues.append(("$.authority", "transcript_candidate.authority", "candidate authority must remain review-only context"))
    mention_class = payload.get("mention_class")
    terms_by_class = dict(_MENTION_TERMS)
    matched_terms = payload.get("matched_terms")
    if (
        not isinstance(matched_terms, list)
        or matched_terms != sorted(matched_terms)
        or not isinstance(mention_class, str)
        or any(term not in terms_by_class.get(mention_class, ()) for term in matched_terms)
    ):
        issues.append(("$.matched_terms", "transcript_candidate.terms", "matched terms must be sorted members of the fixed lexical allowlist"))
    return issues


def _candidate_binding_messages(
    candidate: Mapping[str, Any], span_read: Mapping[str, Any]
) -> list[tuple[str, str, str]]:
    """Bind every embedded candidate to its one exact nested transcript span."""
    issues: list[tuple[str, str, str]] = []
    document = span_read.get("document")
    spans = span_read.get("spans")
    if not isinstance(document, Mapping) or not isinstance(spans, list):
        return [("$", "transcript_bundle.read_unavailable", "candidates require one available nested read")]
    expected_read = {
        "read_id": span_read.get("read_id"),
        "read_payload_sha256": span_read.get("read_payload_sha256"),
    }
    if candidate.get("source_read") != expected_read:
        issues.append(("$.source_read", "transcript_bundle.candidate_read_binding", "candidate must bind the exact nested read identity and payload hash"))
    if (
        candidate.get("document_id") != document.get("document_id")
        or candidate.get("document_revision_id") != document.get("document_revision_id")
    ):
        issues.append(("$.document_id", "transcript_bundle.candidate_document_binding", "candidate must bind the exact nested document revision"))
    source_span = candidate.get("source_span")
    if not isinstance(source_span, Mapping):
        return issues
    matching = [
        span
        for span in spans
        if isinstance(span, Mapping) and span.get("span_id") == source_span.get("span_id")
    ]
    if len(matching) != 1:
        return issues + [("$.source_span.span_id", "transcript_bundle.candidate_span_binding", "candidate must reference exactly one nested span")]
    span = matching[0]
    receipt = span.get("receipt")
    expected_span = {
        "span_id": span.get("span_id"),
        "claim_id": span.get("claim_id"),
        "kind": span.get("kind"),
        "source_sha256": receipt.get("source_sha256") if isinstance(receipt, Mapping) else None,
        "text_sha256": span.get("text_sha256"),
    }
    if source_span != expected_span:
        issues.append(("$.source_span", "transcript_bundle.candidate_span_binding", "candidate span receipt reference must exactly equal the nested span"))
    mention_class = candidate.get("mention_class")
    text = span.get("text")
    terms_by_class = dict(_MENTION_TERMS)
    if not isinstance(mention_class, str) or not isinstance(text, str):
        return issues
    expected_terms = sorted(
        term
        for term in terms_by_class.get(mention_class, ())
        if _MENTION_PATTERNS[term].search(text.casefold())
    )
    if candidate.get("matched_terms") != expected_terms:
        issues.append(("$.matched_terms", "transcript_bundle.candidate_phrase_binding", "matched_terms must contain all and only phrase-bound allowlist hits in the exact nested span"))
    return issues


def _bundle_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    span_read = payload.get("span_read")
    candidates = payload.get("candidates")
    return {
        "read_id": span_read.get("read_id") if isinstance(span_read, Mapping) else None,
        "read_payload_sha256": (
            span_read.get("read_payload_sha256") if isinstance(span_read, Mapping) else None
        ),
        "candidate_ids": (
            [candidate.get("candidate_id") for candidate in candidates if isinstance(candidate, Mapping)]
            if isinstance(candidates, list) else []
        ),
    }


def _with_bundle_identity_and_hash(payload: dict[str, Any]) -> dict[str, Any]:
    payload["bundle_id"] = _stable_id(
        "biocatalyst_transcript_context_bundle_", _bundle_identity(payload)
    )
    payload["bundle_payload_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"bundle_id", "bundle_payload_sha256"}
        }
    )
    return payload


def _prefixed_messages(
    prefix: str, messages: list[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    return [
        (prefix + path[1:] if path.startswith("$") else prefix, code, message)
        for path, code, message in messages
    ]


def _bundle_semantic_messages(payload: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    expected_hash = canonical_json_sha256(
        {key: value for key, value in payload.items() if key not in {"bundle_id", "bundle_payload_sha256"}}
    )
    if payload.get("bundle_payload_sha256") != expected_hash:
        issues.append(("$.bundle_payload_sha256", "transcript_bundle.hash", "bundle hash must bind the complete atomic bundle"))
    expected_id = _stable_id("biocatalyst_transcript_context_bundle_", _bundle_identity(payload))
    if payload.get("bundle_id") != expected_id:
        issues.append(("$.bundle_id", "transcript_bundle.deterministic_id", "bundle ID must bind the exact nested read and candidate identities"))
    if payload.get("authority") != _BUNDLE_AUTHORITY:
        issues.append(("$.authority", "transcript_bundle.authority", "bundle authority must remain context-only"))
    if payload.get("integrity_scope") != _INTEGRITY_SCOPE:
        issues.append(("$.integrity_scope", "transcript_bundle.integrity_scope", "bundle validation proves only a private, self-consistent receipt-bound projection; it carries no independent source-authenticity attestation"))
    span_read = payload.get("span_read")
    candidates = payload.get("candidates")
    if not isinstance(span_read, Mapping):
        return issues
    if span_read.get("integrity_scope") != payload.get("integrity_scope"):
        issues.append(("$.integrity_scope", "transcript_bundle.integrity_scope_binding", "bundle and nested read must declare the identical private trust boundary"))
    issues.extend(_prefixed_messages("$.span_read", _read_semantic_messages(span_read)))
    if not isinstance(candidates, list):
        return issues
    if payload.get("candidate_count") != len(candidates):
        issues.append(("$.candidate_count", "transcript_bundle.candidate_count", "candidate_count must equal the embedded candidate list length"))
    if span_read.get("available") is not True and candidates:
        issues.append(("$.candidates", "transcript_bundle.unavailable_read_candidates", "unavailable reads must carry no candidates"))
    seen_ids: set[str] = set()
    prior_sort: tuple[str, str, str] | None = None
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            continue
        prefix = f"$.candidates[{index}]"
        issues.extend(_prefixed_messages(prefix, _candidate_semantic_messages(candidate)))
        issues.extend(_prefixed_messages(prefix, _candidate_binding_messages(candidate, span_read)))
        candidate_id = candidate.get("candidate_id")
        if candidate_id in seen_ids:
            issues.append((f"{prefix}.candidate_id", "transcript_bundle.candidate_unique", "candidate IDs must be unique"))
        seen_ids.add(str(candidate_id))
        source_span = candidate.get("source_span")
        if isinstance(source_span, Mapping):
            sort_key = (
                str(source_span.get("span_id")),
                str(candidate.get("mention_class")),
                str(candidate_id),
            )
            if prior_sort is not None and sort_key <= prior_sort:
                issues.append((prefix, "transcript_bundle.candidate_order", "candidates must use deterministic source-span then mention-class order"))
            prior_sort = sort_key
    try:
        expected_candidates = extract_transcript_mention_candidates(span_read)
    except Exception:
        issues.append(("$.span_read", "transcript_bundle.candidate_replay", "nested read cannot be replayed into the complete deterministic candidate set"))
    else:
        if candidates != expected_candidates:
            issues.append(("$.candidates", "transcript_bundle.complete_candidate_set", "candidates must exactly equal the complete deterministic lexical set for every nested span"))
    return issues


def transcript_contract_semantic_issues(
    contract_id: str, document: Mapping[str, Any]
) -> list[Any]:
    """Expose the read and atomic bundle replays to the shared registry."""
    from engine.sector_intelligence.contracts import ValidationIssue

    if contract_id == READ_CONTRACT_ID:
        raw = _read_semantic_messages(document)
    elif contract_id == BUNDLE_CONTRACT_ID:
        raw = _bundle_semantic_messages(document)
    else:
        return []
    return [ValidationIssue(path, code, message) for path, code, message in raw]


def _validate_local(contract_id: str, payload: Mapping[str, Any]) -> None:
    from engine.sector_intelligence.contracts import ContractValidationError, validate_contract

    validate_contract(contract_id, payload)
    issues = transcript_contract_semantic_issues(contract_id, payload)
    if issues:
        raise ContractValidationError(contract_id, issues)


def validate_transcript_span_read(payload: Mapping[str, Any]) -> None:
    """Validate deterministic receipt binding, not independent source authenticity."""
    _validate_local(READ_CONTRACT_ID, payload)


def validate_transcript_context_bundle(payload: Mapping[str, Any]) -> None:
    """Validate the sole atomically consumable C1α adapter output."""
    _validate_local(BUNDLE_CONTRACT_ID, payload)


def extract_transcript_mention_candidates(span_read: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return bounded lexical review candidates from one valid transcript read.

    An empty list means only that no allowlisted lexical cue was found in the
    returned bounded spans.  It never concludes that a company lacks a catalyst
    or that a clinical, regulatory, partnering, or financing event is absent.
    """
    validate_transcript_span_read(span_read)
    if span_read.get("available") is not True:
        return []
    document = span_read.get("document")
    spans = span_read.get("spans")
    if not isinstance(document, Mapping) or not isinstance(spans, list):
        raise BioCatalystTranscriptAdapterError("invalid_span_read")
    candidates: list[dict[str, Any]] = []
    for span in spans:
        if not isinstance(span, Mapping):
            raise BioCatalystTranscriptAdapterError("invalid_span_read")
        text = span.get("text")
        receipt = span.get("receipt")
        if not isinstance(text, str) or not isinstance(receipt, Mapping):
            raise BioCatalystTranscriptAdapterError("invalid_span_read")
        folded = text.casefold()
        for mention_class, terms in _MENTION_TERMS:
            matched_terms = sorted(
                {term for term in terms if _MENTION_PATTERNS[term].search(folded)}
            )
            if not matched_terms:
                continue
            candidate = {
                "source_read": {
                    "read_id": span_read.get("read_id"),
                    "read_payload_sha256": span_read.get("read_payload_sha256"),
                },
                "document_id": document.get("document_id"),
                "document_revision_id": document.get("document_revision_id"),
                "source_span": {
                    "span_id": span.get("span_id"),
                    "claim_id": span.get("claim_id"),
                    "kind": span.get("kind"),
                    "source_sha256": receipt.get("source_sha256"),
                    "text_sha256": span.get("text_sha256"),
                },
                "mention_class": mention_class,
                "matched_terms": matched_terms,
                "extraction_method": LEXICAL_METHOD,
                "asserted": False,
                "review_required": True,
                "no_negative_conclusion": True,
                "source_fact": False,
                "authority": dict(_CANDIDATE_AUTHORITY),
                "hash_scope": "canonical_payload_excluding_candidate_id_and_candidate_payload_sha256",
            }
            candidates.append(_with_candidate_identity_and_hash(candidate))
            if len(candidates) > MAX_CANDIDATES:
                raise BioCatalystTranscriptAdapterError("candidate_capacity_exceeded")
    candidates.sort(key=lambda item: (item["source_span"]["span_id"], item["mention_class"], item["candidate_id"]))
    return candidates


def read_earnings_transcript_context_bundle(
    params: Mapping[str, Any], *, root: Path | None = None
) -> dict[str, Any]:
    """Return the one atomic C1α consumable from one upstream reader call."""
    span_read = read_earnings_transcript_spans(params, root=root)
    candidates = extract_transcript_mention_candidates(span_read)
    payload: dict[str, Any] = {
        "contract_id": BUNDLE_CONTRACT_ID,
        "schema_version": "1.0.0",
        "span_read": span_read,
        "candidate_order": "source_span_then_mention_class_ascending",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "integrity_scope": dict(_INTEGRITY_SCOPE),
        "authority": dict(_BUNDLE_AUTHORITY),
        "hash_scope": "canonical_payload_excluding_bundle_id_and_bundle_payload_sha256",
    }
    result = _with_bundle_identity_and_hash(payload)
    validate_transcript_context_bundle(result)
    return result
