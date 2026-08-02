"""Deterministic, receipt-complete earnings event digests.

The evidence graph intentionally extracts *everything*.  This module performs
the next, still-model-free job: select a small and diverse packet of exact
sentences for downstream dossiers, Press, X, and Neural Web context.  Selection
is lexical and fully disclosed in the artifact.  It is a content-routing score,
never a trading score or recommendation.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Mapping

from .contracts import (
    AUTHORITY,
    EXECUTION_RECEIPT,
    KNOWN_INSUFFICIENCY,
    KNOWN_WARNINGS,
    ContractError,
    canonical_json_bytes,
    direct_claim_id,
    event_key,
    normalize_numeric,
    safe_ticker,
    transcript_id,
    validate_event_identity,
    validate_evidence_pair,
    validate_source_receipt,
    validate_span_receipt,
    validate_terminal_transcript,
    verify_fact_pack_against_transcript,
)


DIGEST_SCHEMA = "company_event_digest.v1"
EXTRACTOR_NAME = "earnings_event_digest"
EXTRACTOR_VERSION = "1.0.0"

_DIGEST_ID = re.compile(r"^digest_[0-9a-f]{32}$")
_DIGEST_FACT_ID = re.compile(r"^digestfact_[0-9a-f]{32}$")
_FACT_ID = re.compile(r"^fact_[0-9a-f]{32}$")
_CLAIM_ID = re.compile(r"^claim_[0-9a-f]{32}$")

_CATEGORY_PRIORITY = (
    "guidance",
    "performance",
    "margins",
    "demand",
    "capital_allocation",
    "risks",
    "management_commitments",
    "segment_changes",
    "q_and_a",
)
_CATEGORY_SET = frozenset(_CATEGORY_PRIORITY)

# Phrase lists are deliberately compact and inspectable.  They route exact
# evidence into a digest; they do not infer sentiment, surprise, or direction.
_CATEGORY_PHRASES: dict[str, tuple[str, ...]] = {
    "guidance": (
        "guidance", "outlook", "we expect", "we anticipate", "we forecast",
        "full year", "full-year", "next quarter", "going forward", "target",
    ),
    "performance": (
        "revenue", "sales", "earnings", "eps", "grew", "growth", "declined",
        "increased", "decreased", "operating income", "net income", "cash flow",
    ),
    "margins": (
        "margin", "gross profit", "operating leverage", "profitability",
        "cost of revenue", "cost of sales",
    ),
    "demand": (
        "demand", "orders", "backlog", "bookings", "customer", "customers",
        "usage", "traffic", "volume", "volumes", "churn", "pipeline",
    ),
    "capital_allocation": (
        "capital expenditure", "capex", "buyback", "repurchase", "dividend",
        "debt", "free cash flow", "acquisition", "capital allocation",
    ),
    "risks": (
        "risk", "headwind", "uncertainty", "pressure", "slowdown", "challenge",
        "constraint", "volatile", "weakness", "impact",
    ),
    "management_commitments": (
        "we will", "we plan to", "we remain committed", "we are committed",
        "we intend to", "our priority", "we continue to invest",
    ),
    "segment_changes": (
        "segment", "geography", "region", "international", "north america",
        "enterprise", "consumer", "product mix", "channel mix",
    ),
}

_MANAGEMENT_ROLE_TERMS = (
    "chief executive", "chief financial", "ceo", "cfo", "president",
    "executive", "officer", "management",
)
_Q_AND_A_MARKERS = (
    "question-and-answer", "question and answer", "questions and answers",
    "begin the q&a", "begin the q and a", "open the call for questions",
)
_ANALYST_ROLE_TERMS = ("analyst", "questioner")

_SELECTION_WEIGHTS = {
    "bounded_length": 1,
    "category_keyword": 4,
    "management_role": 1,
    "numeric_evidence": 2,
    "qa_exchange": 1,
}
_SELECTION_REASONS = frozenset(_SELECTION_WEIGHTS)

_DIGEST_KEYS = frozenset({
    "schema", "authority", "digest_id", "event", "source",
    "source_completeness", "selection", "facts", "guidance",
    "segment_changes", "capital_allocation", "risks",
    "management_commitments", "qa_exchanges", "narrative_deltas",
    "issuer_mentions", "relationship_updates", "market_reaction",
    "theme_context", "claims", "citation_coverage", "extractor", "quality",
    "execution",
})
_COMPLETENESS_KEYS = frozenset({"release", "filing", "transcript", "slides", "consensus"})
_SELECTION_KEYS = frozenset({
    "policy", "max_facts", "per_category_cap", "candidate_count",
    "selected_count", "weights",
})
_DIGEST_FACT_KEYS = frozenset({
    "digest_fact_id", "categories", "text", "speaker", "role", "chapter",
    "selection_score", "selection_reasons", "evidence",
})
_EVIDENCE_KEYS = frozenset({
    "claim_id", "fact_id", "kind", "text", "numeric_value", "numeric_unit",
    "receipt",
})
_EXTRACTOR_KEYS = frozenset({"name", "version"})
_QUALITY_KEYS = frozenset({"status", "warnings", "insufficiency"})
_MARKET_REACTION_KEYS = frozenset({"status", "as_of", "security_ids"})

_DIGEST_WARNINGS = KNOWN_WARNINGS | frozenset({
    "selection_bounded", "single_source_transcript_only",
})
_DIGEST_INSUFFICIENCY = KNOWN_INSUFFICIENCY | frozenset({"no_material_sentences"})


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: frozenset[str], *, name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractError(
            f"{name} fields mismatch "
            f"(missing={sorted(expected - actual)}, unsupported={sorted(actual - expected)})"
        )


def _text(value: object, *, field: str, allow_empty: bool = False, limit: int = 4_000) -> str:
    if (
        not isinstance(value, str)
        or "\x00" in value
        or len(value) > limit
        or (not allow_empty and not value)
    ):
        raise ContractError(f"{field} invalid")
    return value


def _codes(value: object, *, allowed: frozenset[str], name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"{name} must be a list of codes")
    if value != sorted(set(value)) or not set(value) <= allowed:
        raise ContractError(f"{name} contains unknown or unordered codes")
    return value


def _digest_fact_id(quote_claim_id: str) -> str:
    return "digestfact_" + sha256(("digest-fact:" + quote_claim_id).encode("utf-8")).hexdigest()[:32]


def _chapter_map(transcript: Mapping[str, Any]) -> list[str]:
    chapters: list[str] = []
    q_and_a = False
    for segment in transcript["segments"]:
        assert isinstance(segment, Mapping)
        speaker = str(segment.get("speaker") or "").casefold()
        role = str(segment.get("role") or "").casefold()
        body = str(segment.get("text") or "").casefold()
        if any(marker in body for marker in _Q_AND_A_MARKERS) or any(
            term in role or term in speaker for term in _ANALYST_ROLE_TERMS
        ):
            q_and_a = True
        chapters.append("q_and_a" if q_and_a else "prepared")
    return chapters


def _categories(text: str, *, chapter: str) -> tuple[list[str], int]:
    low = text.casefold()
    matched: set[str] = set()
    hit_count = 0
    for category, phrases in _CATEGORY_PHRASES.items():
        hits = sum(1 for phrase in phrases if phrase in low)
        if hits:
            matched.add(category)
            hit_count += hits
    if chapter == "q_and_a":
        matched.add("q_and_a")
    return [category for category in _CATEGORY_PRIORITY if category in matched], hit_count


def _is_management_role(speaker: str, role: str) -> bool:
    value = f"{speaker} {role}".casefold()
    return any(term in value for term in _MANAGEMENT_ROLE_TERMS)


def _evidence_order(item: Mapping[str, Any]) -> tuple[int, int, int, str]:
    receipt = item["receipt"]
    return (
        int(receipt["segment_index"]),
        int(receipt["span_start_byte"]),
        0 if item["kind"] == "quote" else 1,
        str(item["fact_id"]),
    )


def _digest_unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(payload)
    unsigned["digest_id"] = "digest_" + ("0" * 32)
    return unsigned


def validate_event_digest(payload: object) -> None:
    """Validate the closed, model-free ``company_event_digest.v1`` contract."""
    row = _mapping(payload, name="event_digest")
    _keys(row, _DIGEST_KEYS, name="event_digest")
    if row.get("schema") != DIGEST_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("event_digest schema or authority mismatch")
    digest_id = row.get("digest_id")
    if not isinstance(digest_id, str) or not _DIGEST_ID.fullmatch(digest_id):
        raise ContractError("event_digest.digest_id invalid")

    event = validate_event_identity(row.get("event"))
    source = validate_source_receipt(row.get("source"))
    if event_key(event) != f"{source['ticker']}/{source['transcript_id']}":
        raise ContractError("event_digest event/source identity mismatch")

    completeness = _mapping(row.get("source_completeness"), name="event_digest.source_completeness")
    _keys(completeness, _COMPLETENESS_KEYS, name="event_digest.source_completeness")
    expected_completeness = {
        "release": "not_ingested",
        "filing": "not_ingested",
        "transcript": "present",
        "slides": "not_ingested",
        "consensus": "unlicensed_absent",
    }
    if dict(completeness) != expected_completeness:
        raise ContractError("event_digest source completeness must disclose transcript-only v1")

    selection = _mapping(row.get("selection"), name="event_digest.selection")
    _keys(selection, _SELECTION_KEYS, name="event_digest.selection")
    if selection.get("policy") != "lexical_diversity_v1" or selection.get("weights") != _SELECTION_WEIGHTS:
        raise ContractError("event_digest selection policy or weights mismatch")
    for key, lo, hi in (
        ("max_facts", 1, 50),
        ("per_category_cap", 1, 10),
        ("candidate_count", 0, 100_000),
        ("selected_count", 0, 50),
    ):
        value = selection.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise ContractError(f"event_digest.selection.{key} invalid")
    if selection["selected_count"] > selection["max_facts"]:
        raise ContractError("event_digest selected_count exceeds max_facts")
    if selection["candidate_count"] < selection["selected_count"]:
        raise ContractError("event_digest candidate_count cannot trail selected_count")

    facts = row.get("facts")
    if not isinstance(facts, list) or len(facts) != selection["selected_count"]:
        raise ContractError("event_digest.facts count mismatch")
    seen_digest_facts: set[str] = set()
    all_claim_ids: set[str] = set()
    prior_fact_order: tuple[int, int, str] | None = None
    fact_categories: dict[str, list[str]] = {}
    for index, item in enumerate(facts):
        fact = _mapping(item, name=f"event_digest.facts[{index}]")
        _keys(fact, _DIGEST_FACT_KEYS, name=f"event_digest.facts[{index}]")
        digest_fact_id = fact.get("digest_fact_id")
        if (
            not isinstance(digest_fact_id, str)
            or not _DIGEST_FACT_ID.fullmatch(digest_fact_id)
            or digest_fact_id in seen_digest_facts
        ):
            raise ContractError("event_digest digest_fact_id invalid or duplicate")
        seen_digest_facts.add(digest_fact_id)
        categories = fact.get("categories")
        if not isinstance(categories, list) or not categories:
            raise ContractError("event_digest fact categories invalid or unordered")
        expected_categories = [category for category in _CATEGORY_PRIORITY if category in set(categories)]
        if categories != expected_categories:
            raise ContractError("event_digest fact categories invalid or unordered")
        fact_categories[digest_fact_id] = categories
        text = _text(fact.get("text"), field=f"event_digest.facts[{index}].text")
        _text(fact.get("speaker"), field=f"event_digest.facts[{index}].speaker", allow_empty=True, limit=400)
        _text(fact.get("role"), field=f"event_digest.facts[{index}].role", allow_empty=True, limit=400)
        if fact.get("chapter") not in {"prepared", "q_and_a"}:
            raise ContractError("event_digest fact chapter invalid")
        score = fact.get("selection_score")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise ContractError("event_digest fact selection_score invalid")
        _codes(
            fact.get("selection_reasons"),
            allowed=_SELECTION_REASONS,
            name=f"event_digest.facts[{index}].selection_reasons",
        )
        evidence = fact.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ContractError("event_digest fact evidence must be non-empty")
        prior_evidence_order: tuple[int, int, int, str] | None = None
        for ev_index, ev_item in enumerate(evidence):
            evidence_row = _mapping(ev_item, name=f"event_digest.facts[{index}].evidence[{ev_index}]")
            _keys(evidence_row, _EVIDENCE_KEYS, name=f"event_digest.facts[{index}].evidence[{ev_index}]")
            claim_id = evidence_row.get("claim_id")
            fact_id = evidence_row.get("fact_id")
            if not isinstance(claim_id, str) or not _CLAIM_ID.fullmatch(claim_id):
                raise ContractError("event_digest evidence claim_id invalid")
            if not isinstance(fact_id, str) or not _FACT_ID.fullmatch(fact_id):
                raise ContractError("event_digest evidence fact_id invalid")
            if claim_id != direct_claim_id(fact_id):
                raise ContractError("event_digest evidence claim_id must bind fact_id")
            if claim_id in all_claim_ids:
                raise ContractError("event_digest evidence claim_id reused")
            all_claim_ids.add(claim_id)
            kind = evidence_row.get("kind")
            if kind not in {"quote", "numeric"}:
                raise ContractError("event_digest evidence kind invalid")
            evidence_text = _text(
                evidence_row.get("text"),
                field=f"event_digest.facts[{index}].evidence[{ev_index}].text",
            )
            validate_span_receipt(
                evidence_row.get("receipt"),
                source_sha256=str(source["body_sha256"]),
                text=evidence_text,
            )
            if kind == "quote":
                if ev_index != 0 or evidence_text != text:
                    raise ContractError("event_digest first evidence must be the selected quote")
                if evidence_row.get("numeric_value") is not None or evidence_row.get("numeric_unit") is not None:
                    raise ContractError("event_digest quote evidence cannot carry numeric fields")
                if digest_fact_id != _digest_fact_id(str(claim_id)):
                    raise ContractError("event_digest digest_fact_id does not bind quote claim")
            else:
                value, unit = normalize_numeric(evidence_text)
                if evidence_row.get("numeric_value") != value or evidence_row.get("numeric_unit") != unit:
                    raise ContractError("event_digest numeric evidence value/unit mismatch")
            order = _evidence_order(evidence_row)
            if prior_evidence_order is not None and order <= prior_evidence_order:
                raise ContractError("event_digest evidence must remain in source order")
            prior_evidence_order = order
        quote_receipt = evidence[0]["receipt"]
        fact_order = (
            int(quote_receipt["segment_index"]),
            int(quote_receipt["span_start_byte"]),
            str(digest_fact_id),
        )
        if prior_fact_order is not None and fact_order <= prior_fact_order:
            raise ContractError("event_digest facts must remain in source order")
        prior_fact_order = fact_order

    category_fields = {
        "guidance": "guidance",
        "segment_changes": "segment_changes",
        "capital_allocation": "capital_allocation",
        "risks": "risks",
        "management_commitments": "management_commitments",
        "qa_exchanges": "q_and_a",
    }
    fact_order_ids = [fact["digest_fact_id"] for fact in facts]
    primary_category_counts: dict[str, int] = {}
    for fact in facts:
        primary = str(fact["categories"][0])
        primary_category_counts[primary] = primary_category_counts.get(primary, 0) + 1
    if any(count > selection["per_category_cap"] for count in primary_category_counts.values()):
        raise ContractError("event_digest selected facts exceed per-category cap")
    for field, category in category_fields.items():
        refs = row.get(field)
        expected = [fact_id for fact_id in fact_order_ids if category in fact_categories[fact_id]]
        if refs != expected:
            raise ContractError(f"event_digest.{field} must exactly reference selected category facts")

    for field in ("narrative_deltas", "issuer_mentions", "relationship_updates", "theme_context"):
        if row.get(field) != []:
            raise ContractError(f"event_digest.{field} is unsupported by transcript-only v1")
    reaction = _mapping(row.get("market_reaction"), name="event_digest.market_reaction")
    _keys(reaction, _MARKET_REACTION_KEYS, name="event_digest.market_reaction")
    if dict(reaction) != {"status": "not_joined", "as_of": None, "security_ids": []}:
        raise ContractError("event_digest market reaction must disclose not_joined v1")

    claims = row.get("claims")
    if claims != sorted(all_claim_ids):
        raise ContractError("event_digest.claims must exactly list selected evidence claims")
    coverage = row.get("citation_coverage")
    expected_coverage = 1.0 if facts else 0.0
    if isinstance(coverage, bool) or not isinstance(coverage, (int, float)) or coverage != expected_coverage:
        raise ContractError("event_digest citation_coverage mismatch")
    extractor = _mapping(row.get("extractor"), name="event_digest.extractor")
    _keys(extractor, _EXTRACTOR_KEYS, name="event_digest.extractor")
    if dict(extractor) != {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION}:
        raise ContractError("event_digest extractor mismatch")
    quality = _mapping(row.get("quality"), name="event_digest.quality")
    _keys(quality, _QUALITY_KEYS, name="event_digest.quality")
    _codes(quality.get("warnings"), allowed=_DIGEST_WARNINGS, name="event_digest.quality.warnings")
    insufficiency = _codes(
        quality.get("insufficiency"),
        allowed=_DIGEST_INSUFFICIENCY,
        name="event_digest.quality.insufficiency",
    )
    if facts:
        if quality.get("status") != "ready" or "no_material_sentences" in insufficiency:
            raise ContractError("non-empty event_digest must be ready")
    elif quality.get("status") != "insufficient" or "no_material_sentences" not in insufficiency:
        raise ContractError("empty event_digest must disclose no_material_sentences")
    if row.get("execution") != EXECUTION_RECEIPT:
        raise ContractError("event_digest must prove zero-provider deterministic execution")

    bounded = "selection_bounded" in quality["warnings"]
    if bounded != (selection["candidate_count"] > selection["selected_count"]):
        raise ContractError("event_digest selection_bounded warning mismatch")
    expected_id = "digest_" + sha256(canonical_json_bytes(_digest_unsigned(row))).hexdigest()[:32]
    if digest_id != expected_id:
        raise ContractError("event_digest.digest_id does not match canonical content")


def _direct_claims_by_fact(claim_graph: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for claim in claim_graph["claims"]:
        if claim["claim_type"] in {"direct_quote", "direct_numeric"}:
            out[str(claim["fact_id"])] = claim
    return out


def build_event_digest(
    fact_pack: object,
    claim_graph: object,
    transcript: object,
    *,
    max_facts: int = 12,
    per_category_cap: int = 3,
) -> dict[str, Any]:
    """Select a bounded, diverse, exact evidence packet for one call."""
    if isinstance(max_facts, bool) or not isinstance(max_facts, int) or not 1 <= max_facts <= 50:
        raise ContractError("max_facts must be an integer from 1 to 50")
    if (
        isinstance(per_category_cap, bool)
        or not isinstance(per_category_cap, int)
        or not 1 <= per_category_cap <= 10
    ):
        raise ContractError("per_category_cap must be an integer from 1 to 10")
    validate_evidence_pair(fact_pack, claim_graph)
    verify_fact_pack_against_transcript(fact_pack, transcript)
    assert isinstance(fact_pack, Mapping)
    assert isinstance(claim_graph, Mapping)
    tx = validate_terminal_transcript(transcript)
    chapters = _chapter_map(tx)
    facts_by_id = {str(fact["fact_id"]): fact for fact in fact_pack["facts"]}
    claims_by_fact = _direct_claims_by_fact(claim_graph)

    candidates: list[dict[str, Any]] = []
    quote_facts = [fact for fact in fact_pack["facts"] if fact["kind"] == "quote"]
    numeric_facts = [fact for fact in fact_pack["facts"] if fact["kind"] == "numeric"]
    for quote in quote_facts:
        receipt = quote["receipt"]
        segment_index = int(receipt["segment_index"])
        segment = tx["segments"][segment_index]
        assert isinstance(segment, Mapping)
        chapter = chapters[segment_index]
        categories, keyword_hits = _categories(str(quote["text"]), chapter=chapter)
        if categories == ["q_and_a"] and any(
            marker in str(quote["text"]).casefold() for marker in _Q_AND_A_MARKERS
        ):
            # A section header is navigation, not a material Q&A exchange.
            continue
        contained_numbers = [
            fact for fact in numeric_facts
            if fact["receipt"]["segment_index"] == segment_index
            and fact["receipt"]["span_start_byte"] >= receipt["span_start_byte"]
            and fact["receipt"]["span_end_byte"] <= receipt["span_end_byte"]
        ]
        if not categories and contained_numbers:
            categories = ["performance"]
        if not categories:
            continue
        speaker = str(segment.get("speaker") or "")
        role = str(segment.get("role") or "")
        reasons: set[str] = set()
        score = 0
        if keyword_hits:
            reasons.add("category_keyword")
            score += _SELECTION_WEIGHTS["category_keyword"] * min(keyword_hits, 3)
        if contained_numbers:
            reasons.add("numeric_evidence")
            score += _SELECTION_WEIGHTS["numeric_evidence"] * min(len(contained_numbers), 3)
        if _is_management_role(speaker, role):
            reasons.add("management_role")
            score += _SELECTION_WEIGHTS["management_role"]
        if chapter == "q_and_a":
            reasons.add("qa_exchange")
            score += _SELECTION_WEIGHTS["qa_exchange"]
        if 40 <= len(str(quote["text"])) <= 600:
            reasons.add("bounded_length")
            score += _SELECTION_WEIGHTS["bounded_length"]

        evidence_facts = [quote] + contained_numbers
        evidence_facts.sort(key=lambda item: (
            int(item["receipt"]["segment_index"]),
            int(item["receipt"]["span_start_byte"]),
            0 if item["kind"] == "quote" else 1,
            str(item["fact_id"]),
        ))
        evidence: list[dict[str, Any]] = []
        for evidence_fact in evidence_facts:
            claim = claims_by_fact[str(evidence_fact["fact_id"])]
            evidence.append({
                "claim_id": claim["claim_id"],
                "fact_id": evidence_fact["fact_id"],
                "kind": evidence_fact["kind"],
                "text": evidence_fact["text"],
                "numeric_value": evidence_fact["numeric_value"],
                "numeric_unit": evidence_fact["numeric_unit"],
                "receipt": dict(evidence_fact["receipt"]),
            })
        quote_claim_id = str(evidence[0]["claim_id"])
        candidates.append({
            "digest_fact_id": _digest_fact_id(quote_claim_id),
            "categories": categories,
            "text": quote["text"],
            "speaker": speaker,
            "role": role,
            "chapter": chapter,
            "selection_score": score,
            "selection_reasons": sorted(reasons),
            "evidence": evidence,
            "_primary_category": categories[0],
            "_source_order": (
                segment_index,
                int(receipt["span_start_byte"]),
                _digest_fact_id(quote_claim_id),
            ),
        })

    ranked = sorted(
        candidates,
        key=lambda item: (-int(item["selection_score"]), item["_source_order"]),
    )
    selected: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    for candidate in ranked:
        primary = str(candidate["_primary_category"])
        if category_counts.get(primary, 0) >= per_category_cap:
            continue
        selected.append(candidate)
        category_counts[primary] = category_counts.get(primary, 0) + 1
        if len(selected) >= max_facts:
            break
    selected.sort(key=lambda item: item["_source_order"])
    for item in selected:
        item.pop("_primary_category", None)
        item.pop("_source_order", None)

    warnings = set(str(code) for code in fact_pack["warnings"])
    warnings.add("single_source_transcript_only")
    if len(candidates) > len(selected):
        warnings.add("selection_bounded")
    insufficiency = set(str(code) for code in fact_pack["insufficiency"])
    if not selected:
        insufficiency.add("no_material_sentences")

    fact_ids = [str(item["digest_fact_id"]) for item in selected]
    claims = sorted({
        str(evidence["claim_id"])
        for item in selected
        for evidence in item["evidence"]
    })
    payload: dict[str, Any] = {
        "schema": DIGEST_SCHEMA,
        "authority": AUTHORITY,
        "digest_id": "digest_" + ("0" * 32),
        "event": dict(fact_pack["event"]),
        "source": dict(fact_pack["source"]),
        "source_completeness": {
            "release": "not_ingested",
            "filing": "not_ingested",
            "transcript": "present",
            "slides": "not_ingested",
            "consensus": "unlicensed_absent",
        },
        "selection": {
            "policy": "lexical_diversity_v1",
            "max_facts": max_facts,
            "per_category_cap": per_category_cap,
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "weights": dict(_SELECTION_WEIGHTS),
        },
        "facts": selected,
        "guidance": [fact_id for fact_id, item in zip(fact_ids, selected) if "guidance" in item["categories"]],
        "segment_changes": [fact_id for fact_id, item in zip(fact_ids, selected) if "segment_changes" in item["categories"]],
        "capital_allocation": [fact_id for fact_id, item in zip(fact_ids, selected) if "capital_allocation" in item["categories"]],
        "risks": [fact_id for fact_id, item in zip(fact_ids, selected) if "risks" in item["categories"]],
        "management_commitments": [fact_id for fact_id, item in zip(fact_ids, selected) if "management_commitments" in item["categories"]],
        "qa_exchanges": [fact_id for fact_id, item in zip(fact_ids, selected) if "q_and_a" in item["categories"]],
        "narrative_deltas": [],
        "issuer_mentions": [],
        "relationship_updates": [],
        "market_reaction": {"status": "not_joined", "as_of": None, "security_ids": []},
        "theme_context": [],
        "claims": claims,
        "citation_coverage": 1.0 if selected else 0.0,
        "extractor": {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION},
        "quality": {
            "status": "ready" if selected else "insufficient",
            "warnings": sorted(warnings),
            "insufficiency": sorted(insufficiency),
        },
        "execution": dict(EXECUTION_RECEIPT),
    }
    payload["digest_id"] = "digest_" + sha256(canonical_json_bytes(_digest_unsigned(payload))).hexdigest()[:32]
    validate_event_digest(payload)
    return payload


def validate_event_digest_against_evidence(
    digest: object,
    fact_pack: object,
    claim_graph: object,
    transcript: object,
) -> None:
    """Replay the digest and prove it is the deterministic evidence selection."""
    validate_event_digest(digest)
    assert isinstance(digest, Mapping)
    selection = digest["selection"]
    rebuilt = build_event_digest(
        fact_pack,
        claim_graph,
        transcript,
        max_facts=int(selection["max_facts"]),
        per_category_cap=int(selection["per_category_cap"]),
    )
    if canonical_json_bytes(digest) != canonical_json_bytes(rebuilt):
        raise ContractError("event_digest does not replay from its evidence pair and transcript")


def event_ref(digest: Mapping[str, Any]) -> str:
    """Stable company-period reference used by downstream dedupe rails."""
    validate_event_digest(digest)
    event = digest["event"]
    return f"earnings:{safe_ticker(event['ticker'])}/{transcript_id(event['transcript_id'])}"
