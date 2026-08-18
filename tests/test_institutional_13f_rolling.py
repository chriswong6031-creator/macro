"""Focused contracts for bounded rolling institutional 13F ingestion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import pytest
import yaml

import scripts.run_institutional_13f_rolling as rolling_runner
from engine.institutional_census.catalog import load_catalog_generation
from engine.institutional_census.models import (
    HOLDING_BUCKET_ROLES,
    canonical_json_bytes,
    catalog_pointer_key,
)
from engine.institutional_census.rolling import (
    MAX_ACCESSIONS,
    MAX_SEC_RESPONSE_BYTES,
    MAX_SEC_RUN_RESPONSE_BYTES,
    ROLLING_CHECKPOINT_KEY,
    ROLLING_CHECKPOINT_SCHEMA,
    SYNTHETIC_INFOTABLE_SK_BASE,
    Institutional13FRollingError,
    PacedFetch,
    decode_framed_evidence,
    project_catalog_rows,
    run_rolling_ingestion,
)
from engine.institutional_census.sec_sources import (
    COVER_PAGE_COLUMNS,
    HOLDING_COLUMNS,
    INCLUDED_MANAGER_COLUMNS,
    REPORTED_BY_COLUMNS,
    SUBMISSION_COLUMNS,
    SUMMARY_PAGE_COLUMNS,
    BulkTables,
    FilingDiscovery,
    parse_filing_package,
)
from engine.institutional_census.storage import (
    load_raw_evidence,
    publish_raw_evidence,
)
from engine.research_vault.r2_store import LocalStore
from scripts.run_institutional_13f_rolling import main as rolling_main

FIXTURES = Path(__file__).parent / "fixtures" / "institutional_13f"
ACCESSION = "0001398344-26-013841"
SECOND_ACCESSION = "0001398344-26-013842"
CIK = "0001792167"
PERIOD = "2025-12-31"
ACCEPTED_AT = "2026-08-07T17:25:16-04:00"


def _index_url(accession: str) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/1792167/"
        f"{accession.replace('-', '')}/{accession}-index.htm"
    )


def _atom(accessions: list[str]) -> bytes:
    entries = []
    for accession in accessions:
        entries.append(
            f"""
            <entry>
              <title>13F-HR/A - Meeder Advisory Services, Inc. ({CIK}) (Filer)</title>
              <link rel="alternate" href="{_index_url(accession)}"/>
              <summary type="html">Filed: 2026-08-07 AccNo: {accession}</summary>
              <updated>{ACCEPTED_AT}</updated>
              <category term="13F-HR/A"/><id>{accession}</id>
            </entry>
            """
        )
    return (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
        + "".join(entries)
        + "</feed>"
    ).encode("utf-8")


def _package(accession: str) -> dict[str, bytes]:
    original_compact = ACCESSION.replace("-", "")
    compact = accession.replace("-", "")
    index = (FIXTURES / "filing_index.json").read_bytes()
    header = (FIXTURES / f"{ACCESSION}-index-headers.html").read_bytes()
    if accession != ACCESSION:
        index = index.replace(ACCESSION.encode(), accession.encode()).replace(
            original_compact.encode(), compact.encode()
        )
        header = header.replace(ACCESSION.encode(), accession.encode())
    return {
        "index.json": index,
        f"{accession}-index-headers.html": header,
        "primary_doc.xml": (FIXTURES / "primary_doc.xml").read_bytes(),
        "information_table.xml": (FIXTURES / "information_table.xml").read_bytes(),
    }


class _FixtureFetch:
    def __init__(
        self,
        accessions: list[str],
        *,
        atom_error: bool = False,
        atom_accessions: list[str] | None = None,
    ) -> None:
        self.accessions = list(accessions)
        self.atom_error = atom_error
        # The Atom feed is decoupled from the fetchable filing packages so a
        # test can hand Atom strictly fewer entries than --max-accessions --
        # which is what makes the scan complete via short_page -- while still
        # serving every accession the run actually selects.
        self.atom_accessions = list(
            accessions if atom_accessions is None else atom_accessions
        )
        self.calls: list[str] = []
        self.response_bytes = 0
        self.packages = {item.replace("-", ""): _package(item) for item in accessions}

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if "browse-edgar" in url:
            if self.atom_error:
                raise RuntimeError("simulated Atom outage")
            body = _atom(self.atom_accessions)
        else:
            parsed = urlparse(url)
            parts = parsed.path.split("/")
            compact = parts[-2]
            body = self.packages[compact][parts[-1]]
        self.response_bytes += len(body)
        return body


class _FakeMonotonic:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class _RecordingStore:
    """Structural strict-store proxy that records every conditional write."""

    def __init__(self, inner: LocalStore) -> None:
        self.inner = inner
        self.writes: list[dict[str, object]] = []

    def get_bytes(self, key):
        return self.inner.get_bytes(key)

    def get_bytes_strict(self, key):
        return self.inner.get_bytes_strict(key)

    def get_bytes_strict_bounded(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    def get_bytes_strict_bounded_versioned(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded_versioned(key, maximum_bytes)

    def validate_strict_conditional_write_capability(self):
        return self.inner.validate_strict_conditional_write_capability()

    def put_bytes_strict_conditional(
        self, key, data, *, expected_version, content_type="application/octet-stream"
    ):
        self.writes.append(
            {
                "key": key,
                "content_type": content_type,
                "expected_version": expected_version,
            }
        )
        return self.inner.put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        raise AssertionError("rolling publication must not use unconditional writes")

    def list_prefix(self, prefix):
        return self.inner.list_prefix(prefix)

    def exists(self, key):
        return self.inner.exists(key)

    def upload_time(self, key):
        return self.inner.upload_time(key)


def _run(
    store,
    fetch,
    fake_time: _FakeMonotonic,
    *,
    hour: int = 12,
    master_index_source=None,
    max_accessions: int = 3,
):
    return run_rolling_ingestion(
        store=store,
        fetch=fetch,
        master_index_source=master_index_source,
        max_accessions=max_accessions,
        now=lambda: datetime(2026, 8, 8, hour, tzinfo=timezone.utc),
        monotonic=fake_time.monotonic,
        sleep=fake_time.sleep,
    )


def test_paced_fetch_enforces_eight_per_second_and_byte_ceiling() -> None:
    fake_time = _FakeMonotonic()
    starts: list[float] = []

    def fetch(_url: str) -> bytes:
        starts.append(fake_time.value)
        return b"ok"

    paced = PacedFetch(
        fetch,
        requests_per_second=8,
        monotonic=fake_time.monotonic,
        sleep=fake_time.sleep,
    )
    for index in range(3):
        assert paced(f"https://www.sec.gov/{index}") == b"ok"
    assert starts == [0.0, 0.125, 0.25]
    assert paced.request_count == 3

    with pytest.raises(ValueError, match="at most 8"):
        PacedFetch(fetch, requests_per_second=8.01)
    assert MAX_SEC_RESPONSE_BYTES == 64 * 1024 * 1024
    assert MAX_SEC_RUN_RESPONSE_BYTES == 2 * 1024 * 1024 * 1024
    with pytest.raises(ValueError, match="SEC response ceiling"):
        PacedFetch(fetch, maximum_bytes=MAX_SEC_RESPONSE_BYTES + 1)
    with pytest.raises(ValueError, match="SEC run ceiling"):
        PacedFetch(fetch, maximum_total_bytes=MAX_SEC_RUN_RESPONSE_BYTES + 1)
    too_large = PacedFetch(lambda _url: b"12345", maximum_bytes=4)
    with pytest.raises(Institutional13FRollingError, match="exceeds 4 bytes"):
        too_large("https://www.sec.gov/oversize")

    calls = 0

    def cumulative_fetch(_url: str) -> bytes:
        nonlocal calls
        calls += 1
        return b"1234"

    cumulative = PacedFetch(
        cumulative_fetch,
        maximum_bytes=4,
        maximum_total_bytes=6,
        monotonic=fake_time.monotonic,
        sleep=fake_time.sleep,
    )
    assert cumulative("https://www.sec.gov/one") == b"1234"
    with pytest.raises(Institutional13FRollingError, match="cumulative response"):
        cumulative("https://www.sec.gov/two")
    assert cumulative.request_count == 2
    assert cumulative.response_bytes == 8
    with pytest.raises(Institutional13FRollingError, match="cumulative response"):
        cumulative("https://www.sec.gov/three")
    assert calls == 2


def test_sec_response_cap_matches_config_and_streaming_runner(monkeypatch) -> None:
    configured = yaml.safe_load(Path("config/institutional_13f.yml").read_text())
    assert (
        configured["storage"]["rolling_sec_response_max_bytes"]
        == MAX_SEC_RESPONSE_BYTES
    )
    assert (
        configured["storage"]["rolling_sec_run_max_bytes"] == MAX_SEC_RUN_RESPONSE_BYTES
    )

    class Response:
        def __init__(self, *, announced=None, chunks=()):
            self.headers = {} if announced is None else {"Content-Length": announced}
            self._chunks = chunks

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, _chunk_size):
            yield from self._chunks

    class Session:
        def __init__(self, response):
            self.response = response

        def get(self, *_args, **_kwargs):
            return self.response

        def close(self):
            return None

    monkeypatch.setattr(rolling_runner, "MAX_SEC_RESPONSE_BYTES", 4)
    fetcher = rolling_runner._RequestsSecFetch(user_agent="test example@example.com")
    fetcher._session = Session(Response(announced="5"))
    with pytest.raises(RuntimeError, match="SEC response byte ceiling"):
        fetcher("https://www.sec.gov/announced-oversize")

    fetcher._session = Session(Response(chunks=(b"123", b"45")))
    with pytest.raises(RuntimeError, match="SEC response byte ceiling"):
        fetcher("https://www.sec.gov/streamed-oversize")


class _HeaderControlledResponse:
    """Fake ``requests`` streaming response with independently controllable
    headers and body chunks, so a content-coded response (e.g. gzip) can be
    modeled with a Content-Length that legitimately disagrees with the bytes
    ``iter_content`` yields (already decompressed by requests/urllib3)."""

    def __init__(self, *, headers=None, chunks=()):
        self.headers = dict(headers or {})
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, _chunk_size):
        yield from self._chunks


class _HeaderControlledSession:
    def __init__(self, response):
        self.response = response

    def get(self, *_args, **_kwargs):
        return self.response

    def close(self):
        return None


def test_truncated_identity_encoded_response_raises() -> None:
    fetcher = rolling_runner._RequestsSecFetch(user_agent="test example@example.com")
    fetcher._session = _HeaderControlledSession(
        _HeaderControlledResponse(headers={"Content-Length": "10"}, chunks=(b"12345",))
    )
    with pytest.raises(RuntimeError, match="SEC response truncated"):
        fetcher("https://www.sec.gov/truncated-identity")


def test_complete_identity_encoded_response_does_not_raise() -> None:
    fetcher = rolling_runner._RequestsSecFetch(user_agent="test example@example.com")
    fetcher._session = _HeaderControlledSession(
        _HeaderControlledResponse(headers={"Content-Length": "5"}, chunks=(b"12345",))
    )
    assert fetcher("https://www.sec.gov/complete-identity") == b"12345"


def test_content_length_is_not_compared_against_a_decoded_body() -> None:
    """Regression guard for the defect that would have taken production down:
    Content-Length describes the ENCODED body, not the decoded one. Live SEC
    served spectrum13f2026q2.xml with ``content-encoding: gzip`` and
    ``content-length: 3815`` (the compressed size on the wire) while
    ``iter_content`` transparently decompresses it to 42886 bytes -- comparing
    the two is a category error, not a truncation. A content-coded response
    must never raise on a Content-Length/observed-bytes mismatch; the codec's
    own framing (a truncated gzip stream fails to decode) is what detects real
    truncation there instead.
    """
    fetcher = rolling_runner._RequestsSecFetch(user_agent="test example@example.com")
    decompressed_body = b"x" * 42886
    fetcher._session = _HeaderControlledSession(
        _HeaderControlledResponse(
            headers={"Content-Length": "3815", "Content-Encoding": "gzip"},
            chunks=(decompressed_body,),
        )
    )
    assert fetcher("https://www.sec.gov/gzip-encoded") == decompressed_body


def test_index_size_mismatch_no_longer_fails_parsing_and_warns(capsys) -> None:
    """SEC's index.json `size` is advisory (verified against live SEC: it
    disagrees with SEC's own Content-Length and served bytes -- a
    block-rounded metadata artifact). A body/index size mismatch must parse
    successfully and only surface as a line-leading GitHub Actions
    `::warning`, never a raised SecSourceError."""
    package = _package(ACCESSION)
    index_source = package.pop("index.json")
    package["information_table.xml"] += b"\n"

    tables = parse_filing_package(
        index_url=_index_url(ACCESSION),
        index_source=index_source,
        documents=package,
    )

    assert len(tables.holdings) >= 1
    out = capsys.readouterr().out
    warning_lines = [line for line in out.splitlines() if line.startswith("::")]
    assert warning_lines, f"no line-leading annotation emitted; captured: {out!r}"
    assert any(
        "sec-index-size-mismatch" in line and "information_table.xml" in line
        for line in warning_lines
    )


def test_raw_first_append_checkpoint_and_mixed_unit_contract(tmp_path: Path) -> None:
    inner = LocalStore(tmp_path / "store")
    store = _RecordingStore(inner)
    fake_time = _FakeMonotonic()
    first_fetch = _FixtureFetch([ACCESSION])

    first = _run(store, first_fetch, fake_time)
    assert first["status"] == "ok"
    assert first["counts"]["new_filings_published"] == 1
    assert first["counts"]["sec_response_bytes"] == first_fetch.response_bytes
    assert first["checkpoint"] == {
        "object_key": ROLLING_CHECKPOINT_KEY,
        "authority": "operational_discovery_only",
        "entries_before": 0,
        "entries_after": 1,
        "updated": True,
        "updated_at": "2026-08-08T12:00:00Z",
    }

    write_keys = [str(item["key"]) for item in store.writes]
    raw_receipt_position = next(
        index for index, key in enumerate(write_keys) if "/filings/" in key
    )
    first_parquet_position = next(
        index
        for index, item in enumerate(store.writes)
        if item["content_type"] == "application/vnd.apache.parquet"
    )
    catalog_pointer_position = write_keys.index(catalog_pointer_key(PERIOD))
    checkpoint_position = write_keys.index(ROLLING_CHECKPOINT_KEY)
    assert raw_receipt_position < first_parquet_position
    assert catalog_pointer_position < checkpoint_position

    catalog = load_catalog_generation(inner, report_period=PERIOD)
    assert len(catalog.filings) == 1
    assert len(catalog.holdings) == 2
    assert len(catalog.manager_relationships) == 3
    assert (
        len(
            [
                item
                for item in catalog.manifest.artifacts
                if item.role in HOLDING_BUCKET_ROLES
            ]
        )
        == 64
    )
    filing = dict(catalog.filings[0])
    assert filing["form"] == "13F-HR/A"
    assert filing["form13f_file_number"] == "028-23090"
    assert filing["lineage_state"] == "amendment_new_holdings"
    assert filing["accepted_at"] == "2026-08-07T21:25:16Z"
    assert filing["table_value_total_usd"] is None
    assert filing["quality_state"].startswith("unit_unresolved")

    holding_keys = [int(item["infotable_sk"]) for item in catalog.holdings]
    assert holding_keys == [
        SYNTHETIC_INFOTABLE_SK_BASE + 1,
        SYNTHETIC_INFOTABLE_SK_BASE + 2,
    ]
    for item in catalog.holdings:
        row = dict(item)
        observed_hash = row.pop("row_hash")
        assert observed_hash == sha256(canonical_json_bytes(row)).hexdigest()
        assert row["value_reported"] in {"1000", "2000"}
        assert row["value_unit"] == "unresolved"
        assert row["value_usd"] is None

    included = [
        dict(item)
        for item in catalog.manager_relationships
        if item["source_table"] == "OTHERMANAGER2"
    ]
    assert [item["manager_sequence"] for item in included] == [1, 1]
    assert [item["other_manager_sk"] for item in included] == [1, 2]
    assert {item["relationship_kind"] for item in catalog.manager_relationships} == {
        "reported_by_manager",
        "included_manager",
    }

    receipt, raw_payload = load_raw_evidence(
        inner,
        (
            f"smart-money/13f/evidence/v1/filings/{CIK}/{ACCESSION}/"
            f"{filing['source_receipt_id']}.json"
        ),
    )
    parts = decode_framed_evidence(raw_payload)
    assert receipt.raw_object.sha256 == filing["raw_sha256"]
    assert sha256(raw_payload).hexdigest() == filing["raw_sha256"]
    assert parts == _package(ACCESSION)

    pointer_before = inner.get_bytes_strict(catalog_pointer_key(PERIOD))
    writes_before = len(store.writes)
    calls_before = len(first_fetch.calls)
    second = _run(store, first_fetch, fake_time)
    assert second["status"] == "no_changes"
    assert second["counts"]["checkpoint_accessions_skipped"] == 1
    assert second["counts"]["requests"] == 1
    assert len(first_fetch.calls) - calls_before == 1
    assert "browse-edgar" in first_fetch.calls[-1]
    assert len(store.writes) == writes_before
    assert inner.get_bytes_strict(catalog_pointer_key(PERIOD)) == pointer_before

    append_fetch = _FixtureFetch([SECOND_ACCESSION, ACCESSION])
    appended = _run(store, append_fetch, fake_time, hour=13)
    assert appended["status"] == "ok"
    assert appended["counts"]["checkpoint_accessions_skipped"] == 1
    assert appended["counts"]["new_filings_published"] == 1
    appended_catalog = load_catalog_generation(inner, report_period=PERIOD)
    assert {item["accession"] for item in appended_catalog.filings} == {
        ACCESSION,
        SECOND_ACCESSION,
    }
    assert len(appended_catalog.holdings) == 4
    assert len(appended_catalog.manager_relationships) == 6
    assert appended["checkpoint"]["entries_after"] == 2


def test_supplied_master_index_is_backstop_and_backlog_stays_retryable(
    tmp_path: Path,
) -> None:
    dummy_accession = "0000000001-26-000001"
    master = (
        "CIK|Company Name|Form Type|Date Filed|File Name\n"
        f"1792167|Fixture Manager|13F-HR/A|20260807|edgar/data/1792167/{ACCESSION}.txt\n"
        f"1|Backlog Manager|13F-NT|20260807|edgar/data/1/{dummy_accession}.txt\n"
    ).encode("latin-1")
    fetch = _FixtureFetch([ACCESSION], atom_error=True)
    fake_time = _FakeMonotonic()
    result = _run(
        LocalStore(tmp_path / "store"),
        fetch,
        fake_time,
        master_index_source=master,
        max_accessions=1,
    )

    assert result["status"] == "partial_failure"
    assert result["discovery"]["master_index"]["entries"] == 2
    assert result["discovery"]["master_index"]["sha256"] == sha256(master).hexdigest()
    assert result["counts"]["new_filings_published"] == 1
    assert result["backlog"]["count"] == 1
    assert result["backlog"]["details"][0]["accession"] == dummy_accession
    assert result["failures"]["details"][0]["stage"] == "atom_discovery"
    assert not any(dummy_accession.replace("-", "") in item for item in fetch.calls)
    assert result["checkpoint"]["entries_after"] == 1


def test_bound_saturated_backlog_is_progress_not_a_coverage_gap(
    tmp_path: Path,
) -> None:
    """Saturating --max-accessions on an otherwise clean run is bounded
    throughput control, not a coverage gap: it must not be classed
    partial_failure/failed, and its receipt must stay zero-failure.

    Atom is handed strictly fewer entries than --max-accessions so the scan
    completes via ``short_page``. entry_limit is min(max_accessions, 930), so
    an Atom feed as long as the bound would instead fall through to
    ``ephemeral_limit`` -- a real, and correctly fatal, coverage gap.
    """
    dummy_accession = "0000000001-26-000001"
    master = (
        "CIK|Company Name|Form Type|Date Filed|File Name\n"
        f"1792167|Fixture Manager|13F-HR/A|20260807|edgar/data/1792167/{ACCESSION}.txt\n"
        f"1792167|Fixture Manager|13F-HR/A|20260807"
        f"|edgar/data/1792167/{SECOND_ACCESSION}.txt\n"
        f"1|Backlog Manager|13F-NT|20260807|edgar/data/1/{dummy_accession}.txt\n"
    ).encode("latin-1")
    fetch = _FixtureFetch([ACCESSION, SECOND_ACCESSION], atom_accessions=[ACCESSION])
    fake_time = _FakeMonotonic()
    result = _run(
        LocalStore(tmp_path / "store"),
        fetch,
        fake_time,
        master_index_source=master,
        max_accessions=2,
    )

    assert result["status"] == "bounded_backlog"
    assert result["discovery"]["atom"]["complete"] is True
    assert result["counts"]["failures"] == 0
    assert result["counts"]["new_filings_published"] == 2
    assert result["backlog"]["count"] == 1
    assert result["discovery"]["backlog_accessions"] == 1
    assert result["backlog"]["details"][0]["accession"] == dummy_accession
    assert not any(dummy_accession.replace("-", "") in item for item in fetch.calls)


def test_notice_projection_never_turns_unknown_holdings_into_zero(
    tmp_path: Path,
) -> None:
    accession = "0001000490-26-000003"
    accepted = "2026-08-07T17:15:50-04:00"
    retained = "2026-08-08T12:00:00Z"
    payload = b"exact notice evidence"
    tables = BulkTables(
        submissions=pd.DataFrame.from_records(
            [
                {
                    "accession": accession,
                    "filing_date": "2026-08-07",
                    "form": "13F-NT",
                    "cik": "0001000490",
                    "period_end": "2026-06-30",
                    "accepted_at": accepted,
                }
            ],
            columns=SUBMISSION_COLUMNS,
        ),
        cover_pages=pd.DataFrame.from_records(
            [
                {
                    "source_ordinal": 1,
                    "accession": accession,
                    "is_amendment": False,
                    "filing_manager_name": "Fixture Notice Manager",
                    "report_type": "13F NOTICE",
                }
            ],
            columns=COVER_PAGE_COLUMNS,
        ),
        summary_pages=pd.DataFrame.from_records(
            [
                {
                    "source_ordinal": 1,
                    "accession": accession,
                    "other_included_managers_count": 0,
                    "table_entry_total": 0,
                    "table_value_total": 0,
                    "is_confidential_omitted": False,
                }
            ],
            columns=SUMMARY_PAGE_COLUMNS,
        ),
        holdings=pd.DataFrame(columns=HOLDING_COLUMNS),
        reported_by=pd.DataFrame(columns=REPORTED_BY_COLUMNS),
        included_managers=pd.DataFrame(columns=INCLUDED_MANAGER_COLUMNS),
        source_sha256=sha256(payload).hexdigest(),
        source_bytes=len(payload),
    )
    discovery = FilingDiscovery(
        accession=accession,
        cik="0001000490",
        form="13F-NT",
        filing_date="2026-08-07",
        accepted_at=accepted,
        index_url=(
            "https://www.sec.gov/Archives/edgar/data/1000490/"
            "000100049026000003/0001000490-26-000003-index.htm"
        ),
    )
    store = LocalStore(tmp_path / "store")
    receipt = publish_raw_evidence(
        store,
        accession=accession,
        filer_cik=discovery.cik,
        form=discovery.form,
        report_period="2026-06-30",
        accepted_at="2026-08-07T21:15:50Z",
        retained_at=retained,
        source_url=discovery.index_url,
        payload=payload,
        producer_version="rolling-test-v1",
    )
    rows = project_catalog_rows(
        tables,
        discovery,
        receipt,
        retained_at=retained,
        parser_version="rolling-test-v1",
    )

    assert rows.holdings == ()
    assert rows.filing["lineage_state"] == "notice"
    assert rows.filing["table_entry_total"] is None
    assert rows.filing["table_value_total_usd"] is None
    assert rows.filing["confidential_omitted"] is None
    assert rows.filing["quality_state"] == "notice_only_no_holdings"


def test_full_index_replay_beyond_1200_is_filtered_without_refetch(
    tmp_path: Path,
) -> None:
    accessions = [f"0000000001-26-{index:06d}" for index in range(1, 1306)]
    normalized_acceptance = "2026-08-07T21:25:16Z"
    checkpoint_entries = [
        {"accession": accession, "accepted_at": normalized_acceptance}
        for accession in sorted(accessions, reverse=True)
    ]
    checkpoint_payload = canonical_json_bytes(
        {
            "schema": ROLLING_CHECKPOINT_SCHEMA,
            "updated_at": "2026-08-08T12:00:00Z",
            "entries": checkpoint_entries,
        }
    )
    inner = LocalStore(tmp_path / "store")
    assert inner.put_bytes_strict_conditional(
        ROLLING_CHECKPOINT_KEY,
        checkpoint_payload,
        expected_version=None,
        content_type="application/json",
    )
    store = _RecordingStore(inner)
    master = (
        "CIK|Company Name|Form Type|Date Filed|File Name\n"
        + "".join(
            (f"1|Manager {index}|13F-HR|20260807|edgar/data/1/{accession}.txt\n")
            for index, accession in enumerate(accessions, start=1)
        )
    ).encode("latin-1")
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if "browse-edgar" in url:
            return b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        raise AssertionError("checkpointed full-index accessions must not be fetched")

    result = _run(
        store,
        fetch,
        _FakeMonotonic(),
        master_index_source=master,
        max_accessions=3,
    )

    assert result["status"] == "no_changes"
    assert result["discovery"]["checkpoint_filtered_accessions"] == 1305
    assert result["discovery"]["selected_accessions"] == 0
    assert result["discovery"]["backlog_accessions"] == 0
    assert result["checkpoint"]["entries_before"] == 1305
    assert result["counts"]["requests"] == 1
    assert len(calls) == 1 and "browse-edgar" in calls[0]
    assert store.writes == []


def test_bounds_reject_more_than_the_accession_cap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=f"between 1 and {MAX_ACCESSIONS}"):
        run_rolling_ingestion(
            store=LocalStore(tmp_path / "store"),
            fetch=lambda _url: b"",
            max_accessions=MAX_ACCESSIONS + 1,
        )


def test_cli_explicit_local_mode_writes_a_loud_fatal_receipt(
    tmp_path: Path, capsys
) -> None:
    receipt_path = tmp_path / "receipts" / "rolling.json"
    result = rolling_main(
        [
            "--local-store",
            str(tmp_path / "store"),
            "--max-accessions",
            str(MAX_ACCESSIONS + 1),
            "--receipt",
            str(receipt_path),
        ]
    )

    assert result == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["failures"]["count"] == 1
    assert receipt["failures"]["details"][0]["stage"] == "runner"
    assert receipt["checkpoint"]["authority"] == "operational_discovery_only"
    emitted = json.loads(capsys.readouterr().out)
    assert emitted == receipt


def _stub_receipt(status: str) -> dict:
    return {
        "schema": "institutional_13f.rolling_receipt/v1",
        "status": status,
        "discovery": {"backlog_accessions": 0},
        "counts": {"failures": 0},
    }


@pytest.mark.parametrize(
    "status, expected_exit",
    [
        ("ok", 0),
        ("no_changes", 0),
        ("bounded_backlog", 0),
        ("partial_failure", 1),
        ("failed", 1),
    ],
)
def test_main_exit_code_matches_receipt_status(
    tmp_path: Path, monkeypatch, status: str, expected_exit: int
) -> None:
    """main() must exit 0 for every non-degraded status, including the new
    bounded_backlog outcome, and non-zero for a genuine coverage gap."""
    monkeypatch.setattr(
        rolling_runner,
        "run_rolling_ingestion",
        lambda **_kwargs: _stub_receipt(status),
    )
    receipt_path = tmp_path / "receipts" / "rolling.json"
    result = rolling_main(
        [
            "--local-store",
            str(tmp_path / "store"),
            "--receipt",
            str(receipt_path),
        ]
    )
    assert result == expected_exit
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == status


def test_receipts_bound_and_redact_exception_details(
    tmp_path: Path, monkeypatch
) -> None:
    secret_message = (
        "GET https://www.sec.gov/private?token=supersecret "
        "failed at /Users/alice/.aws/credentials; "
        "fallback ../../private/credentials.json; "
        "INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY=do-not-leak "
        "AKIAIOSFODNN7EXAMPLE "
        "Bearer abcdefghijklmnopqrstuvwxyz0123456789"
    )

    def unsafe_fetch(_url: str) -> bytes:
        raise RuntimeError(secret_message + ("x" * 2_000))

    receipt = _run(LocalStore(tmp_path / "store"), unsafe_fetch, _FakeMonotonic())
    encoded = canonical_json_bytes(receipt).decode("utf-8")
    assert receipt["status"] == "failed"
    assert receipt["counts"]["sec_response_bytes"] == 0
    detail = receipt["failures"]["details"][0]
    assert detail["error"].startswith("RuntimeError: ")
    assert detail["reason_code"] == "runtime_error"
    assert len(detail["error"]) <= 330
    for leaked in (
        "https://",
        "/Users/alice",
        "../../private",
        "INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY",
        "do-not-leak",
        "AKIAIOSFODNN7EXAMPLE",
        "abcdefghijklmnopqrstuvwxyz0123456789",
    ):
        assert leaked not in encoded

    receipt_path = tmp_path / "receipts" / "fatal.json"
    monkeypatch.setattr(
        rolling_runner,
        "build_institutional_13f_store",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(secret_message)),
    )
    assert (
        rolling_runner.main(
            [
                "--local-store",
                str(tmp_path / "fatal-store"),
                "--receipt",
                str(receipt_path),
            ]
        )
        == 1
    )
    fatal_encoded = receipt_path.read_text(encoding="utf-8")
    fatal = json.loads(fatal_encoded)
    assert fatal["counts"]["sec_response_bytes"] == 0
    assert fatal["failures"]["details"][0]["reason_code"] == "runtime_error"
    for leaked in (
        "https://",
        "/Users/alice",
        "../../private",
        "INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY",
        "do-not-leak",
        "AKIAIOSFODNN7EXAMPLE",
        "abcdefghijklmnopqrstuvwxyz0123456789",
    ):
        assert leaked not in fatal_encoded
