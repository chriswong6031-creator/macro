"""Strict point-in-time contract tests for the event-state projection.

This is deliberately an event/edge/review projection only.  A later Wave 2
term engine may add separately-versioned observations; it must not smuggle
financial estimates or model output into this event-state surface.
"""
from __future__ import annotations

import copy
import json
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.event_spine import build_event_version, build_review_queue, make_stable_span
from engine.capital_structure.projection import build_projection_bundle, validate_projection_bundle


ROOT = Path(__file__).resolve().parents[1]
HASH = "f" * 64
GENERATED_AT = "2026-08-10T12:00:00Z"
UNAVAILABLE = [
    "active_instrument_overhang",
    "cash_runway",
    "financing_probability",
    "fully_diluted_shares",
    "instruments",
    "normalized_terms",
    "offering_ability",
    "remaining_capacity",
]


def _event(
    accession: str,
    form: str,
    *,
    seen: str,
    accepted: str | None = None,
    ticker: str | None = "ABC",
    issuer_id: str = "sec:cik:0000000001",
    cik: str = "1",
    correction_version: int = 1,
    correction_of: str | None = None,
    source_suffix: str = "",
) -> dict:
    manifest_id = f"manifest:{accession}:{correction_version}:{source_suffix or 'base'}"
    observation = {
        "source_system": "sec_edgar",
        "source_id": accession,
        "manifest_id": manifest_id,
        "accession": accession,
        "issuer_id": issuer_id,
        "cik": cik,
        "ticker": ticker,
        "aliases": ["ABC Corp", "ABC Holdings"],
        "form": form,
        "file_number": "333-123",
        "filing_date": "2026-08-01",
        "accepted_at": accepted or seen,
        "first_seen_at": seen,
        "primary_document_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}.htm",
        "exhibit_urls": [f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}-exhibit.htm"],
        "content_hashes": [HASH],
    }
    span = make_stable_span(manifest_id, f"{form}:{source_suffix or accession}", locator="document")
    return build_event_version(
        observation,
        [span],
        correction_version=correction_version,
        correction_of=correction_of,
    )


def _edge(from_event_id: str, to_event_id: str, *, observed_at: str) -> dict:
    digest = sha256(f"{from_event_id}|{to_event_id}|{observed_at}".encode()).hexdigest()
    return {
        "schema": "capital_structure.event_edge.v1",
        "edge_id": f"edge:cs:{digest[:24]}",
        "from_event_id": from_event_id,
        "to_event_id": to_event_id,
        "relationship": "effectuates",
        "link_method": "explicit_accession",
        "observed_at": observed_at,
        "immutable_record": True,
    }


def _telemetry(
    *,
    status: str = "ok",
    event_count: int = 0,
    edge_count: int = 0,
    review_count: int = 0,
) -> dict:
    is_degraded = status == "degraded"
    is_empty = status == "no_source_manifest"
    manifest_count = 0 if is_empty else max(1, event_count)
    return {
        "schema": "capital_structure.telemetry.v1",
        "status": status,
        "as_of": GENERATED_AT,
        "generation_id": None if (is_degraded or is_empty) else "generation:cs:" + ("c" * 24),
        "authority": {
            "is_context_only": True,
            "rank_authority": False,
            "sizing_authority": False,
            "entry_authority": False,
            "prophet_authority": False,
        },
        "form_policy": {
            "policy_version": "capital-structure-sec-form-policy/1.0.0",
            "wave1_discovery": ["S-3"],
            "wave2_declared_not_collected": ["8-K"],
            "capital_relevant_declared_not_collected": ["S-8"],
        },
        "coverage_claim": "explicit_wave1_form_allowlist_only",
        "known_exclusions": ["8-K", "S-8"],
        "counts": {
            "source_manifests": manifest_count,
            "accessions_grouped": 0 if is_empty else event_count,
            "event_versions": 0 if (is_degraded or is_empty) else event_count,
            "new_event_versions": 0 if (is_degraded or is_empty) else event_count,
            "event_edges": 0 if (is_degraded or is_empty) else edge_count,
            "review_queue": 0 if (is_degraded or is_empty) else review_count,
            "compile_failures": 1 if is_degraded else 0,
        },
        "compile_failures": (
            [{"accession": None, "state": "invalid_source", "errors": ["fixture degradation"]}]
            if is_degraded else []
        ),
        "migration_receipt": {
            "schema": "capital_structure.migration_receipt.v1",
            "receipt_id": "migration:capital-structure-event-v1",
            "source_contract": "capital_structure.event.v1",
            "target_contract": "company_event.v1",
            "state": "temporary_adapter_active_pending_target",
            "owner": "capital-structure-intelligence",
            "review_by": "2026-10-01",
            "adjudicator": "operator",
            "acceptance_evidence": ["docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md"],
            "pit_preservation_state": "verified",
            "legacy_writer": "collectors/edgar_dilution.py",
            "legacy_projection_state": "shadow_only_no_cutover",
            "immutable_record": True,
        },
        "source_ledger_receipt": {
            "schema": "capital_structure.source_ledger_receipt.v1",
            "record_count": manifest_count,
            "prefix_sha256": "d" * 64,
            "form_policy_version": "capital-structure-sec-form-policy/1.0.0",
            "immutable_prefix": True,
        },
        "artifact_hashes": {
            "event_versions": None if (is_degraded or is_empty) else HASH,
            "event_edges": None if (is_degraded or is_empty) else HASH,
            "review_queue": None if (is_degraded or is_empty) else HASH,
        },
    }


