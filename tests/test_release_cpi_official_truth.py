from __future__ import annotations

import calendar
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from engine.release_cpi_official_truth import (
    ARCHIVE_NONPUBLICATION_ACTUAL_BASIS,
    ARCHIVE_SEQUENCE,
    ARCHIVED_TABLE1_ACTUAL_BASIS,
    FIRST_PRINT_STATUS,
    USER_AGENT,
    CpiOfficialTruthError,
    CpiSourceSpec,
    build_cpi_not_published_truth,
    build_cpi_official_truth,
    canonical_json_bytes,
    parse_table1_rows,
    parse_table1_workbook,
    rebuild_cpi_official_truth_receipt,
    validate_source_spec,
)
from scripts import collect_release_cpi_official_truth as collector_module
from scripts.collect_release_cpi_official_truth import (
    DEFAULT_BUILD_COMPLETION,
    DEFAULT_COLLECTION_MANIFEST,
    DEFAULT_RECEIPTS,
    DEFAULT_STORE,
    FetchResult,
    collect_cpi_official_truth,
    collect_preregistered_sample,
    load_preregistered_specs,
)

FIXTURES = Path(__file__).parent / "fixtures" / "release_cpi_truth"
PREREGISTERED_SAMPLE = (
    Path(__file__).parent.parent
    / "data"
    / "release_forecast"
    / "cpi_truth"
    / "preregistered_sample.json"
)
DIRECT_URL = (
    "https://www.bls.gov/cpi/tables/supplemental-files/news-release-table1-202606.xlsx"
)


def _rows() -> list[list[object]]:
    return json.loads((FIXTURES / "table1_rows.json").read_text(encoding="utf-8"))


def _xlsx(rows: list[list[object]] | None = None) -> bytes:
    rows = rows or _rows()
    worksheet_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column, value in enumerate(row):
            if value is None:
                continue
            ref = f"{_column_name(column)}{row_number}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                escaped = (
                    str(value)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'
                )
        worksheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(worksheet_rows)}</sheetData></worksheet>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def _annual_zip(member: str, document: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, document)
    return buffer.getvalue()


def _replace_xlsx_sheet(document: bytes, sheet_body: bytes) -> bytes:
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(document)) as source,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for name in source.namelist():
            target.writestr(
                name,
                sheet_body if name == "xl/worksheets/sheet1.xml" else source.read(name),
            )
    return buffer.getvalue()


def _column_name(column: int) -> str:
    value = column + 1
    out = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        out = chr(ord("A") + remainder) + out
    return out


def _shift_month(period: str, delta: int) -> tuple[int, int]:
    year, month = (int(part) for part in period.split("-"))
    absolute = year * 12 + month - 1 + delta
    return divmod(absolute, 12)[0], divmod(absolute, 12)[1] + 1


def _month_token(value: tuple[int, int], *, full: bool = False) -> str:
    year, month = value
    name = calendar.month_name[month] if full else calendar.month_abbr[month] + "."
    return f"{name} {year}"


def _rows_for_period(
    period: str,
    *,
    headline: float,
    core: float,
) -> list[list[object]]:
    target = _shift_month(period, 0)
    prior = _shift_month(period, -1)
    prior_two = _shift_month(period, -2)
    prior_three = _shift_month(period, -3)
    prior_year = (target[0] - 1, target[1])
    return [
        [
            None,
            "Table 1. Consumer Price Index for All Urban Consumers (CPI-U): "
            "U.S. city average, by expenditure category, "
            + _month_token(target, full=True),
        ],
        [None, "[1982-84=100, unless otherwise noted]"],
        [],
        [
            "Indent Level",
            "Expenditure category",
            "Relative importance " + _month_token(prior),
            "Unadjusted indexes",
            "Unadjusted indexes",
            "Unadjusted indexes",
            "Unadjusted percent change",
            "Unadjusted percent change",
            "Seasonally adjusted percent change",
            "Seasonally adjusted percent change",
            "Seasonally adjusted percent change",
        ],
        [
            None,
            None,
            None,
            _month_token(prior_year),
            _month_token(prior),
            _month_token(target),
            f"{_month_token(prior_year)}-{_month_token(target)}",
            f"{_month_token(prior)}-{_month_token(target)}",
            f"{_month_token(prior_three)}-{_month_token(prior_two)}",
            f"{_month_token(prior_two)}-{_month_token(prior)}",
            f"{_month_token(prior)}-{_month_token(target)}",
        ],
        [],
        [0, "All items", 100.0, 300.0, 310.0, 311.0, 3.0, 0.3, 0.1, 0.2, headline],
        [
            1,
            "All items less food and energy",
            79.0,
            300.0,
            310.0,
            311.0,
            2.5,
            0.2,
            0.1,
            0.2,
            core,
        ],
    ]


