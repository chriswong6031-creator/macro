from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pandas as pd
import pytest
import requests

import collectors.sec_capital_structure as sec
from collectors.sec_capital_structure import (
    collect_latest_filings_overlay,
    DocumentInspection,
    LatestFilingsTraversalIncomplete,
    latest_filings_discovery_rows,
    parse_latest_filings_atom,
    reconcile_discovery_rows,
    SecCapitalStructureAdapter,
    SubmissionBundle,
    SubmissionDocument,
    due_index_dates,
    file_number_provenance_errors,
    inspect_source_document,
    parse_form_index,
    parse_submission,
    retrieval_priority,
    retrieval_lane_quotas,
    select_retrieval_queue,
    select_relevant_documents,
)
from engine.capital_structure.source_store import (
    ContentAddressedSourceStore,
    LocalStore,
    SourceReceipt,
    STORE_ID_DEDICATED_R2,
)
from engine.capital_structure.source_identity import (
    ManifestIdentityError,
    canonical_manifest_bytes,
    manifest_id_for,
)
from engine.capital_structure.source_ledger_io import (
    encode_source_ledger,
    read_source_ledger,
    source_ledger_path,
)


@pytest.fixture(autouse=True)
def _keep_legacy_adapter_tests_off_the_new_network_surface(monkeypatch):
    """Existing adapter fixtures remain daily-index-only unless a test opts in."""
    monkeypatch.setattr(
        SecCapitalStructureAdapter, "latest_filings_enabled", False,
    )


def _write_ledger(path, records):
    """Write a source-manifest ledger fixture, bypassing the validating writer.

    Fixtures deliberately include ledgers the identity law rejects.
    """
    path.write_bytes(encode_source_ledger(list(records)))


INDEX = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
S-3                                  ACME CORP                                 1234567     20260801    edgar/data/1234567/0001234567-26-000001.txt
EFFECT                               ACME CORP                                 1234567     20260802    edgar/data/1234567/9999999995-26-002222.txt
424B5                                MEDTECH LTD                               1111111     20260803    edgar/data/1111111/0001111111-26-000003.txt
1-A POS                              REG A CO                                  2222222     20260804    edgar/data/2222222/0002222222-26-000004.txt
8-K                                  BROAD EVENT CO                            3333333     20260805    edgar/data/3333333/0003333333-26-000005.txt
"""

BUSINESS_DAY_INDEX = INDEX
for _fixture_date in ("20260801", "20260802", "20260803", "20260804", "20260805"):
    BUSINESS_DAY_INDEX = BUSINESS_DAY_INDEX.replace(_fixture_date, "20260731")

SUBMISSION = b"""\
<SEC-DOCUMENT>0001234567-26-000001.txt
<ACCEPTANCE-DATETIME>20260801123456
<FILE-NUMBER>333-123456
<DOCUMENT>
<TYPE>S-3
<SEQUENCE>1
<FILENAME>forms3.htm
<DESCRIPTION>REGISTRATION STATEMENT
<TEXT><html><body>Registration statement.</body></html></TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-10.1
<SEQUENCE>2
<FILENAME>purchase.htm
<DESCRIPTION>PURCHASE AGREEMENT
<TEXT><html><body>Purchase agreement.</body></html></TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>GRAPHIC
<SEQUENCE>3
<FILENAME>logo.jpg
<TEXT>binary-placeholder</TEXT>
</DOCUMENT>
"""

SINGLE_INDEX = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
S-3                                  ACME CORP                                 1234567     20260801    edgar/data/1234567/0001234567-26-000001.txt
"""

SINGLE_BUSINESS_DAY_INDEX = SINGLE_INDEX.replace("20260801", "20260731")

LEGACY_DISCOVERY_COLUMNS = [
    "accession", "cik", "ticker", "company_name", "form", "filing_date",
    "file_path", "canonical_url", "_first_seen",
]


def _atom_page(*entries: dict, updated: str = "2026-08-25T18:30:00-04:00") -> str:
    body = []
    for entry in entries:
        accession = entry["accession"]
        cik = str(entry.get("cik", "1234567")).zfill(10)
        form = entry.get("form", "S-3")
        company = entry.get("company", "ACME CORP")
        role = entry.get("role", "Filer")
        filed = entry.get("filing_date", "2026-08-25")
        entry_updated = entry.get("updated", updated)
        compact = accession.replace("-", "")
        body.append(f"""
<entry>
<title>{form} - {company} ({cik}) ({role})</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/{int(cik)}/{compact}/{accession}-index.htm"/>
<summary type="html">&lt;b&gt;Filed:&lt;/b&gt; {filed} &lt;b&gt;AccNo:&lt;/b&gt; {accession} &lt;b&gt;Size:&lt;/b&gt; 12 KB</summary>
<updated>{entry_updated}</updated>
<category scheme="https://www.sec.gov/" label="form type" term="{form}"/>
<id>urn:tag:sec.gov,2008:accession-number={accession}</id>
</entry>
""")
    return f"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings</title>
<updated>{updated}</updated>
{''.join(body)}
</feed>
"""


def test_latest_filings_atom_is_role_aware_and_accession_deduped():
    accession = "0001234567-26-000001"
    parsed = parse_latest_filings_atom(_atom_page(
        {
            "accession": accession, "cik": "7654321",
            "company": "REPORTING OWNER", "role": "Reporting",
        },
        {
            "accession": accession, "cik": "1234567",
            "company": "ACME CORP", "role": "Filer",
        },
    ))

    rows = latest_filings_discovery_rows(
        parsed["entries"],
        existing_discovery=pd.DataFrame(columns=sec._DISCOVERY_COLUMNS),
        cik_tickers={1234567: "ACME"},
        first_seen="2026-08-25T22:30:00Z",
    )

    assert parsed["observed_through"] == "2026-08-25T22:30:00Z"
    assert len(rows) == 1
    assert rows[0]["accession"] == accession
    assert rows[0]["cik"] == "0001234567"
    assert rows[0]["latest_filings_role"] == "Filer"
    assert rows[0]["discovery_channel"] == "latest_filings"


def test_latest_filings_traversal_crosses_durable_boundary_not_one_page(monkeypatch):
    monkeypatch.setattr(sec, "LATEST_FILINGS_PAGE_SIZE", 2)
    monkeypatch.setattr(sec, "MAX_LATEST_FILINGS_PAGES", 4)
    pages = {
        0: _atom_page(
            {"accession": "0001234567-26-000003", "updated": "2026-08-25T18:30:00-04:00"},
            {"accession": "0001234567-26-000002", "updated": "2026-08-25T18:20:00-04:00"},
        ),
        2: _atom_page(
            {"accession": "0001234567-26-000001", "updated": "2026-08-25T18:10:00-04:00"},
            {"accession": "0001234567-26-000000", "updated": "2026-08-25T17:59:00-04:00"},
        ),
    }
    starts: list[int] = []

    def fetch_page(start: int, count: int) -> str:
        starts.append(start)
        assert count == 2
        return pages[start]

    coverage = pd.DataFrame([{
        "coverage_kind": "latest_filings",
        "index_date": "2026-08-25",
        "status": "complete",
        "observed_through": "2026-08-25T22:00:00Z",
        "policy_version": sec.FORM_POLICY["policy_version"],
    }])
    result = collect_latest_filings_overlay(
        fetch_page,
        discovery=pd.DataFrame(columns=sec._DISCOVERY_COLUMNS),
        coverage=coverage,
        cik_tickers={},
        observed_at=datetime.fromisoformat("2026-08-25T22:30:00+00:00"),
    )

    assert starts == [0, 2, 0]
    assert [row["accession"] for row in result["rows"]] == [
        "0001234567-26-000003",
        "0001234567-26-000002",
        "0001234567-26-000001",
    ]
    assert result["pages_scanned"] == 2


def test_latest_filings_traversal_cap_discards_unproven_partial_scan(monkeypatch):
    monkeypatch.setattr(sec, "LATEST_FILINGS_PAGE_SIZE", 1)
    monkeypatch.setattr(sec, "MAX_LATEST_FILINGS_PAGES", 2)
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    pages = {
        0: _atom_page({
            "accession": "0001234567-26-000002",
            "updated": "2026-08-25T18:20:00-04:00",
        }),
        1: _atom_page({
            "accession": "0001234567-26-000001",
            "updated": "2026-08-25T18:10:00-04:00",
        }),
    }
    starts: list[int] = []

    def fetch_page(start: int, count: int) -> str:
        starts.append(start)
        return pages[start]

    coverage = pd.DataFrame([{
        "coverage_kind": "latest_filings",
        "index_date": "2026-08-25",
        "status": "complete",
        "observed_through": "2026-08-25T21:00:00Z",
        "policy_version": sec.FORM_POLICY["policy_version"],
    }])
    with pytest.raises(
        LatestFilingsTraversalIncomplete,
        match="boundary not reached in 2 pages",
    ):
        collect_latest_filings_overlay(
            fetch_page,
            discovery=pd.DataFrame(columns=sec._DISCOVERY_COLUMNS),
            coverage=coverage,
            cik_tickers={},
            observed_at=datetime.fromisoformat("2026-08-25T22:30:00+00:00"),
        )

    assert starts == [0, 1]


def test_latest_filings_unavailable_persists_retry_without_partial_discovery(
    tmp_path, monkeypatch,
):
    class OverlayUnavailableAdapter(SecCapitalStructureAdapter):
        def _fetch_latest_filings_page(self, start, count, ua):
            raise RuntimeError("forced Latest Filings outage")

        def _fetch_index(self, value, ua):
            raise AssertionError("no daily index is due in this fixture")

        def _fetch_submission(self, url, ua):
            raise AssertionError("partial overlay rows must never reach retrieval")

    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(sec, "due_index_dates", lambda *args, **kwargs: [])
    adapter = OverlayUnavailableAdapter(
        source_store=object(),
        now_fn=lambda: datetime(2026, 8, 25, 22, 30, tzinfo=timezone.utc),
        max_filings_per_run=0,
    )
    adapter.latest_filings_enabled = True

    heartbeat = adapter.fetch()["sec_evidence__ingest"]

    root = tmp_path / "capital_structure"
    coverage = pd.read_parquet(root / "index_coverage.parquet")
    discovery = pd.read_parquet(root / "discovery.parquet")
    receipt = json.loads((root / "retrieval_queue_receipt.json").read_text())
    assert discovery.empty
    assert len(coverage) == 1
    assert coverage.iloc[0]["coverage_kind"] == "latest_filings"
    assert coverage.iloc[0]["status"] == "retry"
    assert "forced Latest Filings outage" in coverage.iloc[0]["last_error"]
    assert int(heartbeat.iloc[0]["index_days_complete"]) == 0
    assert (
        receipt["discovery_clock_policy_version"]
        == sec.DISCOVERY_CLOCK_POLICY_VERSION
    )


def test_latest_filings_then_daily_reconciliation_keeps_one_evidence_and_event(
    tmp_path, monkeypatch,
):
    from scripts.compile_capital_structure_events import compile_manifest_records

    accession = "0001234567-26-000001"
    atom = _atom_page({
        "accession": accession,
        "company": "PROVISIONAL ACME NAME",
        "filing_date": "2026-07-31",
        "updated": "2026-07-31T16:00:00-04:00",
    }, updated="2026-07-31T16:05:00-04:00")
    state = {
        "now": datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        "daily_due": False,
    }

    class OverlayThenDailyAdapter(SecCapitalStructureAdapter):
        def _fetch_latest_filings_page(self, start, count, ua):
            return atom if start == 0 else _atom_page(
                updated="2026-07-31T16:05:00-04:00",
            )

        def _fetch_index(self, value, ua):
            assert value == date(2026, 7, 31)
            return SINGLE_BUSINESS_DAY_INDEX

        def _fetch_submission(self, url, ua):
            return SUBMISSION

    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec,
        "due_index_dates",
        lambda *args, **kwargs: (
            [date(2026, 7, 31)] if state["daily_due"] else []
        ),
    )
    store = ContentAddressedSourceStore(
        LocalStore(tmp_path / "objects"), backend="local",
    )
    adapter = OverlayThenDailyAdapter(
        source_store=store,
        now_fn=lambda: state["now"],
        max_filings_per_run=1,
    )
    adapter.latest_filings_enabled = True

    first = adapter.fetch()["sec_evidence__ingest"]
    root = tmp_path / "capital_structure"
    ledger_path = source_ledger_path(root)
    first_ledger_bytes = ledger_path.read_bytes()
    first_attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    assert int(first.iloc[0]["retrieved"]) == 1
    assert len(first_attempts) == 1

    state["daily_due"] = True
    state["now"] = datetime(2026, 8, 1, 13, 30, tzinfo=timezone.utc)
    second = adapter.fetch()["sec_evidence__ingest"]

    discovery = pd.read_parquet(root / "discovery.parquet")
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    manifests = read_source_ledger(ledger_path)
    compiled = compile_manifest_records(
        manifests,
        generated_at="2026-08-01T14:00:00Z",
    )
    assert int(second.iloc[0]["retrieved"]) == 0
    assert len(discovery) == 1
    assert discovery.iloc[0]["accession"] == accession
    assert discovery.iloc[0]["company_name"] == "ACME CORP"
    assert discovery.iloc[0]["discovery_channel"] == "daily_index"
    assert discovery.iloc[0]["_first_seen"] == "2026-08-01T13:00:00Z"
    assert ledger_path.read_bytes() == first_ledger_bytes
    assert len(attempts) == len(first_attempts) == 1
    assert len({row["evidence_id"] for row in manifests}) == len(manifests)
    assert len(compiled["events"]) == 1
    assert compiled["telemetry"]["counts"]["compile_failures"] == 0


def test_latest_filings_then_daily_index_reconciles_one_accession_in_place():
    accession = "0001234567-26-000001"
    overlay = latest_filings_discovery_rows(
        parse_latest_filings_atom(_atom_page({"accession": accession}))["entries"],
        existing_discovery=pd.DataFrame(columns=sec._DISCOVERY_COLUMNS),
        cik_tickers={1234567: "ACME"},
        first_seen="2026-08-25T22:30:00Z",
    )
    provisional = reconcile_discovery_rows(
        pd.DataFrame(columns=sec._DISCOVERY_COLUMNS),
        overlay_rows=overlay,
        daily_rows=[],
        reconciled_at="2026-08-25T22:30:00Z",
    )
    daily = [{
        "accession": accession,
        "cik": "0007654321",
        "ticker": "CORR",
        "company_name": "CORRECTED DAILY INDEX ISSUER",
        "form": "S-3",
        "filing_date": "2026-08-25",
        "file_path": "edgar/data/7654321/000123456726000001/0001234567-26-000001.txt",
        "canonical_url": "https://www.sec.gov/Archives/edgar/data/7654321/000123456726000001/0001234567-26-000001.txt",
        "collection_scope": sec.DISCOVERY_SCOPE_REGISTRATION,
        "_first_seen": "2026-08-26T10:00:00Z",
    }]

    reconciled = reconcile_discovery_rows(
        provisional,
        overlay_rows=[],
        daily_rows=daily,
        reconciled_at="2026-08-26T10:00:00Z",
    )

    assert len(reconciled) == 1
    row = reconciled.iloc[0]
    assert row["cik"] == "0007654321"
    assert row["company_name"] == "CORRECTED DAILY INDEX ISSUER"
    assert row["discovery_channel"] == "daily_index"
    assert row["_first_seen"] == "2026-08-25T22:30:00Z"
    assert row["latest_filings_updated_at"] == "2026-08-25T22:30:00Z"
    assert row["reconciled_at"] == "2026-08-26T10:00:00Z"

WRAPPED_OFFICIAL_HEADER_INDEX = """\
Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    Aug 1, 2026

