"""Replay guard for the Company Intelligence golden corpus (R0-D).

A receipt that cannot be replayed is worthless, so nothing here trusts a stored
hash: every transcript body is re-hashed with the production
``canonical_transcript_body_bytes``, and every exact-span receipt is re-derived by
the production ``receipt_for_span``, which slices the committed bytes and raises if
the slice disagrees.

The v1 payloads round-trip through the REAL ``validate_context`` /
``validate_manifest``, so a schema drift in ``engine/company_intelligence/contracts.py``
breaks this benchmark loudly instead of leaving it quietly wrong.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.company_intelligence.contracts import ContractError, validate_context, validate_manifest
from engine.earnings_narrative.contracts import ContractError as NarrativeContractError
from engine.earnings_narrative.contracts import (
    canonical_transcript_body_bytes,
    receipt_for_span,
    sha256_bytes,
    validate_terminal_transcript,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "research/company_intelligence/GOLDEN_CORPUS_MANIFEST.json"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "company_intelligence"

# engine/earnings_narrative/contracts.py::_RECEIPT_KEYS — the exact-span shape R0-D
# instructs this corpus to reuse rather than reinvent.
RECEIPT_KEYS = frozenset({
    "source_sha256", "segment_index", "segment_sha256", "segment_bytes",
    "span_start_byte", "span_end_byte", "text_sha256",
})


def _load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def documents() -> dict[str, dict]:
    payload = _load("golden_corpus_documents.v1.json")
    assert payload["document_count"] == len(payload["documents"])
    return {row["document_id"]: row for row in payload["documents"]}


# ─────────────────────────────────────────────────────────────────────────────
# Document bodies
# ─────────────────────────────────────────────────────────────────────────────

def test_every_document_is_a_valid_terminal_transcript(documents: dict[str, dict]) -> None:
    assert documents
    for document_id, row in documents.items():
        validate_terminal_transcript(row["body"])
        assert row["provenance"] == "synthetic", document_id
        assert row["body"]["ticker"] == row["ticker"]
        assert row["body"]["id"] == row["transcript_id"]


def test_every_body_hash_replays_with_the_production_serializer(documents: dict[str, dict]) -> None:
    for document_id, row in documents.items():
        body_bytes = canonical_transcript_body_bytes(row["body"])
        assert sha256_bytes(body_bytes) == row["body_sha256"], document_id
        assert len(body_bytes) == row["body_bytes"], document_id


# ─────────────────────────────────────────────────────────────────────────────
# Exact-span receipts — byte replay
# ─────────────────────────────────────────────────────────────────────────────

def test_every_exact_span_receipt_byte_replays(manifest: dict, documents: dict[str, dict]) -> None:
    replayed = 0
    for case in manifest["cases"]:
        receipt = case["receipt"]
        if receipt is None:
            continue
        assert frozenset(receipt) == RECEIPT_KEYS, case["case_id"]

        document = documents[case["excerpt_document_id"]]
        assert receipt["source_sha256"] == document["body_sha256"], case["case_id"]

        segment_text = document["body"]["segments"][receipt["segment_index"]]["text"]
        sliced = segment_text.encode("utf-8")[
            receipt["span_start_byte"]:receipt["span_end_byte"]
        ].decode("utf-8")

        # receipt_for_span re-derives every hash AND replays the byte slice, raising
        # if the span does not reproduce the exact text.
        rederived = receipt_for_span(
            source_sha256=document["body_sha256"],
            segment_index=receipt["segment_index"],
            segment_text=segment_text,
            start_byte=receipt["span_start_byte"],
            end_byte=receipt["span_end_byte"],
            text=sliced,
        )
        assert rederived == receipt, f"{case['case_id']} receipt does not replay"
        assert sliced.strip(), case["case_id"]
        replayed += 1

    assert replayed == manifest["counts"]["cases_with_exact_span_receipt"]
    assert replayed > 0, "no case carries an exact-span receipt — the replay gate is vacuous"


def test_a_tampered_body_fails_the_replay(manifest: dict, documents: dict[str, dict]) -> None:
    """The gate must be able to SEE a failure, or its green means nothing."""
    case = next(c for c in manifest["cases"] if c["receipt"] is not None)
    receipt = case["receipt"]
    document = documents[case["excerpt_document_id"]]
    segment_text = document["body"]["segments"][receipt["segment_index"]]["text"]
    original = segment_text.encode("utf-8")[receipt["span_start_byte"]:receipt["span_end_byte"]].decode("utf-8")

    tampered = segment_text.replace(original, original.replace("was", "wax", 1), 1)
    if tampered == segment_text:  # the chosen span had no "was"; mutate the digits instead
        tampered = segment_text.replace(original, original[:-1] + "!", 1)

    with pytest.raises(NarrativeContractError):
        receipt_for_span(
            source_sha256=document["body_sha256"],
            segment_index=receipt["segment_index"],
            segment_text=tampered,
            start_byte=receipt["span_start_byte"],
            end_byte=receipt["span_end_byte"],
            text=original,
        )


def test_a_shifted_span_fails_the_replay(manifest: dict, documents: dict[str, dict]) -> None:
    case = next(c for c in manifest["cases"] if c["receipt"] is not None)
    receipt = case["receipt"]
    document = documents[case["excerpt_document_id"]]
    segment_text = document["body"]["segments"][receipt["segment_index"]]["text"]
    original = segment_text.encode("utf-8")[receipt["span_start_byte"]:receipt["span_end_byte"]].decode("utf-8")

    with pytest.raises(NarrativeContractError):
        receipt_for_span(
            source_sha256=document["body_sha256"],
            segment_index=receipt["segment_index"],
            segment_text=segment_text,
            start_byte=receipt["span_start_byte"] + 1,
            end_byte=receipt["span_end_byte"] + 1,
            text=original,
        )


# ─────────────────────────────────────────────────────────────────────────────
# v1 payloads through the REAL validators
# ─────────────────────────────────────────────────────────────────────────────

def test_v1_contexts_round_trip_through_the_real_validator() -> None:
    payload = _load("golden_corpus_v1_contexts.v1.json")
    statuses = set()
    for row in payload["contexts"]:
        assert row["expected"] == "valid"
        validate_context(row["context"])
        statuses.add(row["context"]["status"])
    # All four values of the CONTEXT status vocabulary are exercised.
    assert statuses == {"ready", "partial", "stale", "not_covered"}


def test_v1_manifests_round_trip_through_the_real_validator() -> None:
    payload = _load("golden_corpus_v1_manifests.v1.json")
    statuses = set()
    for row in payload["manifests"]:
        assert row["expected"] == "valid"
        validate_manifest(row["manifest"])
        statuses.add(row["manifest"]["status"])
    # A DIFFERENT vocabulary from the context one above — the manifest's
    # known_limits row "status-vocabularies-are-inline-set-literals" made executable.
    assert statuses == {"ready", "degraded", "empty"}


def test_claim_citations_pending_is_still_a_hard_v1_invariant() -> None:
    """Pinned deliberately: Wave 1 replaces this, and the replacement must be visible here.

    ``validate_context`` raises unless every event carries exactly ``True``
    (engine/company_intelligence/contracts.py:501-502).  When Wave 1 lands its v2
    projection, this test is the file that must change with it.
    """
    payload = _load("golden_corpus_v1_contexts.v1.json")
    context = next(row["context"] for row in payload["contexts"] if row["context"]["history"])
    mutated = json.loads(json.dumps(context))
    mutated["history"][0]["claim_citations_pending"] = False
    mutated["latest_event"] = mutated["history"][0]

    with pytest.raises(ContractError, match="claim citations"):
        validate_context(mutated)


def test_a_dropped_context_field_is_rejected_by_the_closed_schema() -> None:
    payload = _load("golden_corpus_v1_contexts.v1.json")
    context = next(row["context"] for row in payload["contexts"] if row["context"]["history"])
    mutated = json.loads(json.dumps(context))
    mutated["unexpected_field"] = 1
    with pytest.raises(ContractError):
        validate_context(mutated)


# ─────────────────────────────────────────────────────────────────────────────
# The EDGAR identity join — computed, not asserted in prose
# ─────────────────────────────────────────────────────────────────────────────

def test_the_two_edgar_readers_share_no_event_key(manifest: dict) -> None:
    payload = _load("golden_corpus_edgar_identity.v1.json")
    assert payload["pairs"], "no EDGAR identity pairs in the corpus"

    case_ids = {case["case_id"] for case in manifest["cases"]
                if case["difficulty_class"] == "edgar_identity_join"}
    assert {row["case_ref"] for row in payload["pairs"]} == case_ids

    for row in payload["pairs"]:
        collector_keys = set(row["collector_edgar_earnings_8k_row"])
        wire_keys = set(row["engine_edgar_earnings_wire_row"]) - {"when_semantics"}
        shared = collector_keys & wire_keys

        # The finding: the intersection is `ticker` alone, which cannot key an event.
        assert shared == {"ticker"}, f"{row['case_ref']} intersection drifted: {sorted(shared)}"
        assert row["joinable_keys_today"] == ["ticker"]
        assert "accession" not in collector_keys
        assert "cik" not in wire_keys and "filing_date" not in wire_keys
        assert row["missing_for_join"]["collector_edgar_earnings_8k"] == ["accession"]
        assert set(row["missing_for_join"]["engine_edgar_earnings_wire"]) >= {"cik", "filing_date"}

    assert payload["open_contract_question"].strip()
