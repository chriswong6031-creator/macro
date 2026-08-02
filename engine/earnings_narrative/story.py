"""Immutable distribution manifests for one earnings-event claim set.

``canonical_story.v1`` is not another fact database and it is not a prose
generator.  It freezes the exact claims a later writer may express, records
promotion/correction intent, and allocates derivative identities.  The source-
ready compiler in this module is deterministic and token-free; the existing
Press writer and validators remain the only article-writing rail.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Mapping

from .contracts import (
    AUTHORITY,
    EXECUTION_RECEIPT,
    ContractError,
    canonical_json_bytes,
    direct_claim_id,
    event_key,
    normalize_numeric,
    safe_ticker,
    transcript_id,
    validate_event_identity,
    validate_source_receipt,
    validate_span_receipt,
)
from .digest import DIGEST_SCHEMA, validate_event_digest


STORY_SCHEMA = "canonical_story.v1"

_STORY_ID = re.compile(r"^story_[0-9a-f]{32}$")
_REVISION_ID = re.compile(r"^storyrev_[0-9a-f]{32}$")
_DERIVATIVE_ID = re.compile(r"^der_[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^span_[0-9a-f]{32}$")
_FACT_ID = re.compile(r"^fact_[0-9a-f]{32}$")
_CLAIM_ID = re.compile(r"^claim_[0-9a-f]{32}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")

_STORY_KEYS = frozenset({
    "schema", "authority", "story_id", "story_revision_id", "status",
    "event", "source", "digest", "promotion", "approved_claim_ids",
    "approved_spans", "deterministic_assets", "copy", "seo", "correction",
    "derivatives", "attribution", "generation", "execution",
})
_DIGEST_REF_KEYS = frozenset({"schema", "digest_id", "citation_coverage", "quality_status"})
_PROMOTION_KEYS = frozenset({"tier", "reasons", "decision_source", "article_eligible"})
_SPAN_KEYS = frozenset({
    "span_id", "claim_id", "fact_id", "kind", "text", "text_sha256", "receipt",
})
_ASSET_KEYS = frozenset({"tables", "charts"})
_COPY_KEYS = frozenset({"headline", "dek", "sections", "conclusion", "uncertainty_disclosure"})
_COPY_SECTION_KEYS = frozenset({"heading", "body", "claim_ids"})
_SEO_KEYS = frozenset({"slug", "title", "description", "structured_data", "indexing"})
_CORRECTION_KEYS = frozenset({"status", "supersedes_revision_id", "invalidates_derivative_ids"})
_DERIVATIVE_KEYS = frozenset({
    "article_id", "ticker_module_id", "x_post_ids", "short_form_ids", "alert_id", "email_id",
})
_ATTRIBUTION_KEYS = frozenset({"utm_source", "utm_medium", "utm_campaign", "utm_content"})
_GENERATION_KEYS = frozenset({"writer", "verifier"})
_MODEL_LEDGER_KEYS = frozenset({
    "provider", "model", "prompt_sha256", "input_tokens", "output_tokens", "cost_usd",
})
_EXECUTION_KEYS = frozenset({"mode", "providers", "model_calls", "tokens"})

_DECISION_SOURCES = frozenset({"default_hold", "governed_triage", "operator"})


def article_receipt_floor(tier: str) -> int:
    """Minimum distinct numeric receipts required for an article derivative."""
    normalized = str(tier).upper()
    if normalized == "A":
        return 5
    if normalized == "B":
        return 3
    if normalized == "C":
        return 0
    raise ContractError("tier must be A, B, or C")


def article_receipt_value(text: str) -> float | int | None:
    """Return a Press-countable metric value, excluding counts and calendar years."""
    value, unit = normalize_numeric(text)
    if unit is None and (
        (isinstance(value, int) and 1900 <= value <= 2100)
        or float(value) <= 12
    ):
        return None
    return value


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


def _text(value: object, *, field: str, allow_null: bool = False, limit: int = 8_000) -> str | None:
    if value is None and allow_null:
        return None
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > limit:
        raise ContractError(f"{field} invalid")
    return value


def _story_id(event: Mapping[str, Any]) -> str:
    stable = f"earnings:{safe_ticker(event.get('ticker'))}/{transcript_id(event.get('transcript_id'))}"
    return "story_" + sha256(stable.encode("utf-8")).hexdigest()[:32]


def _span_id(claim_id: str, receipt: Mapping[str, Any]) -> str:
    material = ":".join((
        claim_id,
        str(receipt["source_sha256"]),
        str(receipt["segment_index"]),
        str(receipt["span_start_byte"]),
        str(receipt["span_end_byte"]),
    ))
    return "span_" + sha256(material.encode("utf-8")).hexdigest()[:32]


def _derivative_id(story_id: str, digest_id: str, channel: str) -> str:
    return "der_" + sha256(f"{story_id}:{digest_id}:{channel}".encode("utf-8")).hexdigest()[:32]


def _story_unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(payload)
    unsigned["story_revision_id"] = "storyrev_" + ("0" * 32)
    return unsigned


def _all_derivative_ids(derivatives: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("article_id", "ticker_module_id", "alert_id", "email_id"):
        value = derivatives.get(key)
        if isinstance(value, str):
            values.append(value)
    for key in ("x_post_ids", "short_form_ids"):
        for value in derivatives.get(key) or []:
            if isinstance(value, str):
                values.append(value)
    return sorted(set(values))


def _zero_model_ledger() -> dict[str, Any]:
    return {
        "provider": None,
        "model": None,
        "prompt_sha256": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }


def _validate_model_ledger(value: object, *, name: str, source_ready: bool) -> None:
    row = _mapping(value, name=name)
    _keys(row, _MODEL_LEDGER_KEYS, name=name)
    for key in ("input_tokens", "output_tokens"):
        item = row.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ContractError(f"{name}.{key} invalid")
    cost = row.get("cost_usd")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
        raise ContractError(f"{name}.cost_usd invalid")
    for key in ("provider", "model"):
        if row.get(key) is not None:
            _text(row.get(key), field=f"{name}.{key}", limit=300)
    prompt_sha = row.get("prompt_sha256")
    if prompt_sha is not None and (not isinstance(prompt_sha, str) or not _SHA.fullmatch(prompt_sha)):
        raise ContractError(f"{name}.prompt_sha256 invalid")
    if source_ready and dict(row) != _zero_model_ledger():
        raise ContractError(f"{name} must be zeroed before prose generation")


def validate_canonical_story(payload: object) -> None:
    """Validate a closed canonical story distribution manifest."""
    row = _mapping(payload, name="canonical_story")
    _keys(row, _STORY_KEYS, name="canonical_story")
    if row.get("schema") != STORY_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("canonical_story schema or authority mismatch")
    story_id = row.get("story_id")
    revision_id = row.get("story_revision_id")
    if not isinstance(story_id, str) or not _STORY_ID.fullmatch(story_id):
        raise ContractError("canonical_story.story_id invalid")
    if not isinstance(revision_id, str) or not _REVISION_ID.fullmatch(revision_id):
        raise ContractError("canonical_story.story_revision_id invalid")
    status = row.get("status")
    if status not in {"source_ready", "approved"}:
        raise ContractError("canonical_story.status invalid")
    source_ready = status == "source_ready"

    event = validate_event_identity(row.get("event"))
    source = validate_source_receipt(row.get("source"))
    if event_key(event) != f"{source['ticker']}/{source['transcript_id']}":
        raise ContractError("canonical_story event/source identity mismatch")
    if story_id != _story_id(event):
        raise ContractError("canonical_story.story_id must remain stable for the logical event")

    digest_ref = _mapping(row.get("digest"), name="canonical_story.digest")
    _keys(digest_ref, _DIGEST_REF_KEYS, name="canonical_story.digest")
    if digest_ref.get("schema") != DIGEST_SCHEMA:
        raise ContractError("canonical_story digest schema mismatch")
    digest_id = digest_ref.get("digest_id")
    if not isinstance(digest_id, str) or not re.fullmatch(r"digest_[0-9a-f]{32}", digest_id):
        raise ContractError("canonical_story digest_id invalid")
    if digest_ref.get("quality_status") not in {"ready", "insufficient"}:
        raise ContractError("canonical_story digest quality status invalid")
    coverage = digest_ref.get("citation_coverage")
    if isinstance(coverage, bool) or coverage not in {0.0, 1.0}:
        raise ContractError("canonical_story digest citation coverage invalid")

    promotion = _mapping(row.get("promotion"), name="canonical_story.promotion")
    _keys(promotion, _PROMOTION_KEYS, name="canonical_story.promotion")
    tier = promotion.get("tier")
    if tier not in {"A", "B", "C"}:
        raise ContractError("canonical_story promotion tier invalid")
    reasons = promotion.get("reasons")
    if (
        not isinstance(reasons, list)
        or not reasons
        or any(not isinstance(reason, str) or not reason or len(reason) > 160 for reason in reasons)
        or reasons != sorted(set(reasons))
    ):
        raise ContractError("canonical_story promotion reasons invalid")
    if promotion.get("decision_source") not in _DECISION_SOURCES:
        raise ContractError("canonical_story promotion decision_source invalid")
    eligible = tier in {"A", "B"} and digest_ref["quality_status"] == "ready"
    if promotion.get("article_eligible") is not eligible:
        raise ContractError("canonical_story article_eligible does not match tier and digest quality")

    claim_ids = row.get("approved_claim_ids")
    if (
        not isinstance(claim_ids, list)
        or any(not isinstance(claim_id, str) or not _CLAIM_ID.fullmatch(claim_id) for claim_id in claim_ids)
        or claim_ids != sorted(set(claim_ids))
    ):
        raise ContractError("canonical_story approved_claim_ids invalid")
    spans = row.get("approved_spans")
    if not isinstance(spans, list):
        raise ContractError("canonical_story approved_spans invalid")
    span_claim_ids: list[str] = []
    prior_span_order: tuple[int, int, str] | None = None
    for index, item in enumerate(spans):
        span = _mapping(item, name=f"canonical_story.approved_spans[{index}]")
        _keys(span, _SPAN_KEYS, name=f"canonical_story.approved_spans[{index}]")
        span_id = span.get("span_id")
        claim_id = span.get("claim_id")
        fact_id = span.get("fact_id")
        if not isinstance(span_id, str) or not _SPAN_ID.fullmatch(span_id):
            raise ContractError("canonical_story span_id invalid")
        if not isinstance(claim_id, str) or not _CLAIM_ID.fullmatch(claim_id):
            raise ContractError("canonical_story span claim_id invalid")
        if not isinstance(fact_id, str) or not _FACT_ID.fullmatch(fact_id):
            raise ContractError("canonical_story span fact_id invalid")
        if claim_id != direct_claim_id(fact_id):
            raise ContractError("canonical_story span claim_id must bind fact_id")
        if span.get("kind") not in {"quote", "numeric"}:
            raise ContractError("canonical_story span kind invalid")
        text = _text(span.get("text"), field=f"canonical_story.approved_spans[{index}].text", limit=4_000)
        assert isinstance(text, str)
        text_sha = sha256(text.encode("utf-8")).hexdigest()
        if span.get("text_sha256") != text_sha:
            raise ContractError("canonical_story span text_sha256 mismatch")
        receipt = validate_span_receipt(
            span.get("receipt"), source_sha256=str(source["body_sha256"]), text=text,
        )
        if span_id != _span_id(claim_id, receipt):
            raise ContractError("canonical_story span_id does not bind claim and receipt")
        order = (int(receipt["segment_index"]), int(receipt["span_start_byte"]), str(span_id))
        if prior_span_order is not None and order <= prior_span_order:
            raise ContractError("canonical_story approved_spans must remain in source order")
        prior_span_order = order
        span_claim_ids.append(claim_id)
    if sorted(span_claim_ids) != claim_ids or len(span_claim_ids) != len(set(span_claim_ids)):
        raise ContractError("canonical_story approved spans must cover each approved claim exactly once")
    numeric_receipts = {
        value
        for span in spans
        if span["kind"] == "numeric"
        for value in [article_receipt_value(str(span["text"]))]
        if value is not None
    }
    receipt_floor = article_receipt_floor(str(tier))
    if eligible and len(numeric_receipts) < receipt_floor:
        raise ContractError(
            "canonical_story article eligibility lacks distinct numeric receipts "
            f"for Tier {tier}: {len(numeric_receipts)} < {receipt_floor}"
        )

    assets = _mapping(row.get("deterministic_assets"), name="canonical_story.deterministic_assets")
    _keys(assets, _ASSET_KEYS, name="canonical_story.deterministic_assets")
    if assets.get("tables") != [] or assets.get("charts") != []:
        raise ContractError("canonical_story source-ready v1 cannot originate tables or charts")

    copy = _mapping(row.get("copy"), name="canonical_story.copy")
    _keys(copy, _COPY_KEYS, name="canonical_story.copy")
    if source_ready:
        if dict(copy) != {
            "headline": None,
            "dek": None,
            "sections": [],
            "conclusion": None,
            "uncertainty_disclosure": None,
        }:
            raise ContractError("canonical_story source_ready copy must remain empty")
    else:
        _text(copy.get("headline"), field="canonical_story.copy.headline", limit=120)
        _text(copy.get("dek"), field="canonical_story.copy.dek", limit=300)
        sections = copy.get("sections")
        if not isinstance(sections, list) or not sections:
            raise ContractError("approved canonical_story requires sections")
        for index, item in enumerate(sections):
            section = _mapping(item, name=f"canonical_story.copy.sections[{index}]")
            _keys(section, _COPY_SECTION_KEYS, name=f"canonical_story.copy.sections[{index}]")
            _text(section.get("heading"), field=f"canonical_story.copy.sections[{index}].heading", limit=160)
            _text(section.get("body"), field=f"canonical_story.copy.sections[{index}].body", limit=8_000)
            section_claims = section.get("claim_ids")
            if (
                not isinstance(section_claims, list)
                or not section_claims
                or section_claims != sorted(set(section_claims))
                or any(claim_id not in claim_ids for claim_id in section_claims)
            ):
                raise ContractError(f"canonical_story.copy.sections[{index}].claim_ids invalid")
        _text(copy.get("conclusion"), field="canonical_story.copy.conclusion", limit=4_000)
        _text(
            copy.get("uncertainty_disclosure"),
            field="canonical_story.copy.uncertainty_disclosure",
            limit=1_000,
        )

    seo = _mapping(row.get("seo"), name="canonical_story.seo")
    _keys(seo, _SEO_KEYS, name="canonical_story.seo")
    expected_slug = f"{safe_ticker(event['ticker']).lower()}-{transcript_id(event['transcript_id']).lower()}-earnings-call"
    if seo.get("slug") != expected_slug:
        raise ContractError("canonical_story SEO slug mismatch")
    if source_ready:
        if any(seo.get(key) is not None for key in ("title", "description", "structured_data")):
            raise ContractError("canonical_story source_ready SEO copy must remain empty")
        if seo.get("indexing") != "noindex_until_approved":
            raise ContractError("canonical_story source_ready indexing must fail closed")
    elif seo.get("indexing") not in {"index", "noindex"}:
        raise ContractError("approved canonical_story indexing invalid")

    correction = _mapping(row.get("correction"), name="canonical_story.correction")
    _keys(correction, _CORRECTION_KEYS, name="canonical_story.correction")
    correction_status = correction.get("status")
    supersedes = correction.get("supersedes_revision_id")
    invalidates = correction.get("invalidates_derivative_ids")
    if correction_status not in {"current", "corrected"}:
        raise ContractError("canonical_story correction status invalid")
    if not isinstance(invalidates, list) or invalidates != sorted(set(invalidates)):
        raise ContractError("canonical_story correction invalidation list invalid")
    if any(not isinstance(item, str) or not _DERIVATIVE_ID.fullmatch(item) for item in invalidates):
        raise ContractError("canonical_story correction derivative id invalid")
    if correction_status == "current":
        if supersedes is not None or invalidates:
            raise ContractError("current canonical_story cannot supersede or invalidate")
    else:
        if not isinstance(supersedes, str) or not _REVISION_ID.fullmatch(supersedes):
            raise ContractError("corrected canonical_story requires superseded revision")
        if not invalidates:
            raise ContractError("corrected canonical_story must invalidate prior derivatives")

    derivatives = _mapping(row.get("derivatives"), name="canonical_story.derivatives")
    _keys(derivatives, _DERIVATIVE_KEYS, name="canonical_story.derivatives")
    for key in ("article_id", "ticker_module_id", "alert_id", "email_id"):
        value = derivatives.get(key)
        if value is not None and (not isinstance(value, str) or not _DERIVATIVE_ID.fullmatch(value)):
            raise ContractError(f"canonical_story derivatives.{key} invalid")
    for key in ("x_post_ids", "short_form_ids"):
        values = derivatives.get(key)
        if (
            not isinstance(values, list)
            or values != sorted(set(values))
            or any(not isinstance(value, str) or not _DERIVATIVE_ID.fullmatch(value) for value in values)
        ):
            raise ContractError(f"canonical_story derivatives.{key} invalid")
    expected_derivatives = {
        "article_id": _derivative_id(story_id, digest_id, "article") if eligible else None,
        "ticker_module_id": _derivative_id(story_id, digest_id, "ticker_module"),
        "x_post_ids": [_derivative_id(story_id, digest_id, "x_post")] if eligible else [],
        "short_form_ids": [_derivative_id(story_id, digest_id, "short_form")] if tier == "A" and eligible else [],
        "alert_id": _derivative_id(story_id, digest_id, "alert") if eligible else None,
        "email_id": _derivative_id(story_id, digest_id, "email") if tier == "A" and eligible else None,
    }
    if dict(derivatives) != expected_derivatives:
        raise ContractError("canonical_story derivative identities mismatch tier policy")

    attribution = _mapping(row.get("attribution"), name="canonical_story.attribution")
    _keys(attribution, _ATTRIBUTION_KEYS, name="canonical_story.attribution")
    expected_attribution = {
        "utm_source": "mastermind",
        "utm_medium": "owned",
        "utm_campaign": "earnings-intelligence",
        "utm_content": story_id,
    }
    if dict(attribution) != expected_attribution:
        raise ContractError("canonical_story attribution mismatch")

    generation = _mapping(row.get("generation"), name="canonical_story.generation")
    _keys(generation, _GENERATION_KEYS, name="canonical_story.generation")
    _validate_model_ledger(generation.get("writer"), name="canonical_story.generation.writer", source_ready=source_ready)
    _validate_model_ledger(generation.get("verifier"), name="canonical_story.generation.verifier", source_ready=source_ready)
    execution = _mapping(row.get("execution"), name="canonical_story.execution")
    _keys(execution, _EXECUTION_KEYS, name="canonical_story.execution")
    if source_ready:
        if dict(execution) != EXECUTION_RECEIPT:
            raise ContractError("canonical_story source_ready execution must be deterministic and token-free")
    else:
        providers = execution.get("providers")
        if not isinstance(providers, list) or providers != sorted(set(providers)) or not providers:
            raise ContractError("approved canonical_story must disclose providers")
        if execution.get("mode") != "model_assisted_verified":
            raise ContractError("approved canonical_story execution mode invalid")
        if (
            isinstance(execution.get("model_calls"), bool)
            or not isinstance(execution.get("model_calls"), int)
            or execution["model_calls"] < 1
        ):
            raise ContractError("approved canonical_story model_calls invalid")
        if (
            isinstance(execution.get("tokens"), bool)
            or not isinstance(execution.get("tokens"), int)
            or execution["tokens"] < 1
        ):
            raise ContractError("approved canonical_story tokens invalid")

    expected_revision = "storyrev_" + sha256(canonical_json_bytes(_story_unsigned(row))).hexdigest()[:32]
    if revision_id != expected_revision:
        raise ContractError("canonical_story.story_revision_id does not match canonical content")


def _span_rows(digest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for digest_fact in digest["facts"]:
        for evidence in digest_fact["evidence"]:
            receipt = dict(evidence["receipt"])
            claim_id = str(evidence["claim_id"])
            text = str(evidence["text"])
            rows.append({
                "span_id": _span_id(claim_id, receipt),
                "claim_id": claim_id,
                "fact_id": evidence["fact_id"],
                "kind": evidence["kind"],
                "text": text,
                "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                "receipt": receipt,
            })
    rows.sort(key=lambda row: (
        int(row["receipt"]["segment_index"]),
        int(row["receipt"]["span_start_byte"]),
        str(row["span_id"]),
    ))
    return rows


def build_canonical_story(
    digest: object,
    *,
    tier: str = "C",
    reasons: list[str] | tuple[str, ...] = ("awaiting_governed_promotion",),
    decision_source: str = "default_hold",
    prior_story: object | None = None,
) -> dict[str, Any]:
    """Compile a source-ready story without a model call or prose authority."""
    validate_event_digest(digest)
    assert isinstance(digest, Mapping)
    tier = str(tier).upper()
    if tier not in {"A", "B", "C"}:
        raise ContractError("tier must be A, B, or C")
    quality_status = str(digest["quality"]["status"])
    if tier in {"A", "B"} and quality_status != "ready":
        raise ContractError("article promotion requires a ready event digest")
    normalized_reasons = sorted(set(str(reason).strip() for reason in reasons if str(reason).strip()))
    if not normalized_reasons:
        raise ContractError("at least one promotion reason is required")
    if decision_source not in _DECISION_SOURCES:
        raise ContractError("unsupported promotion decision source")

    event = dict(digest["event"])
    source = dict(digest["source"])
    story_id = _story_id(event)
    digest_id = str(digest["digest_id"])
    eligible = tier in {"A", "B"} and quality_status == "ready"
    derivatives = {
        "article_id": _derivative_id(story_id, digest_id, "article") if eligible else None,
        "ticker_module_id": _derivative_id(story_id, digest_id, "ticker_module"),
        "x_post_ids": [_derivative_id(story_id, digest_id, "x_post")] if eligible else [],
        "short_form_ids": [_derivative_id(story_id, digest_id, "short_form")] if tier == "A" and eligible else [],
        "alert_id": _derivative_id(story_id, digest_id, "alert") if eligible else None,
        "email_id": _derivative_id(story_id, digest_id, "email") if tier == "A" and eligible else None,
    }
    correction = {
        "status": "current",
        "supersedes_revision_id": None,
        "invalidates_derivative_ids": [],
    }
    if prior_story is not None:
        validate_canonical_story(prior_story)
        assert isinstance(prior_story, Mapping)
        if prior_story["story_id"] != story_id or prior_story["event"] != event:
            raise ContractError("a correction must retain the same logical event and story_id")
        if prior_story["source"]["body_sha256"] == source["body_sha256"]:
            raise ContractError("a correction requires a new source revision")
        correction = {
            "status": "corrected",
            "supersedes_revision_id": prior_story["story_revision_id"],
            "invalidates_derivative_ids": _all_derivative_ids(prior_story["derivatives"]),
        }

    payload: dict[str, Any] = {
        "schema": STORY_SCHEMA,
        "authority": AUTHORITY,
        "story_id": story_id,
        "story_revision_id": "storyrev_" + ("0" * 32),
        "status": "source_ready",
        "event": event,
        "source": source,
        "digest": {
            "schema": DIGEST_SCHEMA,
            "digest_id": digest_id,
            "citation_coverage": digest["citation_coverage"],
            "quality_status": quality_status,
        },
        "promotion": {
            "tier": tier,
            "reasons": normalized_reasons,
            "decision_source": decision_source,
            "article_eligible": eligible,
        },
        "approved_claim_ids": list(digest["claims"]),
        "approved_spans": _span_rows(digest),
        "deterministic_assets": {"tables": [], "charts": []},
        "copy": {
            "headline": None,
            "dek": None,
            "sections": [],
            "conclusion": None,
            "uncertainty_disclosure": None,
        },
        "seo": {
            "slug": f"{safe_ticker(event['ticker']).lower()}-{transcript_id(event['transcript_id']).lower()}-earnings-call",
            "title": None,
            "description": None,
            "structured_data": None,
            "indexing": "noindex_until_approved",
        },
        "correction": correction,
        "derivatives": derivatives,
        "attribution": {
            "utm_source": "mastermind",
            "utm_medium": "owned",
            "utm_campaign": "earnings-intelligence",
            "utm_content": story_id,
        },
        "generation": {
            "writer": _zero_model_ledger(),
            "verifier": _zero_model_ledger(),
        },
        "execution": dict(EXECUTION_RECEIPT),
    }
    payload["story_revision_id"] = "storyrev_" + sha256(
        canonical_json_bytes(_story_unsigned(payload))
    ).hexdigest()[:32]
    validate_canonical_story(payload)
    validate_story_against_digest(payload, digest)
    if prior_story is not None:
        validate_correction_against_prior(payload, prior_story)
    return payload


def validate_story_against_digest(story: object, digest: object) -> None:
    """Prove the story's claim set and spans exactly equal its cited digest."""
    validate_canonical_story(story)
    validate_event_digest(digest)
    assert isinstance(story, Mapping)
    assert isinstance(digest, Mapping)
    if story["event"] != digest["event"] or story["source"] != digest["source"]:
        raise ContractError("canonical_story event/source differs from event_digest")
    expected_ref = {
        "schema": DIGEST_SCHEMA,
        "digest_id": digest["digest_id"],
        "citation_coverage": digest["citation_coverage"],
        "quality_status": digest["quality"]["status"],
    }
    if story["digest"] != expected_ref:
        raise ContractError("canonical_story digest reference mismatch")
    if story["approved_claim_ids"] != digest["claims"]:
        raise ContractError("canonical_story claim set changed from event_digest")
    if story["approved_spans"] != _span_rows(digest):
        raise ContractError("canonical_story spans changed from event_digest")


def derivative_ids(story: object) -> list[str]:
    validate_canonical_story(story)
    assert isinstance(story, Mapping)
    return _all_derivative_ids(story["derivatives"])


def validate_correction_against_prior(story: object, prior_story: object) -> None:
    """Bind a corrected revision to the exact prior revision and derivatives."""
    validate_canonical_story(story)
    validate_canonical_story(prior_story)
    assert isinstance(story, Mapping)
    assert isinstance(prior_story, Mapping)
    if story["correction"]["status"] != "corrected":
        raise ContractError("correction validation requires corrected status")
    if story["story_id"] != prior_story["story_id"] or story["event"] != prior_story["event"]:
        raise ContractError("corrected canonical_story must retain prior logical identity")
    if story["source"]["body_sha256"] == prior_story["source"]["body_sha256"]:
        raise ContractError("corrected canonical_story requires a changed source revision")
    if story["correction"]["supersedes_revision_id"] != prior_story["story_revision_id"]:
        raise ContractError("corrected canonical_story supersedes_revision_id differs from prior")
    if story["correction"]["invalidates_derivative_ids"] != derivative_ids(prior_story):
        raise ContractError("corrected canonical_story must invalidate every prior derivative")
