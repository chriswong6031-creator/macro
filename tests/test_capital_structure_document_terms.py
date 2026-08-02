"""Fixture-pinned precision tests for document-row fee-table transcription."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.document_terms import (
    DocumentTermCompileDegraded,
    compile_document_term_records,
    current_document_terms_as_of,
    observation_id_for,
    validate_document_term_history,
    validate_observation_source_binding,
)
from engine.capital_structure.source_identity import manifest_id_for
from scripts.compile_capital_structure_document_terms import (
    DOCUMENT_TERM_COLUMNS,
    compile_from_disk,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/capital_structure/document_terms/registration_fee_table_submission.txt"


def _manifest(raw: bytes, *, form: str = "S-3", parser_eligibility: str = "eligible") -> dict:
    digest = sha256(raw).hexdigest()
    record = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": "0000000001-26-000001:0:complete-submission.txt",
        "issuer": {
            "issuer_id": "sec:cik:0000000001", "cik": "1", "ticker": "ABC",
            "aliases": ["ABC Corp"],
        },
        "filing": {
            "accession": "0000000001-26-000001", "form": form,
            "filing_date": "2026-08-01", "accepted_at": "2026-08-01T11:00:00Z",
            "file_number": "333-123456",
        },
        "document": {
            "canonical_url": "https://www.sec.gov/Archives/edgar/data/1/example.txt",
            "document_name": "complete-submission.txt", "document_type": form,
            "document_role": "complete_submission", "sequence": "0", "media_type": "text/plain",
            "byte_length": len(raw), "document_version": 1, "content_sha256": digest,
            "parent_manifest_id": None, "root_locator": f"sha256:{digest}",
        },
        "retrieval": {
            "retrieved_at": "2026-08-02T12:00:00Z", "first_seen_at": "2026-08-02T12:00:00Z",
            "transport_status": "retrieved",
        },
        "storage": {
            "backend": "r2", "store_id": "r2_shared",
            "object_key": f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
            "content_addressed": True, "retention_state": "retained",
        },
        "rights": {
            "redistribution_class": "public_source_link", "attribution_required": True,
            "license_note": "United States SEC EDGAR public filing",
        },
        "privacy": {"classification": "public", "contains_personal_data": True},
        "parser": {
            "eligibility": parser_eligibility, "corruption_state": "clean",
            "parser_version": "sec-source-inspector/1.0.0",
        },
        "spans": [{
            "span_id": f"root:{digest}", "locator_type": "document",
            "locator": f"bytes:0-{len(raw)}", "text_sha256": digest,
        }],
    }
    record["manifest_id"] = manifest_id_for(record)
    return record


def _reader(raw: bytes):
    return lambda manifest: raw


def _contract() -> dict:
    return json.loads((ROOT / "contracts/capital_structure_document_term_observation.schema.json").read_text())


def _schema_validate(rows: list[dict]) -> None:
    validator = Draft202012Validator(_contract(), format_checker=FormatChecker())
    for row in rows:
        errors = list(validator.iter_errors(row))
        assert not errors, errors[0].message


def test_complete_submission_is_the_fee_table_parser_path_and_preserves_decimal_strings():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    result = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z"
    )
    rows = result["observations"]
    _schema_validate(rows)
    assert len(rows) == 5
    by_term = {row["term"]["name"]: row for row in rows}
    assert by_term["amount_to_be_registered"]["reported"]["value"] == "1250000"
    assert by_term["proposed_maximum_offering_price_per_unit"]["reported"]["value"] == "8.5"
    assert by_term["proposed_maximum_aggregate_offering_price"]["reported"]["value"] == "10625000"
    assert by_term["registration_fee"]["reported"]["value"] == "1237.1"
    assert by_term["filing_fee_rate"]["reported"]["value"] == "0.0001164"
    assert all(row["state"] == {"disposition": "observed", "reason": "direct_table_value"} for row in rows)
    assert all(row["normalized"] == row["reported"] for row in rows)
    for row in rows:
        assert row["document"]["document_role"] == "complete_submission"
        assert row["document"]["source_manifest_id"] == manifest["manifest_id"]
        span = row["evidence"]["spans"][0]
        assert span["manifest_id"] == manifest["manifest_id"]
        assert span["locator_type"] == "table"
        assert span["text_sha256"] != manifest["document"]["content_sha256"]
        assert row["point_in_time"]["source_available_at"] == "2026-08-02T12:00:00Z"
        # A source first seen in August cannot appear in an earlier canonical replay.
        assert row["point_in_time"]["available_at"] == "2026-08-03T00:00:00Z"
        assert "instrument_id" not in row and "authority" not in row


def test_no_fee_table_is_explicitly_unavailable_not_a_zero_or_capacity_claim():
    raw = FIXTURE.read_bytes().replace(b"Calculation of Filing Fee Tables", b"Unrelated disclosure")
    raw = raw.replace(b"<table", b"<div").replace(b"</table>", b"</div>")
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z"
    )["observations"]
    assert {row["state"]["disposition"] for row in rows} == {"unavailable"}
    assert {row["state"]["reason"] for row in rows} == {"fee_table_not_detected"}
    assert all(row["reported"]["value"] is None for row in rows)
    assert all(row["reported"]["raw_text"] is None for row in rows)
    assert all(row["evidence"]["spans"][0]["locator_type"] == "document" for row in rows)


def test_primary_document_form_must_match_the_manifest_exactly():
    raw = FIXTURE.read_bytes().replace(b"<TYPE>S-3", b"<TYPE>S-3/A")
    manifest = _manifest(raw, form="S-3")
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z"
    )["observations"]
    assert {row["state"]["reason"] for row in rows} == {"eligible_document_not_found"}


def test_multiple_direct_rows_are_row_scoped_and_never_summed_or_collapsed():
    raw = FIXTURE.read_bytes().replace(
        b"</table>",
        b"<tr><td>Preferred stock</td><td>500,000</td><td>$4.00</td><td>$2,000,000</td><td>$232.80</td><td>0.0001164</td></tr></table>",
    )
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z"
    )["observations"]
    assert len(rows) == 10
    assert {row["state"]["disposition"] for row in rows} == {"observed"}
    assert len({row["security"]["row_id"] for row in rows}) == 2
    amounts = [
        row for row in rows if row["term"]["name"] == "amount_to_be_registered"
    ]
    assert {(row["security"]["title_raw"], row["reported"]["value"], row["reported"]["unit"]) for row in amounts} == {
        ("Common stock", "1250000", "shares"),
        ("Preferred stock", "500000", "shares"),
    }


def test_parser_correction_is_append_only_and_becomes_visible_only_when_produced():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    original = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z"
    )["observations"]
    old = deepcopy(original)
    target = next(row for row in old if row["term"]["name"] == "registration_fee")
    target["state"] = {"disposition": "unavailable", "reason": "header_without_direct_value"}
    target["reported"] = {"raw_text": None, "value": None, "unit": None, "currency": None, "scale": None}
    target["normalized"] = deepcopy(target["reported"])
    target["extraction"]["parser_version"] = "capital-structure-document-terms/0.9.0"
    target["observation_id"] = observation_id_for(target)
    result = compile_document_term_records(
        [manifest], source_reader=_reader(raw), existing_observations=old,
        generated_at="2026-08-04T00:00:00Z",
    )
    corrected = [row for row in result["observations"] if row["term"]["name"] == "registration_fee"]
    assert len(corrected) == 2
    prior, later = sorted(corrected, key=lambda row: row["version"]["correction_version"])
    assert later["version"] == {
        "immutable_record": True, "correction_version": 2, "correction_of": prior["observation_id"],
    }
    assert later["relationships"]["supersedes"] == [prior["observation_id"]]
    assert later["reported"]["value"] == "1237.1"
    before = current_document_terms_as_of(result["observations"], "2026-08-03T12:00:00Z")
    after = current_document_terms_as_of(result["observations"], "2026-08-04T00:00:00Z")
    assert next(row for row in before if row["term"]["name"] == "registration_fee")["reported"]["value"] is None
    assert next(row for row in after if row["term"]["name"] == "registration_fee")["reported"]["value"] == "1237.1"


def test_missing_or_wrong_source_bytes_abort_the_whole_generation():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    with pytest.raises(DocumentTermCompileDegraded, match="source failure"):
        compile_document_term_records(
            [manifest], source_reader=lambda _: None, generated_at="2026-08-03T00:00:00Z"
        )
    with pytest.raises(DocumentTermCompileDegraded, match="source failure"):
        compile_document_term_records(
            [manifest], source_reader=lambda _: raw + b"tamper", generated_at="2026-08-03T00:00:00Z"
        )


def test_re_signed_manifest_cannot_detach_its_root_span_from_retained_bytes():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    manifest["document"]["root_locator"] = "sha256:" + ("f" * 64)
    manifest["manifest_id"] = manifest_id_for(manifest)
    with pytest.raises(ValueError, match="root_locator"):
        compile_document_term_records(
            [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z"
        )


def test_disk_compiler_requires_matching_store_namespace_and_writes_canonical_ledger(tmp_path):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    pd.DataFrame([manifest]).to_parquet(tmp_path / "source_manifest.parquet", index=False)

    class Store:
        store_id = "r2_shared"

        def get_verified(self, object_key: str, expected_sha256: str) -> bytes | None:
            assert object_key == manifest["storage"]["object_key"]
            assert expected_sha256 == manifest["document"]["content_sha256"]
            return raw

    result = compile_from_disk(
        root=tmp_path, generated_at="2026-08-03T00:00:00Z", source_store=Store()
    )
    assert result["status"] == "ok"
    assert result["new_observations"] == 5
    ledger = pd.read_parquet(tmp_path / "document_term_observations.parquet")
    assert ledger.columns.tolist() == DOCUMENT_TERM_COLUMNS
    assert ledger["state"].tolist() == ["observed"] * 5
    assert all(value == json.dumps(json.loads(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False) for value in ledger["observation_json"])

    class WrongNamespace(Store):
        store_id = "r2_research"

    with pytest.raises(DocumentTermCompileDegraded, match="source failure"):
        compile_from_disk(
            root=tmp_path, generated_at="2026-08-04T00:00:00Z", source_store=WrongNamespace(), rebuild=True
        )


def test_disk_compiler_resolves_mixed_manifest_namespaces_independently(tmp_path):
    raw = FIXTURE.read_bytes()
    shared = _manifest(raw)
    research = deepcopy(shared)
    research["source_id"] = "0000000002-26-000002:0:complete-submission.txt"
    research["issuer"] = {
        "issuer_id": "sec:cik:0000000002", "cik": "2", "ticker": "XYZ",
        "aliases": ["XYZ Corp"],
    }
    research["filing"] = {
        "accession": "0000000002-26-000002", "form": "S-3",
        "filing_date": "2026-08-01", "accepted_at": "2026-08-01T11:01:00Z",
        "file_number": "333-654321",
    }
    research["storage"]["store_id"] = "r2_research"
    research["manifest_id"] = manifest_id_for(research)
    pd.DataFrame([shared, research]).to_parquet(tmp_path / "source_manifest.parquet", index=False)

    class Store:
        def __init__(self, store_id: str):
            self.store_id = store_id

        def get_verified(self, object_key: str, expected_sha256: str) -> bytes | None:
            assert object_key == shared["storage"]["object_key"]
            assert expected_sha256 == shared["document"]["content_sha256"]
            return raw

    result = compile_from_disk(
        root=tmp_path, generated_at="2026-08-03T00:00:00Z",
        source_store={"r2_shared": Store("r2_shared"), "r2_research": Store("r2_research")},
    )
    assert result["new_observations"] == 10
    ledger = pd.read_parquet(tmp_path / "document_term_observations.parquet")
    assert set(ledger["issuer_id"]) == {"sec:cik:0000000001", "sec:cik:0000000002"}


def test_debt_and_unit_rows_have_safe_explicit_dimensions_not_share_defaults():
    raw = FIXTURE.read_bytes()
    raw = raw.replace(b"Common stock", b"Senior notes")
    raw = raw.replace(b"1,250,000", b"$50,000,000")
    raw = raw.replace(b"$8.50", b"100%")
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    by_term = {row["term"]["name"]: row for row in rows}
    amount = by_term["amount_to_be_registered"]
    assert amount["term"]["term_type"] == "principal_amount"
    assert amount["reported"] == {
        "raw_text": "$50,000,000", "value": "50000000", "unit": "USD",
        "currency": "USD", "scale": "1",
    }
    price = by_term["proposed_maximum_offering_price_per_unit"]
    assert price["state"] == {
        "disposition": "ambiguous", "reason": "unsupported_dimensional_value",
    }
    assert price["reported"]["value"] is None


@pytest.mark.parametrize(("title", "amount_unit", "price_unit"), [
    (b"Units", "units", "USD/unit"),
    (b"Warrants", "securities", "USD/security"),
])
def test_unit_and_warrant_rows_keep_their_own_quantity_and_price_basis(
    title, amount_unit, price_unit,
):
    raw = FIXTURE.read_bytes().replace(b"Common stock", title)
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    by_term = {row["term"]["name"]: row for row in rows}
    assert by_term["amount_to_be_registered"]["reported"]["unit"] == amount_unit
    assert by_term["proposed_maximum_offering_price_per_unit"]["reported"]["unit"] == price_unit
    _schema_validate(rows)


@pytest.mark.parametrize("marker", [b"(1) ", b"[1] ", b"<sup>(1)</sup>"])
def test_leading_footnote_markers_never_become_the_economic_value(marker):
    raw = FIXTURE.read_bytes().replace(
        b"<td>1,250,000</td>", b"<td>" + marker + b"1,250,000</td>",
    )
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    amount = next(row for row in rows if row["term"]["name"] == "amount_to_be_registered")
    assert amount["reported"]["value"] == "1250000"


def test_denominated_fee_rate_preserves_numerator_and_denominator_exactly():
    raw = FIXTURE.read_bytes().replace(b"0.0001164", b"$147.60 per $1,000,000")
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    rate = next(row for row in rows if row["term"]["name"] == "filing_fee_rate")
    assert rate["reported"] == {
        "raw_text": "$147.60 per $1,000,000", "value": "147.6",
        "unit": "USD_per_USD", "currency": "USD", "scale": "1000000",
    }
    assert rate["normalized"] == rate["reported"]
    validate_observation_source_binding(rate, manifest, raw)
    silently_normalized = deepcopy(rate)
    silently_normalized["reported"] = {
        "raw_text": "$147.60 per $1,000,000", "value": "0.0001476",
        "unit": "rate", "currency": None, "scale": "1",
    }
    silently_normalized["normalized"] = deepcopy(silently_normalized["reported"])
    silently_normalized["observation_id"] = observation_id_for(silently_normalized)
    with pytest.raises(ValueError, match="does not round-trip"):
        validate_observation_source_binding(silently_normalized, manifest, raw)
    _schema_validate(rows)


def test_ex_filing_fees_child_is_selected_with_exact_child_provenance():
    fixture = FIXTURE.read_bytes()
    fee_child = fixture.split(b"<DOCUMENT>", 1)[1].rsplit(b"</DOCUMENT>", 1)[0]
    fee_child = fee_child.replace(b"<TYPE>S-3", b"<TYPE>EX-FILING FEES")
    primary = (
        b"<TYPE>S-3\n<SEQUENCE>1\n<FILENAME>registration.htm\n"
        b"<TEXT><html><body>No fee table in the primary document.</body></html></TEXT>"
    )
    raw = (
        b"<SEC-DOCUMENT>test.txt\n<SEC-HEADER>test\n<DOCUMENT>" + primary
        + b"</DOCUMENT>\n<DOCUMENT>" + fee_child + b"</DOCUMENT>\n</SEC-DOCUMENT>"
    )
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    assert {row["state"]["disposition"] for row in rows} == {"observed"}
    assert {row["document"]["child_document_type"] for row in rows} == {"EX-FILING FEES"}
    assert all("type=EX-FILING FEES" in span["locator"] for row in rows for span in row["evidence"]["spans"])
    for row in rows:
        validate_observation_source_binding(row, manifest, raw)


def test_identical_duplicate_rows_remain_two_distinct_observation_slots():
    duplicate = (
        b"<tr><td>Common stock</td><td>1,250,000</td><td>$8.50</td>"
        b"<td>$10,625,000.00</td><td>$1,237.10</td><td>0.0001164</td></tr>"
    )
    raw = FIXTURE.read_bytes().replace(b"</table>", duplicate + b"</table>")
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    amounts = [row for row in rows if row["term"]["name"] == "amount_to_be_registered"]
    assert len(amounts) == 2
    assert len({row["logical_observation_id"] for row in amounts}) == 2
    assert {row["reported"]["value"] for row in amounts} == {"1250000"}


def test_generated_at_cannot_precede_source_availability():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    with pytest.raises(ValueError, match="cannot precede retained source availability"):
        compile_document_term_records(
            [manifest], source_reader=_reader(raw), generated_at="2026-08-01T00:00:00Z",
        )


def test_exact_span_hash_and_locator_are_rebound_to_source_bytes():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    row = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"][0]
    validate_observation_source_binding(row, manifest, raw)
    detached = deepcopy(row)
    detached["evidence"]["spans"][-1]["locator"] = (
        "complete_submission:type=S-3:sequence=1:filename=registration.htm:"
        "table=0:row=1:cell=1:role=amount_to_be_registered:bytes:0-1"
    )
    detached["observation_id"] = observation_id_for(detached)
    with pytest.raises(ValueError, match="span hash is detached"):
        validate_observation_source_binding(detached, manifest, raw)

    wrong_issuer = deepcopy(row)
    wrong_issuer["issuer_id"] = "sec:cik:9999999999"
    wrong_issuer["observation_id"] = observation_id_for(wrong_issuer)
    with pytest.raises(ValueError, match="issuer_id is detached"):
        validate_observation_source_binding(wrong_issuer, manifest, raw)

    wrong_row = deepcopy(row)
    wrong_row["security"]["row_id"] = "fee-row:cs:" + ("f" * 24)
    wrong_row["observation_id"] = observation_id_for(wrong_row)
    with pytest.raises(ValueError, match="row_id is detached"):
        validate_observation_source_binding(wrong_row, manifest, raw)

    wrong_title = deepcopy(row)
    wrong_title["security"]["title_raw"] = "Preferred stock"
    wrong_title["security"]["title_normalized"] = "preferred stock"
    wrong_title["security"]["classification"] = "preferred_stock"
    wrong_title["observation_id"] = observation_id_for(wrong_title)
    with pytest.raises(ValueError, match="security identity is detached"):
        validate_observation_source_binding(wrong_title, manifest, raw)

    wrong_source_clock = deepcopy(row)
    wrong_source_clock["point_in_time"]["source_available_at"] = "2026-08-01T12:00:00Z"
    wrong_source_clock["observation_id"] = observation_id_for(wrong_source_clock)
    with pytest.raises(ValueError, match="source_available_at is detached"):
        validate_observation_source_binding(wrong_source_clock, manifest, raw)


def test_history_requires_source_before_output_and_exact_supersedes_link():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    original = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"][0]
    impossible = deepcopy(original)
    impossible["point_in_time"]["available_at"] = "2026-08-01T00:00:00Z"
    impossible["observation_id"] = observation_id_for(impossible)
    with pytest.raises(ValueError, match="precedes source_available_at"):
        validate_document_term_history([impossible])

    correction = deepcopy(original)
    correction["version"] = {
        "immutable_record": True, "correction_version": 2,
        "correction_of": original["observation_id"],
    }
    correction["relationships"]["supersedes"] = []
    correction["point_in_time"]["available_at"] = "2026-08-04T00:00:00Z"
    correction["extraction"]["parser_version"] = "capital-structure-document-terms/1.2.0"
    correction["observation_id"] = observation_id_for(correction)
    with pytest.raises(ValueError, match="supersedes does not point to prior"):
        validate_document_term_history([original, correction])


def test_daily_compiler_has_namespace_parity_with_collector():
    workflow = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    step = workflow.split(
        "- name: compile capital-structure direct document terms", 1,
    )[1].split("- name: build capital-structure projection", 1)[0]
    for variable in (
        "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
        "R2_CAPITAL_STRUCTURE_ENDPOINT", "R2_CAPITAL_STRUCTURE_ACCESS_KEY_ID",
        "R2_CAPITAL_STRUCTURE_SECRET_ACCESS_KEY", "R2_CAPITAL_STRUCTURE_BUCKET",
        "R2_RESEARCH_ENDPOINT", "R2_RESEARCH_ACCESS_KEY_ID",
        "R2_RESEARCH_SECRET_ACCESS_KEY", "R2_RESEARCH_BUCKET",
    ):
        assert f"{variable}:" in step
