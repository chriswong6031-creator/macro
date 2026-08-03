"""Strict offline tests for pinned-source filing-package materialization."""
from __future__ import annotations

from dataclasses import replace
import gzip
from hashlib import sha256
import json
from pathlib import Path

import pytest

from collectors.sec_document_spine import (
    manifest_storage_key,
    missing_receipt_json_bytes,
    missing_receipt_storage_key,
    receipt_storage_key,
)
from engine.fundamental_forensics.filing_attestation import PinnedSourceAuthority
from engine.fundamental_forensics.filing_package import (
    FilingPackageError,
    PinnedFilingPackageDescriptor,
    build_filing_package,
    materialize_filing_package_from_pinned_source,
)
from engine.fundamental_forensics.models import canonical_json, stable_id
from engine.fundamental_forensics.sec_document_spine import (
    archive_document_url,
    archive_index_url,
    build_filing_manifests,
    manifest_json_bytes,
)
from engine.fundamental_forensics.source_sync import sync_source_roots
from engine.research_vault.r2_store import LocalStore


RECORDED_AT = "2026-08-02T12:00:00.000000Z"
SNAPSHOT_AT = "2026-08-02T15:00:00.000000Z"
ASSEMBLED_AT = "2026-08-02T16:00:00.000000Z"
ANNUAL_BYTES = b"<html>annual filing</html>"
SUPPLEMENT_BYTES = b"<xbrl>supplement</xbrl>"


