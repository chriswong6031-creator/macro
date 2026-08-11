"""Official archived CPI release-edition observations from BLS Table 1.

This module is intentionally narrower than the live publication parser.  It
accepts only the official BLS supplemental-file paths, binds the exact transport
and workbook bytes, and resolves Table 1 by semantic row/header labels.  BLS
retrospective archives may be revised, so these receipts deliberately do not
claim to contain the original release-day bytes or values.  A layout
or label change returns an explicit ``status='unavailable'`` receipt; it never
falls back to fixed cell coordinates or an ALFRED-derived approximation.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

SCHEMA_VERSION = "release_cpi_official_truth.v1"
PARSER_NAME = "bls_cpi_archived_release_table1"
PARSER_VERSION = 1
INTEGRITY_PROFILE = "bls_table1_exact_bytes_sha256.v1"
NONPUBLICATION_INTEGRITY_PROFILE = "bls_nonpublication_page_exact_bytes_sha256.v1"
ARCHIVE_SEQUENCE = "archived_release_edition"
FIRST_PRINT_STATUS = "unverified_retrospective_archive"
ARCHIVED_TABLE1_ACTUAL_BASIS = "official_bls_archived_release_table1"
ARCHIVE_NONPUBLICATION_ACTUAL_BASIS = "official_archive_nonpublication_declaration"
USER_AGENT = (
    "MastermindX-ReleaseRadar-CPI-Archive/1.0 "
    "(+https://www.mastermind-x.com; research intake)"
)
BLS_PUBLISHER = "U.S. Bureau of Labor Statistics"

_DIRECT_PATH = re.compile(
    r"/cpi/tables/supplemental-files/news-release-table1-(?P<period>\d{6})\.xlsx"
)
_ARCHIVE_PATH = re.compile(
    r"/cpi/tables/supplemental-files/archive-(?P<year>\d{4})\.zip"
)
_NONPUBLICATION_PATH = "/bls/news-release/cpi.htm"
_PERIOD = re.compile(r"^(?:19|20)\d{2}-(?:0[1-9]|1[0-2])$")
_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
_MAX_ZIP_ENTRIES = 4_096
_MAX_XLSX_XML_ENTRY_BYTES = 4 * 1024 * 1024
_MAX_WORKSHEET_ROWS = 2_000
_MAX_WORKSHEET_COLUMNS = 256
_XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


class CpiOfficialTruthError(ValueError):
    """The requested source is unsafe or violates its declared contract."""


class _ParseUnavailable(ValueError):
    """A bounded source was readable but could not produce an exact target."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


@dataclass(frozen=True)
class CpiSourceSpec:
    """One official CPI archived release-edition source."""

    period: str
    release_date: str
    url: str
    member: str | None = None


@dataclass(frozen=True)
class CpiOfficialTruthBuild:
    """Archived-edition receipt plus the exact bytes that a store must retain."""

    receipt: dict[str, Any]
    transport_bytes: bytes
    document_bytes: bytes
    document_extension: str