Form Type   Company Name                                                  CIK
      Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
S-3               ACME CORP                                                     1234567     20260801    edgar/data/1234567/0001234567-26-000001.txt
"""

ISSUER_SCOPED_RECONCILIATION_INDEX = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
S-3                                  ANCHORED CO                               1234567     20260801    edgar/data/1234567/0001234567-26-000001.txt
8-K                                  ANCHORED CO                               1234567     20260801    edgar/data/1234567/0001234567-26-000002.txt
10-Q                                 ANCHORED CO                               1234567     20260801    edgar/data/1234567/0001234567-26-000003.txt
8-K                                  UNANCHORED CO                             7654321     20260801    edgar/data/7654321/0007654321-26-000004.txt
"""

RECONCILIATION_ONLY_INDEX = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
8-K                                  ANCHORED CO                               1234567     20260804    edgar/data/1234567/0001234567-26-000010.txt
"""

REGISTRATION_ONLY_INDEX = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
S-3                                  ANCHORED CO                               1234567     20260803    edgar/data/1234567/0001234567-26-000011.txt
"""

MODERN_HEADER_SUBMISSION = b"""\
<SEC-DOCUMENT>0001234567-26-000002.txt
<SEC-HEADER>
SEC FILE NUMBER: 333 - 765432
</SEC-HEADER>
<DOCUMENT>
<TYPE>S-3
<SEQUENCE>1
<FILENAME>modern.htm
<TEXT><html><body>Modern registration.</body></html></TEXT>
</DOCUMENT>
"""

EFFECT_XML_SUBMISSION = b"""\
<SEC-DOCUMENT>0001234567-26-000003.txt
<DOCUMENT>
<TYPE>EFFECT
<SEQUENCE>1
<FILENAME>effect.xml
<TEXT><?xml version="1.0"?><submission><fileNumber>333-765432</fileNumber></submission></TEXT>
</DOCUMENT>
"""

CONFLICTING_FILE_NUMBER_SUBMISSION = b"""\
<SEC-DOCUMENT>0001234567-26-000004.txt
<FILE-NUMBER>333-111111
SEC FILE NUMBER: 333-222222
<DOCUMENT>
<TYPE>S-3
<SEQUENCE>1
<FILENAME>conflict.htm
<TEXT><html><body>Conflicting header.</body></html></TEXT>
</DOCUMENT>
"""

MULTI_VALUE_FILE_NUMBER_SUBMISSION = b"""\
<SEC-DOCUMENT>0001234567-26-000005.txt
<FILE-NUMBER>333-111111 and 333-222222
SEC FILE NUMBER: 333-111111
<DOCUMENT>
<TYPE>S-3
<SEQUENCE>1
<FILENAME>multi-value.htm
<TEXT><html><body>Malformed multi-value header.</body></html></TEXT>
</DOCUMENT>
"""


def test_form_index_policy_is_explicit_and_does_not_claim_broad_reconciliation():
    rows = parse_form_index(INDEX)
    assert [row["form"] for row in rows] == ["S-3", "EFFECT", "424B5", "1-A POS"]
    assert all(row["cik"] == row["cik"].zfill(10) for row in rows)
    assert rows[0]["canonical_url"].startswith("https://www.sec.gov/Archives/")
    assert "8-K" in sec.FORM_POLICY["wave2_declared_not_collected"]
    assert "S-8" in sec.FORM_POLICY["capital_relevant_declared_not_collected"]
    assert "S-8" not in sec.FORM_POLICY["wave1_discovery"]
    assert "424B2" in sec.FORM_POLICY["capital_relevant_declared_not_collected"]
    assert "424B2" not in sec.FORM_POLICY["wave1_discovery"]
    assert sec.WORK_CLASS_RESERVATIONS == {
        "LIVE_TAIL": 500,
        "RECOVERY": 20,
        "HISTORICAL_BACKFILL": 20,
    }
    assert sec.MAX_FILINGS_PER_RUN == 540
    assert sec.MAX_FILINGS_PER_RUN == sum(sec.WORK_CLASS_RESERVATIONS.values())


def test_form_index_rejects_html_malformed_and_header_only_responses():
    invalid_responses = [
        "<!doctype html><html><body>rate limited</body></html>",
        """Form Type  Company Name  CIK  Date Filed  File Name
------------------------------
not enough columns
""",
        """Form Type  Company Name  CIK  Date Filed  File Name
------------------------------
""",
    ]
    for response in invalid_responses:
        try:
            parse_form_index(response)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed SEC index was accepted")

    assert parse_form_index(INDEX, target_forms={"DOES-NOT-EXIST"}) == []
    assert parse_form_index(WRAPPED_OFFICIAL_HEADER_INDEX)[0]["form"] == "S-3"


def test_submission_parser_retains_acceptance_file_number_and_relevant_documents():
    bundle = parse_submission(SUBMISSION)
    assert bundle.accepted_at == "2026-08-01T16:34:56+00:00"
    assert bundle.file_number == "333-123456"
    assert len(bundle.documents) == 3
    selected = select_relevant_documents("S-3", bundle.documents)
    assert [(role, doc.filename) for role, doc in selected] == [
        ("primary", "forms3.htm"), ("exhibit", "purchase.htm")
    ]


def test_submission_parser_accepts_modern_header_and_effect_xml_file_numbers():
    modern = parse_submission(MODERN_HEADER_SUBMISSION)
    effect = parse_submission(EFFECT_XML_SUBMISSION)

    assert modern.file_number == "333-765432"
    assert modern.file_number_provenance == {
        "state": "observed",
        "value": "333-765432",
        "candidate_values": ["333-765432"],
        "sources": ["sec_header_file_number"],
    }
    assert effect.file_number == "333-765432"
    assert effect.file_number_provenance == {
        "state": "observed",
        "value": "333-765432",
        "candidate_values": ["333-765432"],
        "sources": ["effect_xml_file_number"],
    }


def test_conflicting_authoritative_file_numbers_are_null_and_provenanced():
    bundle = parse_submission(CONFLICTING_FILE_NUMBER_SUBMISSION)

    assert bundle.file_number is None
    assert bundle.file_number_provenance == {
        "state": "ambiguous",
        "value": None,
        "candidate_values": ["333-111111", "333-222222"],
        "sources": ["legacy_sgml_file_number", "sec_header_file_number"],
    }
    assert not file_number_provenance_errors({
        "file_number": None,
        "file_number_provenance": bundle.file_number_provenance,
    })
    assert file_number_provenance_errors({
        "file_number": "333-111111",
        "file_number_provenance": bundle.file_number_provenance,
    }) == ["non-observed file-number provenance requires null filing.file_number"]


def test_multiple_file_numbers_inside_one_header_field_cannot_disappear():
    bundle = parse_submission(MULTI_VALUE_FILE_NUMBER_SUBMISSION)

    assert bundle.file_number is None
    assert bundle.file_number_provenance == {
        "state": "ambiguous",
        "value": None,
        "candidate_values": ["333-111111", "333-222222"],
        "sources": ["legacy_sgml_file_number", "sec_header_file_number"],
    }


def test_relevant_document_selection_retains_underwriting_and_fee_exhibits():
    documents = (
        SubmissionDocument("1", "8-K", "current.htm", None, b"current"),
        SubmissionDocument("2", "EX-1.1", "underwriting.htm", None, b"underwriting"),
        SubmissionDocument("3", "EX-FILING FEES", "fees.htm", None, b"fees"),
        SubmissionDocument("4", "EX-2.1", "unrelated.htm", None, b"unrelated"),
    )

    selected = select_relevant_documents("8-K", documents)

    assert [(role, doc.filename) for role, doc in selected] == [
        ("primary", "current.htm"),
        ("underwriting_exhibit", "underwriting.htm"),
        ("filing_fee_exhibit", "fees.htm"),
    ]


