"""Bounded exact-evidence context and weekly intelligence projections.

These contracts are derivatives of a verified ``earnings.public_wire_manifest``.
They do not fetch, summarize, produce investment scores, or call a model. Their
only editorial operation is deterministic public-excerpt selection. Their main
job is to make the same receipt-bound evidence cheaply usable by product
surfaces without granting it trade or Prophet authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from .contracts import EXECUTION_RECEIPT
from .public_wire import (
    PublicWireContractError,
    verify_public_wire_article,
    verify_public_wire_fact_projection,
    verify_public_wire_manifest,
    wire_slug,
)


CONTEXT_PACKET_SCHEMA = "earnings.context_packet/v1"
CONTEXT_MANIFEST_SCHEMA = "earnings.context_manifest/v1"
WEEKLY_INTELLIGENCE_SCHEMA = "earnings.weekly_intelligence/v1"
PUBLIC_FACT_LIMIT = 2
MAX_CONTEXT_FACTS = 6
MAX_WEEKLY_NOTABLE_RECORDS = 12

_AUTHORITY = {
    "class": "context_only",
    "may_add_candidate": False,
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
    "may_escalate": False,
    "prophet_authority": False,
}
_PACKET_KEYS = frozenset({
    "schema", "context_id", "event", "identities", "source", "admission",
    "categories", "facts", "source_completeness", "links", "authority", "execution",
})
_MANIFEST_KEYS = frozenset({
    "schema", "generation_id", "knowledge_cutoff", "source", "ticker_count",
    "event_count", "objects", "execution",
})
_WEEK_KEYS = frozenset({
    "schema", "week_start", "week_end", "knowledge_cutoff", "source",
    "coverage", "category_pulse", "notable_records", "disclosures", "authority", "execution",
})
_EVENT_KEYS = frozenset({"ticker", "transcript_id", "period", "date"})
_IDENTITY_KEYS = frozenset({"article_id", "packet_id", "story_id", "story_revision_id"})
_SOURCE_KEYS = frozenset({"kind", "source_sha256", "known_at", "correction_status"})
_ADMISSION_KEYS = frozenset({"promotion_tier", "quality_status", "citation_coverage"})
_LINK_KEYS = frozenset({"record", "dossier", "terminal"})
_SOURCE_COMPLETENESS = {
    "release": "not_ingested", "filing": "not_ingested", "transcript": "present",
    "slides": "not_ingested", "consensus": "unlicensed_absent",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARTICLE_ID = re.compile(r"^wirearticle_[0-9a-f]{32}$")
_TICKER = re.compile(r"^[A-Z0-9.\-]{1,16}$")
_TRANSCRIPT = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")
_BOILERPLATE_PREVIEW = re.compile(
    r"\b(safe\s+harbor|forward[- ]looking|operator|replay|webcast|good\s+morning|thank\s+you)\b",
    re.IGNORECASE,
)
_MATERIAL_PREVIEW = re.compile(
    r"\b(revenue|margin|guidance|demand|backlog|growth|profit|cash|bookings|outlook|expect)\b",
    re.IGNORECASE,
)
_NUMBER_PREVIEW = re.compile(
    r"(?:\$?\d[\d,.]*%?|\b\d+(?:\.\d+)?\s*(?:bps|million|billion|percent)\b)",
    re.IGNORECASE,
)
# House law: "validated" in user-facing text is an authority claim. A receipt-bound
# transcript excerpt may use the word (WAVE Q4 FY2025: "validated technology");
# the packet stays verbatim. Public HTML must not — select_public_facts drops
# those excerpts, and refuses the article if every excerpt carries the token.
_AUTHORITY_TOKEN_PREVIEW = re.compile(r"\bvalidated\b|已验证", re.IGNORECASE)


class EarningsContextContractError(ValueError):
    """An exact-evidence context projection violated its closed contract."""


def canonical_json_bytes(payload: object) -> bytes:
    try:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise EarningsContextContractError("context payload is not canonical JSON") from exc


def _closed(value: Mapping[str, Any], keys: frozenset[str], name: str) -> None:
    if set(value) != keys:
        raise EarningsContextContractError(
            f"{name} fields mismatch (missing={sorted(keys - set(value))}, unsupported={sorted(set(value) - keys)})"
        )


def _iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise EarningsContextContractError(f"invalid ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _context_id(unsigned: Mapping[str, Any]) -> str:
    return "earnctx_" + sha256(canonical_json_bytes(unsigned)).hexdigest()[:32]


def _public_fact_score(fact: Mapping[str, Any]) -> int:
    """Rank public preview evidence without creating or changing a claim."""
    text = _quote_text(fact)
    role = str(fact.get("role") or "").lower()
    score = 18 if role in {"executive", "management"} else (-30 if role == "analyst" else 0)
    score += 14 * len(set(str(item) for item in fact.get("categories", []) if str(item) in {
        "performance", "guidance", "demand", "margins", "risks",
    }))
    if fact.get("numeric"):
        score += 12
    if _NUMBER_PREVIEW.search(text):
        score += 8
    if _MATERIAL_PREVIEW.search(text):
        score += 10
    if _BOILERPLATE_PREVIEW.search(text):
        score -= 45
    return score + min(len(text) // 80, 5)


def _quote_text(fact: object) -> str:
    if not isinstance(fact, Mapping):
        return ""
    quote = fact.get("quote") if isinstance(fact.get("quote"), Mapping) else {}
    return str(quote.get("text") or "")


def _carries_authority_token(fact: object) -> bool:
    return bool(_AUTHORITY_TOKEN_PREVIEW.search(_quote_text(fact)))


def select_public_facts(facts: object, *, limit: int = PUBLIC_FACT_LIMIT) -> list[Mapping[str, Any]]:
    """Return the one canonical public excerpt subset in relevance order."""
    if not isinstance(facts, list) or not facts:
        raise EarningsContextContractError("public fact selection requires a non-empty fact list")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > PUBLIC_FACT_LIMIT:
        raise EarningsContextContractError("public fact selection limit invalid")
    clean = [
        (index, fact) for index, fact in enumerate(facts)
        if not _carries_authority_token(fact)
    ]
    if not clean:
        raise EarningsContextContractError(
            "public fact selection found only excerpts carrying a banned authority token"
        )
    ranked = sorted(
        clean, key=lambda row: (-_public_fact_score(row[1]), row[0]),
    )[: min(limit, len(clean))]
    return [fact for _index, fact in ranked]


def build_context_packet(
    article: Mapping[str, Any], *, facts: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project one verified event into a small citation-bearing context packet."""
    verify_public_wire_article(article)
    selected = list(article["facts"])[:MAX_CONTEXT_FACTS] if facts is None else list(facts)
    if not selected or len(selected) > MAX_CONTEXT_FACTS:
        raise EarningsContextContractError("context fact selection must be bounded and non-empty")
    admitted_by_claim = {str(fact["claim_id"]): fact for fact in article["facts"]}
    if any(
        admitted_by_claim.get(str(fact.get("claim_id") or "")) != fact
        for fact in selected
    ):
        raise EarningsContextContractError("context fact selection is not an exact article subset")
    selected_facts = deepcopy(selected)
    categories = sorted({str(category) for fact in selected_facts for category in fact["categories"]})
    event = article["event"]
    packet = article["packet"]
    unsigned: dict[str, Any] = {
        "schema": CONTEXT_PACKET_SCHEMA,
        "context_id": "earnctx_" + ("0" * 32),
        "event": {
            "ticker": str(event["ticker"]), "transcript_id": str(event["transcript_id"]),
            "period": str(event["period"]), "date": str(event["date"]),
        },
        "identities": {
            "article_id": str(article["article_id"]), "packet_id": str(packet["packet_id"]),
            "story_id": str(packet["story_id"]), "story_revision_id": str(packet["story_revision_id"]),
        },
        "source": {
            "kind": str(article["source"]["kind"]),
            "source_sha256": str(article["source"]["body_sha256"]),
            "known_at": str(article["source"]["index_generated_at"]),
            "correction_status": str(article["admission"]["correction_status"]),
        },
        "admission": {
            "promotion_tier": str(article["admission"]["tier"]),
            "quality_status": str(article["admission"]["quality_status"]),
            "citation_coverage": float(article["admission"]["citation_coverage"]),
        },
        "categories": categories,
        "facts": selected_facts,
        "source_completeness": deepcopy(article["source_completeness"]),
        "links": {
            "record": f"/stocks/earnings/{event['slug']}.html",
            "dossier": f"/stocks/{event['ticker']}.html",
            "terminal": (
                "https://app.mastermind-x.com/terminal?"
                f"sym={event['ticker']}&pane=transcripts&tx={event['transcript_id']}"
            ),
        },
        "authority": dict(_AUTHORITY),
        "execution": dict(EXECUTION_RECEIPT),
    }
    unsigned["context_id"] = _context_id(unsigned)
    validate_context_packet(unsigned)
    return unsigned