def _build(
    events: list[dict],
    *,
    edges: list[dict] | None = None,
    review_items: list[dict] | None = None,
    as_of: str = GENERATED_AT,
    telemetry: dict | None = None,
) -> dict:
    return build_projection_bundle(
        events,
        edges or [],
        review_items or [],
        telemetry or _telemetry(
            event_count=len(events), edge_count=len(edges or []), review_count=len(review_items or []),
        ),
        as_of=as_of,
        generated_at=GENERATED_AT,
    )


def _schema_errors(bundle: dict) -> list:
    schema = json.loads((ROOT / "contracts/capital_structure_projection.schema.json").read_text())
    return list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(bundle))


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*( _all_keys(child) for child in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_all_keys(child) for child in value)) if value else set()
    return set()


def test_projection_bundle_is_strict_schema_valid_context_only_and_public_safe():
    event = _event("0000000001-26-000001", "S-3", seen="2026-08-01T10:00:03Z")
    bundle = _build([event])

    validate_projection_bundle(bundle, ROOT / "contracts/capital_structure_projection.schema.json")
    assert not _schema_errors(bundle)
    assert bundle["schema"] == "capital_structure.projection_bundle.v1"
    assert bundle["authority"] == {
        "is_context_only": True,
        "rank_authority": False,
        "sizing_authority": False,
        "entry_authority": False,
        "prophet_authority": False,
    }
    record = bundle["records"][0]
    assert record["schema"] == "capital_structure.projection.v1"
    assert record["issuer_id"] == "sec:cik:0000000001"
    assert record["authority"] == bundle["authority"]
    source = record["latest_observed_event"]["source"]
    assert source["filing_url"].startswith("https://www.sec.gov/")
    assert source["manifest_ids"] == [event["source"]["manifest_ids"][0]]
    assert source["evidence"] == [event["evidence"][0]]
    assert record["latest_observed_event"]["clocks"] == {
        "sec_accepted_at": "2026-08-01T10:00:03Z",
        "mastermind_observed_at": "2026-08-01T10:00:03Z",
        "projection_generated_at": GENERATED_AT,
    }
    assert bundle["unavailable"] == UNAVAILABLE
    forbidden = {"object_key", "raw_document", "raw_docs", "score", "scores", "probability", "probabilities", "capacity", "runway", "overhang"}
    assert not (_all_keys(bundle) & forbidden)


def test_system_point_in_time_uses_correction_only_after_mastermind_observed_clock():
    original = _event("0000000001-26-000001", "S-3", seen="2026-08-01T10:00:00Z")
    correction = _event(
        "0000000001-26-000001", "S-3", seen="2026-08-03T10:00:00Z",
        correction_version=2, correction_of=original["event_id"], source_suffix="correction",
    )

    before = _build([original, correction], as_of="2026-08-02T23:59:59Z")
    after = _build([original, correction], as_of="2026-08-03T10:00:00Z")

    assert before["records"][0]["latest_observed_event"]["event_id"] == original["event_id"]
    assert after["records"][0]["latest_observed_event"]["event_id"] == correction["event_id"]
    assert after["records"][0]["latest_observed_event"]["correction_of"] == original["event_id"]
    correction_changes = [
        item for item in after["records"][0]["what_changed"]
        if item["event_id"] == correction["event_id"]
    ]
    assert len(correction_changes) == 1
    assert correction_changes[0]["observed_at"] == "2026-08-03T10:00:00Z"