def test_form_index_admits_reconciliation_only_for_anchored_issuer_scope():
    rows = parse_form_index(
        ISSUER_SCOPED_RECONCILIATION_INDEX,
        reconciliation_ciks=set(),
        include_same_index_issuers=True,
    )

    assert [(row["form"], row["cik"], row["collection_scope"]) for row in rows] == [
        ("S-3", "0001234567", "registration_issuance"),
        ("8-K", "0001234567", "issuer_reconciliation"),
        ("10-Q", "0001234567", "issuer_reconciliation"),
    ]


def test_relevant_document_selection_never_invents_a_primary():
    documents = (
        SubmissionDocument("1", "GRAPHIC", "cover.jpg", None, b"graphic"),
        SubmissionDocument("2", "EX-10.1", "agreement.htm", None, b"agreement"),
    )

    selected = select_relevant_documents("S-3", documents)

    assert [(role, document.filename) for role, document in selected] == [
        ("exhibit", "agreement.htm")
    ]


def test_source_inspector_preserves_supported_text_types_and_defers_binary():
    html = inspect_source_document(
        b"<TYPE>S-3\n<TEXT><html><body>terms</body></html></TEXT>",
        filename="terms.htm",
        document_role="primary",
    )
    xml = inspect_source_document(
        b"<TYPE>XML\n<TEXT><?xml version='1.0'?><terms/></TEXT>",
        filename="terms.xml",
        document_role="exhibit",
    )
    pdf = inspect_source_document(
        b"<TYPE>EX-10\n<TEXT>%PDF-1.7\nopaque bytes</TEXT>",
        filename="agreement.pdf",
        document_role="exhibit",
    )
    opaque = inspect_source_document(
        b"<TYPE>EX-10\n<TEXT>\x00\x01\x02opaque</TEXT>",
        filename="agreement.bin",
        document_role="exhibit",
    )

    assert html == DocumentInspection("text/html", "eligible", "clean")
    assert xml == DocumentInspection("application/xml", "eligible", "clean")
    assert pdf == DocumentInspection("application/pdf", "deferred", "clean")
    assert opaque == DocumentInspection(
        "application/octet-stream", "deferred", "unreadable"
    )


def test_source_inspector_defers_suspect_complete_submission_and_extension_conflict():
    error_page = inspect_source_document(
        b"<html><body>access denied</body></html>",
        filename="complete-submission.txt",
        document_role="complete_submission",
    )
    fake_pdf = inspect_source_document(
        b"<TYPE>EX-10\n<TEXT>not actually a pdf</TEXT>",
        filename="agreement.pdf",
        document_role="exhibit",
    )
    fake_html = inspect_source_document(
        b"<TYPE>EX-10\n<TEXT>not actually html</TEXT>",
        filename="agreement.htm",
        document_role="exhibit",
    )
    truncated = inspect_source_document(
        b"<DOCUMENT>one</DOCUMENT><DOCUMENT>two",
        filename="complete-submission.txt",
        document_role="complete_submission",
    )

    assert error_page == DocumentInspection("text/plain", "deferred", "suspect")
    assert fake_pdf == DocumentInspection("application/pdf", "deferred", "suspect")
    assert fake_html == DocumentInspection("text/html", "deferred", "suspect")
    assert truncated == DocumentInspection("text/plain", "deferred", "suspect")


def test_only_clean_eligible_complete_submission_closes_retrieval_queue():
    manifests = [
        {
            "filing": {
                "accession": "clean",
                "file_number": "333-123456",
                "file_number_provenance": {
                    "state": "observed", "value": "333-123456",
                    "candidate_values": ["333-123456"],
                    "sources": ["legacy_sgml_file_number"],
                },
            },
            "document": {"document_role": "complete_submission"},
            "parser": {"eligibility": "eligible", "corruption_state": "clean"},
        },
        {
            "filing": {
                "accession": "suspect",
                "file_number": None,
                "file_number_provenance": {
                    "state": "unavailable", "value": None,
                    "candidate_values": [], "sources": [],
                },
            },
            "document": {"document_role": "complete_submission"},
            "parser": {"eligibility": "deferred", "corruption_state": "suspect"},
        },
        {
            "filing": {"accession": "legacy", "file_number": "333-123456"},
            "document": {"document_role": "complete_submission"},
            "parser": {"eligibility": "eligible", "corruption_state": "clean"},
        },
    ]

    assert sec._eligible_complete_accessions(manifests) == {"clean"}


def test_legacy_complete_manifest_gets_one_bounded_provenance_backfill():
    discovery = pd.DataFrame([{
        "accession": "legacy", "cik": "0001234567", "form": "S-3",
        "filing_date": "2026-08-01", "collection_scope": None,
        "_first_seen": "2026-08-01T11:00:00Z",
    }])
    legacy = [{
        "filing": {"accession": "legacy", "file_number": "333-123456"},
        "document": {"document_role": "complete_submission"},
        "parser": {"eligibility": "eligible", "corruption_state": "clean"},
    }]
    hardened = [*legacy, {
        "filing": {
            "accession": "legacy", "file_number": None,
            "file_number_provenance": {
                "state": "unavailable", "value": None,
                "candidate_values": [], "sources": [],
            },
        },
        "document": {"document_role": "complete_submission"},
        "parser": {"eligibility": "eligible", "corruption_state": "clean"},
    }]
    now = datetime(2026, 8, 2, 13, 0, tzinfo=timezone.utc)

    first = select_retrieval_queue(
        discovery,
        have_complete=sec._eligible_complete_accessions(legacy),
        max_filings=1,
        now=now,
    )
    second = select_retrieval_queue(
        discovery,
        have_complete=sec._eligible_complete_accessions(hardened),
        max_filings=1,
        now=now,
    )

    assert first["accession"].tolist() == ["legacy"]
    assert first.attrs["retrieval_queue_receipt"]["selected_count"] == 1
    assert second.empty
    assert second.attrs["retrieval_queue_receipt"]["selected_count"] == 0


def test_zero_target_index_day_is_complete_and_not_due_again():
    coverage = pd.DataFrame([{
        "index_date": "2026-07-31", "status": "complete", "target_count": 0,
        "attempt_count": 1, "last_attempt_at": "2026-08-01T00:00:00Z",
        "last_error": None, "policy_version": sec.FORM_POLICY["policy_version"],
    }])
    due = due_index_dates(
        coverage, today=date(2026, 7, 31), lookback_days=1, full_history=False
    )
    assert due == []
    assert due_index_dates(
        coverage, today=date(2026, 7, 31), lookback_days=1, full_history=True
    ) == [date(2026, 7, 31)]


def test_failed_index_older_than_nightly_lookback_remains_due():
    coverage = pd.DataFrame([
        {
            "index_date": "2026-07-31",
            "status": "retry",
        },
        {
            "index_date": "2026-07-30",
            "status": "complete",
            "policy_version": sec.FORM_POLICY["policy_version"],
        },
        {
            "index_date": "2026-07-29",
            "status": "complete",
            "policy_version": "capital-structure-sec-form-policy/0.9.0",
        },
    ])

    due = due_index_dates(
        coverage,
        today=date(2026, 8, 10),
        lookback_days=7,
        full_history=False,
    )

    assert date(2026, 7, 31) in due
    assert date(2026, 7, 30) not in due
    assert date(2026, 7, 29) in due


def test_full_history_flag_revalidates_bounded_ninety_day_window(
    tmp_path, monkeypatch
):
    root = tmp_path / "capital_structure"
    root.mkdir(parents=True)
    row = parse_form_index(SINGLE_INDEX)[0] | {
        "ticker": "ACME",
        "_first_seen": "2026-07-31T12:00:00Z",
    }
    pd.DataFrame([row]).reindex(columns=sec._DISCOVERY_COLUMNS).to_parquet(
        root / "discovery.parquet", index=False
    )
    captured = {}

    def capture_due(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(sec, "_data_dir", lambda: root)
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "due_index_dates", capture_due)
    adapter = SecCapitalStructureAdapter(
        source_store=object(),
        now_fn=lambda: datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=0,
    )

    adapter.fetch(full_history=True)

    assert captured["lookback_days"] == sec.LOOKBACK_DAYS_FIRST == 90
    assert captured["full_history"] is True
    assert captured["today"] == date(2026, 7, 31)


def test_structured_note_prospectuses_cannot_starve_registration_evidence():
    assert retrieval_priority("S-3") < retrieval_priority("424B5")
    assert retrieval_priority("424B5") < retrieval_priority("424B2")


