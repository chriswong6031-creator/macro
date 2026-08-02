"""Offline contract tests for the accession-level SEC document source spine."""
from __future__ import annotations

import gzip
import hashlib

import pytest

from collectors.sec_document_spine import (
    ArchiveStoreError,
    ChecksumMismatch,
    SecFilingArchiveCollector,
    persist_archive_document,
    persist_filing_manifest,
    read_archive_document,
    read_filing_manifest,
    read_primary_document,
)
from engine.fundamental_forensics.sec_document_spine import (
    FilingManifestError,
    archive_directory_url,
    build_filing_manifests,
    canonical_cik,
    documents_from_archive_index,
    manifest_from_json_bytes,
    manifest_json_bytes,
    select_periodic_comparables,
    with_archive_documents,
)


RECORDED_AT = "2026-08-01T12:00:00Z"


@pytest.mark.parametrize(
    "value",
    ("0", "0000000000", "١", "１２", "1\u0662", "1e2", "-1"),
)
def test_sec_identifiers_are_ascii_decimal_only(value: str):
    with pytest.raises(FilingManifestError, match="invalid CIK"):
        canonical_cik(value)


@pytest.mark.parametrize(
    "accession",
    (
        "٠٠٠٠٠٠٠٠٠١-26-000001",
        "0000000001-٢٦-000001",
        "0000000001-26-٠٠٠٠٠١",
    ),
)
def test_accession_segments_are_ascii_decimal_only(accession: str):
    with pytest.raises(FilingManifestError, match="invalid accession"):
        archive_directory_url(1, accession)


def test_sec_cik_range_is_positive_and_ten_digit_bounded() -> None:
    assert canonical_cik(1) == "0000000001"
    assert canonical_cik("9999999999") == "9999999999"


def _submissions() -> dict:
    return {
        "cik": "1",
        "name": "Fixture Holdings, Inc.",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000000001-26-000004",  # 10-Q/A, direct lineage is inferred
                    "0000000001-26-000001",  # original Q1 10-Q
                    "0000000001-26-000002",  # original Q2 10-Q
                    "0000000001-26-000003",  # 10-K current period
                    "0000000001-26-000005",  # unknown-parent amendment
                ],
                "form": ["10-Q/A", "10-Q", "10-Q", "10-K", "10-K/A"],
                "filingDate": [
                    "2026-05-15", "2026-05-01", "2026-08-01", "2026-02-20", "2026-02-25"
                ],
                "reportDate": [
                    "2026-03-31", "2026-03-31", "2026-06-30", "2025-12-31", "2024-12-31"
                ],
                "acceptanceDateTime": [
                    "2026-05-15T16:00:00.000Z",
                    "2026-05-01T16:00:00.000Z",
                    "2026-08-01T16:00:00.000Z",
                    "2026-02-20T16:00:00.000Z",
                    "2026-02-25T16:00:00.000Z",
                ],
                "primaryDocument": [
                    "q1a.htm", "q1.htm", "q2.htm", "annual.htm", "prior-a.htm"
                ],
                "isXBRL": [1, 1, 1, 1, 1],
                "isInlineXBRL": [1, 1, 1, 1, 1],
            }
        },
    }


def _by_accession() -> dict[str, dict]:
    return {
        item["filing"]["accession"]: item
        for item in build_filing_manifests(_submissions(), recorded_at=RECORDED_AT)
    }


def test_filing_manifest_has_explicit_three_clocks_and_conservative_amendment_lineage():
    manifests = _by_accession()
    original = manifests["0000000001-26-000001"]
    amendment = manifests["0000000001-26-000004"]
    unresolved = manifests["0000000001-26-000005"]

    assert original["clocks"] == {
        "accepted_at": "2026-05-01T16:00:00.000000Z",
        "filed_on": "2026-05-01",
        "recorded_at": "2026-08-01T12:00:00.000000Z",
    }
    assert original["lineage"] == {
        "is_amendment": False,
        "amends_accession": None,
        "relationship": "original",
    }
    assert amendment["lineage"] == {
        "is_amendment": True,
        "amends_accession": "0000000001-26-000001",
        "relationship": "inferred_same_form_report_period",
    }
    assert unresolved["lineage"] == {
        "is_amendment": True,
        "amends_accession": None,
        "relationship": "unresolved",
    }
    assert amendment["documents"][0]["archive_url"].endswith("/1/000000000126000004/q1a.htm")