def test_edge_is_visible_only_after_its_own_observed_clock_and_preserves_three_clocks():
    parent = _event("0000000001-26-000001", "S-3", seen="2026-08-01T10:00:00Z")
    child = _event("0000000001-26-000002", "EFFECT", seen="2026-08-02T10:00:00Z")
    edge = _edge(child["event_id"], parent["event_id"], observed_at="2026-08-04T11:00:00Z")

    before = _build([parent, child], edges=[edge], as_of="2026-08-04T10:59:59Z")
    after = _build([parent, child], edges=[edge], as_of="2026-08-04T11:00:00Z")

    assert before["records"][0]["latest_observed_event"]["relationships"] == []
    assert after["records"][0]["latest_observed_event"]["relationships"] == [{
        "edge_id": edge["edge_id"],
        "relationship": "effectuates",
        "to_event_id": parent["event_id"],
        "observed_at": "2026-08-04T11:00:00Z",
    }]
    relationship = [item for item in after["records"][0]["what_changed"] if item["edge_id"] == edge["edge_id"]]
    assert relationship == [{
        "change_id": relationship[0]["change_id"],
        "change_type": "effectuates_link_observed",
        "event_id": child["event_id"],
        "label": "Effectiveness link observed",
        "edge_id": edge["edge_id"],
        "observed_at": "2026-08-04T11:00:00Z",
    }]
    assert after["records"][0]["latest_observed_event"]["clocks"]["sec_accepted_at"] == "2026-08-02T10:00:00Z"
    assert after["records"][0]["latest_observed_event"]["clocks"]["mastermind_observed_at"] == "2026-08-02T10:00:00Z"
    assert after["records"][0]["latest_observed_event"]["clocks"]["projection_generated_at"] == GENERATED_AT


def test_edge_cannot_reveal_future_endpoint_and_cross_issuer_links_fail_closed():
    parent = _event("0000000001-26-000001", "S-3", seen="2026-08-05T10:00:00Z")
    child = _event("0000000001-26-000002", "EFFECT", seen="2026-08-02T10:00:00Z")
    edge = _edge(child["event_id"], parent["event_id"], observed_at="2026-08-03T10:00:00Z")

    before_parent = _build(
        [parent, child], edges=[edge], as_of="2026-08-04T23:59:59Z"
    )
    record = before_parent["records"][0]
    assert record["latest_observed_event"]["event_id"] == child["event_id"]
    assert record["latest_observed_event"]["relationships"] == []
    assert all(item.get("edge_id") != edge["edge_id"] for item in record["what_changed"])
    assert parent["event_id"] not in json.dumps(before_parent, sort_keys=True)

    other = _event(
        "0000000002-26-000001",
        "S-3",
        seen="2026-08-02T11:00:00Z",
        issuer_id="sec:cik:0000000002",
        cik="2",
        ticker="DEF",
    )
    cross_issuer = _edge(
        child["event_id"], other["event_id"], observed_at="2026-08-03T10:00:00Z"
    )
    with pytest.raises(ValueError, match="cross-issuer event edge is forbidden"):
        _build([child, other], edges=[cross_issuer])


def test_deferred_424b_is_preserved_as_unknown_reviewable_event_not_a_financing_claim():
    prospectus = _event("0000000001-26-000003", "424B5", seen="2026-08-05T10:00:00Z")
    review = build_review_queue([prospectus])
    bundle = _build([prospectus], review_items=review)

    record = bundle["records"][0]
    latest = record["latest_observed_event"]
    assert latest["classification_state"] == "deferred_ambiguous_content"
    assert latest["family"] == "other"
    assert latest["subtype"] == "prospectus_event"
    assert record["coverage"] == {
        "state": "partial",
        "event_count": 1,
        "classified_event_count": 0,
        "deferred_event_count": 1,
        "review_count": 1,
        "review_queue_semantics": "current_rebuild_not_historical_ledger",
        "contradiction_ids": [],
    }
    assert latest["review"]["state"] == "pending"
    assert latest["review"]["queue_ids"] == [review[0]["queue_id"]]
    assert latest["review"]["items"] == [{
        "queue_id": review[0]["queue_id"],
        "classification_state": "deferred_ambiguous_content",
        "defer_reason": "prospectus_requires_content_to_distinguish_pricing_atm_resale_or_rights",
        "candidate_event_ids": [],
        "first_queued_at": "2026-08-05T10:00:00Z",
    }]
    assert "priced" not in json.dumps(bundle).lower()


