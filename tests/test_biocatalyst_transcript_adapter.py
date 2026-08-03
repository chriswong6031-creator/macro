from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

import engine.earnings_narrative.biocatalyst_transcript_adapter as adapter
from engine.sector_intelligence.contracts import ContractValidationError, validate_contract


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "a" * 64
OBJECT_SHA = "b" * 64


def _receipt(text: str, *, index: int, start: int) -> dict[str, object]:
    return {
        "source_sha256": SOURCE_SHA,
        "segment_sha256": sha256(f"segment-{index}".encode()).hexdigest(),
        "segment_index": index,
        "segment_bytes": 4096,
        "span_start_byte": start,
        "span_end_byte": start + len(text.encode("utf-8")),
        "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
    }


def _reader_success(text: str) -> dict:
    numeric = "12%"
    return {
        "available": True,
        "ticker": "BIOT",
        "is_context_only": True,
        "authority": "context_only",
        "generation_id": "earnctxgen_test_01",
        "knowledge_cutoff": "2026-08-02T21:00:00Z",
        "event": {
            "ticker": "BIOT",
            "transcript_id": "2026Q2",
            "period": "Q2 FY2026",
            "date": "2026-08-01",
        },
        "categories": ["guidance"],
        "facts": [
            {
                "claim_id": "quote_1",
                "quote": {
                    "claim_id": "quote_1",
                    "kind": "quote",
                    "text": text,
                    "receipt": _receipt(text, index=0, start=100),
                },
                "speaker": "Chief Executive Officer",
                "role": "executive",
                "chapter": "prepared_remarks",
                "categories": ["guidance"],
                "numeric": [
                    {
                        "claim_id": "numeric_1",
                        "kind": "numeric",
                        "text": numeric,
                        "receipt": _receipt(numeric, index=0, start=220),
                    }
                ],
            }
        ],
        "source_completeness": {
            "release": "not_ingested",
            "filing": "not_ingested",
            "transcript": "present",
            "slides": "not_ingested",
            "consensus": "unlicensed_absent",
        },
        "links": {"record": "/private", "dossier": "/private", "terminal": "/private"},
        "receipts": {
            "context_id": "earnctx_" + ("c" * 32),
            "source_sha256": SOURCE_SHA,
            "known_at": "2026-08-02T20:00:00Z",
            "correction_status": "corrected",
            "object_sha256": OBJECT_SHA,
        },
        "permissions": {"prophet_authority": False},
        # Deliberately hostile extras: the adapter must never carry handles.
        "object_key": "private/earnings/should-not-leak.json",
        "private_path": "/var/lib/private/should-not-leak.json",
    }


def _rehash_read(payload: dict) -> None:
    query = payload["query"]
    ticker = query["ticker"] if isinstance(query["ticker"], str) else "unavailable"
    payload["read_id"] = adapter._stable_id(
        f"earnings_transcript_span_read_{ticker}_", adapter._read_identity(payload)
    )
    payload["read_payload_sha256"] = adapter.canonical_json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"read_id", "read_payload_sha256"}
        }
    )


def _rehash_candidate(payload: dict) -> None:
    payload["candidate_id"] = adapter._stable_id(
        "biocatalyst_transcript_mention_", adapter._candidate_identity(payload)
    )
    payload["candidate_payload_sha256"] = adapter.canonical_json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"candidate_id", "candidate_payload_sha256"}
        }
    )


def _rehash_bundle(payload: dict) -> None:
    payload["bundle_id"] = adapter._stable_id(
        "biocatalyst_transcript_context_bundle_", adapter._bundle_identity(payload)
    )
    payload["bundle_payload_sha256"] = adapter.canonical_json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"bundle_id", "bundle_payload_sha256"}
        }
    )


