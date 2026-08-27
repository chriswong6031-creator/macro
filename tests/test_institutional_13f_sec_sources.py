from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from engine.institutional_census.sec_sources import (
    ATOM_EPHEMERAL_ENTRY_LIMIT,
    ATOM_FETCH_ATTEMPTS,
    ATOM_HONORED_PAGE_SIZES,
    ATOM_MAX_FETCH_ATTEMPTS,
    COVER_PAGE_COLUMNS,
    HOLDING_COLUMNS,
    INCLUDED_MANAGER_COLUMNS,
    REPORTED_BY_COLUMNS,
    SUBMISSION_COLUMNS,
    SUMMARY_PAGE_COLUMNS,
    FilingDiscovery,
    SecSourceError,
    SecSourceUnavailableError,
    iter_bulk_holding_chunks,
    parse_filing_index,
    parse_filing_package,
    parse_latest_filings_atom,
    parse_master_index,
    read_bulk_package,
    read_filing_package,
    scan_latest_filings_atom,
    validate_bulk_invariants,
)


FIXTURES = Path(__file__).parent / "fixtures" / "institutional_13f"
ACCESSION = "0001398344-26-013841"
INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/1792167/000139834426013841/"
    "0001398344-26-013841-index.htm"
)


BULK_HEADERS = {
    "SUBMISSION.tsv": [
        "ACCESSION_NUMBER",
        "FILING_DATE",
        "SUBMISSIONTYPE",
        "CIK",
        "PERIODOFREPORT",
    ],
    "COVERPAGE.tsv": [
        "ACCESSION_NUMBER",
        "REPORTCALENDARORQUARTER",
        "ISAMENDMENT",
        "AMENDMENTNO",
        "AMENDMENTTYPE",
        "CONFDENIEDEXPIRED",
        "DATEDENIEDEXPIRED",
        "DATEREPORTED",
        "REASONFORNONCONFIDENTIALITY",
        "FILINGMANAGER_NAME",
        "FILINGMANAGER_STREET1",
        "FILINGMANAGER_STREET2",
        "FILINGMANAGER_CITY",
        "FILINGMANAGER_STATEORCOUNTRY",
        "FILINGMANAGER_ZIPCODE",
        "REPORTTYPE",
        "FORM13FFILENUMBER",
        "CRDNUMBER",
        "SECFILENUMBER",
        "PROVIDEINFOFORINSTRUCTION5",
        "ADDITIONALINFORMATION",
    ],
    "SUMMARYPAGE.tsv": [
        "ACCESSION_NUMBER",
        "OTHERINCLUDEDMANAGERSCOUNT",
        "TABLEENTRYTOTAL",
        "TABLEVALUETOTAL",
        "ISCONFIDENTIALOMITTED",
    ],
    "INFOTABLE.tsv": [
        "ACCESSION_NUMBER",
        "INFOTABLE_SK",
        "NAMEOFISSUER",
        "TITLEOFCLASS",
        "CUSIP",
        "FIGI",
        "VALUE",
        "SSHPRNAMT",
        "SSHPRNAMTTYPE",
        "PUTCALL",
        "INVESTMENTDISCRETION",
        "OTHERMANAGER",
        "VOTING_AUTH_SOLE",
        "VOTING_AUTH_SHARED",
        "VOTING_AUTH_NONE",
    ],
    "OTHERMANAGER.tsv": [
        "ACCESSION_NUMBER",
        "OTHERMANAGER_SK",
        "CIK",
        "FORM13FFILENUMBER",
        "CRDNUMBER",
        "SECFILENUMBER",
        "NAME",
    ],
    "OTHERMANAGER2.tsv": [
        "ACCESSION_NUMBER",
        "SEQUENCENUMBER",
        "CIK",
        "FORM13FFILENUMBER",
        "CRDNUMBER",
        "SECFILENUMBER",
        "NAME",
    ],
    "SIGNATURE.tsv": [
        "ACCESSION_NUMBER",
        "NAME",
        "TITLE",
        "PHONE",
        "SIGNATURE",
        "CITY",
        "STATEORCOUNTRY",
        "SIGNATUREDATE",
    ],
}


