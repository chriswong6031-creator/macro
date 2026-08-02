"""Adversarial tests for the deliberately pre-instrument candidate-term kernel."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.document_terms import (
    compile_document_term_records,
    observation_id_for,
)
from engine.capital_structure.instrument_candidates import (
    candidate_term_id_for,
    candidate_mapping_for_document_term,
    compile_candidate_term_records,
    current_candidate_terms_as_of,
    validate_candidate_term_history,
)
from engine.capital_structure.source_identity import manifest_id_for
from scripts.compile_capital_structure_instrument_candidate_terms import (
    CANDIDATE_TERM_COLUMNS,
    DOCUMENT_TERM_COLUMNS,
    compile_from_disk,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/capital_structure/document_terms/registration_fee_table_submission.txt"


def _manifest(raw: bytes) -> dict:
    digest = sha256(raw).hexdigest()
    record = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": "0000000001-26-000001:0:complete-submission.txt",
        "issuer": {"issuer_id": "sec:cik:0000000001", "cik": "1", "ticker": "ABC", "aliases": ["ABC Corp"]},
        "filing": {"accession": "0000000001-26-000001", "form": "S-3", "filing_date": "2026-08-01", "accepted_at": "2026-08-01T11:00:00Z", "file_number": "333-123456"},
        "document": {
            "canonical_url": "https://www.sec.gov/Archives/edgar/data/1/example.txt",
            "document_name": "complete-submission.txt", "document_type": "S-3", "document_role": "complete_submission", "sequence": "0", "media_type": "text/plain",
            "byte_length": len(raw), "document_version": 1, "content_sha256": digest, "parent_manifest_id": None, "root_locator": f"sha256:{digest}",
        },
        "retrieval": {"retrieved_at": "2026-08-02T12:00:00Z", "first_seen_at": "2026-08-02T12:00:00Z", "transport_status": "retrieved"},
        "storage": {"backend": "r2", "store_id": "r2_shared", "object_key": f"capital_structure/sec/sha256/{digest[:2]}/{digest}", "content_addressed": True, "retention_state": "retained"},
        "rights": {"redistribution_class": "public_source_link", "attribution_required": True, "license_note": "United States SEC EDGAR public filing"},
        "privacy": {"classification": "public", "contains_personal_data": True},
        "parser": {"eligibility": "eligible", "corruption_state": "clean", "parser_version": "sec-source-inspector/1.0.0"},
        "spans": [{"span_id": f"root:{digest}", "locator_type": "document", "locator": f"bytes:0-{len(raw)}", "text_sha256": digest}],
    }
    record["manifest_id"] = manifest_id_for(record)
    return record


def _direct_rows() -> list[dict]:
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    return compile_document_term_records(
        [manifest], source_reader=lambda _: raw, generated_at="2026-08-03T00:00:00Z",
    )["observations"]


def _candidate_contract() -> dict:
    return json.loads((ROOT / "contracts/capital_structure_instrument_candidate_term.schema.json").read_text())


def _schema_validate(rows: list[dict]) -> None:
    validator = Draft202012Validator(_candidate_contract(), format_checker=FormatChecker())
    for row in rows:
        errors = list(validator.iter_errors(row))
        assert not errors, errors[0].message


def _direct_frame(rows: list[dict]) -> pd.DataFrame:
    materialized = []
    for row in rows:
        materialized.append({
            "observation_id": row["observation_id"], "logical_observation_id": row["logical_observation_id"], "issuer_id": row["issuer_id"],
            "accession": row["filing"]["accession"], "form": row["filing"]["form"], "source_manifest_id": row["document"]["source_manifest_id"],
            "term_name": row["term"]["name"], "state": row["state"]["disposition"], "available_at": row["point_in_time"]["available_at"],
            "correction_version": row["version"]["correction_version"],
            "observation_json": json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        })
    return pd.DataFrame(materialized, columns=DOCUMENT_TERM_COLUMNS)


def test_candidate_projection_is_one_to_one_and_preserves_direct_evidence_without_creating_an_instrument():
    source = _direct_rows()
    result = compile_candidate_term_records(source, generated_at="2026-08-04T00:00:00Z")
    rows = result["observations"]
    _schema_validate(rows)
    assert result["counts"] == {
        "input_document_terms": 5, "input_current_document_terms": 5,
        "created": 5, "unchanged": 0, "total": 5,
    }
    by_source = {row["source_term"]["observation_id"]: row for row in rows}
    direct_amount = next(row for row in source if row["term"]["name"] == "amount_to_be_registered")
    candidate = by_source[direct_amount["observation_id"]]
    assert candidate["candidate"] == {
        "mapping_version": "capital-structure-instrument-candidate-terms/1.0.0",
        "family": "common_stock", "supply_role": "registration_security_candidate",
        "state": {"disposition": "observed", "reason": "direct_security_class_mapping"},
    }
    assert candidate["evidence"] == direct_amount["evidence"]
    assert candidate["security"] == direct_amount["security"]
    assert candidate["source_term"]["observation_id"] == direct_amount["observation_id"]
    assert candidate["point_in_time"] == {
        "source_available_at": "2026-08-02T12:00:00Z",
        "source_term_available_at": "2026-08-03T00:00:00Z",
        "available_at": "2026-08-04T00:00:00Z",
    }
    assert all("instrument_id" not in row and "instrument_candidate_id" not in row for row in rows)
    assert all(row["authority"] == {
        "context_only": True, "may_calculate_capacity": False, "may_emit_risk": False,
        "may_emit_probability": False, "may_gate_prophet": False,
    } for row in rows)


def test_rate_and_fee_rows_remain_evidence_only_not_an_implied_supply_or_capacity():
    rows = compile_candidate_term_records(_direct_rows(), generated_at="2026-08-04T00:00:00Z")["observations"]
    rate = next(row for row in rows if row["term"]["name"] == "filing_fee_rate")
    assert rate["candidate"]["family"] == "common_stock"
    assert rate["candidate"]["supply_role"] == "not_applicable"
    assert rate["candidate"]["state"]["reason"] == "direct_security_class_mapping_supply_not_applicable"
    assert "capacity" not in rate
    assert rate["authority"]["may_calculate_capacity"] is False


def test_unknown_direct_security_and_unsupported_term_type_stay_explicitly_deferred():
    source = deepcopy(next(row for row in _direct_rows() if row["term"]["name"] == "registration_fee"))
    source["security"]["classification"] = "unknown"
    source["observation_id"] = observation_id_for(source)
    projected = compile_candidate_term_records([source], generated_at="2026-08-04T00:00:00Z")["observations"][0]
    assert projected["candidate"]["state"] == {"disposition": "deferred", "reason": "security_classification_unknown"}
    unsupported = deepcopy(source)
    unsupported["term"]["term_type"] = "banana"
    assert candidate_mapping_for_document_term(unsupported)["state"] == {
        "disposition": "deferred", "reason": "unsupported_source_term_type",
    }


def test_ambiguous_upstream_direct_term_cannot_be_promoted_to_a_candidate_family():
    source = deepcopy(next(row for row in _direct_rows() if row["term"]["name"] == "registration_fee"))
    source["state"] = {"disposition": "ambiguous", "reason": "multiple_numeric_tokens"}
    source["reported"] = {"raw_text": None, "value": None, "unit": None, "currency": None, "scale": None}
    source["normalized"] = deepcopy(source["reported"])
    source["observation_id"] = observation_id_for(source)
    projected = compile_candidate_term_records([source], generated_at="2026-08-04T00:00:00Z")["observations"][0]
    assert projected["candidate"]["state"] == {"disposition": "ambiguous", "reason": "upstream_document_term_ambiguous"}
    assert projected["candidate"]["family"] == "unknown"
    assert projected["candidate"]["supply_role"] == "unknown"


def test_candidate_correction_is_not_visible_until_this_projection_compiles():
    direct_v1 = _direct_rows()
    baseline = compile_candidate_term_records(direct_v1, generated_at="2026-08-04T00:00:00Z")["observations"]
    # Simulate an append-only upstream parser correction after W3A already
    # established a baseline. Both source versions remain in the direct ledger.
    original = next(row for row in direct_v1 if row["term"]["name"] == "registration_fee")
    corrected_source = deepcopy(original)
    corrected_source["state"] = {"disposition": "unavailable", "reason": "header_without_direct_value"}
    corrected_source["reported"] = {"raw_text": None, "value": None, "unit": None, "currency": None, "scale": None}
    corrected_source["normalized"] = deepcopy(corrected_source["reported"])
    corrected_source["relationships"] = {"amends": [], "supersedes": [original["observation_id"]], "contradiction_ids": []}
    corrected_source["version"] = {"immutable_record": True, "correction_version": 2, "correction_of": original["observation_id"]}
    corrected_source["point_in_time"]["available_at"] = "2026-08-05T00:00:00Z"
    corrected_source["observation_id"] = observation_id_for(corrected_source)
    upstream_corrected = direct_v1 + [corrected_source]
    result = compile_candidate_term_records(
        upstream_corrected, existing_candidate_terms=baseline, generated_at="2026-08-06T00:00:00Z",
    )
    corrected = [row for row in result["observations"] if row["term"]["name"] == "registration_fee"]
    assert len(corrected) == 2
    prior, later = sorted(corrected, key=lambda row: row["version"]["correction_version"])
    assert later["version"] == {"immutable_record": True, "correction_version": 2, "correction_of": prior["candidate_term_id"]}
    assert later["point_in_time"]["available_at"] == "2026-08-06T00:00:00Z"
    before = current_candidate_terms_as_of(result["observations"], "2026-08-05T23:59:59Z")
    after = current_candidate_terms_as_of(result["observations"], "2026-08-06T00:00:00Z")
    assert next(row for row in before if row["term"]["name"] == "registration_fee")["source_term"]["observation_id"] == prior["source_term"]["observation_id"]
    assert next(row for row in after if row["term"]["name"] == "registration_fee")["source_term"]["observation_id"] == later["source_term"]["observation_id"]


def test_candidate_history_rejects_id_body_mutation_duplicate_ids_and_missing_evidence():
    source = _direct_rows()
    rows = compile_candidate_term_records(source, generated_at="2026-08-04T00:00:00Z")["observations"]
    mutated = deepcopy(rows)
    mutated[0]["candidate"]["family"] = "other"
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_candidate_term_history(mutated)
    recomputed = deepcopy(mutated)
    recomputed[0]["candidate_term_id"] = candidate_term_id_for(recomputed[0])
    with pytest.raises(ValueError, match="candidate mapping is detached from embedded source fields"):
        validate_candidate_term_history(recomputed)
    rebound_evidence = deepcopy(rows)
    rebound_evidence[0]["evidence"]["spans"][0]["locator"] = "tampered:locator"
    rebound_evidence[0]["candidate_term_id"] = candidate_term_id_for(rebound_evidence[0])
    with pytest.raises(ValueError, match="evidence is detached from its direct observation"):
        compile_candidate_term_records(
            source, existing_candidate_terms=rebound_evidence, generated_at="2026-08-05T00:00:00Z",
        )
    with pytest.raises(ValueError, match="duplicate"):
        validate_candidate_term_history(rows + [deepcopy(rows[0])])
    no_evidence = deepcopy(source[0])
    no_evidence["evidence"]["spans"] = []
    no_evidence["observation_id"] = observation_id_for(no_evidence)
    with pytest.raises(ValueError, match="contract violation"):
        compile_candidate_term_records([no_evidence], generated_at="2026-08-04T00:00:00Z")


def test_no_fuzzy_join_exists_when_two_identical_family_rows_share_an_issuer():
    raw = FIXTURE.read_bytes().replace(
        b"</table>",
        b"<tr><td>Common stock</td><td>500,000</td><td>$4.00</td><td>$2,000,000</td><td>$232.80</td><td>0.0001164</td></tr></table>",
    )
    manifest = _manifest(raw)
    source = compile_document_term_records([manifest], source_reader=lambda _: raw, generated_at="2026-08-03T00:00:00Z")["observations"]
    rows = compile_candidate_term_records(source, generated_at="2026-08-04T00:00:00Z")["observations"]
    amounts = [row for row in rows if row["term"]["name"] == "amount_to_be_registered"]
    assert len(amounts) == 2
    assert len({row["logical_candidate_term_id"] for row in amounts}) == 2
    assert len({row["source_term"]["observation_id"] for row in amounts}) == 2
    assert all("match" not in row and "instrument_id" not in row for row in amounts)


def test_offline_compiler_requires_the_exact_direct_ledger_and_writes_canonical_candidate_ledger(tmp_path):
    direct = _direct_rows()
    _direct_frame(direct).to_parquet(tmp_path / "document_term_observations.parquet", index=False)
    result = compile_from_disk(root=tmp_path, generated_at="2026-08-04T00:00:00Z")
    assert result["status"] == "ok"
    assert result["created"] == 5
    ledger = pd.read_parquet(tmp_path / "instrument_candidate_terms.parquet")
    assert ledger.columns.tolist() == CANDIDATE_TERM_COLUMNS
    assert all(value == json.dumps(json.loads(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False) for value in ledger["candidate_term_json"])
    absent = compile_from_disk(root=tmp_path / "missing", generated_at="2026-08-04T00:00:00Z")
    assert absent["status"] == "unavailable"
    assert absent["reason"] == "document_term_ledger_absent"
