"""Adapt one receipt-frozen earnings story to the existing Press slot contract.

No network, model, scheduler, or publisher lives here.  The adapter deliberately
feeds ``engine.press.writer`` and ``engine.press.validators`` rather than
creating a parallel article path.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.earnings_narrative.contracts import ContractError, safe_ticker, transcript_id
from engine.earnings_narrative.digest import validate_event_digest
from engine.earnings_narrative.story import (
    article_receipt_floor,
    article_receipt_value,
    validate_canonical_story,
    validate_correction_against_prior,
    validate_story_against_digest,
)


def _stable_source_ref(event: Mapping[str, Any]) -> str:
    # earnings_transcript_intake.py is the canonical constructor for this id.
    return (
        "chronicle:defeatbeta:"
        f"{safe_ticker(event.get('ticker'))}:{transcript_id(event.get('transcript_id'))}"
    )


def _numeric_values(digest_fact: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for evidence in digest_fact["evidence"]:
        if evidence["kind"] != "numeric":
            continue
        receipt_value = article_receipt_value(str(evidence["text"]))
        if receipt_value is None:
            continue
        value = str(receipt_value)
        if value not in values:
            values.append(value)
    return values


def story_to_press_slot(
    story: object,
    digest: object,
    *,
    chronicle_context: Mapping[str, Any] | None = None,
    prior_story: object | None = None,
) -> dict[str, Any]:
    """Return an exact Press slot for a Tier-A/B source-ready story.

    Tier C deliberately has no article slot.  It still has a ticker-module
    derivative id in ``canonical_story.v1`` and can be summarized on demand.
    """
    validate_canonical_story(story)
    validate_event_digest(digest)
    validate_story_against_digest(story, digest)
    assert isinstance(story, Mapping)
    assert isinstance(digest, Mapping)
    if story["correction"]["status"] == "corrected":
        if prior_story is None:
            raise ContractError("corrected canonical story requires its prior manifest")
        validate_correction_against_prior(story, prior_story)
    promotion = story["promotion"]
    if not promotion["article_eligible"]:
        raise ContractError("canonical story is not eligible for a Press article")

    tier = str(promotion["tier"])
    required_receipts = article_receipt_floor(tier)
    event = story["event"]
    source = story["source"]
    source_ref = _stable_source_ref(event)
    receipt = f"sha256:{source['body_sha256']}"

    facts: list[dict[str, Any]] = []
    distinct_numeric_values: set[str] = set()
    for item in digest["facts"]:
        text = str(item["text"])
        if len(text) > 2_000:
            raise ContractError("canonical story contains an overlong Press source fact")
        values = _numeric_values(item)
        distinct_numeric_values.update(values)
        quote = item["evidence"][0]
        facts.append({
            "id": item["digest_fact_id"],
            "text": text,
            "ref": f"earnings-evidence:{quote['claim_id']}",
            "tier": "first_party",
            "values": values,
            "url": None,
            "source_name": "Mastermind earnings evidence",
            "dated": str(event["date"]),
            "claim_ids": [evidence["claim_id"] for evidence in item["evidence"]],
            "span_ids": [
                span["span_id"]
                for span in story["approved_spans"]
                if span["claim_id"] in {evidence["claim_id"] for evidence in item["evidence"]}
            ],
        })
    if len(distinct_numeric_values) < required_receipts:
        raise ContractError(
            "canonical story lacks enough distinct Press-countable numeric receipts "
            f"for Tier {tier}: {len(distinct_numeric_values)} < {required_receipts}"
        )
    if not facts:
        raise ContractError("canonical story has no press-safe source facts")

    context = dict(chronicle_context or {})
    if not context:
        context = {
            "lines": [],
            "coverage": {
                "note": "Transcript-only event digest; filing, release, slides, consensus, market reaction, and theme joins are not present in v1."
            },
        }
    model_key = "press_research" if tier == "A" else "press_brief"
    min_words, max_words = ((500, 850) if tier == "A" else (300, 550))
    story_id = str(story["story_id"])
    story_revision_id = str(story["story_revision_id"])
    title_hint = (
        f"{safe_ticker(event['ticker'])} {event['period']}: "
        "what changed on the earnings call"
    )
    return {
        "id": f"press-earnings-{story_revision_id.removeprefix('storyrev_')}",
        "desk": "brief",
        "publication": "mastermind_news",
        "byline": "Earnings Desk — Mastermind News",
        "cluster": "earnings-intelligence",
        "as_of": str(event["date"]),
        "model_key": model_key,
        "min_words": min_words,
        "max_words": max_words,
        "min_anchored_receipts": required_receipts,
        "allowed_links": [],
        "story": {
            "kind": "earnings_call",
            "title_hint": title_hint,
            "tickers": [safe_ticker(event["ticker"])],
            "themes": [],
            "event_date": str(event["date"]),
            "canonical_story_id": story_id,
            "canonical_story_revision_id": story_revision_id,
        },
        "primary_source": {
            "kind": "first_party",
            "name": "Mastermind earnings evidence",
            "url": f"https://app.mastermind-x.com{source['locator']}",
            "ref": source_ref,
            "receipt": receipt,
        },
        "sources": [source_ref],
        "source_revisions": {source_ref: receipt},
        "seed_refs": sorted({fact["ref"] for fact in facts}),
        "facts": facts,
        "raw_documents": [{
            "ref": source_ref,
            "text": " ".join(str(item["text"]) for item in digest["facts"]),
        }],
        "chronicle_context": context,
        "slug_hint": str(story["seo"]["slug"]),
        "canonical_story_id": story_id,
        "canonical_story_revision_id": story_revision_id,
        "canonical_story_status": story["status"],
        # Source-ready packets may be staged and inspected, never emitted.  A
        # later verified approval compiler must produce a new approved slot.
        "canonical_emit_allowed": False,
        "approved_claim_ids": list(story["approved_claim_ids"]),
        "article_derivative_id": story["derivatives"]["article_id"],
    }
