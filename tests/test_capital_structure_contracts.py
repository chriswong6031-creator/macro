"""Strict Wave-0 JSON-schema contracts for Capital Structure Intelligence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.source_identity import manifest_id_for


ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
HASH = "a" * 64


def _schema(name: str) -> dict:
    with (CONTRACTS / name).open(encoding="utf-8") as fh:
        return json.load(fh)


def _validate(name: str, instance: dict) -> None:
    validator = Draft202012Validator(_schema(name), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


def _invalid(name: str, instance: dict, fragment: str) -> None:
    validator = Draft202012Validator(_schema(name), format_checker=FormatChecker())
    messages = [error.message for error in validator.iter_errors(instance)]
    assert any(fragment in message for message in messages), messages


def _issuer() -> dict:
    return {"issuer_id": "issuer:0000320193", "cik": "320193", "ticker": "AAPL", "aliases": ["Apple Inc."]}


def _source_manifest() -> dict:
    record = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": "0000320193-26-000001",
        "issuer": _issuer(),
        "filing": {"accession": "0000320193-26-000001", "form": "S-3", "filing_date": "2026-08-01", "accepted_at": "2026-08-01T11:00:00Z", "file_number": "333-123456"},
        "document": {"canonical_url": "https://www.sec.gov/Archives/example.htm", "document_name": "primary.htm", "document_type": "S-3", "document_role": "primary", "sequence": "1", "media_type": "text/html", "byte_length": 1024, "document_version": 1, "content_sha256": HASH, "parent_manifest_id": None, "root_locator": "sha256:" + HASH},
        "retrieval": {"retrieved_at": "2026-08-01T12:00:00Z", "first_seen_at": "2026-08-01T12:00:00Z", "transport_status": "retrieved"},
        "storage": {"backend": "r2", "store_id": "r2_shared", "object_key": "capital_structure/sec/sha256/aa/" + HASH, "content_addressed": True, "retention_state": "retained"},
        "rights": {"redistribution_class": "public_source_link", "attribution_required": True, "license_note": "SEC filing"},
        "privacy": {"classification": "public", "contains_personal_data": False},
        "parser": {"eligibility": "eligible", "corruption_state": "clean", "parser_version": "capital-structure-parser/1.0"},
        "spans": [{"span_id": "span:cover", "locator_type": "page", "locator": "page=1", "text_sha256": HASH}]
    }
    record["manifest_id"] = manifest_id_for(record)
    return record


def _event() -> dict:
    return {
        "schema": "capital_structure.event.v1", "event_id": "event:sec:0001",
        "source": {"source_system": "sec_edgar", "source_id": "0000320193-26-000001", "manifest_ids": ["manifest:sec:0001", "manifest:sec:0001:exhibit:1"]},
        "issuer": _issuer(),
        "filing": {"accession": "0000320193-26-000001", "form": "S-3", "file_number": "333-123456", "filing_date": "2026-08-01", "accepted_at": "2026-08-01T11:00:00Z", "primary_document_url": "https://www.sec.gov/Archives/example.htm", "exhibit_urls": [], "content_hashes": [HASH]},
        "event": {"family": "shelf", "subtype": "registration", "affected_instrument_candidate_ids": []},
        "lifecycle": {"state": "filed"},
        "relationships": {"amendment_of": None, "supersedes": []},
        "classification": {"state": "classified", "defer_reason": None},
        "evidence": [{"manifest_id": "manifest:sec:0001", "span_id": "span:cover", "text_sha256": HASH}],
        "extraction": {"method": "deterministic", "parser_version": "1.0", "review_status": "unreviewed"},
        "reconciliation": {"state": "unreconciled", "contradiction_ids": []},
        "version": {"immutable_record": True, "correction_version": 1, "correction_of": None},
        "point_in_time": {"first_seen_at": "2026-08-01T11:01:00Z", "public_available_at": None, "system_available_at": "2026-08-01T11:01:00Z", "available_at": "2026-08-01T11:01:00Z"},
        "authority": {
            "is_context_only": True, "rank_authority": False,
            "sizing_authority": False, "entry_authority": False,
            "prophet_authority": False,
        }
    }


def _term() -> dict:
    return {
        "schema": "capital_structure.instrument_term_observation.v1", "observation_id": "term:1", "issuer_id": "issuer:0000320193", "instrument_id": "instrument:1", "event_id": "event:sec:0001",
        "term": {"name": "exercise_price", "term_type": "price"},
        "reported": {"raw_text": "$5.00 per share", "value": 5.0, "unit": "USD/share", "currency": "USD", "scale": 1},
        "normalized": {"value": None, "unit": "USD/share", "currency": "USD", "scale": 1, "state": "unknown"},
        "effective_from": None, "observed_at": "2026-08-01T11:01:00Z",
        "evidence": {
            "manifest_id": "manifest:sec:0001", "span_id": "span:cover", "text_sha256": HASH,
            "rights_class": "public_source_link", "privacy_classification": "public",
            "contains_personal_data": False,
            "publication": {
                "disposition": "internal_evidence_only", "excerpt_char_count": 0,
                "personal_data_redacted": False,
            },
        },
        "extraction": {"method": "deterministic", "parser_version": "1.0", "confidence": 0.9, "review_status": "unreviewed"},
        "relationships": {"amends": [], "supersedes": [], "contradiction_ids": []},
        "version": {"immutable_record": True, "correction_version": 1, "correction_of": None},
        "point_in_time": {"available_at": "2026-08-01T11:01:00Z"}
    }


def _document_term() -> dict:
    return {
        "schema": "capital_structure.document_term_observation.v1",
        "observation_id": "document-term:cs:" + ("d" * 24),
        "logical_observation_id": "document-term-slot:cs:" + ("e" * 24),
        "issuer_id": "sec:cik:0000320193",
        "filing": {
            "accession": "0000320193-26-000001", "form": "S-3",
            "filing_date": "2026-08-01", "accepted_at": "2026-08-01T11:00:00Z",
        },
        "document": {
            "source_manifest_id": "manifest:cs:" + HASH,
            "source_id": "0000320193-26-000001:0:complete-submission.txt",
            "document_role": "complete_submission",
            "canonical_url": "https://www.sec.gov/Archives/example.txt",
            "content_sha256": HASH,
            "child_document_type": "EX-FILING FEES", "child_sequence": "2",
            "child_filename": "filing-fees.htm", "child_text_start": 10,
            "child_text_end": 200,
        },
        "security": {
            "row_id": "fee-row:cs:" + ("c" * 24), "table_index": 0,
            "row_index": 1, "title_raw": "Common stock",
            "title_normalized": "common stock", "classification": "common_stock",
        },
        "term": {
            "name": "registration_fee", "term_type": "amount",
            "scope": "registration_fee_table_row",
        },
        "state": {"disposition": "observed", "reason": "direct_table_value"},
        "reported": {"raw_text": "$1,234.50", "value": "1234.5", "unit": "USD", "currency": "USD", "scale": "1"},
        "normalized": {"raw_text": "$1,234.50", "value": "1234.5", "unit": "USD", "currency": "USD", "scale": "1"},
        "evidence": {
            "source_manifest_id": "manifest:cs:" + HASH,
            "source_document_sha256": HASH,
            "rights_class": "public_source_link", "privacy_classification": "public",
            "contains_personal_data": True,
            "publication": {"disposition": "public_fact_only", "excerpt_char_count": 0, "personal_data_redacted": False},
            "spans": [{
                "manifest_id": "manifest:cs:" + HASH,
                "span_id": "span:cs:" + ("f" * 24), "locator_type": "text_range",
                "locator": "complete_submission:type=EX-FILING FEES:sequence=2:table=0:row=1:cell=4:role=registration_fee:bytes:10-200", "text_sha256": HASH,
            }],
        },
        "extraction": {"method": "deterministic", "parser_version": "capital-structure-document-terms/1.1.0", "review_status": "unreviewed"},
        "relationships": {"amends": [], "supersedes": [], "contradiction_ids": []},
        "version": {"immutable_record": True, "correction_version": 1, "correction_of": None},
        "point_in_time": {"source_available_at": "2026-08-01T12:00:00Z", "available_at": "2026-08-02T12:00:00Z"},
    }


def _metric() -> dict:
    return {"value": None, "unit": "shares", "state": "unknown", "evidence_ids": []}


def _record_list() -> dict:
    return {"state": "unknown", "records": [], "evidence_ids": []}


def _context() -> dict:
    metric_keys = ["reported_shares", "estimated_float", "authorized_headroom", "registered_resale_supply", "incentive_equity_supply", "active_primary_financing_capacity", "active_instrument_overhang", "near_price_overhang", "cash_resources", "normalized_cash_use", "runway"]
    record_keys = ["debt_and_convertible_maturities", "shelf_state", "pending_and_live_offerings", "historical_offering_behavior", "counterparty_history", "corporate_action_state"]
    observations = {key: _metric() for key in metric_keys}
    observations.update({key: _record_list() for key in record_keys})
    return {
        "schema": "capital_structure.context.v1", "issuer_id": "issuer:0000320193", "as_of": "2026-08-01T12:00:00Z", "calculation_version": "1.0", "observations": observations,
        "lineage": {"event_ids": ["event:sec:0001"], "term_observation_ids": ["term:1"], "calculation_receipt_ids": ["receipt:1"]},
        "coverage": {"state": "partial", "freshness": "fresh", "contradiction_ids": []},
        "risk_claims": {"authority": "context_only", "claims": []},
        "authority": {"is_context_only": True, "rank_authority": False, "sizing_authority": False, "entry_authority": False, "prophet_authority": False}
    }


def _edge() -> dict:
    return {
        "schema": "capital_structure.event_edge.v1",
        "edge_id": "edge:cs:" + ("a" * 24),
        "from_event_id": "event:cs:child",
        "to_event_id": "event:cs:parent",
        "relationship": "amendment_of",
        "link_method": "exact_cik_file_number_family_chronology",
        "observed_at": "2026-08-01T12:00:00Z",
        "immutable_record": True,
    }


def _review_item() -> dict:
    return {
        "schema": "capital_structure.review_item.v1",
        "queue_id": "review:cs:" + ("b" * 24),
        "event_id": "event:cs:child",
        "accession": "0000320193-26-000001",
        "issuer_id": "issuer:0000320193",
        "form": "S-3/A",
        "classification_state": "deferred_linkage",
        "defer_reason": "no_unique_link_target",
        "candidate_event_ids": [],
        "source_manifest_ids": ["manifest:sec:0001"],
        "first_queued_at": "2026-08-01T12:00:00Z",
        "review_state": "pending",
        "immutable_source": True,
    }


def _telemetry() -> dict:
    return {
        "schema": "capital_structure.telemetry.v1",
        "status": "ok",
        "as_of": "2026-08-01T12:00:00Z",
        "generation_id": "generation:cs:" + ("c" * 24),
        "authority": {
            "is_context_only": True, "rank_authority": False,
            "sizing_authority": False, "entry_authority": False,
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
            "source_manifests": 1, "accessions_grouped": 1,
            "event_versions": 1, "new_event_versions": 1,
            "event_edges": 0, "review_queue": 0, "compile_failures": 0,
        },
        "compile_failures": [],
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
            "pit_preservation_state": "not_yet_tested",
            "legacy_writer": "collectors/edgar_dilution.py",
            "legacy_projection_state": "shadow_only_no_cutover",
            "immutable_record": True,
        },
        "source_ledger_receipt": {
            "schema": "capital_structure.source_ledger_receipt.v1",
            "record_count": 1,
            "prefix_sha256": "d" * 64,
            "form_policy_version": "capital-structure-sec-form-policy/1.0.0",
            "immutable_prefix": True,
        },
        "artifact_hashes": {
            "event_versions": HASH, "event_edges": HASH, "review_queue": HASH,
        },
    }


def _retrieval_queue_receipt() -> dict:
    lanes = [
        "registration", "state", "prospectus", "reg_a", "issuer_current_report",
        "issuer_periodic", "issuer_proxy",
    ]
    return {
        "schema": "capital_structure.retrieval_queue_receipt.v1",
        "as_of": "2026-08-01T12:00:00Z",
        "policy_version": "capital-structure-sec-form-policy/1.2.0",
        "max_filings": 14,
        "selected_count": 0,
        "deferred_count": 0,
        "lane_quota_slots": {
            "registration": 4, "state": 2, "prospectus": 2, "reg_a": 1,
            "issuer_current_report": 2, "issuer_periodic": 2, "issuer_proxy": 1,
        },
        "lanes": [{
            "lane": lane, "pending_count": 0, "selected_count": 0,
            "deferred_count": 0, "oldest_pending_first_seen": None,
            "oldest_pending_age_days": None, "unknown_first_seen_count": 0,
        } for lane in lanes],
        "authority": {
            "is_context_only": True, "rank_authority": False,
            "sizing_authority": False, "entry_authority": False,
            "prophet_authority": False,
        },
    }


@pytest.mark.parametrize(("name", "factory"), [
    ("capital_structure_source_manifest.schema.json", _source_manifest),
    ("capital_structure_event.schema.json", _event),
    ("capital_structure_instrument_term_observation.schema.json", _term),
    ("capital_structure_document_term_observation.schema.json", _document_term),
    ("capital_structure_context.schema.json", _context),
    ("capital_structure_event_edge.schema.json", _edge),
    ("capital_structure_review_item.schema.json", _review_item),
    ("capital_structure_telemetry.schema.json", _telemetry),
    ("capital_structure_retrieval_queue_receipt.schema.json", _retrieval_queue_receipt),
])
def test_contracts_are_strict_draft_2020_12(name, factory):
    schema = _schema(name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    Draft202012Validator.check_schema(schema)
    _validate(name, factory())


def test_source_manifest_requires_explicit_rights_storage_parser_and_corruption_state():
    record = _source_manifest()
    del record["rights"]
    _invalid("capital_structure_source_manifest.schema.json", record, "required property")

    record = _source_manifest()
    record["parser"]["corruption_state"] = "maybe"
    _invalid("capital_structure_source_manifest.schema.json", record, "is not one of")

    record = _source_manifest()
    record["retrieval"]["transport_status"] = "failed"
    _invalid("capital_structure_source_manifest.schema.json", record, "'retrieved' was expected")

    record = _source_manifest()
    del record["storage"]["store_id"]
    _invalid("capital_structure_source_manifest.schema.json", record, "required property")

    record = _source_manifest()
    record["storage"]["store_id"] = "customer-secret-bucket-name"
    _invalid("capital_structure_source_manifest.schema.json", record, "is not one of")

    record = _source_manifest()
    record["storage"]["backend"] = "local"
    _invalid("capital_structure_source_manifest.schema.json", record, "was expected")


def test_event_is_immutable_context_only_and_has_classification_and_pit_dual_clocks():
    record = _event()
    record["version"]["immutable_record"] = False
    _invalid("capital_structure_event.schema.json", record, "True was expected")

    record = _event()
    del record["point_in_time"]["first_seen_at"]
    _invalid("capital_structure_event.schema.json", record, "required property")

    record = _event()
    del record["point_in_time"]["public_available_at"]
    _invalid("capital_structure_event.schema.json", record, "required property")

    record = _event()
    assert record["point_in_time"]["available_at"] == record["point_in_time"]["system_available_at"]
    assert "Canonical system availability" in _schema("capital_structure_event.schema.json")["properties"]["point_in_time"]["properties"]["available_at"]["description"]

    record = _event()
    record["classification"] = {"state": "deferred_missing_document", "defer_reason": None}
    _invalid("capital_structure_event.schema.json", record, "is not of type 'string'")

    record = _event()
    record["classification"] = {"state": "deferred_missing_document", "defer_reason": "Primary document unavailable"}
    _validate("capital_structure_event.schema.json", record)

    record = _event()
    record["normalized_terms"] = []
    _invalid("capital_structure_event.schema.json", record, "Additional properties")

    record = _event()
    record["relationships"]["superseded_by"] = ["event:later"]
    _invalid("capital_structure_event.schema.json", record, "Additional properties")

    record = _event()
    record["authority"]["prophet_authority"] = True
    _invalid("capital_structure_event.schema.json", record, "False was expected")


def test_event_file_number_provenance_is_optional_for_legacy_but_closed_when_present():
    legacy = _event()
    _validate("capital_structure_event.schema.json", legacy)

    hardened = _event()
    hardened["filing"]["file_number_provenance"] = {
        "state": "observed", "value": "333-123456",
        "candidate_values": ["333-123456"],
        "sources": ["legacy_sgml_file_number", "sec_header_file_number"],
    }
    _validate("capital_structure_event.schema.json", hardened)

    hardened["filing"]["file_number_provenance"]["inferred"] = True
    _invalid(
        "capital_structure_event.schema.json", hardened, "Additional properties"
    )


def test_term_observation_preserves_reported_value_and_allows_unknown_as_null_not_zero():
    _validate("capital_structure_instrument_term_observation.schema.json", _term())

    record = _term()
    del record["reported"]
    _invalid("capital_structure_instrument_term_observation.schema.json", record, "required property")

    record = _term()
    record["normalized"]["value"] = None
    record["normalized"]["state"] = "unknown"
    _validate("capital_structure_instrument_term_observation.schema.json", record)


def test_document_term_requires_decimal_strings_and_cannot_tunnel_an_issuer_state_claim():
    name = "capital_structure_document_term_observation.schema.json"
    _validate(name, _document_term())

    record = _document_term()
    record["reported"]["value"] = 1234.5
    _invalid(name, record, "is not valid under any of the given schemas")

    record = _document_term()
    record["state"] = {"disposition": "observed", "reason": "fee_table_not_detected"}
    _invalid(name, record, "'direct_table_value' was expected")

    record = _document_term()
    record["remaining_capacity"] = "1234.5"
    _invalid(name, record, "Additional properties")

    record = _document_term()
    record["state"] = {"disposition": "ambiguous", "reason": "multiple_fee_tables_detected"}
    _invalid(name, record, "is not of type 'null'")

    record = _document_term()
    record["reported"] = {"raw_text": None, "value": None, "unit": None, "currency": None, "scale": None}
    record["normalized"] = dict(record["reported"])
    _invalid(name, record, "is not of type 'string'")

    record = _document_term()
    record["reported"]["unit"] = "shares"
    record["reported"]["currency"] = None
    record["normalized"] = dict(record["reported"])
    _invalid(name, record, "'USD' was expected")

    record = _document_term()
    record["term"]["term_type"] = "share_count"
    _invalid(name, record, "'amount' was expected")


def test_document_term_schema_binds_security_class_to_amount_and_price_dimensions():
    name = "capital_structure_document_term_observation.schema.json"

    debt_as_shares = _document_term()
    debt_as_shares["security"]["classification"] = "debt"
    debt_as_shares["security"]["title_raw"] = "Senior notes"
    debt_as_shares["security"]["title_normalized"] = "senior notes"
    debt_as_shares["term"] = {
        "name": "amount_to_be_registered", "term_type": "share_count",
        "scope": "registration_fee_table_row",
    }
    debt_as_shares["reported"] = {
        "raw_text": "50,000,000", "value": "50000000", "unit": "shares",
        "currency": None, "scale": "1",
    }
    debt_as_shares["normalized"] = dict(debt_as_shares["reported"])
    _invalid(name, debt_as_shares, "is not valid under any of the given schemas")

    unknown_amount = _document_term()
    unknown_amount["security"]["classification"] = "unknown"
    unknown_amount["term"] = {
        "name": "amount_to_be_registered", "term_type": "quantity",
        "scope": "registration_fee_table_row",
    }
    unknown_amount["reported"] = {
        "raw_text": "1,000", "value": "1000", "unit": "securities",
        "currency": None, "scale": "1",
    }
    unknown_amount["normalized"] = dict(unknown_amount["reported"])
    _invalid(name, unknown_amount, "is not valid under any of the given schemas")

    debt_price = _document_term()
    debt_price["security"]["classification"] = "debt"
    debt_price["term"] = {
        "name": "proposed_maximum_offering_price_per_unit", "term_type": "price",
        "scope": "registration_fee_table_row",
    }
    debt_price["reported"] = {
        "raw_text": "$100", "value": "100", "unit": "USD/security",
        "currency": "USD", "scale": "1",
    }
    debt_price["normalized"] = dict(debt_price["reported"])
    _invalid(name, debt_price, "is not valid under any of the given schemas")


def test_document_term_schema_binds_correction_version_to_lineage_presence():
    name = "capital_structure_document_term_observation.schema.json"
    version_one_with_parent = _document_term()
    version_one_with_parent["version"]["correction_of"] = "document-term:cs:" + ("b" * 24)
    version_one_with_parent["relationships"]["supersedes"] = ["document-term:cs:" + ("b" * 24)]
    _invalid(name, version_one_with_parent, "is not of type 'null'")

    version_two_without_parent = _document_term()
    version_two_without_parent["version"]["correction_version"] = 2
    _invalid(name, version_two_without_parent, "is not of type 'string'")


@pytest.mark.parametrize("factory", [_event, _term])
def test_canonical_observations_reject_llm_originated_truth(factory):
    record = factory()
    record["extraction"]["method"] = "llm_assisted"
    name = (
        "capital_structure_event.schema.json"
        if record["schema"] == "capital_structure.event.v1"
        else "capital_structure_instrument_term_observation.schema.json"
    )
    _invalid(name, record, "is not one of")


def test_term_raw_excerpt_and_publication_disposition_are_bounded():
    name = "capital_structure_instrument_term_observation.schema.json"

    record = _term()
    record["reported"]["raw_text"] = "x" * 500
    _validate(name, record)

    record["reported"]["raw_text"] = "x" * 501
    _invalid(name, record, "is too long")

    record = _term()
    record["evidence"]["publication"] = {
        "disposition": "bounded_public_excerpt", "excerpt_char_count": 15,
        "personal_data_redacted": False,
    }
    _invalid(name, record, "'excerpt_permitted' was expected")

    record["evidence"]["rights_class"] = "excerpt_permitted"
    _validate(name, record)

    record["evidence"]["contains_personal_data"] = True
    _invalid(name, record, "True was expected")

    record["evidence"]["publication"]["personal_data_redacted"] = True
    _validate(name, record)

    record = _term()
    record["evidence"]["publication"] = {
        "disposition": "public_fact_only", "excerpt_char_count": 1,
        "personal_data_redacted": False,
    }
    _invalid(name, record, "0 was expected")


def test_edge_review_and_telemetry_contracts_are_strict_receipts():
    edge = _edge()
    edge["immutable_record"] = False
    _invalid("capital_structure_event_edge.schema.json", edge, "True was expected")

    review = _review_item()
    review["classification_state"] = "classified"
    _invalid("capital_structure_review_item.schema.json", review, "is not one of")

    telemetry = _telemetry()
    telemetry["authority"]["prophet_authority"] = True
    _invalid("capital_structure_telemetry.schema.json", telemetry, "False was expected")

    telemetry = _telemetry()
    telemetry["migration_receipt"]["immutable_record"] = False
    _invalid("capital_structure_telemetry.schema.json", telemetry, "True was expected")

    telemetry = _telemetry()
    telemetry["source_ledger_receipt"]["immutable_prefix"] = False
    _invalid("capital_structure_telemetry.schema.json", telemetry, "True was expected")

    telemetry = _telemetry()
    telemetry["source_ledger_receipt"]["record_count"] = 0
    _invalid("capital_structure_telemetry.schema.json", telemetry, "less than the minimum of 1")


def test_no_source_telemetry_is_an_explicit_zero_generation_receipt():
    record = _telemetry()
    record["status"] = "no_source_manifest"
    record["generation_id"] = None
    record["counts"] = {key: 0 for key in record["counts"]}
    record["source_ledger_receipt"]["record_count"] = 0
    record["artifact_hashes"] = {
        "event_versions": None, "event_edges": None, "review_queue": None,
    }
    _validate("capital_structure_telemetry.schema.json", record)

    record["counts"]["source_manifests"] = 1
    _invalid("capital_structure_telemetry.schema.json", record, "0 was expected")

    record = _telemetry()
    record["status"] = "no_source_manifest"
    record["generation_id"] = None
    record["counts"] = {key: 0 for key in record["counts"]}
    record["artifact_hashes"] = {
        "event_versions": None, "event_edges": None, "review_queue": None,
    }
    _invalid("capital_structure_telemetry.schema.json", record, "0 was expected")


def test_degraded_telemetry_cannot_masquerade_as_a_committed_generation():
    record = _telemetry()
    record["status"] = "degraded"
    record["generation_id"] = None
    record["counts"]["compile_failures"] = 1
    record["compile_failures"] = [{
        "accession": "0000000001-26-000001",
        "state": "invalid_source_manifest_bundle",
        "errors": ["digest mismatch"],
    }]
    record["artifact_hashes"] = {
        "event_versions": None, "event_edges": None, "review_queue": None,
    }
    _validate("capital_structure_telemetry.schema.json", record)

    record["artifact_hashes"]["event_versions"] = HASH
    _invalid("capital_structure_telemetry.schema.json", record, "is not of type 'null'")

    ok = _telemetry()
    ok["counts"]["compile_failures"] = 1
    ok["compile_failures"] = record["compile_failures"]
    _invalid("capital_structure_telemetry.schema.json", ok, "0 was expected")


def test_context_separates_observations_from_non_authoritative_claims_and_rejects_prophet():
    record = _context()
    record["authority"]["prophet_authority"] = True
    _invalid("capital_structure_context.schema.json", record, "False was expected")

    record = _context()
    record["prophet"] = {"score": 1}
    _invalid("capital_structure_context.schema.json", record, "Additional properties")

    record = _context()
    record["risk_claims"]["authority"] = "ranked"
    _invalid("capital_structure_context.schema.json", record, "'context_only' was expected")


def test_context_record_lists_are_strict_evidence_facts_not_authority_tunnels():
    record = _context()
    fact = {
        "record_id": "registration:1", "record_type": "registration",
        "label": "S-3 shelf", "state": "observed", "value": "active",
        "unit": None, "effective_at": "2026-08-01T11:00:00Z",
        "evidence_ids": ["manifest:sec:0001"],
    }
    record["observations"]["shelf_state"] = {
        "state": "observed", "records": [fact],
        "evidence_ids": ["manifest:sec:0001"],
    }
    _validate("capital_structure_context.schema.json", record)

    record["observations"]["shelf_state"]["records"][0]["prophet_authority"] = True
    _invalid("capital_structure_context.schema.json", record, "Additional properties")
