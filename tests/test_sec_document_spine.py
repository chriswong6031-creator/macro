"""Offline contract tests for the accession-level SEC document source spine."""
from __future__ import annotations

import gzip
import hashlib

import pytest

from collectors.sec_document_spine import (
    ArchiveResponseTooLarge,
    ArchiveStoreError,
    ChecksumMismatch,
    DEFAULT_MAX_DOCUMENT_BYTES,
    HARD_MAX_ARCHIVE_RECEIPT_BYTES,
    HARD_MAX_DOCUMENT_BYTES,
    HARD_MAX_HTTP_METADATA_BYTES,
    SecFilingArchiveCollector,
    persist_archive_document,
    persist_filing_manifest,
    read_archive_document,
    read_filing_manifest,
    read_primary_document,
    receipt_storage_key,
)
from engine.fundamental_forensics.sec_document_spine import (
    FilingManifestError,
    HARD_MAX_FILING_MANIFEST_BYTES,
    HARD_MAX_ARCHIVE_INDEX_MEMBERS,
    archive_directory_url,
    archive_document_url,
    archive_index_document,
    build_filing_manifests,
    canonical_cik,
    documents_from_archive_index,
    manifest_from_json_bytes,
    manifest_json_bytes,
    select_periodic_comparables,
    with_archive_documents,
    with_document_retrievals,
)
from engine.fundamental_forensics.models import stable_id


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

    with pytest.raises(FilingManifestError, match="not UTF-8 JSON"):
        manifest_from_json_bytes(b'{"oversized_integer":' + b"9" * 5_000 + b"}")


def test_manifest_reads_reject_traversal_oversize_and_identity_mismatched_keys(tmp_path):
    manifest = build_filing_manifests(_submissions(), recorded_at=RECORDED_AT)[0]
    key = persist_filing_manifest(tmp_path, manifest)

    with pytest.raises(ArchiveStoreError, match="invalid filing manifest storage key"):
        read_filing_manifest(tmp_path, "manifests/../../outside.json")

    target = tmp_path / key
    target.write_bytes(b"x" * (HARD_MAX_FILING_MANIFEST_BYTES + 1))
    with pytest.raises(ArchiveStoreError, match="exceeds byte safety limit"):
        read_filing_manifest(tmp_path, key)

    canonical = manifest_json_bytes(manifest)
    wrong_key = key.replace("manifests/0000000001/", "manifests/0000000002/", 1)
    wrong_path = tmp_path / wrong_key
    wrong_path.parent.mkdir(parents=True, exist_ok=True)
    wrong_path.write_bytes(canonical)
    with pytest.raises(ArchiveStoreError, match="does not bind its identity"):
        read_filing_manifest(tmp_path, wrong_key)


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


def test_archive_index_expansion_shares_the_package_member_cap():
    manifest = _by_accession()["0000000001-26-000001"]
    payload = {
        "directory": {
            "item": [
                {"name": f"member-{index}.xml"}
                for index in range(HARD_MAX_ARCHIVE_INDEX_MEMBERS + 1)
            ]
        }
    }
    with pytest.raises(FilingManifestError, match="member safety limit"):
        documents_from_archive_index(manifest, payload)


def test_archive_index_document_has_the_manifest_bound_canonical_identity():
    manifest = _by_accession()["0000000001-26-000001"]
    index = archive_index_document(manifest)

    assert index["document_name"] == "index.json"
    assert index["role"] == "archive"
    assert index["archive_url"] == manifest["filing"]["archive_index_url"]
    assert index["archive_url"] == archive_document_url(
        manifest["issuer"]["cik"], manifest["filing"]["accession"], "index.json"
    )
    assert index["document_id"] == stable_id(
        "sec_document",
        manifest["issuer"]["cik"],
        manifest["filing"]["accession"],
        "archive",
        "index.json",
    )
    assert index["availability"] == "declared"
    assert index["content_sha256"] is None
    assert index["byte_length"] is None
    assert index["storage_key"] is None
    assert index["retrieval"] is None
    assert index["source_spans"] == []


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
    object_path.write_bytes(gzip.compress(b"changed! bytes", mtime=0))
    with pytest.raises(ArchiveStoreError, match="checksum mismatch"):
        read_archive_document(tmp_path, receipt)


