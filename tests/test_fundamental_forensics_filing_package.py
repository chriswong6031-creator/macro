"""Offline contract tests for immutable filing-package attestations."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from engine.fundamental_forensics.filing_package import (
    FILING_PACKAGE_SCHEMA,
    HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES,
    FilingPackage,
    FilingPackageError,
    build_filing_package,
    filing_package_from_json_bytes,
)
from engine.fundamental_forensics.models import canonical_json, stable_id
from engine.fundamental_forensics.sec_document_spine import (
    HARD_MAX_ARCHIVE_DOCUMENT_BYTES,
    HARD_MAX_HTTP_METADATA_BYTES,
    archive_document_url,
    archive_index_url,
    build_filing_manifests,
)


STAMP = "2026-08-01T12:00:00Z"


def _manifest() -> dict:
    return build_filing_manifests(
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


def _stored_receipt(document_id: str, archive_url: str, content: bytes) -> tuple[str, int, str, dict]:
    digest = sha256(content).hexdigest()
    storage_key = f"objects/sha256/{digest[:2]}/{digest}.bin.gz"
    body = {
        "schema": "fundamental_forensics.sec_archive_receipt/v1",
        "status": "retrieved",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": "2026-08-01T12:00:00.000000Z",
        "content_sha256": digest,
        "byte_length": len(content),
        "storage_key": storage_key,
        "http_etag": None,
        "http_last_modified": None,
    }
    return digest, len(content), storage_key, {
        "receipt_id": stable_id("sec_archive_receipt", body),
        **body,
    }


def _missing_receipt(document_id: str, archive_url: str) -> dict:
    return {
        "schema": "fundamental_forensics.sec_archive_receipt/v1",
        "status": "missing",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": "2026-08-01T12:00:00.000000Z",
        "http_status": 404,
        "reason": "sec_archive_document_missing",
    }


def _index_bytes(payload: dict) -> bytes:
    # Preserve a realistic non-canonical wire representation.  The package
    # hashes these exact bytes, then stores a separate canonical projection.
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _index_document(manifest: dict, content: bytes) -> dict:
    cik = manifest["issuer"]["cik"]
    accession = manifest["filing"]["accession"]
    document_id = stable_id("sec_document", cik, accession, "archive", "index.json")
    url = archive_index_url(cik, accession)
    digest, length, storage_key, receipt = _stored_receipt(document_id, url, content)
    return {
        "document_id": document_id,
        "document_name": "index.json",
        "document_type": None,
        "sequence": None,
        "role": "archive",
        "archive_url": url,
        "availability": "stored",
        "content_sha256": digest,
        "byte_length": length,
        "storage_key": storage_key,
        "retrieval": receipt,
        "source_spans": [
            {
                "span_id": stable_id("sec_span", document_id, f"bytes:0-{length}", digest),
                "locator_type": "byte_range",
                "locator": f"bytes:0-{length}",
                "text_sha256": digest,
            }
        ],
    }


def _fixture_inputs() -> tuple[dict, dict, dict, bytes, dict]:
    manifest = _manifest()
    cik = manifest["issuer"]["cik"]
    accession = manifest["filing"]["accession"]
    primary = manifest["documents"][0]
    primary_digest, primary_length, primary_key, primary_receipt = _stored_receipt(
        primary["document_id"], primary["archive_url"], b"annual filing"
    )
    missing_name = "FilingSummary.xml"
    missing_id = stable_id("sec_document", cik, accession, "archive", missing_name)
    missing_url = archive_document_url(cik, accession, missing_name)
    payload = {
        "directory": {
            "item": [
                {"name": "annual.htm", "size": "13"},
                {"name": missing_name},
                {"name": "notes.txt"},
                {"name": "secret.xml"},
            ]
        }
    }
    states = {
        "annual.htm": {
            "state": "stored",
            "content_sha256": primary_digest,
            "byte_length": primary_length,
            "storage_key": primary_key,
            "retrieval": primary_receipt,
            "policy_reason": None,
        },
        missing_name: {
            "state": "missing",
            "content_sha256": None,
            "byte_length": None,
            "storage_key": None,
            "retrieval": _missing_receipt(missing_id, missing_url),
            "policy_reason": None,
        },
        "notes.txt": "not_requested",
        "secret.xml": {
            "state": "rejected_by_policy",
            "content_sha256": None,
            "byte_length": None,
            "storage_key": None,
            "retrieval": None,
            "policy_reason": "profile excludes inline XBRL parsing in this wave",
        },
    }
    content = _index_bytes(payload)
    return manifest, _index_document(manifest, content), payload, content, states


def _package() -> FilingPackage:
    manifest, document, _payload, content, states = _fixture_inputs()
    return build_filing_package(
        manifest,
        document,
        content,
        states,
        assembled_at="2026-08-01T13:00:00Z",
        policy_profile="safe_archive_inventory",
        policy_version="v1",
    )


def test_package_binds_one_manifest_stored_index_and_complete_inventory_without_overclaiming():
    package = _package()
    record = package.to_dict()
    _manifest_value, _document, payload, raw_index, _states = _fixture_inputs()

    assert record["schema"] == FILING_PACKAGE_SCHEMA
    assert package.package_id.startswith("ffpkg_")
    assert package.content_id == package.package_id
    assert record["filing"]["cik"] == "0000000001"
    assert record["archive_index"]["document"]["document_name"] == "index.json"
    assert record["archive_index"]["document"]["retrieval"]["status"] == "retrieved"
    assert record["archive_index"]["document"]["content_sha256"] == sha256(raw_index).hexdigest()
    assert record["archive_index"]["payload_sha256"] == sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
    assert record["archive_index"]["payload_sha256"] != sha256(raw_index).hexdigest()
    assert [item["document_name"] for item in record["inventory"]] == [
        "FilingSummary.xml",
        "annual.htm",
        "notes.txt",
        "secret.xml",
    ]
    assert record["inventory"][1]["role"] == "primary"
    assert record["coverage"] == {
        "package_inventory_complete": True,
        "safe_archive_index_member_count": 4,
        "stored_member_count": 1,
        "missing_member_count": 1,
        "not_requested_member_count": 1,
        "rejected_by_policy_member_count": 1,
        "all_index_members_receipted_as_stored": False,
        "all_filing_bytes_retained": False,
        "sec_universe_complete": False,
    }
    assert record["attestations"] == {
        "archive_object_presence_attested": False,
        "xbrl_semantic_attested": False,
    }


def test_archive_index_inventory_is_derived_from_the_exact_receipted_raw_bytes():
    manifest, document, payload, content, states = _fixture_inputs()
    semantically_equal_but_different = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    assert semantically_equal_but_different != content

    with pytest.raises(FilingPackageError, match="retained document receipt"):
        build_filing_package(
            manifest,
            document,
            semantically_equal_but_different,
            states,
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'{"directory":{"item":[]},"directory":{"item":[]}}', "duplicate"),
        (b"\xff", "strict UTF-8 JSON"),
        (b'{"directory":{"item":[]},"value":NaN}', "non-finite"),
        (
            b'{"directory":{"item":[]},"value":' + b"9" * 5_000 + b"}",
            "strict UTF-8 JSON",
        ),
    ],
)
def test_archive_index_raw_json_rejects_ambiguous_or_non_json_content(content, message):
    manifest = _manifest()
    document = _index_document(manifest, content)
    with pytest.raises(FilingPackageError, match=message):
        build_filing_package(
            manifest,
            document,
            content,
            {},
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


def test_archive_index_raw_bytes_are_capped_before_digest_or_json_work():
    manifest, document, _payload, _content, _states = _fixture_inputs()
    oversized = b" " * (HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES + 1)
    with pytest.raises(FilingPackageError, match="content exceeds byte safety limit"):
        build_filing_package(
            manifest,
            document,
            oversized,
            {},
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


def test_stored_member_receipts_share_the_archive_collectors_hard_byte_cap():
    manifest, document, _payload, content, states = _fixture_inputs()
    evidence = states["annual.htm"]
    receipt = evidence["retrieval"]

    for length, should_pass in (
        (HARD_MAX_ARCHIVE_DOCUMENT_BYTES, True),
        (HARD_MAX_ARCHIVE_DOCUMENT_BYTES + 1, False),
    ):
        evidence["byte_length"] = length
        receipt["byte_length"] = length
        body = dict(receipt)
        body.pop("receipt_id")
        receipt["receipt_id"] = stable_id("sec_archive_receipt", body)
        if should_pass:
            assert build_filing_package(
                manifest,
                document,
                content,
                states,
                assembled_at="2026-08-01T13:00:00Z",
                policy_profile="safe_archive_inventory",
                policy_version="v1",
            ).package_id.startswith("ffpkg_")
        else:
            with pytest.raises(FilingPackageError, match="bounded byte range"):
                build_filing_package(
                    manifest,
                    document,
                    content,
                    states,
                    assembled_at="2026-08-01T13:00:00Z",
                    policy_profile="safe_archive_inventory",
                    policy_version="v1",
                )


def test_package_is_immutable_and_has_one_canonical_json_restore_boundary():
    package = _package()
    content = package.to_json_bytes()
    restored = filing_package_from_json_bytes(content)

    assert restored.to_json_bytes() == content
    assert FilingPackage.from_json_bytes(content).package_id == package.package_id
    with pytest.raises(TypeError):
        package.manifest["coverage"]["sec_universe_complete"] = True

    copied = package.to_dict()
    copied["coverage"]["sec_universe_complete"] = True
    assert package.to_dict()["coverage"]["sec_universe_complete"] is False

    with pytest.raises(FilingPackageError, match="canonically encoded"):
        filing_package_from_json_bytes(b" " + content)
    duplicate_schema = content.replace(b'{"archive_index"', b'{"schema":"forged","archive_index"', 1)
    with pytest.raises(FilingPackageError, match="duplicate JSON key"):
        filing_package_from_json_bytes(duplicate_schema)

    huge_integer = content.replace(
        b'"safe_archive_index_member_count":4',
        b'"safe_archive_index_member_count":' + b"9" * 5_000,
        1,
    )
    with pytest.raises(FilingPackageError, match="not UTF-8 JSON"):
        filing_package_from_json_bytes(huge_integer)


def test_restore_rederives_projection_from_embedded_raw_index_witness():
    record = _package().to_dict()
    record["archive_index"]["payload"]["directory"]["projection_not_in_raw_receipt"] = (
        "forged"
    )
    projected = canonical_json(record["archive_index"]["payload"]).encode("utf-8")
    record["archive_index"]["payload_sha256"] = sha256(projected).hexdigest()
    record["archive_index"]["payload_byte_length"] = len(projected)
    body = {key: value for key, value in record.items() if key != "package_id"}
    record["package_id"] = "ffpkg_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()

    with pytest.raises(FilingPackageError, match="does not derive from its raw-content witness"):
        FilingPackage.from_dict(record)


def test_identity_and_clock_are_fail_closed_on_mutation_or_forgery():
    record = _package().to_dict()
    record["package_id"] = "ffpkg_" + "0" * 64
    with pytest.raises(FilingPackageError, match="identity mismatch"):
        FilingPackage.from_dict(record)

    record = _package().to_dict()
    record["assembly"]["assembled_at"] = "2026-08-01T13:00:00+00:00"
    with pytest.raises(FilingPackageError, match="canonical UTC"):
        FilingPackage.from_dict(record)

    record = _package().to_dict()
    record["inventory"][1]["retrieval"]["content_sha256"] = "0" * 64
    with pytest.raises(FilingPackageError, match="stored bytes"):
        FilingPackage.from_dict(record)

    record = _package().to_dict()
    record["assembly"]["assembled_at"] = "2026-08-01T11:59:59.000000Z"
    record["package_id"] = "ffpkg_" + sha256(
        canonical_json({key: value for key, value in record.items() if key != "package_id"}).encode(
            "utf-8"
        )
    ).hexdigest()
    with pytest.raises(FilingPackageError, match="before its evidence"):
        FilingPackage.from_dict(record)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("http_status", 500, "observed SEC 404"),
        ("reason", "transient_server_error", "canonical missing-document reason"),
    ],
)
def test_missing_state_only_accepts_the_canonical_observed_sec_404(field, value, message):
    manifest, document, _payload, content, states = _fixture_inputs()
    states["FilingSummary.xml"]["retrieval"][field] = value
    with pytest.raises(FilingPackageError, match=message):
        build_filing_package(
            manifest,
            document,
            content,
            states,
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda payload, states: payload["directory"]["item"].append({"name": "annual.htm"}), "duplicate"),
        (lambda payload, states: payload["directory"]["item"].append({"name": "../escape.xml"}), "safe"),
        (lambda payload, states: states.pop("notes.txt"), "exactly"),
        (lambda payload, states: states.update({"invented.xml": "not_requested"}), "exactly"),
    ],
)
def test_archive_index_members_are_neither_duplicated_skipped_nor_invented(mutator, message):
    manifest, _document, payload, _content, states = _fixture_inputs()
    mutator(payload, states)
    content = _index_bytes(payload)
    document = _index_document(manifest, content)
    with pytest.raises(FilingPackageError, match=message):
        build_filing_package(
            manifest,
            document,
            content,
            states,
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


def test_member_state_evidence_and_index_receipt_cannot_claim_unretained_bytes():
    manifest, document, _payload, content, states = _fixture_inputs()
    states["FilingSummary.xml"]["content_sha256"] = "0" * 64
    with pytest.raises(FilingPackageError, match="missing inventory"):
        build_filing_package(
            manifest,
            document,
            content,
            states,
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


@pytest.mark.parametrize(
    "etag", ["x" * (HARD_MAX_HTTP_METADATA_BYTES + 1), "safe\r\nInjected: yes"]
)
def test_package_receipts_enforce_the_shared_http_metadata_contract(etag):
    manifest, document, _payload, content, states = _fixture_inputs()
    receipt = states["annual.htm"]["retrieval"]
    receipt["http_etag"] = etag
    body = dict(receipt)
    body.pop("receipt_id")
    receipt["receipt_id"] = stable_id("sec_archive_receipt", body)
    with pytest.raises(FilingPackageError, match="http_etag"):
        build_filing_package(
            manifest,
            document,
            content,
            states,
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )

    manifest, document, _payload, content, states = _fixture_inputs()
    document["retrieval"]["receipt_id"] = "sec_archive_receipt_" + "0" * 64
    with pytest.raises(FilingPackageError, match="identity mismatch"):
        build_filing_package(
            manifest,
            document,
            content,
            states,
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


class _LenLyingMemberStates(Mapping[str, object]):
    """Claims to be empty while exposing an extra member through ``items``."""

    def __getitem__(self, key: str) -> object:  # pragma: no cover - items drives the kernel.
        raise KeyError(key)

    def __iter__(self):  # pragma: no cover - items drives the kernel.
        return iter(())

    def __len__(self) -> int:
        return 0

    def items(self):
        return iter((("annual.htm", "not_requested"), ("invented.xml", "not_requested")))


def test_member_mapping_length_cannot_hide_extra_or_invented_entries():
    manifest, _document, _payload, _content, _states = _fixture_inputs()
    payload = {"directory": {"item": [{"name": "annual.htm"}]}}
    content = _index_bytes(payload)
    document = _index_document(manifest, content)
    with pytest.raises(FilingPackageError, match="exactly"):
        build_filing_package(
            manifest,
            document,
            content,
            _LenLyingMemberStates(),
            assembled_at="2026-08-01T13:00:00Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


def test_restored_inventory_cannot_change_derived_document_role_or_coverage():
    record = _package().to_dict()
    primary = next(item for item in record["inventory"] if item["document_name"] == "annual.htm")
    primary["role"] = "archive"
    with pytest.raises(FilingPackageError, match="document_id"):
        FilingPackage.from_dict(record)

    record = _package().to_dict()
    record["coverage"] = deepcopy(record["coverage"])
    record["coverage"]["package_inventory_complete"] = False
    with pytest.raises(FilingPackageError, match="coverage"):
        FilingPackage.from_dict(record)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda record: record["filing"].update({"accession": 1}),
        lambda record: record["inventory"][0].update({"role": []}),
        lambda record: record["inventory"][0].update({"state": []}),
    ],
)
def test_malformed_restore_scalars_fail_with_the_package_error_contract(mutator):
    record = _package().to_dict()
    mutator(record)
    with pytest.raises(FilingPackageError):
        FilingPackage.from_dict(record)