def test_cik_identity_survives_ticker_change_without_merging_or_splitting_issuer_records():
    old = _event("0000000001-26-000001", "S-3", seen="2026-08-01T10:00:00Z", ticker="ABC")
    new = _event("0000000001-26-000002", "EFFECT", seen="2026-08-02T10:00:00Z", ticker="XYZ")
    bundle = _build([old, new])

    assert len(bundle["records"]) == 1
    record = bundle["records"][0]
    assert record["issuer_id"] == "sec:cik:0000000001"
    assert record["identity"]["cik"] == "1"
    assert record["identity"]["ticker"] == "XYZ"
    assert record["identity"]["observed_tickers"] == ["ABC", "XYZ"]
    assert record["coverage"]["event_count"] == 2


def test_degraded_telemetry_is_unavailable_not_zero_and_emits_no_issuer_records():
    event = _event("0000000001-26-000001", "S-3", seen="2026-08-01T10:00:00Z")
    bundle = _build([event], telemetry=_telemetry(status="degraded", event_count=1))

    assert bundle["coverage"]["state"] == "unavailable"
    assert bundle["coverage"]["source_status"] == "degraded"
    assert bundle["coverage"]["reason"] == "source_generation_degraded"
    assert bundle["coverage"]["issuer_count"] == 0
    assert bundle["records"] == []
    assert bundle["unavailable"] == UNAVAILABLE


def test_projection_is_idempotent_and_order_independent_without_private_storage_leakage():
    first = _event("0000000001-26-000001", "S-3", seen="2026-08-01T10:00:00Z")
    second = _event("0000000001-26-000002", "EFFECT", seen="2026-08-02T10:00:00Z")
    edge = _edge(second["event_id"], first["event_id"], observed_at="2026-08-03T10:00:00Z")
    forward = _build([first, second], edges=[edge])
    reverse = _build([second, first], edges=[edge])

    assert forward == reverse == _build([first, second], edges=[edge])
    wire = json.dumps(forward, sort_keys=True)
    assert "object_key" not in wire
    assert "capital_structure/sec/sha256" not in wire
    assert "r2_" not in wire


def test_validator_rejects_private_or_forbidden_projection_properties():
    event = _event("0000000001-26-000001", "S-3", seen="2026-08-01T10:00:00Z")
    bundle = _build([event])
    poisoned = copy.deepcopy(bundle)
    poisoned["records"][0]["latest_observed_event"]["source"]["object_key"] = "private/r2/key"

    with pytest.raises(ValueError):
        validate_projection_bundle(poisoned, ROOT / "contracts/capital_structure_projection.schema.json")

    poisoned = copy.deepcopy(bundle)
    poisoned["records"][0]["score"] = 99
    with pytest.raises(ValueError):
        validate_projection_bundle(poisoned, ROOT / "contracts/capital_structure_projection.schema.json")

    poisoned = copy.deepcopy(bundle)
    poisoned["records"][0]["latest_observed_event"]["source"]["filing_url"] = "https://example.com/private"
    with pytest.raises(ValueError):
        validate_projection_bundle(poisoned, ROOT / "contracts/capital_structure_projection.schema.json")


def test_verified_telemetry_counts_and_source_clock_must_match_projection_inputs():
    event = _event("0000000001-26-000001", "S-3", seen="2026-08-01T10:00:00Z")
    bad_counts = _telemetry(event_count=2)
    with pytest.raises(ValueError, match="event_versions count"):
        _build([event], telemetry=bad_counts)

    with pytest.raises(ValueError, match="cannot exceed the verified source"):
        build_projection_bundle(
            [event], [], [], _telemetry(event_count=1),
            as_of="2026-08-11T00:00:00Z",
            generated_at="2026-08-12T00:00:00Z",
        )
