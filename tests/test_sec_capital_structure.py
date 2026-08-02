from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pandas as pd
import pytest
import requests

import collectors.sec_capital_structure as sec
from collectors.sec_capital_structure import (
    DocumentInspection,
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
    manifest_id_for,
)


INDEX = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
S-3                                  ACME CORP                                 1234567     20260801    edgar/data/1234567/0001234567-26-000001.txt
EFFECT                               ACME CORP                                 1234567     20260802    edgar/data/1234567/9999999995-26-002222.txt
424B5                                MEDTECH LTD                               1111111     20260803    edgar/data/1111111/0001111111-26-000003.txt
1-A POS                              REG A CO                                  2222222     20260804    edgar/data/2222222/0002222222-26-000004.txt
8-K                                  BROAD EVENT CO                            3333333     20260805    edgar/data/3333333/0003333333-26-000005.txt
"""

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
8-K                                  ANCHORED CO                               1234567     20260802    edgar/data/1234567/0001234567-26-000010.txt
"""

REGISTRATION_ONLY_INDEX = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
S-3                                  ANCHORED CO                               1234567     20260801    edgar/data/1234567/0001234567-26-000011.txt
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
    assert sec.MAX_FILINGS_PER_RUN >= 200


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
    manifests = pd.DataFrame([
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
    ])

    assert sec._eligible_complete_accessions(manifests) == {"clean"}


def test_legacy_complete_manifest_gets_one_bounded_provenance_backfill():
    discovery = pd.DataFrame([{
        "accession": "legacy", "cik": "0001234567", "form": "S-3",
        "filing_date": "2026-08-01", "collection_scope": None,
        "_first_seen": "2026-08-01T11:00:00Z",
    }])
    legacy = pd.DataFrame([{
        "filing": {"accession": "legacy", "file_number": "333-123456"},
        "document": {"document_role": "complete_submission"},
        "parser": {"eligibility": "eligible", "corruption_state": "clean"},
    }])
    hardened = pd.concat([legacy, pd.DataFrame([{
        "filing": {
            "accession": "legacy", "file_number": None,
            "file_number_provenance": {
                "state": "unavailable", "value": None,
                "candidate_values": [], "sources": [],
            },
        },
        "document": {"document_role": "complete_submission"},
        "parser": {"eligibility": "eligible", "corruption_state": "clean"},
    }])], ignore_index=True)
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
    pd.DataFrame([row])[sec._DISCOVERY_COLUMNS].to_parquet(
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
        return INDEX

    def _fetch_submission(self, url, ua):
        return SUBMISSION


class CrossIndexScopeAdapter(SecCapitalStructureAdapter):
    def _fetch_index(self, value, ua):
        return {
            date(2026, 8, 2): RECONCILIATION_ONLY_INDEX,
            date(2026, 8, 1): REGISTRATION_ONLY_INDEX,
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
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 1)]
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
    monkeypatch.setattr(sec, "_data_dir", lambda: tmp_path / "capital_structure")
    monkeypatch.setattr(sec, "_cik_map", lambda: {1234567: "ACME"})
    monkeypatch.setattr(sec, "_ua", lambda: "test@example.com")
    monkeypatch.setattr(sec, "PACE_SECONDS", 0)
    monkeypatch.setattr(sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 1)])
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
    manifests = pd.read_parquet(root / "source_manifest.parquet")
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    queue_receipt = json.loads((root / "retrieval_queue_receipt.json").read_text())
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
    assert set(attempts["retrieval_lane"]) == {
        "registration", "state", "prospectus", "reg_a"
    }
    assert queue_receipt["selected_count"] == 4
    assert queue_receipt["deferred_count"] == 0
    assert [row["lane"] for row in queue_receipt["lanes"]] == list(
        sec.RETRIEVAL_LANE_ORDER
    )
    assert int(heartbeat.iloc[0]["retrieved"]) == 4

    rerun = adapter.fetch()["sec_evidence__ingest"]
    assert len(pd.read_parquet(root / "source_manifest.parquet")) == len(manifests)
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
        lambda *args, **kwargs: [date(2026, 8, 2), date(2026, 8, 1)],
    )
    adapter = CrossIndexScopeAdapter(
        source_store=object(),
        now_fn=lambda: datetime(2026, 8, 2, 13, 0, tzinfo=timezone.utc),
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
    legacy_columns = [
        column for column in sec._DISCOVERY_COLUMNS if column != "collection_scope"
    ]
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
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 1)]
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
    path = tmp_path / "capital_structure" / "source_manifest.parquet"
    manifests = pd.read_parquet(path)
    manifests.at[0, "rights"] = {
        **manifests.at[0, "rights"],
        "license_note": "tampered after identity assignment",
    }
    manifests.to_parquet(path, index=False)

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
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 1)]
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
    manifests = pd.read_parquet(root / "source_manifest.parquet")
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
    monkeypatch.setattr(sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 1)])
    adapter = OneDayAdapter(
        source_store=FailingSourceStore(),
        now_fn=lambda: datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc),
        max_filings_per_run=1,
    )

    adapter.fetch()

    root = tmp_path / "capital_structure"
    manifests = pd.read_parquet(root / "source_manifest.parquet")
    attempts = pd.read_parquet(root / "retrieval_attempts.parquet")
    assert manifests.empty
    assert attempts.iloc[0]["state"] == "storage_deferred"
    assert "verification failed" in attempts.iloc[0]["error"]


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
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 1)]
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
    manifests = pd.read_parquet(root / "source_manifest.parquet")
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
        return SINGLE_INDEX

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
        sec, "due_index_dates", lambda *args, **kwargs: [date(2026, 8, 1)]
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
    manifests = pd.read_parquet(root / "source_manifest.parquet")
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