def test_archive_receipt_reads_are_bounded_and_corruption_is_not_mislabeled_missing(tmp_path):
    document = _by_accession()["0000000001-26-000001"]["documents"][0]
    receipt = persist_archive_document(
        tmp_path, document, b"small", retrieved_at=RECORDED_AT
    )
    receipt_path = tmp_path / receipt_storage_key(receipt.receipt_id)
    receipt_path.write_bytes(b"x" * (HARD_MAX_ARCHIVE_RECEIPT_BYTES + 1))

    with pytest.raises(ArchiveStoreError, match="exceeds byte safety limit") as error:
        read_archive_document(tmp_path, receipt)
    assert "missing archive receipt" not in str(error.value)

    receipt_path.write_bytes(b'{"oversized_integer":' + b"9" * 5_000 + b"}")
    with pytest.raises(ArchiveStoreError, match="not UTF-8 JSON"):
        read_archive_document(tmp_path, receipt)


def test_archive_receipt_metadata_is_capped_before_any_durable_write(tmp_path):
    document = _by_accession()["0000000001-26-000001"]["documents"][0]
    with pytest.raises(ArchiveStoreError, match="metadata exceeds byte safety limit"):
        persist_archive_document(
            tmp_path,
            document,
            b"small",
            retrieved_at=RECORDED_AT,
            http_etag="x" * (HARD_MAX_HTTP_METADATA_BYTES + 1),
        )
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


@pytest.mark.parametrize(
    "etag", ["x" * (HARD_MAX_HTTP_METADATA_BYTES + 1), "safe\r\nInjected: yes"]
)
def test_cached_receipt_and_manifest_restore_share_http_metadata_validation(tmp_path, etag):
    manifest = _by_accession()["0000000001-26-000001"]
    document = manifest["documents"][0]
    receipt = persist_archive_document(
        tmp_path, document, b"small", retrieved_at=RECORDED_AT
    ).to_dict()
    receipt["http_etag"] = etag
    body = dict(receipt)
    body.pop("receipt_id")
    receipt["receipt_id"] = stable_id("sec_archive_receipt", body)

    with pytest.raises(ArchiveStoreError, match="metadata"):
        read_archive_document(tmp_path, receipt)
    with pytest.raises(FilingManifestError, match="HTTP metadata"):
        with_document_retrievals(manifest, {document["document_id"]: receipt})


def test_manifest_rejects_oversized_or_cross_document_retrieval_receipts(tmp_path):
    manifests = _by_accession()
    source = manifests["0000000001-26-000001"]
    target = manifests["0000000001-26-000002"]
    source_document = source["documents"][0]
    target_document = target["documents"][0]
    receipt = persist_archive_document(
        tmp_path, source_document, b"small", retrieved_at=RECORDED_AT
    )

    oversized = receipt.to_dict()
    oversized["byte_length"] = HARD_MAX_DOCUMENT_BYTES + 1
    body = dict(oversized)
    body.pop("receipt_id")
    oversized["receipt_id"] = stable_id("sec_archive_receipt", body)
    with pytest.raises(FilingManifestError, match="archive safety limit"):
        with_document_retrievals(
            source, {source_document["document_id"]: oversized}
        )

    with pytest.raises(FilingManifestError, match="identities differ"):
        with_document_retrievals(
            target, {target_document["document_id"]: receipt.to_dict()}
        )

    forged_identity = receipt.to_dict()
    forged_identity["receipt_id"] = "sec_archive_receipt_" + "0" * 64
    with pytest.raises(FilingManifestError, match="identity mismatch"):
        with_document_retrievals(
            source, {source_document["document_id"]: forged_identity}
        )

    false_missing = {
        "schema": "fundamental_forensics.sec_archive_receipt/v1",
        "status": "missing",
        "document_id": source_document["document_id"],
        "archive_url": source_document["archive_url"],
        "retrieved_at": "2026-08-01T12:00:00.000000Z",
        "http_status": 500,
        "reason": "sec_archive_document_missing",
    }
    with pytest.raises(FilingManifestError, match="observed SEC 404"):
        with_document_retrievals(
            source, {source_document["document_id"]: false_missing}
        )


