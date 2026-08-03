"""Fixture-pinned precision tests for document-row fee-table transcription."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import MappingProxyType

import pandas as pd
import pytest
import jsonschema
from jsonschema import Draft202012Validator, FormatChecker

import engine.capital_structure.document_terms as document_terms
from engine.capital_structure.document_terms import (
    DocumentTermCompileDegraded,
    compile_document_term_records,
    current_document_terms_as_of,
    observation_id_for,
    validate_document_term_source_authority,
    validate_document_term_history,
    validate_observation_source_binding,
)
from engine.capital_structure.source_identity import (
    ManifestIdentityError,
    manifest_id_for,
    validate_manifest_retained_bytes_binding,
)
from scripts.compile_capital_structure_document_terms import (
    DOCUMENT_TERM_COLUMNS,
    compile_from_disk,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/capital_structure/document_terms/registration_fee_table_submission.txt"
SUPPORTED_RUNTIME_EXECUTABLES = (
    pytest.param(sys.executable, id="active-reviewed-runtime"),
    pytest.param(
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
        id="cpython-3.12.2-python-org",
    ),
    pytest.param(
        "/opt/homebrew/Caskroom/miniconda/base/bin/python",
        id="cpython-3.12.4-anaconda",
    ),
    pytest.param(
        "/opt/homebrew/bin/python3.12",
        id="cpython-3.12.13-homebrew",
    ),
)


def _copy_tracked_authority_source(export_root: Path) -> None:
    export_root.mkdir()
    tracked = subprocess.check_output(
        [
            "git", "ls-files", "-z", "--", "engine", "contracts",
            "app/__init__.py", "app/capital_structure.py",
        ],
        cwd=ROOT,
    ).split(b"\0")
    for encoded in tracked:
        if not encoded:
            continue
        relative = Path(os.fsdecode(encoded))
        source = ROOT / relative
        if not source.exists():
            continue
        destination = export_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _supported_runtime_or_skip(interpreter: str) -> str:
    if not Path(interpreter).is_file() or not os.access(interpreter, os.X_OK):
        pytest.skip(f"reviewed runtime is not installed: {interpreter}")
    return interpreter


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


_FIXTURE_PRIOR_PARSER_VERSION = "test-document-terms-fixture/0.0.1"


def _fixture_prior_unavailable_parser(manifest: dict, raw: bytes | None, parser_version: str) -> list[dict]:
    """Test-only retained v1 fixture: same slots, conservative unavailable facts."""
    rows = document_terms._records_for_manifest_v1_1_0(manifest, raw, parser_version)
    for row in rows:
        row["state"] = {"disposition": "unavailable", "reason": "header_without_direct_value"}
        row["reported"] = document_terms._empty_value()
        row["normalized"] = document_terms._empty_value()
    return rows


def _fixture_prior_parser_lane() -> tuple[str, object, object]:
    """Build an explicit private capability lane for one historic fixture."""
    entrypoints = (
        *document_terms._parser_semantic_entrypoints(_fixture_prior_unavailable_parser),
        document_terms.SemanticEntrypoint(
            "fixture_base_extractor", document_terms._records_for_manifest_v1_1_0,
        ),
    )
    dispatch_roots = document_terms._parser_semantic_dispatch_roots()
    manifest, manifest_sha256, implementation_sha256 = document_terms._semantic_closure(
        entrypoints, dispatch_roots,
    )
    registration = document_terms.ParserRegistration(
        version=_FIXTURE_PRIOR_PARSER_VERSION,
        implementation_sha256=implementation_sha256,
        extractor=_fixture_prior_unavailable_parser,
        semantic_bundle=document_terms.ParserSemanticBundle(
            entrypoints=entrypoints,
            dispatch_roots=dispatch_roots,
            dependency_count=len(manifest),
            dependency_manifest_sha256=manifest_sha256,
        ),
    )
    capability = document_terms._PRIVATE_TEST_PARSER_CAPABILITY
    lane = document_terms._make_test_parser_lane(
        [registration], capability=capability,
    )
    return _FIXTURE_PRIOR_PARSER_VERSION, lane, capability


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


def test_parser_correction_is_append_only_and_keeps_each_historic_fact_source_bound():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    prior_version, lane, capability = _fixture_prior_parser_lane()
    original = document_terms._compile_document_term_records_test_lane(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
        parser_lane=lane, parser_version=prior_version, capability=capability,
    )["observations"]
    result = document_terms._compile_document_term_records_test_lane(
        [manifest], source_reader=_reader(raw), existing_observations=original,
        generated_at="2026-08-04T00:00:00Z",
        parser_lane=lane, parser_version="capital-structure-document-terms/1.1.0",
        capability=capability,
    )
    corrected = [row for row in result["observations"] if row["term"]["name"] == "registration_fee"]
    assert len(corrected) == 2
    prior, later = sorted(corrected, key=lambda row: row["version"]["correction_version"])
    assert later["version"] == {
        "immutable_record": True, "correction_version": 2, "correction_of": prior["observation_id"],
    }
    assert later["relationships"]["supersedes"] == [prior["observation_id"]]
    assert prior["extraction"]["parser_version"] == prior_version
    assert later["extraction"]["parser_version"] == "capital-structure-document-terms/1.1.0"
    assert later["reported"]["value"] == "1237.1"
    before = document_terms._current_document_terms_as_of_test_lane(
        result["observations"], "2026-08-03T12:00:00Z",
        parser_lane=lane, capability=capability,
    )
    after = document_terms._current_document_terms_as_of_test_lane(
        result["observations"], "2026-08-04T00:00:00Z",
        parser_lane=lane, capability=capability,
    )
    assert next(row for row in before if row["term"]["name"] == "registration_fee")["reported"]["value"] is None
    assert next(row for row in after if row["term"]["name"] == "registration_fee")["reported"]["value"] == "1237.1"


def test_unknown_or_phantom_parser_correction_fails_closed_against_retained_bytes():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    original = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]

    unknown = deepcopy(original)
    unknown[0]["extraction"]["parser_version"] = "forged-document-terms/99.0.0"
    unknown[0]["observation_id"] = observation_id_for(unknown[0])
    with pytest.raises(ValueError, match="parser_version is not registered"):
        validate_document_term_source_authority(
            unknown, source_manifests=[manifest], source_reader=_reader(raw),
        )

    phantom = deepcopy(original)
    prior = phantom[0]
    duplicate = deepcopy(prior)
    duplicate["version"] = {
        "immutable_record": True, "correction_version": 2,
        "correction_of": prior["observation_id"],
    }
    duplicate["relationships"]["supersedes"] = [prior["observation_id"]]
    duplicate["point_in_time"]["available_at"] = "2026-08-04T00:00:00Z"
    duplicate["observation_id"] = observation_id_for(duplicate)
    phantom.append(duplicate)
    with pytest.raises(ValueError, match="duplicates prior source semantics"):
        validate_document_term_source_authority(
            phantom, source_manifests=[manifest], source_reader=_reader(raw),
        )


@pytest.mark.parametrize(
    "target",
    [
        "_canonical_json", "_digest_id", "_clone_json_value", "_parse_time", "_iso",
        "_unique_spans", "make_stable_span", "_base_record",
        "_records_for_manifest_v1_1_0",
    ],
)
def test_registered_parser_closure_rejects_every_mutated_semantic_helper(
    monkeypatch, target,
):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    original_rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    original = getattr(document_terms, target)

    def altered_semantic_helper(*args, **kwargs):
        return original(*args, **kwargs)

    monkeypatch.setattr(document_terms, target, altered_semantic_helper)
    with pytest.raises(ValueError, match="closure mismatch"):
        compile_document_term_records(
            [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
        )
    with pytest.raises(ValueError, match="closure mismatch"):
        validate_document_term_source_authority(
            original_rows, source_manifests=[manifest], source_reader=_reader(raw),
        )


def test_registered_parser_closure_rejects_mutated_semantic_constant(monkeypatch):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    original_rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    monkeypatch.setattr(document_terms, "TERM_NAMES", (*document_terms.TERM_NAMES, "forged"))
    with pytest.raises(ValueError, match="closure mismatch"):
        compile_document_term_records(
            [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
        )
    with pytest.raises(ValueError, match="closure mismatch"):
        validate_document_term_source_authority(
            original_rows, source_manifests=[manifest], source_reader=_reader(raw),
        )


@pytest.mark.parametrize(
    ("module_name", "attribute"),
    [("hashlib", "sha256"), ("json", "dumps"), ("re", "sub")],
)
def test_registered_parser_closure_rejects_mutated_module_attribute(
    monkeypatch, module_name, attribute,
):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    original_rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    module = getattr(document_terms, module_name)
    original = getattr(module, attribute)

    def altered_module_attribute(*args, **kwargs):
        return original(*args, **kwargs)

    monkeypatch.setattr(module, attribute, altered_module_attribute)
    with pytest.raises(ValueError, match="closure mismatch"):
        compile_document_term_records(
            [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
        )
    with pytest.raises(ValueError, match="closure mismatch"):
        validate_document_term_source_authority(
            original_rows, source_manifests=[manifest], source_reader=_reader(raw),
        )


def test_released_parser_registry_has_closed_golden_semantic_bundle():
    assert tuple(document_terms._PARSER_REGISTRY) == (
        "capital-structure-document-terms/1.1.0",
    )
    registration = document_terms._PARSER_REGISTRY[
        "capital-structure-document-terms/1.1.0"
    ]
    manifest, manifest_sha256, implementation_sha256 = document_terms._semantic_closure(
        registration.semantic_bundle.entrypoints,
        registration.semantic_bundle.dispatch_roots,
    )
    assert len(manifest) == 263
    assert manifest_sha256 == (
        "4939a46ef7ca1a9583f869de398692e6a8736fc4566c6a5f3860b95c5f6e6f0d"
    )
    assert implementation_sha256 == (
        "d47515272069bfc3f3f768b84b94a218f7f66e7c746e36a8702efd97c26af645"
    )
    assert len(manifest) == registration.semantic_bundle.dependency_count
    assert manifest_sha256 == registration.semantic_bundle.dependency_manifest_sha256
    assert implementation_sha256 == registration.implementation_sha256
    runtime_manifest, runtime_manifest_sha256, runtime_implementation_sha256 = (
        document_terms._runtime_dispatch_closure(
            registration.semantic_bundle.dispatch_roots,
        )
    )
    runtime = document_terms._validate_released_parser_runtime(
        registration.semantic_bundle.dispatch_roots,
    )
    assert len(runtime_manifest) == runtime.dependency_count
    assert runtime_manifest_sha256 == runtime.dependency_manifest_sha256
    assert runtime_implementation_sha256 == runtime.implementation_sha256
    assert any("_markupbase.ParserBase.reset" in node for node in runtime_manifest)
    assert any("function:html.unescape" in node for node in runtime_manifest)
    assert any("function:html._replace_charref" in node for node in runtime_manifest)
    for required in (
        "._digest_id", "._parse_time", "._iso", "._unique_spans",
        ".make_stable_span", "._materialize_observation", ".observation_id_for",
        ".hashlib.attribute.sha256", ".json.attribute.dumps", "runtime:python",
        "html.parser.HTMLParser.feed", "html.parser.HTMLParser.close",
        "html.parser.HTMLParser.goahead", "_markupbase.ParserBase.updatepos",
        "CDATA_CONTENT_ELEMENTS",
    ):
        assert any(required in node for node in manifest), required


def test_parser_runtime_dispatch_seal_recovers_after_in_process_monkeypatch(monkeypatch):
    original_code = document_terms.HTMLParser.feed.__code__

    def altered_feed(self, data):
        return None

    with monkeypatch.context() as patch:
        patch.setattr(
            document_terms.HTMLParser.feed,
            "__code__",
            altered_feed.__code__,
        )
        with pytest.raises(ValueError, match="runtime dispatch mismatch"):
            document_terms._registered_parser(document_terms.PARSER_VERSION)

    assert document_terms.HTMLParser.feed.__code__ is original_code
    registration = document_terms._registered_parser(document_terms.PARSER_VERSION)
    assert registration.version == document_terms.PARSER_VERSION


def test_parser_runtime_html_helper_code_seal_recovers_after_mutation(monkeypatch):
    original_code = document_terms._stdlib_html.unescape.__code__

    def altered_unescape(value):
        return value

    with monkeypatch.context() as patch:
        patch.setattr(
            document_terms._stdlib_html.unescape,
            "__code__",
            altered_unescape.__code__,
        )
        with pytest.raises(ValueError, match="runtime dispatch mismatch"):
            document_terms._registered_parser(document_terms.PARSER_VERSION)

    assert document_terms._stdlib_html.unescape.__code__ is original_code
    assert (
        document_terms._registered_parser(document_terms.PARSER_VERSION).version
        == document_terms.PARSER_VERSION
    )


def test_parser_runtime_html_entity_data_seal_recovers_after_mutation(monkeypatch):
    original = document_terms._stdlib_html._html5["Aacute"]
    with monkeypatch.context() as patch:
        patch.setitem(
            document_terms._stdlib_html._html5,
            "Aacute",
            "forged character reference",
        )
        with pytest.raises(ValueError, match="runtime dispatch mismatch"):
            document_terms._registered_parser(document_terms.PARSER_VERSION)

    assert document_terms._stdlib_html._html5["Aacute"] == original
    assert (
        document_terms._registered_parser(document_terms.PARSER_VERSION).version
        == document_terms.PARSER_VERSION
    )


def test_parser_runtime_dispatch_helper_rebinding_fails_closed(monkeypatch):
    registration = document_terms._PARSER_REGISTRY[document_terms.PARSER_VERSION]
    runtime = document_terms._validate_released_parser_runtime(
        registration.semantic_bundle.dispatch_roots,
    )
    monkeypatch.setattr(
        document_terms,
        "_runtime_dispatch_closure",
        lambda _roots: (
            tuple(range(runtime.dependency_count)),
            runtime.dependency_manifest_sha256,
            runtime.implementation_sha256,
        ),
    )
    with pytest.raises(ValueError, match="runtime closure binding changed"):
        document_terms._registered_parser(document_terms.PARSER_VERSION)


def test_released_runtime_allowlist_is_closed_reviewed_and_current():
    allowlist = document_terms._PARSER_V1_1_0_RUNTIME_ALLOWLIST
    assert isinstance(allowlist, type(MappingProxyType({})))
    assert len(allowlist) == 4
    assert {
        fingerprint.version_info[:3]
        for fingerprint in allowlist
    } == {
        (3, 12, 2),
        (3, 12, 3),
        (3, 12, 4),
        (3, 12, 13),
    }
    assert all(
        tuple(path for path, _digest in fingerprint.stdlib_source_sha256)
        == (
            "_markupbase.py",
            "html/__init__.py",
            "html/entities.py",
            "html/parser.py",
            "re/__init__.py",
        )
        for fingerprint in allowlist
    )
    current = document_terms._parser_runtime_fingerprint()
    assert current in allowlist
    registration = document_terms._PARSER_REGISTRY[document_terms.PARSER_VERSION]
    assert allowlist[current] == document_terms._validate_released_parser_runtime(
        registration.semantic_bundle.dispatch_roots,
    )
    with pytest.raises(TypeError):
        allowlist[current] = allowlist[current]


def test_released_runtime_allowlist_rebinding_cannot_mint_authority(monkeypatch):
    current = document_terms._parser_runtime_fingerprint()
    forged = MappingProxyType({
        current: document_terms.ParserRuntimeBundle(
            dependency_count=0,
            dependency_manifest_sha256="0" * 64,
            implementation_sha256="0" * 64,
        ),
    })
    monkeypatch.setattr(
        document_terms, "_PARSER_V1_1_0_RUNTIME_ALLOWLIST", forged,
    )
    with pytest.raises(ValueError, match="allowlist binding changed"):
        document_terms._registered_parser(document_terms.PARSER_VERSION)


def test_parser_runtime_source_digest_change_fails_closed_and_recovers(monkeypatch):
    original_code = Path.read_bytes.__code__

    def altered_read_bytes(self):
        with self.open(mode="rb") as source:
            payload = source.read()
        if self.as_posix().endswith("/html/parser.py"):
            return payload + b"\n# ordinary on-disk source mutation probe\n"
        return payload

    with monkeypatch.context() as patch:
        patch.setattr(Path.read_bytes, "__code__", altered_read_bytes.__code__)
        with pytest.raises(ValueError, match="fingerprint is not released"):
            document_terms._registered_parser(document_terms.PARSER_VERSION)

    assert Path.read_bytes.__code__ is original_code
    assert (
        document_terms._registered_parser(document_terms.PARSER_VERSION).version
        == document_terms.PARSER_VERSION
    )


@pytest.mark.parametrize("interpreter", SUPPORTED_RUNTIME_EXECUTABLES)
def test_clean_preimport_forged_stdlib_method_imports_but_parser_fails_closed(
    tmp_path, interpreter,
):
    interpreter = _supported_runtime_or_skip(interpreter)
    export_root = tmp_path / "preimport-spoof-export"
    _copy_tracked_authority_source(export_root)
    probe = """
