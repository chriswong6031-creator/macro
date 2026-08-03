"""Deterministic public projection for receipt-bound earnings call records.

This module is intentionally *not* a second Press writer.  The upstream
``canonical_story.v1`` object is source-ready, has no prose/SEO authority, and
is deliberately fail-closed for canonical emission.  The public wire is a
separate presentation contract: it may show only verified, verbatim approved
spans plus non-claim template labels derived from the event identity.

The boundary is useful for two reasons:

* a public record can be useful before a model-written article is admitted; and
* a source-ready story can never become an unbounded public claim merely
  because a static-site builder happened to see it.

No function here calls a model, summarizes a span, changes a promotion tier,
or reads ``story.copy`` / ``story.seo`` prose fields.  Callers must validate
the packet-store receipt before passing a packet into this compiler.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence

from .contracts import EXECUTION_RECEIPT, canonical_json_bytes, sha256_bytes
from .story import article_receipt_floor
from .story_packets import validate_story_packet


PUBLIC_WIRE_ARTICLE_SCHEMA = "earnings.public_wire_article/v1"
PUBLIC_WIRE_MANIFEST_SCHEMA = "earnings.public_wire_manifest/v1"
PUBLIC_WIRE_TEMPLATE_VERSION = "exact-evidence-template-v1"

_ARTICLE_ID = re.compile(r"^wirearticle_[0-9a-f]{32}$")
_MANIFEST_ID = re.compile(r"^wiremanifest_[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TICKER = re.compile(r"^[A-Z0-9.\-]{1,16}$")
_TRANSCRIPT = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")

_ARTICLE_KEYS = frozenset({
    "schema", "article_id", "packet", "event", "source", "admission",
    "facts", "source_completeness", "execution",
})
_PACKET_KEYS = frozenset({
    "generation_id", "packet_id", "story_id", "story_revision_id",
    "object_key", "object_sha256", "object_bytes",
})
_EVENT_KEYS = frozenset({"ticker", "transcript_id", "period", "date", "title", "slug"})
_SOURCE_KEYS = frozenset({
    "kind", "locator", "body_sha256", "body_bytes", "index_generated_at",
    "index_sha256",
})
_ADMISSION_KEYS = frozenset({
    "status", "tier", "citation_coverage", "quality_status", "correction_status",
    "template_version", "copy_scope",
})
_FACT_KEYS = frozenset({
    "claim_id", "quote", "speaker", "role", "chapter", "categories", "numeric",
})
_SPAN_KEYS = frozenset({"claim_id", "kind", "text", "receipt"})
_RECEIPT_KEYS = frozenset({
    "source_sha256", "segment_sha256", "segment_index", "segment_bytes",
    "span_start_byte", "span_end_byte", "text_sha256",
})
_MANIFEST_KEYS = frozenset({
    "schema", "manifest_id", "status", "source", "articles", "routes", "execution",
})
_MANIFEST_SOURCE_KEYS = frozenset({
    "generation_id", "manifest_sha256", "packet_count", "packet_manifest_schema",
})
_ROUTE_KEYS = frozenset({"article_id", "url_path", "canonical", "lastmod"})


class PublicWireContractError(ValueError):
    """An upstream packet cannot safely enter the public evidence wire."""


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicWireContractError(f"{name} must be an object")
    return value


def _closed_keys(value: Mapping[str, Any], expected: frozenset[str], *, name: str) -> None:
    if set(value) != expected:
        raise PublicWireContractError(
            f"{name} fields mismatch (missing={sorted(expected - set(value))}, "
            f"unsupported={sorted(set(value) - expected)})"
        )


def _text(value: object, *, name: str, limit: int = 8_000) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > limit:
        raise PublicWireContractError(f"{name} invalid")
    return value


def _sha(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PublicWireContractError(f"{name} must be sha256 hex")
    return value


def _article_unsigned(article: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(article)
    unsigned["article_id"] = "wirearticle_" + ("0" * 32)
    return unsigned


def _manifest_unsigned(manifest: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(manifest)
    unsigned["manifest_id"] = "wiremanifest_" + ("0" * 32)
    return unsigned


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + sha256(canonical_json_bytes(payload)).hexdigest()[:32]


def wire_slug(ticker: object, transcript_id: object) -> str:
    """Return the compiler-owned, event-identity-only public URL slug."""
    symbol = _text(ticker, name="ticker", limit=16).upper()
    tx_id = _text(transcript_id, name="transcript_id", limit=80).lower()
    if not _TICKER.fullmatch(symbol) or not _TRANSCRIPT.fullmatch(tx_id):
        raise PublicWireContractError("event identity cannot form a public wire slug")
    return f"{symbol.lower().replace('.', '-')}-{tx_id}-call-record"


def _receipt_projection(span: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _mapping(span.get("receipt"), name="approved span receipt")
    _closed_keys(receipt, _RECEIPT_KEYS, name="approved span receipt")
    text = _text(span.get("text"), name="approved span text", limit=4_000)
    if sha256(text.encode("utf-8")).hexdigest() != receipt.get("text_sha256"):
        raise PublicWireContractError("approved span text receipt mismatch")
    for key in ("source_sha256", "segment_sha256", "text_sha256"):
        _sha(receipt.get(key), name=f"approved span receipt.{key}")
    for key in ("segment_index", "segment_bytes", "span_start_byte", "span_end_byte"):
        value = receipt.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PublicWireContractError(f"approved span receipt.{key} invalid")
    if int(receipt["span_end_byte"]) <= int(receipt["span_start_byte"]):
        raise PublicWireContractError("approved span receipt byte range invalid")
    return {
        "claim_id": _text(span.get("claim_id"), name="approved span claim_id", limit=64),
        "kind": _text(span.get("kind"), name="approved span kind", limit=16),
        "text": text,
        "receipt": dict(receipt),
    }


def _verify_compiler_admission(packet: Mapping[str, Any], *, policy_snapshot: Mapping[str, Any]) -> None:
    """Fail closed before a source-ready packet becomes a public record."""
    # The upstream closed contract proves the story was built from bounded
    # transcript evidence.  It also keeps source-ready prose/SEO empty.
    try:
        validate_story_packet(packet, policy=policy_snapshot)
    except Exception as exc:  # noqa: BLE001 - convert contract details to this boundary.
        raise PublicWireContractError(f"upstream story packet is invalid: {exc}") from exc

    story = _mapping(packet.get("story"), name="packet.story")
    digest = _mapping(packet.get("digest"), name="packet.digest")
    source = _mapping(story.get("source"), name="packet.story.source")
    promotion = _mapping(story.get("promotion"), name="packet.story.promotion")
    correction = _mapping(story.get("correction"), name="packet.story.correction")
    copy = _mapping(story.get("copy"), name="packet.story.copy")
    seo = _mapping(story.get("seo"), name="packet.story.seo")

    # This public compiler deliberately remains compatible with the source-ready
    # contract.  It does not treat source_ready as permission to use its empty
    # prose fields; it only permits a fixed evidence-record layout.
    if story.get("status") != "source_ready":
        raise PublicWireContractError("only source_ready packets may enter the exact-evidence compiler")
    if dict(copy) != {
        "headline": None,
        "dek": None,
        "sections": [],
        "conclusion": None,
        "uncertainty_disclosure": None,
    }:
        raise PublicWireContractError("source-ready packet unexpectedly contains copy")
    if seo.get("indexing") != "noindex_until_approved":
        raise PublicWireContractError("upstream source-ready SEO boundary changed")
    if promotion.get("article_eligible") is not True or promotion.get("tier") not in {"A", "B"}:
        raise PublicWireContractError("packet does not meet governed article eligibility")
    if story.get("digest", {}).get("citation_coverage") != 1.0 or story.get("digest", {}).get("quality_status") != "ready":
        raise PublicWireContractError("packet lacks receipt-complete ready digest")
    if digest.get("citation_coverage") != 1.0 or digest.get("quality", {}).get("status") != "ready":
        raise PublicWireContractError("packet digest is not citation-complete and ready")
    if source.get("source_kind") != "transcript":
        raise PublicWireContractError("public wire currently permits transcript records only")
    if correction.get("status") not in {"current", "corrected"}:
        raise PublicWireContractError("packet correction state is unsupported")
    if packet.get("execution") != EXECUTION_RECEIPT:
        raise PublicWireContractError("public wire permits deterministic packets only")


def compile_public_wire_article(
    packet: Mapping[str, Any],
    *,
    policy_snapshot: Mapping[str, Any],
    generation_id: str,
    object_key: str,
    object_sha256: str,
    object_bytes: int,
) -> dict[str, Any]:
    """Compile a verified packet into a closed, exact-evidence page payload.

    ``policy_snapshot`` comes from the same aggregate packet manifest as the
    object receipt.  It is transiently injected for upstream contract replay
    and never enters the public payload.
    """
    if not isinstance(generation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", generation_id):
        raise PublicWireContractError("story packet generation id invalid")
    if not isinstance(object_key, str) or not object_key.startswith("objects/") or not object_key.endswith(".json"):
        raise PublicWireContractError("story packet object key invalid")
    _sha(object_sha256, name="story packet object sha256")
    if isinstance(object_bytes, bool) or not isinstance(object_bytes, int) or object_bytes <= 0:
        raise PublicWireContractError("story packet object bytes invalid")

    # Keep the public compiler separate from the upstream payload and avoid
    # mutating a packet object a caller might reuse for a stricter rail.
    _verify_compiler_admission(packet, policy_snapshot=policy_snapshot)

    story = _mapping(packet["story"], name="packet.story")
    digest = _mapping(packet["digest"], name="packet.digest")
    event = _mapping(story["event"], name="packet.story.event")
    source = _mapping(story["source"], name="packet.story.source")
    correction = _mapping(story["correction"], name="packet.story.correction")
    promotion = _mapping(story["promotion"], name="packet.story.promotion")
    approved = [_receipt_projection(_mapping(item, name="approved span")) for item in story["approved_spans"]]
    approved_by_claim = {str(item["claim_id"]): item for item in approved}
    if len(approved_by_claim) != len(approved):
        raise PublicWireContractError("approved span claim ids are not unique")

    facts: list[dict[str, Any]] = []
    seen_claims: set[str] = set()
    for raw_fact in digest["facts"]:
        fact = _mapping(raw_fact, name="digest fact")
        evidence = fact.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise PublicWireContractError("digest fact evidence missing")
        first = _mapping(evidence[0], name="digest fact quote")
        quote_claim = str(first.get("claim_id") or "")
        quote = approved_by_claim.get(quote_claim)
        if quote is None or quote["kind"] != "quote" or quote["text"] != fact.get("text"):
            raise PublicWireContractError("digest quote is not an approved exact span")
        numeric: list[dict[str, Any]] = []
        for raw_evidence in evidence[1:]:
            item = _mapping(raw_evidence, name="digest fact numeric evidence")
            claim_id = str(item.get("claim_id") or "")
            span = approved_by_claim.get(claim_id)
            if span is None or span["kind"] != "numeric" or span["text"] != item.get("text"):
                raise PublicWireContractError("digest numeric is not an approved exact span")
            numeric.append(span)
            seen_claims.add(claim_id)
        categories = fact.get("categories")
        if not isinstance(categories, list) or not categories or any(not isinstance(value, str) for value in categories):
            raise PublicWireContractError("digest fact categories invalid")
        facts.append({
            "claim_id": quote_claim,
            "quote": quote,
            "speaker": str(fact.get("speaker") or ""),
            "role": str(fact.get("role") or ""),
            "chapter": str(fact.get("chapter") or ""),
            "categories": list(categories),
            "numeric": numeric,
        })
        seen_claims.add(quote_claim)

    if seen_claims != set(approved_by_claim):
        raise PublicWireContractError("wire facts do not cover every approved span exactly once")
    source_sha = _sha(source.get("body_sha256"), name="story source body sha256")
    for span in approved:
        if span["receipt"]["source_sha256"] != source_sha:
            raise PublicWireContractError("approved span points at another source body")

    ticker = _text(event.get("ticker"), name="event ticker", limit=16).upper()
    transcript_id = _text(event.get("transcript_id"), name="event transcript id", limit=80)
    if not _TICKER.fullmatch(ticker) or not _TRANSCRIPT.fullmatch(transcript_id):
        raise PublicWireContractError("event identity invalid")
    slug = wire_slug(ticker, transcript_id)
    article: dict[str, Any] = {
        "schema": PUBLIC_WIRE_ARTICLE_SCHEMA,
        "article_id": "wirearticle_" + ("0" * 32),
        "packet": {
            "generation_id": generation_id,
            "packet_id": _text(packet.get("packet_id"), name="packet id", limit=80),
            "story_id": _text(story.get("story_id"), name="story id", limit=80),
            "story_revision_id": _text(story.get("story_revision_id"), name="story revision id", limit=80),
            "object_key": object_key,
            "object_sha256": object_sha256,
            "object_bytes": object_bytes,
        },
        "event": {
            "ticker": ticker,
            "transcript_id": transcript_id,
            "period": _text(event.get("period"), name="event period", limit=120),
            "date": _text(event.get("date"), name="event date", limit=32),
            "title": _text(event.get("title"), name="event title", limit=400),
            "slug": slug,
        },
        "source": {
            "kind": _text(source.get("source_kind"), name="source kind", limit=40),
            "locator": _text(source.get("locator"), name="source locator", limit=500),
            "body_sha256": source_sha,
            "body_bytes": int(source.get("body_bytes") or 0),
            "index_generated_at": _text(source.get("index_generated_at"), name="source indexed at", limit=64),
            "index_sha256": _sha(source.get("index_sha256"), name="source index sha256"),
        },
        "admission": {
            "status": "verified_exact_evidence",
            "tier": str(promotion["tier"]),
            "citation_coverage": 1.0,
            "quality_status": "ready",
            "correction_status": str(correction["status"]),
            "template_version": PUBLIC_WIRE_TEMPLATE_VERSION,
            "copy_scope": "approved_spans_only",
        },
        "facts": facts,
        "source_completeness": dict(_mapping(digest["source_completeness"], name="source completeness")),
        "execution": dict(EXECUTION_RECEIPT),
    }
    article["article_id"] = _stable_id("wirearticle_", _article_unsigned(article))
    verify_public_wire_article(article)
    return article


def verify_public_wire_article(payload: object) -> None:
    """Verify the standalone public payload without reopening the packet store."""
    article = _mapping(payload, name="public wire article")
    _closed_keys(article, _ARTICLE_KEYS, name="public wire article")
    if article.get("schema") != PUBLIC_WIRE_ARTICLE_SCHEMA:
        raise PublicWireContractError("public wire article schema invalid")
    article_id = article.get("article_id")
    if not isinstance(article_id, str) or not _ARTICLE_ID.fullmatch(article_id):
        raise PublicWireContractError("public wire article id invalid")
    if article_id != _stable_id("wirearticle_", _article_unsigned(article)):
        raise PublicWireContractError("public wire article id does not bind payload")

    packet = _mapping(article.get("packet"), name="public wire article packet")
    _closed_keys(packet, _PACKET_KEYS, name="public wire article packet")
    if not isinstance(packet.get("generation_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", packet["generation_id"]):
        raise PublicWireContractError("public wire packet generation invalid")
    for key in ("packet_id", "story_id", "story_revision_id", "object_key"):
        _text(packet.get(key), name=f"public wire packet {key}", limit=300)
    _sha(packet.get("object_sha256"), name="public wire packet object sha256")
    if isinstance(packet.get("object_bytes"), bool) or not isinstance(packet.get("object_bytes"), int) or packet["object_bytes"] <= 0:
        raise PublicWireContractError("public wire packet object bytes invalid")

    event = _mapping(article.get("event"), name="public wire event")
    _closed_keys(event, _EVENT_KEYS, name="public wire event")
    ticker = _text(event.get("ticker"), name="public wire event ticker", limit=16)
    transcript_id = _text(event.get("transcript_id"), name="public wire event transcript id", limit=80)
    if not _TICKER.fullmatch(ticker) or not _TRANSCRIPT.fullmatch(transcript_id):
        raise PublicWireContractError("public wire event identity invalid")
    if event.get("slug") != wire_slug(ticker, transcript_id):
        raise PublicWireContractError("public wire slug does not bind event identity")
    for key in ("period", "date", "title"):
        _text(event.get(key), name=f"public wire event {key}", limit=400)

    source = _mapping(article.get("source"), name="public wire source")
    _closed_keys(source, _SOURCE_KEYS, name="public wire source")
    for key in ("kind", "locator", "index_generated_at"):
        _text(source.get(key), name=f"public wire source {key}", limit=500)
    source_sha = _sha(source.get("body_sha256"), name="public wire source body sha256")
    _sha(source.get("index_sha256"), name="public wire source index sha256")
    if isinstance(source.get("body_bytes"), bool) or not isinstance(source.get("body_bytes"), int) or source["body_bytes"] <= 0:
        raise PublicWireContractError("public wire source bytes invalid")

    admission = _mapping(article.get("admission"), name="public wire admission")
    _closed_keys(admission, _ADMISSION_KEYS, name="public wire admission")
    if dict(admission) != {
        "status": "verified_exact_evidence",
        "tier": admission.get("tier"),
        "citation_coverage": 1.0,
        "quality_status": "ready",
        "correction_status": admission.get("correction_status"),
        "template_version": PUBLIC_WIRE_TEMPLATE_VERSION,
        "copy_scope": "approved_spans_only",
    }:
        raise PublicWireContractError("public wire admission contract invalid")
    if admission.get("tier") not in {"A", "B"} or admission.get("correction_status") not in {"current", "corrected"}:
        raise PublicWireContractError("public wire admission state invalid")

    facts = article.get("facts")
    if not isinstance(facts, list) or not facts:
        raise PublicWireContractError("public wire needs at least one exact fact")
    claims: set[str] = set()
    numeric_values: set[tuple[str, str]] = set()
    for index, raw_fact in enumerate(facts):
        fact = _mapping(raw_fact, name=f"public wire fact {index}")
        _closed_keys(fact, _FACT_KEYS, name=f"public wire fact {index}")
        quote = _mapping(fact.get("quote"), name=f"public wire fact {index} quote")
        _closed_keys(quote, _SPAN_KEYS, name=f"public wire fact {index} quote")
        if quote.get("kind") != "quote" or quote.get("claim_id") != fact.get("claim_id"):
            raise PublicWireContractError("public wire quote binding invalid")
        _verify_wire_span(quote, source_sha=source_sha, claims=claims, numeric_values=numeric_values)
        for key in ("speaker", "role", "chapter"):
            if not isinstance(fact.get(key), str) or len(fact[key]) > 400:
                raise PublicWireContractError(f"public wire fact {key} invalid")
        categories = fact.get("categories")
        if not isinstance(categories, list) or not categories or any(not isinstance(item, str) for item in categories):
            raise PublicWireContractError("public wire fact categories invalid")
        numeric = fact.get("numeric")
        if not isinstance(numeric, list):
            raise PublicWireContractError("public wire fact numeric invalid")
        for raw_span in numeric:
            span = _mapping(raw_span, name="public wire numeric span")
            _closed_keys(span, _SPAN_KEYS, name="public wire numeric span")
            if span.get("kind") != "numeric":
                raise PublicWireContractError("public wire numeric span kind invalid")
            _verify_wire_span(span, source_sha=source_sha, claims=claims, numeric_values=numeric_values)
    if len(claims) < 2:
        raise PublicWireContractError("public wire has too little approved evidence")
    if len(numeric_values) < article_receipt_floor(str(admission["tier"])):
        raise PublicWireContractError("public wire lacks the required distinct numeric evidence")
    completeness = _mapping(article.get("source_completeness"), name="public wire source completeness")
    expected_completeness = {
        "release": "not_ingested", "filing": "not_ingested", "transcript": "present",
        "slides": "not_ingested", "consensus": "unlicensed_absent",
    }
    if dict(completeness) != expected_completeness:
        raise PublicWireContractError("public wire must disclose transcript-only source completeness")
    if article.get("execution") != EXECUTION_RECEIPT:
        raise PublicWireContractError("public wire execution must remain token-free")


def _verify_wire_span(
    span: Mapping[str, Any], *, source_sha: str, claims: set[str], numeric_values: set[tuple[str, str]],
) -> None:
    claim_id = _text(span.get("claim_id"), name="public wire span claim id", limit=80)
    if claim_id in claims:
        raise PublicWireContractError("public wire claim was repeated")
    claims.add(claim_id)
    text = _text(span.get("text"), name="public wire span text", limit=4_000)
    receipt = _mapping(span.get("receipt"), name="public wire span receipt")
    _closed_keys(receipt, _RECEIPT_KEYS, name="public wire span receipt")
    if receipt.get("source_sha256") != source_sha or receipt.get("text_sha256") != sha256(text.encode("utf-8")).hexdigest():
        raise PublicWireContractError("public wire span receipt mismatch")
    for key in ("segment_sha256", "text_sha256", "source_sha256"):
        _sha(receipt.get(key), name=f"public wire span receipt {key}")
    for key in ("segment_index", "segment_bytes", "span_start_byte", "span_end_byte"):
        value = receipt.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PublicWireContractError("public wire span receipt coordinate invalid")
    if receipt["span_end_byte"] <= receipt["span_start_byte"]:
        raise PublicWireContractError("public wire span receipt range invalid")
    if span.get("kind") == "numeric":
        numeric_values.add((text, str(receipt["text_sha256"])))


def build_public_wire_manifest(
    articles: Sequence[Mapping[str, Any]], *, source_generation_id: str,
    source_manifest_sha256: str, source_packet_count: int,
    source_packet_manifest_schema: str,
    canonical_base: str = "https://www.mastermind-x.com",
) -> dict[str, Any]:
    """Freeze a replayable, last-good public wire catalog from verified articles."""
    if not isinstance(source_generation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", source_generation_id):
        raise PublicWireContractError("source generation id invalid")
    _sha(source_manifest_sha256, name="source manifest sha256")
    if isinstance(source_packet_count, bool) or not isinstance(source_packet_count, int) or source_packet_count < 0:
        raise PublicWireContractError("source packet count invalid")
    if source_packet_manifest_schema != "earnings.story_packet_manifest/v1":
        raise PublicWireContractError("source packet manifest schema invalid")
    base = canonical_base.rstrip("/")
    if not base.startswith("https://"):
        raise PublicWireContractError("public wire canonical base must be https")
    rows = [dict(article) for article in articles]
    for article in rows:
        verify_public_wire_article(article)
        if article["packet"]["generation_id"] != source_generation_id:
            raise PublicWireContractError("article packet belongs to another source generation")
    rows.sort(key=lambda row: (str(row["event"]["date"]), str(row["event"]["ticker"]), str(row["article_id"])), reverse=True)
    article_ids = [str(row["article_id"]) for row in rows]
    if article_ids != sorted(set(article_ids), key=article_ids.index):
        raise PublicWireContractError("public wire article identities are not unique")
    routes = [
        {
            "article_id": str(article["article_id"]),
            "url_path": f"/stocks/earnings/{article['event']['slug']}.html",
            "canonical": f"{base}/stocks/earnings/{article['event']['slug']}.html",
            # The source index time is the only durable content-update time this
            # deterministic compiler has. It is not a fabricated page publish time.
            "lastmod": str(article["source"]["index_generated_at"]),
        }
        for article in rows
    ]
    manifest: dict[str, Any] = {
        "schema": PUBLIC_WIRE_MANIFEST_SCHEMA,
        "manifest_id": "wiremanifest_" + ("0" * 32),
        "status": "ready",
        "source": {
            "generation_id": source_generation_id,
            "manifest_sha256": source_manifest_sha256,
            "packet_count": source_packet_count,
            "packet_manifest_schema": source_packet_manifest_schema,
        },
        "articles": rows,
        "routes": routes,
        "execution": dict(EXECUTION_RECEIPT),
    }
    manifest["manifest_id"] = _stable_id("wiremanifest_", _manifest_unsigned(manifest))
    verify_public_wire_manifest(manifest)
    return manifest


def verify_public_wire_manifest(payload: object) -> None:
    """Validate a saved last-good public wire manifest before it is reused."""
    manifest = _mapping(payload, name="public wire manifest")
    _closed_keys(manifest, _MANIFEST_KEYS, name="public wire manifest")
    if manifest.get("schema") != PUBLIC_WIRE_MANIFEST_SCHEMA or manifest.get("status") != "ready":
        raise PublicWireContractError("public wire manifest state invalid")
    manifest_id = manifest.get("manifest_id")
    if not isinstance(manifest_id, str) or not _MANIFEST_ID.fullmatch(manifest_id):
        raise PublicWireContractError("public wire manifest id invalid")
    if manifest_id != _stable_id("wiremanifest_", _manifest_unsigned(manifest)):
        raise PublicWireContractError("public wire manifest id does not bind payload")
    source = _mapping(manifest.get("source"), name="public wire manifest source")
    _closed_keys(source, _MANIFEST_SOURCE_KEYS, name="public wire manifest source")
    if not isinstance(source.get("generation_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", source["generation_id"]):
        raise PublicWireContractError("public wire manifest source generation invalid")
    _sha(source.get("manifest_sha256"), name="public wire manifest source sha256")
    if isinstance(source.get("packet_count"), bool) or not isinstance(source.get("packet_count"), int) or source["packet_count"] < 0:
        raise PublicWireContractError("public wire manifest packet count invalid")
    if source.get("packet_manifest_schema") != "earnings.story_packet_manifest/v1":
        raise PublicWireContractError("public wire manifest source schema invalid")
    articles = manifest.get("articles")
    if not isinstance(articles, list):
        raise PublicWireContractError("public wire manifest articles invalid")
    article_ids: set[str] = set()
    slugs: set[str] = set()
    for article in articles:
        verify_public_wire_article(article)
        if article["packet"]["generation_id"] != source["generation_id"]:
            raise PublicWireContractError("public wire article source generation mismatch")
        if article["article_id"] in article_ids or article["event"]["slug"] in slugs:
            raise PublicWireContractError("public wire manifest duplicate article")
        article_ids.add(article["article_id"])
        slugs.add(article["event"]["slug"])
    routes = manifest.get("routes")
    if not isinstance(routes, list) or len(routes) != len(articles):
        raise PublicWireContractError("public wire manifest routes invalid")
    route_ids: set[str] = set()
    expected_by_id = {
        str(article["article_id"]): (
            f"/stocks/earnings/{article['event']['slug']}.html",
            str(article["source"]["index_generated_at"]),
        )
        for article in articles
    }
    for route in routes:
        row = _mapping(route, name="public wire route")
        _closed_keys(row, _ROUTE_KEYS, name="public wire route")
        article_id = _text(row.get("article_id"), name="public wire route article id", limit=80)
        expected = expected_by_id.get(article_id)
        if expected is None or article_id in route_ids:
            raise PublicWireContractError("public wire route article binding invalid")
        route_ids.add(article_id)
        if row.get("url_path") != expected[0] or row.get("lastmod") != expected[1]:
            raise PublicWireContractError("public wire route path or lastmod invalid")
        canonical = _text(row.get("canonical"), name="public wire route canonical", limit=500)
        if not canonical.startswith("https://") or not canonical.endswith(expected[0]):
            raise PublicWireContractError("public wire route canonical invalid")
    if manifest.get("execution") != EXECUTION_RECEIPT:
        raise PublicWireContractError("public wire manifest execution must remain token-free")


def public_wire_manifest_json(manifest: Mapping[str, Any]) -> bytes:
    """Return canonical bytes only after a full closed-contract replay."""
    verify_public_wire_manifest(manifest)
    return canonical_json_bytes(manifest)


def source_manifest_sha256(raw: bytes) -> str:
    """Name the exact remote marker bytes used by a public wire publication."""
    return sha256_bytes(raw)