class _Response:
    def __init__(
        self,
        status_code: int,
        content: bytes = b"",
        *,
        headers: dict[str, str] | None = None,
        chunks: list[object] | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = {"ETag": '"fixture"'}
        if headers:
            self.headers.update(headers)
        self._content = content
        self._chunks = chunks
        self._stream_error = stream_error
        self.iter_content_calls: list[int] = []
        self.close_calls = 0

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        self.iter_content_calls.append(chunk_size)
        chunks = self._chunks if self._chunks is not None else [self._content]
        for chunk in chunks:
            if not isinstance(chunk, bytes):
                yield chunk
                continue
            for start in range(0, len(chunk), chunk_size):
                yield chunk[start : start + chunk_size]
        if self._stream_error is not None:
            raise self._stream_error

    def close(self) -> None:
        self.close_calls += 1


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        response.url = url
        return response


class _LegacySession:
    def get(self, url, *, headers, timeout):
        raise AssertionError("an unstreamed adapter must never be used")


class _ReboundSession:
    def __init__(self, response):
        self.response = response

    def get(self, url, **kwargs):
        self.response.url = "https://untrusted.invalid/rebound"
        return self.response


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
                "stream": True,
                "allow_redirects": False,
            },
        )
    ]
    assert session.responses == []
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


def test_collector_closes_response_if_an_injected_post_get_clock_fails(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    response = _Response(200, b"ok")
    calls = 0

    def monotonic() -> float:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fixture clock failed")
        return 100.0

    collector = SecFilingArchiveCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        session=_Session([response]),
        monotonic=monotonic,
        max_attempts=1,
    )
    with pytest.raises(RuntimeError, match="fixture clock failed"):
        collector.fetch_document(manifest["documents"][0], retrieved_at=RECORDED_AT)
    assert response.close_calls == 1
    assert not list(tmp_path.rglob("*.gz"))


def test_collector_fails_closed_for_sessions_without_streaming_support(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    collector = SecFilingArchiveCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        session=_LegacySession(),
        max_attempts=1,
    )
    with pytest.raises(ArchiveStoreError, match="must support streamed responses"):
        collector.fetch_document(manifest["documents"][0], retrieved_at=RECORDED_AT)
    assert not list(tmp_path.rglob("*.gz"))