def _write_small_preregistered_sample(path: Path) -> dict[str, bytes]:
    first = _xlsx(_rows_for_period("2026-05", headline=0.2, core=0.3))
    second = _xlsx(_rows_for_period("2026-06", headline=-0.4, core=0.0))
    members = {
        "news-release-table1-202605.xlsx": first,
        "news-release-table1-202606.xlsx": second,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, document in members.items():
            archive.writestr(member, document)
    transport = buffer.getvalue()
    source_url = "https://www.bls.gov/cpi/tables/supplemental-files/archive-2026.zip"
    gap_url = "https://www.bls.gov/bls/news-release/cpi.htm"
    gap_statement = (
        "October 2025 Consumer Price Index – Not published because of 2025 "
        "lapse in federal government appropriations"
    )
    gap_html = f"<html><body><li>{gap_statement}</li></body></html>".encode()
    gap = build_cpi_not_published_truth(
        gap_html,
        case_id="gap",
        source_id="bls_cpi_archive_index",
        period="2025-10",
        reason="BLS states that October 2025 CPI was not published.",
        source_url=gap_url,
        evidence_statement=gap_statement,
    ).receipt
    payload = {
        "schema": "release_cpi_truth_preregistered_sample.v1",
        "gate": {
            "published_cases_required": 2,
            "explicit_gap_cases_required": 1,
        },
        "sources": {
            "archive_2026": {
                "url": source_url,
                "container_sha256": hashlib.sha256(transport).hexdigest(),
                "container_bytes": len(transport),
            },
            "bls_cpi_archive_index": {
                "url": gap_url,
                "container_sha256": gap["source_sha256"],
                "container_bytes": len(gap_html),
                "publisher": "U.S. Bureau of Labor Statistics",
                "host": "www.bls.gov",
                "content_type": "text/html",
            },
        },
        "cases": [
            {
                "case_id": "may",
                "period": "2026-05",
                "release_date": "2026-06-10",
                "classification": "ordinary",
                "publication_status": "published",
                "source_id": "archive_2026",
                "member": "news-release-table1-202605.xlsx",
                "member_sha256": hashlib.sha256(first).hexdigest(),
                "member_bytes": len(first),
                "release_page_url": "https://www.bls.gov/news.release/",
            },
            {
                "case_id": "june",
                "period": "2026-06",
                "release_date": "2026-07-14",
                "classification": "ordinary",
                "publication_status": "published",
                "source_id": "archive_2026",
                "member": "news-release-table1-202606.xlsx",
                "member_sha256": hashlib.sha256(second).hexdigest(),
                "member_bytes": len(second),
                "release_page_url": "https://www.bls.gov/news.release/",
            },
            {
                "case_id": "gap",
                "period": "2025-10",
                "release_date": None,
                "classification": "ordinary",
                "publication_status": "not_published",
                "source_id": "bls_cpi_archive_index",
                "member": None,
                "member_sha256": None,
                "member_bytes": None,
                "release_page_url": gap_url,
                "reason": "BLS states that October 2025 CPI was not published.",
                "evidence_statement": gap_statement,
                "evidence_sha256": gap["source_sha256"],
                "evidence_bytes": len(gap_html),
                "receipt_id": gap["receipt_id"],
                "source_sha256": gap["source_sha256"],
                "declaration_sha256": gap["source"]["declaration_sha256"],
                "declaration_bytes": gap["source"]["declaration_bytes"],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {source_url: transport, gap_url: gap_html}


def test_table1_parse_is_label_and_period_header_driven() -> None:
    result = parse_table1_rows(_rows(), period="2026-06")

    assert result["status"] == "ok"
    assert result["selection"]["mom_column"] == "K"
    assert result["selection"]["yoy_column"] == "G"
    assert result["selection"]["relative_importance_column"] == "C"
    headline, core = result["targets"]
    assert headline["label"] == "All items"
    assert headline["mom"] == -0.4
    assert headline["yoy"] == 3.5
    assert headline["relative_importance"] == 100.0
    assert headline["sequence"] == ARCHIVE_SEQUENCE
    assert headline["first_print_status"] == FIRST_PRINT_STATUS
    assert headline["actual_basis"] == ARCHIVED_TABLE1_ACTUAL_BASIS
    assert headline["exact_target_id"] == "cpi_headline_mom_archived_release_edition"
    assert core["mom"] == 0.0
    assert core["yoy"] == 2.6
    assert core["relative_importance"] == 78.763
    assert core["exact_target_id"] == "cpi_core_mom_archived_release_edition"


def test_layout_shift_does_not_change_semantic_result() -> None:
    shifted = [[None, None, *row] for row in _rows()]
    result = parse_table1_rows(shifted, period="2026-06")

    assert [target["mom"] for target in result["targets"]] == [-0.4, 0.0]
    assert result["selection"]["mom_column"] == "M"


def test_legacy_merged_title_does_not_make_month_columns_ambiguous() -> None:
    rows = _rows_for_period("2012-01", headline=0.2, core=0.2)
    title = rows[0][1]
    rows[0] = [title] * 11

    result = parse_table1_rows(rows, period="2012-01")

    assert result["selection"]["mom_column"] == "K"
    assert result["selection"]["yoy_column"] == "G"
    assert [target["mom"] for target in result["targets"]] == [0.2, 0.2]


def test_header_drift_is_explicitly_unavailable() -> None:
    rows = _rows()
    rows[3] = [
        "monthly change" if value == "Seasonally adjusted percent change" else value
        for value in rows[3]
    ]
    build = build_cpi_official_truth(
        _xlsx(rows),
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
    )

    assert build.receipt["status"] == "unavailable"
    assert build.receipt["reason"] == "current_month_sa_mom_header_missing"
    assert build.receipt["targets"] == []


def test_direct_xlsx_binds_exact_bytes_and_is_deterministic() -> None:
    body = _xlsx()
    spec = CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL)
    first = build_cpi_official_truth(body, spec=spec)
    second = build_cpi_official_truth(body, spec=spec)

    assert first.receipt == second.receipt
    assert first.receipt["status"] == "ok"
    assert first.receipt["source"] == {
        "url": DIRECT_URL,
        "transport_sha256": hashlib.sha256(body).hexdigest(),
        "transport_bytes": len(body),
        "member": None,
        "document_sha256": hashlib.sha256(body).hexdigest(),
        "document_bytes": len(body),
        "document_extension": ".xlsx",
    }
    assert first.receipt["receipt_id"].startswith("cpi_official_truth:")
    assert first.receipt["metrics"] == {"cpi_headline": -0.4, "cpi_core": 0.0}
    assert first.receipt["source_sha256"] == hashlib.sha256(body).hexdigest()
    assert first.receipt["authority"] is False
    assert first.receipt["display_only"] is True
    assert first.receipt["sequence"] == ARCHIVE_SEQUENCE
    assert first.receipt["first_print_status"] == FIRST_PRINT_STATUS
    assert first.receipt["actual_basis"] == ARCHIVED_TABLE1_ACTUAL_BASIS


def test_retained_document_rebuild_is_byte_exact_for_annual_member() -> None:
    document = _xlsx(_rows_for_period("2024-06", headline=0.1, core=0.2))
    member = "news-release-table1-202406.xlsx"
    transport = _annual_zip(member, document)
    spec = CpiSourceSpec(
        "2024-06",
        "2024-07-11",
        "https://www.bls.gov/cpi/tables/supplemental-files/archive-2024.zip",
        member,
    )
    collected = build_cpi_official_truth(transport, spec=spec).receipt
    rebuilt = rebuild_cpi_official_truth_receipt(
        document,
        spec=spec,
        transport_sha256=hashlib.sha256(transport).hexdigest(),
        transport_bytes=len(transport),
    )

    assert rebuilt == collected


def test_nonpublication_receipt_is_explicit_and_deterministic() -> None:
    statement = (
        "October 2025 Consumer Price Index – Not published because of 2025 "
        "lapse in federal government appropriations"
    )
    body = f"<html><body><li>{statement}</li></body></html>".encode()
    kwargs = {
        "case_id": "gap_2025_10_appropriations_lapse",
        "source_id": "bls_cpi_archive_index",
        "period": "2025-10",
        "reason": "BLS states that October 2025 CPI was not published.",
        "source_url": "https://www.bls.gov/bls/news-release/cpi.htm",
        "evidence_statement": statement,
    }
    first = build_cpi_not_published_truth(body, **kwargs).receipt
    second = build_cpi_not_published_truth(body, **kwargs).receipt

    assert first == second
    assert first["status"] == "not_published"
    assert first["targets"] == []
    assert first["release_date"] is None
    assert first["receipt_id"].startswith("cpi_official_truth:")
    assert first["sequence"] == ARCHIVE_SEQUENCE
    assert first["first_print_status"] == FIRST_PRINT_STATUS
    assert first["actual_basis"] == ARCHIVE_NONPUBLICATION_ACTUAL_BASIS
    assert first["parser"]["selection"] == ARCHIVE_NONPUBLICATION_ACTUAL_BASIS


def test_annual_zip_binds_container_and_exact_member_bytes() -> None:
    document = _xlsx()
    member = "news-release-table1-202406.xlsx"
    body = _annual_zip(member, document)
    spec = CpiSourceSpec(
        "2024-06",
        "2024-07-11",
        "https://www.bls.gov/cpi/tables/supplemental-files/archive-2024.zip",
        member,
    )
    build = build_cpi_official_truth(body, spec=spec)

    assert (
        build.receipt["source"]["transport_sha256"] == hashlib.sha256(body).hexdigest()
    )
    assert (
        build.receipt["source"]["document_sha256"]
        == hashlib.sha256(document).hexdigest()
    )
    assert build.receipt["source"]["member"] == member
    # The synthetic table says June 2026, so a 2024-period spec must fail closed.
    assert build.receipt["status"] == "unavailable"
    assert build.receipt["reason"] == "current_month_sa_mom_header_missing"


def test_annual_zip_entry_count_is_bounded_before_member_read() -> None:
    member = "news-release-table1-202406.xlsx"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, _xlsx())
        for index in range(4_096):
            archive.writestr(f"padding/{index}.txt", b"")
    spec = CpiSourceSpec(
        "2024-06",
        "2024-07-11",
        "https://www.bls.gov/cpi/tables/supplemental-files/archive-2024.zip",
        member,
    )

    build = build_cpi_official_truth(buffer.getvalue(), spec=spec)

    assert build.receipt["status"] == "unavailable"
    assert build.receipt["reason"] == "archive_entry_count_exceeds_limit"


def test_xlsx_xml_entry_inflation_is_bounded() -> None:
    oversized_sheet = (
        b'<worksheet xmlns="http://schemas.openxmlformats.org/'
        b'spreadsheetml/2006/main"><sheetData/>'
        + b" " * (4 * 1024 * 1024)
        + b"</worksheet>"
    )
    document = _replace_xlsx_sheet(_xlsx(), oversized_sheet)

    build = build_cpi_official_truth(
        document,
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
    )

    assert build.receipt["status"] == "unavailable"
    assert build.receipt["reason"] == "xlsx_xml_entry_exceeds_size_limit"


def test_xlsx_merged_endpoint_outside_parser_bounds_is_rejected() -> None:
    document = _xlsx()
    with zipfile.ZipFile(io.BytesIO(document)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml")
    sheet = sheet.replace(
        b"</worksheet>",
        b'<mergeCells><mergeCell ref="A1:A999999"/></mergeCells></worksheet>',
    )
    document = _replace_xlsx_sheet(document, sheet)

    build = build_cpi_official_truth(
        document,
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
    )

    assert build.receipt["status"] == "unavailable"
    assert build.receipt["reason"] == "xlsx_merged_dimensions_exceed_limit"


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (
            CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL.replace("https", "http")),
            "allowlist",
        ),
        (
            CpiSourceSpec(
                "2026-06",
                "2026-07-14",
                DIRECT_URL.replace("www.bls.gov", "example.com"),
            ),
            "allowlist",
        ),
        (CpiSourceSpec("2026-05", "2026-07-14", DIRECT_URL), "period"),
        (
            CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL + "?download=1"),
            "allowlist",
        ),
    ],
)
def test_source_allowlist_rejects_unpinned_inputs(
    spec: CpiSourceSpec, message: str
) -> None:
    with pytest.raises(CpiOfficialTruthError, match=message):
        validate_source_spec(spec)