from html.parser import HTMLParser

original = HTMLParser.feed

def altered_feed(self, data):
    return original(self, data)

altered_feed.__module__ = "html.parser"
altered_feed.__name__ = "feed"
altered_feed.__qualname__ = "HTMLParser.feed"
HTMLParser.feed = altered_feed

import engine.capital_structure.document_terms as document_terms

try:
    document_terms._registered_parser(document_terms.PARSER_VERSION)
except ValueError as exc:
    if "runtime dispatch mismatch" not in str(exc):
        raise
    print("PREIMPORT_STDLIB_SPOOF_PARSER_REJECTED")
else:
    raise SystemExit("PREIMPORT_STDLIB_SPOOF_ACCEPTED")
"""
    result = subprocess.run(
        [interpreter, "-B", "-c", probe],
        cwd=export_root,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(export_root),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PREIMPORT_STDLIB_SPOOF_PARSER_REJECTED"
    assert "ACCEPTED" not in result.stderr
    assert not list(export_root.rglob("__pycache__"))


@pytest.mark.parametrize("interpreter", SUPPORTED_RUNTIME_EXECUTABLES)
def test_clean_preimport_forged_html_helper_imports_but_parser_fails_closed(
    tmp_path, interpreter,
):
    interpreter = _supported_runtime_or_skip(interpreter)
    export_root = tmp_path / "preimport-html-helper-export"
    _copy_tracked_authority_source(export_root)
    probe = """
