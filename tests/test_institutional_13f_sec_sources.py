from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from engine.institutional_census.sec_sources import (
    ATOM_EPHEMERAL_ENTRY_LIMIT,
    COVER_PAGE_COLUMNS,
    HOLDING_COLUMNS,
    INCLUDED_MANAGER_COLUMNS,
    REPORTED_BY_COLUMNS,
    SUBMISSION_COLUMNS,
    SUMMARY_PAGE_COLUMNS,
    FilingDiscovery,
    SecSourceError,
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


def _atom_page(start: int, count: int) -> bytes:
    rows = []
    for sequence in range(start + 1, start + count + 1):
        accession = f"0000000001-26-{sequence:06d}"
        compact = accession.replace("-", "")
        rows.append(
            f"""
            <entry>
              <title>13F-HR - Page Fixture ({2:010d}) (Filer)</title>
              <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/2/{compact}/{accession}-index.htm"/>
              <summary type="html">Filed: 2026-08-07 AccNo: {accession}</summary>
              <updated>2026-08-07T17:00:00-04:00</updated>
              <category term="13F-HR"/><id>{accession}</id>
            </entry>"""
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        + "".join(rows)
        + "</feed>"
    ).encode()


def test_atom_scanner_has_explicit_ephemeral_boundary() -> None:
    calls: list[tuple[int, int]] = []

    def fetch(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        start = int(query["start"][0])
        count = int(query["count"][0])
        calls.append((start, count))
        return _atom_page(start, count)

    result = scan_latest_filings_atom(fetch)
    assert len(result.entries) == ATOM_EPHEMERAL_ENTRY_LIMIT == 930
    assert result.pages_fetched == 10
    assert not result.complete
    assert result.stop_reason == "ephemeral_limit"
    assert calls[-1] == (900, 30)
    with pytest.raises(ValueError, match="entry_limit"):
        scan_latest_filings_atom(fetch, entry_limit=931)


def test_atom_scanner_short_page_is_complete() -> None:
    payload = (FIXTURES / "latest_filings.atom").read_bytes()
    result = scan_latest_filings_atom(lambda _url: payload)
    assert result.complete
    assert result.stop_reason == "short_page"
    assert result.pages_fetched == 1


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