def test_archive_member_traversal_is_rejected() -> None:
    spec = CpiSourceSpec(
        "2024-06",
        "2024-07-11",
        "https://www.bls.gov/cpi/tables/supplemental-files/archive-2024.zip",
        "../news-release-table1-202406.xlsx",
    )
    with pytest.raises(CpiOfficialTruthError, match="unsafe"):
        validate_source_spec(spec)


def test_collector_injects_descriptive_ua_and_writes_content_addressed_objects(
    tmp_path: Path,
) -> None:
    calls = []
    body = _xlsx()

    def fake_fetcher(url: str, **kwargs) -> FetchResult:
        calls.append((url, kwargs))
        return FetchResult(200, body, url)

    result = collect_cpi_official_truth(
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
        store_root=tmp_path,
        fetcher=fake_fetcher,
        retrieved_at="2026-07-14T12:31:00+00:00",
    )

    assert result["status"] == "written"
    assert result["truth_status"] == "ok"
    assert calls[0][1]["headers"]["User-Agent"] == USER_AGENT
    assert "Mozilla" not in USER_AGENT
    assert (tmp_path / result["paths"]["transport_object"]).read_bytes() == body
    assert (tmp_path / result["paths"]["document_object"]).read_bytes() == body
    canonical = json.loads((tmp_path / result["paths"]["canonical"]).read_text())
    assert canonical["receipt_id"] == result["receipt_id"]


