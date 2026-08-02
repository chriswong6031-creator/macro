"""Closed public contracts for receipt-backed earnings evidence.

The graph is deliberately a context substrate, not a rating, recommendation,
or market-action engine.  Every direct claim points to an exact UTF-8 span of
one Terminal ``mastermind.tx/v1`` segment.  Derived claims point only to direct
claims and declare their formula.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping


FACT_PACK_SCHEMA = "earnings.fact_pack/v1"
CLAIM_GRAPH_SCHEMA = "earnings.claim_graph/v1"
MANIFEST_SCHEMA = "earnings.evidence_manifest/v1"
TERMINAL_TRANSCRIPT_SCHEMA = "mastermind.tx/v1"
AUTHORITY = "context_only"
EXECUTION_RECEIPT = {
    "mode": "deterministic",
    "providers": [],
    "model_calls": 0,
    "tokens": 0,
}

_SHA = re.compile(r"^[0-9a-f]{64}$")
_GENERATION = re.compile(r"^[0-9a-f]{32}$")
_TICKER = re.compile(r"^[A-Z0-9](?:[A-Z0-9.-]{0,14}[A-Z0-9])?$")
_ID = re.compile(r"^\d{4}Q[1-4]$")
_FACT_ID = re.compile(r"^fact_[0-9a-f]{32}$")
_CLAIM_ID = re.compile(r"^claim_[0-9a-f]{32}$")
_NUMBER = re.compile(
    r"^([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?:\s*(%|bps|x|million|billion|m|bn))?$",
    re.IGNORECASE,
)

_TX_KEYS = frozenset({"schema", "ticker", "id", "period", "date", "title", "segments"})
_TX_SEGMENT_KEYS = frozenset({"speaker", "role", "text"})
_SOURCE_KEYS = frozenset({
    "source_kind", "ticker", "transcript_id", "body_sha256", "body_bytes", "index_sha256",
    "indexed_body_sha256", "index_generated_at", "locator",
})
_EVENT_KEYS = frozenset({"ticker", "transcript_id", "period", "date", "title"})
_EXECUTION_KEYS = frozenset({"mode", "providers", "model_calls", "tokens"})
_RECEIPT_KEYS = frozenset({
    "source_sha256", "segment_index", "segment_sha256", "segment_bytes",
    "span_start_byte", "span_end_byte", "text_sha256",
})
_FACT_KEYS = frozenset({"fact_id", "kind", "text", "numeric_value", "numeric_unit", "receipt"})
_PACK_KEYS = frozenset({"schema", "authority", "event", "source", "facts", "warnings", "insufficiency", "execution"})
_DIRECT_CLAIM_KEYS = frozenset({"claim_id", "claim_type", "fact_id"})
_DERIVED_CLAIM_KEYS = frozenset({
    "claim_id", "claim_type", "text", "numeric_value", "numeric_unit",
    "formula", "parent_claim_ids",
})
_GRAPH_KEYS = frozenset({"schema", "authority", "event", "source", "claims", "warnings", "insufficiency", "execution"})
_MANIFEST_KEYS = frozenset({
    "schema", "authority", "generation_id", "parent_generation_id", "generated_at", "status", "warnings",
    "omissions", "coverage", "events", "files", "execution",
})
_EVENT_MANIFEST_KEYS = frozenset({"source_sha256", "supersedes_source_sha256", "fact_pack", "claim_graph", "source_body"})
_FILE_KEYS = frozenset({"sha256", "bytes", "schema", "object_key"})
_OMISSION_KEYS = frozenset({"event_key", "reason", "expected_source_sha256"})
_COVERAGE_KEYS = frozenset({
    "selection_policy", "batch_limit", "historical_completeness", "event_count",
    "oldest_call_date", "newest_call_date", "index_body_count", "index_generated_at",
})

KNOWN_WARNINGS = frozenset({"empty_segment", "overlong_sentence", "no_numeric_statements", "selection_bounded", "backfill_pending", "no_selected_bodies"})
KNOWN_INSUFFICIENCY = frozenset({"no_extractable_segments", "no_numeric_statements"})
KNOWN_OMISSIONS = frozenset({"missing_body", "body_contract_invalid", "body_revision_mismatch"})


class ContractError(ValueError):
    """The artifact cannot be safely treated as public evidence."""


def canonical_json_bytes(payload: object) -> bytes:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError(f"payload is not canonical JSON: {exc}") from exc


def canonical_json_sha256(payload: object) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def canonical_transcript_body_bytes(payload: object) -> bytes:
    """Match Terminal's ``canonical_body_sha256`` byte-for-byte.

    Public evidence artifacts use ``canonical_json_bytes`` with a trailing
    newline.  Terminal transcript revisions deliberately do not; conflating
    those two serializations would reject every body advertised by the live
    ``mastermind.tx-index/v1`` marker.
    """
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError(f"transcript is not canonical JSON: {exc}") from exc


def canonical_transcript_body_sha256(payload: object) -> str:
    return sha256(canonical_transcript_body_bytes(payload)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def safe_ticker(value: object) -> str:
    ticker = str(value or "").strip().upper()
    if not ticker or "/" in ticker or "\\" in ticker or ".." in ticker or not _TICKER.fullmatch(ticker):
        raise ContractError(f"unsafe ticker: {value!r}")
    return ticker


def transcript_id(value: object) -> str:
    tx_id = str(value or "").strip().upper()
    if not _ID.fullmatch(tx_id):
        raise ContractError(f"invalid transcript id: {value!r}")
    return tx_id


def iso_timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a UTC ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be a UTC ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def iso_date(value: object, *, field: str) -> str:
    if not isinstance(value, str) or len(value) != 10:
        raise ContractError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO date") from exc


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: frozenset[str], *, name: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ContractError(f"{name} fields mismatch (missing={missing}, unsupported={unknown})")


def _text(value: object, *, field: str, allow_empty: bool = False, limit: int = 4000) -> str:
    if not isinstance(value, str) or "\x00" in value or len(value) > limit or (not allow_empty and not value):
        raise ContractError(f"{field} invalid")
    return value


def _sha(value: object, *, field: str, allow_null: bool = False) -> str | None:
    if value is None and allow_null:
        return None
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ContractError(f"{field} must be sha256 hex")
    return value


def _finite(value: object, *, field: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractError(f"{field} must be a finite number")
    return value


def validate_terminal_transcript(payload: object) -> Mapping[str, Any]:
    """Validate the exact Terminal transcript body used as an evidence source."""
    item = _mapping(payload, name="transcript")
    _keys(item, _TX_KEYS, name="transcript")
    if item.get("schema") != TERMINAL_TRANSCRIPT_SCHEMA:
        raise ContractError("transcript schema mismatch")
    safe_ticker(item.get("ticker"))
    transcript_id(item.get("id"))
    _text(item.get("period"), field="transcript.period", limit=120)
    iso_date(item.get("date"), field="transcript.date")
    _text(item.get("title"), field="transcript.title", limit=800)
    segments = item.get("segments")
    if not isinstance(segments, list) or len(segments) > 20_000:
        raise ContractError("transcript.segments must be a bounded list")
    for index, segment in enumerate(segments):
        row = _mapping(segment, name=f"transcript.segments[{index}]")
        _keys(row, _TX_SEGMENT_KEYS, name=f"transcript.segments[{index}]")
        _text(row.get("speaker"), field=f"transcript.segments[{index}].speaker", allow_empty=True, limit=400)
        _text(row.get("role"), field=f"transcript.segments[{index}].role", allow_empty=True, limit=400)
        _text(row.get("text"), field=f"transcript.segments[{index}].text", allow_empty=True, limit=80_000)
    return item


def transcript_source(payload: object, *, index_payload: object, indexed_body_sha256: object, index_generated_at: object) -> dict[str, Any]:
    """Return the canonical source receipt after verifying index/body identity."""
    transcript = validate_terminal_transcript(payload)
    body = canonical_transcript_body_bytes(transcript)
    body_sha = sha256_bytes(body)
    indexed_sha = _sha(indexed_body_sha256, field="indexed_body_sha256", allow_null=True)
    if indexed_sha is not None and indexed_sha != body_sha:
        raise ContractError(f"indexed transcript revision mismatch: {indexed_sha} != {body_sha}")
    indexed_at = iso_timestamp(index_generated_at, field="index_generated_at")
    if iso_date(transcript["date"], field="transcript.date") > indexed_at[:10]:
        raise ContractError("transcript date is after index receipt")
    return {
        "source_kind": "transcript",
        "ticker": safe_ticker(transcript["ticker"]),
        "transcript_id": transcript_id(transcript["id"]),
        "body_sha256": body_sha,
        "body_bytes": len(body),
        "index_sha256": canonical_json_sha256(index_payload),
        "indexed_body_sha256": indexed_sha,
        "index_generated_at": indexed_at,
        "locator": f"/data/tx/{safe_ticker(transcript['ticker'])}/{transcript_id(transcript['id'])}.json.gz",
    }


def transcript_source_from_receipt(payload: object, receipt: object) -> dict[str, Any]:
    """Reuse an intake-time source receipt for an unchanged cached body.

    The Terminal index is a moving commit marker.  Replacing its timestamp or
    hash in an unchanged event would churn every fact and graph object on each
    refresh.  This path accepts only the exact receipt previously created by
    :func:`transcript_source`, then replays its body and identity bindings.
    """
    transcript = validate_terminal_transcript(payload)
    source = _validate_source(receipt, name="source_receipt")
    body = canonical_transcript_body_bytes(transcript)
    if (
        source["ticker"] != safe_ticker(transcript["ticker"])
        or source["transcript_id"] != transcript_id(transcript["id"])
        or source["body_sha256"] != sha256_bytes(body)
        or source["body_bytes"] != len(body)
    ):
        raise ContractError("source_receipt does not bind this transcript body")
    if iso_date(transcript["date"], field="transcript.date") > str(source["index_generated_at"])[:10]:
        raise ContractError("transcript date is after source_receipt index receipt")
    return dict(source)


def event_from_transcript(payload: object) -> dict[str, str]:
    transcript = validate_terminal_transcript(payload)
    return {
        "ticker": safe_ticker(transcript["ticker"]),
        "transcript_id": transcript_id(transcript["id"]),
        "period": _text(transcript["period"], field="transcript.period", limit=120),
        "date": iso_date(transcript["date"], field="transcript.date"),
        "title": _text(transcript["title"], field="transcript.title", limit=800),
    }


def event_key(event: Mapping[str, Any]) -> str:
    return f"{safe_ticker(event.get('ticker'))}/{transcript_id(event.get('transcript_id'))}"


def normalize_numeric(text: str) -> tuple[float | int, str | None]:
    match = _NUMBER.fullmatch(text)
    if match is None:
        raise ContractError("numeric fact text is not an exact supported number")
    numeric = float(match.group(1).replace(",", ""))
    if not math.isfinite(numeric):
        raise ContractError("numeric fact is not finite")
    unit_raw = (match.group(2) or "").lower()
    units = {"%": "percent", "bps": "basis_points", "x": "multiple", "million": "million", "m": "million", "billion": "billion", "bn": "billion"}
    unit = units.get(unit_raw)
    return (int(numeric) if numeric.is_integer() else numeric), unit


def receipt_for_span(*, source_sha256: str, segment_index: int, segment_text: str, start_byte: int, end_byte: int, text: str) -> dict[str, Any]:
    if not isinstance(segment_index, int) or segment_index < 0:
        raise ContractError("segment_index must be a non-negative integer")
    segment_bytes = segment_text.encode("utf-8")
    text_bytes = text.encode("utf-8")
    if start_byte < 0 or end_byte < start_byte or end_byte > len(segment_bytes) or end_byte - start_byte != len(text_bytes):
        raise ContractError("span does not bound exact UTF-8 text bytes")
    if segment_bytes[start_byte:end_byte] != text_bytes:
        raise ContractError("span does not reproduce exact UTF-8 text")
    return {
        "source_sha256": source_sha256,
        "segment_index": segment_index,
        "segment_sha256": sha256_bytes(segment_bytes),
        "segment_bytes": len(segment_bytes),
        "span_start_byte": start_byte,
        "span_end_byte": end_byte,
        "text_sha256": sha256_bytes(text_bytes),
    }


def _validate_execution(value: object, *, name: str) -> None:
    row = _mapping(value, name=name)
    _keys(row, _EXECUTION_KEYS, name=name)
    if dict(row) != EXECUTION_RECEIPT:
        raise ContractError(f"{name} must prove zero-provider deterministic execution")


def _validate_source(value: object, *, name: str) -> Mapping[str, Any]:
    row = _mapping(value, name=name)
    _keys(row, _SOURCE_KEYS, name=name)
    if row.get("source_kind") != "transcript":
        raise ContractError(f"{name}.source_kind must be transcript in v1")
    safe_ticker(row.get("ticker"))
    transcript_id(row.get("transcript_id"))
    _sha(row.get("body_sha256"), field=f"{name}.body_sha256")
    if isinstance(row.get("body_bytes"), bool) or not isinstance(row.get("body_bytes"), int) or row["body_bytes"] <= 0:
        raise ContractError(f"{name}.body_bytes invalid")
    _sha(row.get("index_sha256"), field=f"{name}.index_sha256")
    indexed = _sha(row.get("indexed_body_sha256"), field=f"{name}.indexed_body_sha256", allow_null=True)
    if indexed is not None and indexed != row.get("body_sha256"):
        raise ContractError(f"{name}.indexed_body_sha256 must match body_sha256")
    iso_timestamp(row.get("index_generated_at"), field=f"{name}.index_generated_at")
    expected_locator = f"/data/tx/{safe_ticker(row['ticker'])}/{transcript_id(row['transcript_id'])}.json.gz"
    if row.get("locator") != expected_locator:
        raise ContractError(f"{name}.locator must be the canonical Terminal transcript path")
    return row


def _validate_event(value: object, *, name: str) -> Mapping[str, Any]:
    row = _mapping(value, name=name)
    _keys(row, _EVENT_KEYS, name=name)
    safe_ticker(row.get("ticker"))
    transcript_id(row.get("transcript_id"))
    _text(row.get("period"), field=f"{name}.period", limit=120)
    iso_date(row.get("date"), field=f"{name}.date")
    _text(row.get("title"), field=f"{name}.title", limit=800)
    return row


def _validate_receipt(value: object, *, source_sha: str, text: str, name: str) -> Mapping[str, Any]:
    row = _mapping(value, name=name)
    _keys(row, _RECEIPT_KEYS, name=name)
    if row.get("source_sha256") != source_sha:
        raise ContractError(f"{name}.source_sha256 must match source")
    if not isinstance(row.get("segment_index"), int) or isinstance(row.get("segment_index"), bool) or row["segment_index"] < 0:
        raise ContractError(f"{name}.segment_index invalid")
    _sha(row.get("segment_sha256"), field=f"{name}.segment_sha256")
    if not isinstance(row.get("segment_bytes"), int) or row["segment_bytes"] < 0:
        raise ContractError(f"{name}.segment_bytes invalid")
    start, end = row.get("span_start_byte"), row.get("span_end_byte")
    if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) or isinstance(end, bool) or start < 0 or end < start or end > row["segment_bytes"]:
        raise ContractError(f"{name}.span invalid")
    encoded = text.encode("utf-8")
    if end - start != len(encoded):
        raise ContractError(f"{name}.span does not match exact UTF-8 text bytes")
    if row.get("text_sha256") != sha256_bytes(encoded):
        raise ContractError(f"{name}.text_sha256 mismatch")
    return row


def _warnings(value: object, *, allowed: frozenset[str], name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"{name} must be a list of codes")
    if value != sorted(set(value)) or not set(value) <= allowed:
        raise ContractError(f"{name} contains unknown or unordered codes")
    return value


def validate_fact_pack(payload: object) -> None:
    row = _mapping(payload, name="fact_pack")
    _keys(row, _PACK_KEYS, name="fact_pack")
    if row.get("schema") != FACT_PACK_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("fact_pack schema or authority mismatch")
    event = _validate_event(row.get("event"), name="fact_pack.event")
    source = _validate_source(row.get("source"), name="fact_pack.source")
    if event_key(event) != f"{source['ticker']}/{source['transcript_id']}":
        raise ContractError("fact_pack event/source identity mismatch")
    if event["date"] > source["index_generated_at"][:10]:
        raise ContractError("fact_pack event date is after source receipt")
    facts = row.get("facts")
    if not isinstance(facts, list) or len(facts) > 100_000:
        raise ContractError("fact_pack.facts invalid")
    seen: set[str] = set()
    prior_order: tuple[int, int, str] | None = None
    for index, item in enumerate(facts):
        fact = _mapping(item, name=f"fact_pack.facts[{index}]")
        _keys(fact, _FACT_KEYS, name=f"fact_pack.facts[{index}]")
        fact_id = fact.get("fact_id")
        if not isinstance(fact_id, str) or not _FACT_ID.fullmatch(fact_id) or fact_id in seen:
            raise ContractError("fact_pack fact_id invalid or duplicate")
        seen.add(fact_id)
        kind = fact.get("kind")
        if kind not in {"quote", "numeric"}:
            raise ContractError("fact_pack fact kind invalid")
        text = _text(fact.get("text"), field=f"fact_pack.facts[{index}].text", limit=4000)
        receipt = _validate_receipt(fact.get("receipt"), source_sha=str(source["body_sha256"]), text=text, name=f"fact_pack.facts[{index}].receipt")
        ordering = (int(receipt["segment_index"]), int(receipt["span_start_byte"]), str(fact_id))
        if prior_order is not None and ordering <= prior_order:
            raise ContractError("fact_pack facts must be deterministic receipt order")
        prior_order = ordering
        if kind == "quote":
            if fact.get("numeric_value") is not None or fact.get("numeric_unit") is not None:
                raise ContractError("quote fact cannot carry numeric fields")
        else:
            value, unit = normalize_numeric(text)
            if fact.get("numeric_value") != value or fact.get("numeric_unit") != unit:
                raise ContractError("numeric fact value/unit must equal exact text")
    _warnings(row.get("warnings"), allowed=KNOWN_WARNINGS, name="fact_pack.warnings")
    insufficiency = _warnings(row.get("insufficiency"), allowed=KNOWN_INSUFFICIENCY, name="fact_pack.insufficiency")
    if not facts and "no_extractable_segments" not in insufficiency:
        raise ContractError("empty fact pack requires no_extractable_segments")
    _validate_execution(row.get("execution"), name="fact_pack.execution")


def direct_claim_id(fact_id: str) -> str:
    return "claim_" + sha256(("direct:" + fact_id).encode("utf-8")).hexdigest()[:32]


def derived_claim_id(parent_ids: list[str]) -> str:
    return "claim_" + sha256(("count:" + ",".join(parent_ids)).encode("utf-8")).hexdigest()[:32]


def validate_claim_graph(payload: object) -> None:
    row = _mapping(payload, name="claim_graph")
    _keys(row, _GRAPH_KEYS, name="claim_graph")
    if row.get("schema") != CLAIM_GRAPH_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("claim_graph schema or authority mismatch")
    event = _validate_event(row.get("event"), name="claim_graph.event")
    source = _validate_source(row.get("source"), name="claim_graph.source")
    if event_key(event) != f"{source['ticker']}/{source['transcript_id']}":
        raise ContractError("claim_graph event/source identity mismatch")
    claims = row.get("claims")
    if not isinstance(claims, list) or len(claims) > 100_001:
        raise ContractError("claim_graph.claims invalid")
    ids: set[str] = set()
    direct_numeric: list[str] = []
    derived_count = 0
    for index, item in enumerate(claims):
        claim = _mapping(item, name=f"claim_graph.claims[{index}]")
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not _CLAIM_ID.fullmatch(claim_id) or claim_id in ids:
            raise ContractError("claim_graph claim_id invalid or duplicate")
        ids.add(claim_id)
        kind = claim.get("claim_type")
        if kind in {"direct_quote", "direct_numeric"}:
            _keys(claim, _DIRECT_CLAIM_KEYS, name=f"claim_graph.claims[{index}]")
            fact_id = claim.get("fact_id")
            if not isinstance(fact_id, str) or not _FACT_ID.fullmatch(fact_id) or claim_id != direct_claim_id(fact_id):
                raise ContractError("direct claim must bind one fact_id")
            if kind == "direct_numeric":
                direct_numeric.append(claim_id)
        elif kind == "derived_metric":
            _keys(claim, _DERIVED_CLAIM_KEYS, name=f"claim_graph.claims[{index}]")
            derived_count += 1
            text = _text(claim.get("text"), field=f"claim_graph.claims[{index}].text", limit=4000)
            parents = claim.get("parent_claim_ids")
            if not isinstance(parents, list) or any(not isinstance(parent, str) or not _CLAIM_ID.fullmatch(parent) for parent in parents) or parents != sorted(set(parents)):
                raise ContractError("claim_graph parent_claim_ids invalid")
            if claim.get("formula") != "count(parent_claim_ids)" or claim.get("numeric_unit") != "count":
                raise ContractError("derived metric formula/unit invalid")
            if parents != direct_numeric or claim.get("numeric_value") != len(parents) or claim_id != derived_claim_id(parents):
                raise ContractError("derived metric must bind ordered direct numeric parents")
            if text != f"Extracted numeric statement count: {len(parents)}.":
                raise ContractError("derived metric text mismatch")
        else:
            raise ContractError("claim_graph claim_type invalid")
    if derived_count > 1:
        raise ContractError("claim_graph has more than one derived metric")
    _warnings(row.get("warnings"), allowed=KNOWN_WARNINGS, name="claim_graph.warnings")
    _warnings(row.get("insufficiency"), allowed=KNOWN_INSUFFICIENCY, name="claim_graph.insufficiency")
    _validate_execution(row.get("execution"), name="claim_graph.execution")


def validate_evidence_pair(fact_pack: object, claim_graph: object) -> None:
    validate_fact_pack(fact_pack)
    validate_claim_graph(claim_graph)
    pack = _mapping(fact_pack, name="fact_pack")
    graph = _mapping(claim_graph, name="claim_graph")
    if pack["event"] != graph["event"] or pack["source"] != graph["source"]:
        raise ContractError("fact pack and claim graph source/event mismatch")
    direct = [claim for claim in graph["claims"] if claim["claim_type"] != "derived_metric"]
    if len(direct) != len(pack["facts"]):
        raise ContractError("every fact must yield exactly one direct claim")
    facts = {str(fact["fact_id"]): fact for fact in pack["facts"]}
    if len(facts) != len(pack["facts"]):
        raise ContractError("fact pack fact_id collision")
    claimed_facts: set[str] = set()
    for claim in direct:
        fact_id = claim.get("fact_id")
        if not isinstance(fact_id, str) or fact_id in claimed_facts or fact_id not in facts:
            raise ContractError("direct claim fact_id mapping invalid")
        claimed_facts.add(fact_id)
        fact = facts[fact_id]
        expected_type = "direct_numeric" if fact["kind"] == "numeric" else "direct_quote"
        if (
            claim["claim_id"] != direct_claim_id(fact["fact_id"])
            or claim["claim_type"] != expected_type
        ):
            raise ContractError("direct claim does not exactly bind its fact")


def verify_fact_pack_against_transcript(fact_pack: object, transcript: object) -> None:
    """Replay every direct receipt against its immutable source body bytes."""
    validate_fact_pack(fact_pack)
    pack = _mapping(fact_pack, name="fact_pack")
    tx = validate_terminal_transcript(transcript)
    source = pack["source"]
    body = canonical_transcript_body_bytes(tx)
    if sha256_bytes(body) != source["body_sha256"] or len(body) != source["body_bytes"]:
        raise ContractError("fact_pack source body receipt mismatch")
    if event_from_transcript(tx) != pack["event"]:
        raise ContractError("fact_pack event does not match source body")
    for index, fact in enumerate(pack["facts"]):
        receipt = fact["receipt"]
        segment_index = int(receipt["segment_index"])
        segments = tx["segments"]
        if segment_index >= len(segments):
            raise ContractError(f"fact_pack facts[{index}] segment is absent from source body")
        segment_text = str(segments[segment_index]["text"])
        segment_bytes = segment_text.encode("utf-8")
        start = int(receipt["span_start_byte"])
        end = int(receipt["span_end_byte"])
        if (
            receipt["segment_sha256"] != sha256_bytes(segment_bytes)
            or receipt["segment_bytes"] != len(segment_bytes)
            or segment_bytes[start:end] != fact["text"].encode("utf-8")
        ):
            raise ContractError(f"fact_pack facts[{index}] does not replay against source bytes")


def validate_manifest(payload: object) -> None:
    row = _mapping(payload, name="manifest")
    _keys(row, _MANIFEST_KEYS, name="manifest")
    if row.get("schema") != MANIFEST_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("manifest schema or authority mismatch")
    if not isinstance(row.get("generation_id"), str) or not _GENERATION.fullmatch(row["generation_id"]):
        raise ContractError("manifest generation_id invalid")
    parent_generation = row.get("parent_generation_id")
    if parent_generation is not None and (not isinstance(parent_generation, str) or not _GENERATION.fullmatch(parent_generation) or parent_generation == row["generation_id"]):
        raise ContractError("manifest parent_generation_id invalid")
    iso_timestamp(row.get("generated_at"), field="manifest.generated_at")
    if row.get("status") not in {"ready", "partial"}:
        raise ContractError("manifest status invalid")
    _warnings(row.get("warnings"), allowed=KNOWN_WARNINGS, name="manifest.warnings")
    coverage = _mapping(row.get("coverage"), name="manifest.coverage")
    _keys(coverage, _COVERAGE_KEYS, name="manifest.coverage")
    if coverage.get("selection_policy") not in {"explicit_input", "append_only_full_index"}:
        raise ContractError("manifest coverage selection_policy invalid")
    if not isinstance(coverage.get("batch_limit"), int) or isinstance(coverage.get("batch_limit"), bool) or not 1 <= coverage["batch_limit"] <= 500:
        raise ContractError("manifest coverage batch_limit invalid")
    if not isinstance(coverage.get("historical_completeness"), bool):
        raise ContractError("manifest coverage historical_completeness invalid")
    if not isinstance(coverage.get("event_count"), int) or isinstance(coverage.get("event_count"), bool) or coverage["event_count"] < 0:
        raise ContractError("manifest coverage event_count invalid")
    if not isinstance(coverage.get("index_body_count"), int) or isinstance(coverage.get("index_body_count"), bool) or coverage["index_body_count"] < 0:
        raise ContractError("manifest coverage index_body_count invalid")
    if iso_timestamp(coverage.get("index_generated_at"), field="manifest.coverage.index_generated_at") != row["generated_at"]:
        raise ContractError("manifest coverage index_generated_at must equal generated_at")
    oldest, newest = coverage.get("oldest_call_date"), coverage.get("newest_call_date")
    if coverage["event_count"] == 0:
        if oldest is not None or newest is not None:
            raise ContractError("empty manifest coverage dates must be null")
    elif iso_date(oldest, field="manifest.coverage.oldest_call_date") > iso_date(newest, field="manifest.coverage.newest_call_date"):
        raise ContractError("manifest coverage dates invalid")
    if coverage["historical_completeness"] and coverage["event_count"] < coverage["index_body_count"]:
        raise ContractError("historically complete coverage cannot have fewer events than the index")
    omissions = row.get("omissions")
    if not isinstance(omissions, list):
        raise ContractError("manifest omissions invalid")
    omission_keys: list[str] = []
    for index, item in enumerate(omissions):
        omission = _mapping(item, name=f"manifest.omissions[{index}]")
        _keys(omission, _OMISSION_KEYS, name=f"manifest.omissions[{index}]")
        key = str(omission.get("event_key") or "")
        if "/" not in key:
            raise ContractError("manifest omission event_key invalid")
        ticker, tx_id = key.split("/", 1)
        if f"{safe_ticker(ticker)}/{transcript_id(tx_id)}" != key or omission.get("reason") not in KNOWN_OMISSIONS:
            raise ContractError("manifest omission invalid")
        _sha(omission.get("expected_source_sha256"), field="manifest omission expected_source_sha256", allow_null=True)
        omission_keys.append(key)
    if omission_keys != sorted(set(omission_keys)):
        raise ContractError("manifest omissions must be sorted and unique")
    events = _mapping(row.get("events"), name="manifest.events")
    files = _mapping(row.get("files"), name="manifest.files")
    for key, event in events.items():
        if not isinstance(key, str) or "/" not in key:
            raise ContractError("manifest event key invalid")
        ticker, tx_id = key.split("/", 1)
        if key != f"{safe_ticker(ticker)}/{transcript_id(tx_id)}":
            raise ContractError("manifest event key invalid")
        block = _mapping(event, name=f"manifest.events[{key}]")
        _keys(block, _EVENT_MANIFEST_KEYS, name=f"manifest.events[{key}]")
        _sha(block.get("source_sha256"), field="manifest event source_sha256")
        superseded = _sha(block.get("supersedes_source_sha256"), field="manifest event supersedes_source_sha256", allow_null=True)
        if superseded == block.get("source_sha256"):
            raise ContractError("manifest cannot supersede same revision")
        expected_base = key.replace("/", "/")
        if block.get("fact_pack") != f"fact_packs/{expected_base}.json" or block.get("claim_graph") != f"claim_graphs/{expected_base}.json":
            raise ContractError("manifest event paths invalid")
        if block.get("source_body") != f"source_bodies/{block['source_sha256']}.json":
            raise ContractError("manifest source body path invalid")
        for path, schema in (
            (block["fact_pack"], FACT_PACK_SCHEMA),
            (block["claim_graph"], CLAIM_GRAPH_SCHEMA),
            (block["source_body"], TERMINAL_TRANSCRIPT_SCHEMA),
        ):
            file = _mapping(files.get(path), name=f"manifest.files[{path}]")
            _keys(file, _FILE_KEYS, name=f"manifest.files[{path}]")
            _sha(file.get("sha256"), field=f"manifest.files[{path}].sha256")
            if (
                not isinstance(file.get("bytes"), int)
                or file["bytes"] <= 0
                or file.get("schema") != schema
                or file.get("object_key") != f"objects/{file['sha256']}.json"
            ):
                raise ContractError("manifest file block invalid")
    if set(files) != {path for block in events.values() for path in (block["fact_pack"], block["claim_graph"], block["source_body"])}:
        raise ContractError("manifest files must exactly cover event artifacts")
    if coverage["event_count"] != len(events):
        raise ContractError("manifest coverage event_count must match events")
    # Event dates are available only in the referenced artifacts; the health
    # verifier replays those paths. Here we pin content addressability before
    # any filesystem access.
    unsigned = dict(row)
    unsigned["generation_id"] = "0" * 32
    if canonical_json_sha256(unsigned)[:32] != row["generation_id"]:
        raise ContractError("manifest generation_id does not match canonical unsigned manifest")
    # ``ready`` means the immutable tree is complete and verifies. Coverage
    # notices and an individual event's insufficiency remain explicit in their
    # own receipts; they are not a reason to suppress healthy peers.
    if row["status"] == "partial" and events:
        raise ContractError("partial manifest is reserved for an empty generation")
    _validate_execution(row.get("execution"), name="manifest.execution")