def _bulk_zip() -> bytes:
    hr = "0001214659-26-001839"
    hra = "0001214659-26-001840"
    nt = "0001000490-26-000003"
    nta = "0000278331-26-000010"
    records = {
        "SUBMISSION.tsv": [
            {
                "ACCESSION_NUMBER": hr,
                "FILING_DATE": "17-FEB-2026",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "1738902",
                "PERIODOFREPORT": "31-DEC-2025",
            },
            {
                "ACCESSION_NUMBER": hra.replace("-", ""),
                "FILING_DATE": "20260218",
                "SUBMISSIONTYPE": "13F-HR/A",
                "CIK": "1738902",
                "PERIODOFREPORT": "2025-12-31",
            },
            {
                "ACCESSION_NUMBER": nt,
                "FILING_DATE": "07-AUG-2026",
                "SUBMISSIONTYPE": "13F-NT",
                "CIK": "1000490",
                "PERIODOFREPORT": "30-JUN-2026",
            },
            {
                "ACCESSION_NUMBER": nta,
                "FILING_DATE": "31-MAR-2026",
                "SUBMISSIONTYPE": "13F-NT/A",
                "CIK": "278331",
                "PERIODOFREPORT": "30-SEP-2025",
            },
        ],
        "COVERPAGE.tsv": [
            {
                "ACCESSION_NUMBER": hr,
                "REPORTCALENDARORQUARTER": "31-DEC-2025",
                "ISAMENDMENT": "false",
                "FILINGMANAGER_NAME": "Fixture Holdings LLC",
                "FILINGMANAGER_CITY": "New York",
                "FILINGMANAGER_STATEORCOUNTRY": "NY",
                "FILINGMANAGER_ZIPCODE": "10001",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "028-00001",
                "PROVIDEINFOFORINSTRUCTION5": "N",
            },
            {
                "ACCESSION_NUMBER": hra,
                "REPORTCALENDARORQUARTER": "31-DEC-2025",
                "ISAMENDMENT": "true",
                "AMENDMENTNO": "1",
                "AMENDMENTTYPE": "RESTATEMENT",
                "FILINGMANAGER_NAME": "Fixture Holdings LLC",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "028-00001",
                "PROVIDEINFOFORINSTRUCTION5": "Y",
            },
            {
                "ACCESSION_NUMBER": nt,
                "REPORTCALENDARORQUARTER": "30-JUN-2026",
                "ISAMENDMENT": "N",
                "FILINGMANAGER_NAME": "Fixture Notice LLC",
                "REPORTTYPE": "13F NOTICE",
                "FORM13FFILENUMBER": "028-00002",
                "PROVIDEINFOFORINSTRUCTION5": "N",
            },
            {
                "ACCESSION_NUMBER": nta,
                "REPORTCALENDARORQUARTER": "30-SEP-2025",
                "ISAMENDMENT": "Y",
                "AMENDMENTNO": "2",
                "FILINGMANAGER_NAME": "Fixture Notice Two LLC",
                "REPORTTYPE": "13F NOTICE",
                "FORM13FFILENUMBER": "028-00003",
                "PROVIDEINFOFORINSTRUCTION5": "N",
            },
        ],
        "SUMMARYPAGE.tsv": [
            {
                "ACCESSION_NUMBER": hr,
                "OTHERINCLUDEDMANAGERSCOUNT": "2",
                "TABLEENTRYTOTAL": "2",
                "TABLEVALUETOTAL": "300",
                "ISCONFIDENTIALOMITTED": "false",
            },
            {
                "ACCESSION_NUMBER": hra,
                "OTHERINCLUDEDMANAGERSCOUNT": "0",
                "TABLEENTRYTOTAL": "1",
                "TABLEVALUETOTAL": "50",
                "ISCONFIDENTIALOMITTED": "false",
            },
        ],
        "INFOTABLE.tsv": [
            {
                "ACCESSION_NUMBER": hr,
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "Alpha Corp",
                "TITLEOFCLASS": "COM",
                "CUSIP": "000000AA1",
                "FIGI": "bbg000alpha",
                "VALUE": "100",
                "SSHPRNAMT": "10",
                "SSHPRNAMTTYPE": "sh",
                "PUTCALL": "Call",
                "INVESTMENTDISCRETION": "DFND",
                "OTHERMANAGER": "1, 01",
                "VOTING_AUTH_SOLE": "4",
                "VOTING_AUTH_SHARED": "3",
                "VOTING_AUTH_NONE": "3",
            },
            {
                "ACCESSION_NUMBER": hr,
                "INFOTABLE_SK": "2",
                "NAMEOFISSUER": "Beta Corp",
                "TITLEOFCLASS": "COM",
                "CUSIP": "000000BB2",
                "VALUE": "200",
                "SSHPRNAMT": "20",
                "SSHPRNAMTTYPE": "SH",
                "INVESTMENTDISCRETION": "SOLE",
                "VOTING_AUTH_SOLE": "20",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
            {
                "ACCESSION_NUMBER": hra,
                "INFOTABLE_SK": "3",
                "NAMEOFISSUER": "Gamma Corp",
                "TITLEOFCLASS": "COM",
                "CUSIP": "000000CC3",
                "VALUE": "50",
                "SSHPRNAMT": "5",
                "SSHPRNAMTTYPE": "SH",
                "INVESTMENTDISCRETION": "SOLE",
                "VOTING_AUTH_SOLE": "5",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
        ],
        "OTHERMANAGER.tsv": [
            {
                "ACCESSION_NUMBER": nt,
                "OTHERMANAGER_SK": "1",
                "CIK": "1527166",
                "FORM13FFILENUMBER": "028-15025",
                "CRDNUMBER": "111128",
                "SECFILENUMBER": "801-52462",
                "NAME": "Carlyle Group Inc.",
            }
        ],
        "OTHERMANAGER2.tsv": [
            {
                "ACCESSION_NUMBER": hr,
                "SEQUENCENUMBER": "1",
                "CIK": "1327354",
                "FORM13FFILENUMBER": "028-11406",
                "NAME": "Included Manager One",
            },
            {
                "ACCESSION_NUMBER": hr,
                "SEQUENCENUMBER": "1",
                "NAME": "Included Manager One for another account",
            },
        ],
        "SIGNATURE.tsv": [
            {
                "ACCESSION_NUMBER": accession,
                "NAME": "Fixture Signer",
                "TITLE": "CCO",
                "SIGNATURE": "/s/ Fixture Signer",
                "CITY": "New York",
                "STATEORCOUNTRY": "NY",
                "SIGNATUREDATE": "17-FEB-2026",
            }
            for accession in (hr, hra, nt, nta)
        ],
    }
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, headers in BULK_HEADERS.items():
            rows = records[name]
            text = "\t".join(headers) + "\n"
            text += "".join(
                "\t".join(str(row.get(header, "")) for header in headers) + "\n"
                for row in rows
            )
            archive.writestr(name, text)
        archive.writestr("FORM13F_metadata.json", "{}")
        archive.writestr("FORM13F_readme.htm", "<html>fixture</html>")
    return output.getvalue()


def test_read_bulk_package_contract_and_streaming(tmp_path: Path) -> None:
    payload = _bulk_zip()
    source = tmp_path / "form13f.zip"
    source.write_bytes(payload)
    tables = read_bulk_package(source)

    assert tables.source_sha256 == sha256(payload).hexdigest()
    assert tables.source_bytes == len(payload)
    assert list(tables.submissions.columns) == SUBMISSION_COLUMNS
    assert list(tables.cover_pages.columns) == COVER_PAGE_COLUMNS
    assert list(tables.summary_pages.columns) == SUMMARY_PAGE_COLUMNS
    assert list(tables.holdings.columns) == HOLDING_COLUMNS
    assert list(tables.reported_by.columns) == REPORTED_BY_COLUMNS
    assert list(tables.included_managers.columns) == INCLUDED_MANAGER_COLUMNS
    assert set(tables.submissions["form"]) == {
        "13F-HR",
        "13F-HR/A",
        "13F-NT",
        "13F-NT/A",
    }
    assert tables.submissions.iloc[0].to_dict() == {
        "accession": "0001214659-26-001839",
        "filing_date": "2026-02-17",
        "form": "13F-HR",
        "cik": "0001738902",
        "period_end": "2025-12-31",
        "accepted_at": None,
    }
    assert str(tables.holdings["value"].dtype) == "Int64"
    assert str(tables.cover_pages["is_amendment"].dtype) == "boolean"
    assert tables.holdings["source_ordinal"].tolist() == [1, 2, 3]
    assert tables.holdings.iloc[0]["figi"] == "BBG000ALPHA"
    assert tables.holdings.iloc[0]["other_manager"] == "1, 01"

    assert tables.reported_by.iloc[0]["filer_cik"] == "0001000490"
    assert tables.reported_by.iloc[0]["reporting_manager_cik"] == "0001527166"
    assert (
        tables.reported_by.iloc[0]["relation_type"]
        == "filer_holdings_reported_by_manager"
    )
    assert tables.included_managers["sequence_number"].tolist() == [1, 1]
    assert tables.included_managers["source_ordinal"].tolist() == [1, 2]
    assert set(tables.included_managers["relation_type"]) == {
        "manager_included_in_filing"
    }

    joined = tables.joined_holdings()
    assert list(joined.columns) == [
        *HOLDING_COLUMNS,
        "cik",
        "period_end",
        "filing_date",
        "form",
        "accepted_at",
    ]
    assert joined.iloc[2]["cik"] == "0001738902"
    chunks = list(iter_bulk_holding_chunks(payload, chunk_size=2))
    assert [len(chunk) for chunk in chunks] == [2, 1]
    assert pd.concat(chunks)["source_ordinal"].tolist() == [1, 2, 3]

    findings = validate_bulk_invariants(tables)
    assert [finding.code for finding in findings] == [
        "duplicate_included_manager_sequence"
    ]


def test_bulk_package_rejects_member_drift() -> None:
    payload = _bulk_zip()
    output = BytesIO()
    with ZipFile(BytesIO(payload)) as source, ZipFile(output, "w") as target:
        for item in source.infolist():
            if item.filename != "FORM13F_readme.htm":
                target.writestr(item, source.read(item.filename))
    with pytest.raises(SecSourceError, match="member mismatch"):
        read_bulk_package(output.getvalue())


def test_official_one_unit_summary_discrepancy_is_a_warning() -> None:
    tables = read_bulk_package(_bulk_zip())
    holdings = tables.holdings.copy()
    summary_pages = tables.summary_pages.copy()
    accession = "0001214659-26-001839"
    holding_rows = holdings.index[holdings["accession"] == accession]
    holdings.loc[holding_rows[0], "value"] = 3_006_335_524
    holdings.loc[holding_rows[1], "value"] = 0
    summary_pages.loc[
        summary_pages["accession"] == accession, "table_value_total"
    ] = 3_006_335_523
    findings = validate_bulk_invariants(
        replace(tables, holdings=holdings, summary_pages=summary_pages)
    )
    finding = next(
        item
        for item in findings
        if item.code == "table_value_total_mismatch" and item.accession == accession
    )
    assert finding.severity == "warning"
    assert finding.detail == "summary=3006335523, rows=3006335524"


def test_atom_uses_filer_cik_not_accession_prefix() -> None:
    payload = (FIXTURES / "latest_filings.atom").read_bytes()
    entries = parse_latest_filings_atom(payload)
    assert len(entries) == 2
    assert entries[0] == FilingDiscovery(
        accession=ACCESSION,
        cik="0001792167",
        form="13F-HR",
        filing_date="2026-08-07",
        accepted_at="2026-08-07T17:25:16-04:00",
        index_url=INDEX_URL,
        company_name="Meeder Advisory Services, Inc.",
        source_ordinal=1,
    )
    assert entries[1].form == "13F-NT"
    assert entries[1].cik == "0001555793"

    mismatch = payload.replace(b"/data/1792167/", b"/data/1234567/", 1)
    with pytest.raises(SecSourceError, match="CIK mismatch"):
        parse_latest_filings_atom(mismatch)


def test_atom_unicode_string_ignores_stale_byte_encoding_declaration() -> None:
    source = (FIXTURES / "latest_filings.atom").read_text()
    source = source.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"')
    source = source.replace(
        "Meeder Advisory Services, Inc.", "Société de Gestion", 1
    )
    assert parse_latest_filings_atom(source)[0].company_name == "Société de Gestion"


def _atom_page(start: int, count: int, *, forms: dict[int, str] | None = None) -> bytes:
    """Render ``count`` RAW entries; ``forms`` overrides the form of an offset."""

    forms = forms or {}
    rows = []
    for offset, sequence in enumerate(range(start + 1, start + count + 1)):
        accession = f"0000000001-26-{sequence:06d}"
        compact = accession.replace("-", "")
        form = forms.get(offset, "13F-HR")
        # Only the 13F forms the parser keeps carry a parseable title; EDGAR's
        # other 13F-family titles are shaped differently and must be skipped on
        # the category term alone.
        title = (
            f"{form} - Page Fixture ({2:010d}) (Filer)"
            if form in {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}
            else f"{form} - Page Fixture"
        )
        rows.append(
            f"""
            <entry>
              <title>{title}</title>
              <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/2/{compact}/{accession}-index.htm"/>
              <summary type="html">Filed: 2026-08-07 AccNo: {accession}</summary>
              <updated>2026-08-07T17:00:00-04:00</updated>
              <category term="{form}"/><id>{accession}</id>
            </entry>"""
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        + "".join(rows)
        + "</feed>"
    ).encode()


def _edgar_honored(count: int) -> int:
    """Round ``count`` down the way the live browse-edgar surface does."""

    return next(
        (size for size in reversed(ATOM_HONORED_PAGE_SIZES) if size <= count),
        ATOM_HONORED_PAGE_SIZES[0],
    )


def _deep_feed(
    calls: list[tuple[int, int]],
    *,
    total: int | None = None,
    forms: dict[int, str] | None = None,
):
    """A fake browse-edgar that rounds ``count`` down exactly like the real one.

    ``total`` bounds the feed (``None`` means bottomless); ``forms`` overrides the
    form of a raw offset on the first page.
    """

    def fetch(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        start = int(query["start"][0])
        count = int(query["count"][0])
        calls.append((start, count))
        served = _edgar_honored(count)
        if total is not None:
            served = max(0, min(served, total - start))
        return _atom_page(start, served, forms=forms if start == 0 else None)

    return fetch


def test_atom_scanner_has_explicit_ephemeral_boundary() -> None:
    calls: list[tuple[int, int]] = []
    result = scan_latest_filings_atom(_deep_feed(calls))
    assert len(result.entries) == ATOM_EPHEMERAL_ENTRY_LIMIT == 930
    assert not result.complete
    assert result.stop_reason == "ephemeral_limit"
    # The 930 boundary is not a multiple of the 100-entry page, so the tail is
    # paged at sizes EDGAR actually serves rather than in one unhonored ask.
    assert calls[-1] == (920, 10)
    assert result.pages_fetched == len(calls) == 11
    with pytest.raises(ValueError, match="entry_limit"):
        scan_latest_filings_atom(_deep_feed([]), entry_limit=931)


def test_atom_scanner_only_requests_page_sizes_edgar_honors() -> None:
    """EDGAR rounds an unhonored ``count`` DOWN, which reads as a short page.

    Measured against the live feed 2026-08-17: ``count=50`` serves 40 entries and
    ``count=30`` serves 20.  Production runs ``--max-accessions 750``, so the tail
    page used to ask for 50, receive 40, and call the truncated scan complete.
    """

    calls: list[tuple[int, int]] = []
    result = scan_latest_filings_atom(_deep_feed(calls), entry_limit=750)
    assert [count for _start, count in calls if count not in ATOM_HONORED_PAGE_SIZES] == []
    assert not result.complete
    assert result.stop_reason == "ephemeral_limit"
    assert len(result.entries) == 750
    assert calls[-1] == (740, 10)


def test_atom_scanner_form_filter_never_shortens_a_page() -> None:
    """A full page carrying a non-``FORM_TYPES`` 13F form is not a short page.

    ``type=13F`` prefix-matches on EDGAR (verified 2026-08-17: ``type=13F-H``
    returns both ``13F-HR`` and ``13F-HR/A``), so the feed can serve 13F-family
    forms outside ``FORM_TYPES`` — ``13FCONP`` is a live example.  Deciding the
    page length after the filter ended the scan and still reported it complete.
    """

    calls: list[tuple[int, int]] = []
    result = scan_latest_filings_atom(
        _deep_feed(calls, forms={5: "13FCONP"}), entry_limit=200
    )
    assert not result.complete, "a filtered entry must not end the scan as complete"
    assert result.stop_reason == "ephemeral_limit"
    assert result.pages_fetched == 2
    # 200 raw entries walked, minus the single 13FCONP the filter drops.
    assert len(result.entries) == 199
    assert {entry.form for entry in result.entries} == {"13F-HR"}


def test_atom_scanner_filtered_entry_does_not_shift_later_ordinals() -> None:
    calls: list[tuple[int, int]] = []
    result = scan_latest_filings_atom(
        _deep_feed(calls, total=100, forms={5: "13FCONP"}), entry_limit=200
    )
    assert result.complete
    assert result.stop_reason == "short_page"
    ordinals = [entry.source_ordinal for entry in result.entries]
    # Raw feed positions 1..100 with position 6 (offset 5) dropped by the filter.
    assert ordinals == [value for value in range(1, 101) if value != 6]


def test_atom_scanner_all_filtered_full_page_is_not_a_stall() -> None:
    """A page with no 13F entries had nothing that *could* have been new."""

    calls: list[tuple[int, int]] = []
    forms = {offset: "13FCONP" for offset in range(100)}
    result = scan_latest_filings_atom(
        _deep_feed(calls, total=200, forms=forms), entry_limit=200
    )
    assert result.stop_reason != "stalled"
    assert result.pages_fetched == 2
    assert len(result.entries) == 100


def test_atom_scanner_short_page_is_complete() -> None:
    payload = (FIXTURES / "latest_filings.atom").read_bytes()
    result = scan_latest_filings_atom(lambda _url: payload)
    assert result.complete
    assert result.stop_reason == "short_page"
    assert result.pages_fetched == 1


# SEC answers a brief outage with this, carrying an HTTP 200, so the document
# type is the only thing separating "SEC is unwell" from "the feed is broken".
UNAVAILABLE_HTML = (
    b"<!DOCTYPE html>\n<html lang=\"en\"><head>"
    b"<title>SEC.gov | File Unavailable</title></head>"
    b"<body><h1>File Unavailable</h1></body></html>"
)


def _atom_fetcher(
    unavailable_at: int, *, times: int | None = None
) -> tuple[object, list[int]]:
    """Serve normal pages, but fail the page at ``unavailable_at``.

    ``times=None`` fails that page forever; an int fails only the first N
    attempts so the retry can be observed recovering.
    """

    calls: list[int] = []

    def fetch(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        start = int(query["start"][0])
        count = int(query["count"][0])
        calls.append(start)
        if start == unavailable_at and (
            times is None or calls.count(start) <= times
        ):
            return UNAVAILABLE_HTML
        return _atom_page(start, count)

    return fetch, calls


def test_atom_scanner_matches_the_live_production_page_ladder() -> None:
    """Anchor the happy path to what the real feed served on 2026-08-17.

    Observed against live EDGAR at 04:07Z with the production entry_limit of
    750, when the feed was genuinely deeper than that: 9 pages, no unhonored
    page size, and the tail walked 700->740->750 rather than stopping short.
    A change that alters this ladder has changed what production discovers.
    """

    calls: list[tuple[int, int]] = []

    def fetch(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        start = int(query["start"][0])
        count = int(query["count"][0])
        calls.append((start, count))
        return _atom_page(start, count)

    result = scan_latest_filings_atom(fetch, entry_limit=750)

    assert calls == [
        (0, 100),
        (100, 100),
        (200, 100),
        (300, 100),
        (400, 100),
        (500, 100),
        (600, 100),
        (700, 40),
        (740, 10),
    ]
    assert [count for _start, count in calls if count not in ATOM_HONORED_PAGE_SIZES] == []
    assert result.pages_fetched == 9
    assert len(result.entries) == 750
    assert [entry.source_ordinal for entry in result.entries] == list(range(1, 751))
    assert not result.complete
    assert result.stop_reason == "ephemeral_limit"
    assert result.fetch_retries == 0


def test_atom_scanner_advances_by_served_not_by_requested() -> None:
    """The cursor must follow what EDGAR SERVED, against a hypothetical over-server.

    Under-serving is caught by the ``raw_entries < count`` check.  Over-serving
    is caught only here, and the two directions together are what make the pager
    total over EDGAR's behaviour rather than correct for the one shape measured
    on 2026-08-17.  This matters because "EDGAR never serves more than asked" is
    an EMPIRICAL claim about a surface that already surprised us once: the bug
    #5854 fixed came from assuming EDGAR honours ``count``, and it rounds down.

    Measured against the shipped code with an EDGAR that ignores ``count`` and
    always serves 100.  With ``start += count`` instead, the cursor lags what
    was consumed, so the scan re-fetches an overlapping window and runs an extra
    page.

    Read the 800 below as relative advance behaviour, NOT as boundary respect.
    ``entry_limit`` is enforced on ``start``, which only bounds the entry count
    while EDGAR serves what it was asked for; under a hypothetical over-server
    NEITHER variant holds the 750 line (shipped overshoots to 800, the lagging
    cursor to 840).  The claim under test is that the shipped cursor tracks what
    was served and therefore overshoots less, not that the boundary survives an
    EDGAR that breaks its own count contract.
    """

    def over_serving(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        return _atom_page(int(query["start"][0]), 100)

    result = scan_latest_filings_atom(over_serving, entry_limit=750)

    # 8 pages of 100 reach the 750 boundary; a cursor advancing by the REQUESTED
    # count would lag and spend a 9th page re-reading entries it already had.
    assert result.pages_fetched == 8
    assert len(result.entries) == 800
    assert [entry.source_ordinal for entry in result.entries] == list(range(1, 801))
    assert not result.complete
    assert result.stop_reason == "ephemeral_limit"


def test_atom_html_error_page_is_not_a_broken_contract() -> None:
    """A transient outage page and a malformed feed must not be one error."""

    with pytest.raises(SecSourceUnavailableError):
        parse_latest_filings_atom(UNAVAILABLE_HTML)
    # Malformed Atom stays a contract violation, so it can never be retried as
    # though SEC were merely unwell.
    with pytest.raises(SecSourceError) as caught:
        parse_latest_filings_atom(
            b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        )
    assert not isinstance(caught.value, SecSourceUnavailableError)


def test_atom_scanner_retries_a_transient_page_and_keeps_scanning() -> None:
    fetch, calls = _atom_fetcher(200, times=1)
    result = scan_latest_filings_atom(fetch, entry_limit=400)

    assert len(result.entries) == 400
    assert result.fetch_retries == 1
    assert calls.count(200) == 2, "the failed page must be asked for again"
    assert result.pages_fetched == 4, "a retry is not another page"
    assert [entry.source_ordinal for entry in result.entries[:3]] == [1, 2, 3]


def test_atom_scanner_keeps_the_pages_it_walked_when_a_page_stays_unavailable() -> None:
    """One transient page must not cost every discovery ahead of it."""

    fetch, calls = _atom_fetcher(200)
    result = scan_latest_filings_atom(fetch, entry_limit=400)

    # The two good pages survive instead of being discarded with the third.
    assert len(result.entries) == 200
    assert result.pages_fetched == 2
    assert calls.count(200) == ATOM_FETCH_ATTEMPTS
    assert result.fetch_retries == ATOM_FETCH_ATTEMPTS - 1
    # The gap is still declared: complete=False reds the run exactly as the
    # discarded-everything path did.
    assert not result.complete
    assert result.stop_reason == "fetch_error"
    assert isinstance(result.error, SecSourceUnavailableError)


def test_atom_scanner_first_page_unavailable_yields_no_false_completeness() -> None:
    fetch, _calls = _atom_fetcher(0)
    result = scan_latest_filings_atom(fetch, entry_limit=400)

    assert result.entries == ()
    assert result.pages_fetched == 0
    assert not result.complete
    assert result.stop_reason == "fetch_error"


def test_atom_scanner_never_retries_a_malformed_feed() -> None:
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'

    with pytest.raises(SecSourceError) as caught:
        scan_latest_filings_atom(fetch, entry_limit=100)
    assert not isinstance(caught.value, SecSourceUnavailableError)
    assert len(calls) == 1, "a broken contract must fail on the first attempt"


def test_atom_scanner_fetch_attempts_is_bounded() -> None:
    fetch, calls = _atom_fetcher(0)
    with pytest.raises(ValueError, match="fetch_attempts"):
        scan_latest_filings_atom(fetch, fetch_attempts=0)
    with pytest.raises(ValueError, match="fetch_attempts"):
        scan_latest_filings_atom(
            fetch, fetch_attempts=ATOM_MAX_FETCH_ATTEMPTS + 1
        )
    with pytest.raises(ValueError, match="fetch_attempts"):
        scan_latest_filings_atom(fetch, fetch_attempts=True)
    assert calls == [], "validation must precede any request"

    # attempts=1 disables the retry without disabling partial recovery.
    fetch, calls = _atom_fetcher(200)
    result = scan_latest_filings_atom(fetch, entry_limit=400, fetch_attempts=1)
    assert calls.count(200) == 1
    assert result.fetch_retries == 0
    assert len(result.entries) == 200
    assert result.stop_reason == "fetch_error"


def test_atom_scanner_clean_scan_reports_no_retries() -> None:
    def fetch(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        return _atom_page(int(query["start"][0]), int(query["count"][0]))

    assert scan_latest_filings_atom(fetch, entry_limit=200).fetch_retries == 0


def test_daily_and_full_master_index_contract() -> None:
    frame = parse_master_index((FIXTURES / "master.idx").read_bytes())
    assert frame["form"].tolist() == [
        "13F-HR",
        "13F-NT",
        "13F-HR/A",
        "13F-NT/A",
    ]
    assert frame["source_ordinal"].tolist() == [1, 2, 4, 5]
    assert frame["cik"].tolist()[0] == "0001792167"
    assert frame["accession"].tolist()[0] == ACCESSION
    assert frame["filing_date"].tolist() == [
        "2026-08-07",
        "2026-08-07",
        "2026-08-07",
        "2026-03-31",
    ]


def _filing_documents() -> dict[str, bytes]:
    return {
        "0001398344-26-013841-index-headers.html": (
            FIXTURES / "0001398344-26-013841-index-headers.html"
        ).read_bytes(),
        "0001398344-26-013841.txt": (FIXTURES / "filing.txt").read_bytes(),
        "primary_doc.xml": (FIXTURES / "primary_doc.xml").read_bytes(),
        "information_table.xml": (FIXTURES / "information_table.xml").read_bytes(),
    }


def test_filing_index_and_xml_normalize_to_bulk_shape() -> None:
    index_source = (FIXTURES / "filing_index.json").read_bytes()
    descriptors = parse_filing_index(index_source, index_url=INDEX_URL)
    assert [item.name for item in descriptors] == [
        "0001398344-26-013841-index-headers.html",
        "0001398344-26-013841.txt",
        "primary_doc.xml",
        "information_table.xml",
    ]
    assert descriptors[0].size == 330
    assert descriptors[2].url.endswith("/primary_doc.xml")

    discovery = FilingDiscovery(
        accession=ACCESSION,
        cik="0001792167",
        form="13F-HR/A",
        filing_date="2026-08-07",
        accepted_at="2026-08-07T17:25:16-04:00",
        index_url=INDEX_URL,
    )
    documents = _filing_documents()
    tables = parse_filing_package(
        index_url=INDEX_URL,
        index_source=index_source,
        documents=documents,
        discovery=discovery,
    )

    assert list(tables.submissions.columns) == SUBMISSION_COLUMNS
    assert tables.submissions.iloc[0].to_dict() == {
        "accession": ACCESSION,
        "filing_date": "2026-08-07",
        "form": "13F-HR/A",
        "cik": "0001792167",
        "period_end": "2025-12-31",
        "accepted_at": "2026-08-07T17:25:16-04:00",
    }
    cover = tables.cover_pages.iloc[0]
    assert bool(cover["is_amendment"])
    assert cover["amendment_number"] == 2
    assert cover["amendment_type"] == "NEW HOLDINGS"
    assert bool(cover["confidential_denied_or_expired"])
    assert cover["date_denied_or_expired"] == "2026-08-01"
    assert cover["date_reported"] == "2026-08-07"

    assert len(tables.holdings) == 2
    assert str(tables.holdings["info_table_sk"].dtype) == "Int64"
    assert tables.holdings["info_table_sk"].isna().all()
    assert str(tables.reported_by["other_manager_sk"].dtype) == "Int64"
    assert tables.holdings["put_call"].tolist() == ["CALL", "PUT"]
    assert tables.holdings["investment_discretion"].tolist() == ["DFND", "SOLE"]
    assert tables.holdings["other_manager"].tolist()[0] == "1, 01"
    assert tables.holdings.iloc[0]["voting_authority_shared"] == 3
    assert tables.reported_by.iloc[0]["reporting_manager_cik"] == "0001527166"
    assert tables.included_managers["sequence_number"].tolist() == [1, 1]
    assert tables.included_managers.iloc[0]["included_manager_cik"] == "0001327354"
    assert tables.included_managers.iloc[1]["included_manager_cik"] is None
    assert tables.included_managers.iloc[1]["manager_name"].endswith(
        "another account"
    )
    assert [finding.code for finding in validate_bulk_invariants(tables)] == [
        "duplicate_included_manager_sequence"
    ]
    assert tables.source_bytes == len(index_source) + sum(map(len, documents.values()))
    assert len(tables.source_sha256) == 64


def test_read_filing_package_uses_injected_fetch() -> None:
    index = (FIXTURES / "filing_index.json").read_bytes()
    documents = _filing_documents()
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if url.endswith("/index.json"):
            return index
        return documents[url.rsplit("/", 1)[-1]]

    tables = read_filing_package(INDEX_URL, fetch)
    assert len(tables.holdings) == 2
    assert calls[0].endswith("/index.json")
    assert {url.rsplit("/", 1)[-1] for url in calls[1:]} == set(documents) - {
        "0001398344-26-013841.txt"
    }


def test_filing_package_rejects_identity_and_completeness_drift() -> None:
    index = (FIXTURES / "filing_index.json").read_bytes()
    documents = _filing_documents()
    wrong_discovery = FilingDiscovery(
        accession="0001398344-26-013842",
        cik="0001792167",
        form="13F-HR/A",
        filing_date="2026-08-07",
        accepted_at="2026-08-07T17:25:16-04:00",
        index_url=INDEX_URL,
    )
    with pytest.raises(SecSourceError, match="accession mismatch"):
        parse_filing_package(
            index_url=INDEX_URL,
            index_source=index,
            documents=documents,
            discovery=wrong_discovery,
        )

    wrong_cik_url = INDEX_URL.replace("/data/1792167/", "/data/1555793/")
    with pytest.raises(SecSourceError, match="archive_path"):
        parse_filing_package(
            index_url=wrong_cik_url,
            index_source=index,
            documents=documents,
        )

    incomplete = dict(documents)
    incomplete.pop("information_table.xml")
    with pytest.raises(SecSourceError, match="XML was not supplied"):
        parse_filing_package(
            index_url=INDEX_URL,
            index_source=index,
            documents=incomplete,
        )


def test_filing_package_tolerates_index_size_mismatch_and_warns(capsys) -> None:
    """SEC's index.json ``size`` is advisory (it provably disagrees with SEC's
    own Content-Length and served bytes for some documents, block-rounded to
    4096B in production). A body/index size mismatch must not fail parsing --
    transport truncation is gated authoritatively at fetch time -- but it must
    still surface as a GitHub Actions ``::warning`` annotation."""
    index = (FIXTURES / "filing_index.json").read_bytes()
    documents = _filing_documents()
    wrong_size = dict(documents)
    wrong_size["information_table.xml"] += b"\n"

    tables = parse_filing_package(
        index_url=INDEX_URL,
        index_source=index,
        documents=wrong_size,
    )

    assert len(tables.holdings) == 2
    out = capsys.readouterr().out
    warning_lines = [line for line in out.splitlines() if line.startswith("::")]
    assert warning_lines, f"no line-leading annotation emitted; captured: {out!r}"
    assert any(
        "sec-index-size-mismatch" in line and "information_table.xml" in line
        for line in warning_lines
    )


def test_filing_index_rejects_unsafe_member_name() -> None:
    payload = {"directory": {"item": [{"name": "../primary_doc.xml"}]}}
    with pytest.raises(SecSourceError, match="unsafe filing document"):
        parse_filing_index(payload, index_url=INDEX_URL)


# --- SEC index.json document-omission regression (~2026-08-25) -----------
#
# EDGAR's archive index.json has intermittently served a directory.item list
# that omits one of the filing's own XML documents.  Verified live
# 2026-08-27: accession 0000905148-26-003956 (Whitebox Advisors, CIK
# 1257391, 13F-HR/A) has an index.json that lists only form13fInfoTable.xml
# and the two index/txt files -- primary_doc.xml is absent from index.json
# even though it serves fine directly and is listed in the filing's own SGML
# header.  The fixtures below are captured live (not synthesized) so this
# suite is pinned to the actual regression shape rather than a guess at it.

REGRESSION_FIXTURES = FIXTURES / "regression_index_omission"
REGRESSION_ACCESSION = "0000905148-26-003956"
REGRESSION_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/1257391/000090514826003956/"
    "0000905148-26-003956-index.htm"
)


def test_read_filing_package_recovers_document_missing_from_index_json(capsys) -> None:
    index_body = (REGRESSION_FIXTURES / "index.json").read_bytes()
    index_names = {item["name"] for item in json.loads(index_body)["directory"]["item"]}
    assert "primary_doc.xml" not in index_names, (
        "captured fixture no longer reproduces the index.json omission -- "
        "re-capture it before trusting this test"
    )

    documents = {
        "0000905148-26-003956-index-headers.html": (
            REGRESSION_FIXTURES / "0000905148-26-003956-index-headers.html"
        ).read_bytes(),
        "form13fInfoTable.xml": (
            REGRESSION_FIXTURES / "form13fInfoTable.xml"
        ).read_bytes(),
        "primary_doc.xml": (REGRESSION_FIXTURES / "primary_doc.xml").read_bytes(),
    }
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if url.endswith("/index.json"):
            return index_body
        return documents[url.rsplit("/", 1)[-1]]

    tables = read_filing_package(REGRESSION_INDEX_URL, fetch)

    submission = tables.submissions.iloc[0]
    assert submission["cik"] == "0001257391"
    assert submission["form"] == "13F-HR/A"
    assert submission["accession"] == REGRESSION_ACCESSION
    assert not tables.holdings.empty

    assert any(url.endswith("/primary_doc.xml") for url in calls), (
        "recovery must actively fetch the document index.json omitted"
    )

    out = capsys.readouterr().out
    warning_lines = [line for line in out.splitlines() if line.startswith("::")]
    assert any(
        line.startswith("::warning title=sec-index-missing-documents::")
        for line in warning_lines
    ), f"no recovery annotation emitted; captured: {out!r}"


def test_parse_filing_package_recovers_xml_omitted_from_index_json() -> None:
    """Same recovery, exercised on the pre-existing fixture set: a hand-built
    index.json with the information_table.xml entry dropped still parses when
    the document body is supplied (SGML recovery), and still fails closed
    when it is not (no body to recover with -- the completeness gate must
    stay a real gate, not a rubber stamp)."""

    index_payload = json.loads((FIXTURES / "filing_index.json").read_bytes())
    items = index_payload["directory"]["item"]
    truncated_items = [item for item in items if item["name"] != "information_table.xml"]
    assert len(truncated_items) == len(items) - 1
    index_payload["directory"]["item"] = truncated_items

    base_header = (FIXTURES / "0001398344-26-013841-index-headers.html").read_text()
    assert "FILENAME" not in base_header.upper(), (
        "fixture header must not already list documents, or this test proves nothing"
    )
    header_source = base_header.replace(
        "</PRE></BODY></HTML>",
        "&lt;DOCUMENT&gt;\n&lt;TYPE&gt;13F-HR/A\n&lt;SEQUENCE&gt;1\n"
        "&lt;FILENAME&gt;primary_doc.xml\n&lt;/DOCUMENT&gt;\n"
        "&lt;DOCUMENT&gt;\n&lt;TYPE&gt;INFORMATION TABLE\n&lt;SEQUENCE&gt;2\n"
        "&lt;FILENAME&gt;information_table.xml\n&lt;/DOCUMENT&gt;\n"
        "</PRE></BODY></HTML>",
    )
    assert header_source != base_header

    documents = {
        "0001398344-26-013841-index-headers.html": header_source.encode("utf-8"),
        "primary_doc.xml": (FIXTURES / "primary_doc.xml").read_bytes(),
        "information_table.xml": (FIXTURES / "information_table.xml").read_bytes(),
    }

    tables = parse_filing_package(
        index_url=INDEX_URL,
        index_source=index_payload,
        documents=documents,
    )
    assert len(tables.holdings) == 2

    incomplete = dict(documents)
    incomplete.pop("information_table.xml")
    with pytest.raises(SecSourceError, match="not supplied"):
        parse_filing_package(
            index_url=INDEX_URL,
            index_source=index_payload,
            documents=incomplete,
        )


def test_sgml_document_names_rejects_unsafe_filename() -> None:
    from engine.institutional_census import sec_sources

    header = "<PRE>&lt;DOCUMENT&gt;\n&lt;FILENAME&gt;../evil.xml\n&lt;/DOCUMENT&gt;</PRE>"
    with pytest.raises(SecSourceError, match="unsafe filing document name"):
        sec_sources._sgml_document_names(header)