import html

original = html.unescape

def altered_unescape(value):
    return original(value)

altered_unescape.__module__ = "html"
altered_unescape.__name__ = "unescape"
altered_unescape.__qualname__ = "unescape"
html.unescape = altered_unescape

import engine.capital_structure.document_terms as document_terms

try:
    document_terms._registered_parser(document_terms.PARSER_VERSION)
except ValueError as exc:
    if not any(
        message in str(exc)
        for message in ("semantic node collision", "runtime dispatch mismatch")
    ):
        raise
    print("PREIMPORT_HTML_HELPER_SPOOF_PARSER_REJECTED")
else:
    raise SystemExit("PREIMPORT_HTML_HELPER_SPOOF_ACCEPTED")
"""
    result = subprocess.run(
        [interpreter, "-B", "-c", probe],
        cwd=export_root,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(export_root),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PREIMPORT_HTML_HELPER_SPOOF_PARSER_REJECTED"
    assert "ACCEPTED" not in result.stderr
    assert not list(export_root.rglob("__pycache__"))


@pytest.mark.parametrize("interpreter", SUPPORTED_RUNTIME_EXECUTABLES)
def test_clean_unknown_interpreter_imports_router_but_parser_fails_closed(
    tmp_path, interpreter,
):
    interpreter = _supported_runtime_or_skip(interpreter)
    export_root = tmp_path / "unknown-runtime-export"
    _copy_tracked_authority_source(export_root)
    probe = """