def test_collector_refuses_redirects_and_mismatched_final_response_urls(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    document = manifest["documents"][0]

    redirected = _Response(302, b"redirect body", headers={"Location": "https://example.com"})
    with pytest.raises(ArchiveStoreError, match="redirects are refused"):
        SecFilingArchiveCollector(
            tmp_path / "redirect",
            user_agent="MastermindX research@example.com",
            session=_Session([redirected]),
            max_attempts=1,
        ).fetch_document(document, retrieved_at=RECORDED_AT)
    assert redirected.close_calls == 1

    rebound = _Response(200, b"untrusted body")
    with pytest.raises(ArchiveStoreError, match="URL does not match"):
        SecFilingArchiveCollector(
            tmp_path / "rebound",
            user_agent="MastermindX research@example.com",
            session=_ReboundSession(rebound),
            max_attempts=1,
        ).fetch_document(document, retrieved_at=RECORDED_AT)
    assert rebound.close_calls == 1
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_collector_rejects_oversized_response_metadata_before_persistence(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    response = _Response(
        200,
        b"safe body",
        headers={"ETag": "x" * (HARD_MAX_HTTP_METADATA_BYTES + 1)},
    )
    with pytest.raises(ArchiveStoreError, match="metadata exceeds byte safety limit"):
        SecFilingArchiveCollector(
            tmp_path,
            user_agent="MastermindX research@example.com",
            session=_Session([response]),
            max_attempts=1,
        ).fetch_document(manifest["documents"][0], retrieved_at=RECORDED_AT)
    assert response.close_calls == 1
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_collector_stream_cap_rejects_an_oversized_body_without_content_length(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    response = _Response(200, b"12345")
    collector = SecFilingArchiveCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        session=_Session([response]),
        max_document_bytes=4,
        max_attempts=1,
    )

    with pytest.raises(ArchiveResponseTooLarge, match="5 > 4"):
        collector.fetch_document(manifest["documents"][0], retrieved_at=RECORDED_AT)
    assert response.iter_content_calls == [5]
    assert response.close_calls == 1
    assert not list(tmp_path.rglob("*.gz"))


def test_collector_default_and_hard_archive_caps_are_finite(tmp_path):
    collector = SecFilingArchiveCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        session=_Session([]),
    )
    assert collector.max_document_bytes == DEFAULT_MAX_DOCUMENT_BYTES
    with pytest.raises(ValueError, match="no larger than"):
        SecFilingArchiveCollector(
            tmp_path,
            user_agent="MastermindX research@example.com",
            max_document_bytes=HARD_MAX_DOCUMENT_BYTES + 1,
        )


def test_collector_rejects_non_bytes_stream_chunks_and_persists_nothing(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    response = _Response(200, chunks=[b"ok", "not bytes"])
    collector = SecFilingArchiveCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        session=_Session([response]),
        max_attempts=1,
    )

    with pytest.raises(ArchiveStoreError, match="stream yielded non-bytes"):
        collector.fetch_document(manifest["documents"][0], retrieved_at=RECORDED_AT)
    assert response.close_calls == 1
    assert not list(tmp_path.rglob("*.gz"))


def test_collector_closes_a_response_when_its_stream_fails(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    response = _Response(200, stream_error=OSError("fixture stream broke"))
    collector = SecFilingArchiveCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        session=_Session([response]),
        max_attempts=1,
    )

    with pytest.raises(ArchiveStoreError, match="stream failed"):
        collector.fetch_document(manifest["documents"][0], retrieved_at=RECORDED_AT)
    assert response.close_calls == 1
    assert not list(tmp_path.rglob("*.gz"))


def test_collector_closes_responses_for_success_missing_declared_oversize_and_transient(tmp_path):
    manifest = _by_accession()["0000000001-26-000001"]
    document = manifest["documents"][0]

    success = _Response(200, b"ok")
    SecFilingArchiveCollector(
        tmp_path / "success",
        user_agent="MastermindX research@example.com",
        session=_Session([success]),
    ).fetch_document(document, retrieved_at=RECORDED_AT)
    assert success.close_calls == 1

    missing = _Response(404)
    SecFilingArchiveCollector(
        tmp_path / "missing",
        user_agent="MastermindX research@example.com",
        session=_Session([missing]),
    ).fetch_document(document, retrieved_at=RECORDED_AT)
    assert missing.close_calls == 1

    declared_oversize = _Response(200, headers={"Content-Length": "5"})
    with pytest.raises(ArchiveResponseTooLarge):
        SecFilingArchiveCollector(
            tmp_path / "oversize",
            user_agent="MastermindX research@example.com",
            session=_Session([declared_oversize]),
            max_document_bytes=4,
        ).fetch_document(document, retrieved_at=RECORDED_AT)
    assert declared_oversize.close_calls == 1

    transient = _Response(429)
    with pytest.raises(ArchiveStoreError, match="failed after retries"):
        SecFilingArchiveCollector(
            tmp_path / "transient",
            user_agent="MastermindX research@example.com",
            session=_Session([transient]),
            max_attempts=1,
        ).fetch_document(document, retrieved_at=RECORDED_AT)
    assert transient.close_calls == 1


def test_archive_object_inflation_is_bounded_by_the_trusted_receipt_length(tmp_path):
    document = _by_accession()["0000000001-26-000001"]["documents"][0]
    receipt = persist_archive_document(
        tmp_path, document, b"small", retrieved_at=RECORDED_AT
    )
    object_path = tmp_path / receipt.storage_key
    object_path.write_bytes(gzip.compress(b"x" * 1_000_000, mtime=0))

    with pytest.raises(ArchiveStoreError, match="exceeds trusted receipt"):
        read_archive_document(tmp_path, receipt)

    object_path.write_bytes(b"not a gzip object")
    with pytest.raises(ArchiveStoreError, match="corrupt compressed"):
        read_archive_document(tmp_path, receipt)


def test_read_archive_document_rejects_a_forged_huge_receipt_before_inflation(tmp_path):
    document = _by_accession()["0000000001-26-000001"]["documents"][0]
    receipt = persist_archive_document(
        tmp_path, document, b"small", retrieved_at=RECORDED_AT
    )
    forged = receipt.to_dict()
    forged["byte_length"] = HARD_MAX_DOCUMENT_BYTES + 1
    identity_body = dict(forged)
    identity_body.pop("receipt_id")
    forged["receipt_id"] = stable_id("sec_archive_receipt", identity_body)

    with pytest.raises(ArchiveStoreError, match="no larger than"):
        read_archive_document(tmp_path, forged)