def test_safe_relative_primary_document_path_is_preserved_without_allowing_traversal():
    submissions = _submissions()
    submissions["filings"]["recent"]["primaryDocument"][0] = "xslF345X03/edgar.xml"
    manifest = next(
        item
        for item in build_filing_manifests(submissions, recorded_at=RECORDED_AT)
        if item["filing"]["accession"] == "0000000001-26-000004"
    )
    primary = manifest["documents"][0]
    assert primary["document_name"] == "xslF345X03/edgar.xml"
    assert primary["archive_url"].endswith("/xslF345X03/edgar.xml")

    for unsafe in (
        "../edgar.xml",
        "/edgar.xml",
        "safe/../edgar.xml",
        "safe\\edgar.xml",
        "edgar.xml?x=1",
    ):
        broken = _submissions()
        broken["filings"]["recent"]["primaryDocument"][0] = unsafe
        with pytest.raises(FilingManifestError, match="unsafe archive document name"):
            build_filing_manifests(broken, recorded_at=RECORDED_AT)


def test_manifest_round_trip_and_source_array_order_are_deterministic(tmp_path):
    left = build_filing_manifests(_submissions(), recorded_at=RECORDED_AT)
    shuffled = _submissions()
    for values in shuffled["filings"]["recent"].values():
        if isinstance(values, list):
            values.reverse()
    right = build_filing_manifests(shuffled, recorded_at=RECORDED_AT)
    left_bytes = [manifest_json_bytes(item) for item in left]
    right_bytes = [manifest_json_bytes(item) for item in right]
    assert left_bytes == right_bytes

    key = persist_filing_manifest(tmp_path, left[0])
    assert read_filing_manifest(tmp_path, key) == left[0]
    assert manifest_from_json_bytes(left_bytes[0]) == left[0]
    assert (tmp_path / key).read_bytes() == left_bytes[0]


def test_periodic_selector_uses_acceptance_time_and_latest_amended_period_version():
    manifests = build_filing_manifests(_submissions(), recorded_at=RECORDED_AT)
    selected = select_periodic_comparables(
        manifests,
        form="10-Q",
        as_of="2026-06-01T00:00:00Z",
        count=2,
    )
    assert [item["filing"]["accession"] for item in selected] == ["0000000001-26-000004"]

    selected = select_periodic_comparables(manifests, form="10-Q", count=2)
    assert [item["filing"]["accession"] for item in selected] == [
        "0000000001-26-000002", "0000000001-26-000004"
    ]
    with pytest.raises(FilingManifestError, match="10-K or 10-Q"):
        select_periodic_comparables(manifests, form="8-K")


def test_periodic_selector_can_scope_a_cik_manifest_set_to_a_ticker():
    manifests = build_filing_manifests(
        _submissions(), ticker="fxt", recorded_at=RECORDED_AT
    )
    selected = select_periodic_comparables(manifests, form="10-Q", ticker="FXT")
    assert selected[0]["issuer"]["ticker"] == "FXT"
    assert select_periodic_comparables(manifests, form="10-Q", ticker="OTHER") == ()


def test_archive_index_expansion_is_metadata_only_and_preserves_canonical_primary():
    manifest = _by_accession()["0000000001-26-000001"]
    documents = documents_from_archive_index(
        manifest,
        {
            "directory": {
                "item": [
                    {"name": "FilingSummary.xml"},
                    {"name": "q1.htm"},
                    {"name": "exhibit-99.htm"},
                ]
            }
        },
    )
    expanded = with_archive_documents(manifest, documents)
    assert [(item["role"], item["document_name"]) for item in expanded["documents"]] == [
        ("primary", "q1.htm"),
        ("archive", "FilingSummary.xml"),
        ("archive", "exhibit-99.htm"),
    ]
    assert all(item["availability"] == "declared" for item in expanded["documents"])