def test_retrieval_queue_hard_priority_and_aging_prevent_starvation():
    rows = [
        {
            "accession": f"note-{index}",
            "form": "424B2",
            "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        }
        for index in range(100)
    ]
    rows.extend([
        {
            "accession": "registration-aged",
            "form": "S-3",
            "filing_date": "2026-07-20",
            "_first_seen": "2026-07-20T11:00:00Z",
        },
        {
            "accession": "registration-new",
            "form": "S-3",
            "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        },
    ])

    queue = select_retrieval_queue(
        pd.DataFrame(rows),
        have_complete=set(),
        max_filings=2,
        now=datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
    )

    assert queue["accession"].tolist() == [
        "registration-aged",
        "registration-new",
    ]
    assert not queue["form"].eq("424B2").any()


def test_saturated_prospectus_lane_cannot_starve_effect_or_scoped_reconciliation():
    now = datetime(2026, 8, 14, 13, 0, tzinfo=timezone.utc)
    rows = [
        {
            "accession": f"prospectus-{index:03d}",
            "cik": "0001234567",
            "form": "424B5",
            "collection_scope": "registration_issuance",
            "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        }
        for index in range(100)
    ]
    rows.extend([
        {
            "accession": "registration-anchor", "cik": "0001234567", "form": "S-3",
            "collection_scope": "registration_issuance", "filing_date": "2026-08-14",
            "_first_seen": "2026-08-14T11:00:00Z",
        },
        {
            "accession": "effect-notice", "cik": "0001234567", "form": "EFFECT",
            "collection_scope": "registration_issuance", "filing_date": "2026-08-14",
            "_first_seen": "2026-08-14T11:00:00Z",
        },
        {
            "accession": "current-report-fee-exhibit", "cik": "0001234567", "form": "8-K",
            "collection_scope": "issuer_reconciliation", "filing_date": "2026-08-14",
            "_first_seen": "2026-08-14T11:00:00Z",
        },
        {
            "accession": "periodic-reconciliation", "cik": "0001234567", "form": "10-Q",
            "collection_scope": "issuer_reconciliation", "filing_date": "2026-08-14",
            "_first_seen": "2026-08-14T11:00:00Z",
        },
    ])

    queue = select_retrieval_queue(
        pd.DataFrame(rows),
        have_complete=set(),
        max_filings=sum(sec.RETRIEVAL_LANE_WEIGHTS.values()),
        now=now,
    )
    receipt = queue.attrs["retrieval_queue_receipt"]
    schema = json.loads((
        Path(__file__).resolve().parents[1]
        / "contracts/capital_structure_retrieval_queue_receipt.schema.json"
    ).read_text())

    assert {"effect-notice", "current-report-fee-exhibit", "periodic-reconciliation"} <= set(
        queue["accession"]
    )
    assert not list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt))
    by_lane = {row["lane"]: row for row in receipt["lanes"]}
    assert by_lane["prospectus"]["deferred_count"] > 0
    assert by_lane["state"]["selected_count"] == 1
    assert by_lane["issuer_current_report"]["selected_count"] == 1
    assert by_lane["issuer_periodic"]["selected_count"] == 1
    assert by_lane["prospectus"]["oldest_pending_age_days"] == 13
    assert sum(receipt["lane_quota_slots"].values()) == receipt["max_filings"]

    fee_documents = (
        SubmissionDocument("1", "8-K", "current.htm", None, b"current"),
        SubmissionDocument("2", "EX-FILING FEES", "fees.htm", None, b"fees"),
    )
    assert ("filing_fee_exhibit", fee_documents[1]) in select_relevant_documents(
        "8-K", fee_documents
    )


def test_rotating_quota_ties_eventually_offer_every_populated_lane_a_turn():
    rows = [
        {
            "accession": "registration", "cik": "0001234567", "form": "S-3",
            "collection_scope": "registration_issuance", "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        },
        {
            "accession": "state", "cik": "0001234567", "form": "EFFECT",
            "collection_scope": "registration_issuance", "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        },
        {
            "accession": "prospectus", "cik": "0001234567", "form": "424B5",
            "collection_scope": "registration_issuance", "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        },
        {
            "accession": "reg-a", "cik": "0001234567", "form": "1-A",
            "collection_scope": "registration_issuance", "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        },
        {
            "accession": "current", "cik": "0001234567", "form": "8-K",
            "collection_scope": "issuer_reconciliation", "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        },
        {
            "accession": "periodic", "cik": "0001234567", "form": "10-Q",
            "collection_scope": "issuer_reconciliation", "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        },
        {
            "accession": "proxy", "cik": "0001234567", "form": "DEF 14A",
            "collection_scope": "issuer_reconciliation", "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        },
    ]
    discovery = pd.DataFrame(rows)
    offered: set[str] = set()
    for day in range(sum(sec.RETRIEVAL_LANE_WEIGHTS.values())):
        now = datetime(2026, 8, 1 + day, 13, 0, tzinfo=timezone.utc)
        queue = select_retrieval_queue(
            discovery, have_complete=set(), max_filings=1, now=now
        )
        offered.add(queue.iloc[0]["accession"])
        assert retrieval_lane_quotas(max_filings=1, now=now) == (
            queue.attrs["retrieval_queue_receipt"]["lane_quota_slots"]
        )

    assert offered == {row["accession"] for row in rows}


def test_full_weighted_cycle_records_exact_per_lane_selection_counts():
    now = datetime(2026, 8, 14, 13, 0, tzinfo=timezone.utc)
    lane_forms = {
        "registration": ("S-3", "registration_issuance"),
        "state": ("EFFECT", "registration_issuance"),
        "prospectus": ("424B5", "registration_issuance"),
        "reg_a": ("1-A", "registration_issuance"),
        "issuer_current_report": ("8-K", "issuer_reconciliation"),
        "issuer_periodic": ("10-Q", "issuer_reconciliation"),
        "issuer_proxy": ("DEF 14A", "issuer_reconciliation"),
    }
    rows = [
        {
            "accession": f"{lane}-{index}", "cik": "0001234567", "form": form,
            "collection_scope": scope, "filing_date": "2026-08-14",
            "_first_seen": "2026-08-14T11:00:00Z",
        }
        for lane, (form, scope) in lane_forms.items()
        for index in range(5)
    ]

    queue = select_retrieval_queue(
        pd.DataFrame(rows),
        have_complete=set(),
        max_filings=sum(sec.RETRIEVAL_LANE_WEIGHTS.values()),
        now=now,
    )
    receipt = queue.attrs["retrieval_queue_receipt"]

    assert len(queue) == sum(sec.RETRIEVAL_LANE_WEIGHTS.values())
    assert retrieval_lane_quotas(
        max_filings=receipt["max_filings"], now=now
    ) == sec.RETRIEVAL_LANE_WEIGHTS
    assert {
        row["lane"]: row["selected_count"] for row in receipt["lanes"]
    } == sec.RETRIEVAL_LANE_WEIGHTS
    assert all(row["deferred_count"] >= 0 for row in receipt["lanes"])


def _w2_coverage_sessions(end: date = date(2026, 8, 28), count: int = 20) -> pd.DataFrame:
    sessions: list[dict] = []
    current = end
    while len(sessions) < count:
        if current.weekday() < 5:
            sessions.append({
                "index_date": current.isoformat(), "status": "complete",
                "policy_version": sec.FORM_POLICY["policy_version"],
            })
        current -= timedelta(days=1)
    return pd.DataFrame(sessions)


def _w2_row(accession: str, form: str, filing_date: str, *, first_seen: str) -> dict:
    return {
        "accession": accession, "cik": "0001234567", "form": form,
        "collection_scope": sec.DISCOVERY_SCOPE_REGISTRATION,
        "filing_date": filing_date, "_first_seen": first_seen,
    }


def test_work_class_reserves_protect_live_tail_and_preserve_lane_fairness():
    """18k historical rows cannot consume the 500/20/20 W2B reservations."""
    now = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    live_forms = ["S-3", "EFFECT", "424B5", "1-A"]
    old_rows = [
        _w2_row(
            f"historical-{index:05d}", live_forms[index % len(live_forms)], "2026-07-01",
            first_seen="2026-07-01T11:00:00Z",
        )
        for index in range(18_000)
    ]
    live_rows = [
        _w2_row(
            f"live-{index:03d}", live_forms[index % len(live_forms)], "2026-08-28",
            first_seen="2026-08-28T11:00:00Z",
        )
        for index in range(500)
    ]
    recovery_rows = [
        _w2_row(
            f"recovery-{index:03d}", live_forms[index % len(live_forms)], "2026-08-28",
            first_seen="2026-08-27T11:00:00Z",
        )
        for index in range(30)
    ]
    attempts = pd.DataFrame([
        {
            "accession": row["accession"], "state": "transient_error",
            "attempted_at": "2026-08-27T12:00:00Z",
        }
        for row in recovery_rows
    ])

    queue = select_retrieval_queue(
        pd.DataFrame([*old_rows, *live_rows, *recovery_rows]),
        have_complete=set(), max_filings=540, now=now,
        coverage=_w2_coverage_sessions(), attempts=attempts,
        current_run_arrivals={"live-000", "recovery-000"},
    )
    receipt = queue.attrs["retrieval_queue_receipt"]
    classes = {row["work_class"]: row for row in receipt["work_classes"]}

    assert len(queue) == 540
    assert receipt["class_quota_slots"] == {
        "LIVE_TAIL": 500, "RECOVERY": 20, "HISTORICAL_BACKFILL": 20,
    }
    assert {key: value["selected_count"] for key, value in classes.items()} == {
        "LIVE_TAIL": 500, "RECOVERY": 20, "HISTORICAL_BACKFILL": 20,
    }
    assert classes["LIVE_TAIL"]["current_run_arrivals"] == 1
    assert classes["RECOVERY"]["current_run_arrivals"] == 1
    assert classes["RECOVERY"]["live_session_pending_count"] == 30
    assert classes["RECOVERY"]["live_session_unserved_count"] == 10
    assert classes["HISTORICAL_BACKFILL"]["selected_count"] == 20
    assert receipt["live_tail_arrivals_current_run"] == 2
    assert receipt["live_tail_effective_capacity"] == 500
    assert receipt["live_tail_arrival_overflow"] == 0
    assert receipt["live_tail_pending_before_selection"] == 530
    assert receipt["live_tail_selected"] == 520
    assert receipt["live_tail_unserved_after_selection"] == 10
    # Every class runs the existing lane selector, rather than one global class
    # sort silently returning to a prospectus-only backlog.
    for work_class in sec.WORK_CLASS_ORDER:
        selected_lanes = {
            row["lane"] for row in classes[work_class]["lanes"]
            if row["selected_count"]
        }
        assert {"registration", "state", "prospectus", "reg_a"} <= selected_lanes


def test_one_current_effect_is_selected_ahead_of_eighteen_thousand_old_prospectuses():
    now = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    historical = [
        _w2_row(
            f"old-prospectus-{index:05d}", "424B5", "2026-07-01",
            first_seen="2026-07-01T11:00:00Z",
        )
        for index in range(18_000)
    ]
    current = _w2_row(
        "current-effect", "EFFECT", "2026-08-28",
        first_seen="2026-08-28T11:00:00Z",
    )

    queue = select_retrieval_queue(
        pd.DataFrame([*historical, current]),
        have_complete=set(), max_filings=540, now=now,
        coverage=_w2_coverage_sessions(), attempts=pd.DataFrame(),
        current_run_arrivals={"current-effect"},
    )
    receipt = queue.attrs["retrieval_queue_receipt"]

    assert "current-effect" in set(queue["accession"])
    assert receipt["live_tail_arrivals_current_run"] == 1
    assert receipt["live_tail_selected"] == 1
    assert len(queue) == sec.MAX_FILINGS_PER_RUN


def test_discovery_watermark_clock_belongs_to_the_newest_filing_date():
    now = datetime(2026, 9, 2, 13, 0, tzinfo=timezone.utc)
    rows = [
        _w2_row(
            "newest-filing", "S-3", "2026-08-28",
            first_seen="2026-08-28T23:00:00Z",
        ),
        _w2_row(
            "older-late-observation", "S-3", "2026-07-01",
            first_seen="2026-09-01T23:00:00Z",
        ),
    ]
    queue = select_retrieval_queue(
        pd.DataFrame(rows), have_complete=set(), max_filings=2, now=now,
        coverage=_w2_coverage_sessions(), attempts=pd.DataFrame(),
    )
    receipt = queue.attrs["retrieval_queue_receipt"]

    assert receipt["latest_discovered_in_policy_filing_date"] == "2026-08-28"
    assert receipt["latest_discovered_in_policy_observed_at"] == "2026-08-28T23:00:00Z"


def test_live_tail_uses_newest_session_first_under_current_ledger_shaped_pressure():
    """Five-session live debt cannot push the newest session behind the cap."""
    now = datetime(2026, 8, 22, 13, 0, tzinfo=timezone.utc)
    session_counts = {
        "2026-08-14": 485,
        "2026-08-17": 217,
        "2026-08-18": 190,
        "2026-08-19": 229,
        "2026-08-20": 199,
    }
    live_rows = [
        _w2_row(
            f"live-{filing_date}-{index:03d}", "S-3", filing_date,
            first_seen=f"{filing_date}T23:00:00Z",
        )
        for filing_date, count in session_counts.items()
        for index in range(count)
    ]
    historical = [
        _w2_row(
            f"historical-{index:03d}", "S-3", "2026-07-01",
            first_seen="2026-07-01T11:00:00Z",
        )
        for index in range(100)
    ]
    newest = {
        row["accession"] for row in live_rows
        if row["filing_date"] == "2026-08-20"
    }
    late_prior_session_arrivals = {
        row["accession"] for row in live_rows
        if row["filing_date"] == "2026-08-19"
    }
    late_prior_session_arrivals = set(sorted(late_prior_session_arrivals)[:10])

    queue = select_retrieval_queue(
        pd.DataFrame([*historical, *live_rows]),
        have_complete=set(), max_filings=540, now=now,
        coverage=_w2_coverage_sessions(end=date(2026, 8, 20)),
        attempts=pd.DataFrame(),
        current_run_arrivals=newest | late_prior_session_arrivals,
    )
    receipt = queue.attrs["retrieval_queue_receipt"]
    selected_classes = queue.attrs["retrieval_work_classes_by_accession"]
    selected_live = queue.loc[
        queue["accession"].map(selected_classes).eq("LIVE_TAIL")
    ]

    assert len(selected_live) == 520  # 500 reserve + empty RECOVERY spill
    assert newest <= set(selected_live["accession"])
    assert receipt["latest_discovered_in_policy_filing_date"] == "2026-08-20"
    assert receipt["live_tail_arrivals_current_run"] == 209
    assert receipt["live_tail_arrival_overflow"] == 0


def test_work_class_spill_is_deterministic_when_live_tail_is_empty_and_parked_is_excluded():
    now = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    rows = [
        _w2_row(
            f"historical-{index:05d}", "S-3", "2026-07-01",
            first_seen="2026-07-01T11:00:00Z",
        )
        for index in range(18_000)
    ]
    rows.extend(
        _w2_row(
            f"recovery-{index:02d}", "EFFECT", "2026-08-28",
            first_seen="2026-08-27T11:00:00Z",
        )
        for index in range(10)
    )
    attempts = pd.DataFrame([
        {
            "accession": f"recovery-{index:02d}", "state": "storage_deferred",
            "attempted_at": "2026-08-27T12:00:00Z",
        }
        for index in range(10)
    ])
    parked = {"historical-00000"}

    queue = select_retrieval_queue(
        pd.DataFrame(rows), have_complete=set(), max_filings=540, now=now,
        coverage=_w2_coverage_sessions(), attempts=attempts, parked=parked,
    )
    receipt = queue.attrs["retrieval_queue_receipt"]
    classes = {row["work_class"]: row for row in receipt["work_classes"]}

    assert len(queue) == 540
    assert "historical-00000" not in set(queue["accession"])
    assert classes["LIVE_TAIL"]["selected_count"] == 0
    assert classes["RECOVERY"]["selected_count"] == 10
    assert classes["HISTORICAL_BACKFILL"]["selected_count"] == 530
    assert receipt["spill_transfers"] == [
        {"donor": "LIVE_TAIL", "recipient": "HISTORICAL_BACKFILL", "slots": 500},
        {"donor": "RECOVERY", "recipient": "HISTORICAL_BACKFILL", "slots": 10},
    ]


def test_work_class_spill_returns_empty_recovery_and_historical_capacity_to_live_tail():
    now = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    rows = [
        _w2_row(
            f"live-{index:03d}", "S-3", "2026-08-28",
            first_seen="2026-08-28T11:00:00Z",
        )
        for index in range(600)
    ]

    queue = select_retrieval_queue(
        pd.DataFrame(rows), have_complete=set(), max_filings=999, now=now,
        coverage=_w2_coverage_sessions(), attempts=pd.DataFrame(),
        current_run_arrivals={row["accession"] for row in rows},
    )
    receipt = queue.attrs["retrieval_queue_receipt"]
    classes = {row["work_class"]: row for row in receipt["work_classes"]}

    assert len(queue) == 540
    assert classes["LIVE_TAIL"]["reserved_slots"] == 500
    assert classes["LIVE_TAIL"]["spill_in_slots"] == 40
    assert classes["LIVE_TAIL"]["selected_count"] == 540
    assert receipt["live_tail_effective_capacity"] == 540
    assert receipt["live_tail_arrival_overflow"] == 60
    assert receipt["live_tail_pending_before_selection"] == 600
    assert receipt["live_tail_selected"] == 540
    assert receipt["live_tail_unserved_after_selection"] == 60
    assert receipt["spill_transfers"] == [
        {"donor": "RECOVERY", "recipient": "LIVE_TAIL", "slots": 20},
        {"donor": "HISTORICAL_BACKFILL", "recipient": "LIVE_TAIL", "slots": 20},
    ]


def _w2b_lane_row(
    accession: str, lane: str, filing_date: str, *, first_seen: str,
) -> dict:
    forms = {
        "registration": "S-3",
        "state": "EFFECT",
        "prospectus": "424B5",
        "reg_a": "1-A",
        "issuer_current_report": "8-K",
        "issuer_periodic": "10-Q",
        "issuer_proxy": "DEF 14A",
    }
    row = _w2_row(
        accession, forms[lane], filing_date, first_seen=first_seen,
    )
    if lane.startswith("issuer_"):
        row["collection_scope"] = sec.DISCOVERY_SCOPE_RECONCILIATION
    return row


def _w2b_live_arrivals(count: int, *, filing_date: str = "2026-08-28") -> list[dict]:
    """Build one observed-shaped seven-lane completed-session cohort."""
    observed_max_lanes = [
        *("issuer_periodic",) * 190,
        *("issuer_current_report",) * 168,
        *("prospectus",) * 82,
        *("state",) * 19,
        *("registration",) * 13,
        *("issuer_proxy",) * 8,
        *("reg_a",) * 5,
    ]
    lanes = [
        observed_max_lanes[index % len(observed_max_lanes)]
        for index in range(count)
    ]
    return [
        _w2b_lane_row(
            f"arrival-{count:03d}-{index:03d}", lane, filing_date,
            first_seen=f"{filing_date}T11:00:00Z",
        )
        for index, lane in enumerate(lanes)
    ]


def test_w2b_485_arrivals_all_land_with_recovery_and_history_protected():
    now = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    arrivals = _w2b_live_arrivals(485)
    recovery = [
        _w2_row(
            f"recovery-envelope-{index:03d}", "EFFECT", "2026-08-26",
            first_seen="2026-08-26T11:00:00Z",
        )
        for index in range(20)
    ]
    historical = [
        _w2_row(
            f"historical-envelope-{index:05d}", "424B5", "2026-07-01",
            first_seen="2026-07-01T11:00:00Z",
        )
        for index in range(2_000)
    ]
    attempts = pd.DataFrame([
        {
            "accession": row["accession"], "state": "transient_error",
            "attempted_at": "2026-08-27T12:00:00Z",
        }
        for row in recovery
    ])
    arrival_ids = {row["accession"] for row in arrivals}

    queue = select_retrieval_queue(
        pd.DataFrame([*historical, *arrivals, *recovery]),
        have_complete=set(), max_filings=540, now=now,
        coverage=_w2_coverage_sessions(), attempts=attempts,
        current_run_arrivals=arrival_ids,
    )
    receipt = queue.attrs["retrieval_queue_receipt"]
    classes = {row["work_class"]: row for row in receipt["work_classes"]}

    assert len(queue) == 540
    assert arrival_ids <= set(queue["accession"])
    assert receipt["class_quota_slots"] == {
        "LIVE_TAIL": 485, "RECOVERY": 20, "HISTORICAL_BACKFILL": 35,
    }
    assert {name: row["selected_count"] for name, row in classes.items()} == {
        "LIVE_TAIL": 485, "RECOVERY": 20, "HISTORICAL_BACKFILL": 35,
    }
    assert receipt["live_tail_arrivals_current_run"] == 485
    assert receipt["live_tail_arrival_overflow"] == 0
    assert {
        lane["lane"] for lane in classes["LIVE_TAIL"]["lanes"]
        if lane["selected_count"]
    } == set(sec.RETRIEVAL_LANE_ORDER)


def test_w2b_empty_recovery_spills_exactly_twenty_slots_to_live():
    now = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    arrivals = _w2b_live_arrivals(520)
    historical = [
        _w2_row(
            f"historical-spill-{index:04d}", "424B5", "2026-07-01",
            first_seen="2026-07-01T11:00:00Z",
        )
        for index in range(1_000)
    ]
    queue = select_retrieval_queue(
        pd.DataFrame([*historical, *arrivals]), have_complete=set(),
        max_filings=540, now=now, coverage=_w2_coverage_sessions(),
        attempts=pd.DataFrame(),
        current_run_arrivals={row["accession"] for row in arrivals},
    )
    receipt = queue.attrs["retrieval_queue_receipt"]

    assert receipt["class_quota_slots"] == {
        "LIVE_TAIL": 520, "RECOVERY": 0, "HISTORICAL_BACKFILL": 20,
    }
    assert receipt["spill_transfers"] == [
        {"donor": "RECOVERY", "recipient": "LIVE_TAIL", "slots": 20},
    ]
    assert receipt["live_tail_arrival_overflow"] == 0
    assert receipt["live_tail_unserved_after_selection"] == 0
    assert len(queue) == 540


@pytest.mark.parametrize(
    ("arrivals", "overflow", "unserved"),
    [(500, 0, 0), (501, 1, 1)],
)
def test_w2b_arrival_overflow_uses_current_arrivals_not_inherited_debt(
    arrivals: int, overflow: int, unserved: int,
):
    now = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    live = _w2b_live_arrivals(arrivals)
    recovery = [
        _w2_row(
            f"recovery-overflow-{index:03d}", "EFFECT", "2026-08-26",
            first_seen="2026-08-26T11:00:00Z",
        )
        for index in range(20)
    ]
    historical = [
        _w2_row(
            f"historical-overflow-{index:04d}", "424B5", "2026-07-01",
            first_seen="2026-07-01T11:00:00Z",
        )
        for index in range(100)
    ]
    attempts = pd.DataFrame([
        {
            "accession": row["accession"], "state": "storage_deferred",
            "attempted_at": "2026-08-27T12:00:00Z",
        }
        for row in recovery
    ])
    queue = select_retrieval_queue(
        pd.DataFrame([*historical, *live, *recovery]), have_complete=set(),
        max_filings=540, now=now, coverage=_w2_coverage_sessions(),
        attempts=attempts,
        current_run_arrivals={row["accession"] for row in live},
    )
    receipt = queue.attrs["retrieval_queue_receipt"]

    assert len(queue) == 540
    assert receipt["live_tail_effective_capacity"] == 500
    assert receipt["live_tail_arrivals_current_run"] == arrivals
    assert receipt["live_tail_arrival_overflow"] == overflow
    assert receipt["live_tail_unserved_after_selection"] == unserved


def test_reconciliation_row_without_registration_anchor_is_not_queue_eligible():
    queue = select_retrieval_queue(
        pd.DataFrame([{
            "accession": "unanchored-current", "cik": "0007654321", "form": "8-K",
            "collection_scope": "issuer_reconciliation", "filing_date": "2026-08-01",
            "_first_seen": "2026-08-01T11:00:00Z",
        }]),
        have_complete=set(),
        max_filings=10,
        now=datetime(2026, 8, 2, 13, 0, tzinfo=timezone.utc),
    )

    assert queue.empty
    assert queue.attrs["retrieval_queue_receipt"]["selected_count"] == 0


def test_manifest_record_conforms_to_strict_contract():
    discovery = parse_form_index(INDEX)[0] | {
        "ticker": "ACME", "_first_seen": "2026-08-01T12:35:00+00:00"
    }
    bundle = parse_submission(SUBMISSION)
    digest = __import__("hashlib").sha256(SUBMISSION).hexdigest()
    receipt = SourceReceipt(
        object_key=f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
        sha256=digest, byte_length=len(SUBMISSION), media_type="text/plain", backend="r2",
        store_id=STORE_ID_DEDICATED_R2,
    )
    record = SecCapitalStructureAdapter._manifest_record(
        discovery=discovery, bundle=bundle,
        source_id="0001234567-26-000001:0:complete-submission.txt",
        canonical_url=discovery["canonical_url"],
        document_name="complete-submission.txt", document_type="S-3",
        document_role="complete_submission", sequence="0", raw=SUBMISSION,
        receipt=receipt,
        inspection=DocumentInspection("text/plain", "eligible", "clean"),
        retrieved_at="2026-08-01T12:36:00+00:00",
        first_seen_at=discovery["_first_seen"], document_version=1,
        parent_manifest_id=None,
    )
    schema = json.loads((
        Path(__file__).resolve().parents[1]
        / "contracts/capital_structure_source_manifest.schema.json"
    ).read_text())
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record))
    assert not errors, [error.message for error in errors]
    assert record["privacy"] == {"classification": "public", "contains_personal_data": True}
    assert record["storage"]["store_id"] == STORE_ID_DEDICATED_R2
    assert record["manifest_id"] == manifest_id_for(record)

    bad_receipt = SourceReceipt(
        object_key=receipt.object_key, sha256="0" * 64, byte_length=len(SUBMISSION),
        media_type="text/plain", backend="r2",
        store_id=STORE_ID_DEDICATED_R2,
    )
    try:
        SecCapitalStructureAdapter._manifest_record(
            discovery=discovery, bundle=bundle, source_id="bad", canonical_url=discovery["canonical_url"],
            document_name="complete-submission.txt", document_type="S-3",
            document_role="complete_submission", sequence="0", raw=SUBMISSION,
            receipt=bad_receipt,
            inspection=DocumentInspection("text/plain", "eligible", "clean"),
            retrieved_at="2026-08-01T12:36:00+00:00",
            first_seen_at=discovery["_first_seen"], document_version=1,
            parent_manifest_id=None,
        )
    except ValueError as exc:
        assert "receipt" in str(exc)
    else:
        raise AssertionError("mismatched storage receipt was accepted")


class OneDayAdapter(SecCapitalStructureAdapter):
    def _fetch_index(self, value, ua):
        return BUSINESS_DAY_INDEX

    def _fetch_submission(self, url, ua):
        return SUBMISSION


class CrossIndexScopeAdapter(SecCapitalStructureAdapter):
    def _fetch_index(self, value, ua):
        return {
            date(2026, 8, 4): RECONCILIATION_ONLY_INDEX,
            date(2026, 8, 3): REGISTRATION_ONLY_INDEX,
        }[value]

    def _fetch_submission(self, url, ua):
        raise AssertionError("zero-budget scope test must not fetch a submission")


class HtmlIndexAdapter(SecCapitalStructureAdapter):
    def _fetch_index(self, value, ua):
        return "<html><body>temporary SEC error</body></html>"

    def _fetch_submission(self, url, ua):
        raise AssertionError("invalid index must never create a retrieval queue")


class MissingIndexAdapter(SecCapitalStructureAdapter):
    def _fetch_index(self, value, ua):
        raise sec.IndexNotPublished(value, 404)

    def _fetch_submission(self, url, ua):
        raise AssertionError("missing index must never create a retrieval queue")


class ForbiddenIndexAdapter(SecCapitalStructureAdapter):
    def _fetch_index(self, value, ua):
        response = requests.Response()
        response.status_code = 403
        raise requests.HTTPError("HTTP 403", response=response)

    def _fetch_submission(self, url, ua):
        raise AssertionError("forbidden index must never create a retrieval queue")


class CalendarClosedAdapter(SecCapitalStructureAdapter):
    def _fetch_index(self, value, ua):
        raise AssertionError("calendar closure must skip the network")

    def _fetch_submission(self, url, ua):
        raise AssertionError("calendar closure must never create a retrieval queue")


def test_html_index_response_stays_retryable_and_never_closes_zero_target_day(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    adapter = HtmlIndexAdapter(
        now_fn=lambda: datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=0,
    )

    heartbeat = adapter.fetch()["sec_evidence__ingest"]

    coverage = pd.read_parquet(
        tmp_path / "capital_structure" / "index_coverage.parquet"
    )
    assert coverage.iloc[0]["status"] == "retry"
    assert pd.isna(coverage.iloc[0]["target_count"])
    assert "response is HTML" in coverage.iloc[0]["last_error"]
    assert int(heartbeat.iloc[0]["index_days_complete"]) == 0


def test_repeated_aged_404_is_terminal_but_same_day_404_remains_retryable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    due_dates = [date(2026, 7, 31), date(2026, 8, 10)]
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: list(due_dates)
    )
    adapter = MissingIndexAdapter(
        now_fn=lambda: datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=0,
    )

    adapter.fetch()
    adapter.fetch()

    coverage = pd.read_parquet(
        tmp_path / "capital_structure" / "index_coverage.parquet"
    ).set_index("index_date")
    assert coverage.loc["2026-07-31", "status"] == "not_published"
    assert coverage.loc["2026-08-10", "status"] == "retry"
    assert int(coverage.loc["2026-07-31", "attempt_count"]) == 2
    assert int(coverage.loc["2026-08-10", "attempt_count"]) == 2
    due = due_index_dates(
        coverage.reset_index(),
        today=date(2026, 8, 10),
        lookback_days=7,
    )
    assert date(2026, 7, 31) not in due
    assert date(2026, 8, 10) in due


def test_repeated_aged_generic_403_never_becomes_not_published(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    adapter = ForbiddenIndexAdapter(
        now_fn=lambda: datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=0,
    )

    adapter.fetch()
    adapter.fetch()

    coverage = pd.read_parquet(
        tmp_path / "capital_structure" / "index_coverage.parquet"
    )
    assert coverage.iloc[0]["status"] == "retry"
    assert int(coverage.iloc[0]["attempt_count"]) == 2
    assert "HTTPError: HTTP 403" in coverage.iloc[0]["last_error"]


def test_observed_federal_holiday_is_terminal_without_network(
    tmp_path, monkeypatch
):
    holiday = date(2026, 7, 3)  # Observed Independence Day (July 4 is Saturday).
    assert sec.is_sec_calendar_closed(holiday)
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [holiday]
    )
    adapter = CalendarClosedAdapter(
        now_fn=lambda: datetime(2026, 7, 10, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=0,
    )

    adapter.fetch()

    coverage = pd.read_parquet(
        tmp_path / "capital_structure" / "index_coverage.parquet"
    )
    assert coverage.iloc[0]["status"] == "not_published"
    assert coverage.iloc[0]["last_error"].startswith("SEC calendar closure")


def test_adapter_materializes_discovery_coverage_verified_manifests_and_attempts(
    tmp_path, monkeypatch
):
    business_day_index = INDEX
    for filing_date in ("20260801", "20260802", "20260803", "20260804", "20260805"):
        business_day_index = business_day_index.replace(filing_date, "20260731")
    monkeypatch.setattr(
        OneDayAdapter,
        "_fetch_index",
        lambda self, value, ua: business_day_index,
    )
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    store = ContentAddressedSourceStore(LocalStore(tmp_path / "objects"), backend="local")
    adapter = OneDayAdapter(
        source_store=store,
        now_fn=lambda: datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=10,
    )

    heartbeat = adapter.fetch()["sec_evidence__ingest"]

    root = tmp_path / "capital_structure"
    discovery = pd.read_parquet(root / "discovery.parquet")
    coverage = pd.read_parquet(root / "index_coverage.parquet")
    manifests = pd.DataFrame(read_source_ledger(source_ledger_path(root)))
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    queue_receipt = json.loads((root / "retrieval_queue_receipt.json").read_text())
    ingestion = json.loads((root / "ingestion_run.json").read_text())
    assert len(discovery) == 4
    assert coverage.iloc[0]["status"] == "complete"
    assert set(manifests["document"].map(lambda value: value["document_role"])) == {
        "complete_submission", "primary", "exhibit"
    }
    manifest_by_name = {
        value["document_name"]: (value, parser)
        for value, parser in zip(manifests["document"], manifests["parser"])
    }
    assert manifest_by_name["complete-submission.txt"][0]["media_type"] == "text/plain"
    assert manifest_by_name["forms3.htm"][0]["media_type"] == "text/html"
    assert manifest_by_name["purchase.htm"][0]["media_type"] == "text/html"
    assert manifest_by_name["forms3.htm"][1]["eligibility"] == "eligible"
    assert attempts.iloc[0]["state"] == "stored"
    assert attempts["work_class"].notna().all()
    assert set(attempts["work_class"]) <= set(sec.WORK_CLASS_ORDER)
    assert "LIVE_TAIL" in set(attempts["work_class"])
    assert set(attempts["retrieval_lane"]) == {
        "registration", "state", "prospectus", "reg_a"
    }
    assert queue_receipt["selected_count"] == 4
    assert queue_receipt["deferred_count"] == 0
    assert [row["lane"] for row in queue_receipt["lanes"]] == list(
        sec.RETRIEVAL_LANE_ORDER
    )
    assert int(heartbeat.iloc[0]["retrieved"]) == 4
    progress = {
        row["work_class"]: row for row in ingestion["work_classes"]
    }
    assert set(progress) == set(sec.WORK_CLASS_ORDER)
    for work_class in sec.WORK_CLASS_ORDER:
        class_attempts = attempts.loc[attempts["work_class"].eq(work_class)]
        assert progress[work_class] == {
            "work_class": work_class,
            "attempted_count": len(class_attempts),
            "retrieved_count": int(class_attempts["state"].eq("stored").sum()),
            "parser_deferred_count": int(
                class_attempts["state"].eq("stored_parser_deferred").sum()
            ),
            "storage_deferred_count": int(
                class_attempts["state"].eq("storage_deferred").sum()
            ),
            "transient_error_count": int(
                class_attempts["state"].eq("transient_error").sum()
            ),
        }

    rerun = adapter.fetch()["sec_evidence__ingest"]
    assert len(pd.DataFrame(read_source_ledger(source_ledger_path(root)))) == len(manifests)
    assert len(pd.read_parquet(root / "retrieval_attempts.parquet")) == len(attempts)
    assert int(rerun.iloc[0]["retrieved"]) == 0


def test_cross_index_registration_anchor_scopes_newer_reconciliation_row(
    tmp_path, monkeypatch
):
    """A current-first traversal must not discard a recon row before its anchor."""
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec,
        "due_index_dates",
        lambda *args, **kwargs: [date(2026, 8, 4), date(2026, 8, 3)],
    )
    adapter = CrossIndexScopeAdapter(
        source_store=object(),
        now_fn=lambda: datetime(2026, 8, 4, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=0,
    )

    adapter.fetch()

    discovery = pd.read_parquet(
        tmp_path / "capital_structure" / "discovery.parquet"
    )
    scopes = dict(zip(discovery["form"], discovery["collection_scope"]))
    assert scopes == {
        "8-K": "issuer_reconciliation",
        "S-3": "registration_issuance",
    }


def test_old_discovery_ledger_is_migrated_with_null_collection_scope(tmp_path):
    """Wave 2C must not make a pre-existing append-only ledger unreadable."""
    legacy_columns = LEGACY_DISCOVERY_COLUMNS
    path = tmp_path / "discovery.parquet"
    pd.DataFrame([{
        "accession": "legacy", "cik": "0001234567", "ticker": "ACME",
        "company_name": "Acme Corp", "form": "S-3", "filing_date": "2026-08-01",
        "file_path": "edgar/data/1234567/legacy.txt",
        "canonical_url": "https://www.sec.gov/Archives/edgar/data/1234567/legacy.txt",
        "_first_seen": "2026-08-01T12:00:00Z",
    }])[legacy_columns].to_parquet(path, index=False)

    migrated = sec._read_table(path, sec._DISCOVERY_COLUMNS)

    assert list(migrated.columns) == sec._DISCOVERY_COLUMNS
    assert pd.isna(migrated.iloc[0]["collection_scope"])


def test_existing_manifest_identity_mismatch_aborts_before_append(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    store = ContentAddressedSourceStore(
        LocalStore(tmp_path / "objects"), backend="local"
    )
    adapter = OneDayAdapter(
        source_store=store,
        now_fn=lambda: datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=1,
    )
    adapter.fetch()
    path = source_ledger_path(tmp_path / "capital_structure")
    records = read_source_ledger(path)
    records[0]["rights"] = {
        **records[0]["rights"],
        "license_note": "tampered after identity assignment",
    }
    _write_ledger(path, records)

    with pytest.raises(ManifestIdentityError, match="source ledger row 0"):
        adapter.fetch()


def test_manifest_clock_is_stamped_after_bundle_readback_completion(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    clocks = iter([
        datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 1, 13, 1, tzinfo=timezone.utc),
        datetime(2026, 8, 1, 13, 5, tzinfo=timezone.utc),
    ])
    store = ContentAddressedSourceStore(
        LocalStore(tmp_path / "objects"), backend="local"
    )
    adapter = OneDayAdapter(
        source_store=store,
        now_fn=lambda: next(clocks),
        max_filings_per_run=1,
    )

    adapter.fetch()

    root = tmp_path / "capital_structure"
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    manifests = pd.DataFrame(read_source_ledger(source_ledger_path(root)))
    assert attempts.iloc[0]["attempted_at"] == "2026-08-01T13:01:00+00:00"
    assert {
        retrieval["retrieved_at"] for retrieval in manifests["retrieval"]
    } == {"2026-08-01T13:05:00+00:00"}
    assert {
        retrieval["first_seen_at"] for retrieval in manifests["retrieval"]
    } == {"2026-08-01T13:05:00+00:00"}


class FailingSourceStore:
    def put_verified(self, raw, media_type="application/octet-stream"):
        return None


def test_storage_failure_records_retryable_attempt_and_emits_no_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    adapter = OneDayAdapter(
        source_store=FailingSourceStore(),
        now_fn=lambda: datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=1,
    )

    adapter.fetch()

    root = tmp_path / "capital_structure"
    manifests = pd.DataFrame(read_source_ledger(source_ledger_path(root)))
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    assert manifests.empty
    assert attempts.iloc[0]["state"] == "storage_deferred"
    assert "verification failed" in attempts.iloc[0]["error"]
    ingestion = json.loads((root / "ingestion_run.json").read_text())
    assert ingestion["verdict"] == "fail"
    assert ingestion["counters"]["selected"] >= 1
    assert ingestion["counters"]["manifested_sources"] == 0
    progress = {
        row["work_class"]: row for row in ingestion["work_classes"]
    }
    assert progress["LIVE_TAIL"]["attempted_count"] == 1
    assert progress["LIVE_TAIL"]["retrieved_count"] == 0
    assert progress["LIVE_TAIL"]["storage_deferred_count"] == 1


class FailFirstWriteSourceStore:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = 0

    def put_verified(self, raw, media_type="application/octet-stream"):
        self.calls += 1
        if self.calls == 1:
            return None
        return self.delegate.put_verified(raw, media_type=media_type)


def test_manifest_first_seen_clock_starts_at_successful_evidence_retention(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    clock = {"now": datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc)}
    delegate = ContentAddressedSourceStore(
        LocalStore(tmp_path / "objects"), backend="local"
    )
    source_store = FailFirstWriteSourceStore(delegate)
    adapter = OneDayAdapter(
        source_store=source_store,
        now_fn=lambda: clock["now"],
        max_filings_per_run=1,
    )

    adapter.fetch()
    clock["now"] = datetime(2026, 8, 2, 15, 30, tzinfo=timezone.utc)
    adapter.fetch()

    root = tmp_path / "capital_structure"
    discovery = pd.read_parquet(root / "discovery.parquet")
    manifests = pd.DataFrame(read_source_ledger(source_ledger_path(root)))
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    accession = manifests.iloc[0]["filing"]["accession"]
    discovery_time = discovery.loc[
        discovery["accession"] == accession, "_first_seen"
    ].iloc[0]
    manifest_times = {
        value["first_seen_at"] for value in manifests["retrieval"]
    }

    assert discovery_time == "2026-08-01T13:00:00+00:00"
    assert manifest_times == {"2026-08-02T15:30:00+00:00"}
    assert set(attempts["state"]) == {"storage_deferred", "stored"}


class SuspectThenValidAdapter(SecCapitalStructureAdapter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.submission_calls = 0

    def _fetch_index(self, value, ua):
        return SINGLE_BUSINESS_DAY_INDEX

    def _fetch_submission(self, url, ua):
        self.submission_calls += 1
        if self.submission_calls == 1:
            return b"<html><body>temporary SEC error</body></html>"
        return SUBMISSION


def test_suspect_bundle_retry_advances_closed_version_and_compiles(
    tmp_path, monkeypatch
):
    from scripts.compile_capital_structure_events import (
        compile_manifest_records,
        dataframe_records,
    )

    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 7, 31)]
    )
    clock = {"now": datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc)}
    store = ContentAddressedSourceStore(
        LocalStore(tmp_path / "objects"), backend="local"
    )
    adapter = SuspectThenValidAdapter(
        source_store=store,
        now_fn=lambda: clock["now"],
        max_filings_per_run=1,
    )

    first_heartbeat = adapter.fetch()["sec_evidence__ingest"]
    clock["now"] = datetime(2026, 8, 2, 15, 30, tzinfo=timezone.utc)
    second_heartbeat = adapter.fetch()["sec_evidence__ingest"]

    root = tmp_path / "capital_structure"
    manifests = pd.DataFrame(read_source_ledger(source_ledger_path(root)))
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    records = dataframe_records(manifests)
    version_one = [
        row for row in records if row["document"]["document_version"] == 1
    ]
    version_two = [
        row for row in records if row["document"]["document_version"] == 2
    ]
    complete_v2 = next(
        row for row in version_two
        if row["document"]["document_role"] == "complete_submission"
    )
    children_v2 = [
        row for row in version_two
        if row["document"]["document_role"] != "complete_submission"
    ]

    assert len(version_one) == 1
    assert version_one[0]["parser"] == {
        "corruption_state": "suspect",
        "eligibility": "deferred",
        "parser_version": "sec-source-inspector/1.0.0",
    }
    assert {row["document"]["document_version"] for row in version_two} == {2}
    assert children_v2
    assert {
        row["document"]["parent_manifest_id"] for row in children_v2
    } == {complete_v2["manifest_id"]}
    assert list(attempts["state"]) == ["stored_parser_deferred", "stored"]
    assert "parser deferred" in attempts.iloc[0]["error"]
    assert int(first_heartbeat.iloc[0]["retrieved"]) == 0
    assert int(first_heartbeat.iloc[0]["deferred"]) == 1
    assert int(first_heartbeat.iloc[0]["backlog"]) == 1
    assert int(second_heartbeat.iloc[0]["retrieved"]) == 1
    assert int(second_heartbeat.iloc[0]["deferred"]) == 0
    assert int(second_heartbeat.iloc[0]["backlog"]) == 0

    result = compile_manifest_records(
        records,
        manifest_schema=json.loads((
            Path(__file__).resolve().parents[1]
            / "contracts/capital_structure_source_manifest.schema.json"
        ).read_text()),
        generated_at="2026-08-02T16:00:00Z",
    )
    assert len(result["events"]) == 1
    assert result["telemetry"]["counts"]["compile_failures"] == 0


# ---------------------------------------------------------------------------
# W1-A nightly-unfreeze: the NaN manifest abort and the unbounded deferral.
#
# daily.yml failed 2026-08-03..08-06.  The 08-06 collect log carried 130 lines of
# ``sec_capital_structure: <accession> deferred: TypeError: non-finite numbers are
# not canonical manifest values`` — the same filings, every night, forever.
# ---------------------------------------------------------------------------


def test_iterrows_launders_a_null_discovery_scope_into_a_nan_sentinel():
    """Pin the mechanism: the row-Series build is what turns ``None`` into NaN.

    ``collection_scope`` is legitimately ``None`` for every discovery row written
    before Wave 2C added the column, and ``_read_table`` migrates it as ``None`` in
    an object column.  ``DataFrame.iterrows()`` then builds a per-row Series, and
    THAT construction substitutes ``float('nan')`` — pandas' missing-value sentinel.
    ``to_dict("records")`` does not.  If a future pandas stops laundering, this test
    goes red and the extra hop in the collector can be retired deliberately.
    """
    frame = pd.DataFrame([{"accession": "a", "collection_scope": None}])
    assert frame["collection_scope"].dtype == object
    assert frame.iloc[0]["collection_scope"] is None

    laundered = [series.to_dict()["collection_scope"] for _, series in frame.iterrows()]
    assert len(laundered) == 1
    assert isinstance(laundered[0], float) and math.isnan(laundered[0])

    assert frame.to_dict("records")[0]["collection_scope"] is None


def test_nan_scope_reaches_the_canonical_writer_as_a_typeerror():
    """The blast: a NaN anywhere in a manifest aborts canonical encoding.

    This is the exact exception the 08-06 nightly logged 130 times, raised from
    ``engine/capital_structure/source_identity.py`` ``_native``.  The guard is
    CORRECT and stays strict — a canonical manifest may not contain a non-finite
    number — so the repair belongs upstream, at the frame boundary.
    """
    with pytest.raises(TypeError, match="non-finite numbers are not canonical"):
        canonical_manifest_bytes({"filing": {"collection_scope": float("nan")}})


def test_manifest_scalar_nulls_every_pandas_missing_sentinel_and_never_zeroes():
    """NaN/NA/NaT become ``None``; real values and legitimate ``None`` are untouched."""
    sanitized: list[str] = []
    assert sec._manifest_scalar(float("nan"), field="filing.form", sanitized=sanitized) is None
    assert sec._manifest_scalar(pd.NA, field="filing.accession", sanitized=sanitized) is None
    assert sec._manifest_scalar(pd.NaT, field="filing.filing_date", sanitized=sanitized) is None
    assert sanitized == ["filing.form", "filing.accession", "filing.filing_date"]

    # A field that was ALREADY None is absent, not sanitized — reporting it would
    # make ``filing.file_number`` (null by contract on most filings) read as a defect.
    already: list[str] = []
    assert sec._manifest_scalar(None, field="filing.file_number", sanitized=already) is None
    assert already == []

    # Real values survive, and nothing is ever coerced to a fabricated 0.
    for value in ("S-3", "", 0, False, 12.5, ["a"], {"k": "v"}):
        assert sec._manifest_scalar(value, field="x", sanitized=already) == value
    assert already == []


def test_manifest_record_with_a_nan_scope_encodes_canonically(tmp_path):
    """The defect, end to end at the boundary that produced it.

    Feed ``_manifest_record`` the row EXACTLY as the retrieval loop used to hand it
    over — a NaN ``collection_scope`` and a NaN ``company_name`` — and require a
    canonically-encodable, schema-valid manifest.  On the pre-fix collector this
    raises ``TypeError: non-finite numbers are not canonical manifest values``
    inside ``manifest_id_for``.
    """
    discovery = parse_form_index(INDEX)[0] | {
        "ticker": "ACME",
        "_first_seen": "2026-08-01T12:35:00+00:00",
        # The two pandas sentinels a legacy discovery row carries after iterrows().
        "collection_scope": float("nan"),
        "company_name": float("nan"),
    }
    bundle = parse_submission(SUBMISSION)
    digest = __import__("hashlib").sha256(SUBMISSION).hexdigest()
    receipt = SourceReceipt(
        object_key=f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
        sha256=digest, byte_length=len(SUBMISSION), media_type="text/plain",
        backend="r2", store_id=STORE_ID_DEDICATED_R2,
    )
    sanitized: list[str] = []

    record = SecCapitalStructureAdapter._manifest_record(
        discovery=discovery, bundle=bundle,
        source_id="0001234567-26-000001:0:complete-submission.txt",
        canonical_url=discovery["canonical_url"],
        document_name="complete-submission.txt", document_type="S-3",
        document_role="complete_submission", sequence="0", raw=SUBMISSION,
        receipt=receipt,
        inspection=DocumentInspection("text/plain", "eligible", "clean"),
        retrieved_at="2026-08-01T12:36:00+00:00",
        first_seen_at=discovery["_first_seen"], document_version=1,
        parent_manifest_id=None, sanitized=sanitized,
    )

    # The sentinel is recorded as the JSON null the contract declares...
    assert record["filing"]["collection_scope"] is None
    # ...and BOTH conversions are named.  ``issuer.aliases`` used to sanitize
    # silently, so a NaN company name dropped the alias with nothing in the run
    # output to say which field went missing.
    assert sanitized == ["issuer.aliases", "filing.collection_scope"]
    # ...never as a fabricated 0/"" value.
    assert record["filing"]["collection_scope"] != 0
    # NaN is truthy, so the raw value used to publish the alias ["nan"].
    assert record["issuer"]["aliases"] == []
    # And the record now encodes canonically instead of aborting the night.
    assert canonical_manifest_bytes(record)
    assert record["manifest_id"] == manifest_id_for(record)

    schema = json.loads((
        Path(__file__).resolve().parents[1]
        / "contracts/capital_structure_source_manifest.schema.json"
    ).read_text())
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record)
    )
    assert not errors, [error.message for error in errors]


def test_legacy_discovery_ledger_migrates_to_a_json_representable_null(tmp_path):
    """``pd.isna`` was too weak an assertion — it is true for BOTH None and NaN.

    ``test_old_discovery_ledger_is_migrated_with_null_collection_scope`` asserted
    only ``pd.isna(...)``, so it passed while the migrated value was a NaN that no
    canonical writer could encode.  Assert JSON-representability instead.
    """
    legacy_columns = LEGACY_DISCOVERY_COLUMNS
    path = tmp_path / "discovery.parquet"
    pd.DataFrame([{
        "accession": "legacy", "cik": "0001234567", "ticker": "ACME",
        "company_name": "Acme Corp", "form": "S-3", "filing_date": "2026-08-01",
        "file_path": "edgar/data/1234567/legacy.txt",
        "canonical_url": "https://www.sec.gov/Archives/edgar/data/1234567/legacy.txt",
        "_first_seen": "2026-08-01T12:00:00Z",
    }])[legacy_columns].to_parquet(path, index=False)

    migrated = sec._read_table(path, sec._DISCOVERY_COLUMNS)
    row = migrated.to_dict("records")[0]

    assert row["collection_scope"] is None
    assert json.dumps(row["collection_scope"]) == "null"


def test_repeatedly_failing_filing_is_parked_and_leaves_the_retrieval_queue():
    """A filing may not be retried forever — the bound is what stops the creep."""
    attempts = pd.DataFrame([
        {"accession": "aaa", "state": "transient_error"},
        {"accession": "aaa", "state": "transient_error"},
        {"accession": "bbb", "state": "storage_deferred"},
    ])
    # Under the bound, neither has exhausted it yet.
    assert sec.parked_accessions(attempts) == set()

    attempts = pd.concat([attempts, pd.DataFrame([
        {"accession": "aaa", "state": "transient_error"},
    ])], ignore_index=True)
    assert sec.parked_accessions(attempts) == {"aaa"}

    # ``stored`` closes the item via ``have_complete``, so it never counts toward
    # the bound however many times it is recorded.
    retained = pd.DataFrame([
        {"accession": "ccc", "state": "stored"},
        {"accession": "ccc", "state": "stored"},
        {"accession": "ccc", "state": "stored"},
    ])
    assert sec.parked_accessions(retained) == set()

    discovery = pd.DataFrame([
        {
            "accession": accession, "cik": "1234567", "ticker": "ACME",
            "company_name": "Acme Corp", "form": "S-3", "filing_date": "2026-08-01",
            "file_path": "p", "canonical_url": "https://example.test/x.txt",
            "collection_scope": sec.DISCOVERY_SCOPE_REGISTRATION,
            "_first_seen": "2026-08-01T12:00:00Z",
        }
        for accession in ("aaa", "bbb")
    ])
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

    unbounded = select_retrieval_queue(
        discovery, have_complete=set(), max_filings=10, now=now,
    )
    assert set(unbounded["accession"]) == {"aaa", "bbb"}

    bounded = select_retrieval_queue(
        discovery, have_complete=set(), max_filings=10, now=now, parked={"aaa"},
    )
    assert set(bounded["accession"]) == {"bbb"}
    # The receipt must not keep counting a parked filing as pending work.
    assert bounded.attrs["retrieval_queue_receipt"]["selected_count"] == 1
    assert bounded.attrs["retrieval_queue_receipt"]["deferred_count"] == 0


def _parser_deferred_manifest(accession: str) -> dict:
    """A retained-but-parser-deferred complete submission, as the collector writes it."""
    return {
        "filing": {
            "accession": accession,
            "file_number_provenance": {"state": "unavailable", "observations": []},
        },
        "document": {"document_role": "complete_submission"},
        "parser": {"eligibility": "deferred", "corruption_state": "suspect"},
    }


def test_parser_deferred_filing_counts_toward_the_bound_because_it_never_closes():
    """Retained bytes are not a closed queue item, and the bound must see that.

    ``_eligible_complete_accessions`` admits only ``eligible``/``clean`` manifests,
    so a ``stored_parser_deferred`` filing is BY DEFINITION never in
    ``have_complete``: it re-enters the retrieval queue every night, forever.  The
    shipped rationale said its retained bytes closed the queue item and therefore
    excluded it from the bound — which reopened the exact unbounded backlog the
    bound exists to close, for the WORST class of filing (an SEC error page, a
    corrupt bundle, suspect bytes).  It was latent only because every committed
    manifest today is eligible/clean.
    """
    # The premise, asserted rather than assumed: retained bytes do NOT close it.
    assert sec._eligible_complete_accessions([_parser_deferred_manifest("ddd")]) == set()

    attempts = pd.DataFrame(
        [{"accession": "ddd", "state": "stored_parser_deferred"}]
        * sec.MAX_RETRIEVAL_ATTEMPTS
    )
    assert sec.parked_accessions(attempts) == {"ddd"}

    # One short of the bound is still retried — parking is the ceiling, not a rule
    # that suspect bytes get one look.
    assert sec.parked_accessions(attempts.head(sec.MAX_RETRIEVAL_ATTEMPTS - 1)) == set()

    # Mixed unclosed states share one counter: the queue item stayed open either way.
    mixed = pd.DataFrame([
        {"accession": "eee", "state": "transient_error"},
        {"accession": "eee", "state": "stored_parser_deferred"},
        {"accession": "eee", "state": "storage_deferred"},
    ])
    assert sec.parked_accessions(mixed) == {"eee"}

    # The control: ``stored`` closes the item via ``have_complete``, so it never
    # counts however many times it is recorded.
    stored = pd.DataFrame(
        [{"accession": "fff", "state": "stored"}] * (sec.MAX_RETRIEVAL_ATTEMPTS + 2)
    )
    assert sec.parked_accessions(stored) == set()

    # And a parked parser-deferred filing actually leaves the queue.
    discovery = pd.DataFrame([{
        "accession": "ddd", "cik": "1234567", "ticker": "ACME",
        "company_name": "Acme Corp", "form": "S-3", "filing_date": "2026-08-01",
        "file_path": "p", "canonical_url": "https://example.test/x.txt",
        "collection_scope": sec.DISCOVERY_SCOPE_REGISTRATION,
        "_first_seen": "2026-08-01T12:00:00Z",
    }])
    bounded = select_retrieval_queue(
        discovery,
        have_complete=sec._eligible_complete_accessions([_parser_deferred_manifest("ddd")]),
        max_filings=10,
        now=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        parked=sec.parked_accessions(attempts),
    )
    assert bounded.empty


def test_attempt_bound_env_override_is_the_real_unpark_lever(monkeypatch):
    """``CS_MAX_RETRIEVAL_ATTEMPTS`` exists, and is read at the point of use.

    The shipped prose promised "a later ``--rebuild`` or a raised bound" would pick
    a parked filing back up.  There is no ``--rebuild`` flag on this collector and
    the bound was a frozen literal, so the documented lever did not exist at all —
    an operator following the docstring had nothing to pull.
    """
    attempts = pd.DataFrame(
        [{"accession": "ggg", "state": "transient_error"}] * sec.MAX_RETRIEVAL_ATTEMPTS
    )
    monkeypatch.delenv(sec.MAX_RETRIEVAL_ATTEMPTS_ENV, raising=False)
    assert sec._max_retrieval_attempts() == sec.MAX_RETRIEVAL_ATTEMPTS
    assert sec.parked_accessions(attempts) == {"ggg"}

    # The lever: raising the bound picks the parked filing straight back up, with
    # no edit, no deploy, and nothing to rebuild.
    monkeypatch.setenv(sec.MAX_RETRIEVAL_ATTEMPTS_ENV, "10")
    assert sec._max_retrieval_attempts() == 10
    assert sec.parked_accessions(attempts) == set()

    # Garbage, zero, and negative fall back to the default WITHOUT raising: a typo
    # in a workflow variable may neither abort the night nor uncap the backlog.
    for raw in ("", "   ", "three", "0", "-1", "2.5", "10x"):
        monkeypatch.setenv(sec.MAX_RETRIEVAL_ATTEMPTS_ENV, raw)
        assert sec._max_retrieval_attempts() == sec.MAX_RETRIEVAL_ATTEMPTS
        assert sec.parked_accessions(attempts) == {"ggg"}


class SeededDiscoveryAdapter(SecCapitalStructureAdapter):
    """Retrieval-only run: the queue comes from a pre-existing discovery ledger."""

    def _fetch_index(self, value, ua):
        raise AssertionError("seeded-discovery run must not fetch a daily index")

    def _fetch_submission(self, url, ua):
        return SUBMISSION


def test_legacy_null_scope_survives_the_retrieval_loop_unlaundered(
    tmp_path, monkeypatch, capsys
):
    """The retrieval loop must hand the manifest writer ``None``, not a NaN.

    A discovery row written before Wave 2C added ``collection_scope`` carries a
    legitimate ``None``.  ``iterrows()`` builds a per-row Series and that build
    substitutes ``float('nan')``; ``to_dict("records")`` does not.  Both shapes now
    produce a schema-valid manifest — ``_manifest_scalar`` nulls the sentinel — so
    the only thing that still separates them is the DISCLOSURE: under ``iterrows``
    the collector reports a sanitized field for a value that was never a sentinel,
    which is precisely the conflation ``_manifest_scalar`` documents as forbidden
    ("sanitized" must never mean "legitimately absent").  Asserting the annotation's
    ABSENCE is therefore the fence on the ``to_dict("records")`` hunk; reverting
    that hunk turns this test red.
    """
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    # No index is due: this run is the retrieval half of the night, nothing else.
    monkeypatch.setattr(sec, "due_index_dates", lambda *args, **kwargs: [])

    root = tmp_path / "capital_structure"
    root.mkdir(parents=True)
    # Seeded exactly as the legacy ledger is on disk — the column simply is not
    # there — so ``_read_table`` performs the real production migration to ``None``.
    legacy_columns = LEGACY_DISCOVERY_COLUMNS
    pd.DataFrame([{
        "accession": "0001234567-26-000001",
        "cik": "0001234567",
        "ticker": "ACME",
        "company_name": "ACME CORP",
        "form": "S-3",
        "filing_date": "2026-08-01",
        "file_path": "edgar/data/1234567/0001234567-26-000001.txt",
        "canonical_url": (
            "https://www.sec.gov/Archives/edgar/data/1234567/"
            "0001234567-26-000001.txt"
        ),
        "_first_seen": "2026-08-01T12:00:00Z",
    }])[legacy_columns].to_parquet(root / "discovery.parquet", index=False)

    store = ContentAddressedSourceStore(LocalStore(tmp_path / "objects"), backend="local")
    adapter = SeededDiscoveryAdapter(
        source_store=store,
        now_fn=lambda: datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=10,
    )

    heartbeat = adapter.fetch()["sec_evidence__ingest"]
    captured = capsys.readouterr().out

    # The filing really was retrieved through the loop under test.
    assert int(heartbeat.iloc[0]["retrieved"]) == 1
    manifests = read_source_ledger(source_ledger_path(root))
    assert manifests
    for record in manifests:
        assert record["filing"]["collection_scope"] is None
        assert json.dumps(record["filing"]["collection_scope"]) == "null"
    # The alias survives, so nothing else in this row was a sentinel either.
    assert manifests[0]["issuer"]["aliases"] == ["ACME CORP"]

    # THE FENCE.  A legitimately-absent scope was never converted, so the collector
    # must report no sanitized field at all.  Under ``iterrows()`` the same row
    # arrives as NaN, ``_manifest_scalar`` converts it, and this annotation fires
    # for every manifest in the bundle.
    assert "capital-structure-manifest-null-fields" not in captured
    assert "filing.collection_scope" not in captured
