"""Adversarial tests for the deliberately pre-instrument candidate-term kernel."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import inspect
import json
from pathlib import Path

import pandas as pd
import pytest
import jsonschema
from jsonschema import Draft202012Validator, FormatChecker

import engine.capital_structure.document_terms as document_terms
import engine.capital_structure.instrument_candidates as instrument_candidates
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


def test_candidate_authority_rejects_post_import_synthetic_parser_registration(monkeypatch):
    source, manifests, reader = _direct_authority()
    released = document_terms._PARSER_REGISTRY[
        "capital-structure-document-terms/1.1.0"
    ]
    forged = document_terms.ParserRegistration(
        version=_FIXTURE_PRIOR_PARSER_VERSION,
        implementation_sha256=released.implementation_sha256,
        extractor=released.extractor,
        semantic_bundle=released.semantic_bundle,
    )
    monkeypatch.setattr(
        document_terms,
        "_PARSER_REGISTRY",
        {**dict(document_terms._PARSER_REGISTRY), forged.version: forged},
    )
    tampered = deepcopy(source)
    for row in tampered:
        row["extraction"]["parser_version"] = forged.version
        row["observation_id"] = document_terms.observation_id_for(row)

    with pytest.raises(ValueError, match="parser_version is not registered"):
        _compile(tampered, manifests=manifests, reader=reader)


def test_candidate_authority_policy_has_release_golden_closure():
    manifest, manifest_sha256, implementation_sha256 = (
        instrument_candidates._semantic_closure(
            instrument_candidates._CANDIDATE_AUTHORITY_ENTRYPOINTS,
        )
    )
    assert len(manifest) == 194
    assert manifest_sha256 == (
        "5c93c5790e103ebc82f9e7865e27bb9576370235ddd27c64ff57a84fbc1bb9eb"
    )
    assert implementation_sha256 == (
        "7adefd79136224d8c0ca0c84cd4ef41bd206690f9ec28622cdf95f682c811b28"
    )
    for required in (
        "._validate_candidate_term_records_contract",
        "._validate_candidate_term_structure",
        "._validate_candidate_source_binding_core",
        "._validate_candidate_term_history_core",
        "._current_candidate_terms_as_of_core",
        "._validate_document_term_authority_core",
        "._compile_candidate_term_records_core",
        "._candidate_term_contract_validator",
    ):
        assert any(required in node for node in manifest), required


def test_public_candidate_trust_surfaces_expose_no_injectable_trust_parameters():
    surfaces = (
        instrument_candidates.validate_candidate_source_binding,
        instrument_candidates.validate_candidate_term_structure,
        instrument_candidates.validate_candidate_term_history,
        instrument_candidates.current_candidate_terms_as_of,
        instrument_candidates.validate_document_term_authority,
        instrument_candidates.compile_candidate_term_records,
    )
    forbidden = {
        "_trusted_source_authority",
        "_document_term_authority_validator",
        "_candidate_history_validator",
        "_current_document_terms_selector",
    }
    for surface in surfaces:
        assert forbidden.isdisjoint(inspect.signature(surface).parameters)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        instrument_candidates.validate_document_term_authority(
            [], source_manifests=[], source_reader=lambda _manifest: b"",
            _trusted_source_authority=lambda *args, **kwargs: [],
        )


def test_candidate_schema_provider_monkeypatch_cannot_admit_unknown_fields(monkeypatch):
    source, manifests, reader = _direct_authority()
    rows = _compile(source, manifests=manifests, reader=reader)["observations"]
    tampered = deepcopy(rows)
    tampered[0]["unexpected_top_level"] = "smuggled"
    tampered[0]["candidate_term_id"] = candidate_term_id_for(tampered[0])

    class NoopValidator:
        @classmethod
        def check_schema(cls, schema):
            return None

        def __init__(self, *args, **kwargs):
            pass

        def iter_errors(self, record):
            return iter(())

    monkeypatch.setattr(jsonschema, "Draft202012Validator", NoopValidator)
    with pytest.raises(ValueError, match="contract violation"):
        instrument_candidates.validate_candidate_term_structure(tampered)


def test_candidate_source_binding_admits_both_rows_through_closed_contracts():
    source, manifests, reader = _direct_authority()
    rows = _compile(source, manifests=manifests, reader=reader)["observations"]
    candidate = rows[0]
    direct = next(
        row
        for row in source
        if row["observation_id"] == candidate["source_term"]["observation_id"]
    )
    instrument_candidates.validate_candidate_source_binding(candidate, direct)

    tampered_candidate = deepcopy(candidate)
    tampered_candidate["unexpected_top_level"] = "smuggled"
    tampered_candidate["candidate_term_id"] = candidate_term_id_for(
        tampered_candidate,
    )
    with pytest.raises(ValueError, match="contract violation"):
        instrument_candidates.validate_candidate_source_binding(
            tampered_candidate, direct,
        )

    invalid_time_candidate = deepcopy(candidate)
    invalid_time_candidate["point_in_time"]["available_at"] = "not-a-time"
    invalid_time_candidate["candidate_term_id"] = candidate_term_id_for(
        invalid_time_candidate,
    )
    with pytest.raises(ValueError, match="contract violation"):
        instrument_candidates.validate_candidate_source_binding(
            invalid_time_candidate, direct,
        )

    tampered_direct = deepcopy(direct)
    tampered_direct["unexpected_top_level"] = "smuggled"
    tampered_direct["observation_id"] = observation_id_for(tampered_direct)
    rebound_candidate = instrument_candidates._project_record(
        tampered_direct,
        generated_at="2026-08-04T00:00:00Z",
        correction_version=1,
        correction_of=None,
    )
    with pytest.raises(ValueError, match="document-term contract violation"):
        instrument_candidates.validate_candidate_source_binding(
            rebound_candidate, tampered_direct,
        )


def test_candidate_source_binding_rejects_rebound_document_contract(monkeypatch):
    source, manifests, reader = _direct_authority()
    candidate = _compile(
        source, manifests=manifests, reader=reader,
    )["observations"][0]
    direct = next(
        row
        for row in source
        if row["observation_id"] == candidate["source_term"]["observation_id"]
    )
    monkeypatch.setattr(
        instrument_candidates,
        "validate_document_term_contract",
        lambda _record: None,
    )
    with pytest.raises(ValueError, match="document-term contract binding changed"):
        instrument_candidates.validate_candidate_source_binding(candidate, direct)


@pytest.mark.parametrize("method_name", ["iter_errors", "descend"])
def test_candidate_gates_reject_mutated_captured_validator_methods(
    monkeypatch, method_name,
):
    source, manifests, reader = _direct_authority()
    rows = _compile(source, manifests=manifests, reader=reader)["observations"]
    tampered = deepcopy(rows)
    tampered[0]["unexpected_top_level"] = "smuggled"
    tampered[0]["candidate_term_id"] = candidate_term_id_for(tampered[0])

    monkeypatch.setattr(
        Draft202012Validator,
        method_name,
        lambda self, instance, *args, **kwargs: iter(()),
    )
    calls = (
        lambda: instrument_candidates.validate_candidate_term_structure(tampered),
        lambda: validate_candidate_term_history(
            tampered,
            document_term_observations=source,
            source_manifests=manifests,
            source_reader=reader,
        ),
        lambda: current_candidate_terms_as_of(
            tampered,
            "2026-08-04T00:00:00Z",
            document_term_observations=source,
            source_manifests=manifests,
            source_reader=reader,
        ),
    )
    for call in calls:
        with pytest.raises(
            ValueError, match="schema validator executable binding changed",
        ):
            call()


def test_candidate_gate_rejects_in_place_validator_code_mutation(monkeypatch):
    source, manifests, reader = _direct_authority()
    rows = _compile(source, manifests=manifests, reader=reader)["observations"]
    tampered = deepcopy(rows)
    tampered[0]["unexpected_top_level"] = "smuggled"
    tampered[0]["candidate_term_id"] = candidate_term_id_for(tampered[0])

    marker = object()

    def noop_iter_errors(self, instance, *args, **kwargs):
        _ = marker
        return iter(())

    monkeypatch.setattr(
        Draft202012Validator.iter_errors,
        "__code__",
        noop_iter_errors.__code__,
    )
    with pytest.raises(
        ValueError,
        match="schema validator executable binding changed|authority closure mismatch",
    ):
        instrument_candidates.validate_candidate_term_structure(tampered)


def test_candidate_schema_validator_state_is_fresh_for_every_trust_use():
    source, manifests, reader = _direct_authority()
    rows = _compile(source, manifests=manifests, reader=reader)["observations"]
    leaked = instrument_candidates._candidate_term_contract_validator()
    properties = next(
        value
        for _implementation, keyword, value in leaked.__self__._validators
        if keyword == "properties"
    )
    properties["version"]["additionalProperties"] = True
    assert (
        instrument_candidates._candidate_term_contract_validator().__self__
        is not leaked.__self__
    )

    tampered = deepcopy(rows)
    tampered[0]["version"]["unexpected_nested"] = "smuggled"
    tampered[0]["candidate_term_id"] = candidate_term_id_for(tampered[0])
    calls = (
        lambda: instrument_candidates.validate_candidate_term_structure(tampered),
        lambda: validate_candidate_term_history(
            tampered,
            document_term_observations=source,
            source_manifests=manifests,
            source_reader=reader,
        ),
        lambda: current_candidate_terms_as_of(
            tampered,
            "2026-08-04T00:00:00Z",
            document_term_observations=source,
            source_manifests=manifests,
            source_reader=reader,
        ),
        lambda: _compile(
            source,
            manifests=manifests,
            reader=reader,
            existing=tampered,
            generated_at="2026-08-05T00:00:00Z",
        ),
    )
    for call in calls:
        with pytest.raises(ValueError, match="contract violation"):
            call()


def test_candidate_gate_rejects_mutated_validator_helper_global(monkeypatch):
    source, manifests, reader = _direct_authority()
    rows = _compile(source, manifests=manifests, reader=reader)["observations"]
    tampered = deepcopy(rows)
    tampered[0]["unexpected_top_level"] = "smuggled"
    tampered[0]["candidate_term_id"] = candidate_term_id_for(tampered[0])

    additional_properties = Draft202012Validator.VALIDATORS[
        "additionalProperties"
    ]
    monkeypatch.setitem(
        additional_properties.__globals__,
        "find_additional_properties",
        lambda _instance, _schema: iter(()),
    )
    with pytest.raises(
        ValueError, match="schema validator executable binding changed",
    ):
        instrument_candidates.validate_candidate_term_structure(tampered)


def test_candidate_compile_rejects_noop_imported_direct_authority(monkeypatch):
    source, manifests, reader = _direct_authority()

    def noop(*args, **kwargs):
        return [deepcopy(row) for row in source]

    monkeypatch.setattr(
        instrument_candidates,
        "validate_document_term_source_authority",
        noop,
    )
    monkeypatch.setattr(
        instrument_candidates,
        "_RELEASED_DOCUMENT_TERM_SOURCE_AUTHORITY",
        noop,
    )
    with pytest.raises(ValueError, match="document-term authority binding changed"):
        _compile(source, manifests=manifests, reader=reader)


def test_candidate_compile_rejects_rebound_candidate_authority_gate(monkeypatch):
    source, manifests, reader = _direct_authority()
    monkeypatch.setattr(
        instrument_candidates,
        "validate_document_term_authority",
        lambda *args, **kwargs: [deepcopy(row) for row in source],
    )
    with pytest.raises(ValueError, match="document-term gate binding changed"):
        _compile(source, manifests=manifests, reader=reader)


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


def test_historical_source_as_of_rollback_is_rejected_by_pure_and_disk_compilers(tmp_path):
    direct_v2, manifests, reader = _direct_authority()
    candidates = _compile(
        direct_v2, manifests=manifests, reader=reader,
        generated_at="2026-08-06T00:00:00Z",
    )["observations"]
    with pytest.raises(ValueError, match="historical source_as_of cannot write"):
        _compile(
            direct_v2, manifests=manifests, reader=reader, existing=candidates,
            generated_at="2026-08-07T00:00:00Z", source_as_of="2026-08-02T00:00:00Z",
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
            source_as_of="2026-08-02T00:00:00Z", source_store=_FixtureStore(manifest, raw),
        )
