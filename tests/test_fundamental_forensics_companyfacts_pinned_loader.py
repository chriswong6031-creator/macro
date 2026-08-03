"""Focused source-snapshot contracts for Company Facts ledger materialization."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from collectors.edgar_forensics import persist_response
from collectors.fundamental_forensics_companyfacts import (
    acquire_companyfacts,
    read_companyfacts_manifest,
)
from engine.fundamental_forensics.companyfacts_ledger import (
    CompanyFactsConversionSourceBundle,
    CompanyFactsLedgerConversionConfig,
    CompanyFactsLedgerError,
    PinnedSubmissionsSource,
    load_companyfacts_ledger_from_pinned_source,
)
from engine.fundamental_forensics.filing_attestation import PinnedSourceAuthority
from engine.fundamental_forensics.source_sync import sync_source_roots
from engine.research_vault.r2_store import LocalStore


CIK = "0000000001"
RECENT_ACCESSION = "0000000001-26-000001"
OLDER_ACCESSION = "0000000001-23-000001"
OLDER_NAME = "CIK0000000001-submissions-001.json"
SOURCE_AT = "2026-08-02T15:00:00.000000Z"
RECORDED_AT = "2026-08-02T16:00:00.000000Z"


class _Response:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, body: bytes, *, url: str) -> None:
        self.body = body
        self.url = url

    def iter_content(self, *, chunk_size: int):
        del chunk_size
        yield self.body

    def close(self) -> None:
        return None


def _body(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _receipt_path(object_path: str) -> str:
    return str(Path(object_path).with_suffix(".receipt.json"))


def _companyfacts_body(*, recent_value_token: str = "120") -> bytes:
    content = _body(
        {
            "cik": 1,
            "entityName": "Pinned Fixture",
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {
                            "USD": [
                                {
                                    "start": "2022-01-01",
                                    "end": "2022-12-31",
                                    "val": 100,
                                    "accn": OLDER_ACCESSION,
                                    "fy": 2022,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2023-02-20",
                                },
                                {
                                    "start": "2025-01-01",
                                    "end": "2025-12-31",
                                    "val": "__EXACT_RECENT_VALUE__",
                                    "accn": RECENT_ACCESSION,
                                    "fy": 2025,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2026-02-20",
                                },
                            ]
                        }
                    }
                }
            },
        }
    )
    return content.replace(
        b'"__EXACT_RECENT_VALUE__"', recent_value_token.encode("ascii")
    )


def _columns(rows: list[tuple[str, str]]) -> dict[str, list[str]]:
    return {
        "accessionNumber": [accession for accession, _ in rows],
        "acceptanceDateTime": [accepted_at for _, accepted_at in rows],
    }


def _fixture(
    tmp_path: Path,
    *,
    snapshot_at: str = RECORDED_AT,
    companyfacts_gzip_padding_bytes: int = 0,
    companyfacts_recent_value_token: str = "120",
) -> tuple[PinnedSourceAuthority, CompanyFactsConversionSourceBundle]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw_root = tmp_path / "raw"
    archive_root = tmp_path / "archive"
    raw_root.mkdir()
    archive_root.mkdir()
    result = acquire_companyfacts(
        targets=("PINF=1",),
        raw_root=raw_root,
        archive_root=archive_root,
        user_agent="MastermindX research@example.com",
        source_snapshot_at=SOURCE_AT,
        recorded_at=SOURCE_AT,
        fetcher=lambda url, **kwargs: _Response(
            _companyfacts_body(recent_value_token=companyfacts_recent_value_token),
            url=url,
        ),
        utc_now=lambda: datetime(2026, 8, 2, 15, tzinfo=timezone.utc),
    )
    companyfacts_receipt = result["run"]["ticker_receipts"][0]
    manifest = read_companyfacts_manifest(
        archive_root, companyfacts_receipt["manifest_key"]
    )
    # Collector publication uses this local coordination sentinel.  It is not
    # immutable source evidence and source-sync correctly refuses hidden paths.
    (archive_root / "wave3_companyfacts" / ".manifest_publish.lock").unlink(
        missing_ok=True
    )

    recent = persist_response(
        raw_root,
        cik=CIK,
        endpoint="submissions",
        url=f"https://data.sec.gov/submissions/CIK{CIK}.json",
        content=_body(
            {
                "cik": CIK,
                "filings": {
                    "recent": _columns(
                        [(RECENT_ACCESSION, "2026-02-20T16:00:00.000000Z")]
                    ),
                    "files": [{"name": OLDER_NAME}],
                },
            }
        ),
        retrieved_at=SOURCE_AT,
    )
    older = persist_response(
        raw_root,
        cik=CIK,
        endpoint="submissions",
        url=f"https://data.sec.gov/submissions/{OLDER_NAME}",
        content=_body(
            {
                "cik": CIK,
                **_columns([(OLDER_ACCESSION, "2023-02-20T16:00:00.000000Z")]),
            }
        ),
        retrieved_at=SOURCE_AT,
    )
    # ``persist_response`` now points mutable latest.json at the *older*
    # response.  The loader must ignore it and use the named current receipt.
    bundle = CompanyFactsConversionSourceBundle(
        cik=CIK,
        companyfacts_manifest_path=companyfacts_receipt["manifest_key"],
        companyfacts_capture_path=manifest["source"]["capture_receipt_key"],
        companyfacts_response_path=manifest["source"]["response_object_path"],
        recent_submissions=PinnedSubmissionsSource(
            source_name="recent",
            receipt_path=_receipt_path(recent.object_path),
            object_path=recent.object_path,
            is_older=False,
        ),
        older_submissions=(
            PinnedSubmissionsSource(
                source_name=OLDER_NAME,
                receipt_path=_receipt_path(older.object_path),
                object_path=older.object_path,
                is_older=True,
            ),
        ),
    )
    if companyfacts_gzip_padding_bytes:
        response_object = raw_root / bundle.companyfacts_response_path
        response_object.write_bytes(
            response_object.read_bytes() + (b"\0" * companyfacts_gzip_padding_bytes)
        )
    store = LocalStore(tmp_path / "private-source")
    snapshot = sync_source_roots(
        raw_root=raw_root,
        archive_root=archive_root,
        store=store,
        snapshot_at=snapshot_at,
    )
    return PinnedSourceAuthority(store=store, snapshot_id=snapshot.snapshot_id), bundle


def test_materializes_only_named_pinned_members_and_ignores_latest(tmp_path: Path) -> None:
    authority, bundle = _fixture(tmp_path)

    conversion = load_companyfacts_ledger_from_pinned_source(
        authority=authority,
        source_bundle=bundle,
        submissions_recorded_at=RECORDED_AT,
    )

    assert conversion.receipt.cik == CIK
    assert conversion.receipt.older_submissions_file_count == 1
    assert conversion.receipt.unmapped_accessions == ()
    assert [source.source_name for source in conversion.submission_sources] == [
        "recent",
        OLDER_NAME,
    ]


def test_fractional_exact_projection_uses_verified_legacy_witness(
    tmp_path: Path,
) -> None:
    authority, bundle = _fixture(
        tmp_path,
        companyfacts_recent_value_token="123.4500000000000000000001",
    )

    conversion = load_companyfacts_ledger_from_pinned_source(
        authority=authority,
        source_bundle=bundle,
        submissions_recorded_at=RECORDED_AT,
    )

    recent = next(
        item for item in conversion.occurrences if item.accession == RECENT_ACCESSION
    )
    assert recent.occurrence.parsed_value == "123.4500000000000000000001"
    assert conversion.receipt.companyfacts_sha256 != conversion.receipt.input_sha256


def test_float_collision_cannot_collapse_two_pinned_exact_sources(
    tmp_path: Path,
) -> None:
    # Both lexemes decode to the same IEEE-754 float under the collector's
    # established manifest projection.  Response SHA and the exact Decimal
    # projection must still keep their semantic outcomes distinct.
    first_authority, first_bundle = _fixture(
        tmp_path / "first",
        companyfacts_recent_value_token="9007199254740992.0",
    )
    second_authority, second_bundle = _fixture(
        tmp_path / "second",
        companyfacts_recent_value_token="9007199254740993.0",
    )
    first_manifest = json.loads(
        first_authority.read_file(
            kind="archive",
            relative_path=first_bundle.companyfacts_manifest_path,
            maximum_bytes=1024 * 1024,
        ).content
    )
    second_manifest = json.loads(
        second_authority.read_file(
            kind="archive",
            relative_path=second_bundle.companyfacts_manifest_path,
            maximum_bytes=1024 * 1024,
        ).content
    )
    assert first_manifest["source"]["logical_sha256"] == second_manifest["source"]["logical_sha256"]
    assert first_manifest["source"]["fact_occurrence_sha256"] == second_manifest["source"]["fact_occurrence_sha256"]
    assert first_manifest["source"]["response_sha256"] != second_manifest["source"]["response_sha256"]

    first = load_companyfacts_ledger_from_pinned_source(
        authority=first_authority,
        source_bundle=first_bundle,
        submissions_recorded_at=RECORDED_AT,
    )
    second = load_companyfacts_ledger_from_pinned_source(
        authority=second_authority,
        source_bundle=second_bundle,
        submissions_recorded_at=RECORDED_AT,
    )
    first_recent = next(
        item for item in first.occurrences if item.accession == RECENT_ACCESSION
    )
    second_recent = next(
        item for item in second.occurrences if item.accession == RECENT_ACCESSION
    )
    assert first_recent.occurrence.parsed_value == "9007199254740992"
    assert second_recent.occurrence.parsed_value == "9007199254740993"
    assert first.receipt.companyfacts_sha256 == second.receipt.companyfacts_sha256
    assert first.receipt.input_sha256 != second.receipt.input_sha256
    assert first.receipt.output_sha256 != second.receipt.output_sha256


def test_requires_every_declared_older_source_before_loading_it(tmp_path: Path) -> None:
    authority, bundle = _fixture(tmp_path)
    incomplete = CompanyFactsConversionSourceBundle(
        cik=bundle.cik,
        companyfacts_manifest_path=bundle.companyfacts_manifest_path,
        companyfacts_capture_path=bundle.companyfacts_capture_path,
        companyfacts_response_path=bundle.companyfacts_response_path,
        recent_submissions=bundle.recent_submissions,
    )

    with pytest.raises(CompanyFactsLedgerError, match="declared older Submissions"):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=incomplete,
            submissions_recorded_at=RECORDED_AT,
        )


def test_rejects_a_crosswired_companyfacts_response_path(tmp_path: Path) -> None:
    authority, bundle = _fixture(tmp_path)
    crosswired = CompanyFactsConversionSourceBundle(
        cik=bundle.cik,
        companyfacts_manifest_path=bundle.companyfacts_manifest_path,
        companyfacts_capture_path=bundle.companyfacts_capture_path,
        companyfacts_response_path="0000000001/companyfacts_v3/objects/aa/crosswired.json.gz",
        recent_submissions=bundle.recent_submissions,
        older_submissions=bundle.older_submissions,
    )

    with pytest.raises(CompanyFactsLedgerError, match="response path does not bind capture"):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=crosswired,
            submissions_recorded_at=RECORDED_AT,
        )


def test_rejects_a_tampered_named_pinned_member(tmp_path: Path) -> None:
    authority, bundle = _fixture(tmp_path)
    source_entry = authority._snapshot.entry_for(
        kind="raw", relative_path=bundle.recent_submissions.receipt_path
    )
    assert authority._store.put_bytes(source_entry.object_key, b"tampered") is True

    with pytest.raises(CompanyFactsLedgerError, match="Submissions recent receipt pinned source read failed"):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=bundle,
            submissions_recorded_at=RECORDED_AT,
        )


def test_rejects_a_missing_named_pinned_member(tmp_path: Path) -> None:
    authority, bundle = _fixture(tmp_path)
    source_entry = authority._snapshot.entry_for(
        kind="raw", relative_path=bundle.recent_submissions.object_path
    )
    authority._store._p(source_entry.object_key).unlink()

    with pytest.raises(CompanyFactsLedgerError, match="Submissions recent response pinned gzip source read failed"):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=bundle,
            submissions_recorded_at=RECORDED_AT,
        )


def test_rejects_source_snapshot_and_retention_clock_causality_violations(
    tmp_path: Path,
) -> None:
    authority, bundle = _fixture(
        tmp_path / "predated-source",
        snapshot_at="2026-08-02T14:00:00.000000Z",
    )
    with pytest.raises(
        CompanyFactsLedgerError,
        match="manifest clock cannot be after pinned source snapshot_at",
    ):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=bundle,
            submissions_recorded_at="2026-08-02T14:00:00.000000Z",
        )

    authority, bundle = _fixture(tmp_path / "future-retention")
    with pytest.raises(
        CompanyFactsLedgerError,
        match="submissions_recorded_at cannot be after pinned source snapshot_at",
    ):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=bundle,
            submissions_recorded_at="2026-08-02T16:00:01.000000Z",
        )


def test_rehydrates_low_level_mutated_source_and_config_nominals_before_reads(
    tmp_path: Path,
) -> None:
    authority, bundle = _fixture(tmp_path / "bundle")
    object.__setattr__(bundle.recent_submissions, "receipt_path", "latest.json")
    with pytest.raises(CompanyFactsLedgerError, match="mutable latest pointer"):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=bundle,
            submissions_recorded_at=RECORDED_AT,
        )

    authority, bundle = _fixture(tmp_path / "config")
    config = CompanyFactsLedgerConversionConfig()
    object.__setattr__(config, "max_payload_bytes", 0)
    with pytest.raises(CompanyFactsLedgerError, match="max_payload_bytes"):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=bundle,
            submissions_recorded_at=RECORDED_AT,
            config=config,
        )


def test_rejects_padded_gzip_before_it_can_bypass_aggregate_source_budget(
    tmp_path: Path,
) -> None:
    authority, bundle = _fixture(
        tmp_path,
        companyfacts_gzip_padding_bytes=2 * 1024 * 1024,
    )

    with pytest.raises(
        CompanyFactsLedgerError,
        match="Company Facts response pinned gzip source read failed",
    ):
        load_companyfacts_ledger_from_pinned_source(
            authority=authority,
            source_bundle=bundle,
            submissions_recorded_at=RECORDED_AT,
            config=CompanyFactsLedgerConversionConfig(
                max_payload_bytes=8 * 1024,
                max_total_input_bytes=20 * 1024,
            ),
        )
