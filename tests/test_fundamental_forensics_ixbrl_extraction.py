"""Contract tests for receipt-bound immutable iXBRL extraction wrappers."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from engine.fundamental_forensics.filing_package import FilingPackage, build_filing_package
from engine.fundamental_forensics.ixbrl_extraction import (
    FFXBRL_LIMITS,
    FFXBRL_SCHEMA,
    IxbrlExtraction,
    IxbrlExtractionError,
    build_ixbrl_extraction,
    ixbrl_extraction_json_bytes,
    ixbrl_extraction_from_json_bytes,
    ixbrl_extraction_id_for,
    verify_ixbrl_extraction_source,
)
from engine.fundamental_forensics.models import stable_id
from engine.fundamental_forensics.sec_document_spine import (
    archive_index_url,
    build_filing_manifests,
)


STAMP = "2026-08-02T12:00:00.000000Z"
CONTENT = b"<html xmlns='http://www.w3.org/1999/xhtml'><body>fixture</body></html>"
PARSER_SCHEMA = "fundamental_forensics.sec_filing_parser/v1"
PARSER_PROFILE = "strict_offline_ixbrl/v1"
PARSER_VERSION = "1"
PARSER_FINGERPRINT = sha256(b"fixture parser algorithm/v1").hexdigest()
PARSER_TRANSFORMS = {
    "{http://www.xbrl.org/inlineXBRL/transformation/2015-02-26}numdotdecimal": "numeric"
}
PARSER_LIMITS = {
    "max_contexts": FFXBRL_LIMITS["max_contexts"],
    "max_units": FFXBRL_LIMITS["max_units"],
    "max_continuations": FFXBRL_LIMITS["max_continuations"],
    "max_facts": FFXBRL_LIMITS["max_facts"],
    "max_continuation_chain": FFXBRL_LIMITS["max_continuation_chain"],
    "max_output_bytes": FFXBRL_LIMITS["max_parser_output_bytes"],
}


class _ExplodingMapping(Mapping):
    """A Mapping whose first iteration attempt fails outside our domain error."""

    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def items(self):
        raise RuntimeError("untrusted mapping exploded")


class _InfiniteMapping(Mapping):
    """A deliberately unbounded object stream for public-boundary tests."""

    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def items(self):
        def entries():
            index = 0
            while True:
                yield (f"unbounded_{index}", None)
                index += 1

        return entries()


class _HostileFilingPackageSubclass(FilingPackage):
    def to_dict(self):
        raise RuntimeError("subclass to_dict must not be dispatched")


class _HostileIxbrlExtractionSubclass(IxbrlExtraction):
    def to_dict(self):
        raise RuntimeError("subclass to_dict must not be dispatched")

    def to_json_bytes(self):
        raise RuntimeError("subclass to_json_bytes must not be dispatched")


def _forged_nominal(cls, record):
    instance = object.__new__(cls)
    object.__setattr__(instance, "_record", record)
    return instance


def _receipt(document_id: str, archive_url: str, content: bytes) -> dict:
    digest = sha256(content).hexdigest()
    body = {
        "schema": "fundamental_forensics.sec_archive_receipt/v1",
        "status": "retrieved",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": STAMP,
        "content_sha256": digest,
        "byte_length": len(content),
        "storage_key": f"objects/sha256/{digest[:2]}/{digest}.bin.gz",
        "http_etag": None,
        "http_last_modified": None,
    }
    return {"receipt_id": stable_id("sec_archive_receipt", body), **body}


def _package(content: bytes = CONTENT) -> FilingPackage:
    manifest = build_filing_manifests(
        {
            "cik": "1",
            "name": "Fixture Holdings",
            "filings": {
                "recent": {
                    "accessionNumber": ["0000000001-26-000001"],
                    "form": ["10-K"],
                    "filingDate": ["2026-02-20"],
                    "reportDate": ["2025-12-31"],
                    "acceptanceDateTime": ["2026-02-20T16:00:00Z"],
                    "primaryDocument": ["annual.htm"],
                }
            },
        },
        recorded_at=STAMP,
    )[0]
    cik = manifest["issuer"]["cik"]
    accession = manifest["filing"]["accession"]
    index_payload = {"directory": {"item": [{"name": "annual.htm"}, {"name": "notes.txt"}]}}
    index_content = json.dumps(index_payload, indent=2).encode("utf-8")
    index_id = stable_id("sec_document", cik, accession, "archive", "index.json")
    index_url = archive_index_url(cik, accession)
    index_receipt = _receipt(index_id, index_url, index_content)
    index_document = {
        "document_id": index_id,
        "document_name": "index.json",
        "document_type": None,
        "sequence": None,
        "role": "archive",
        "archive_url": index_url,
        "availability": "stored",
        "content_sha256": index_receipt["content_sha256"],
        "byte_length": index_receipt["byte_length"],
        "storage_key": index_receipt["storage_key"],
        "retrieval": index_receipt,
        "source_spans": [
            {
                "span_id": stable_id(
                    "sec_span",
                    index_id,
                    f"bytes:0-{len(index_content)}",
                    index_receipt["content_sha256"],
                ),
                "locator_type": "byte_range",
                "locator": f"bytes:0-{len(index_content)}",
                "text_sha256": index_receipt["content_sha256"],
            }
        ],
    }
    primary = manifest["documents"][0]
    receipt = _receipt(primary["document_id"], primary["archive_url"], content)
    return build_filing_package(
        manifest,
        index_document,
        index_content,
        {
            "annual.htm": {
                "state": "stored",
                "content_sha256": receipt["content_sha256"],
                "byte_length": receipt["byte_length"],
                "storage_key": receipt["storage_key"],
                "retrieval": receipt,
                "policy_reason": None,
            },
            "notes.txt": "not_requested",
        },
        assembled_at="2026-08-02T13:00:00Z",
        policy_profile="fixture",
        policy_version="v1",
    )


def _parser_output(content: bytes, document_name: str, *, status: str = "available") -> dict:
    return {
        "schema": PARSER_SCHEMA,
        "parser": {
            "profile": PARSER_PROFILE,
            "version": PARSER_VERSION,
            "algorithm_fingerprint": PARSER_FINGERPRINT,
            "library": "lxml",
            "library_version": "fixture",
            "xml_library_version": "fixture",
            "transform_registry": [
                {"qname": qname, "kind": kind} for qname, kind in sorted(PARSER_TRANSFORMS.items())
            ],
        },
        "source": {
            "document_name": document_name,
            "content_sha256": sha256(content).hexdigest(),
            "byte_length": len(content),
        },
        "document": {
            "kind": "inline_xbrl",
            "root_qname": "{http://www.w3.org/1999/xhtml}html",
            "root_lexical_name": "html",
        },
        "contexts": [{"context_id": "c1", "source_span": {"start": 0, "end": 1}}],
        "units": [{"unit_id": "usd", "source_span": {"start": 2, "end": 3}}],
        "continuations": [
            {
                "continuation_id": "cont1",
                "continued_at": None,
                "source_span": {"start": 4, "end": 5},
            }
        ],
        "facts": [
            {
                "fact_id": "fact1",
                "status": status,
                "normalized_value": "78000000" if status == "available" else None,
                "source_span": {"start": 6, "end": 7},
                "continuation_chain": ["cont1"],
            },
            {
                "fact_id": "fact2",
                "status": "unsupported_transform",
                "normalized_value": None,
                "source_span": {"start": 8, "end": 9},
                "continuation_chain": [],
            },
        ],
        "diagnostics": [{"code": "unsupported_transform"}],
        "coverage": {"fact_inventory_complete": True, "canonical_value_complete": False},
    }


@pytest.fixture
def install_parser(monkeypatch):
    def install(*, output=None, reject: bool = False, validator=None, parser_limits=None):
        module = ModuleType("collectors.sec_filing_parser")

        class SecFilingParseError(ValueError):
            pass

        def parse(content: bytes, *, document_name: str) -> dict:
            if reject:
                raise SecFilingParseError("unsafe XML")
            return deepcopy(output if output is not None else _parser_output(content, document_name))

        module.SecFilingParseError = SecFilingParseError
        module.SEC_FILING_PARSER_SCHEMA = PARSER_SCHEMA
        module.SEC_FILING_PARSER_PROFILE = PARSER_PROFILE
        module.SEC_FILING_PARSER_VERSION = PARSER_VERSION
        module.SEC_FILING_PARSER_ALGORITHM_FINGERPRINT = PARSER_FINGERPRINT
        module.PARSER_LIMITS = dict(PARSER_LIMITS if parser_limits is None else parser_limits)
        module.SUPPORTED_TRANSFORMS = dict(PARSER_TRANSFORMS)
        module.parse_sec_filing_document = parse
        module.validate_sec_filing_parse_result = validator or (lambda value, *, source_content=None: value)
        monkeypatch.setitem(sys.modules, "collectors.sec_filing_parser", module)
        return SecFilingParseError

    return install


def test_build_binds_exact_stored_member_and_preserves_parser_fact_statuses(install_parser):
    install_parser()
    package = _package()
    extraction = build_ixbrl_extraction(
        package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    record = extraction.to_dict()

    assert record["schema"] == FFXBRL_SCHEMA
    assert extraction.extraction_id.startswith("ffxbrl_")
    assert record["source"]["package_id"] == package.package_id
    assert record["source"]["member"]["content_sha256"] == sha256(CONTENT).hexdigest()
    assert record["parser"]["profile"] == PARSER_PROFILE
    assert record["facts"][0]["normalized_value"] == "78000000"
    assert record["facts"][1]["status"] == "unsupported_transform"
    assert record["facts"][1]["normalized_value"] is None
    assert record["contexts"][0]["ffxbrl_context_id"].startswith("ffxbrl_context_")
    assert record["units"][0]["ffxbrl_unit_id"].startswith("ffxbrl_unit_")
    assert record["continuations"][0]["ffxbrl_continuation_id"].startswith(
        "ffxbrl_continuation_"
    )
    assert record["facts"][0]["ffxbrl_fact_id"].startswith("ffxbrl_fact_")
    assert record["facts"][0]["ffxbrl_span_id"].startswith("ffxbrl_span_")
    assert record["continuations"][0]["ffxbrl_continued_at_ref_id"] is None
    assert record["facts"][0]["ffxbrl_continuation_ref_ids"] == [
        record["continuations"][0]["ffxbrl_continuation_id"]
    ]
    assert record["coverage"]["parser_context_count"] == 1
    assert record["coverage"]["parser_fact_count"] == 2
    assert record["coverage"]["parser_coverage"]["canonical_value_complete"] is False
    assert record["nonclaims"]["xbrl_semantic_attested"] is False
    assert record["nonclaims"]["wrapper_network_accessed"] is False


def test_rejects_unstored_unknown_or_byte_mismatched_member_before_parser(install_parser):
    install_parser()
    package = _package()

    with pytest.raises(IxbrlExtractionError, match="not a stored"):
        build_ixbrl_extraction(package, "notes.txt", b"ignored", computed_at="2026-08-02T14:00:00Z")
    with pytest.raises(IxbrlExtractionError, match="not present"):
        build_ixbrl_extraction(package, "invented.htm", CONTENT, computed_at="2026-08-02T14:00:00Z")
    with pytest.raises(IxbrlExtractionError, match="do not match"):
        build_ixbrl_extraction(package, "annual.htm", CONTENT + b"x", computed_at="2026-08-02T14:00:00Z")


def test_parser_source_schema_and_fixed_metadata_must_bind_member_bytes(install_parser):
    bad_source = _parser_output(CONTENT, "annual.htm")
    bad_source["source"]["content_sha256"] = "0" * 64
    install_parser(output=bad_source)

    with pytest.raises(IxbrlExtractionError, match="does not bind"):
        build_ixbrl_extraction(_package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z")

    bad_schema = _parser_output(CONTENT, "annual.htm")
    bad_schema["schema"] = "forged/v1"
    install_parser(output=bad_schema)
    with pytest.raises(IxbrlExtractionError, match="schema"):
        build_ixbrl_extraction(_package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z")

    bad_profile = _parser_output(CONTENT, "annual.htm")
    bad_profile["parser"]["profile"] = "forged"
    install_parser(output=bad_profile)
    with pytest.raises(IxbrlExtractionError, match="profile"):
        build_ixbrl_extraction(_package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z")


def test_immutable_restore_canonical_json_and_forged_identity_fail_closed(install_parser):
    install_parser()
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    content = extraction.to_json_bytes()
    restored = ixbrl_extraction_from_json_bytes(content)

    assert restored.to_json_bytes() == content
    with pytest.raises(TypeError):
        extraction.manifest["coverage"]["filing_complete"] = True
    with pytest.raises(IxbrlExtractionError, match="canonically"):
        ixbrl_extraction_from_json_bytes(b" " + content)
    duplicate = content.replace(b'{"contexts"', b'{"schema":"forged","contexts"', 1)
    with pytest.raises(IxbrlExtractionError, match="duplicate"):
        ixbrl_extraction_from_json_bytes(duplicate)

    forged = extraction.to_dict()
    forged["facts"][0]["normalized_value"] = "0"
    with pytest.raises(IxbrlExtractionError, match="identity mismatch"):
        IxbrlExtraction.from_dict(forged)


def test_source_replay_is_mandatory_and_detects_a_recomputed_forgery(install_parser):
    install_parser()
    package = _package()
    extraction = build_ixbrl_extraction(
        package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    verify_ixbrl_extraction_source(extraction, package, CONTENT)

    forged = extraction.to_dict()
    forged["facts"][0]["normalized_value"] = "0"
    forged["extraction_id"] = ixbrl_extraction_id_for(forged)
    forged_result = IxbrlExtraction.from_dict(forged)
    with pytest.raises(IxbrlExtractionError, match="does not reproduce"):
        verify_ixbrl_extraction_source(forged_result, package, CONTENT)
    with pytest.raises(IxbrlExtractionError, match="do not match"):
        verify_ixbrl_extraction_source(extraction, package, CONTENT + b"x")


def test_computed_clock_and_parser_rejections_fail_closed(install_parser):
    install_parser()
    package = _package()
    with pytest.raises(IxbrlExtractionError, match="cannot predate"):
        build_ixbrl_extraction(package, "annual.htm", CONTENT, computed_at="2026-08-02T11:59:59Z")
    with pytest.raises(IxbrlExtractionError, match="package assembly"):
        build_ixbrl_extraction(package, "annual.htm", CONTENT, computed_at="2026-08-02T12:59:59Z")

    install_parser(reject=True)
    with pytest.raises(IxbrlExtractionError, match="parser rejected"):
        build_ixbrl_extraction(package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z")


def test_parser_output_arrays_and_derived_coverage_cannot_be_forged(install_parser):
    bad_array = _parser_output(CONTENT, "annual.htm")
    bad_array["facts"] = {"not": "an array"}
    install_parser(output=bad_array)
    with pytest.raises(IxbrlExtractionError, match="facts must be a bounded array"):
        build_ixbrl_extraction(_package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z")

    install_parser()
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    forged = extraction.to_dict()
    forged["coverage"]["parser_fact_count"] = 99
    forged["extraction_id"] = ixbrl_extraction_id_for(forged)
    with pytest.raises(IxbrlExtractionError, match="coverage"):
        IxbrlExtraction.from_dict(forged)


def test_children_require_exact_source_spans_and_canonical_byte_order(install_parser):
    missing_span = _parser_output(CONTENT, "annual.htm")
    del missing_span["facts"][0]["source_span"]
    install_parser(output=missing_span)
    with pytest.raises(IxbrlExtractionError, match="source_span"):
        build_ixbrl_extraction(
            _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )

    reordered = _parser_output(CONTENT, "annual.htm")
    reordered["facts"].reverse()
    install_parser(output=reordered)
    with pytest.raises(IxbrlExtractionError, match="canonical source-span order"):
        build_ixbrl_extraction(
            _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )

    null_fact_ids = _parser_output(CONTENT, "annual.htm")
    null_fact_ids["facts"][0]["fact_id"] = None
    null_fact_ids["facts"][1]["fact_id"] = None
    install_parser(output=null_fact_ids)
    first = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    second = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.to_dict()["facts"][0]["ffxbrl_fact_id"] != first.to_dict()["facts"][1]["ffxbrl_fact_id"]


def test_continuation_outer_references_are_derived_and_fail_closed(install_parser):
    output = _parser_output(CONTENT, "annual.htm")
    output["continuations"].append(
        {
            "continuation_id": "cont2",
            "continued_at": None,
            "source_span": {"start": 5, "end": 6},
        }
    )
    output["continuations"][0]["continued_at"] = "cont2"
    output["facts"][0]["continuation_chain"] = ["cont1", "cont2"]
    install_parser(output=output)
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    record = extraction.to_dict()
    first_continuation = record["continuations"][0]
    second_continuation = record["continuations"][1]
    assert first_continuation["ffxbrl_continued_at_ref_id"] == second_continuation[
        "ffxbrl_continuation_id"
    ]
    assert record["facts"][0]["ffxbrl_continuation_ref_ids"] == [
        first_continuation["ffxbrl_continuation_id"],
        second_continuation["ffxbrl_continuation_id"],
    ]

    tampered_next = extraction.to_dict()
    tampered_next["continuations"][0]["ffxbrl_continued_at_ref_id"] = None
    tampered_next["extraction_id"] = ixbrl_extraction_id_for(tampered_next)
    with pytest.raises(IxbrlExtractionError, match="continued_at"):
        IxbrlExtraction.from_dict(tampered_next)

    tampered_chain = extraction.to_dict()
    tampered_chain["facts"][0]["ffxbrl_continuation_ref_ids"] = []
    tampered_chain["extraction_id"] = ixbrl_extraction_id_for(tampered_chain)
    with pytest.raises(IxbrlExtractionError, match="continuation_chain"):
        IxbrlExtraction.from_dict(tampered_chain)

    missing_next = _parser_output(CONTENT, "annual.htm")
    del missing_next["continuations"][0]["continued_at"]
    install_parser(output=missing_next)
    with pytest.raises(IxbrlExtractionError, match="continued_at is required"):
        build_ixbrl_extraction(
            _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )

    unknown_next = _parser_output(CONTENT, "annual.htm")
    unknown_next["continuations"][0]["continued_at"] = "missing"
    install_parser(output=unknown_next)
    with pytest.raises(IxbrlExtractionError, match="unknown continuation"):
        build_ixbrl_extraction(
            _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )

    unknown_chain = _parser_output(CONTENT, "annual.htm")
    unknown_chain["facts"][0]["continuation_chain"] = ["missing"]
    install_parser(output=unknown_chain)
    with pytest.raises(IxbrlExtractionError, match="unknown continuation"):
        build_ixbrl_extraction(
            _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )


def test_package_bound_child_ids_and_parser_restore_validation_detect_forgery(install_parser):
    calls: list[dict] = []

    def validator(value: dict, *, source_content: bytes | None = None) -> None:
        calls.append(value)
        if source_content is not None:
            assert source_content == CONTENT
        if value["facts"][0]["normalized_value"] == "0":
            raise ValueError("forged parser fact")

    install_parser(validator=validator)
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    assert calls
    calls.clear()

    tampered_span = extraction.to_dict()
    tampered_span["facts"][0]["ffxbrl_span_id"] = "ffxbrl_span_" + "0" * 64
    tampered_span["extraction_id"] = ixbrl_extraction_id_for(tampered_span)
    with pytest.raises(IxbrlExtractionError, match="outer identity"):
        IxbrlExtraction.from_dict(tampered_span)

    tampered_fact = extraction.to_dict()
    tampered_fact["facts"][0]["normalized_value"] = "0"
    tampered_fact["extraction_id"] = ixbrl_extraction_id_for(tampered_fact)
    with pytest.raises(IxbrlExtractionError, match="embedded strict parser result"):
        IxbrlExtraction.from_dict(tampered_fact)


@pytest.mark.parametrize(
    ("location", "mutate"),
    [
        ("fact", lambda output: output["facts"][0].update({"ffxbrl_context_id": "forged"})),
        ("context", lambda output: output["contexts"][0].update({"ffxbrl_fact_id": "forged"})),
        ("diagnostic", lambda output: output["diagnostics"][0].update({"ffxbrl_fact_id": "forged"})),
        ("document", lambda output: output["document"].update({"ffxbrl_fact_id": "forged"})),
        ("coverage", lambda output: output["coverage"].update({"ffxbrl_fact_id": "forged"})),
    ],
)
def test_parser_cannot_inject_wrapper_reserved_ids(install_parser, location, mutate):
    output = _parser_output(CONTENT, "annual.htm")
    mutate(output)
    install_parser(output=output)

    with pytest.raises(IxbrlExtractionError, match="reserved wrapper field"):
        build_ixbrl_extraction(
            _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )


def test_restore_allows_only_derived_reserved_ids(install_parser):
    install_parser()
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )

    forged_fact_reference = extraction.to_dict()
    forged_fact_reference["facts"][0]["ffxbrl_context_id"] = "ffxbrl_context_" + "0" * 64
    forged_fact_reference["extraction_id"] = ixbrl_extraction_id_for(forged_fact_reference)
    with pytest.raises(IxbrlExtractionError, match="no matching parser local ID"):
        IxbrlExtraction.from_dict(forged_fact_reference)

    forged_cross_kind = extraction.to_dict()
    forged_cross_kind["contexts"][0]["ffxbrl_fact_id"] = "ffxbrl_fact_" + "0" * 64
    forged_cross_kind["extraction_id"] = ixbrl_extraction_id_for(forged_cross_kind)
    with pytest.raises(IxbrlExtractionError, match="reserved wrapper field"):
        IxbrlExtraction.from_dict(forged_cross_kind)


def test_hostile_nominal_instances_are_rehydrated_at_public_boundaries(install_parser):
    install_parser()
    package = _package()
    forged_package_record = package.to_dict()
    forged_package_record["package_id"] = "ffpkg_" + "0" * 64
    hostile_package = object.__new__(FilingPackage)
    object.__setattr__(hostile_package, "_record", forged_package_record)
    with pytest.raises(IxbrlExtractionError, match="invalid filing package"):
        build_ixbrl_extraction(
            hostile_package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )

    extraction = build_ixbrl_extraction(
        package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    forged_extraction_record = extraction.to_dict()
    forged_extraction_record["extraction_id"] = "ffxbrl_" + "0" * 64
    hostile_extraction = object.__new__(IxbrlExtraction)
    object.__setattr__(hostile_extraction, "_record", forged_extraction_record)
    with pytest.raises(IxbrlExtractionError, match="identity mismatch"):
        verify_ixbrl_extraction_source(hostile_extraction, package, CONTENT)


def test_public_nominal_boundaries_never_dispatch_hostile_methods(install_parser, monkeypatch):
    """Forged records and subclasses must fail in the owning domain, bounded."""
    import engine.fundamental_forensics.ixbrl_extraction as ixbrl_module

    install_parser()
    package = _package()
    extraction = build_ixbrl_extraction(
        package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )

    # Keep an infinite top-level mapping test microscopic: normalisation must
    # exhaust the JSON-node budget before it can traverse arbitrary entries.
    exact_exploding_package = _forged_nominal(FilingPackage, _ExplodingMapping())
    with pytest.raises(IxbrlExtractionError, match="invalid filing package"):
        build_ixbrl_extraction(
            exact_exploding_package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )

    subclass_infinite_package = _forged_nominal(_HostileFilingPackageSubclass, _InfiniteMapping())
    with pytest.raises(IxbrlExtractionError, match="invalid filing package subclass"):
        build_ixbrl_extraction(
            subclass_infinite_package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )

    # The forged nominal values below must never reach their overriding
    # serialization code.
    exact_infinite_extraction = _forged_nominal(IxbrlExtraction, _InfiniteMapping())
    with monkeypatch.context() as bounded:
        bounded.setattr(ixbrl_module, "HARD_MAX_JSON_NODES", 8)
        with pytest.raises(IxbrlExtractionError, match="node safety limit"):
            verify_ixbrl_extraction_source(exact_infinite_extraction, package, CONTENT)

    subclass_exploding_extraction = _forged_nominal(
        _HostileIxbrlExtractionSubclass, _ExplodingMapping()
    )
    with pytest.raises(IxbrlExtractionError, match="invalid ixbrl extraction subclass"):
        verify_ixbrl_extraction_source(subclass_exploding_extraction, package, CONTENT)

    exact_exploding_extraction = _forged_nominal(IxbrlExtraction, _ExplodingMapping())
    with pytest.raises(IxbrlExtractionError, match="cannot be iterated"):
        ixbrl_extraction_json_bytes(exact_exploding_extraction)

    subclass_infinite_extraction = _forged_nominal(
        _HostileIxbrlExtractionSubclass, _InfiniteMapping()
    )
    with pytest.raises(IxbrlExtractionError, match="invalid ixbrl extraction subclass"):
        ixbrl_extraction_json_bytes(subclass_infinite_extraction)

    # The legitimate immutable remains accepted after every rehydration path.
    assert ixbrl_extraction_json_bytes(extraction) == extraction.to_json_bytes()


def test_restore_enforces_one_aggregate_json_node_budget(install_parser, monkeypatch):
    import engine.fundamental_forensics.ixbrl_extraction as ixbrl_module

    install_parser()
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_NODES", 1_000)
    forged = extraction.to_dict()
    # Each component remains under the local cap.  Together, object keys,
    # values, and containers exceed it and must fail before derived-field checks.
    forged["diagnostics"] = [{"code": "fixture"} for _ in range(250)]
    forged["coverage"]["parser_coverage"] = {
        f"fixture_{index}": True for index in range(250)
    }
    forged["coverage"]["parser_diagnostic_count"] = 250
    forged["extraction_id"] = ixbrl_extraction_id_for(forged)
    with pytest.raises(IxbrlExtractionError, match="node safety limit"):
        IxbrlExtraction.from_dict(forged)


def test_restore_rejects_non_json_native_parser_data(install_parser):
    install_parser()
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    record = extraction.to_dict()
    record["diagnostics"] = [{"code": float("nan")}]
    with pytest.raises(IxbrlExtractionError, match="binary floats"):
        IxbrlExtraction.from_dict(record)


def test_parser_admission_envelope_and_non_xbrl_documents_fail_closed(install_parser):
    wider_limits = dict(PARSER_LIMITS)
    wider_limits["max_facts"] += 1
    install_parser(parser_limits=wider_limits)
    with pytest.raises(IxbrlExtractionError, match="admission envelope"):
        build_ixbrl_extraction(
            _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )

    other_xml = _parser_output(CONTENT, "annual.htm")
    other_xml["document"]["kind"] = "other_xml"
    install_parser(output=other_xml)
    with pytest.raises(IxbrlExtractionError, match="document kind"):
        build_ixbrl_extraction(
            _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
        )


def test_restore_uses_semantic_parser_contract_not_runtime_library_observation(install_parser):
    install_parser()
    package = _package()
    extraction = build_ixbrl_extraction(
        package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )

    runtime_drift = extraction.to_dict()
    runtime_drift["parser"].update(
        {
            "library": "stdlib.xml.parsers.expat",
            "library_version": "python-9.9.9",
            "xml_library_version": "expat-9.9.9",
        }
    )
    runtime_drift["extraction_id"] = ixbrl_extraction_id_for(runtime_drift)
    restored = IxbrlExtraction.from_dict(runtime_drift)
    assert restored.to_dict()["parser"]["library"] == "stdlib.xml.parsers.expat"
    # The immutable artifact retains its observed runtime provenance and gets a
    # distinct ID.  Exact-byte replay would falsely reject it after a harmless
    # Python/Expat patch; semantic replay deliberately strips only those fields.
    verify_ixbrl_extraction_source(restored, package, CONTENT)

    semantic_drift = extraction.to_dict()
    semantic_drift["parser"]["algorithm_fingerprint"] = "0" * 64
    semantic_drift["extraction_id"] = ixbrl_extraction_id_for(semantic_drift)
    with pytest.raises(IxbrlExtractionError, match="parser contract"):
        IxbrlExtraction.from_dict(semantic_drift)

    changed_fact = extraction.to_dict()
    changed_fact["facts"][0]["normalized_value"] = "0"
    changed_fact["extraction_id"] = ixbrl_extraction_id_for(changed_fact)
    with pytest.raises(IxbrlExtractionError, match="does not reproduce"):
        verify_ixbrl_extraction_source(
            IxbrlExtraction.from_dict(changed_fact), package, CONTENT
        )


def test_json_restore_preflight_bounds_hostile_syntax_before_decoder(monkeypatch, install_parser):
    # Keep the regression compact while exercising the same lexical gate used
    # at the production cap.  It is intentionally called before json.loads.
    import engine.fundamental_forensics.ixbrl_extraction as ixbrl_module

    install_parser()
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_NODES", 32)
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_TOKENS", 40)
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_SCALARS", 40)
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_OBJECT_KEYS", 16)
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_DEPTH", 8)
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_STRING_TOKEN_BYTES", 32)
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_DECODED_STRING_BYTES", 48)
    monkeypatch.setattr(ixbrl_module, "HARD_MAX_JSON_NUMBER_TOKEN_BYTES", 8)

    with pytest.raises(IxbrlExtractionError, match="node safety limit"):
        ixbrl_extraction_from_json_bytes(b"[" + b"0," * 40 + b"0]")
    with pytest.raises(IxbrlExtractionError, match="nesting safety limit"):
        ixbrl_extraction_from_json_bytes(b"[" * 9 + b"0" + b"]" * 9)
    with pytest.raises(IxbrlExtractionError, match="string token safety limit"):
        ixbrl_extraction_from_json_bytes(b'{"x":"' + b"a" * 33 + b'"}')
    with pytest.raises(IxbrlExtractionError, match="number token safety limit"):
        ixbrl_extraction_from_json_bytes(b'{"x":' + b"1" * 9 + b"}")
    with pytest.raises(IxbrlExtractionError, match="non-finite JSON constant"):
        ixbrl_extraction_from_json_bytes(b'{"x":NaN}')
    with pytest.raises(IxbrlExtractionError, match="unterminated string"):
        ixbrl_extraction_from_json_bytes(b'{"x":"unterminated')


def test_json_restore_rejects_duplicate_keys_after_lexical_preflight(install_parser):
    install_parser()
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    duplicate = extraction.to_json_bytes().replace(
        b'{"contexts"', b'{"schema":"forged","contexts"', 1
    )
    with pytest.raises(IxbrlExtractionError, match="duplicate JSON key"):
        ixbrl_extraction_from_json_bytes(duplicate)


def test_largest_practical_canonical_wrapper_artifact_round_trips(install_parser):
    output = _parser_output(CONTENT, "annual.htm")
    output["facts"] = [
        {
            "fact_id": f"bulk_{index:05d}",
            "status": "available",
            "normalized_value": "1",
            "source_span": {"start": 6, "end": 7},
            "continuation_chain": [],
        }
        for index in range(FFXBRL_LIMITS["max_facts"])
    ]
    output["diagnostics"] = []
    output["coverage"] = {"fact_inventory_complete": True, "canonical_value_complete": True}
    install_parser(output=output)
    extraction = build_ixbrl_extraction(
        _package(), "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00Z"
    )
    content = extraction.to_json_bytes()

    assert len(content) <= FFXBRL_LIMITS["max_artifact_bytes"]
    assert len(extraction.to_dict()["facts"]) == FFXBRL_LIMITS["max_facts"]
    assert ixbrl_extraction_from_json_bytes(content).to_json_bytes() == content


def test_real_parser_build_and_exact_source_replay_for_inline_fixture():
    content = (Path(__file__).parent / "fixtures" / "sec_filings" / "minimal_inline.xhtml").read_bytes()
    package = _package(content)

    extraction = build_ixbrl_extraction(
        package, "annual.htm", content, computed_at="2026-08-02T14:00:00Z"
    )

    assert extraction.to_dict()["document"]["kind"] == "inline_xbrl"
    assert extraction.to_dict()["parser"]["algorithm_fingerprint"]
    verify_ixbrl_extraction_source(extraction, package, content)
