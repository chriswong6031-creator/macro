from __future__ import annotations

import json
from pathlib import Path

import pytest

from collectors.edgar_forensics import (
    SecForensicsCollector,
    SecResponseTooLarge,
    endpoint_url,
    persist_response,
)
from collectors.fundamental_forensics_acquisition import (
    ACQUISITION_RELATIVE_ROOT,
    AcquisitionError,
    acquire_bounded_filings,
    normalize_targets,
    read_verified_submissions,
)
from collectors.sec_document_spine import (
    ArchiveResponseTooLarge,
    SecFilingArchiveCollector,
    persist_archive_document,
)
from engine.fundamental_forensics.sec_document_spine import (
    build_filing_manifests,
    with_document_retrievals,
)


RECORDED_AT = "2026-08-02T00:05:00Z"
AS_OF = "2026-08-01T23:59:59Z"


def _submissions(cik: int) -> dict:
    return {
        "cik": str(cik),
        "name": "Fixture Holdings, Inc.",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000000001-26-000001",  # Q2 2026
                    "0000000001-26-000002",  # Q1 2026
                    "0000000001-25-000003",  # prior Q (excluded by cap)
                    "0000000001-26-000004",  # FY25 K
                    "0000000001-25-000005",  # FY24 K
                    "0000000001-24-000006",  # FY23 K (excluded by cap)
                ],
                "form": ["10-Q", "10-Q", "10-Q", "10-K", "10-K", "10-K"],
                "filingDate": [
                    "2026-08-01", "2026-05-01", "2025-11-01", "2026-02-20", "2025-02-20", "2024-02-20"
                ],
                "reportDate": [
                    "2026-06-30", "2026-03-31", "2025-09-30", "2025-12-31", "2024-12-31", "2023-12-31"
                ],
                "acceptanceDateTime": [
                    "2026-08-01T16:00:00.000Z", "2026-05-01T16:00:00.000Z", "2025-11-01T16:00:00.000Z",
                    "2026-02-20T16:00:00.000Z", "2025-02-20T16:00:00.000Z", "2024-02-20T16:00:00.000Z",
                ],
                "primaryDocument": ["q2.htm", "q1.htm", "q0.htm", "k25.htm", "k24.htm", "k23.htm"],
                "isXBRL": [1, 1, 1, 1, 1, 1],
                "isInlineXBRL": [1, 1, 1, 1, 1, 1],
            }
        },
    }


class _SubmissionsCollector:
    calls: list[tuple[str, str, int | None]] = []
    fail_ciks: set[str] = set()

    def __init__(self, raw_root: Path, **kwargs) -> None:
        self.raw_root = raw_root

    def fetch(self, cik, endpoint, *, retrieved_at, max_response_bytes=None):
        cik10 = f"{int(cik):010d}"
        self.calls.append((cik10, endpoint, max_response_bytes))
        if cik10 in self.fail_ciks:
            raise RuntimeError("fixture submissions outage")
        content = json.dumps(_submissions(int(cik))).encode("utf-8")
        return persist_response(
            self.raw_root,
            cik=cik,
            endpoint=endpoint,
            url=endpoint_url(cik, endpoint),
            content=content,
            retrieved_at=retrieved_at,
        )


class _ArchiveCollector:
    calls: list[tuple[str, int | None]] = []
    oversized: bool = False

    def __init__(self, archive_root: Path, **kwargs) -> None:
        self.archive_root = archive_root

    def fetch_primary_document(self, manifest, *, retrieved_at, max_document_bytes=None):
        accession = str(manifest["filing"]["accession"])
        self.calls.append((accession, max_document_bytes))
        primary = manifest["documents"][0]
        content = b"x" * ((max_document_bytes or 0) + 1) if self.oversized else accession.encode("utf-8")
        receipt = persist_archive_document(
            self.archive_root,
            primary,
            content,
            retrieved_at=retrieved_at,
        )
        return with_document_retrievals(manifest, {primary["document_id"]: receipt.to_dict()})


def _run(tmp_path: Path, *, targets=("FXT=1",), **kwargs):
    _SubmissionsCollector.calls = []
    _SubmissionsCollector.fail_ciks = set()
    _ArchiveCollector.calls = []
    _ArchiveCollector.oversized = False
    return acquire_bounded_filings(
        targets=targets,
        raw_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        min_interval_seconds=0.1,
        submissions_collector_factory=_SubmissionsCollector,
        archive_collector_factory=_ArchiveCollector,
        **kwargs,
    )


def test_acquisition_only_fetches_submissions_and_latest_two_10k_and_10q(tmp_path: Path):
    run = _run(tmp_path)

    assert run["status"] == "complete"
    assert [(cik, endpoint) for cik, endpoint, _ in _SubmissionsCollector.calls] == [
        ("0000000001", "submissions")
    ]
    assert [accession for accession, _ in _ArchiveCollector.calls] == [
        "0000000001-26-000004", "0000000001-25-000005",  # 10-K
        "0000000001-26-000001", "0000000001-26-000002",  # 10-Q
    ]
    ticker = run["ticker_receipts"][0]
    assert ticker["status"] == "complete"
    assert ticker["forms"][0]["selected_accessions"] == [
        "0000000001-26-000004", "0000000001-25-000005"
    ]
    assert ticker["forms"][1]["selected_accessions"] == [
        "0000000001-26-000001", "0000000001-26-000002"
    ]
    assert all((tmp_path / "archive" / key).is_file() for form in ticker["forms"] for key in form["manifest_keys"])
    receipt_path = tmp_path / "archive" / ACQUISITION_RELATIVE_ROOT / run["run_id"] / "FXT.json"
    assert receipt_path.is_file()