def test_private_reader_is_called_once_and_projects_exact_transcript_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[dict, Path | None]] = []
    upstream = _reader_success(
        "We expect to start a Phase 3 clinical trial, discuss the FDA path, and have 12% enrollment growth."
    )

    def fake_reader(params: dict, *, root: Path | None) -> dict:
        calls.append((dict(params), root))
        return deepcopy(upstream)

    monkeypatch.setattr(adapter, "_read_earnings_evidence", fake_reader)
    bundle = adapter.read_earnings_transcript_context_bundle(
        {"ticker": "biot", "as_of": "2026-08-02T20:00:00.123456Z"}, root=tmp_path
    )
    result = bundle["span_read"]

    assert calls == [
        ({"ticker": "BIOT", "as_of": "2026-08-02T20:00:00.123456Z"}, tmp_path)
    ]
    assert result["available"] is True
    assert result["query"]["as_of"] == "2026-08-02T20:00:00.123456Z"
    assert result["document"]["source_kind"] == "transcript"
    assert result["document"]["correction_status"] == "corrected"
    assert result["document"]["known_at"] == "2026-08-02T20:00:00Z"
    assert result["generation"]["knowledge_cutoff"] == "2026-08-02T21:00:00Z"
    assert result["span_count"] == 2
    assert result["coverage"]["absence_conclusion"] is False
    assert result["authority"]["decision_authority"] is False
    assert result["integrity_scope"] == bundle["integrity_scope"] == {
        "validation": "self_consistent_receipt_bound_projection",
        "source_authenticity": "trusted_upstream_reader_required_not_independently_attested",
        "authorized_transport": "private_in_process_only",
        "persistence_authorized": False,
    }
    assert "object_key" not in json.dumps(result)
    assert "private_path" not in json.dumps(result)
    assert "/var/lib/" not in json.dumps(result)
    validate_contract(bundle, repo_root=ROOT)

    candidates = bundle["candidates"]
    assert bundle["candidate_count"] == len(candidates)
    assert {candidate["mention_class"] for candidate in candidates} == {
        "clinical_trial_mention", "regulatory_mention",
    }
    for candidate in candidates:
        assert candidate["asserted"] is False
        assert candidate["review_required"] is True
        assert candidate["no_negative_conclusion"] is True
        assert candidate["authority"]["decision_authority"] is False
        assert "text" not in candidate["source_span"]
    adapter.validate_transcript_context_bundle(bundle)


def test_contract_cannot_upgrade_itself_to_attested_or_cross_boundary_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapter,
        "_read_earnings_evidence",
        lambda _params, *, root: _reader_success("We expect a Phase 3 trial."),
    )
    bundle = adapter.read_earnings_transcript_context_bundle({"ticker": "BIOT"})

    upgrades = (
        ("source_authenticity", "independently_attested"),
        ("authorized_transport", "api_or_persistent_store"),
        ("persistence_authorized", True),
    )
    for field, value in upgrades:
        forged = deepcopy(bundle)
        forged["integrity_scope"][field] = value
        _rehash_bundle(forged)
        with pytest.raises(ContractValidationError):
            validate_contract(forged, repo_root=ROOT)