def test_archive_store_is_idempotent_then_atomically_repairs_a_corrupt_object(tmp_path):
    document = _by_accession()["0000000001-26-000001"]["documents"][0]
    content = b"<html>Q1 filing source</html>"
    kwargs = dict(document=document, content=content, retrieved_at=RECORDED_AT)
    first = persist_archive_document(tmp_path, **kwargs)
    second = persist_archive_document(tmp_path, **kwargs)
    assert first == second
    assert len(list((tmp_path / "objects").rglob("*.gz"))) == 1
    assert len(list((tmp_path / "receipts").rglob("*.json"))) == 1
    assert read_archive_document(tmp_path, first) == content

    object_path = tmp_path / first.storage_key
    object_path.write_bytes(b"truncated")
    repaired = persist_archive_document(tmp_path, **kwargs)
    assert repaired == first
    assert read_archive_document(tmp_path, repaired) == content
    assert not list(tmp_path.rglob("*.tmp"))


def test_bad_checksum_and_checksum_corruption_fail_closed(tmp_path):
    document = _by_accession()["0000000001-26-000001"]["documents"][0]
    content = b"original bytes"
    with pytest.raises(ChecksumMismatch):
        persist_archive_document(
            tmp_path,
            document,
            content,
            retrieved_at=RECORDED_AT,
            expected_sha256="0" * 64,
        )
    assert not list(tmp_path.rglob("*.gz"))

    receipt = persist_archive_document(tmp_path, document, content, retrieved_at=RECORDED_AT)
    object_path = tmp_path / receipt.storage_key
    # Valid gzip, wrong uncompressed checksum: existence and decompression alone
    # are intentionally not enough to trust a content-addressed source object.
    object_path.write_bytes(gzip.compress(b"different bytes", mtime=0))
    with pytest.raises(ArchiveStoreError, match="checksum mismatch"):
        read_archive_document(tmp_path, receipt)


class _Response:
    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content
        self.headers = {"ETag": '"fixture"'}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_collector_persists_exact_primary_url_and_missing_docs_are_explicit(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    primary = manifest["documents"][0]
    session = _Session([_Response(200, b"<html>primary</html>")])
    collector = SecFilingArchiveCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        session=session,
    )
    materialized = collector.fetch_primary_document(manifest, retrieved_at=RECORDED_AT)
    stored = materialized["documents"][0]
    assert session.calls == [
        (
            primary["archive_url"],
            {
                "headers": {
                    "User-Agent": "MastermindX research@example.com",
                    "Accept-Encoding": "gzip, deflate",
                },
                "timeout": 30.0,
            },
        )
    ]
    assert stored["availability"] == "stored"
    assert stored["source_spans"][0]["locator"] == "bytes:0-20"
    assert stored["source_spans"][0]["text_sha256"] == hashlib.sha256(
        b"<html>primary</html>"
    ).hexdigest()
    assert read_primary_document(tmp_path, materialized) == b"<html>primary</html>"

    missing = SecFilingArchiveCollector(
        tmp_path / "missing",
        user_agent="MastermindX research@example.com",
        session=_Session([_Response(404)]),
    ).fetch_primary_document(manifest, retrieved_at=RECORDED_AT)
    missing_doc = missing["documents"][0]
    assert missing_doc["availability"] == "missing"
    assert missing_doc["retrieval"]["status"] == "missing"
    assert missing_doc["source_spans"] == []
    assert not list((tmp_path / "missing").rglob("*.gz"))


def test_collector_retries_transient_response_using_injected_pacing_hooks(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    session = _Session([_Response(429), _Response(200, b"ok")])
    waits: list[float] = []
    collector = SecFilingArchiveCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        session=session,
        sleeper=waits.append,
        monotonic=lambda: 100.0,
    )
    receipt = collector.fetch_document(manifest["documents"][0], retrieved_at=RECORDED_AT)
    assert receipt.status == "retrieved"
    assert len(session.calls) == 2
    assert waits == pytest.approx([1, 0.12])