import sys
import importlib.util

original_cache_tag = sys.implementation.cache_tag
sys.implementation.cache_tag = "unsupported-cpython-312-audit-probe"
import engine.capital_structure as capital_structure
import engine.capital_structure.document_terms as document_terms

if capital_structure.DOCUMENT_TERM_PARSER_VERSION != document_terms.PARSER_VERSION:
    raise SystemExit("UNKNOWN_RUNTIME_PACKAGE_IMPORT_MISMATCH")
router_state = "ROUTER_DEPENDENCY_ABSENT"
if importlib.util.find_spec("fastapi") is not None:
    from app.capital_structure import router
    if router is None:
        raise SystemExit("UNKNOWN_RUNTIME_ROUTER_MISSING")
    router_state = "ROUTER_OK"
try:
    document_terms._registered_parser(document_terms.PARSER_VERSION)
except ValueError as exc:
    if "runtime fingerprint is not released" not in str(exc):
        raise
    print(f"UNKNOWN_RUNTIME_IMPORT_OK_{router_state}_PARSER_REJECTED")
else:
    raise SystemExit("UNKNOWN_RUNTIME_ACCEPTED")
finally:
    sys.implementation.cache_tag = original_cache_tag
"""
    result = subprocess.run(
        [interpreter, "-B", "-c", probe],
        cwd=export_root,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(export_root),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() in {
        "UNKNOWN_RUNTIME_IMPORT_OK_ROUTER_OK_PARSER_REJECTED",
        "UNKNOWN_RUNTIME_IMPORT_OK_ROUTER_DEPENDENCY_ABSENT_PARSER_REJECTED",
    }
    assert "ACCEPTED" not in result.stderr
    assert not list(export_root.rglob("__pycache__"))


def test_cold_tracked_source_export_import_is_repeatable_without_bytecode(tmp_path):
    export_root = tmp_path / "cold-export"
    _copy_tracked_authority_source(export_root)

    command = [
        sys.executable,
        "-B",
        "-c",
        (
            "import engine.capital_structure.document_terms as d; "
            "import engine.capital_structure.instrument_candidates as c; "
            "r=d._PARSER_REGISTRY[d.PARSER_VERSION]; "
            "print(r.semantic_bundle.dependency_count, r.implementation_sha256, "
            "d._AUTHORITY_POLICY.implementation_sha256, "
            "c._CANDIDATE_AUTHORITY_IMPLEMENTATION_SHA256)"
        ),
    ]
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(export_root),
    }
    outputs = [
        subprocess.check_output(
            command, cwd=export_root, env=environment, text=True,
        ).strip()
        for _run in range(3)
    ]
    assert outputs == [outputs[0]] * 3
    assert outputs[0] == (
        "263 d47515272069bfc3f3f768b84b94a218f7f66e7c746e36a8702efd97c26af645 "
        "3650894df320e83771b1d9c0de6fd658cde50e2d7533cb958fc835837c32a18c "
        "7adefd79136224d8c0ca0c84cd4ef41bd206690f9ec28622cdf95f682c811b28"
    )
    assert not list(export_root.rglob("__pycache__"))


def test_released_authority_policy_has_independent_golden_closure():
    policy = document_terms._AUTHORITY_POLICY
    manifest, manifest_sha256, implementation_sha256 = document_terms._semantic_closure(
        policy.entrypoints,
    )
    assert len(manifest) == 421
    assert manifest_sha256 == (
        "de327cf44e5e00e5a43e36f0f26ddc4ba71d3f2ea662a93c303d9af3a46142fa"
    )
    assert implementation_sha256 == (
        "3650894df320e83771b1d9c0de6fd658cde50e2d7533cb958fc835837c32a18c"
    )
    assert len(manifest) == policy.dependency_count
    assert manifest_sha256 == policy.dependency_manifest_sha256
    assert implementation_sha256 == policy.implementation_sha256
    for required in (
        "source_identity.validate_manifest_retained_bytes_binding",
        "._validate_document_term_records_contract",
        "._assert_zero_authority",
        "._validate_observation_source_binding_core",
        "._validate_document_term_history_core",
        "._validate_document_term_source_authority_core",
    ):
        assert any(required in node for node in manifest), required
    assert document_terms._SemanticClosureBuilder()._reference(
        document_terms._DOCUMENT_TERM_SCHEMA_PATH
    ) == {
        "kind": "repo_path",
        "value": "contracts/capital_structure_document_term_observation.schema.json",
    }


@pytest.mark.parametrize(
    ("owner", "method"),
    [
        (document_terms.HTMLParser, "feed"),
        (document_terms.HTMLParser, "close"),
        (document_terms.HTMLParser, "goahead"),
        (document_terms.HTMLParser, "__new__"),
        (document_terms.HTMLParser, "__getattribute__"),
        (document_terms.HTMLParser, "__setattr__"),
        (document_terms.HTMLParser.__mro__[1], "reset"),
        (document_terms.HTMLParser.__mro__[1], "updatepos"),
        (document_terms._CellText, "handle_data"),
    ],
)
def test_parser_closure_rejects_mutated_inherited_dispatch_and_callbacks(
    monkeypatch, owner, method,
):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    original_rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    original = getattr(owner, method)

    def altered_dispatch(*args, **kwargs):
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, method, altered_dispatch)
    with pytest.raises(ValueError, match="(?:closure|runtime dispatch) mismatch"):
        compile_document_term_records(
            [manifest], source_reader=_reader(raw),
            generated_at="2026-08-03T00:00:00Z",
        )
    with pytest.raises(ValueError, match="(?:closure|runtime dispatch) mismatch"):
        validate_document_term_source_authority(
            original_rows, source_manifests=[manifest], source_reader=_reader(raw),
        )


def test_parser_closure_rejects_mutated_inherited_class_data(monkeypatch):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    original_rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    monkeypatch.setattr(
        document_terms.HTMLParser,
        "CDATA_CONTENT_ELEMENTS",
        (*document_terms.HTMLParser.CDATA_CONTENT_ELEMENTS, "audit-unused-element"),
    )
    with pytest.raises(ValueError, match="(?:closure|runtime dispatch) mismatch"):
        compile_document_term_records(
            [manifest], source_reader=_reader(raw),
            generated_at="2026-08-03T00:00:00Z",
        )
    with pytest.raises(ValueError, match="(?:closure|runtime dispatch) mismatch"):
        validate_document_term_source_authority(
            original_rows, source_manifests=[manifest], source_reader=_reader(raw),
        )


def test_post_import_self_consistent_registry_insertion_cannot_grant_authority(monkeypatch):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    released = document_terms._PARSER_REGISTRY[
        "capital-structure-document-terms/1.1.0"
    ]
    with pytest.raises(TypeError):
        document_terms._PARSER_REGISTRY["forged"] = released

    forged_version = "forged-document-terms/99.0.0"
    forged = document_terms.ParserRegistration(
        version=forged_version,
        implementation_sha256=released.implementation_sha256,
        extractor=released.extractor,
        semantic_bundle=released.semantic_bundle,
    )
    monkeypatch.setattr(
        document_terms,
        "_PARSER_REGISTRY",
        {**dict(document_terms._PARSER_REGISTRY), forged_version: forged},
    )
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    forged_rows = deepcopy(rows)
    for row in forged_rows:
        row["extraction"]["parser_version"] = forged_version
        row["observation_id"] = observation_id_for(row)

    # Rebinding both apparent release globals still cannot alter the original
    # mapping proxies captured by the production resolver.
    monkeypatch.setattr(
        document_terms,
        "_RELEASED_PARSER_REGISTRY",
        document_terms.MappingProxyType({
            **dict(document_terms._RELEASED_PARSER_REGISTRY),
            forged_version: forged,
        }),
    )
    monkeypatch.setattr(
        document_terms,
        "_RELEASED_PARSER_IMPLEMENTATION_DIGESTS",
        document_terms.MappingProxyType({
            **dict(document_terms._RELEASED_PARSER_IMPLEMENTATION_DIGESTS),
            forged_version: forged.implementation_sha256,
        }),
    )
    with pytest.raises(ValueError, match="parser_version is not registered"):
        validate_document_term_history(forged_rows)
    with pytest.raises(ValueError, match="parser_version is not registered"):
        validate_document_term_source_authority(
            forged_rows, source_manifests=[manifest], source_reader=_reader(raw),
        )


def test_public_authority_rejects_rebound_released_parser_resolver(monkeypatch):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    released = document_terms._PARSER_REGISTRY[
        "capital-structure-document-terms/1.1.0"
    ]
    forged_version = "forged-document-terms/99.0.0"
    forged = document_terms.ParserRegistration(
        version=forged_version,
        implementation_sha256=released.implementation_sha256,
        extractor=released.extractor,
        semantic_bundle=released.semantic_bundle,
    )
    forged_rows = deepcopy(rows)
    for row in forged_rows:
        row["extraction"]["parser_version"] = forged_version
        row["observation_id"] = observation_id_for(row)

    monkeypatch.setattr(document_terms, "_registered_parser", lambda _version: forged)
    with pytest.raises(ValueError, match="resolver binding changed"):
        validate_document_term_history(forged_rows)
    with pytest.raises(ValueError, match="resolver binding changed"):
        validate_document_term_source_authority(
            forged_rows, source_manifests=[manifest], source_reader=_reader(raw),
        )


def test_public_document_trust_surfaces_expose_no_injectable_trust_parameters():
    surfaces = (
        document_terms.validate_document_term_contract,
        document_terms.validate_observation_source_binding,
        document_terms.validate_document_term_source_authority,
        document_terms.validate_document_term_history,
        document_terms.current_document_terms_as_of,
        document_terms.compile_document_term_records,
    )
    forbidden = {
        "_released_parser_resolver",
        "_source_binding_core",
        "_source_authority_core",
        "_history_core",
        "_current_core",
        "_compiler_core",
    }
    for surface in surfaces:
        assert forbidden.isdisjoint(inspect.signature(surface).parameters)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        document_terms.validate_document_term_history(
            [], _released_parser_resolver=lambda _version: None,
        )


@pytest.mark.parametrize(
    ("target", "surface"),
    [
        ("_validate_observation_source_binding_core", "source_binding"),
        ("_validate_document_term_source_authority_core", "source_authority"),
        ("_validate_document_term_history_core", "history"),
        ("_current_document_terms_as_of_core", "current"),
        ("_compile_document_term_records_core", "compile"),
    ],
)
def test_public_trust_wrappers_reject_rebound_core_callables(
    monkeypatch, target, surface,
):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    monkeypatch.setattr(document_terms, target, lambda *args, **kwargs: rows)
    calls = {
        "source_binding": lambda: validate_observation_source_binding(
            rows[0], manifest, raw,
        ),
        "source_authority": lambda: validate_document_term_source_authority(
            rows, source_manifests=[manifest], source_reader=_reader(raw),
        ),
        "history": lambda: validate_document_term_history(rows),
        "current": lambda: current_document_terms_as_of(
            rows, "2026-08-04T00:00:00Z",
        ),
        "compile": lambda: compile_document_term_records(
            [manifest], source_reader=_reader(raw),
            generated_at="2026-08-03T00:00:00Z",
        ),
    }
    with pytest.raises(
        ValueError,
        match="core binding changed|closure mismatch|authority policy binding changed",
    ):
        calls[surface]()


def test_noop_retained_source_validator_cannot_bypass_sealed_authority_policy(monkeypatch):
    raw = FIXTURE.read_bytes().replace(
        b"CENTRAL INDEX KEY: 1\n", b"CENTRAL INDEX KEY: 2\n", 1,
    )
    forged_manifest = _manifest(raw)
    forged_manifest["issuer"] = {
        **forged_manifest["issuer"],
        "issuer_id": "sec:cik:0000000002",
        "cik": "2",
    }
    forged_manifest["manifest_id"] = manifest_id_for(forged_manifest)

    monkeypatch.setattr(
        document_terms,
        "validate_manifest_retained_bytes_binding",
        lambda _manifest, _raw: None,
    )
    with pytest.raises(ValueError, match="authority policy binding changed"):
        compile_document_term_records(
            [forged_manifest], source_reader=_reader(raw),
            generated_at="2026-08-03T00:00:00Z",
        )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda row: row.update({"authority": {"trade_authority": False}}), "zero-authority"),
        (lambda row: row["evidence"].update({"authority": {"rank": False}}), "zero-authority"),
        (lambda row: row.update({"unexpected_top_level": "smuggled"}), "contract violation"),
        (lambda row: row["reported"].update({"unexpected_nested": "smuggled"}), "contract violation"),
    ],
)
def test_all_direct_record_trust_paths_enforce_closed_schema_and_zero_authority(
    mutation, error,
):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    tampered = deepcopy(rows)
    mutation(tampered[0])
    tampered[0]["observation_id"] = observation_id_for(tampered[0])

    calls = (
        lambda: document_terms.validate_document_term_contract(tampered[0]),
        lambda: validate_document_term_history(tampered),
        lambda: current_document_terms_as_of(tampered, "2026-08-04T00:00:00Z"),
        lambda: validate_observation_source_binding(tampered[0], manifest, raw),
        lambda: validate_document_term_source_authority(
            tampered, source_manifests=[manifest], source_reader=_reader(raw),
        ),
    )
    for call in calls:
        with pytest.raises(ValueError, match=error):
            call()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row["filing"].update({"filing_date": "2026-02-30"}),
        lambda row: row["filing"].update(
            {"accepted_at": "2026-08-01 11:00:00"},
        ),
        lambda row: row["document"].update({"canonical_url": "not a uri"}),
    ],
)
def test_direct_contract_uses_only_pinned_strict_format_checkers(mutation):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    row = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"][0]
    mutation(row)
    row["observation_id"] = observation_id_for(row)
    with pytest.raises(ValueError, match="contract violation"):
        document_terms.validate_document_term_contract(row)


def test_ambient_optional_format_registration_does_not_pollute_release_golden(
    monkeypatch,
):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    row = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"][0]

    with monkeypatch.context() as patch:
        patch.setitem(
            FormatChecker.checkers,
            "audit-environment-only",
            (lambda _instance: True, ()),
        )
        document_terms.validate_document_term_contract(row)

    policy = document_terms._validated_authority_policy()
    assert policy is document_terms._AUTHORITY_POLICY


def test_public_admission_uses_captured_schema_validator_not_provider_alias(monkeypatch):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    tampered = deepcopy(rows)
    tampered[0]["unexpected_top_level"] = "smuggled"
    tampered[0]["observation_id"] = observation_id_for(tampered[0])

    class NoopValidator:
        @classmethod
        def check_schema(cls, schema):
            return None

        def __init__(self, *args, **kwargs):
            pass

        def iter_errors(self, record):
            return iter(())

    monkeypatch.setattr(jsonschema, "Draft202012Validator", NoopValidator)
    calls = (
        lambda: validate_document_term_history(tampered),
        lambda: current_document_terms_as_of(tampered, "2026-08-04T00:00:00Z"),
        lambda: validate_document_term_source_authority(
            tampered, source_manifests=[manifest], source_reader=_reader(raw),
        ),
    )
    for call in calls:
        with pytest.raises(ValueError, match="contract violation"):
            call()


@pytest.mark.parametrize("method_name", ["iter_errors", "descend"])
def test_public_admission_rejects_mutated_captured_validator_methods(
    monkeypatch, method_name,
):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    tampered = deepcopy(rows)
    tampered[0]["unexpected_top_level"] = "smuggled"
    tampered[0]["observation_id"] = observation_id_for(tampered[0])

    monkeypatch.setattr(
        Draft202012Validator,
        method_name,
        lambda self, instance, *args, **kwargs: iter(()),
    )
    calls = (
        lambda: validate_document_term_history(tampered),
        lambda: current_document_terms_as_of(
            tampered, "2026-08-04T00:00:00Z",
        ),
        lambda: validate_document_term_source_authority(
            tampered, source_manifests=[manifest], source_reader=_reader(raw),
        ),
    )
    for call in calls:
        with pytest.raises(ValueError, match="validator executable binding changed"):
            call()


def test_public_admission_rejects_in_place_validator_code_mutation(monkeypatch):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    tampered = deepcopy(rows)
    tampered[0]["unexpected_top_level"] = "smuggled"
    tampered[0]["observation_id"] = observation_id_for(tampered[0])

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
        match="validator executable binding changed|authority policy closure mismatch",
    ):
        validate_document_term_history(tampered)


def test_schema_validator_instance_state_is_fresh_for_every_trust_use():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    leaked = document_terms._document_term_contract_validator()
    properties = next(
        value
        for _implementation, keyword, value in leaked.__self__._validators
        if keyword == "properties"
    )
    properties["version"]["additionalProperties"] = True
    assert (
        document_terms._document_term_contract_validator().__self__
        is not leaked.__self__
    )

    tampered = deepcopy(rows)
    tampered[0]["version"]["unexpected_nested"] = "smuggled"
    tampered[0]["observation_id"] = observation_id_for(tampered[0])
    calls = (
        lambda: validate_document_term_history(tampered),
        lambda: current_document_terms_as_of(
            tampered, "2026-08-04T00:00:00Z",
        ),
        lambda: validate_observation_source_binding(tampered[0], manifest, raw),
        lambda: validate_document_term_source_authority(
            tampered, source_manifests=[manifest], source_reader=_reader(raw),
        ),
        lambda: compile_document_term_records(
            [manifest],
            source_reader=_reader(raw),
            existing_observations=tampered,
            generated_at="2026-08-04T00:00:00Z",
        ),
    )
    for call in calls:
        with pytest.raises(ValueError, match="contract violation"):
            call()


def test_public_admission_rejects_mutated_validator_helper_global(monkeypatch):
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    rows = compile_document_term_records(
        [manifest], source_reader=_reader(raw), generated_at="2026-08-03T00:00:00Z",
    )["observations"]
    tampered = deepcopy(rows)
    tampered[0]["unexpected_top_level"] = "smuggled"
    tampered[0]["observation_id"] = observation_id_for(tampered[0])

    additional_properties = Draft202012Validator.VALIDATORS[
        "additionalProperties"
    ]
    monkeypatch.setitem(
        additional_properties.__globals__,
        "find_additional_properties",
        lambda _instance, _schema: iter(()),
    )
    with pytest.raises(ValueError, match="validator executable binding changed"):
        validate_document_term_history(tampered)


def test_complete_submission_header_binds_exact_source_id_and_form():
    raw = FIXTURE.read_bytes()
    manifest = _manifest(raw)
    suffixed = deepcopy(manifest)
    suffixed["source_id"] = "0000000001-26-000001:99:evil.txt"
    suffixed["manifest_id"] = manifest_id_for(suffixed)
    with pytest.raises(ManifestIdentityError, match="source_id is detached"):
        validate_manifest_retained_bytes_binding(suffixed, raw)

    rewritten_form = deepcopy(manifest)
    rewritten_form["filing"]["form"] = "S-1"
    rewritten_form["manifest_id"] = manifest_id_for(rewritten_form)
    with pytest.raises(ManifestIdentityError, match="filing.form is detached"):
        validate_manifest_retained_bytes_binding(rewritten_form, raw)

    absent_header = raw.replace(b"<SEC-HEADER>\n", b"")
    with pytest.raises(ManifestIdentityError, match="canonical SEC-HEADER opener"):
        validate_manifest_retained_bytes_binding(_manifest(absent_header), absent_header)

    multiple_headers = raw.replace(
        b"<SEC-HEADER>\n", b"<SEC-HEADER>\n<SEC-HEADER>\n",
    )
    with pytest.raises(ManifestIdentityError, match="canonical SEC-HEADER opener"):
        validate_manifest_retained_bytes_binding(_manifest(multiple_headers), multiple_headers)

    absent = raw.replace(b"CONFORMED SUBMISSION TYPE: S-3\n", b"")
    with pytest.raises(ManifestIdentityError, match="canonical CONFORMED"):
        validate_manifest_retained_bytes_binding(_manifest(absent), absent)

    multiple = raw.replace(
        b"CONFORMED SUBMISSION TYPE: S-3\n",
        b"CONFORMED SUBMISSION TYPE: S-3\nCONFORMED SUBMISSION TYPE: S-3\n",
    )
    with pytest.raises(ManifestIdentityError, match="canonical CONFORMED"):
        validate_manifest_retained_bytes_binding(_manifest(multiple), multiple)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda raw: raw.replace(b"<SEC-DOCUMENT>", b"junk<SEC-DOCUMENT>", 1), "SEC-DOCUMENT"),
        (lambda raw: raw.replace(b"<SEC-DOCUMENT>", b"<SEC-DOCUMENT evil>", 1), "SEC-DOCUMENT"),
        (lambda raw: raw.replace(raw.splitlines(keepends=True)[0], b"", 1), "SEC-DOCUMENT"),
        (lambda raw: raw.replace(b".txt\n", b".txt.evil\n", 1), "SEC-DOCUMENT"),
        (lambda raw: raw.replace(b".txt\n", b"0.txt\n", 1), "SEC-DOCUMENT"),
        (lambda raw: raw.replace(raw.splitlines(keepends=True)[0], raw.splitlines(keepends=True)[0] * 2, 1), "SEC-DOCUMENT"),
        (lambda raw: raw.replace(raw.splitlines(keepends=True)[0], raw.splitlines(keepends=True)[0] + b"<SEC-DOCUMENT>0000000002-26-000002.txt\n", 1), "SEC-DOCUMENT"),
        (lambda raw: raw.replace(b"<SEC-HEADER>\n", b"junk<SEC-HEADER>\n", 1), "SEC-HEADER"),
        (lambda raw: raw.replace(b"<SEC-HEADER>\n", b"<SEC-HEADER>evil\n", 1), "SEC-HEADER"),
        (lambda raw: raw.replace(b"<SEC-HEADER>\n", b"<SEC-HEADER evil>\n", 1), "SEC-HEADER"),
        (lambda raw: raw.replace(b"<DOCUMENT>\n", b"junk<DOCUMENT>evil\n", 1), "DOCUMENT opener"),
        (lambda raw: raw.replace(b"<DOCUMENT>\n", b"<DOCUMENT evil>\n", 1), "DOCUMENT opener"),
        (lambda raw: raw.replace(b"<DOCUMENT>\n", b"</SEC-HEADER>evil\n<DOCUMENT>\n", 1), "SEC-HEADER closer"),
        (lambda raw: raw.replace(b"ACCESSION NUMBER: ", b"NOT ACCESSION NUMBER: ", 1), "ACCESSION NUMBER"),
        (lambda raw: raw.replace(b"ACCESSION NUMBER: 0000000001-26-000001", b"ACCESSION NUMBER: 0000000001-26-000001.evil", 1), "ACCESSION NUMBER"),
        (lambda raw: raw.replace(b"ACCESSION NUMBER: 0000000001-26-000001\n", b"", 1), "ACCESSION NUMBER"),
        (lambda raw: raw.replace(b"ACCESSION NUMBER: 0000000001-26-000001\n", b"ACCESSION NUMBER: 0000000001-26-000001\nACCESSION NUMBER: 0000000001-26-000001\n", 1), "ACCESSION NUMBER"),
        (lambda raw: raw.replace(b"ACCESSION NUMBER: 0000000001-26-000001\n", b"ACCESSION NUMBER: 0000000001-26-000001\nACCESSION NUMBER: 0000000002-26-000002\n", 1), "ACCESSION NUMBER"),
        (lambda raw: raw.replace(b"ACCESSION NUMBER: 0000000001-26-000001", b"ACCESSION NUMBER: 0000000002-26-000002", 1), "accession conflicts"),
        (lambda raw: raw.replace(b"CONFORMED SUBMISSION TYPE", b"NOT CONFORMED SUBMISSION TYPE", 1), "CONFORMED"),
        (lambda raw: raw.replace(b"CONFORMED SUBMISSION TYPE", b"CONFORMED\nSUBMISSION TYPE", 1), "CONFORMED"),
        (lambda raw: raw.replace(b"CONFORMED SUBMISSION TYPE", b"CONFORMED SUBMISSION TYPE EXTRA", 1), "CONFORMED"),
        (lambda raw: raw.replace(b"CONFORMED SUBMISSION TYPE: S-3\n", b"CONFORMED SUBMISSION TYPE: S-3\nCONFORMED SUBMISSION TYPE: S-1\n", 1), "CONFORMED"),
        (lambda raw: raw.replace(b"CENTRAL INDEX KEY", b"NOT CENTRAL INDEX KEY", 1), "CENTRAL INDEX KEY"),
        (lambda raw: raw.replace(b"CENTRAL INDEX KEY: 1", b"CENTRAL INDEX KEY: 10000000001", 1), "CENTRAL INDEX KEY"),
        (lambda raw: raw.replace(b"CENTRAL INDEX KEY: 1", b"CENTRAL INDEX KEY: 1evil", 1), "CENTRAL INDEX KEY"),
        (lambda raw: raw.replace(b"CENTRAL INDEX KEY: 1\n", b"", 1), "CENTRAL INDEX KEY"),
        (lambda raw: raw.replace(b"CENTRAL INDEX KEY: 1\n", b"CENTRAL INDEX KEY: 1\nCENTRAL INDEX KEY: 1\n", 1), "CENTRAL INDEX KEY"),
        (lambda raw: raw.replace(b"CENTRAL INDEX KEY: 1\n", b"CENTRAL INDEX KEY: 1\nCENTRAL INDEX KEY: 2\n", 1), "CENTRAL INDEX KEY"),
    ],
)
def test_complete_submission_rejects_structural_and_header_lookalikes(mutation, error):
    raw = mutation(FIXTURE.read_bytes())
    with pytest.raises(ManifestIdentityError, match=error):
        validate_manifest_retained_bytes_binding(_manifest(raw), raw)


def _move_header_before_sec_document(raw: bytes) -> bytes:
    first_line = raw.splitlines(keepends=True)[0]
    without_lines = raw.replace(first_line, b"", 1).replace(b"<SEC-HEADER>\n", b"", 1)
    return b"<SEC-HEADER>\n" + first_line + without_lines


def _move_outer_close_before_first_document(raw: bytes) -> bytes:
    without_close = raw.rsplit(b"</SEC-DOCUMENT>", 1)[0]
    return without_close.replace(
        b"<DOCUMENT>\n", b"</SEC-DOCUMENT>\n<DOCUMENT>\n", 1,
    )


def _move_child_close_before_first_document(raw: bytes) -> bytes:
    without_first_close = raw.replace(b"</DOCUMENT>\n", b"", 1)
    return without_first_close.replace(
        b"<DOCUMENT>\n", b"</DOCUMENT>\n<DOCUMENT>\n", 1,
    )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda raw: b"transport preamble\n" + raw, "canonical first line"),
        (lambda raw: raw.rsplit(b"</SEC-DOCUMENT>", 1)[0], "SEC-DOCUMENT closer"),
        (lambda raw: raw + b"\n</SEC-DOCUMENT>", "SEC-DOCUMENT closer"),
        (lambda raw: raw + b"\ntransport trailer", "must terminate"),
        (
            lambda raw: raw.replace(
                b"<SEC-HEADER>\n",
                b"<DOCUMENT>\n</DOCUMENT>\n<SEC-HEADER>\n",
                1,
            ),
            "precedes the canonical SEC header",
        ),
        (_move_header_before_sec_document, "canonical first line"),
        (_move_outer_close_before_first_document, "must terminate"),
        (lambda raw: raw.replace(b"<SEC-DOCUMENT>", b"<sec-document>", 1), "canonical SEC-DOCUMENT"),
        (lambda raw: raw.replace(b"</DOCUMENT>\n", b"", 1), "DOCUMENT closer"),
        (lambda raw: raw.replace(b"</DOCUMENT>\n", b"</DOCUMENT>\n</DOCUMENT>\n", 1), "DOCUMENT closer"),
        (_move_child_close_before_first_document, "closer precedes"),
        (lambda raw: raw.replace(b"</DOCUMENT>\n", b"</document>\n", 1), "DOCUMENT closer"),
    ],
)
def test_outer_sec_envelope_exploits_fail_before_observed_rows_can_compile(
    mutation, error,
):
    raw = mutation(FIXTURE.read_bytes())
    manifest = _manifest(raw)
    with pytest.raises(ManifestIdentityError, match=error):
        validate_manifest_retained_bytes_binding(manifest, raw)
    with pytest.raises(DocumentTermCompileDegraded) as exc_info:
        compile_document_term_records(
            [manifest], source_reader=_reader(raw),
            generated_at="2026-08-03T00:00:00Z",
        )
    assert len(exc_info.value.failures) == 1
    assert exc_info.value.failures[0]["state"] == "source_identity_detached"
    assert error in exc_info.value.failures[0]["errors"][0]


def test_complete_submission_form_normalization_preserves_amendment_status():
    raw = FIXTURE.read_bytes().replace(
        b"CONFORMED SUBMISSION TYPE: S-3", b"CONFORMED SUBMISSION TYPE: s-3/a",
    )
    amended = _manifest(raw, form="S-3/A")
    validate_manifest_retained_bytes_binding(amended, raw)
    base_form = _manifest(raw, form="S-3")
    with pytest.raises(ManifestIdentityError, match="filing.form is detached"):
        validate_manifest_retained_bytes_binding(base_form, raw)


def test_complete_submission_accepts_crlf_tabs_and_exact_amendment_form():
    raw = FIXTURE.read_bytes().replace(
        b"CONFORMED SUBMISSION TYPE: S-3",
        b"\tCONFORMED\tSUBMISSION\tTYPE :\ts-3/a\t",
    ).replace(b"CENTRAL INDEX KEY: 1", b"\tCENTRAL\tINDEX\tKEY :\t1\t")
    raw = raw.replace(
        b"ACCESSION NUMBER: 0000000001-26-000001",
        b"\tACCESSION\tNUMBER :\t0000000001-26-000001\t",
    ).replace(b"\n", b"\r\n")
    validate_manifest_retained_bytes_binding(_manifest(raw, form="S-3/A"), raw)

    closed = raw.replace(b"<DOCUMENT>\r\n", b"</SEC-HEADER>\r\n<DOCUMENT>\r\n", 1)
    validate_manifest_retained_bytes_binding(_manifest(closed, form="S-3/A"), closed)

    dated = raw.replace(b".txt\r\n", b".txt : 20260802\r\n", 1)
    validate_manifest_retained_bytes_binding(_manifest(dated, form="S-3/A"), dated)


@pytest.mark.parametrize("form", ["S-3/AJUNK", "S-3 EVIL"])
def test_complete_submission_rejects_form_suffix_junk(form):
    raw = FIXTURE.read_bytes().replace(b"TYPE: S-3", f"TYPE: {form}".encode("ascii"), 1)
    with pytest.raises(ManifestIdentityError, match="form is malformed"):
        validate_manifest_retained_bytes_binding(_manifest(raw, form=form), raw)


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
    research_raw = (
        raw.replace(b"0000000001-26-000001", b"0000000002-26-000002")
        .replace(b"CENTRAL INDEX KEY: 1", b"CENTRAL INDEX KEY: 2")
    )
    research = _manifest(research_raw)
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
            objects = {
                shared["storage"]["object_key"]: raw,
                research["storage"]["object_key"]: research_raw,
            }
            expected = {
                shared["storage"]["object_key"]: shared["document"]["content_sha256"],
                research["storage"]["object_key"]: research["document"]["content_sha256"],
            }
            assert expected_sha256 == expected[object_key]
            return objects[object_key]

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
        b"<SEC-DOCUMENT>0000000001-26-000001.txt\n<SEC-HEADER>\n"
        b"CONFORMED SUBMISSION TYPE: S-3\nCENTRAL INDEX KEY: 1\n"
        b"ACCESSION NUMBER: 0000000001-26-000001\n<DOCUMENT>\n" + primary
        + b"</DOCUMENT>\n<DOCUMENT>\n" + fee_child + b"</DOCUMENT>\n</SEC-DOCUMENT>"
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
    correction["extraction"]["parser_version"] = "capital-structure-document-terms/1.1.0"
    correction["observation_id"] = observation_id_for(correction)
    with pytest.raises(ValueError, match="non-empty|supersedes does not point to prior"):
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
