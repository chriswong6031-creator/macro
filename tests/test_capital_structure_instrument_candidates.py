"""Adversarial tests for the deliberately pre-instrument candidate-term kernel."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker

import engine.capital_structure.document_terms as document_terms
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


_FIXTURE_PRIOR_PARSER_VERSION = "test-document-terms-fixture/0.0.1"


def _fixture_prior_unavailable_parser(manifest: dict, raw: bytes | None, parser_version: str) -> list[dict]:
    rows = document_terms._records_for_manifest_v1_1_0(manifest, raw, parser_version)
    for row in rows:
        row["state"] = {"disposition": "unavailable", "reason": "header_without_direct_value"}
        row["reported"] = document_terms._empty_value()
        row["normalized"] = document_terms._empty_value()
    return rows


def _register_fixture_prior_parser(monkeypatch) -> str:
    monkeypatch.setitem(
        document_terms._PARSER_REGISTRY,
        _FIXTURE_PRIOR_PARSER_VERSION,
        document_terms.ParserRegistration(
            version=_FIXTURE_PRIOR_PARSER_VERSION,
            implementation_sha256=document_terms._implementation_sha256(
                _fixture_prior_unavailable_parser, (),
            ),
            extractor=_fixture_prior_unavailable_parser,
            semantic_symbols=(),
        ),
    )
    return _FIXTURE_PRIOR_PARSER_VERSION


def _direct_rows() -> list[dict]:
    return _direct_authority()[0]


def _direct_authority() -> tuple[list[dict], list[dict], object]:
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=lambda _: raw, generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    return rows, [manifest], lambda _: raw


class _FixtureStore:
    store_id = "r2_shared"

    def __init__(self, manifest: dict, raw: bytes) -> None:
        self.manifest = manifest
        self.raw = raw

    def get_verified(self, object_key: str, expected_sha256: str) -> bytes | None:
        assert object_key == self.manifest["storage"]["object_key"]
        assert expected_sha256 == self.manifest["document"]["content_sha256"]
        return self.raw


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


def _compile(
    rows: list[dict],
    *,
    manifests: list[dict],
    reader,
    generated_at: str = "2026-08-04T00:00:00Z",
    existing: list[dict] | None = None,
    source_as_of: str | None = None,
) -> dict:
    return compile_candidate_term_records(
        rows,
        source_manifests=manifests,
        source_reader=reader,
        existing_candidate_terms=existing or [],
        generated_at=generated_at,
        source_as_of=source_as_of,
    )


def test_candidate_projection_is_one_to_one_and_preserves_direct_evidence_without_creating_an_instrument():
    source, manifests, reader = _direct_authority()
    result = _compile(source, manifests=manifests, reader=reader)
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
        "is_context_only": True, "instrument_authority": False, "capacity_authority": False,
        "risk_authority": False, "probability_authority": False, "rank_authority": False,
        "sizing_authority": False, "entry_authority": False, "trade_authority": False,
        "prophet_authority": False,
    } for row in rows)


def test_rate_and_fee_rows_remain_evidence_only_not_an_implied_supply_or_capacity():
    source, manifests, reader = _direct_authority()
    rows = _compile(source, manifests=manifests, reader=reader)["observations"]
    rate = next(row for row in rows if row["term"]["name"] == "filing_fee_rate")
    assert rate["candidate"]["family"] == "common_stock"
    assert rate["candidate"]["supply_role"] == "not_applicable"
    assert rate["candidate"]["state"]["reason"] == "direct_security_class_mapping_supply_not_applicable"
    assert "capacity" not in rate
    assert rate["authority"]["capacity_authority"] is False


def test_candidate_contract_rejects_legacy_or_partial_authority_vocabulary():
    source, manifests, reader = _direct_authority()
    row = _compile(source, manifests=manifests, reader=reader)["observations"][0]
    validator = Draft202012Validator(_candidate_contract(), format_checker=FormatChecker())

    legacy = deepcopy(row)
    legacy["authority"] = {
        "context_only": True,
        "may_calculate_capacity": False,
        "may_emit_risk": False,
        "may_emit_probability": False,
        "may_gate_prophet": False,
    }
    assert list(validator.iter_errors(legacy))

    partial = deepcopy(row)
    del partial["authority"]["trade_authority"]
    assert list(validator.iter_errors(partial))


def test_unknown_direct_security_and_unsupported_term_type_stay_explicitly_deferred():
    source = deepcopy(next(row for row in _direct_rows() if row["term"]["name"] == "registration_fee"))
    source["security"]["classification"] = "unknown"
    assert candidate_mapping_for_document_term(source)["state"] == {
        "disposition": "deferred", "reason": "security_classification_unknown",
    }
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
    projected = candidate_mapping_for_document_term(source)
    assert projected["state"] == {"disposition": "ambiguous", "reason": "upstream_document_term_ambiguous"}
    assert projected["family"] == "unknown"
    assert projected["supply_role"] == "unknown"


def test_candidate_correction_is_not_visible_until_this_projection_compiles(monkeypatch):
    prior_version = _register_fixture_prior_parser(monkeypatch)
    monkeypatch.setattr(document_terms, "PARSER_VERSION", prior_version)
    direct_v1, manifests, reader = _direct_authority()
    baseline = _compile(direct_v1, manifests=manifests, reader=reader)["observations"]
    monkeypatch.setattr(document_terms, "PARSER_VERSION", "capital-structure-document-terms/1.1.0")
    direct_v2 = compile_document_term_records(
        manifests,
        source_reader=reader,
        existing_observations=direct_v1,
        generated_at="2026-08-05T00:00:00Z",
    )["observations"]
    result = _compile(
        direct_v2,
        manifests=manifests,
        reader=reader,
        existing=baseline,
        generated_at="2026-08-06T00:00:00Z",
    )
    corrected = [row for row in result["observations"] if row["term"]["name"] == "registration_fee"]
    assert len(corrected) == 2
    prior, later = sorted(corrected, key=lambda row: row["version"]["correction_version"])
    assert later["version"] == {"immutable_record": True, "correction_version": 2, "correction_of": prior["candidate_term_id"]}
    assert prior["source_term_state"]["disposition"] == "unavailable"
    assert later["source_term_state"]["disposition"] == "observed"
    assert later["point_in_time"]["available_at"] == "2026-08-06T00:00:00Z"
    before = current_candidate_terms_as_of(
        result["observations"], "2026-08-05T23:59:59Z",
        document_term_observations=direct_v2, source_manifests=manifests, source_reader=reader,
    )
    after = current_candidate_terms_as_of(
        result["observations"], "2026-08-06T00:00:00Z",
        document_term_observations=direct_v2, source_manifests=manifests, source_reader=reader,
    )
    assert next(row for row in before if row["term"]["name"] == "registration_fee")["source_term"]["observation_id"] == prior["source_term"]["observation_id"]
    assert next(row for row in after if row["term"]["name"] == "registration_fee")["source_term"]["observation_id"] == later["source_term"]["observation_id"]

    with pytest.raises(ValueError, match="historical source_as_of cannot write"):
        _compile(
            direct_v2,
            manifests=manifests,
            reader=reader,
            existing=result["observations"],
            generated_at="2026-08-07T00:00:00Z",
            source_as_of="2026-08-04T00:00:00Z",
        )


def test_candidate_history_rejects_rehashed_issuer_evidence_and_null_value_mutations():
    source, manifests, reader = _direct_authority()
    rows = _compile(source, manifests=manifests, reader=reader)["observations"]
    mutated = deepcopy(rows)
    mutated[0]["candidate"]["family"] = "other"
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_candidate_term_history(
            mutated,
            document_term_observations=source, source_manifests=manifests, source_reader=reader,
        )
    recomputed = deepcopy(mutated)
    recomputed[0]["candidate_term_id"] = candidate_term_id_for(recomputed[0])
    with pytest.raises(ValueError, match="candidate mapping is detached from embedded source fields"):
        validate_candidate_term_history(
            recomputed,
            document_term_observations=source, source_manifests=manifests, source_reader=reader,
        )

    rebound_issuer = deepcopy(rows)
    rebound_issuer[0]["issuer_id"] = "sec:cik:9999999999"
    rebound_issuer[0]["candidate_term_id"] = candidate_term_id_for(rebound_issuer[0])
    with pytest.raises(ValueError, match="issuer_id is detached"):
        current_candidate_terms_as_of(
            rebound_issuer, "2026-08-04T00:00:00Z",
            document_term_observations=source, source_manifests=manifests, source_reader=reader,
        )

    rebound_evidence = deepcopy(rows)
    rebound_evidence[0]["evidence"]["spans"][0]["locator"] = "tampered:locator"
    rebound_evidence[0]["candidate_term_id"] = candidate_term_id_for(rebound_evidence[0])
    with pytest.raises(ValueError, match="evidence is detached from its direct observation"):
        current_candidate_terms_as_of(
            rebound_evidence, "2026-08-04T00:00:00Z",
            document_term_observations=source, source_manifests=manifests, source_reader=reader,
        )

    null_value = deepcopy(rows)
    amount = next(row for row in null_value if row["term"]["name"] == "amount_to_be_registered")
    amount["reported"] = {"raw_text": None, "value": None, "unit": None, "currency": None, "scale": None}
    amount["normalized"] = deepcopy(amount["reported"])
    amount["candidate_term_id"] = candidate_term_id_for(amount)
    with pytest.raises(ValueError, match="reported is detached from its direct observation"):
        current_candidate_terms_as_of(
            null_value, "2026-08-04T00:00:00Z",
            document_term_observations=source, source_manifests=manifests, source_reader=reader,
        )

    with pytest.raises(ValueError, match="duplicate"):
        validate_candidate_term_history(
            rows + [deepcopy(rows[0])],
            document_term_observations=source, source_manifests=manifests, source_reader=reader,
        )
    no_evidence = deepcopy(source[0])
    no_evidence["evidence"]["spans"] = []
    no_evidence["observation_id"] = observation_id_for(no_evidence)
    with pytest.raises(ValueError, match="contract violation"):
        _compile([no_evidence], manifests=manifests, reader=reader)


def test_no_fuzzy_join_exists_when_two_identical_family_rows_share_an_issuer():
    raw = FIXTURE.read_bytes().replace(
        b"</table>",
        b"<tr><td>Common stock</td><td>500,000</td><td>$4.00</td><td>$2,000,000</td><td>$232.80</td><td>0.0001164</td></tr></table>",
    )
    manifest = _manifest(raw)
    source = compile_document_term_records([manifest], source_reader=lambda _: raw, generated_at="2026-08-03T00:00:00Z")["observations"]
    rows = _compile(source, manifests=[manifest], reader=lambda _: raw)["observations"]
    amounts = [row for row in rows if row["term"]["name"] == "amount_to_be_registered"]
    assert len(amounts) == 2
    assert len({row["logical_candidate_term_id"] for row in amounts}) == 2
    assert len({row["source_term"]["observation_id"] for row in amounts}) == 2
    assert all("match" not in row and "instrument_id" not in row for row in amounts)


def test_offline_compiler_requires_the_exact_direct_ledger_and_writes_canonical_candidate_ledger(tmp_path):
    direct, manifests, _ = _direct_authority()
    raw = FIXTURE.read_bytes()
    manifest = manifests[0]
    pd.DataFrame(manifests).to_parquet(tmp_path / "source_manifest.parquet", index=False)
    _direct_frame(direct).to_parquet(tmp_path / "document_term_observations.parquet", index=False)
    result = compile_from_disk(
        root=tmp_path,
        generated_at="2026-08-04T00:00:00Z",
        source_store=_FixtureStore(manifest, raw),
    )
    assert result["status"] == "ok"
    assert result["created"] == 5
    ledger = pd.read_parquet(tmp_path / "instrument_candidate_terms.parquet")
    assert ledger.columns.tolist() == CANDIDATE_TERM_COLUMNS
    assert all(value == json.dumps(json.loads(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False) for value in ledger["candidate_term_json"])
    absent = compile_from_disk(root=tmp_path / "missing", generated_at="2026-08-04T00:00:00Z")
    assert absent["status"] == "unavailable"
    assert absent["reason"] == "document_term_ledger_absent"


def test_offline_compiler_rejects_a_self_consistent_direct_issuer_mutation(tmp_path):
    direct, manifests, _ = _direct_authority()
    raw = FIXTURE.read_bytes()
    manifest = manifests[0]
    tampered = deepcopy(direct)
    tampered[0]["issuer_id"] = "sec:cik:9999999999"
    tampered[0]["observation_id"] = observation_id_for(tampered[0])
    pd.DataFrame(manifests).to_parquet(tmp_path / "source_manifest.parquet", index=False)
    _direct_frame(tampered).to_parquet(tmp_path / "document_term_observations.parquet", index=False)

    with pytest.raises(ValueError, match="issuer_id is detached from source manifest"):
        compile_from_disk(
            root=tmp_path,
            generated_at="2026-08-04T00:00:00Z",
            source_store=_FixtureStore(manifest, raw),
        )


def test_rehashed_direct_and_manifest_envelopes_fail_closed_on_pure_disk_and_pit_surfaces(tmp_path):
    """A valid digest cannot promote a rewritten source-derived direct fact."""
    direct, manifests, reader = _direct_authority()
    raw = FIXTURE.read_bytes()
    baseline = _compile(direct, manifests=manifests, reader=reader)["observations"]

    null_value = deepcopy(direct)
    amount = next(row for row in null_value if row["term"]["name"] == "amount_to_be_registered")
    amount["state"] = {"disposition": "unavailable", "reason": "header_without_direct_value"}
    amount["reported"] = {"raw_text": None, "value": None, "unit": None, "currency": None, "scale": None}
    amount["normalized"] = deepcopy(amount["reported"])
    amount["observation_id"] = observation_id_for(amount)

    span_id = deepcopy(direct)
    span_id[0]["evidence"]["spans"][0]["span_id"] = "span:cs:" + ("0" * 24)
    span_id[0]["observation_id"] = observation_id_for(span_id[0])

    duplicate_slot = deepcopy(direct)
    duplicate = deepcopy(duplicate_slot[0])
    duplicate["logical_observation_id"] = "document-term-slot:cs:" + ("0" * 24)
    duplicate["observation_id"] = observation_id_for(duplicate)
    duplicate_slot.append(duplicate)

    forged_manifest = deepcopy(manifests[0])
    forged_manifest["issuer"] = {
        "issuer_id": "sec:cik:9999999999", "cik": "9999999999", "ticker": "EVIL",
        "aliases": ["Evil Corp"],
    }
    forged_manifest["manifest_id"] = manifest_id_for(forged_manifest)
    forged_issuer = deepcopy(direct)
    for row in forged_issuer:
        row["issuer_id"] = "sec:cik:9999999999"
        row["document"]["source_manifest_id"] = forged_manifest["manifest_id"]
        row["evidence"]["source_manifest_id"] = forged_manifest["manifest_id"]
        for span in row["evidence"]["spans"]:
            span["manifest_id"] = forged_manifest["manifest_id"]
        row["observation_id"] = observation_id_for(row)

    def rebind_direct_rows(forged: dict) -> list[dict]:
        rebound = deepcopy(direct)
        for row in rebound:
            row["issuer_id"] = forged["issuer"]["issuer_id"]
            row["filing"]["accession"] = forged["filing"]["accession"]
            row["filing"]["form"] = forged["filing"]["form"]
            row["document"]["source_manifest_id"] = forged["manifest_id"]
            row["document"]["source_id"] = forged["source_id"]
            row["evidence"]["source_manifest_id"] = forged["manifest_id"]
            for span in row["evidence"]["spans"]:
                span["manifest_id"] = forged["manifest_id"]
            row["observation_id"] = observation_id_for(row)
        return rebound

    forged_source_id = deepcopy(manifests[0])
    forged_source_id["source_id"] = "0000000001-26-000001:99:evil.txt"
    forged_source_id["manifest_id"] = manifest_id_for(forged_source_id)

    forged_form = deepcopy(manifests[0])
    forged_form["filing"]["form"] = "S-1"
    forged_form["manifest_id"] = manifest_id_for(forged_form)

    attacks = [
        ("null_value", null_value, manifests, "state is detached", _FixtureStore(manifests[0], raw)),
        ("span_id", span_id, manifests, "evidence is detached", _FixtureStore(manifests[0], raw)),
        ("logical_slot", duplicate_slot, manifests, "logical_observation_id is detached", _FixtureStore(manifests[0], raw)),
        ("manifest_issuer", forged_issuer, [forged_manifest], "issuer.cik is detached", _FixtureStore(forged_manifest, raw)),
        ("manifest_source_id", rebind_direct_rows(forged_source_id), [forged_source_id], "source_id is detached", _FixtureStore(forged_source_id, raw)),
        ("manifest_form", rebind_direct_rows(forged_form), [forged_form], "filing.form is detached", _FixtureStore(forged_form, raw)),
    ]
    for label, tampered, authority_manifests, error, store in attacks:
        with pytest.raises(ValueError, match=error):
            _compile(tampered, manifests=authority_manifests, reader=lambda _: raw)
        with pytest.raises(ValueError, match=error):
            current_candidate_terms_as_of(
                baseline, "2026-08-04T00:00:00Z",
                document_term_observations=tampered,
                source_manifests=authority_manifests,
                source_reader=lambda _: raw,
            )

        root = tmp_path / label
        root.mkdir()
        pd.DataFrame(authority_manifests).to_parquet(root / "source_manifest.parquet", index=False)
        _direct_frame(tampered).to_parquet(root / "document_term_observations.parquet", index=False)
        with pytest.raises(ValueError, match=error):
            compile_from_disk(
                root=root, generated_at="2026-08-04T00:00:00Z", source_store=store,
            )


def test_historical_source_as_of_rollback_is_rejected_by_pure_and_disk_compilers(tmp_path, monkeypatch):
    prior_version = _register_fixture_prior_parser(monkeypatch)
    monkeypatch.setattr(document_terms, "PARSER_VERSION", prior_version)
    direct_v1, manifests, reader = _direct_authority()
    baseline = _compile(direct_v1, manifests=manifests, reader=reader)["observations"]
    monkeypatch.setattr(document_terms, "PARSER_VERSION", "capital-structure-document-terms/1.1.0")
    direct_v2 = compile_document_term_records(
        manifests, source_reader=reader, existing_observations=direct_v1,
        generated_at="2026-08-05T00:00:00Z",
    )["observations"]
    candidates = _compile(
        direct_v2, manifests=manifests, reader=reader, existing=baseline,
        generated_at="2026-08-06T00:00:00Z",
    )["observations"]
    with pytest.raises(ValueError, match="historical source_as_of cannot write"):
        _compile(
            direct_v2, manifests=manifests, reader=reader, existing=candidates,
            generated_at="2026-08-07T00:00:00Z", source_as_of="2026-08-04T00:00:00Z",
        )

    raw = FIXTURE.read_bytes()
    manifest = manifests[0]
    pd.DataFrame(manifests).to_parquet(tmp_path / "source_manifest.parquet", index=False)
    _direct_frame(direct_v2).to_parquet(tmp_path / "document_term_observations.parquet", index=False)
    candidate_frame = pd.DataFrame([
        {
            "candidate_term_id": row["candidate_term_id"],
            "logical_candidate_term_id": row["logical_candidate_term_id"],
            "issuer_id": row["issuer_id"],
            "accession": row["filing"]["accession"], "form": row["filing"]["form"],
            "source_manifest_id": row["document"]["source_manifest_id"],
            "direct_observation_id": row["source_term"]["observation_id"],
            "candidate_family": row["candidate"]["family"], "supply_role": row["candidate"]["supply_role"],
            "state": row["candidate"]["state"]["disposition"],
            "available_at": row["point_in_time"]["available_at"],
            "correction_version": row["version"]["correction_version"],
            "candidate_term_json": json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        }
        for row in candidates
    ], columns=CANDIDATE_TERM_COLUMNS)
    candidate_frame.to_parquet(tmp_path / "instrument_candidate_terms.parquet", index=False)
    with pytest.raises(ValueError, match="historical source_as_of cannot write"):
        compile_from_disk(
            root=tmp_path, generated_at="2026-08-07T00:00:00Z",
            source_as_of="2026-08-04T00:00:00Z", source_store=_FixtureStore(manifest, raw),
        )
