"""Deterministically extract exact transcript spans into facts and claims."""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Mapping

from .contracts import (
    AUTHORITY,
    CLAIM_GRAPH_SCHEMA,
    EXECUTION_RECEIPT,
    FACT_PACK_SCHEMA,
    ContractError,
    direct_claim_id,
    event_from_transcript,
    normalize_numeric,
    receipt_for_span,
    transcript_source,
    validate_evidence_pair,
)


# The expression intentionally matches a complete lexical number only.  The
# value is never inferred from surrounding prose, and unit normalization lives
# in ``normalize_numeric`` so validation replays the exact same rule.
_NUMERIC_SPAN = re.compile(
    r"(?<![A-Za-z0-9_.])([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s*(?:%|bps|x|million|billion|m|bn))?)(?![A-Za-z0-9_.])",
    re.IGNORECASE,
)


def _span_bytes(text: str, start: int, end: int) -> tuple[int, int]:
    """Translate Python character offsets to exact UTF-8 byte offsets."""
    return len(text[:start].encode("utf-8")), len(text[:end].encode("utf-8"))


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Return bounded sentence-like spans without rewriting source text.

    A final unterminated fragment is retained.  We use only punctuation followed
    by whitespace/end as a boundary, so abbreviations and decimal values remain
    in their source segment rather than being normalized or guessed.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    length = len(text)
    for index, character in enumerate(text):
        if character in ".!?" and (index + 1 == length or text[index + 1].isspace()):
            spans.append((start, index + 1))
            start = index + 1
    if start < length:
        spans.append((start, length))
    bounded: list[tuple[int, int]] = []
    for begin, end in spans:
        while begin < end and text[begin].isspace():
            begin += 1
        while end > begin and text[end - 1].isspace():
            end -= 1
        if begin < end:
            bounded.append((begin, end))
    return bounded


def _fact_id(source_sha: str, segment_index: int, start: int, end: int, kind: str) -> str:
    material = f"{source_sha}:{segment_index}:{start}:{end}:{kind}".encode("utf-8")
    return "fact_" + sha256(material).hexdigest()[:32]


def build_fact_pack(
    transcript: object,
    *,
    index_payload: object,
    indexed_body_sha256: object,
    index_generated_at: object,
) -> dict[str, Any]:
    """Build a v1 fact pack directly from one validated Terminal body.

    Existing summaries, highlights, scores, and model output are intentionally
    absent from this function's inputs and implementation.
    """
    source = transcript_source(
        transcript,
        index_payload=index_payload,
        indexed_body_sha256=indexed_body_sha256,
        index_generated_at=index_generated_at,
    )
    event = event_from_transcript(transcript)
    tx = transcript  # ``transcript_source`` has already closed/validated it.
    assert isinstance(tx, Mapping)
    facts: list[dict[str, Any]] = []
    warnings: set[str] = set()
    for segment_index, segment in enumerate(tx["segments"]):
        assert isinstance(segment, Mapping)
        segment_text = str(segment["text"])
        if not segment_text.strip():
            warnings.add("empty_segment")
            continue
        for char_start, char_end in _sentence_spans(segment_text):
            text = segment_text[char_start:char_end]
            if len(text) > 4_000:
                warnings.add("overlong_sentence")
                continue
            start_byte, end_byte = _span_bytes(segment_text, char_start, char_end)
            facts.append({
                "fact_id": _fact_id(str(source["body_sha256"]), segment_index, start_byte, end_byte, "quote"),
                "kind": "quote",
                "text": text,
                "numeric_value": None,
                "numeric_unit": None,
                "receipt": receipt_for_span(
                    source_sha256=str(source["body_sha256"]),
                    segment_index=segment_index,
                    segment_text=segment_text,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    text=text,
                ),
            })
        for match in _NUMERIC_SPAN.finditer(segment_text):
            text = match.group(1)
            start_byte, end_byte = _span_bytes(segment_text, match.start(1), match.end(1))
            value, unit = normalize_numeric(text)
            facts.append({
                "fact_id": _fact_id(str(source["body_sha256"]), segment_index, start_byte, end_byte, "numeric"),
                "kind": "numeric",
                "text": text,
                "numeric_value": value,
                "numeric_unit": unit,
                "receipt": receipt_for_span(
                    source_sha256=str(source["body_sha256"]),
                    segment_index=segment_index,
                    segment_text=segment_text,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    text=text,
                ),
            })
    facts.sort(key=lambda fact: (fact["receipt"]["segment_index"], fact["receipt"]["span_start_byte"], fact["fact_id"]))
    if not any(fact["kind"] == "numeric" for fact in facts):
        warnings.add("no_numeric_statements")
    insufficiency: list[str] = []
    if not facts:
        insufficiency.append("no_extractable_segments")
    if not any(fact["kind"] == "numeric" for fact in facts):
        insufficiency.append("no_numeric_statements")
    return {
        "schema": FACT_PACK_SCHEMA,
        "authority": AUTHORITY,
        "event": event,
        "source": source,
        "facts": facts,
        "warnings": sorted(warnings),
        "insufficiency": sorted(insufficiency),
        "execution": dict(EXECUTION_RECEIPT),
    }


def build_claim_graph(fact_pack: object) -> dict[str, Any]:
    """Construct one exact, direct claim per extracted fact.

    The v1 graph deliberately publishes no derived metric.  A count of extracted
    numbers is pipeline telemetry, not an earnings statement.  The closed
    contract nevertheless validates a future derived claim only when it names a
    real formula and every direct parent, so downstream versions cannot smuggle
    in an unsupported synthesized conclusion.
    """
    if not isinstance(fact_pack, Mapping):
        raise ContractError("fact pack must be an object")
    claims: list[dict[str, Any]] = []
    for fact in fact_pack.get("facts", []):
        assert isinstance(fact, Mapping)
        kind = "direct_numeric" if fact["kind"] == "numeric" else "direct_quote"
        claim_id = direct_claim_id(str(fact["fact_id"]))
        claims.append({
            "claim_id": claim_id,
            "claim_type": kind,
            "text": fact["text"],
            "numeric_value": fact["numeric_value"],
            "numeric_unit": fact["numeric_unit"],
            "formula": None,
            "parent_claim_ids": [],
            "receipt": fact["receipt"],
        })
    graph = {
        "schema": CLAIM_GRAPH_SCHEMA,
        "authority": AUTHORITY,
        "event": dict(fact_pack["event"]),
        "source": dict(fact_pack["source"]),
        "claims": claims,
        "warnings": list(fact_pack["warnings"]),
        "insufficiency": list(fact_pack["insufficiency"]),
        "execution": dict(EXECUTION_RECEIPT),
    }
    validate_evidence_pair(fact_pack, graph)
    return graph


def build_evidence_pair(
    transcript: object,
    *,
    index_payload: object,
    indexed_body_sha256: object,
    index_generated_at: object,
) -> tuple[dict[str, Any], dict[str, Any]]:
    fact_pack = build_fact_pack(
        transcript,
        index_payload=index_payload,
        indexed_body_sha256=indexed_body_sha256,
        index_generated_at=index_generated_at,
    )
    graph = build_claim_graph(fact_pack)
    return fact_pack, graph