def validate_context_packet(payload: object) -> None:
    if not isinstance(payload, Mapping):
        raise EarningsContextContractError("context packet must be an object")
    _closed(payload, _PACKET_KEYS, "context packet")
    if payload.get("schema") != CONTEXT_PACKET_SCHEMA:
        raise EarningsContextContractError("context packet schema invalid")
    context_id = payload.get("context_id")
    if not isinstance(context_id, str) or not context_id.startswith("earnctx_") or len(context_id) != 40:
        raise EarningsContextContractError("context id invalid")
    unsigned = dict(payload)
    unsigned["context_id"] = "earnctx_" + ("0" * 32)
    if context_id != _context_id(unsigned):
        raise EarningsContextContractError("context id does not bind payload")
    event = payload.get("event")
    if not isinstance(event, Mapping):
        raise EarningsContextContractError("context event must be an object")
    _closed(event, _EVENT_KEYS, "context event")
    ticker = str(event.get("ticker") or "")
    transcript_id = str(event.get("transcript_id") or "")
    if not _TICKER.fullmatch(ticker) or not _TRANSCRIPT.fullmatch(transcript_id):
        raise EarningsContextContractError("context event identity invalid")
    try:
        event_date = date.fromisoformat(str(event.get("date") or ""))
    except ValueError as exc:
        raise EarningsContextContractError("context event date invalid") from exc
    if not isinstance(event.get("period"), str) or not event["period"] or len(event["period"]) > 120:
        raise EarningsContextContractError("context event period invalid")

    identities = payload.get("identities")
    if not isinstance(identities, Mapping):
        raise EarningsContextContractError("context identities must be an object")
    _closed(identities, _IDENTITY_KEYS, "context identities")
    if not _ARTICLE_ID.fullmatch(str(identities.get("article_id") or "")):
        raise EarningsContextContractError("context article identity invalid")
    for key in ("packet_id", "story_id", "story_revision_id"):
        if not isinstance(identities.get(key), str) or not identities[key] or len(identities[key]) > 300:
            raise EarningsContextContractError(f"context {key} identity invalid")

    source = payload.get("source")
    if not isinstance(source, Mapping):
        raise EarningsContextContractError("context source receipt invalid")
    _closed(source, _SOURCE_KEYS, "context source")
    if source.get("kind") != "transcript" or not _SHA256.fullmatch(str(source.get("source_sha256") or "")):
        raise EarningsContextContractError("context source receipt invalid")
    known_at = _iso(str(source.get("known_at") or ""))
    if known_at.date() < event_date:
        raise EarningsContextContractError("context source is known before its event")
    if source.get("correction_status") not in {"current", "corrected"}:
        raise EarningsContextContractError("context correction status invalid")

    admission = payload.get("admission")
    if not isinstance(admission, Mapping):
        raise EarningsContextContractError("context admission must be an object")
    _closed(admission, _ADMISSION_KEYS, "context admission")
    if (
        admission.get("promotion_tier") not in {"A", "B"}
        or admission.get("quality_status") != "ready"
        or admission.get("citation_coverage") != 1.0
    ):
        raise EarningsContextContractError("context admission invalid")

    facts = payload.get("facts")
    try:
        verify_public_wire_fact_projection(
            facts, source_sha256=str(source["source_sha256"]), max_facts=MAX_CONTEXT_FACTS,
        )
    except PublicWireContractError as exc:
        raise EarningsContextContractError(f"context exact facts invalid: {exc}") from exc
    expected_categories = sorted({
        str(category) for fact in facts for category in fact["categories"]
    })
    if payload.get("categories") != expected_categories:
        raise EarningsContextContractError("context categories do not bind exact facts")
    if payload.get("source_completeness") != _SOURCE_COMPLETENESS:
        raise EarningsContextContractError("context source completeness invalid")

    links = payload.get("links")
    if not isinstance(links, Mapping):
        raise EarningsContextContractError("context links must be an object")
    _closed(links, _LINK_KEYS, "context links")
    slug = wire_slug(ticker, transcript_id)
    expected_links = {
        "record": f"/stocks/earnings/{slug}.html",
        "dossier": f"/stocks/{ticker}.html",
        "terminal": (
            "https://app.mastermind-x.com/terminal?"
            f"sym={ticker}&pane=transcripts&tx={transcript_id}"
        ),
    }
    if dict(links) != expected_links:
        raise EarningsContextContractError("context links do not bind event identity")
    if payload.get("authority") != _AUTHORITY:
        raise EarningsContextContractError("context authority must remain context-only")
    if payload.get("execution") != EXECUTION_RECEIPT:
        raise EarningsContextContractError("context execution must remain token-free")
    forbidden = {"combined_rating", "sentiment", "market_reaction", "opportunity_score", "rank"}
    if forbidden & set(payload):
        raise EarningsContextContractError("context packet contains forbidden inference fields")


