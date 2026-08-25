#!/usr/bin/env python3
"""Byte-offset source-context shadow triage for S1F; never semantic admission."""
from __future__ import annotations

from hashlib import sha256
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping

FORBIDDEN = frozenset({"event_family", "episode", "episode_id", "episode_relationship", "probability", "score", "rank", "market_expectation", "price", "outcome", "counterfactual", "trade", "position", "sizing", "execution", "prophet", "radar", "fusion"})
AUTHORITY = {"can_rank": False, "can_gate": False, "can_size": False,
             "can_originate_signal": False, "can_escalate": False}
_RULESET_PATH = Path(__file__).resolve().parents[2] / "research/dislocation_intelligence/p0_s1f/S1F_TRIAGE_RULESET.json"
FROZEN_RULESET_CANONICAL_SHA256 = "ae50a6d6b20e09a255e1755217018739a7ad0699d9b63c546c413583aedc10ed"


class TriageBlocked(RuntimeError):
    pass


def load_ruleset(ruleset: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    """Load and fail closed on drift from the committed prospective rule law."""
    if ruleset is None:
        try:
            ruleset = json.loads(_RULESET_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TriageBlocked("S1F_TRIAGE_RULESET_UNAVAILABLE") from exc
    value = dict(ruleset)
    expected_precedence = ["S1F-SOURCE-GAP-DEFER", "S1F-8K-STRONG-CURRENT-ITEM", "S1F-REALIZED-CURRENT-CONTEXT", "S1F-CERTIFICATION-ONLY", "S1F-AGREEMENT-DEFINITION-ONLY", "S1F-HYPOTHETICAL-RISK-ONLY", "S1F-ORDINARY-FINANCING-DEFER", "S1F-COMPLETED-RESULTS-DEFER", "S1F-DEFAULT-DEFER"]
    normal = value.get("normalization") or {}
    rule_ids = [rule.get("id") for rule in value.get("rules") or [] if isinstance(rule, Mapping)]
    if (
        value.get("schema") != "mastermind.dislocation_p0.s1f_triage_ruleset.v1"
        or value.get("version") != "S1F-TRIAGE-2026-08-23-v1"
        or value.get("triage_skip_authority") != "NONE"
        or value.get("semantic_admission_authority") != "NONE"
        or value.get("authority") != AUTHORITY
        or value.get("precedence") != expected_precedence
        or rule_ids != expected_precedence[:-1]
        or normal.get("window_bytes_before") != 768
        or normal.get("window_bytes_after") != 768
        or normal.get("case_folding") != "ASCII_ONLY"
        or normal.get("offset_unit") != "raw_byte"
        or set(value.get("forbidden_output_fields") or ()) != FORBIDDEN
    ):
        raise TriageBlocked("S1F_TRIAGE_RULESET_EXECUTABLE_DRIFT")
    digest = sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    if digest != FROZEN_RULESET_CANONICAL_SHA256:
        raise TriageBlocked("S1F_TRIAGE_RULESET_HASH_MISMATCH")
    return value, digest


def _span(data: bytes, start: int, end: int) -> dict[str, Any]:
    return {"start": start, "end": end, "excerpt": data[start:end].decode("latin-1")}


def _find(data: bytes, pattern: bytes) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in re.finditer(re.escape(pattern), data, flags=re.IGNORECASE)]


def _near(data: bytes, start: int, end: int, terms: tuple[bytes, ...], width: int = 768) -> bool:
    context = data[max(0, start - width):min(len(data), end + width)].lower()
    return any(term.lower() in context for term in terms)


def _rule_map(ruleset: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(rule["id"]): rule
        for rule in ruleset.get("rules") or []
        if isinstance(rule, Mapping) and isinstance(rule.get("id"), str)
    }


def _ascii_terms(values: Any) -> tuple[bytes, ...]:
    if not isinstance(values, list) or not values or not all(
        isinstance(value, str) and value.isascii() for value in values
    ):
        raise TriageBlocked("S1F_TRIAGE_RULESET_SIGNATURE_INVALID")
    return tuple(value.encode("ascii") for value in values)


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TriageBlocked("S1F_ACCEPTED_AT_INVALID") from exc
    if parsed.tzinfo is None:
        raise TriageBlocked("S1F_ACCEPTED_AT_INVALID")
    return parsed.astimezone(timezone.utc)


def _document_has_all_signature_groups(data: bytes, groups: Any) -> bool:
    if not isinstance(groups, list) or not groups:
        raise TriageBlocked("S1F_TRIAGE_RULESET_SIGNATURE_INVALID")
    lowered = data.lower()
    return all(any(term.lower() in lowered for term in _ascii_terms(group)) for group in groups)


def _forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).lower() in FORBIDDEN or _forbidden(child) for key, child in value.items())
    if isinstance(value, (list, tuple)):
        return any(_forbidden(child) for child in value)
    return False