def test_invalid_input_and_unavailable_results_are_bounded_and_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    def never_reader(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("invalid input must not open the upstream reader")

    monkeypatch.setattr(adapter, "_read_earnings_evidence", never_reader)
    invalid_ticker = adapter.read_earnings_transcript_context_bundle({"ticker": "bad ticker"})
    invalid_as_of = adapter.read_earnings_transcript_context_bundle(
        {"ticker": "BIOT", "as_of": "2026-08-02T20:00:00"}
    )

    for bundle, reason in ((invalid_ticker, "invalid_ticker"), (invalid_as_of, "invalid_as_of")):
        result = bundle["span_read"]
        assert result["available"] is False
        assert result["unavailable_reason"] == reason
        assert result["document"] is None
        assert result["generation"] is None
        assert result["spans"] == []
        assert result["coverage"]["absence_conclusion"] is False
        assert bundle["candidate_count"] == 0
        assert bundle["candidates"] == []
        validate_contract(bundle, repo_root=ROOT)


def test_lexical_terms_are_boundary_aware_and_empty_is_not_a_negative_conclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_reader(_params: dict, *, root: Path | None) -> dict:
        return _reader_success("The treatment is individualized and the team discussed routine operations.")

    monkeypatch.setattr(adapter, "_read_earnings_evidence", fake_reader)
    bundle = adapter.read_earnings_transcript_context_bundle({"ticker": "BIOT"})
    result = bundle["span_read"]
    assert result["available"] is True
    # "atm" must not fire inside treatment and "ind" must not fire inside individualized.
    assert bundle["candidates"] == []
    assert result["coverage"]["absence_conclusion"] is False


def test_all_nine_clinical_terms_fit_the_closed_candidate_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    text = (
        "Clinical trial Phase 1 Phase 2 Phase 3 Phase I Phase II Phase III "
        "endpoint enrollment."
    )

    def fake_reader(_params: dict, *, root: Path | None) -> dict:
        return _reader_success(text)

    monkeypatch.setattr(adapter, "_read_earnings_evidence", fake_reader)
    bundle = adapter.read_earnings_transcript_context_bundle({"ticker": "BIOT"})
    candidates = bundle["candidates"]
    clinical = [
        candidate
        for candidate in candidates
        if candidate["mention_class"] == "clinical_trial_mention"
    ]

    assert len(clinical) == 1
    assert clinical[0]["matched_terms"] == sorted(
        term for mention_class, terms in adapter._MENTION_TERMS
        if mention_class == "clinical_trial_mention"
        for term in terms
    )
    validate_contract(bundle, repo_root=ROOT)


def test_registry_semantics_reject_span_and_candidate_tampering_after_rehash(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_reader(_params: dict, *, root: Path | None) -> dict:
        return _reader_success("We expect a Phase 3 clinical trial and an FDA meeting.")

    monkeypatch.setattr(adapter, "_read_earnings_evidence", fake_reader)
    bundle = adapter.read_earnings_transcript_context_bundle({"ticker": "BIOT"})
    result = bundle["span_read"]
    forged_bundle = deepcopy(bundle)
    forged_read = forged_bundle["span_read"]
    forged_read["spans"][0]["text"] = "Forged text that is not receipt-bound."
    _rehash_read(forged_read)
    _rehash_bundle(forged_bundle)
    with pytest.raises(ContractValidationError):
        validate_contract(forged_bundle, repo_root=ROOT)

    forged_coordinates_bundle = deepcopy(bundle)
    forged_coordinates = forged_coordinates_bundle["span_read"]
    receipt = forged_coordinates["spans"][0]["receipt"]
    receipt["span_end_byte"] += 1
    span = forged_coordinates["spans"][0]
    span["span_id"] = adapter._span_id(
        forged_coordinates["document"]["document_revision_id"], span
    )
    _rehash_read(forged_coordinates)
    _rehash_bundle(forged_coordinates_bundle)
    with pytest.raises(ContractValidationError):
        validate_contract(forged_coordinates_bundle, repo_root=ROOT)

    forged_candidate_bundle = deepcopy(bundle)
    forged_candidate = forged_candidate_bundle["candidates"][0]
    forged_candidate["mention_class"] = "regulatory_mention"
    forged_candidate["matched_terms"] = ["ind"]
    _rehash_candidate(forged_candidate)
    _rehash_bundle(forged_candidate_bundle)
    with pytest.raises(ContractValidationError):
        validate_contract(forged_candidate_bundle, repo_root=ROOT)

    removed_candidate_bundle = deepcopy(bundle)
    removed_candidate_bundle["candidates"].pop()
    removed_candidate_bundle["candidate_count"] -= 1
    _rehash_bundle(removed_candidate_bundle)
    with pytest.raises(ContractValidationError):
        validate_contract(removed_candidate_bundle, repo_root=ROOT)


def test_atomic_bundle_registry_rejects_complete_set_binding_and_identity_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_reader(_params: dict, *, root: Path | None) -> dict:
        return _reader_success("We expect a Phase 3 clinical trial and an FDA meeting.")

    monkeypatch.setattr(adapter, "_read_earnings_evidence", fake_reader)
    bundle = adapter.read_earnings_transcript_context_bundle({"ticker": "BIOT"})
    assert len(bundle["candidates"]) == 2

    added_candidate_bundle = deepcopy(bundle)
    added_candidate_bundle["candidates"].append(
        deepcopy(added_candidate_bundle["candidates"][0])
    )
    added_candidate_bundle["candidate_count"] += 1
    _rehash_bundle(added_candidate_bundle)

    mismatched_read_bundle = deepcopy(bundle)
    mismatched_read = mismatched_read_bundle["candidates"][0]
    mismatched_read["source_read"]["read_payload_sha256"] = "0" * 64
    _rehash_candidate(mismatched_read)
    _rehash_bundle(mismatched_read_bundle)

    mismatched_span_bundle = deepcopy(bundle)
    mismatched_span = mismatched_span_bundle["candidates"][0]
    mismatched_span["source_span"]["claim_id"] = "wrong_claim"
    _rehash_candidate(mismatched_span)
    _rehash_bundle(mismatched_span_bundle)

    reversed_order_bundle = deepcopy(bundle)
    reversed_order_bundle["candidates"].reverse()
    _rehash_bundle(reversed_order_bundle)

    wrong_count_bundle = deepcopy(bundle)
    wrong_count_bundle["candidate_count"] += 1
    _rehash_bundle(wrong_count_bundle)

    wrong_hash_bundle = deepcopy(bundle)
    wrong_hash_bundle["bundle_payload_sha256"] = "0" * 64

    wrong_id_bundle = deepcopy(bundle)
    wrong_id_bundle["bundle_id"] = (
        "biocatalyst_transcript_context_bundle_" + ("0" * 24)
    )

    for forged_bundle in (
        added_candidate_bundle,
        mismatched_read_bundle,
        mismatched_span_bundle,
        reversed_order_bundle,
        wrong_count_bundle,
        wrong_hash_bundle,
        wrong_id_bundle,
    ):
        with pytest.raises(ContractValidationError):
            validate_contract(forged_bundle, repo_root=ROOT)


def _capacity_reader_success(*, span_count: int) -> dict:
    """Build a valid upstream-shaped 48/49-span corpus without I/O."""

    if span_count not in {48, 49}:
        raise AssertionError("capacity fixture supports only the exact boundary")
    text = "12% Phase 3 FDA collaboration financing"
    numeric_counts = [7] * 6
    if span_count == 49:
        numeric_counts[0] = 8
    facts: list[dict] = []
    coordinate = 100
    for fact_index, numeric_count in enumerate(numeric_counts):
        quote_claim_id = f"quote_{fact_index}"
        quote = {
            "claim_id": quote_claim_id,
            "kind": "quote",
            "text": text,
            "receipt": _receipt(text, index=fact_index, start=coordinate),
        }
        coordinate += 60
        numeric = []
        for numeric_index in range(numeric_count):
            claim_id = f"numeric_{fact_index}_{numeric_index}"
            numeric.append(
                {
                    "claim_id": claim_id,
                    "kind": "numeric",
                    "text": text,
                    "receipt": _receipt(text, index=fact_index, start=coordinate),
                }
            )
            coordinate += 60
        facts.append(
            {
                "claim_id": quote_claim_id,
                "quote": quote,
                "speaker": "Chief Executive Officer",
                "role": "executive",
                "chapter": "prepared_remarks",
                "categories": ["guidance"],
                "numeric": numeric,
            }
        )
    assert sum(1 + len(fact["numeric"]) for fact in facts) == span_count
    payload = _reader_success(text)
    payload["facts"] = facts
    return payload


def test_atomic_bundle_exact_capacity_and_overflow_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapter,
        "_read_earnings_evidence",
        lambda _params, *, root: _capacity_reader_success(span_count=48),
    )
    exact = adapter.read_earnings_transcript_context_bundle({"ticker": "BIOT"})
    assert exact["span_read"]["available"] is True
    assert exact["span_read"]["span_count"] == 48
    assert exact["candidate_count"] == 192
    assert len(exact["candidates"]) == 192
    validate_contract(exact, repo_root=ROOT)

    monkeypatch.setattr(
        adapter,
        "_read_earnings_evidence",
        lambda _params, *, root: _capacity_reader_success(span_count=49),
    )
    overflow = adapter.read_earnings_transcript_context_bundle({"ticker": "BIOT"})
    assert overflow["span_read"]["available"] is False
    assert overflow["span_read"]["unavailable_reason"] == "integrity_failure"
    assert overflow["candidate_count"] == 0
    assert overflow["candidates"] == []
    validate_contract(overflow, repo_root=ROOT)
