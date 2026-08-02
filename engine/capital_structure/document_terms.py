"""Precision-first, document-row-scoped registration-fee-table observations.

This is deliberately narrower than an instrument or issuer-state engine.  It
reads the retained *complete submission* identified by a source manifest,
locates an exact primary or ``EX-FILING FEES`` child table inside those immutable
bytes, and emits only row/security-scoped directly displayed cells. It never totals rows, infers
remaining capacity, treats a registration as an active instrument, or creates
a dilution/risk/probability claim.

The complete submission is the canonical parser path. Wave 1 does not retain a
separate ``EX-FILING FEES`` manifest, but the child remains inside the verified
submission bytes and retains exact child/table/row/cell provenance here.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any

from engine.capital_structure.event_spine import make_stable_span
from engine.capital_structure.source_identity import (
    validate_manifest_content_binding,
    validate_manifest_ledger,
    validate_manifest_retained_bytes_binding,
)


DOCUMENT_TERM_SCHEMA = "capital_structure.document_term_observation.v1"
PARSER_VERSION = "capital-structure-document-terms/1.1.0"

# The names mirror direct SEC table headers.  Their economic type/unit is row
# dependent: an "amount to be registered" can be shares, units, securities, or
# debt principal.  Never attach a generic unit before reading the security row.
TERM_NAMES = (
    "amount_to_be_registered",
    "proposed_maximum_offering_price_per_unit",
    "proposed_maximum_aggregate_offering_price",
    "registration_fee",
    "filing_fee_rate",
)

REGISTRATION_FEE_FORMS = frozenset({
    "S-1", "S-1/A", "F-1", "F-1/A", "S-3", "S-3/A", "S-3ASR",
    "F-3", "F-3/A", "F-3ASR", "F-10", "F-10/A", "1-A", "1-A/A", "1-A POS",
})

_DOCUMENT_RE = re.compile(br"<DOCUMENT>(.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)
_TEXT_RE = re.compile(br"<TEXT>\s*(.*?)(?:</TEXT>|$)", re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(br"<table\b[^>]*>.*?</table\s*>", re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(br"<tr\b[^>]*>.*?</tr\s*>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(
    br"<(td|th)\b([^>]*)>(.*?)</\1\s*>", re.IGNORECASE | re.DOTALL,
)
_COLSPAN_RE = re.compile(br"\bcolspan\s*=\s*[\"']?\s*(\d+)", re.IGNORECASE)
_TYPE_RE = re.compile(br"<TYPE>\s*([^\r\n<]+)", re.IGNORECASE)
_SEQUENCE_RE = re.compile(br"<SEQUENCE>\s*([^\r\n<]+)", re.IGNORECASE)
_FILENAME_RE = re.compile(br"<FILENAME>\s*([^\r\n<]+)", re.IGNORECASE)
_NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
_SIMPLE_NUMBER_RE = re.compile(r"^\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)$")
_DENOMINATED_RATE_RE = re.compile(
    r"^\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s+per\s+"
    r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)$",
    re.IGNORECASE,
)
_BYTE_LOCATOR_RE = re.compile(r"bytes:(\d+)-(\d+)$")


class DocumentTermCompileDegraded(RuntimeError):
    """One retained source object could not be read exactly; do not publish a partial run."""

    def __init__(self, failures: Sequence[Mapping[str, Any]]):
        self.failures = [dict(item) for item in failures]
        super().__init__(
            "capital-structure document-term compile degraded with "
            f"{len(self.failures)} source failure(s)"
        )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _digest_id(prefix: str, body: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]


def _parse_time(value: Any, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: Any, field: str) -> str:
    return _parse_time(value, field).isoformat().replace("+00:00", "Z")


def _decode(raw: bytes) -> str:
    """Decode only for structural parsing; all evidence hashes retain source bytes."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _tag_value(block: bytes, pattern: re.Pattern[bytes]) -> str | None:
    match = pattern.search(block)
    if not match:
        return None
    return _decode(match.group(1)).strip() or None


def _normalized_form(value: str) -> str:
    return " ".join(value.upper().split())


@dataclass(frozen=True)
class SubmissionDocument:
    document_type: str
    sequence: str | None
    filename: str | None
    text: bytes
    text_start: int
    text_end: int


def _eligible_documents(raw: bytes, form: str) -> list[SubmissionDocument]:
    """Return exact primary and EX-FILING FEES SGML TEXT segments.

    Modern EDGAR filings commonly put the structured fee table in a dedicated
    ``EX-FILING FEES`` child.  Because the retained complete submission contains
    every child, no additional network/source-manifest dependency is required.
    """
    wanted = _normalized_form(form)
    candidates: list[SubmissionDocument] = []
    for block_match in _DOCUMENT_RE.finditer(raw):
        block = block_match.group(1)
        document_type = _tag_value(block, _TYPE_RE)
        if not document_type:
            continue
        normalized = _normalized_form(document_type)
        if normalized not in {wanted, "EX-FILING FEES"}:
            continue
        text_match = _TEXT_RE.search(block)
        if not text_match:
            continue
        absolute_start = block_match.start(1) + text_match.start(1)
        candidates.append(SubmissionDocument(
            document_type=normalized,
            sequence=_tag_value(block, _SEQUENCE_RE),
            filename=_tag_value(block, _FILENAME_RE),
            text=text_match.group(1),
            text_start=absolute_start,
            text_end=absolute_start + len(text_match.group(1)),
        ))
    return candidates