def test_collector_is_idempotent_and_keep_first_on_changed_source(
    tmp_path: Path,
) -> None:
    original = _xlsx()
    first = collect_cpi_official_truth(
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
        store_root=tmp_path,
        fetcher=lambda url, **kwargs: FetchResult(200, original, url),
        retrieved_at="2026-07-14T12:31:00+00:00",
    )
    again = collect_cpi_official_truth(
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
        store_root=tmp_path,
        fetcher=lambda url, **kwargs: FetchResult(200, original, url),
        retrieved_at="2026-07-14T12:32:00+00:00",
    )
    changed_rows = _rows()
    changed_rows[6][10] = -0.3
    changed = _xlsx(changed_rows)
    conflict = collect_cpi_official_truth(
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
        store_root=tmp_path,
        fetcher=lambda url, **kwargs: FetchResult(200, changed, url),
        retrieved_at="2026-07-14T12:33:00+00:00",
    )

    assert again["status"] == "idempotent"
    assert conflict["status"] == "conflict_keep_first"
    assert conflict["canonical_receipt_id"] == first["receipt_id"]
    assert conflict["receipt_id"] != first["receipt_id"]
    assert conflict["keep_first_preserved"] is True


def test_unavailable_attempt_does_not_block_later_valid_canonical(
    tmp_path: Path,
) -> None:
    drifted_rows = _rows()
    drifted_rows[3] = [
        "monthly change" if value == "Seasonally adjusted percent change" else value
        for value in drifted_rows[3]
    ]
    unavailable = collect_cpi_official_truth(
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
        store_root=tmp_path,
        fetcher=lambda url, **kwargs: FetchResult(200, _xlsx(drifted_rows), url),
    )

    assert unavailable["status"] == "attempt_recorded"
    assert unavailable["truth_status"] == "unavailable"
    assert unavailable["paths"]["canonical"] is None
    assert (tmp_path / unavailable["paths"]["receipt"]).is_file()
    assert not (tmp_path / "canonical" / "2026-06.json").exists()

    repaired = collect_cpi_official_truth(
        spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
        store_root=tmp_path,
        fetcher=lambda url, **kwargs: FetchResult(200, _xlsx(), url),
    )

    assert repaired["status"] == "written"
    assert repaired["truth_status"] == "ok"
    assert (tmp_path / repaired["paths"]["canonical"]).is_file()