def test_acquisition_continues_after_one_ticker_submission_failure_with_receipt(tmp_path: Path):
    _SubmissionsCollector.fail_ciks = {"0000000002"}
    # `_run` resets the fixture, so call the public function explicitly here.
    _SubmissionsCollector.calls = []
    _ArchiveCollector.calls = []
    run = acquire_bounded_filings(
        targets=("FXT=1", "BAD=2"),
        raw_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        submissions_collector_factory=_SubmissionsCollector,
        archive_collector_factory=_ArchiveCollector,
    )

    by_ticker = {item["ticker"]: item for item in run["ticker_receipts"]}
    assert by_ticker["FXT"]["status"] == "complete"
    assert by_ticker["BAD"]["status"] == "failed"
    assert by_ticker["BAD"]["failures"][0]["stage"] == "submissions"
    failed_path = tmp_path / "archive" / ACQUISITION_RELATIVE_ROOT / run["run_id"] / "BAD.json"
    assert failed_path.is_file()
    assert run["status"] == "partial"


def test_acquisition_caps_oversized_primary_before_manifest_is_marked_stored(tmp_path: Path):
    _SubmissionsCollector.calls = []
    _SubmissionsCollector.fail_ciks = set()
    _ArchiveCollector.calls = []
    _ArchiveCollector.oversized = True
    run = acquire_bounded_filings(
        targets=("FXT=1",),
        raw_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        max_submissions_bytes=4 * 1024,
        max_document_bytes=1024,
        max_ticker_bytes=8 * 1024,
        max_total_bytes=8 * 1024,
        submissions_collector_factory=_SubmissionsCollector,
        archive_collector_factory=_ArchiveCollector,
    )

    ticker = run["ticker_receipts"][0]
    assert ticker["status"] == "partial"
    assert all(form["stored_documents"] == 0 for form in ticker["forms"])
    assert all(form["manifest_keys"] for form in ticker["forms"])


def test_target_and_cached_submissions_contracts_are_strict(tmp_path: Path):
    with pytest.raises(AcquisitionError, match="multiple CIKs"):
        normalize_targets(("FXT=1", "FXT=2"))
    with pytest.raises(AcquisitionError, match="exceeds cap"):
        normalize_targets(tuple(f"T{i}=1{i}" for i in range(13)), max_tickers=12)

    _SubmissionsCollector.calls = []
    _SubmissionsCollector.fail_ciks = set()
    collector = _SubmissionsCollector(tmp_path / "raw")
    collector.fetch(1, "submissions", retrieved_at=RECORDED_AT)
    body, receipt = read_verified_submissions(tmp_path / "raw", 1)
    assert body["cik"] == "1"
    assert receipt["endpoint"] == "submissions"
    pointer = tmp_path / "raw" / "0000000001" / "submissions" / "latest.json"
    text = pointer.read_text(encoding="utf-8")
    pointer.write_text(text.replace('"object_path":"0000000001/submissions/', '"object_path":"../'), encoding="utf-8")
    with pytest.raises(AcquisitionError, match="not in the CIK namespace"):
        read_verified_submissions(tmp_path / "raw", 1)


class _NetworkResponse:
    def __init__(self, content: bytes, *, content_length: str) -> None:
        self.status_code = 200
        self.content = content
        self.headers = {"Content-Length": content_length}

    def raise_for_status(self) -> None:
        return None


class _NetworkSession:
    def __init__(self, response: _NetworkResponse) -> None:
        self.response = response
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return self.response


def test_network_collectors_refuse_declared_oversize_before_any_source_persistence(tmp_path: Path):
    submissions_session = _NetworkSession(_NetworkResponse(b'{"cik":"1"}', content_length="999"))
    submissions = SecForensicsCollector(
        tmp_path / "raw",
        user_agent="MastermindX research@example.com",
        session=submissions_session,
        max_response_bytes=16,
    )
    with pytest.raises(SecResponseTooLarge):
        submissions.fetch(1, "submissions", retrieved_at=RECORDED_AT)
    assert submissions_session.calls == 1
    assert not list((tmp_path / "raw").rglob("*.gz"))

    manifest = build_filing_manifests(_submissions(1), recorded_at=RECORDED_AT)[0]
    archive_session = _NetworkSession(_NetworkResponse(b"small", content_length="999"))
    archive = SecFilingArchiveCollector(
        tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        session=archive_session,
        max_document_bytes=16,
    )
    with pytest.raises(ArchiveResponseTooLarge):
        archive.fetch_primary_document(manifest, retrieved_at=RECORDED_AT)
    assert archive_session.calls == 1
    assert not list((tmp_path / "archive").rglob("*.gz"))