class AuditedLocalStore(LocalStore):
    """Local strict store that records which bounded source objects were read."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.bounded_reads: list[tuple[str, int | None]] = []
        self.unbounded_strict_reads: list[str] = []

    def get_bytes_strict(self, key: str) -> bytes | None:
        self.unbounded_strict_reads.append(key)
        return super().get_bytes_strict(key)

    def get_bytes_strict_bounded(
        self,
        key: str,
        maximum_bytes: int | None = None,
        *,
        expected_byte_length: int | None = None,
        max_byte_length: int | None = None,
    ) -> bytes | None:
        self.bounded_reads.append((key, maximum_bytes))
        return super().get_bytes_strict_bounded(
            key,
            maximum_bytes,
            expected_byte_length=expected_byte_length,
            max_byte_length=max_byte_length,
        )


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
        recorded_at=RECORDED_AT,
    )[0]


def _retrieved_receipt(
    document_id: str,
    archive_url: str,
    content: bytes,
    *,
    retrieved_at: str = RECORDED_AT,
) -> dict:
    digest = sha256(content).hexdigest()
    body = {
        "schema": "fundamental_forensics.sec_archive_receipt/v1",
        "status": "retrieved",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "byte_length": len(content),
        "storage_key": f"objects/sha256/{digest[:2]}/{digest}.bin.gz",
        "http_etag": None,
        "http_last_modified": None,
    }
    return {"receipt_id": stable_id("sec_archive_receipt", body), **body}


def _missing_receipt(
    document_id: str,
    archive_url: str,
    *,
    retrieved_at: str = RECORDED_AT,
) -> dict:
    return {
        "schema": "fundamental_forensics.sec_archive_receipt/v1",
        "status": "missing",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": retrieved_at,
        "http_status": 404,
        "reason": "sec_archive_document_missing",
    }


def _index_document(
    manifest: dict,
    content: bytes,
    *,
    retrieved_at: str = RECORDED_AT,
) -> dict:
    cik = manifest["issuer"]["cik"]
    accession = manifest["filing"]["accession"]
    document_id = stable_id("sec_document", cik, accession, "archive", "index.json")
    receipt = _retrieved_receipt(
        document_id,
        archive_index_url(cik, accession),
        content,
        retrieved_at=retrieved_at,
    )
    length = receipt["byte_length"]
    digest = receipt["content_sha256"]
    return {
        "document_id": document_id,
        "document_name": "index.json",
        "document_type": None,
        "sequence": None,
        "role": "archive",
        "archive_url": receipt["archive_url"],
        "availability": "stored",
        "content_sha256": digest,
        "byte_length": length,
        "storage_key": receipt["storage_key"],
        "retrieval": receipt,
        "source_spans": [
            {
                "span_id": stable_id(
                    "sec_span", document_id, f"bytes:0-{length}", digest
                ),
                "locator_type": "byte_range",
                "locator": f"bytes:0-{length}",
                "text_sha256": digest,
            }
        ],
    }


def _write(root: Path, relative_path: str, content: bytes) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _source_fixture(
    tmp_path: Path,
    *,
    include_supplement: bool = True,
    snapshot_at: str = SNAPSHOT_AT,
    retrieval_at: str = RECORDED_AT,
    member_gzip_padding_bytes: int = 0,
) -> tuple[
    PinnedSourceAuthority,
    PinnedFilingPackageDescriptor,
    dict,
    bytes,
    AuditedLocalStore,
    str,
]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = _manifest()
    cik = manifest["issuer"]["cik"]
    accession = manifest["filing"]["accession"]
    index_payload = {
        "directory": {
            "item": [
                {"name": "annual.htm"},
                {"name": "FilingSummary.xml"},
                {"name": "notes.txt"},
                {"name": "secret.xml"},
                {"name": "supplement.xml"},
            ]
        }
    }
    index_content = json.dumps(index_payload, indent=2).encode("utf-8")
    index_document = _index_document(
        manifest,
        index_content,
        retrieved_at=retrieval_at,
    )

    annual = manifest["documents"][0]
    annual_receipt = _retrieved_receipt(
        annual["document_id"],
        annual["archive_url"],
        ANNUAL_BYTES,
        retrieved_at=retrieval_at,
    )
    supplement_name = "supplement.xml"
    supplement_id = stable_id(
        "sec_document", cik, accession, "archive", supplement_name
    )
    supplement_receipt = _retrieved_receipt(
        supplement_id,
        archive_document_url(cik, accession, supplement_name),
        SUPPLEMENT_BYTES,
        retrieved_at=retrieval_at,
    )
    missing_name = "FilingSummary.xml"
    states = {
        "annual.htm": {
            "state": "stored",
            "content_sha256": annual_receipt["content_sha256"],
            "byte_length": annual_receipt["byte_length"],
            "storage_key": annual_receipt["storage_key"],
            "retrieval": annual_receipt,
            "policy_reason": None,
        },
        missing_name: {
            "state": "missing",
            "content_sha256": None,
            "byte_length": None,
            "storage_key": None,
            "retrieval": _missing_receipt(
                stable_id("sec_document", cik, accession, "archive", missing_name),
                archive_document_url(cik, accession, missing_name),
                retrieved_at=retrieval_at,
            ),
            "policy_reason": None,
        },
        "notes.txt": "not_requested",
        "secret.xml": {
            "state": "rejected_by_policy",
            "content_sha256": None,
            "byte_length": None,
            "storage_key": None,
            "retrieval": None,
            "policy_reason": "fixture policy excludes this member",
        },
        supplement_name: {
            "state": "stored",
            "content_sha256": supplement_receipt["content_sha256"],
            "byte_length": supplement_receipt["byte_length"],
            "storage_key": supplement_receipt["storage_key"],
            "retrieval": supplement_receipt,
            "policy_reason": None,
        },
    }
    descriptor = PinnedFilingPackageDescriptor(
        cik=cik,
        accession=accession,
        manifest_id=manifest["manifest_id"],
        archive_index_document=index_document,
        member_states=states,
    )

    raw_root = tmp_path / "raw"
    archive_root = tmp_path / "archive"
    raw_root.mkdir()
    archive_root.mkdir()
    _write(archive_root, manifest_storage_key(manifest), manifest_json_bytes(manifest))
    _write(
        archive_root,
        index_document["storage_key"],
        gzip.compress(index_content, mtime=0),
    )
    _write(
        archive_root,
        receipt_storage_key(index_document["retrieval"]["receipt_id"]),
        canonical_json(index_document["retrieval"]).encode("utf-8"),
    )
    missing_receipt = states[missing_name]["retrieval"]
    _write(
        archive_root,
        missing_receipt_storage_key(missing_receipt),
        missing_receipt_json_bytes(missing_receipt),
    )
    for receipt, content, include in (
        (annual_receipt, ANNUAL_BYTES, True),
        (supplement_receipt, SUPPLEMENT_BYTES, include_supplement),
    ):
        if not include:
            continue
        compressed = gzip.compress(content, mtime=0)
        if content == ANNUAL_BYTES and member_gzip_padding_bytes:
            compressed += b"\0" * member_gzip_padding_bytes
        _write(
            archive_root,
            receipt["storage_key"],
            compressed,
        )
        _write(
            archive_root,
            receipt_storage_key(receipt["receipt_id"]),
            canonical_json(receipt).encode("utf-8"),
        )
    _write(archive_root, "unrelated.bin", b"must not be read")

    store = AuditedLocalStore(tmp_path / "store")
    snapshot = sync_source_roots(
        raw_root=raw_root,
        archive_root=archive_root,
        store=store,
        snapshot_at=snapshot_at,
    )
    authority = PinnedSourceAuthority(store=store, snapshot_id=snapshot.snapshot_id)
    unrelated_key = authority._snapshot.entry_for(
        kind="archive", relative_path="unrelated.bin"
    ).object_key
    store.bounded_reads.clear()
    store.unbounded_strict_reads.clear()
    return authority, descriptor, manifest, index_content, store, unrelated_key


def _materialize(
    authority: PinnedSourceAuthority,
    descriptor: PinnedFilingPackageDescriptor,
):
    return materialize_filing_package_from_pinned_source(
        descriptor,
        authority=authority,
        assembled_at=ASSEMBLED_AT,
        policy_profile="safe_archive_inventory",
        policy_version="v1",
    )


def test_materializer_replays_exact_pinned_sources_with_complete_inventory_and_no_latest(
    tmp_path: Path,
):
    authority, descriptor, manifest, index_content, store, unrelated_key = _source_fixture(
        tmp_path
    )
    expected = build_filing_package(
        manifest,
        descriptor.archive_index_document,
        index_content,
        descriptor.member_states,
        assembled_at=ASSEMBLED_AT,
        policy_profile="safe_archive_inventory",
        policy_version="v1",
    )

    package = _materialize(authority, descriptor)

    assert package.to_json_bytes() == expected.to_json_bytes()
    assert package.to_dict()["coverage"] == {
        "package_inventory_complete": True,
        "safe_archive_index_member_count": 5,
        "stored_member_count": 2,
        "missing_member_count": 1,
        "not_requested_member_count": 1,
        "rejected_by_policy_member_count": 1,
        "all_index_members_receipted_as_stored": False,
        "all_filing_bytes_retained": False,
        "sec_universe_complete": False,
    }
    assert store.unbounded_strict_reads == []
    assert store.bounded_reads
    assert all(isinstance(limit, int) and limit >= 0 for _, limit in store.bounded_reads)
    assert unrelated_key not in {key for key, _limit in store.bounded_reads}
    assert not any("latest" in key for key, _limit in store.bounded_reads)


def test_materializer_fails_closed_when_any_index_member_state_is_omitted(tmp_path: Path):
    authority, descriptor, _manifest_value, _index, _store, _unused = _source_fixture(
        tmp_path
    )
    partial = dict(descriptor.member_states)
    partial.pop("FilingSummary.xml")

    with pytest.raises(FilingPackageError, match="exactly the archive index inventory"):
        _materialize(authority, replace(descriptor, member_states=partial))


def test_materializer_reads_every_stored_member_and_rejects_absent_source_bytes(
    tmp_path: Path,
):
    authority, descriptor, _manifest_value, _index, _store, _unused = _source_fixture(
        tmp_path,
        include_supplement=False,
    )

    with pytest.raises(
        FilingPackageError,
        match=r"pinned archive member source read failed: supplement\.xml",
    ):
        _materialize(authority, descriptor)


def test_materializer_rejects_crosswired_filing_identity_and_nominal_authorities(
    tmp_path: Path,
):
    authority, descriptor, _manifest_value, _index, _store, _unused = _source_fixture(
        tmp_path
    )
    crosswired = replace(descriptor, cik="0000000002")
    with pytest.raises(FilingPackageError, match="does not bind the filing index.json"):
        _materialize(authority, crosswired)

    class LookalikeAuthority:
        snapshot_id = authority.snapshot_id

    with pytest.raises(FilingPackageError, match="exact PinnedSourceAuthority"):
        materialize_filing_package_from_pinned_source(
            descriptor,
            authority=LookalikeAuthority(),
            assembled_at=ASSEMBLED_AT,
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


def test_materializer_rejects_snapshot_that_predates_manifest_recording(tmp_path: Path):
    authority, descriptor, _manifest_value, _index, _store, _unused = _source_fixture(
        tmp_path,
        snapshot_at="2026-08-02T11:59:59.000000Z",
    )

    with pytest.raises(FilingPackageError, match="snapshot predates filing manifest"):
        _materialize(authority, descriptor)


def test_materializer_requires_pinned_evidence_for_every_missing_404(tmp_path: Path):
    authority, descriptor, _manifest_value, _index, _store, _unused = _source_fixture(
        tmp_path
    )
    states = dict(descriptor.member_states)
    cik = descriptor.cik
    accession = descriptor.accession
    name = "notes.txt"
    states[name] = {
        "state": "missing",
        "content_sha256": None,
        "byte_length": None,
        "storage_key": None,
        "retrieval": _missing_receipt(
            stable_id("sec_document", cik, accession, "archive", name),
            archive_document_url(cik, accession, name),
        ),
        "policy_reason": None,
    }

    with pytest.raises(
        FilingPackageError,
        match=r"pinned missing archive receipt source read failed: notes\.txt",
    ):
        _materialize(authority, replace(descriptor, member_states=states))


def test_materializer_rejects_receipt_or_assembly_clocks_outside_snapshot_causality(
    tmp_path: Path,
):
    authority, descriptor, _manifest_value, _index, _store, _unused = _source_fixture(
        tmp_path / "future-receipt",
        retrieval_at="2026-08-02T15:00:01.000000Z",
    )
    with pytest.raises(
        FilingPackageError,
        match="archive index receipt cannot postdate pinned source snapshot",
    ):
        _materialize(authority, descriptor)

    authority, descriptor, _manifest_value, _index, _store, _unused = _source_fixture(
        tmp_path / "early-assembly"
    )
    with pytest.raises(
        FilingPackageError,
        match="assembly cannot predate pinned source snapshot",
    ):
        materialize_filing_package_from_pinned_source(
            descriptor,
            authority=authority,
            assembled_at="2026-08-02T14:59:59.000000Z",
            policy_profile="safe_archive_inventory",
            policy_version="v1",
        )


def test_materializer_applies_retained_byte_cap_before_any_member_inflate(
    tmp_path: Path,
    monkeypatch,
):
    authority, descriptor, _manifest_value, _index, store, _unused = _source_fixture(
        tmp_path
    )
    annual_storage_key = descriptor.member_states["annual.htm"]["storage_key"]
    annual_object_key = authority._snapshot.entry_for(
        kind="archive",
        relative_path=annual_storage_key,
    ).object_key
    monkeypatch.setattr(
        "engine.fundamental_forensics.filing_package.HARD_MAX_RETAINED_MEMBER_BYTES",
        1,
    )

    with pytest.raises(FilingPackageError, match="retained-byte total exceeds"):
        _materialize(authority, descriptor)

    assert annual_object_key not in {key for key, _limit in store.bounded_reads}


def test_materializer_rejects_padded_member_gzip_at_stored_byte_boundary(
    tmp_path: Path,
):
    authority, descriptor, _manifest_value, _index, _store, _unused = _source_fixture(
        tmp_path,
        member_gzip_padding_bytes=2 * 1024 * 1024,
    )

    with pytest.raises(
        FilingPackageError,
        match=r"pinned archive member source read failed: annual\.htm",
    ):
        _materialize(authority, descriptor)