class _CellText(HTMLParser):
    """Decode one cell while excluding explicit superscript footnote markers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "sup":
            self._ignored_depth += 1
        elif lowered == "br" and not self._ignored_depth:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "sup" and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def _label(value: str) -> str:
    cleaned = _clean_text(value).lower()
    cleaned = re.sub(r"\(\s*\d+\s*\)", "", cleaned)
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def _term_for_header(value: str) -> str | None:
    normalized = _label(value)
    if "amount to be registered" in normalized:
        return "amount_to_be_registered"
    if "proposed maximum offering price per unit" in normalized:
        return "proposed_maximum_offering_price_per_unit"
    if "proposed maximum aggregate offering price" in normalized:
        return "proposed_maximum_aggregate_offering_price"
    if "amount of registration fee" in normalized or "amount of filing fee" in normalized:
        return "registration_fee"
    if normalized == "fee rate" or "filing fee rate" in normalized:
        return "filing_fee_rate"
    return None


@dataclass(frozen=True)
class TableCell:
    raw: bytes
    text: str
    start: int
    end: int
    column_start: int
    column_span: int


@dataclass(frozen=True)
class TableRow:
    raw: bytes
    start: int
    end: int
    cells: tuple[TableCell, ...]

    def cell_at(self, column: int) -> TableCell | None:
        for cell in self.cells:
            if cell.column_start <= column < cell.column_start + cell.column_span:
                return cell
        return None


@dataclass(frozen=True)
class FeeTable:
    raw: bytes
    start: int
    end: int
    document: SubmissionDocument
    table_index: int
    rows: tuple[TableRow, ...]
    header_index: int
    columns: Mapping[str, int]
    security_column: int | None
    duplicate_headers: tuple[str, ...]


def _cell_text(raw_inner: bytes) -> str:
    parser = _CellText()
    try:
        parser.feed(_decode(raw_inner))
        parser.close()
    except Exception:  # noqa: BLE001 - malformed public HTML becomes a safe empty cell
        return ""
    return _clean_text(parser.text())


def _table_rows(table_raw: bytes, absolute_start: int) -> tuple[TableRow, ...]:
    rows: list[TableRow] = []
    for row_match in _ROW_RE.finditer(table_raw):
        row_raw = row_match.group(0)
        row_start = absolute_start + row_match.start()
        cells: list[TableCell] = []
        column = 0
        for cell_match in _CELL_RE.finditer(row_raw):
            attrs = cell_match.group(2)
            colspan_match = _COLSPAN_RE.search(attrs)
            span = max(1, int(colspan_match.group(1))) if colspan_match else 1
            cell_start = row_start + cell_match.start()
            cell_raw = cell_match.group(0)
            cells.append(TableCell(
                raw=cell_raw,
                text=_cell_text(cell_match.group(3)),
                start=cell_start,
                end=cell_start + len(cell_raw),
                column_start=column,
                column_span=span,
            ))
            column += span
        if cells:
            rows.append(TableRow(
                raw=row_raw, start=row_start, end=row_start + len(row_raw),
                cells=tuple(cells),
            ))
    return tuple(rows)


def _security_header(value: str) -> bool:
    normalized = _label(value)
    return (
        ("title of each class" in normalized and "securit" in normalized)
        or normalized in {"security type", "title of securities", "security class title"}
    )


def _parse_fee_tables(document: SubmissionDocument, start_index: int) -> list[FeeTable]:
    """Find only tables whose actual cells name direct SEC fee-table fields."""
    candidates: list[FeeTable] = []
    for local_index, match in enumerate(_TABLE_RE.finditer(document.text)):
        absolute_start = document.text_start + match.start()
        rows = _table_rows(match.group(0), absolute_start)
        header_index = -1
        columns: dict[str, int] = {}
        security_column: int | None = None
        duplicate_headers: set[str] = set()
        for index, row in enumerate(rows):
            found: dict[str, int] = {}
            for cell in row.cells:
                name = _term_for_header(cell.text)
                if name is not None:
                    if name in found:
                        duplicate_headers.add(name)
                    else:
                        found[name] = cell.column_start
                if _security_header(cell.text):
                    if security_column is not None:
                        duplicate_headers.add("security_title")
                    else:
                        security_column = cell.column_start
            if len(found) >= 2:
                header_index = index
                columns = found
                break
        if header_index >= 0:
            candidates.append(FeeTable(
                raw=match.group(0), start=absolute_start,
                end=document.text_start + match.end(), document=document,
                table_index=start_index + local_index, rows=rows,
                header_index=header_index, columns=columns,
                security_column=security_column,
                duplicate_headers=tuple(sorted(duplicate_headers)),
            ))
    return candidates


@dataclass(frozen=True)
class ParsedNumber:
    disposition: str
    reason: str
    value: str | None
    scale: str | None


def _decimal_string(value: str) -> str | None:
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _strip_footnote_markers(value: str) -> str:
    cleaned = value.strip()
    marker = r"(?:\(\s*\d+\s*\)|\[\s*\d+\s*\]|[*†‡]+)"
    prior = None
    while prior != cleaned:
        prior = cleaned
        cleaned = re.sub(rf"^{marker}\s*", "", cleaned)
        cleaned = re.sub(rf"\s*{marker}$", "", cleaned)
    return cleaned.strip()


def _parse_number(raw_text: str, *, allow_denominated_rate: bool = False) -> ParsedNumber:
    """Parse a complete cell, never the first convenient numeric substring."""
    visible = _clean_text(raw_text)
    if not visible or visible.lower() in {"n/a", "na", "not applicable", "--", "—", "-"}:
        return ParsedNumber("unavailable", "header_without_direct_value", None, None)
    cleaned = _strip_footnote_markers(visible)
    if allow_denominated_rate:
        rate = _DENOMINATED_RATE_RE.fullmatch(cleaned)
        if rate:
            numerator = _decimal_string(rate.group(1))
            denominator = _decimal_string(rate.group(2))
            if numerator is not None and denominator not in {None, "0"}:
                return ParsedNumber("observed", "direct_table_value", numerator, denominator)
    simple = _SIMPLE_NUMBER_RE.fullmatch(cleaned)
    if simple:
        parsed = _decimal_string(simple.group(1))
        if parsed is not None:
            return ParsedNumber("observed", "direct_table_value", parsed, "1")
    tokens = _NUMBER_TOKEN_RE.findall(cleaned)
    if len(tokens) > 1:
        return ParsedNumber("ambiguous", "multiple_numeric_tokens", None, None)
    return ParsedNumber("ambiguous", "unsupported_dimensional_value", None, None)


def _root_span(manifest: Mapping[str, Any]) -> dict[str, str]:
    document = manifest.get("document") or {}
    manifest_id = str(manifest["manifest_id"])
    digest = str(document.get("content_sha256") or "")
    byte_length = int(document.get("byte_length") or 0)
    for raw_span in manifest.get("spans") or []:
        if not isinstance(raw_span, Mapping):
            continue
        if (
            str(raw_span.get("text_sha256") or "").lower() == digest.lower()
            and str(raw_span.get("locator_type") or "") == "document"
            and str(raw_span.get("locator") or "") == f"bytes:0-{byte_length}"
        ):
            return {
                "manifest_id": manifest_id,
                "span_id": str(raw_span["span_id"]),
                "locator_type": "document",
                "locator": str(raw_span["locator"]),
                "text_sha256": digest,
            }
    # The manifest contract normally makes this unreachable. Preserve a direct
    # deterministic fallback so the caller gets a clear contract failure later.
    return make_stable_span(
        manifest_id, b"", locator_type="document", locator=f"bytes:0-{byte_length}"
    )


def _child_locator(document: SubmissionDocument) -> str:
    return (
        f"type={document.document_type}:sequence={document.sequence or 'unknown'}:"
        f"filename={document.filename or 'unknown'}"
    )


def _table_span(manifest_id: str, table: FeeTable) -> dict[str, str]:
    return make_stable_span(
        manifest_id,
        table.raw,
        locator_type="table",
        locator=(
            f"complete_submission:{_child_locator(table.document)}:"
            f"table={table.table_index}:bytes:{table.start}-{table.end}"
        ),
    )


def _row_span(manifest_id: str, table: FeeTable, row: TableRow, row_index: int) -> dict[str, str]:
    return make_stable_span(
        manifest_id, row.raw, locator_type="text_range",
        locator=(
            f"complete_submission:{_child_locator(table.document)}:table={table.table_index}:"
            f"row={row_index}:bytes:{row.start}-{row.end}"
        ),
    )


def _cell_span(
    manifest_id: str, table: FeeTable, row: TableRow, row_index: int,
    cell: TableCell, role: str,
) -> dict[str, str]:
    return make_stable_span(
        manifest_id, cell.raw, locator_type="text_range",
        locator=(
            f"complete_submission:{_child_locator(table.document)}:table={table.table_index}:"
            f"row={row_index}:cell={cell.column_start}:role={role}:bytes:{cell.start}-{cell.end}"
        ),
    )


def _unique_spans(spans: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for span in spans:
        span_id = str(span.get("span_id") or "")
        if span_id and span_id not in seen:
            seen.add(span_id)
            output.append(dict(span))
    return output


def _document_evidence(
    manifest: Mapping[str, Any], spans: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    document = manifest.get("document") or {}
    rights = manifest.get("rights") or {}
    privacy = manifest.get("privacy") or {}
    return {
        "source_manifest_id": str(manifest["manifest_id"]),
        "source_document_sha256": str(document["content_sha256"]),
        "rights_class": str(rights.get("redistribution_class") or "unknown"),
        "privacy_classification": str(privacy.get("classification") or "unknown"),
        "contains_personal_data": bool(privacy.get("contains_personal_data")),
        "publication": {
            "disposition": "public_fact_only",
            "excerpt_char_count": 0,
            "personal_data_redacted": False,
        },
        "spans": _unique_spans(spans),
    }


def _empty_value() -> dict[str, Any]:
    return {"raw_text": None, "value": None, "unit": None, "currency": None, "scale": None}


def _direct_value(
    raw_text: str, value: str, unit: str, currency: str | None, scale: str,
) -> dict[str, Any]:
    return {
        "raw_text": raw_text[:500], "value": value, "unit": unit,
        "currency": currency, "scale": scale,
    }


def _row_id(manifest_id: str, table: FeeTable, row: TableRow) -> str:
    return _digest_id(
        "fee-row:cs:",
        {"manifest_id": manifest_id, "table_start": table.start, "row_start": row.start, "row_end": row.end},
    )


def _logical_observation_id(manifest_id: str, row_id: str | None, name: str) -> str:
    return _digest_id(
        "document-term-slot:cs:",
        {"manifest_id": manifest_id, "row_id": row_id or "document", "term": name},
    )


def _classify_security(title: str) -> str:
    normalized = _label(title)
    if not normalized:
        return "unknown"
    if "preferred" in normalized and any(token in normalized for token in ("stock", "share")):
        return "preferred_stock"
    if any(token in normalized for token in ("common stock", "ordinary share", "common share")):
        return "common_stock"
    if any(token in normalized for token in ("debt", "note", "bond", "debenture")):
        return "debt"
    if "unit" in normalized:
        return "units"
    if any(token in normalized for token in ("warrant", "right", "option")):
        return "warrants"
    return "other"


def _term_semantics(
    name: str, security_classification: str, *, rate_scale: str | None = None,
) -> tuple[str, str | None, str | None]:
    if name == "amount_to_be_registered":
        if security_classification in {"common_stock", "preferred_stock"}:
            return "share_count", "shares", None
        if security_classification == "debt":
            return "principal_amount", "USD", "USD"
        if security_classification == "units":
            return "quantity", "units", None
        if security_classification == "warrants":
            return "quantity", "securities", None
        return "quantity", None, None
    if name == "proposed_maximum_offering_price_per_unit":
        if security_classification in {"common_stock", "preferred_stock"}:
            return "price", "USD/share", "USD"
        if security_classification == "units":
            return "price", "USD/unit", "USD"
        if security_classification == "warrants":
            return "price", "USD/security", "USD"
        return "price", None, None
    if name in {"proposed_maximum_aggregate_offering_price", "registration_fee"}:
        return "amount", "USD", "USD"
    if name == "filing_fee_rate":
        if rate_scale not in {None, "1"}:
            return "rate", "USD_per_USD", "USD"
        return "rate", "rate", None
    raise ValueError(f"unsupported direct fee-table term {name!r}")


def _document_term_type(name: str) -> str:
    return {
        "amount_to_be_registered": "quantity",
        "proposed_maximum_offering_price_per_unit": "price",
        "proposed_maximum_aggregate_offering_price": "amount",
        "registration_fee": "amount",
        "filing_fee_rate": "rate",
    }[name]


def _empty_security() -> dict[str, Any]:
    return {
        "row_id": None, "table_index": None, "row_index": None,
        "title_raw": None, "title_normalized": None, "classification": "unknown",
    }


def _security_for_row(
    manifest_id: str, table: FeeTable, row: TableRow, row_index: int,
) -> tuple[dict[str, Any], TableCell | None]:
    title_cell = row.cell_at(table.security_column) if table.security_column is not None else None
    title = _clean_text(title_cell.text) if title_cell is not None else ""
    classification = _classify_security(title)
    return ({
        "row_id": _row_id(manifest_id, table, row),
        "table_index": table.table_index,
        "row_index": row_index,
        "title_raw": title or None,
        "title_normalized": _label(title) or None,
        "classification": classification,
    }, title_cell)


def _base_record(
    manifest: Mapping[str, Any],
    name: str,
    *,
    disposition: str,
    reason: str,
    reported: Mapping[str, Any],
    evidence: Mapping[str, Any],
    source_available_at: str,
    term_type: str,
    security: Mapping[str, Any] | None = None,
    child_document: SubmissionDocument | None = None,
) -> dict[str, Any]:
    filing = manifest.get("filing") or {}
    document = manifest.get("document") or {}
    parser_deferred = reason in {"manifest_parser_not_eligible", "manifest_corruption_not_clean"}
    needs_review = disposition == "ambiguous" or parser_deferred
    security_record = dict(security or _empty_security())
    row_id = security_record.get("row_id")
    return {
        "schema": DOCUMENT_TERM_SCHEMA,
        "logical_observation_id": _logical_observation_id(str(manifest["manifest_id"]), row_id, name),
        "issuer_id": str((manifest.get("issuer") or {})["issuer_id"]),
        "filing": {
            "accession": str(filing["accession"]), "form": str(filing["form"]),
            "filing_date": filing.get("filing_date"), "accepted_at": filing.get("accepted_at"),
        },
        "document": {
            "source_manifest_id": str(manifest["manifest_id"]),
            "source_id": str(manifest["source_id"]), "document_role": "complete_submission",
            "canonical_url": str(document["canonical_url"]),
            "content_sha256": str(document["content_sha256"]).lower(),
            "child_document_type": child_document.document_type if child_document else None,
            "child_sequence": child_document.sequence if child_document else None,
            "child_filename": child_document.filename if child_document else None,
            "child_text_start": child_document.text_start if child_document else None,
            "child_text_end": child_document.text_end if child_document else None,
        },
        "security": security_record,
        "term": {"name": name, "term_type": term_type, "scope": "registration_fee_table_row"},
        "state": {"disposition": disposition, "reason": reason},
        "reported": dict(reported),
        # This first slice is a unit-preserving transcription, not a conversion.
        "normalized": dict(reported),
        "evidence": dict(evidence),
        "extraction": {
            "method": "deferred" if parser_deferred else "deterministic",
            "parser_version": PARSER_VERSION,
            "review_status": "deferred" if needs_review else "unreviewed",
        },
        "relationships": {"amends": [], "supersedes": [], "contradiction_ids": []},
        "point_in_time": {"source_available_at": source_available_at},
    }


def _records_for_manifest(
    manifest: Mapping[str, Any], raw: bytes | None,
) -> list[dict[str, Any]]:
    """Build row/security-scoped direct observations for one complete submission."""
    source_available_at = _iso((manifest.get("retrieval") or {}).get("first_seen_at"), "retrieval.first_seen_at")
    root = _root_span(manifest)
    parser = manifest.get("parser") or {}
    if str(parser.get("corruption_state") or "") != "clean":
        reason = "manifest_corruption_not_clean"
        return [
            _base_record(manifest, name, disposition="unavailable", reason=reason,
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, [root]), source_available_at=source_available_at)
            for name in TERM_NAMES
        ]
    if str(parser.get("eligibility") or "") != "eligible":
        reason = "manifest_parser_not_eligible"
        return [
            _base_record(manifest, name, disposition="unavailable", reason=reason,
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, [root]), source_available_at=source_available_at)
            for name in TERM_NAMES
        ]
    assert raw is not None
    documents = _eligible_documents(raw, str((manifest.get("filing") or {}).get("form") or ""))
    if not documents:
        reason = "eligible_document_not_found"
        return [
            _base_record(manifest, name, disposition="unavailable", reason=reason,
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, [root]), source_available_at=source_available_at)
            for name in TERM_NAMES
        ]
    tables: list[FeeTable] = []
    table_cursor = 0
    for child in documents:
        tables.extend(_parse_fee_tables(child, table_cursor))
        table_cursor += len(_TABLE_RE.findall(child.text))
    if not tables:
        reason = "fee_table_not_detected"
        child = documents[0] if len(documents) == 1 else None
        return [
            _base_record(manifest, name, disposition="unavailable", reason=reason,
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, [root]), source_available_at=source_available_at,
                         child_document=child)
            for name in TERM_NAMES
        ]
    spans = [_table_span(str(manifest["manifest_id"]), table) for table in tables]
    if len(tables) != 1:
        return [
            _base_record(manifest, name, disposition="ambiguous", reason="multiple_fee_tables_detected",
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, spans), source_available_at=source_available_at)
            for name in TERM_NAMES
        ]

    table = tables[0]
    if table.duplicate_headers:
        return [
            _base_record(
                manifest, name, disposition="ambiguous", reason="duplicate_header_mapping",
                reported=_empty_value(), term_type=_document_term_type(name),
                evidence=_document_evidence(manifest, spans), source_available_at=source_available_at,
                child_document=table.document,
            )
            for name in TERM_NAMES
        ]
    if table.security_column is None:
        return [
            _base_record(
                manifest, name, disposition="ambiguous", reason="unit_semantics_ambiguous",
                reported=_empty_value(), term_type=_document_term_type(name),
                evidence=_document_evidence(manifest, spans), source_available_at=source_available_at,
                child_document=table.document,
            )
            for name in TERM_NAMES
        ]
    records: list[dict[str, Any]] = []
    data_rows = [
        (row_index, row)
        for row_index, row in enumerate(table.rows[table.header_index + 1:], start=table.header_index + 1)
        if any(
            (cell := row.cell_at(column)) is not None and bool(_clean_text(cell.text))
            for column in table.columns.values()
        )
    ]
    if not data_rows:
        return [
            _base_record(
                manifest, name, disposition="unavailable", reason="header_without_direct_value",
                reported=_empty_value(), term_type=_document_term_type(name),
                evidence=_document_evidence(manifest, spans), source_available_at=source_available_at,
                child_document=table.document,
            )
            for name in TERM_NAMES
        ]

    manifest_id = str(manifest["manifest_id"])
    table_span = spans[0]
    for row_index, row in data_rows:
        security, title_cell = _security_for_row(manifest_id, table, row, row_index)
        row_span = _row_span(manifest_id, table, row, row_index)
        base_spans: list[Mapping[str, Any]] = [table_span, row_span]
        if title_cell is not None:
            base_spans.append(_cell_span(manifest_id, table, row, row_index, title_cell, "security_title"))
        title_present = bool(security.get("title_raw"))
        classification = str(security["classification"])
        for name in TERM_NAMES:
            column = table.columns.get(name)
            cell = row.cell_at(column) if column is not None else None
            term_spans = list(base_spans)
            if cell is not None:
                term_spans.append(_cell_span(manifest_id, table, row, row_index, cell, name))
            parsed = _parse_number(
                cell.text if cell is not None else "",
                allow_denominated_rate=name == "filing_fee_rate",
            )
            term_type, unit, currency = _term_semantics(
                name, classification, rate_scale=parsed.scale,
            )
            disposition = parsed.disposition
            reason = parsed.reason
            if disposition == "observed" and (not title_present or unit is None):
                disposition = "ambiguous"
                reason = "unit_semantics_ambiguous"
            reported = (
                _direct_value(cell.text, str(parsed.value), str(unit), currency, str(parsed.scale))
                if disposition == "observed" and cell is not None and parsed.value is not None
                and parsed.scale is not None and unit is not None
                else _empty_value()
            )
            records.append(_base_record(
                manifest, name, disposition=disposition, reason=reason,
                reported=reported, term_type=term_type,
                evidence=_document_evidence(manifest, term_spans),
                source_available_at=source_available_at, security=security,
                child_document=table.document,
            ))
    return records


def _semantic_body(record: Mapping[str, Any]) -> dict[str, Any]:
    body = deepcopy(dict(record))
    body.pop("observation_id", None)
    body.pop("version", None)
    body.pop("point_in_time", None)
    relationships = dict(body.get("relationships") or {})
    relationships["supersedes"] = []
    body["relationships"] = relationships
    return body


def observation_id_for(record: Mapping[str, Any]) -> str:
    body = deepcopy(dict(record))
    body.pop("observation_id", None)
    return _digest_id("document-term:cs:", body)


def validate_observation_source_binding(
    record: Mapping[str, Any], manifest: Mapping[str, Any], raw: bytes | None,
) -> None:
    """Bind every mirrored field and byte span back to one immutable manifest."""
    validate_manifest_content_binding(manifest)
    validate_manifest_retained_bytes_binding(manifest, raw)
    manifest_id = str(manifest.get("manifest_id") or "")
    filing = record.get("filing") or {}
    manifest_filing = manifest.get("filing") or {}
    document = record.get("document") or {}
    manifest_document = manifest.get("document") or {}
    evidence = record.get("evidence") or {}
    expected_pairs = (
        (record.get("issuer_id"), (manifest.get("issuer") or {}).get("issuer_id"), "issuer_id"),
        (filing.get("accession"), manifest_filing.get("accession"), "filing.accession"),
        (filing.get("form"), manifest_filing.get("form"), "filing.form"),
        (filing.get("filing_date"), manifest_filing.get("filing_date"), "filing.filing_date"),
        (filing.get("accepted_at"), manifest_filing.get("accepted_at"), "filing.accepted_at"),
        (document.get("source_manifest_id"), manifest_id, "document.source_manifest_id"),
        (document.get("source_id"), manifest.get("source_id"), "document.source_id"),
        (document.get("canonical_url"), manifest_document.get("canonical_url"), "document.canonical_url"),
        (str(document.get("content_sha256") or "").lower(), str(manifest_document.get("content_sha256") or "").lower(), "document.content_sha256"),
        (evidence.get("source_manifest_id"), manifest_id, "evidence.source_manifest_id"),
        (str(evidence.get("source_document_sha256") or "").lower(), str(manifest_document.get("content_sha256") or "").lower(), "evidence.source_document_sha256"),
    )
    for actual, expected, label in expected_pairs:
        if actual != expected:
            raise ValueError(f"document term {label} is detached from source manifest")

    point_in_time = record.get("point_in_time") or {}
    manifest_source_time = _iso(
        (manifest.get("retrieval") or {}).get("first_seen_at"), "manifest.retrieval.first_seen_at",
    )
    if point_in_time.get("source_available_at") != manifest_source_time:
        raise ValueError("document term source_available_at is detached from source manifest")
    source_time = _parse_time(point_in_time.get("source_available_at"), "source_available_at")
    available_time = _parse_time(point_in_time.get("available_at"), "available_at")
    if available_time < source_time:
        raise ValueError("document term available_at precedes source_available_at")

    expected_digest = str(manifest_document.get("content_sha256") or "").lower()
    if raw is not None and hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError("document term source bytes fail manifest digest")

    child_fields = (
        document.get("child_document_type"), document.get("child_sequence"),
        document.get("child_filename"), document.get("child_text_start"),
        document.get("child_text_end"),
    )
    if any(value is not None for value in child_fields):
        if raw is None or document.get("child_text_start") is None or document.get("child_text_end") is None:
            raise ValueError("document term child provenance requires retained source bytes")
        matching_children = [
            child for child in _eligible_documents(raw, str(manifest_filing.get("form") or ""))
            if (
                child.document_type == document.get("child_document_type")
                and child.sequence == document.get("child_sequence")
                and child.filename == document.get("child_filename")
                and child.text_start == document.get("child_text_start")
                and child.text_end == document.get("child_text_end")
            )
        ]
        if len(matching_children) != 1:
            raise ValueError("document term child provenance does not resolve exactly")

    spans = evidence.get("spans") or []
    saw_exact_cell = False
    term_name = str((record.get("term") or {}).get("name") or "")
    source_slices: dict[str, bytes] = {}
    table_bounds: dict[int, tuple[int, int]] = {}
    row_bounds: dict[tuple[int, int], tuple[int, int]] = {}
    for span in spans:
        if str((span or {}).get("manifest_id") or "") != manifest_id:
            raise ValueError("document term span crosses source manifests")
        locator = str((span or {}).get("locator") or "")
        match = _BYTE_LOCATOR_RE.search(locator)
        if match is None:
            raise ValueError("document term span lacks an exact byte locator")
        start, end = int(match.group(1)), int(match.group(2))
        if start < 0 or end < start or end > int(manifest_document.get("byte_length") or 0):
            raise ValueError("document term span byte locator is out of bounds")
        locator_type = str((span or {}).get("locator_type") or "")
        if locator_type == "document":
            if start != 0 or end != int(manifest_document.get("byte_length") or 0):
                raise ValueError("document term root span is not the full retained document")
            actual_digest = expected_digest
        else:
            if raw is None:
                raise ValueError("document term derived span cannot be verified without source bytes")
            source_slice = raw[start:end]
            actual_digest = hashlib.sha256(source_slice).hexdigest()
            table_match = re.search(r":table=(\d+):", locator)
            row_match = re.search(r":row=(\d+):", locator)
            if locator_type == "table" and table_match:
                table_bounds[int(table_match.group(1))] = (start, end)
            if locator_type == "text_range" and table_match and row_match and ":cell=" not in locator:
                row_bounds[(int(table_match.group(1)), int(row_match.group(1)))] = (start, end)
            role_match = re.search(r":role=([^:]+):bytes:", locator)
            if role_match:
                source_slices[role_match.group(1)] = source_slice
            if locator_type == "text_range" and f"role={term_name}" in locator:
                saw_exact_cell = True
        if actual_digest != str((span or {}).get("text_sha256") or "").lower():
            raise ValueError("document term span hash is detached from source bytes")

    disposition = str((record.get("state") or {}).get("disposition") or "")
    reported = record.get("reported") or {}
    normalized = record.get("normalized") or {}
    if normalized != reported:
        raise ValueError("document term normalized value must preserve the direct dimensional fact")
    if disposition == "observed":
        if not isinstance(reported.get("value"), str) or not isinstance(reported.get("raw_text"), str):
            raise ValueError("observed document term lacks a direct decimal value")
        if not isinstance(reported.get("unit"), str) or not isinstance(reported.get("scale"), str):
            raise ValueError("observed document term lacks explicit dimensions")
        if not saw_exact_cell:
            raise ValueError("observed document term lacks an exact field-cell span")
        security = record.get("security") or {}
        expected_type, expected_unit, expected_currency = _term_semantics(
            term_name, str(security.get("classification") or "unknown"),
            rate_scale=str(reported.get("scale") or "1"),
        )
        if (
            (record.get("term") or {}).get("term_type") != expected_type
            or reported.get("unit") != expected_unit
            or reported.get("currency") != expected_currency
        ):
            raise ValueError("observed document term dimensions contradict its security row")
        term_slice = source_slices.get(term_name)
        if term_slice is None:
            raise ValueError("observed document term lacks a bound field cell")
        cell_match = _CELL_RE.fullmatch(term_slice)
        if cell_match is None or _cell_text(cell_match.group(3)) != reported.get("raw_text"):
            raise ValueError("observed document term raw text is detached from its field cell")
        reparsed = _parse_number(
            str(reported.get("raw_text") or ""),
            allow_denominated_rate=term_name == "filing_fee_rate",
        )
        if (
            reparsed.disposition != "observed"
            or reparsed.value != reported.get("value")
            or reparsed.scale != reported.get("scale")
        ):
            raise ValueError("observed document term value/scale does not round-trip its raw cell")
    elif any(reported.get(key) is not None for key in ("raw_text", "value", "unit", "currency", "scale")):
        raise ValueError("non-observed document term carries a guessed value")

    security = record.get("security") or {}
    row_id = security.get("row_id")
    if row_id is not None:
        table_index = security.get("table_index")
        row_index = security.get("row_index")
        table_bound = table_bounds.get(table_index)
        row_bound = row_bounds.get((table_index, row_index))
        if table_bound is None or row_bound is None:
            raise ValueError("document term row identity lacks exact table/row spans")
        expected_row_id = _digest_id(
            "fee-row:cs:",
            {
                "manifest_id": manifest_id, "table_start": table_bound[0],
                "row_start": row_bound[0], "row_end": row_bound[1],
            },
        )
        if row_id != expected_row_id:
            raise ValueError("document term row_id is detached from source bytes")
        title_slice = source_slices.get("security_title")
        if title_slice is None:
            raise ValueError("document term row lacks an exact security-title cell")
        title_match = _CELL_RE.fullmatch(title_slice)
        title = _cell_text(title_match.group(3)) if title_match is not None else ""
        if (
            security.get("title_raw") != (title or None)
            or security.get("title_normalized") != (_label(title) or None)
            or security.get("classification") != _classify_security(title)
        ):
            raise ValueError("document term security identity is detached from its title cell")

    # Hash-valid byte ranges alone do not prove that a row has retained the
    # correct role, state, value, or span identity. Rebuild every expected
    # observation from the exact retained complete submission and compare the
    # immutable source-derived body. Version/correction and parser-version
    # fields intentionally remain outside this comparison so historic parser
    # corrections retain their point-in-time chain while their declared facts
    # stay bound to the source bytes.
    expected_by_logical = {
        str(candidate["logical_observation_id"]): candidate
        for candidate in _records_for_manifest(manifest, raw)
    }
    logical = str(record.get("logical_observation_id") or "")
    expected_record = expected_by_logical.get(logical)
    if expected_record is None:
        raise ValueError("document term logical_observation_id is detached from source bytes")
    for field in (
        "schema", "issuer_id", "filing", "document", "security", "term",
        "state", "reported", "normalized", "evidence",
    ):
        if record.get(field) != expected_record.get(field):
            raise ValueError(f"document term {field} is detached from retained source semantics")
    actual_extraction = record.get("extraction") or {}
    expected_extraction = expected_record.get("extraction") or {}
    if {
        "method": actual_extraction.get("method"),
        "review_status": actual_extraction.get("review_status"),
    } != {
        "method": expected_extraction.get("method"),
        "review_status": expected_extraction.get("review_status"),
    }:
        raise ValueError("document term extraction state is detached from retained source semantics")


def validate_document_term_source_authority(
    records: Sequence[Mapping[str, Any]],
    *,
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
) -> list[dict[str, Any]]:
    """Validate an entire direct ledger against manifests and exact retained bytes.

    The append-only history is necessary but not sufficient: every version must
    independently re-derive the same source fact.  This makes a historical
    parser correction auditable without allowing a rehashed null, issuer, span,
    or logical-slot rewrite to become a valid point-in-time observation.
    """
    sources = [deepcopy(dict(raw)) for raw in records]
    manifests = [deepcopy(dict(raw)) for raw in source_manifests]
    validate_manifest_ledger(manifests)
    for manifest in manifests:
        validate_manifest_content_binding(manifest)
    validate_document_term_history(sources)

    manifests_by_id = {str(manifest["manifest_id"]): manifest for manifest in manifests}
    source_cache: dict[str, bytes] = {}
    for index, source in enumerate(sources):
        manifest_id = str((source.get("document") or {}).get("source_manifest_id") or "")
        manifest = manifests_by_id.get(manifest_id)
        if manifest is None:
            raise ValueError(f"document term row {index} source manifest is absent")
        raw = source_cache.get(manifest_id)
        if raw is None:
            loaded = source_reader(manifest)
            if not isinstance(loaded, bytes):
                raise ValueError(f"document term row {index} retained source bytes are unavailable")
            validate_manifest_retained_bytes_binding(manifest, loaded)
            source_cache[manifest_id] = loaded
            raw = loaded
        validate_observation_source_binding(source, manifest, raw)
    return sources


def validate_document_term_history(records: Sequence[Mapping[str, Any]]) -> None:
    """Validate immutable IDs, version chains, and non-retroactive corrections."""
    by_id: set[str] = set()
    by_logical: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, raw in enumerate(records):
        record = dict(raw)
        observation_id = str(record.get("observation_id") or "")
        if observation_id != observation_id_for(record):
            raise ValueError(f"document term row {index} observation_id digest mismatch")
        if observation_id in by_id:
            raise ValueError(f"duplicate document term observation_id {observation_id}")
        by_id.add(observation_id)
        logical = str(record.get("logical_observation_id") or "")
        if not logical:
            raise ValueError(f"document term row {index} lacks logical_observation_id")
        point_in_time = record.get("point_in_time") or {}
        if _parse_time(point_in_time.get("available_at"), "available_at") < _parse_time(
            point_in_time.get("source_available_at"), "source_available_at",
        ):
            raise ValueError(f"document term row {index} available_at precedes source_available_at")
        by_logical[logical].append(record)

    for logical, versions in by_logical.items():
        ordered = sorted(versions, key=lambda row: int((row.get("version") or {}).get("correction_version") or 0))
        expected = list(range(1, len(ordered) + 1))
        actual = [int((row.get("version") or {}).get("correction_version") or 0) for row in ordered]
        if actual != expected:
            raise ValueError(f"document term {logical} has non-contiguous correction versions")
        for number, record in enumerate(ordered, start=1):
            version = record.get("version") or {}
            prior = ordered[number - 2] if number > 1 else None
            supersedes = list((record.get("relationships") or {}).get("supersedes") or [])
            if number == 1:
                if version.get("correction_of") is not None or supersedes:
                    raise ValueError(f"document term {logical} v1 cannot be a correction")
            if prior is not None:
                if version.get("correction_of") != prior.get("observation_id"):
                    raise ValueError(f"document term {logical} correction does not point to prior version")
                if supersedes != [prior.get("observation_id")]:
                    raise ValueError(f"document term {logical} supersedes does not point to prior version")
                prior_time = _parse_time((prior.get("point_in_time") or {}).get("available_at"), "prior.available_at")
                current_time = _parse_time((record.get("point_in_time") or {}).get("available_at"), "available_at")
                if current_time <= prior_time:
                    raise ValueError(f"document term {logical} correction is retroactive")


def current_document_terms_as_of(
    records: Sequence[Mapping[str, Any]], as_of: str,
) -> list[dict[str, Any]]:
    """Return the latest immutable document-term version visible on system time."""
    validate_document_term_history(records)
    cutoff = _parse_time(as_of, "as_of")
    visible: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        record = dict(raw)
        available_at = _parse_time((record.get("point_in_time") or {}).get("available_at"), "available_at")
        if available_at > cutoff:
            continue
        logical = str(record.get("logical_observation_id") or "")
        prior = visible.get(logical)
        if prior is None or int((record.get("version") or {}).get("correction_version") or 0) > int((prior.get("version") or {}).get("correction_version") or 0):
            visible[logical] = record
    return [dict(visible[key]) for key in sorted(visible)]


def compile_document_term_records(
    manifests: Sequence[Mapping[str, Any]],
    *,
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    existing_observations: Sequence[Mapping[str, Any]] = (),
    generated_at: str,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Pure compile surface. ``source_reader`` must return exact manifest bytes.

    All in-scope source reads happen before any candidate is versioned. A missing
    or hash-mismatched object aborts the whole run, preserving the previous
    telemetry-last generation instead of publishing a misleading partial ledger.
    """
    manifest_rows = [dict(item) for item in manifests]
    validate_manifest_ledger(manifest_rows)
    for manifest in manifest_rows:
        validate_manifest_content_binding(manifest)
    generated = _iso(generated_at, "generated_at")
    existing = [dict(item) for item in existing_observations]
    validate_document_term_history(existing)

    current_by_logical: dict[str, Mapping[str, Any]] = {}
    for record in existing:
        logical = str(record["logical_observation_id"])
        prior = current_by_logical.get(logical)
        if prior is None or int((record.get("version") or {}).get("correction_version") or 0) > int((prior.get("version") or {}).get("correction_version") or 0):
            current_by_logical[logical] = record

    selected = [
        row for row in manifest_rows
        if str(row.get("source_system") or "") == "sec_edgar"
        and str((row.get("document") or {}).get("document_role") or "") == "complete_submission"
        and _normalized_form(str((row.get("filing") or {}).get("form") or "")) in REGISTRATION_FEE_FORMS
    ]
    selected.sort(key=lambda row: str(row.get("manifest_id") or ""))
    current_by_manifest: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for prior in current_by_logical.values():
        current_by_manifest[str((prior.get("document") or {}).get("source_manifest_id") or "")].append(prior)
    materialize = [
        manifest for manifest in selected
        if rebuild
        or not current_by_manifest.get(str(manifest["manifest_id"]))
        or any(
            str((prior.get("extraction") or {}).get("parser_version") or "") != PARSER_VERSION
            for prior in current_by_manifest[str(manifest["manifest_id"])]
        )
    ]
    failures: list[dict[str, Any]] = []
    source_bytes: dict[str, bytes] = {}
    for manifest in materialize:
        manifest_id = str(manifest["manifest_id"])
        raw = source_reader(manifest)
        expected = str((manifest.get("document") or {}).get("content_sha256") or "").lower()
        if raw is None:
            failures.append({"accession": (manifest.get("filing") or {}).get("accession"), "state": "source_bytes_unavailable", "errors": [manifest_id]})
            continue
        if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != expected:
            failures.append({"accession": (manifest.get("filing") or {}).get("accession"), "state": "source_bytes_digest_mismatch", "errors": [manifest_id]})
            continue
        try:
            validate_manifest_retained_bytes_binding(manifest, raw)
        except ValueError as exc:
            failures.append({"accession": (manifest.get("filing") or {}).get("accession"), "state": "source_identity_detached", "errors": [str(exc)]})
            continue
        source_bytes[manifest_id] = raw
    if failures:
        raise DocumentTermCompileDegraded(failures)

    incoming: list[dict[str, Any]] = []
    unchanged = 0
    for manifest in materialize:
        for candidate in _records_for_manifest(manifest, source_bytes[str(manifest["manifest_id"])]):
            if _parse_time(generated, "generated_at") < _parse_time(
                (candidate.get("point_in_time") or {}).get("source_available_at"),
                "source_available_at",
            ):
                raise ValueError("generated_at cannot precede retained source availability")
            logical = str(candidate["logical_observation_id"])
            prior = current_by_logical.get(logical)
            if prior is not None and _semantic_body(prior) == _semantic_body(candidate):
                unchanged += 1
                continue
            correction_version = 1 if prior is None else int((prior.get("version") or {}).get("correction_version") or 0) + 1
            if prior is not None:
                prior_time = _parse_time((prior.get("point_in_time") or {}).get("available_at"), "prior.available_at")
                if _parse_time(generated, "generated_at") <= prior_time:
                    raise ValueError("generated_at must be later than a corrected document-term observation")
            candidate["relationships"] = {
                "amends": [],
                "supersedes": [] if prior is None else [str(prior["observation_id"])],
                "contradiction_ids": [],
            }
            candidate["version"] = {
                "immutable_record": True, "correction_version": correction_version,
                "correction_of": None if prior is None else str(prior["observation_id"]),
            }
            candidate["point_in_time"]["available_at"] = generated
            candidate["observation_id"] = observation_id_for(candidate)
            validate_observation_source_binding(
                candidate, manifest, source_bytes[str(manifest["manifest_id"])],
            )
            incoming.append(candidate)
            current_by_logical[logical] = candidate

    output = [*existing, *incoming]
    validate_document_term_source_authority(
        output,
        source_manifests=manifest_rows,
        source_reader=source_reader,
    )
    return {
        "observations": output,
        "new_observations": incoming,
        "counts": {
            "eligible_complete_submissions": len(selected),
            "processed_complete_submissions": len(materialize),
            "observations": len(output),
            "new_observations": len(incoming),
            "unchanged_observations": unchanged,
            "observed": sum(1 for row in output if (row.get("state") or {}).get("disposition") == "observed"),
            "unavailable": sum(1 for row in output if (row.get("state") or {}).get("disposition") == "unavailable"),
            "ambiguous": sum(1 for row in output if (row.get("state") or {}).get("disposition") == "ambiguous"),
        },
    }