def test_existing_content_address_mismatch_is_rejected(tmp_path: Path) -> None:
    body = _xlsx()
    digest = hashlib.sha256(body).hexdigest()
    target = tmp_path / "objects" / "sha256" / digest
    target.parent.mkdir(parents=True)
    target.write_bytes(b"tampered")

    with pytest.raises(
        CpiOfficialTruthError, match="content-addressed object mismatch"
    ):
        collect_cpi_official_truth(
            spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
            store_root=tmp_path,
            fetcher=lambda url, **kwargs: FetchResult(200, body, url),
        )


@pytest.mark.parametrize(
    ("expected_sha256", "expected_bytes", "error"),
    [
        ("0" * 64, None, "pinned transport_sha256 mismatch"),
        (None, 1, "pinned transport_bytes mismatch"),
    ],
)
def test_pinned_source_binding_is_checked_before_parse_or_write(
    tmp_path: Path,
    monkeypatch,
    expected_sha256: str | None,
    expected_bytes: int | None,
    error: str,
) -> None:
    body = _xlsx()
    parser_called = False

    def forbidden_parser(*_args, **_kwargs):
        nonlocal parser_called
        parser_called = True
        raise AssertionError("transport was parsed before pin verification")

    monkeypatch.setattr(
        collector_module,
        "build_cpi_official_truth",
        forbidden_parser,
    )
    with pytest.raises(CpiOfficialTruthError, match=error):
        collect_cpi_official_truth(
            spec=CpiSourceSpec("2026-06", "2026-07-14", DIRECT_URL),
            store_root=tmp_path,
            fetcher=lambda url, **kwargs: FetchResult(200, body, url),
            expected_transport_sha256=expected_sha256,
            expected_transport_bytes=expected_bytes,
        )
    assert parser_called is False
    assert list(tmp_path.iterdir()) == []