def validate_context_packet_at_cutoff(
    payload: object, *, knowledge_cutoff: object,
) -> None:
    """Bind one valid packet to the generation clock that advertises it.

    Packet and manifest receipts are independently content-addressed.  This
    cross-document invariant prevents a correctly re-hashed future packet from
    being smuggled into an older point-in-time generation.
    """
    validate_context_packet(payload)
    assert isinstance(payload, Mapping)  # narrowed by the validator above
    cutoff = _iso(str(knowledge_cutoff or ""))
    known_at = _iso(str(payload["source"]["known_at"]))
    event_date = date.fromisoformat(str(payload["event"]["date"]))
    if known_at > cutoff or event_date > cutoff.date():
        raise EarningsContextContractError(
            "context packet exceeds manifest knowledge cutoff"
        )


def build_context_generation(
    public_manifest: Mapping[str, Any], *, knowledge_cutoff: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Build a small receipt catalog plus one bounded object per ticker."""
    verify_public_wire_manifest(public_manifest)
    cutoff = _iso(knowledge_cutoff) if knowledge_cutoff else None
    articles = [
        article for article in public_manifest["articles"]
        if cutoff is None or _iso(str(article["source"]["index_generated_at"])) <= cutoff
    ]
    articles.sort(
        key=lambda row: (str(row["event"]["date"]), str(row["source"]["index_generated_at"]), str(row["article_id"])),
        reverse=True,
    )
    latest: dict[str, dict[str, Any]] = {}
    for article in articles:
        ticker = str(article["event"]["ticker"])
        latest.setdefault(ticker, build_context_packet(article))
    known_at = max((str(item["source"]["known_at"]) for item in latest.values()), default=(knowledge_cutoff or "1970-01-01T00:00:00Z"))
    objects = {
        ticker: {
            "path": f"{ticker.lower()}.json",
            "context_id": packet["context_id"],
            "sha256": sha256(canonical_json_bytes(packet)).hexdigest(),
            "bytes": len(canonical_json_bytes(packet)),
        }
        for ticker, packet in sorted(latest.items())
    }
    payload: dict[str, Any] = {
        "schema": CONTEXT_MANIFEST_SCHEMA,
        "generation_id": "earnctxgen_" + ("0" * 32),
        "knowledge_cutoff": known_at,
        "source": {
            "generation_id": str(public_manifest["source"]["generation_id"]),
            "manifest_sha256": str(public_manifest["source"]["manifest_sha256"]),
            "wire_manifest_id": str(public_manifest["manifest_id"]),
        },
        "ticker_count": len(latest),
        "event_count": len(articles),
        "objects": objects,
        "execution": dict(EXECUTION_RECEIPT),
    }
    payload["generation_id"] = "earnctxgen_" + sha256(canonical_json_bytes(payload)).hexdigest()[:32]
    validate_context_manifest(payload)
    return payload, {ticker: latest[ticker] for ticker in sorted(latest)}


def build_context_manifest(
    public_manifest: Mapping[str, Any], *, knowledge_cutoff: str | None = None,
) -> dict[str, Any]:
    """Compatibility facade returning only the receipt catalog."""
    return build_context_generation(public_manifest, knowledge_cutoff=knowledge_cutoff)[0]


def validate_context_manifest(payload: object) -> None:
    if not isinstance(payload, Mapping):
        raise EarningsContextContractError("context manifest must be an object")
    _closed(payload, _MANIFEST_KEYS, "context manifest")
    if payload.get("schema") != CONTEXT_MANIFEST_SCHEMA:
        raise EarningsContextContractError("context manifest schema invalid")
    generation_id = payload.get("generation_id")
    if not isinstance(generation_id, str) or not generation_id.startswith("earnctxgen_") or len(generation_id) != 43:
        raise EarningsContextContractError("context generation id invalid")
    unsigned = dict(payload)
    unsigned["generation_id"] = "earnctxgen_" + ("0" * 32)
    expected = "earnctxgen_" + sha256(canonical_json_bytes(unsigned)).hexdigest()[:32]
    if generation_id != expected:
        raise EarningsContextContractError("context generation id does not bind payload")
    objects = payload.get("objects")
    if not isinstance(objects, Mapping) or int(payload.get("ticker_count", -1)) != len(objects):
        raise EarningsContextContractError("context manifest ticker count invalid")
    for ticker, receipt in objects.items():
        if not isinstance(receipt, Mapping) or set(receipt) != {"path", "context_id", "sha256", "bytes"}:
            raise EarningsContextContractError("context object receipt invalid")
        if receipt.get("path") != f"{str(ticker).lower()}.json":
            raise EarningsContextContractError("context object path mismatch")
        if len(str(receipt.get("sha256") or "")) != 64:
            raise EarningsContextContractError("context object sha invalid")
        if not isinstance(receipt.get("bytes"), int) or int(receipt["bytes"]) <= 0:
            raise EarningsContextContractError("context object byte count invalid")
    _iso(str(payload.get("knowledge_cutoff") or ""))
    if payload.get("execution") != EXECUTION_RECEIPT:
        raise EarningsContextContractError("context manifest execution must remain token-free")


def _week_start(value: str) -> date:
    parsed = date.fromisoformat(value)
    return parsed - timedelta(days=parsed.weekday())


def build_weekly_intelligence(
    public_manifest: Mapping[str, Any], *, knowledge_cutoff: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate exact fact categories by event week, with no prose inference."""
    verify_public_wire_manifest(public_manifest)
    cutoff = _iso(knowledge_cutoff) if knowledge_cutoff else None
    grouped: dict[date, list[Mapping[str, Any]]] = defaultdict(list)
    for article in public_manifest["articles"]:
        if cutoff is not None and _iso(str(article["source"]["index_generated_at"])) > cutoff:
            continue
        grouped[_week_start(str(article["event"]["date"]))].append(article)
    ordered_weeks = sorted(grouped)
    prior_share: dict[str, float] = {}
    output: list[dict[str, Any]] = []
    for week in ordered_weeks:
        articles = sorted(
            grouped[week], key=lambda row: (str(row["event"]["date"]), str(row["event"]["ticker"]), str(row["article_id"])),
            reverse=True,
        )
        category_counts: Counter[str] = Counter()
        category_tickers: dict[str, set[str]] = defaultdict(set)
        facts_total = 0
        numeric_total = 0
        corrected = 0
        packets: list[dict[str, Any]] = []
        for article in articles:
            packet = build_context_packet(
                article, facts=select_public_facts(article["facts"]),
            )
            packets.append(packet)
            if article["admission"]["correction_status"] == "corrected":
                corrected += 1
            for fact in article["facts"]:
                facts_total += 1
                numeric_total += len(fact["numeric"])
                ticker = str(article["event"]["ticker"])
                for category in set(str(item) for item in fact["categories"]):
                    category_counts[category] += 1
                    category_tickers[category].add(ticker)
        current_share = {
            category: (count / facts_total if facts_total else 0.0)
            for category, count in category_counts.items()
        }
        pulse = [
            {
                "category": category,
                "fact_count": count,
                "ticker_count": len(category_tickers[category]),
                "share_of_week_facts": round(current_share[category], 6),
                "share_change_vs_prior_week": (
                    round(current_share[category] - prior_share.get(category, 0.0), 6)
                    if prior_share else None
                ),
            }
            for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        notable = sorted(
            packets,
            key=lambda packet: (
                -len(packet["categories"]),
                -sum(len(fact["numeric"]) for fact in packet["facts"]),
                str(packet["event"]["date"]), str(packet["event"]["ticker"]),
            ),
        )[:MAX_WEEKLY_NOTABLE_RECORDS]
        known_at = max(str(packet["source"]["known_at"]) for packet in packets)
        row = {
            "schema": WEEKLY_INTELLIGENCE_SCHEMA,
            "week_start": week.isoformat(),
            "week_end": (week + timedelta(days=6)).isoformat(),
            "knowledge_cutoff": known_at,
            "source": {
                "generation_id": str(public_manifest["source"]["generation_id"]),
                "manifest_sha256": str(public_manifest["source"]["manifest_sha256"]),
                "wire_manifest_id": str(public_manifest["manifest_id"]),
            },
            "coverage": {
                "call_records": len(articles),
                "tickers": len({str(article["event"]["ticker"]) for article in articles}),
                "exact_facts": facts_total,
                "numeric_receipts": numeric_total,
                "corrected_records": corrected,
            },
            "category_pulse": pulse,
            "notable_records": notable,
            "disclosures": {
                "selection": "editorial_relevance_not_opportunity_rank",
                "scope": "admitted_transcript_records_only",
                "historical_completeness": False,
                "unsupported_sources": ["release", "filing", "slides", "consensus", "market_reaction"],
            },
            "authority": dict(_AUTHORITY),
            "execution": dict(EXECUTION_RECEIPT),
        }
        validate_weekly_intelligence(row)
        output.append(row)
        prior_share = current_share
    return list(reversed(output))


def validate_weekly_intelligence(payload: object) -> None:
    if not isinstance(payload, Mapping):
        raise EarningsContextContractError("weekly intelligence must be an object")
    _closed(payload, _WEEK_KEYS, "weekly intelligence")
    if payload.get("schema") != WEEKLY_INTELLIGENCE_SCHEMA:
        raise EarningsContextContractError("weekly intelligence schema invalid")
    start = date.fromisoformat(str(payload.get("week_start")))
    end = date.fromisoformat(str(payload.get("week_end")))
    if start.weekday() != 0 or end != start + timedelta(days=6):
        raise EarningsContextContractError("weekly intelligence window invalid")
    _iso(str(payload.get("knowledge_cutoff") or ""))
    records = payload.get("notable_records")
    if not isinstance(records, list) or len(records) > MAX_WEEKLY_NOTABLE_RECORDS:
        raise EarningsContextContractError("weekly notable records are not bounded")
    for packet in records:
        validate_context_packet_at_cutoff(
            packet, knowledge_cutoff=payload["knowledge_cutoff"],
        )
        event_date = date.fromisoformat(str(packet["event"]["date"]))
        if event_date < start or event_date > end:
            raise EarningsContextContractError("weekly record falls outside its window")
    if payload.get("authority") != _AUTHORITY or payload.get("execution") != EXECUTION_RECEIPT:
        raise EarningsContextContractError("weekly intelligence cannot gain model or decision authority")
