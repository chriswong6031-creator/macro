"""Focused contracts for the sealed ``ffatt_`` boundary."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from engine.fundamental_forensics.filing_attestation import (
    ArchiveDocumentRead,
    CompanyFactsSourcePaths,
    FilingAttestationError,
    PinnedSourceAuthority,
    SourceFileRead,
    SourceWitness,
    build_filing_attestation,
    filing_attestation_from_json_bytes,
    verify_filing_attestation_source,
)
from engine.fundamental_forensics.filing_package import FilingPackage, build_filing_package
from engine.fundamental_forensics.ixbrl_extraction import IxbrlExtraction, build_ixbrl_extraction
from engine.fundamental_forensics.models import canonical_json, stable_id
from engine.fundamental_forensics.sec_document_spine import archive_index_url, build_filing_manifests, manifest_json_bytes
from collectors.sec_document_spine import manifest_storage_key, receipt_storage_key
from collectors.fundamental_forensics_companyfacts import (
    acquire_companyfacts,
    read_companyfacts_manifest,
)
from engine.fundamental_forensics.source_sync import sync_source_roots
from engine.research_vault.r2_store import LocalStore


STAMP = "2026-08-02T12:00:00.000000Z"
ATTESTED_AT = "2026-08-02T16:00:00.000000Z"
CONTENT = b"<html xmlns='http://www.w3.org/1999/xhtml'><body>fixture</body></html>"
SNAPSHOT_ID = "ffsecsrc_" + "a" * 64


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


def _package() -> tuple[FilingPackage, dict, bytes]:
    manifest = build_filing_manifests(
        {
            "cik": "1",
            "name": "Fixture Holdings",
            "filings": {"recent": {
                "accessionNumber": ["0000000001-26-000001"], "form": ["10-K"],
                "filingDate": ["2026-02-20"], "reportDate": ["2025-12-31"],
                "acceptanceDateTime": ["2026-02-20T16:00:00Z"], "primaryDocument": ["annual.htm"],
            }},
        }, recorded_at=STAMP,
    )[0]
    cik, accession = manifest["issuer"]["cik"], manifest["filing"]["accession"]
    index_content = b'{"directory":{"item":[{"name":"annual.htm"}]}}'
    index_id = stable_id("sec_document", cik, accession, "archive", "index.json")
    index_url = archive_index_url(cik, accession)
    index_receipt = _receipt(index_id, index_url, index_content)
    index_document = {
        "document_id": index_id, "document_name": "index.json", "document_type": None,
        "sequence": None, "role": "archive", "archive_url": index_url, "availability": "stored",
        "content_sha256": index_receipt["content_sha256"], "byte_length": index_receipt["byte_length"],
        "storage_key": index_receipt["storage_key"], "retrieval": index_receipt,
        "source_spans": [{"span_id": stable_id("sec_span", index_id, f"bytes:0-{len(index_content)}", index_receipt["content_sha256"]), "locator_type": "byte_range", "locator": f"bytes:0-{len(index_content)}", "text_sha256": index_receipt["content_sha256"]}],
    }
    member = manifest["documents"][0]
    member_receipt = _receipt(member["document_id"], member["archive_url"], CONTENT)
    package = build_filing_package(
        manifest, index_document, index_content,
        {"annual.htm": {"state": "stored", "content_sha256": member_receipt["content_sha256"], "byte_length": member_receipt["byte_length"], "storage_key": member_receipt["storage_key"], "retrieval": member_receipt, "policy_reason": None}},
        assembled_at="2026-08-02T13:00:00.000000Z", policy_profile="fixture", policy_version="v1",
    )
    return package, manifest, index_content


@pytest.fixture
def install_parser(monkeypatch):
    module = ModuleType("collectors.sec_filing_parser")

    class SecFilingParseError(ValueError):
        pass

    def parse(content: bytes, *, document_name: str) -> dict:
        return {
            "schema": "fundamental_forensics.sec_filing_parser/v1",
            "parser": {"profile": "strict_offline_ixbrl/v1", "version": "1", "algorithm_fingerprint": sha256(b"fixture parser").hexdigest(), "library": "fixture", "library_version": "1", "xml_library_version": "1", "transform_registry": []},
            "source": {"document_name": document_name, "content_sha256": sha256(content).hexdigest(), "byte_length": len(content)},
            "document": {"kind": "inline_xbrl", "root_qname": "{http://www.w3.org/1999/xhtml}html", "root_lexical_name": "html"},
            "contexts": [], "units": [], "continuations": [], "facts": [], "diagnostics": [],
            "coverage": {"fact_inventory_complete": True, "canonical_value_complete": True},
        }

    module.SecFilingParseError = SecFilingParseError
    module.SEC_FILING_PARSER_SCHEMA = "fundamental_forensics.sec_filing_parser/v1"
    module.SEC_FILING_PARSER_PROFILE = "strict_offline_ixbrl/v1"
    module.SEC_FILING_PARSER_VERSION = "1"
    module.SEC_FILING_PARSER_ALGORITHM_FINGERPRINT = sha256(b"fixture parser").hexdigest()
    module.PARSER_LIMITS = {"max_contexts": 5_000, "max_units": 2_000, "max_continuations": 10_000, "max_facts": 10_000, "max_continuation_chain": 16, "max_output_bytes": 24 * 1024 * 1024}
    module.SUPPORTED_TRANSFORMS = {}
    module.parse_sec_filing_document = parse
    module.validate_sec_filing_parse_result = lambda value, *, source_content=None: value
    monkeypatch.setitem(sys.modules, "collectors.sec_filing_parser", module)


def _authority(tmp_path: Path, package: FilingPackage, manifest: dict, index_content: bytes, prepare=None) -> PinnedSourceAuthority:
    raw_root, archive_root = tmp_path / "raw", tmp_path / "archive"
    raw_root.mkdir(parents=True); archive_root.mkdir(parents=True)
    if prepare is not None:
        prepare(raw_root, archive_root)
    package_record = package.to_dict()
    index = package_record["archive_index"]["document"]
    member = package_record["inventory"][0]
    source_files = {
        manifest_storage_key(manifest): manifest_json_bytes(manifest),
        index["storage_key"]: gzip.compress(index_content, mtime=0),
        receipt_storage_key(index["retrieval"]["receipt_id"]): canonical_json(index["retrieval"]).encode(),
        member["storage_key"]: gzip.compress(CONTENT, mtime=0),
        receipt_storage_key(member["retrieval"]["receipt_id"]): canonical_json(member["retrieval"]).encode(),
    }
    for key, content in source_files.items():
        target = archive_root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    store = LocalStore(tmp_path / "store")
    snapshot = sync_source_roots(raw_root=raw_root, archive_root=archive_root, store=store, snapshot_at="2026-08-02T15:00:00.000000Z")
    return PinnedSourceAuthority(store=store, snapshot_id=snapshot.snapshot_id)


def _inputs(install_parser, tmp_path: Path) -> tuple[FilingPackage, IxbrlExtraction, PinnedSourceAuthority]:
    package, manifest, index_content = _package()
    extraction = build_ixbrl_extraction(package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00.000000Z")
    return package, extraction, _authority(tmp_path, package, manifest, index_content)


def _numeric_extraction(package: FilingPackage, monkeypatch, *, duplicate: bool = False) -> IxbrlExtraction:
    """Install a compact valid parser result with one USD revenue projection."""
    module = ModuleType("collectors.sec_filing_parser")

    class SecFilingParseError(ValueError):
        pass

    fingerprint = sha256(b"numeric fixture parser").hexdigest()

    def parse(content: bytes, *, document_name: str) -> dict:
        facts = [{
            "fact_id": "revenue1", "concept_qname": "{http://fasb.org/us-gaap/2024}RevenueFromContractWithCustomerExcludingAssessedTax",
            "kind": "numeric", "context_ref": "c1", "unit_ref": "usd", "continuation_chain": [],
            "raw_value": "1", "transformed_value": "1", "normalized_value": "1", "status": "available", "nil": False,
            "lang": None, "decimals": "0", "precision": None, "format": None, "sign": None, "scale": None,
            "hidden": False, "fraction": None, "text_spans": [], "excluded_text_spans": [], "source_span": {"start": 20, "end": 21},
        }]
        if duplicate:
            copied = deepcopy(facts[0]); copied["fact_id"] = "revenue2"; copied["source_span"] = {"start": 22, "end": 23}; facts.append(copied)
        return {
            "schema": "fundamental_forensics.sec_filing_parser/v1",
            "parser": {"profile": "strict_offline_ixbrl/v1", "version": "1", "algorithm_fingerprint": fingerprint, "library": "fixture", "library_version": "1", "xml_library_version": "1", "transform_registry": []},
            "source": {"document_name": document_name, "content_sha256": sha256(content).hexdigest(), "byte_length": len(content)},
            "document": {"kind": "inline_xbrl", "root_qname": "{http://www.w3.org/1999/xhtml}html", "root_lexical_name": "html"},
            "contexts": [{"context_id": "c1", "entity": {"identifier": "0000000001", "scheme": "http://www.sec.gov/CIK", "source_span": {"start": 0, "end": 1}}, "period": {"kind": "duration", "instant_date": None, "start_date": "2024-01-01", "end_date": "2024-12-31", "source_span": {"start": 1, "end": 2}}, "dimensions": [], "segment_content_status": "complete", "unknown_segment_spans": [], "scenario_content_status": "complete", "unknown_scenario_spans": [], "source_span": {"start": 0, "end": 2}}],
            "units": [{"unit_id": "usd", "numerator_measures": ["{http://www.xbrl.org/2003/iso4217}USD"], "denominator_measures": [], "source_span": {"start": 3, "end": 4}}],
            "continuations": [], "facts": facts, "diagnostics": [], "coverage": {"fact_inventory_complete": True, "canonical_value_complete": True},
        }

    module.SecFilingParseError = SecFilingParseError
    module.SEC_FILING_PARSER_SCHEMA = "fundamental_forensics.sec_filing_parser/v1"
    module.SEC_FILING_PARSER_PROFILE = "strict_offline_ixbrl/v1"
    module.SEC_FILING_PARSER_VERSION = "1"
    module.SEC_FILING_PARSER_ALGORITHM_FINGERPRINT = fingerprint
    module.PARSER_LIMITS = {"max_contexts": 5_000, "max_units": 2_000, "max_continuations": 10_000, "max_facts": 10_000, "max_continuation_chain": 16, "max_output_bytes": 24 * 1024 * 1024}
    module.SUPPORTED_TRANSFORMS = {}
    module.parse_sec_filing_document = parse
    module.validate_sec_filing_parse_result = lambda value, *, source_content=None: value
    monkeypatch.setitem(sys.modules, "collectors.sec_filing_parser", module)
    return build_ixbrl_extraction(package, "annual.htm", CONTENT, computed_at="2026-08-02T14:00:00.000000Z")


def _companyfacts_prepare(state: dict, raw_body: bytes):
    class Response:
        status_code = 200
        headers: dict[str, str] = {}

        def iter_content(self, *, chunk_size: int):
            yield raw_body

        def close(self) -> None:
            return None

    def prepare(raw_root: Path, archive_root: Path) -> None:
        result = acquire_companyfacts(
            targets=("FXT=1",), raw_root=raw_root, archive_root=archive_root,
            user_agent="MastermindX research@example.com", source_snapshot_at="2026-08-02T15:00:00.000000Z",
            recorded_at="2026-08-02T15:00:00.000000Z", fetcher=lambda *args, **kwargs: Response(),
            utc_now=lambda: datetime(2026, 8, 2, 15, tzinfo=timezone.utc),
        )
        receipt = result["run"]["ticker_receipts"][0]
        manifest = read_companyfacts_manifest(archive_root, receipt["manifest_key"])
        # Collector publication uses this local coordination sentinel; it is
        # intentionally not part of immutable source evidence.
        (archive_root / "wave3_companyfacts" / ".manifest_publish.lock").unlink(missing_ok=True)
        state["paths"] = CompanyFactsSourcePaths(
            manifest_path=receipt["manifest_key"], capture_path=manifest["source"]["capture_receipt_key"],
            response_path=manifest["source"]["response_object_path"],
        )
    return prepare


def _companyfacts_body(value: str = "1", *, duplicate: bool = False) -> bytes:
    rows = """[{\"start\":\"2024-01-01\",\"end\":\"2024-12-31\",\"val\":%s,\"accn\":\"0000000001-26-000001\",\"fy\":2024,\"fp\":\"FY\",\"form\":\"10-K\",\"filed\":\"2026-02-20\",\"frame\":\"CY2024\"}%s]""" % (value, ",{\"start\":\"2024-01-01\",\"end\":\"2024-12-31\",\"val\":%s,\"accn\":\"0000000001-26-000001\",\"fy\":2024,\"fp\":\"FY\",\"form\":\"10-K\",\"filed\":\"2026-02-20\",\"frame\":\"CY2024\"}" % value if duplicate else "")
    return ("{\"cik\":1,\"entityName\":\"Fixture\",\"facts\":{\"us-gaap\":{\"RevenueFromContractWithCustomerExcludingAssessedTax\":{\"label\":\"Revenue\",\"units\":{\"USD\":%s}}}}}" % rows).encode()


def test_seals_pinned_index_member_manifest_and_parser_replay(install_parser, monkeypatch, tmp_path):
    package, extraction, authority = _inputs(install_parser, tmp_path)
    attestation = build_filing_attestation(
        package, extraction, authority=authority, attested_at=ATTESTED_AT
    )
    record = attestation.to_dict()
    assert attestation.attestation_id.startswith("ffatt_")
    assert record["coverage"]["selected_member_parser_replayed"] is True
    assert record["source_evidence"]["archive_index"]["receipt_sidecar_verified"] is True
    assert record["nonclaims"]["filing_complete"] is False
    assert filing_attestation_from_json_bytes(attestation.to_json_bytes()).to_dict() == record
    verify_filing_attestation_source(attestation, package, extraction, authority=authority)


def test_requires_explicit_causal_operator_clock(install_parser, monkeypatch, tmp_path):
    package, extraction, authority = _inputs(install_parser, tmp_path)

    with pytest.raises(TypeError, match="attested_at"):
        build_filing_attestation(package, extraction, authority=authority)

    with pytest.raises(FilingAttestationError, match="predates source evidence"):
        build_filing_attestation(
            package,
            extraction,
            authority=authority,
            attested_at="2026-08-02T14:59:59.000000Z",
        )


def test_tamper_and_hostile_nominals_fail_closed(install_parser, monkeypatch, tmp_path):
    package, extraction, authority = _inputs(install_parser, tmp_path)
    index_key = package.to_dict()["archive_index"]["document"]["storage_key"]
    outer = authority._snapshot.entry_for(kind="archive", relative_path=index_key)
    assert authority._store.put_bytes(outer.object_key, b"tampered") is True
    with pytest.raises(FilingAttestationError, match="index source read failed"):
        build_filing_attestation(
            package, extraction, authority=authority, attested_at=ATTESTED_AT
        )

    class HostilePackage(FilingPackage):
        @property
        def manifest(self):
            raise RuntimeError("must not dispatch subclass")

    with pytest.raises(FilingAttestationError, match="subclasses"):
        build_filing_attestation(
            HostilePackage(package.to_dict()),
            extraction,
            authority=authority,
            attested_at=ATTESTED_AT,
        )


def test_restore_rejects_duplicate_noncanonical_and_forged_claims(install_parser, monkeypatch, tmp_path):
    package, extraction, authority = _inputs(install_parser, tmp_path)
    content = build_filing_attestation(
        package, extraction, authority=authority, attested_at=ATTESTED_AT
    ).to_json_bytes()
    with pytest.raises(FilingAttestationError, match="canonically"):
        filing_attestation_from_json_bytes(b" " + content)
    with pytest.raises(FilingAttestationError, match="duplicate"):
        filing_attestation_from_json_bytes(content.replace(b'{"attestation_id"', b'{"schema":"x","attestation_id"', 1))
    forged = json.loads(content)
    forged["nonclaims"]["trading_authority"] = True
    body = deepcopy(forged); body.pop("attestation_id")
    forged["attestation_id"] = "ffatt_" + sha256(canonical_json(body).encode()).hexdigest()
    with pytest.raises(FilingAttestationError, match="nonclaims"):
        filing_attestation_from_json_bytes(json.dumps(forged, sort_keys=True, separators=(",", ":")).encode())

    for field, impossible in (
        ("object_key", "arbitrary/path"),
        ("relative_path", "a/../b"),
        ("content_type", "application/octet-stream"),
    ):
        forged_witness = json.loads(content)
        forged_witness["source_evidence"]["filing_manifest"]["outer"][field] = impossible
        body = deepcopy(forged_witness); body.pop("attestation_id")
        forged_witness["attestation_id"] = "ffatt_" + sha256(canonical_json(body).encode()).hexdigest()
        with pytest.raises(FilingAttestationError, match="source witness"):
            filing_attestation_from_json_bytes(
                json.dumps(forged_witness, sort_keys=True, separators=(",", ":")).encode()
            )


def test_exact_companyfacts_projection_is_one_to_one_and_preserves_decimal_precision(monkeypatch, tmp_path):
    package, manifest, index_content = _package()
    extraction = _numeric_extraction(package, monkeypatch)
    state: dict = {}
    authority = _authority(tmp_path, package, manifest, index_content, prepare=_companyfacts_prepare(state, _companyfacts_body()))
    attestation = build_filing_attestation(
        package,
        extraction,
        authority=authority,
        attested_at=ATTESTED_AT,
        companyfacts_paths=state["paths"],
    )
    assert len(attestation.to_dict()["company_facts"]["matches"]) == 1

    near_state: dict = {}
    near_authority = _authority(tmp_path / "near", package, manifest, index_content, prepare=_companyfacts_prepare(near_state, _companyfacts_body("1.0000000000000000000000000001")))
    near = build_filing_attestation(
        package,
        extraction,
        authority=near_authority,
        attested_at=ATTESTED_AT,
        companyfacts_paths=near_state["paths"],
    ).to_dict()
    assert near["company_facts"]["matches"] == []
    assert near["company_facts"]["reason_counts"]["no_exact_companyfacts_row"] == 1

    duplicate_extraction = _numeric_extraction(package, monkeypatch, duplicate=True)
    duplicate_state: dict = {}
    duplicate_authority = _authority(tmp_path / "duplicate", package, manifest, index_content, prepare=_companyfacts_prepare(duplicate_state, _companyfacts_body()))
    duplicate = build_filing_attestation(
        package,
        duplicate_extraction,
        authority=duplicate_authority,
        attested_at=ATTESTED_AT,
        companyfacts_paths=duplicate_state["paths"],
    ).to_dict()
    assert duplicate["company_facts"]["matches"] == []
    assert duplicate["company_facts"]["reason_counts"]["ambiguous_ixbrl_fact"] == 2