def triage_packet(packet: Mapping[str, Any], *, ruleset: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Classify source context only. Missing or ambiguous context is DEFER.

    The matched FTS document is mandatory. A separately supplied primary document
    may add context, but it can never substitute for the matched document.
    """
    frozen_ruleset, ruleset_sha256 = load_ruleset(ruleset)
    rules = _rule_map(frozen_ruleset)
    if _forbidden(packet):
        raise TriageBlocked("triage input contains forbidden semantic/market field")
    docs = packet.get("source_documents")
    if not isinstance(packet.get("accepted_at"), str) or not packet.get("accepted_at"):
        return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", [], [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
    try:
        accepted_at = _parse_timestamp(str(packet["accepted_at"]))
    except TriageBlocked:
        return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", [], [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
    if not isinstance(docs, Mapping):
        return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", [], [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
    expected_by_filename: dict[str, set[str]] = {}
    for edge in packet.get("query_edges") or []:
        if not isinstance(edge, Mapping):
            return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", [], [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
        filename = str(edge.get("filename") or "").strip()
        phrase = str(edge.get("phrase") or "").strip()
        if not filename or not phrase or not phrase.isascii():
            return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", [], [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
        expected_by_filename.setdefault(filename, set()).add(phrase)
    phrases = sorted({phrase for found in expected_by_filename.values() for phrase in found})
    if not phrases or not expected_by_filename:
        return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", [], [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
    exact = packet.get("exact_matched_documents")
    if not isinstance(exact, list) or not exact:
        return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", [], [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
    occurrences: list[dict[str, Any]] = []
    matched_docs: list[tuple[str, bytes]] = []
    seen_filenames: set[str] = set()
    for entry in exact:
        if (
            not isinstance(entry, Mapping)
            or not isinstance(entry.get("filename"), str)
            or not isinstance(entry.get("document_sha256"), str)
            or not isinstance(entry.get("query_phrases"), list)
        ):
            return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", occurrences, [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
        filename = str(entry["filename"])
        if filename in seen_filenames or filename not in expected_by_filename:
            return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", occurrences, [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
        seen_filenames.add(filename)
        if set(entry["query_phrases"]) != expected_by_filename[filename]:
            return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", occurrences, [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
        document_sha = str(entry["document_sha256"])
        source = docs.get(document_sha)
        if not isinstance(source, bytes) or sha256(source).hexdigest() != document_sha:
            return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", occurrences, [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
        matched_docs.append((document_sha, source))
        for phrase in entry["query_phrases"]:
            if not isinstance(phrase, str) or not phrase.isascii() or phrase not in phrases:
                return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", occurrences, [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
            hits = _find(source, phrase.encode("ascii"))
            if not hits:
                return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", occurrences, [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
            occurrences.extend({"filename": filename, "phrase": phrase, "document_sha256": document_sha, **_span(source, start, end)} for start, end in hits)
    if seen_filenames != set(expected_by_filename):
        return _result(packet, "SOURCE_CONTEXT_INCOMPLETE", "DEFER", occurrences, [], "S1F-SOURCE-GAP-DEFER", ruleset_sha256)
    form = str(packet.get("form") or "")
    item_codes = {str(value) for value in packet.get("item_codes") or []}
    strong_rule = rules["S1F-8K-STRONG-CURRENT-ITEM"]
    item_thresholds = strong_rule.get("accepted_at_not_before_by_item")
    if not isinstance(item_thresholds, Mapping):
        raise TriageBlocked("S1F_TRIAGE_RULESET_SIGNATURE_INVALID")
    if form == "8-K":
        for item in strong_rule.get("items_any") or []:
            threshold = item_thresholds.get(item)
            if item in item_codes and isinstance(threshold, str) and accepted_at >= _parse_timestamp(threshold):
                evidence = [
                    {"evidence_kind": "canonical_metadata", "field": "item_codes", "value": item},
                    {"evidence_kind": "canonical_metadata", "field": "accepted_at", "value": packet["accepted_at"]},
                    {"rule_id": strong_rule["id"], **occurrences[0]},
                ]
                return _result(
                    packet, str(strong_rule["category"]), str(strong_rule["disposition"]),
                    occurrences, evidence, str(strong_rule["id"]), ruleset_sha256,
                )
    realized_rule = rules["S1F-REALIZED-CURRENT-CONTEXT"]
    realized_terms = _ascii_terms(realized_rule.get("realized_signatures_ascii"))
    source_by_hash = dict(matched_docs)
    # Additive primary/event documents are separately labelled and can supply
    # context only after all exact matched members have replayed successfully.
    for entry in packet.get("additive_context_documents") or []:
        if not isinstance(entry, Mapping) or entry.get("role") not in {"CANONICAL_PRIMARY_CURRENT_REPORT", "CANONICAL_EVENT_OR_PRESS_RELEASE_EXHIBIT"}:
            continue
        doc_sha = entry.get("document_sha256")
        if isinstance(doc_sha, str) and isinstance(docs.get(doc_sha), bytes) and sha256(docs[doc_sha]).hexdigest() == doc_sha:
            source_by_hash[doc_sha] = docs[doc_sha]
            for phrase in phrases:
                occurrences.extend({"phrase": phrase, "document_sha256": doc_sha, **_span(docs[doc_sha], start, end)} for start, end in _find(docs[doc_sha], phrase.encode("ascii")))
    realized_occurrence = next((
        item for item in occurrences
        if _near(source_by_hash[item["document_sha256"]], item["start"], item["end"], realized_terms)
    ), None)
    if realized_occurrence is not None:
        return _result(
            packet, str(realized_rule["category"]), str(realized_rule["disposition"]),
            occurrences, [{"rule_id": realized_rule["id"], **realized_occurrence}],
            str(realized_rule["id"]), ruleset_sha256,
        )
    # Hard refusal requires every occurrence to be completely accounted for by one deterministic context.
    certification = rules["S1F-CERTIFICATION-ONLY"]
    certification_terms = tuple(
        term for group in certification["document_signatures_ascii_all_groups"]
        for term in _ascii_terms(group)
    )
    if (
        all(_document_has_all_signature_groups(source_by_hash[item["document_sha256"]], certification["document_signatures_ascii_all_groups"]) for item in occurrences)
        and all(_near(source_by_hash[item["document_sha256"]], item["start"], item["end"], certification_terms) for item in occurrences)
    ):
        return _result(packet, str(certification["category"]), str(certification["disposition"]), occurrences,
                       [{"rule_id": certification["id"], **item} for item in occurrences], str(certification["id"]), ruleset_sha256)

    agreement = rules["S1F-AGREEMENT-DEFINITION-ONLY"]
    agreement_terms = _ascii_terms(agreement.get("occurrence_context_signatures_ascii"))
    structure_terms = _ascii_terms(agreement.get("structural_document_signatures_ascii"))
    if (
        all(any(term.lower() in source_by_hash[item["document_sha256"]].lower() for term in structure_terms) for item in occurrences)
        and all(_near(source_by_hash[item["document_sha256"]], item["start"], item["end"], agreement_terms) for item in occurrences)
    ):
        return _result(packet, str(agreement["category"]), str(agreement["disposition"]), occurrences,
                       [{"rule_id": agreement["id"], **item} for item in occurrences], str(agreement["id"]), ruleset_sha256)

    hypothetical = rules["S1F-HYPOTHETICAL-RISK-ONLY"]
    hypothetical_terms = _ascii_terms(hypothetical.get("occurrence_context_signatures_ascii"))
    if all(_near(source_by_hash[item["document_sha256"]], item["start"], item["end"], hypothetical_terms) for item in occurrences):
        return _result(packet, str(hypothetical["category"]), str(hypothetical["disposition"]), occurrences,
                       [{"rule_id": hypothetical["id"], **item} for item in occurrences], str(hypothetical["id"]), ruleset_sha256)

    financing = rules["S1F-ORDINARY-FINANCING-DEFER"]
    financing_terms = _ascii_terms(financing.get("signatures_ascii"))
    if all(_near(source_by_hash[item["document_sha256"]], item["start"], item["end"], financing_terms) for item in occurrences):
        return _result(packet, str(financing["category"]), str(financing["disposition"]), occurrences, [], str(financing["id"]), ruleset_sha256)

    results = rules["S1F-COMPLETED-RESULTS-DEFER"]
    results_terms = _ascii_terms(results.get("signatures_ascii"))
    if all(_near(source_by_hash[item["document_sha256"]], item["start"], item["end"], results_terms) for item in occurrences):
        return _result(packet, str(results["category"]), str(results["disposition"]), occurrences, [], str(results["id"]), ruleset_sha256)

    default = frozen_ruleset["default"]
    return _result(packet, str(default["category"]), str(default["disposition"]), occurrences, [], str(default["rule_id"]), ruleset_sha256)


def _result(packet: Mapping[str, Any], category: str, disposition: str, occurrences: list[dict[str, Any]], evidence: list[dict[str, Any]], rule_id: str, ruleset_sha256: str | None = None) -> dict[str, Any]:
    result = {"schema": "mastermind.dislocation_p0.s1f_source_context_triage.v1",
              "packet_id": str(packet.get("packet_id") or ""), "source_context_category": category,
              "shadow_disposition": disposition, "rule_ids": [rule_id], "triage_ruleset_sha256": ruleset_sha256 or load_ruleset()[1], "phrase_occurrences": occurrences,
              "evidence": evidence, "authority": dict(AUTHORITY)}
    if _forbidden(result):
        raise TriageBlocked("triage result contains forbidden field")
    return result