def test_batch_rejects_raw_transport_before_extraction_or_parse(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sample = tmp_path / "sample.json"
    source_bodies = _write_small_preregistered_sample(sample)
    archive_url = next(url for url in source_bodies if url.endswith(".zip"))
    tampered = bytearray(source_bodies[archive_url])
    tampered[-1] ^= 1
    source_bodies[archive_url] = bytes(tampered)
    parser_called = False

    def forbidden_parser(*_args, **_kwargs):
        nonlocal parser_called
        parser_called = True
        raise AssertionError("transport was parsed before pin verification")

    monkeypatch.setattr(
        collector_module,
        "build_cpi_official_truth",
        forbidden_parser,
    )

    with pytest.raises(CpiOfficialTruthError, match="pinned transport_sha256 mismatch"):
        collect_preregistered_sample(
            sample_path=sample,
            store_root=tmp_path / "archive",
            receipts_path=tmp_path / "receipts.jsonl",
            collection_manifest_path=tmp_path / "collection.json",
            fetcher=lambda url, **_kwargs: FetchResult(200, source_bodies[url], url),
        )

    assert parser_called is False
    assert not (tmp_path / "archive").exists()
    assert not (tmp_path / "receipts.jsonl").exists()
    assert not (tmp_path / "collection.json").exists()


def test_preregistered_panel_has_fourteen_sources_and_one_explicit_gap() -> None:
    sample = json.loads(PREREGISTERED_SAMPLE.read_text(encoding="utf-8"))
    cases = sample["cases"]
    assert len(cases) == 15
    assert [
        case["period"]
        for case in cases
        if case["publication_status"] == "not_published"
    ] == ["2025-10"]

    normalized = load_preregistered_specs(PREREGISTERED_SAMPLE)
    assert len(normalized) == 15
    assert sum(row["publication_status"] == "published" for row in normalized) == 14
    assert sum(row["publication_status"] == "not_published" for row in normalized) == 1
    assert all(
        len(str(row["expected_transport_sha256"])) == 64
        for row in normalized
        if row["publication_status"] == "published"
    )
    assert sample["official_target_epoch"] == {
        "target_epoch": "official_bls_archived_release_table1_v1",
        "status": "withheld",
        "first_print_status": FIRST_PRINT_STATUS,
        "reason": (
            "This preregistered parity panel contains official archived release "
            "editions only; it does not establish original release-day CPI bytes "
            "or values."
        ),
    }


def test_batch_fetches_each_url_once_and_incrementally_reuses_without_network(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.json"
    source_bodies = _write_small_preregistered_sample(sample)
    store = tmp_path / "archive"
    receipts_path = tmp_path / "official_table1_receipts.jsonl"
    manifest_path = tmp_path / "official_table1_collection.json"
    build_completion_path = tmp_path / "build_completion.json"
    calls: list[str] = []

    def fake_fetcher(url: str, **_kwargs) -> FetchResult:
        calls.append(url)
        return FetchResult(200, source_bodies[url], url)

    first = collect_preregistered_sample(
        sample_path=sample,
        store_root=store,
        receipts_path=receipts_path,
        collection_manifest_path=manifest_path,
        fetcher=fake_fetcher,
        retrieved_at="2026-08-11T04:00:00+00:00",
    )
    first_receipt_bytes = receipts_path.read_bytes()
    first_manifest_bytes = manifest_path.read_bytes()
    first_receipt_mtime = receipts_path.stat().st_mtime_ns
    first_manifest_mtime = manifest_path.stat().st_mtime_ns
    downstream_completion = b'{"schema":"sentinel.complete"}\n'
    build_completion_path.write_bytes(downstream_completion)
    first_completion_mtime = build_completion_path.stat().st_mtime_ns
    truth = [json.loads(line) for line in first_receipt_bytes.splitlines()]

    assert len(calls) == 2
    assert first["status"] == "complete"
    assert first["counts"] == {
        "published": 2,
        "not_published": 1,
        "distinct_source_urls": 2,
    }
    assert first["run"]["fetched_cases"] == 3
    assert first["run"]["reused_cases"] == 0
    assert first["run"]["fetched_source_urls"] == 2
    persisted_manifest = json.loads(first_manifest_bytes)
    assert persisted_manifest["completed_at"] == "2026-08-11T04:00:00+00:00"
    assert "run" not in persisted_manifest
    assert "retrieved_at" not in persisted_manifest
    assert [receipt["status"] for receipt in truth] == [
        "ok",
        "ok",
        "not_published",
    ]
    assert all("retrieved_at" not in receipt for receipt in truth)
    assert not (store / "objects").exists()
    assert len(list((store / "documents" / "sha256").iterdir())) == 3

    def no_network(url: str, **_kwargs) -> FetchResult:
        raise AssertionError(f"incremental rerun unexpectedly fetched {url}")

    second = collect_preregistered_sample(
        sample_path=sample,
        store_root=store,
        receipts_path=receipts_path,
        collection_manifest_path=manifest_path,
        fetcher=no_network,
        retrieved_at="2026-08-11T04:01:00+00:00",
    )

    assert receipts_path.read_bytes() == first_receipt_bytes
    assert manifest_path.read_bytes() == first_manifest_bytes
    assert receipts_path.stat().st_mtime_ns == first_receipt_mtime
    assert manifest_path.stat().st_mtime_ns == first_manifest_mtime
    assert build_completion_path.read_bytes() == downstream_completion
    assert build_completion_path.stat().st_mtime_ns == first_completion_mtime
    assert second["completed_at"] == "2026-08-11T04:00:00+00:00"
    assert second["run"]["fetched_cases"] == 0
    assert second["run"]["reused_cases"] == 3
    assert second["run"]["fetched_source_urls"] == 0


def test_resigned_published_authority_tamper_is_rejected_and_not_aggregated(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.json"
    source_bodies = _write_small_preregistered_sample(sample)
    store = tmp_path / "archive"
    receipts_path = tmp_path / "official_table1_receipts.jsonl"
    manifest_path = tmp_path / "official_table1_collection.json"
    collect_preregistered_sample(
        sample_path=sample,
        store_root=store,
        receipts_path=receipts_path,
        collection_manifest_path=manifest_path,
        fetcher=lambda url, **_kwargs: FetchResult(200, source_bodies[url], url),
        retrieved_at="2026-08-11T04:00:00+00:00",
    )
    receipts_before = receipts_path.read_bytes()
    manifest_before = manifest_path.read_bytes()
    canonical_path = store / "canonical" / "2026-05.json"
    tampered = json.loads(canonical_path.read_text(encoding="utf-8"))
    tampered["authority"] = True
    tampered["display_only"] = False
    tampered.pop("receipt_id")
    tampered["receipt_id"] = (
        "cpi_official_truth:"
        + hashlib.sha256(canonical_json_bytes(tampered)).hexdigest()[:32]
    )
    canonical_path.write_bytes(canonical_json_bytes(tampered))
    calls: list[str] = []

    def fake_fetcher(url: str, **_kwargs) -> FetchResult:
        calls.append(url)
        return FetchResult(200, source_bodies[url], url)

    with pytest.raises(CpiOfficialTruthError, match="canonical receipt conflicts"):
        collect_preregistered_sample(
            sample_path=sample,
            store_root=store,
            receipts_path=receipts_path,
            collection_manifest_path=manifest_path,
            fetcher=fake_fetcher,
            retrieved_at="2026-08-11T04:01:00+00:00",
        )

    assert calls == [
        "https://www.bls.gov/cpi/tables/supplemental-files/archive-2026.zip"
    ]
    assert receipts_path.read_bytes() == receipts_before
    assert manifest_path.read_bytes() == manifest_before


def test_changed_aggregate_invalidates_completion_before_manifest_write(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.json"
    source_bodies = _write_small_preregistered_sample(sample)
    store = tmp_path / "archive"
    receipts_path = tmp_path / "official_table1_receipts.jsonl"
    manifest_path = tmp_path / "official_table1_collection.json"
    build_completion_path = tmp_path / "build_completion.json"
    collect_preregistered_sample(
        sample_path=sample,
        store_root=store,
        receipts_path=receipts_path,
        collection_manifest_path=manifest_path,
        fetcher=lambda url, **_kwargs: FetchResult(200, source_bodies[url], url),
        retrieved_at="2026-08-11T04:00:00+00:00",
    )
    expected_receipts = receipts_path.read_bytes()
    assert manifest_path.is_file()
    build_completion_path.write_bytes(b'{"status":"complete"}\n')
    receipts_path.write_bytes(b"stale aggregate\n")

    def fail_manifest_write(_path: Path, _body: bytes) -> None:
        raise RuntimeError("injected manifest write failure")

    with pytest.raises(RuntimeError, match="injected manifest write failure"):
        collect_preregistered_sample(
            sample_path=sample,
            store_root=store,
            receipts_path=receipts_path,
            collection_manifest_path=manifest_path,
            fetcher=lambda url, **_kwargs: (_ for _ in ()).throw(
                AssertionError(f"unexpected fetch: {url}")
            ),
            retrieved_at="2026-08-11T04:01:00+00:00",
            manifest_writer=fail_manifest_write,
        )

    assert receipts_path.read_bytes() == expected_receipts
    assert not manifest_path.exists()
    assert not build_completion_path.exists()


def test_changed_aggregate_invalidates_downstream_completion_before_republish(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.json"
    source_bodies = _write_small_preregistered_sample(sample)
    store = tmp_path / "archive"
    receipts_path = tmp_path / "official_table1_receipts.jsonl"
    manifest_path = tmp_path / "official_table1_collection.json"
    build_completion_path = tmp_path / "build_completion.json"
    collect_preregistered_sample(
        sample_path=sample,
        store_root=store,
        receipts_path=receipts_path,
        collection_manifest_path=manifest_path,
        fetcher=lambda url, **_kwargs: FetchResult(200, source_bodies[url], url),
        retrieved_at="2026-08-11T04:00:00+00:00",
    )
    expected_receipts = receipts_path.read_bytes()
    build_completion_path.write_bytes(b'{"status":"complete"}\n')
    receipts_path.write_bytes(b"stale aggregate\n")

    result = collect_preregistered_sample(
        sample_path=sample,
        store_root=store,
        receipts_path=receipts_path,
        collection_manifest_path=manifest_path,
        fetcher=lambda url, **_kwargs: (_ for _ in ()).throw(
            AssertionError(f"unexpected fetch: {url}")
        ),
        retrieved_at="2026-08-11T04:01:00+00:00",
    )

    assert result["status"] == "complete"
    assert result["completed_at"] == "2026-08-11T04:00:00+00:00"
    assert receipts_path.read_bytes() == expected_receipts
    assert manifest_path.is_file()
    assert not build_completion_path.exists()


def test_changed_preregistered_evidence_uses_current_completion_clock(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.json"
    source_bodies = _write_small_preregistered_sample(sample)
    store = tmp_path / "archive"
    receipts_path = tmp_path / "official_table1_receipts.jsonl"
    manifest_path = tmp_path / "official_table1_collection.json"
    build_completion_path = tmp_path / "build_completion.json"
    collect_preregistered_sample(
        sample_path=sample,
        store_root=store,
        receipts_path=receipts_path,
        collection_manifest_path=manifest_path,
        fetcher=lambda url, **_kwargs: FetchResult(200, source_bodies[url], url),
        retrieved_at="2026-08-11T04:00:00+00:00",
    )
    sample_payload = json.loads(sample.read_text(encoding="utf-8"))
    sample_payload["evidence_revision"] = "new-bound-corpus"
    sample.write_text(
        json.dumps(sample_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    build_completion_path.write_bytes(b'{"status":"complete"}\n')

    result = collect_preregistered_sample(
        sample_path=sample,
        store_root=store,
        receipts_path=receipts_path,
        collection_manifest_path=manifest_path,
        fetcher=lambda url, **_kwargs: (_ for _ in ()).throw(
            AssertionError(f"unexpected fetch: {url}")
        ),
        retrieved_at="2026-08-11T04:02:00+00:00",
    )

    assert result["completed_at"] == "2026-08-11T04:02:00+00:00"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["completed_at"] == (
        "2026-08-11T04:02:00+00:00"
    )
    assert not build_completion_path.exists()


def test_default_paths_target_the_frozen_truth_corpus() -> None:
    expected_root = (
        Path(__file__).parent.parent / "data" / "release_forecast" / "cpi_truth"
    )
    assert DEFAULT_STORE == expected_root / "official_table1_archive"
    assert DEFAULT_RECEIPTS == expected_root / "official_table1_receipts.jsonl"
    assert (
        DEFAULT_COLLECTION_MANIFEST == expected_root / "official_table1_collection.json"
    )
    assert DEFAULT_BUILD_COMPLETION == expected_root / "build_completion.json"


def test_retained_real_2026_xlsx_replays_without_network() -> None:
    document = (
        DEFAULT_STORE
        / "documents"
        / "sha256"
        / "f7fa6474d70b43ceb50202ef31bcbb36567fcdd08f873b01cd399be0eec0d0ba.xlsx"
    )
    assert document.is_file()

    parsed = parse_table1_workbook(
        document.read_bytes(),
        extension=".xlsx",
        period="2026-06",
    )

    assert [target["mom"] for target in parsed["targets"]] == [-0.4, 0.0]
    assert [target["yoy"] for target in parsed["targets"]] == [3.5, 2.6]


def test_retained_real_2012_xls_replays_without_network() -> None:
    document = (
        DEFAULT_STORE
        / "documents"
        / "sha256"
        / "486c5aaf478f7651e5dbd8fb3364d2341813391fc2cff343abbdf09ea23abae0.xls"
    )
    assert document.is_file()
    pytest.importorskip("xlrd", reason="legacy BLS .xls replay requires xlrd")

    parsed = parse_table1_workbook(
        document.read_bytes(),
        extension=".xls",
        period="2012-01",
    )

    assert [target["mom"] for target in parsed["targets"]] == [0.2, 0.2]
    assert [target["yoy"] for target in parsed["targets"]] == [2.9, 2.3]


def test_default_corpus_has_bound_fourteen_plus_one_receipts() -> None:
    cases = load_preregistered_specs(PREREGISTERED_SAMPLE)
    manifest = json.loads(DEFAULT_COLLECTION_MANIFEST.read_text(encoding="utf-8"))
    receipts = [
        json.loads(line)
        for line in DEFAULT_RECEIPTS.read_text(encoding="utf-8").splitlines()
    ]

    assert len(receipts) == len(cases) == 15
    assert sum(receipt["status"] == "ok" for receipt in receipts) == 14
    assert all(receipt["sequence"] == ARCHIVE_SEQUENCE for receipt in receipts)
    assert all(
        receipt["first_print_status"] == FIRST_PRINT_STATUS for receipt in receipts
    )
    assert all(receipt["authority"] is False for receipt in receipts)
    assert all(receipt["display_only"] is True for receipt in receipts)
    gap = next(receipt for receipt in receipts if receipt["status"] == "not_published")
    gap_case = next(
        case for case in cases if case["publication_status"] == "not_published"
    )
    gap_document = (
        DEFAULT_STORE
        / "documents"
        / "sha256"
        / f"{gap_case['expected_evidence_sha256']}.html"
    )
    rebuilt_gap = build_cpi_not_published_truth(
        gap_document.read_bytes(),
        case_id=gap_case["case_id"],
        source_id=gap_case["source_id"],
        period=gap_case["period"],
        reason=gap_case["reason"],
        source_url=gap_case["source_url"],
        evidence_statement=gap_case["evidence_statement"],
    ).receipt
    assert gap == rebuilt_gap
    assert gap["case_id"] == "gap_2025_10_appropriations_lapse"
    assert gap["source_sha256"] == gap["source"]["document_sha256"]
    assert (
        gap["source"]["declaration_sha256"] == gap_case["expected_declaration_sha256"]
    )
    assert all("retrieved_at" not in receipt for receipt in receipts)
    assert manifest["status"] == "complete"
    assert "completed_at" in manifest
    assert "retrieved_at" not in manifest
    assert "run" not in manifest
    assert manifest["counts"] == {
        "published": 14,
        "not_published": 1,
        "distinct_source_urls": 12,
    }
    preregistered_body = PREREGISTERED_SAMPLE.read_bytes()
    receipts_body = DEFAULT_RECEIPTS.read_bytes()
    assert (
        manifest["preregistered_sample"]["sha256"]
        == hashlib.sha256(preregistered_body).hexdigest()
    )
    assert manifest["preregistered_sample"]["bytes"] == len(preregistered_body)
    assert manifest["receipts"]["sha256"] == hashlib.sha256(receipts_body).hexdigest()
    assert manifest["receipts"]["bytes"] == len(receipts_body)
    assert manifest["receipts"]["count"] == len(receipts)
    assert [row["case_id"] for row in manifest["cases"]] == [
        row["case_id"] for row in cases
    ]
    for index, row in enumerate(manifest["cases"]):
        document = DEFAULT_STORE / row["source"]["document_object"]
        body = document.read_bytes()
        assert len(body) == row["source"]["document_bytes"]
        assert hashlib.sha256(body).hexdigest() == row["source"]["document_sha256"]
        receipt = receipts[index]
        receipt_object = (
            DEFAULT_STORE
            / "receipts"
            / "sha256"
            / f"{receipt['receipt_id'].split(':', 1)[1]}.json"
        )
        assert receipt_object.read_bytes() == canonical_json_bytes(receipt)
        if cases[index]["publication_status"] == "published":
            rebuilt = rebuild_cpi_official_truth_receipt(
                body,
                spec=cases[index]["spec"],
                transport_sha256=cases[index]["expected_transport_sha256"],
                transport_bytes=cases[index]["expected_transport_bytes"],
            )
            assert receipt == rebuilt
            assert receipt["actual_basis"] == ARCHIVED_TABLE1_ACTUAL_BASIS
            assert all(
                target["actual_basis"] == ARCHIVED_TABLE1_ACTUAL_BASIS
                and target["sequence"] == ARCHIVE_SEQUENCE
                and target["first_print_status"] == FIRST_PRINT_STATUS
                and target["exact_target_id"].endswith("_archived_release_edition")
                for target in receipt["targets"]
            )