def validate_source_spec(spec: CpiSourceSpec) -> CpiSourceSpec:
    """Validate a source against the bounded official BLS archive allowlist."""
    if not isinstance(spec, CpiSourceSpec):
        raise CpiOfficialTruthError("source spec must be CpiSourceSpec")
    if not _PERIOD.fullmatch(spec.period):
        raise CpiOfficialTruthError("period must be YYYY-MM")
    try:
        release_day = date.fromisoformat(spec.release_date)
    except (TypeError, ValueError) as exc:
        raise CpiOfficialTruthError("release_date must be YYYY-MM-DD") from exc

    period_year, period_month = (int(part) for part in spec.period.split("-"))
    if (release_day.year, release_day.month) <= (period_year, period_month):
        raise CpiOfficialTruthError("release_date must follow the result period")

    parsed = urlparse(spec.url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.bls.gov"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise CpiOfficialTruthError("source URL is outside the official BLS allowlist")

    direct = _DIRECT_PATH.fullmatch(parsed.path)
    archive = _ARCHIVE_PATH.fullmatch(parsed.path)
    period_token = spec.period.replace("-", "")
    if direct:
        if spec.member is not None:
            raise CpiOfficialTruthError(
                "direct XLSX source must not declare a ZIP member"
            )
        if direct.group("period") != period_token:
            raise CpiOfficialTruthError("direct workbook period does not match spec")
    elif archive:
        if archive.group("year") != str(period_year):
            raise CpiOfficialTruthError("annual archive year does not match period")
        member = _validate_member(spec.member)
        if period_token not in PurePosixPath(member).name:
            raise CpiOfficialTruthError("archive member period does not match spec")
    else:
        raise CpiOfficialTruthError("source path is outside the CPI Table 1 allowlist")
    return spec


def build_cpi_official_truth(
    source_bytes: bytes,
    *,
    spec: CpiSourceSpec,
) -> CpiOfficialTruthBuild:
    """Build a deterministic archived-edition receipt from exact source bytes."""
    validate_source_spec(spec)
    if not isinstance(source_bytes, bytes) or not source_bytes:
        raise CpiOfficialTruthError("source body must be non-empty bytes")

    transport_sha = _sha256(source_bytes)
    document_bytes = b""
    extension = PurePosixPath(spec.member or urlparse(spec.url).path).suffix.lower()
    unavailable_reason: str | None = None
    try:
        document_bytes = _extract_document(source_bytes, spec.member)
    except _ParseUnavailable as exc:
        unavailable_reason = exc.reason
    receipt = _build_cpi_official_receipt(
        document_bytes,
        spec=spec,
        transport_sha256=transport_sha,
        transport_bytes=len(source_bytes),
        extension=extension,
        unavailable_reason=unavailable_reason,
    )
    return CpiOfficialTruthBuild(
        receipt=receipt,
        transport_bytes=source_bytes,
        document_bytes=document_bytes,
        document_extension=extension,
    )


def rebuild_cpi_official_truth_receipt(
    document_bytes: bytes,
    *,
    spec: CpiSourceSpec,
    transport_sha256: str,
    transport_bytes: int,
) -> dict[str, Any]:
    """Rebuild the exact receipt from a retained workbook and pinned transport.

    Annual ZIP containers are intentionally not retained by the batch corpus.
    Their hash and length remain preregistered source bindings; the exact
    extracted XLS/XLSX document is retained and reparsed here.  Direct XLSX
    inputs additionally require the transport and document bindings to match.
    """
    validate_source_spec(spec)
    if not isinstance(document_bytes, bytes) or not document_bytes:
        raise CpiOfficialTruthError("retained workbook must be non-empty bytes")
    if (
        not isinstance(transport_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", transport_sha256)
        or isinstance(transport_bytes, bool)
        or not isinstance(transport_bytes, int)
        or transport_bytes <= 0
    ):
        raise CpiOfficialTruthError("retained transport binding is invalid")
    if spec.member is None and (
        _sha256(document_bytes) != transport_sha256
        or len(document_bytes) != transport_bytes
    ):
        raise CpiOfficialTruthError(
            "direct workbook does not match its transport binding"
        )
    extension = PurePosixPath(spec.member or urlparse(spec.url).path).suffix.lower()
    return _build_cpi_official_receipt(
        document_bytes,
        spec=spec,
        transport_sha256=transport_sha256,
        transport_bytes=transport_bytes,
        extension=extension,
    )


def _build_cpi_official_receipt(
    document_bytes: bytes,
    *,
    spec: CpiSourceSpec,
    transport_sha256: str,
    transport_bytes: int,
    extension: str,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    source: dict[str, Any] = {
        "url": spec.url,
        "transport_sha256": transport_sha256,
        "transport_bytes": transport_bytes,
        "member": spec.member,
    }
    if document_bytes:
        source.update(
            {
                "document_sha256": _sha256(document_bytes),
                "document_bytes": len(document_bytes),
                "document_extension": extension,
            }
        )
    if unavailable_reason is None:
        try:
            parsed = parse_table1_workbook(
                document_bytes,
                extension=extension,
                period=spec.period,
            )
        except _ParseUnavailable as exc:
            unavailable_reason = exc.reason
    if unavailable_reason is not None:
        parsed = {
            "status": "unavailable",
            "reason": unavailable_reason,
            "targets": [],
            "gaps": [unavailable_reason],
            "sheet": None,
        }

    payload: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "status": parsed["status"],
        "reason": parsed.get("reason"),
        "release_family": "CPI",
        "period": spec.period,
        "release_date": spec.release_date,
        "sequence": ARCHIVE_SEQUENCE,
        "first_print_status": FIRST_PRINT_STATUS,
        "actual_basis": ARCHIVED_TABLE1_ACTUAL_BASIS,
        "integrity_profile": INTEGRITY_PROFILE,
        "source": source,
        "parser": {
            "name": PARSER_NAME,
            "version": PARSER_VERSION,
            "format": extension.lstrip("."),
            "sheet": parsed.get("sheet"),
            "selection": "semantic_labels_and_period_headers",
        },
        "targets": parsed.get("targets", []),
        "metrics": {
            str(target["release"]): float(target["mom"])
            for target in parsed.get("targets", [])
        },
        "source_sha256": source.get("document_sha256"),
        "gaps": parsed.get("gaps", []),
        "display_only": True,
        "authority": False,
    }
    payload["receipt_id"] = _receipt_id(payload)
    return payload


def build_cpi_not_published_truth(
    source_bytes: bytes,
    *,
    case_id: str,
    source_id: str,
    period: str,
    reason: str,
    source_url: str,
    evidence_statement: str,
) -> CpiOfficialTruthBuild:
    """Build archived source evidence for an explicitly unpublished CPI period."""
    normalized = validate_nonpublication_spec(
        case_id=case_id,
        source_id=source_id,
        period=period,
        reason=reason,
        source_url=source_url,
        evidence_statement=evidence_statement,
    )
    if (
        not isinstance(source_bytes, bytes)
        or not source_bytes
        or len(source_bytes) > _MAX_EVIDENCE_BYTES
    ):
        raise CpiOfficialTruthError(
            "nonpublication evidence must be bounded non-empty bytes"
        )
    try:
        evidence_html = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CpiOfficialTruthError(
            "nonpublication evidence is not UTF-8 HTML"
        ) from exc
    text_parser = _HtmlTextExtractor()
    try:
        text_parser.feed(evidence_html)
        text_parser.close()
    except Exception as exc:
        raise CpiOfficialTruthError("nonpublication evidence HTML is invalid") from exc
    page_text = _normalize_evidence_text(" ".join(text_parser.parts))
    statement_text = _normalize_evidence_text(normalized["evidence_statement"])
    if statement_text not in page_text:
        raise CpiOfficialTruthError(
            "official BLS page does not contain the pinned nonpublication statement"
        )

    source_sha256 = _sha256(source_bytes)
    source_length = len(source_bytes)
    declaration = {
        "schema": "release_cpi_archive_nonpublication_declaration.v1",
        **normalized,
        "source_sha256": source_sha256,
        "source_bytes": source_length,
    }
    declaration_body = canonical_json_bytes(declaration)
    declaration_sha256 = _sha256(declaration_body)

    payload: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "status": "not_published",
        "reason": normalized["reason"],
        "release_family": "CPI",
        "case_id": normalized["case_id"],
        "source_id": normalized["source_id"],
        "period": period,
        "release_date": None,
        "sequence": ARCHIVE_SEQUENCE,
        "first_print_status": FIRST_PRINT_STATUS,
        "actual_basis": ARCHIVE_NONPUBLICATION_ACTUAL_BASIS,
        "integrity_profile": NONPUBLICATION_INTEGRITY_PROFILE,
        "source": {
            "source_id": normalized["source_id"],
            "url": source_url,
            "publisher": BLS_PUBLISHER,
            "host": "www.bls.gov",
            "transport_sha256": source_sha256,
            "transport_bytes": source_length,
            "document_sha256": source_sha256,
            "document_bytes": source_length,
            "document_extension": ".html",
            "evidence_statement": normalized["evidence_statement"],
            "declaration_schema": declaration["schema"],
            "declaration_sha256": declaration_sha256,
            "declaration_bytes": len(declaration_body),
        },
        "parser": {
            "name": PARSER_NAME,
            "version": PARSER_VERSION,
            "format": "html",
            "sheet": None,
            "selection": ARCHIVE_NONPUBLICATION_ACTUAL_BASIS,
        },
        "targets": [],
        "metrics": {},
        "source_sha256": source_sha256,
        "gaps": [normalized["reason"]],
        "display_only": True,
        "authority": False,
    }
    payload["receipt_id"] = _receipt_id(payload)
    return CpiOfficialTruthBuild(
        receipt=payload,
        transport_bytes=source_bytes,
        document_bytes=source_bytes,
        document_extension=".html",
    )


def validate_nonpublication_spec(
    *,
    case_id: str,
    source_id: str,
    period: str,
    reason: str,
    source_url: str,
    evidence_statement: str,
) -> dict[str, str]:
    """Validate a governed nonpublication case before any network request."""
    normalized_case_id = " ".join(str(case_id or "").split())
    if not normalized_case_id:
        raise CpiOfficialTruthError("nonpublication case_id must be non-empty")
    normalized_source_id = " ".join(str(source_id or "").split())
    if not normalized_source_id:
        raise CpiOfficialTruthError("nonpublication source_id must be non-empty")
    if not _PERIOD.fullmatch(period):
        raise CpiOfficialTruthError("period must be YYYY-MM")
    normalized_reason = " ".join(str(reason or "").split())
    if not normalized_reason:
        raise CpiOfficialTruthError("nonpublication reason must be non-empty")
    normalized_statement = " ".join(str(evidence_statement or "").split())
    target_year, target_month = (int(part) for part in period.split("-"))
    required_prefix = f"{_MONTHS[target_month - 1]} {target_year} consumer price index"
    statement_text = _normalize_evidence_text(normalized_statement)
    if required_prefix not in statement_text or "not published" not in statement_text:
        raise CpiOfficialTruthError(
            "nonpublication evidence statement does not identify the target period"
        )
    parsed_url = urlparse(source_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "www.bls.gov"
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.port not in (None, 443)
        or parsed_url.path != _NONPUBLICATION_PATH
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise CpiOfficialTruthError(
            "nonpublication source URL is outside the official BLS allowlist"
        )
    return {
        "case_id": normalized_case_id,
        "source_id": normalized_source_id,
        "period": period,
        "reason": normalized_reason,
        "source_url": source_url,
        "evidence_statement": normalized_statement,
    }


def parse_table1_workbook(
    document_bytes: bytes,
    *,
    extension: str,
    period: str,
) -> dict[str, Any]:
    """Parse one retained XLS/XLSX workbook document by semantic labels."""
    if not isinstance(document_bytes, bytes) or not document_bytes:
        raise CpiOfficialTruthError("workbook document must be non-empty bytes")
    normalized_extension = str(extension).lower()
    rows, sheet_name = _workbook_rows(document_bytes, normalized_extension)
    parsed = parse_table1_rows(rows, period=period)
    parsed["sheet"] = sheet_name
    return parsed


def parse_table1_rows(
    rows: list[list[Any]],
    *,
    period: str,
) -> dict[str, Any]:
    """Resolve headline/core CPI from a Table 1 cell matrix without coordinates."""
    if not _PERIOD.fullmatch(period):
        raise CpiOfficialTruthError("period must be YYYY-MM")
    if not isinstance(rows, list) or not rows:
        raise _ParseUnavailable("table1_empty")

    headline_cell = _unique_label_cell(rows, "all items")
    core_cell = _unique_label_cell(rows, "all items less food and energy")
    first_data_row = min(headline_cell[0], core_cell[0])
    max_columns = max((len(row) for row in rows[: first_data_row + 1]), default=0)
    headers = {
        column: _column_header(rows, column, first_data_row)
        for column in range(max_columns)
    }

    mom_candidates = [
        column
        for column, header in headers.items()
        if "seasonally adjusted percent change" in _normalize(header)
        and _header_matches_mom(header, period)
    ]
    if not mom_candidates:
        raise _ParseUnavailable("current_month_sa_mom_header_missing")
    if len(mom_candidates) != 1:
        raise _ParseUnavailable("current_month_sa_mom_header_ambiguous")
    mom_column = mom_candidates[0]

    yoy_candidates = [
        column
        for column, header in headers.items()
        if "unadjusted percent change" in _normalize(header)
        and _header_matches_yoy(header, period)
    ]
    yoy_column = yoy_candidates[0] if len(yoy_candidates) == 1 else None
    ri_candidates = [
        column
        for column, header in headers.items()
        if "relative importance" in _normalize(header)
    ]
    ri_column = ri_candidates[0] if len(ri_candidates) == 1 else None

    gaps: list[str] = []
    if yoy_column is None:
        gaps.append(
            "yoy_header_missing" if not yoy_candidates else "yoy_header_ambiguous"
        )
    if ri_column is None:
        gaps.append(
            "relative_importance_header_missing"
            if not ri_candidates
            else "relative_importance_header_ambiguous"
        )

    targets = []
    target_specs = (
        (headline_cell, "cpi_headline", "cpi_headline_mom", "All items"),
        (
            core_cell,
            "cpi_core",
            "cpi_core_mom",
            "All items less food and energy",
        ),
    )
    for (row_index, _label_column), release, metric_id, label in target_specs:
        mom = _required_number(
            rows, row_index, mom_column, "current_month_sa_mom_value"
        )
        yoy = _optional_number(rows, row_index, yoy_column)
        relative_importance = _optional_number(rows, row_index, ri_column)
        targets.append(
            {
                "release": release,
                "metric_id": metric_id,
                "exact_target_id": metric_id + "_archived_release_edition",
                "label": label,
                "period": period,
                "sequence": ARCHIVE_SEQUENCE,
                "first_print_status": FIRST_PRINT_STATUS,
                "mom": mom,
                "yoy": yoy,
                "relative_importance": relative_importance,
                "unit": "percent",
                "published_precision": 1,
                "actual_basis": ARCHIVED_TABLE1_ACTUAL_BASIS,
                "mom_cell": _cell_name(row_index, mom_column),
                "yoy_cell": _cell_name(row_index, yoy_column),
                "relative_importance_cell": _cell_name(row_index, ri_column),
            }
        )

    return {
        "status": "ok",
        "reason": None,
        "targets": targets,
        "gaps": gaps,
        "selection": {
            "mom_header": headers[mom_column],
            "mom_column": _column_name(mom_column),
            "yoy_column": _column_name(yoy_column),
            "relative_importance_column": _column_name(ri_column),
        },
    }


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Return the canonical bytes used for deterministic receipts and storage."""
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _validate_member(member: str | None) -> str:
    if not isinstance(member, str) or not member:
        raise CpiOfficialTruthError("annual ZIP source requires an exact member")
    if "\\" in member:
        raise CpiOfficialTruthError("archive member must use POSIX separators")
    path = PurePosixPath(member)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.suffix.lower()
        not in {
            ".xls",
            ".xlsx",
        }
    ):
        raise CpiOfficialTruthError("archive member is unsafe or unsupported")
    return member


def _extract_document(source_bytes: bytes, member: str | None) -> bytes:
    if member is None:
        if len(source_bytes) > _MAX_DOCUMENT_BYTES:
            raise _ParseUnavailable("workbook_exceeds_size_limit")
        return source_bytes
    exact_member = _validate_member(member)
    try:
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
            if len(archive.infolist()) > _MAX_ZIP_ENTRIES:
                raise _ParseUnavailable("archive_entry_count_exceeds_limit")
            info = archive.getinfo(exact_member)
            if info.is_dir() or info.file_size <= 0:
                raise _ParseUnavailable("archive_member_empty")
            if info.file_size > _MAX_DOCUMENT_BYTES:
                raise _ParseUnavailable("archive_member_exceeds_size_limit")
            body = archive.read(info)
    except KeyError as exc:
        raise _ParseUnavailable("archive_member_missing") from exc
    except zipfile.BadZipFile as exc:
        raise _ParseUnavailable("archive_invalid_zip") from exc
    if len(body) != info.file_size:
        raise _ParseUnavailable("archive_member_length_mismatch")
    return body


def _workbook_rows(body: bytes, extension: str) -> tuple[list[list[Any]], str]:
    if extension == ".xlsx":
        return _xlsx_rows(body)
    if extension == ".xls":
        return _xls_rows(body)
    raise _ParseUnavailable("workbook_format_unsupported")


def _xlsx_rows(body: bytes) -> tuple[list[list[Any]], str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise _ParseUnavailable("xlsx_invalid_zip") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ZIP_ENTRIES:
            raise _ParseUnavailable("xlsx_entry_count_exceeds_limit")
        names = {info.filename for info in infos}
        sheets = sorted(
            name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        if not sheets:
            raise _ParseUnavailable("xlsx_worksheet_missing")
        shared = (
            _xlsx_shared_strings(archive) if "xl/sharedStrings.xml" in names else []
        )
        for sheet_name in sheets:
            rows = _xlsx_sheet_rows(
                _read_bounded_xlsx_xml(archive, sheet_name),
                shared,
            )
            if _has_target_labels(rows):
                return rows, sheet_name
    raise _ParseUnavailable("table1_target_rows_missing")


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(
            _read_bounded_xlsx_xml(archive, "xl/sharedStrings.xml")
        )
    except ElementTree.ParseError as exc:
        raise _ParseUnavailable("xlsx_shared_strings_invalid") from exc
    return [
        "".join(node.text or "" for node in item.iter(_XML_NS + "t"))
        for item in root.findall(_XML_NS + "si")
    ]


def _xlsx_sheet_rows(body: bytes, shared: list[str]) -> list[list[Any]]:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise _ParseUnavailable("xlsx_worksheet_invalid") from exc
    cells: dict[tuple[int, int], Any] = {}
    maximum_row = maximum_column = 0
    for cell in root.iter(_XML_NS + "c"):
        ref = str(cell.attrib.get("r") or "")
        match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
        if not match:
            continue
        column = _column_index(match.group(1))
        row = int(match.group(2)) - 1
        if row >= _MAX_WORKSHEET_ROWS or column >= _MAX_WORKSHEET_COLUMNS:
            raise _ParseUnavailable("xlsx_dimensions_exceed_limit")
        value = _xlsx_cell_value(cell, shared)
        if value not in (None, ""):
            cells[(row, column)] = value
        maximum_row = max(maximum_row, row)
        maximum_column = max(maximum_column, column)

    for merged in root.iter(_XML_NS + "mergeCell"):
        ref = str(merged.attrib.get("ref") or "")
        match = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", ref)
        if not match:
            continue
        start_column, start_row = _column_index(match.group(1)), int(match.group(2)) - 1
        end_column, end_row = _column_index(match.group(3)), int(match.group(4)) - 1
        if (
            start_row < 0
            or start_column < 0
            or end_row < start_row
            or end_column < start_column
            or end_row >= _MAX_WORKSHEET_ROWS
            or end_column >= _MAX_WORKSHEET_COLUMNS
        ):
            raise _ParseUnavailable("xlsx_merged_dimensions_exceed_limit")
        value = cells.get((start_row, start_column))
        if value in (None, ""):
            continue
        for row in range(start_row, min(end_row + 1, _MAX_WORKSHEET_ROWS)):
            for column in range(
                start_column, min(end_column + 1, _MAX_WORKSHEET_COLUMNS)
            ):
                cells.setdefault((row, column), value)
        maximum_row = max(maximum_row, end_row)
        maximum_column = max(maximum_column, end_column)

    rows: list[list[Any]] = []
    for row in range(maximum_row + 1):
        rows.append([cells.get((row, column)) for column in range(maximum_column + 1)])
    return rows


def _read_bounded_xlsx_xml(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise _ParseUnavailable("xlsx_xml_entry_missing") from exc
    if info.is_dir() or info.file_size > _MAX_XLSX_XML_ENTRY_BYTES:
        raise _ParseUnavailable("xlsx_xml_entry_exceeds_size_limit")
    body = archive.read(info)
    if len(body) != info.file_size:
        raise _ParseUnavailable("xlsx_xml_entry_length_mismatch")
    return body


def _xlsx_cell_value(cell: ElementTree.Element, shared: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(_XML_NS + "is")
        return (
            "".join(node.text or "" for node in inline.iter(_XML_NS + "t"))
            if inline is not None
            else None
        )
    value_node = cell.find(_XML_NS + "v")
    raw = value_node.text if value_node is not None else None
    if raw is None:
        return None
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (IndexError, ValueError) as exc:
            raise _ParseUnavailable("xlsx_shared_string_reference_invalid") from exc
    if cell_type in {"str", "d"}:
        return raw
    try:
        return float(raw)
    except ValueError:
        return raw


def _xls_rows(body: bytes) -> tuple[list[list[Any]], str]:
    try:
        import xlrd  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise _ParseUnavailable("xls_parser_dependency_missing") from exc
    try:
        book = xlrd.open_workbook(file_contents=body, formatting_info=True)
    except Exception as exc:  # xlrd exposes multiple parse exception classes
        raise _ParseUnavailable("xls_workbook_invalid") from exc
    for sheet in book.sheets():
        if sheet.nrows > _MAX_WORKSHEET_ROWS or sheet.ncols > _MAX_WORKSHEET_COLUMNS:
            raise _ParseUnavailable("xls_dimensions_exceed_limit")
        rows = [sheet.row_values(row) for row in range(sheet.nrows)]
        for start_row, end_row, start_column, end_column in sheet.merged_cells:
            value = rows[start_row][start_column]
            for row in range(start_row, end_row):
                for column in range(start_column, end_column):
                    if rows[row][column] in (None, ""):
                        rows[row][column] = value
        if _has_target_labels(rows):
            return rows, sheet.name
    raise _ParseUnavailable("table1_target_rows_missing")


def _has_target_labels(rows: list[list[Any]]) -> bool:
    labels = {
        _normalize(value) for row in rows for value in row if value not in (None, "")
    }
    return {"all items", "all items less food and energy"}.issubset(labels)


def _unique_label_cell(rows: list[list[Any]], label: str) -> tuple[int, int]:
    matches = [
        (row_index, column_index)
        for row_index, row in enumerate(rows)
        for column_index, value in enumerate(row)
        if _normalize(value) == label
    ]
    if not matches:
        raise _ParseUnavailable(label.replace(" ", "_") + "_row_missing")
    if len(matches) != 1:
        raise _ParseUnavailable(label.replace(" ", "_") + "_row_ambiguous")
    return matches[0]


def _column_header(rows: list[list[Any]], column: int, before_row: int) -> str:
    parts = []
    for row in rows[:before_row]:
        if column < len(row) and row[column] not in (None, ""):
            text = " ".join(str(row[column]).split())
            if text and (not parts or parts[-1] != text):
                parts.append(text)
    return " | ".join(parts)


def _header_matches_mom(header: str, period: str) -> bool:
    target_year, target_month = (int(part) for part in period.split("-"))
    prior_month = 12 if target_month == 1 else target_month - 1
    prior_year = target_year - 1 if target_month == 1 else target_year
    pairs = _month_year_pairs(header)
    return pairs[-2:] == [
        (prior_year, prior_month),
        (target_year, target_month),
    ]


def _header_matches_yoy(header: str, period: str) -> bool:
    target_year, target_month = (int(part) for part in period.split("-"))
    pairs = _month_year_pairs(header)
    return pairs[-2:] == [
        (target_year - 1, target_month),
        (target_year, target_month),
    ]


def _month_year_pairs(header: str) -> list[tuple[int, int]]:
    normalized = _normalize(header)
    month_tokens = {
        token: month
        for month, name in enumerate(_MONTHS, start=1)
        for token in (name, name[:3])
    }
    token_pattern = "|".join(sorted(month_tokens, key=len, reverse=True))
    return [
        (int(match.group("year")), month_tokens[match.group("month")])
        for match in re.finditer(
            rf"\b(?P<month>{token_pattern})\s+(?P<year>(?:19|20)\d{{2}})\b",
            normalized,
        )
    ]


def _required_number(
    rows: list[list[Any]], row: int, column: int, reason: str
) -> float:
    value = _optional_number(rows, row, column)
    if value is None:
        raise _ParseUnavailable(reason + "_missing")
    return value


def _optional_number(
    rows: list[list[Any]], row: int, column: int | None
) -> float | None:
    if column is None or row >= len(rows) or column >= len(rows[row]):
        return None
    raw = rows[row][column]
    if raw in (None, "") or isinstance(raw, bool):
        return None
    try:
        value = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _normalize(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _normalize_evidence_text(value: str) -> str:
    text = str(value).replace("\u2013", "-").replace("\u2014", "-").lower()
    return " ".join(text.split())


def _column_index(name: str) -> int:
    value = 0
    for character in name:
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _column_name(column: int | None) -> str | None:
    if column is None:
        return None
    value = column + 1
    out = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        out = chr(ord("A") + remainder) + out
    return out


def _cell_name(row: int, column: int | None) -> str | None:
    name = _column_name(column)
    return f"{name}{row + 1}" if name else None


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _receipt_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return "cpi_official_truth:" + digest[:32]


__all__ = [
    "ARCHIVED_TABLE1_ACTUAL_BASIS",
    "ARCHIVE_NONPUBLICATION_ACTUAL_BASIS",
    "ARCHIVE_SEQUENCE",
    "BLS_PUBLISHER",
    "FIRST_PRINT_STATUS",
    "INTEGRITY_PROFILE",
    "NONPUBLICATION_INTEGRITY_PROFILE",
    "PARSER_NAME",
    "PARSER_VERSION",
    "SCHEMA_VERSION",
    "USER_AGENT",
    "CpiOfficialTruthBuild",
    "CpiOfficialTruthError",
    "CpiSourceSpec",
    "build_cpi_not_published_truth",
    "build_cpi_official_truth",
    "canonical_json_bytes",
    "parse_table1_rows",
    "parse_table1_workbook",
    "rebuild_cpi_official_truth_receipt",
    "validate_nonpublication_spec",
    "validate_source_spec",
]
