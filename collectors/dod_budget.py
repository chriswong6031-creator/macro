"""Hermetic foundation for immutable DoD P-1/R-1 budget evidence.

This module deliberately has no live HTTP or object-storage implementation yet.
It accepts already-fetched PDF bytes plus extracted page text, then enforces the
source contract before emitting receipt-bound, append-only normalized lines.  A
future scheduled collector may supply the acquisition/storage adapters, but may
not bypass these checks.

The first bounded source family is the DoD Comptroller FY President's Budget
P-1 and R-1 exhibits.  These documents contain historical and enacted reference
columns; those cells remain explicitly labelled and are never promoted to a
current authorization, appropriation, execution, award, or revenue claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit


DOD_BUDGET_RECEIPT_CONTRACT = "government_revenue.dod_budget_collection_receipt.v1"
DOD_BUDGET_SNAPSHOT_CONTRACT = "government_budget_line.v1"
DOD_BUDGET_PROJECTION_STATE_CONTRACT = "government_revenue.dod_budget_projection_state.v1"
DOD_BUDGET_INGEST_STATUS_CONTRACT = "government_revenue.dod_budget_ingest_status.v1"
SCHEMA_VERSION = "1.0.0"
PARSER_VERSION = "dod-budget-fixture-parser.v1"
EXTRACTOR_VERSION = "dod-budget-fixture-pages.v1"
# Publication remains deliberately hard-disabled until a live acquisition lane
# proves the durable object write and derives page text from those exact PDF
# bytes with a production parser/extractor contract.
DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED = False

ALLOWED_SOURCE_HOSTS = {"comptroller.defense.gov", "comptroller.war.gov"}
ALLOWED_EXHIBITS = {"p1", "r1"}
DOCUMENT_STAGE = "president_budget_request"
IMMUTABLE_R2_PREFIX = "government-revenue/dod-budget/pdf/sha256/"

AMOUNT_SEMANTICS = (
    "historical_actual",
    "prior_year_enacted_reference",
    "discretionary_request",
    "reconciliation_request",
    "president_budget_request_total",
)
_FORBIDDEN_RECEIPT_KEY = re.compile(
    r"(?:raw_(?:body|response|request|payload)|(?:request|response)_headers|"
    r"authorization|api[_-]?key|secret|token|password|credential)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(?:fiscal\s+year|fy)\s*(20\d{2})", re.IGNORECASE)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256(_canonical_json(value))


def _utc_iso(value: str | datetime | None = None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be offset-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _text(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing {label}")
    return text


def _number(value: Any, *, label: str, nullable: bool = False) -> float | None:
    if value is None or value == "":
        if nullable:
            return None
        raise ValueError(f"missing {label}")
    if isinstance(value, bool):
        raise ValueError(f"invalid {label}")
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not math.isfinite(number):
        raise ValueError(f"invalid {label}")
    return number


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not result:
        raise ValueError("identifier cannot be normalized")
    return result


def _official_https_url(value: Any) -> str:
    text = _text(value, label="source URL")
    parsed = urlsplit(text)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("DoD budget source URL has an invalid port") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in ALLOWED_SOURCE_HOSTS
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise ValueError("DoD budget source URL is not an allowlisted official HTTPS URL")
    return text


def _contains_forbidden_receipt_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            (
                str(key) != "raw_response_bodies_persisted"
                and _FORBIDDEN_RECEIPT_KEY.search(str(key)) is not None
            )
            or _contains_forbidden_receipt_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_receipt_key(item) for item in value)
    return False


def _header_text(pages: Sequence[str]) -> str:
    return "\n".join(str(page) for page in pages[:2])


def _page_text_sha256s(pages: Sequence[str]) -> list[str]:
    if not pages or not all(isinstance(page, str) and page.strip() for page in pages):
        raise ValueError("DoD budget PDF has no extractable page text")
    return [_sha256(page) for page in pages]


def _extraction_semantic_sha256(page_text_sha256s: Sequence[str]) -> str:
    hashes = list(page_text_sha256s)
    if not hashes or any(re.fullmatch(r"[a-f0-9]{64}", value) is None for value in hashes):
        raise ValueError("DoD budget extraction manifest has invalid page hashes")
    return _sha256_json({"ordered_page_text_sha256s": hashes, "page_count": len(hashes)})


def _receipt_identity(receipt: Mapping[str, Any]) -> str:
    fingerprint = {
        "content_sha256": receipt.get("content_sha256"),
        "extraction_semantic_sha256": receipt.get("extraction_semantic_sha256"),
        "source_url": receipt.get("source_url"),
        "final_url": receipt.get("final_url"),
        "fiscal_year": receipt.get("fiscal_year"),
        "exhibit": receipt.get("exhibit"),
        "observed_at": receipt.get("observed_at"),
        "extractor_version": receipt.get("extractor_version"),
        "parser_version": receipt.get("parser_version"),
    }
    return "dod-budget:" + _sha256_json(fingerprint)


def verify_document_header(pages: Sequence[str], *, fiscal_year: int, exhibit: str) -> None:
    """Require a source-native FY/exhibit header before any parser result is trusted."""
    if exhibit not in ALLOWED_EXHIBITS:
        raise ValueError("unsupported DoD budget exhibit")
    if not pages or not all(isinstance(page, str) and page.strip() for page in pages):
        raise ValueError("DoD budget PDF has no extractable page text")
    header = _header_text(pages).upper()
    years = {int(value) for value in _YEAR_RE.findall(header)}
    if fiscal_year not in years:
        raise ValueError("DoD budget document header fiscal year mismatch")
    required = "PROCUREMENT PROGRAMS (P-1)" if exhibit == "p1" else "RDT&E PROGRAMS (R-1)"
    if required not in header:
        raise ValueError("DoD budget document header exhibit mismatch")
    if "COMPTROLLER" not in header:
        raise ValueError("DoD budget document header publisher mismatch")


def build_document_receipt(
    *,
    source_url: str,
    final_url: str,
    pdf_bytes: bytes,
    pages: Sequence[str],
    fiscal_year: int,
    exhibit: str,
    observed_at: str | datetime,
    immutable_object_key: str,
    extractor_version: str = EXTRACTOR_VERSION,
    parser_version: str = PARSER_VERSION,
) -> dict[str, Any]:
    """Return a hash-only observation receipt bound to PDF and extracted pages.

    ``immutable_object_key`` enforces the content-addressed naming invariant; a
    future live acquisition adapter must separately prove that the object write
    succeeded. The ordered extraction manifest prevents callers from swapping
    page text after this receipt is created.
    """
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("DoD budget source is not a PDF byte stream")
    source_url = _official_https_url(source_url)
    final_url = _official_https_url(final_url)
    if not isinstance(fiscal_year, int) or not 2000 <= fiscal_year <= 2100:
        raise ValueError("invalid fiscal year")
    exhibit = str(exhibit).casefold()
    verify_document_header(pages, fiscal_year=fiscal_year, exhibit=exhibit)
    observed = _utc_iso(observed_at)
    document_sha256 = _sha256(pdf_bytes)
    page_text_sha256s = _page_text_sha256s(pages)
    extraction_semantic_sha256 = _extraction_semantic_sha256(page_text_sha256s)
    expected_object_key = f"{IMMUTABLE_R2_PREFIX}{document_sha256}.pdf"
    if immutable_object_key != expected_object_key:
        raise ValueError("DoD budget immutable object key does not bind source bytes")
    receipt = {
        "contract": DOD_BUDGET_RECEIPT_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "receipt_id": "",
        "publisher": "Office of the Under Secretary of Defense (Comptroller)",
        "fiscal_year": fiscal_year,
        "document_stage": DOCUMENT_STAGE,
        "exhibit": exhibit,
        "source_url": source_url,
        "final_url": final_url,
        "observed_at": observed,
        "content_sha256": document_sha256,
        "page_count": len(pages),
        "page_text_sha256s": page_text_sha256s,
        "extraction_semantic_sha256": extraction_semantic_sha256,
        "immutable_object_key": immutable_object_key,
        "request_sha256": _sha256_json({"source_url": source_url}),
        "response_sha256": document_sha256,
        "extractor_version": _text(extractor_version, label="extractor version"),
        "parser_version": _text(parser_version, label="parser version"),
        "raw_response_bodies_persisted": False,
    }
    receipt["receipt_id"] = _receipt_identity(receipt)
    validate_document_receipt(receipt)
    return receipt


def validate_document_receipt(receipt: Mapping[str, Any]) -> None:
    """Reject unsafe, mutable, or non-content-addressed source receipts."""
    if not isinstance(receipt, Mapping) or _contains_forbidden_receipt_key(receipt):
        raise ValueError("DoD budget receipt contains forbidden raw or sensitive fields")
    required_keys = {
        "contract", "schema_version", "receipt_id", "publisher", "fiscal_year",
        "document_stage", "exhibit", "source_url", "final_url", "observed_at",
        "content_sha256", "page_count", "page_text_sha256s",
        "extraction_semantic_sha256", "immutable_object_key", "request_sha256",
        "response_sha256", "extractor_version", "parser_version",
        "raw_response_bodies_persisted",
    }
    if set(receipt) != required_keys:
        raise ValueError("DoD budget receipt shape mismatch")
    if receipt.get("contract") != DOD_BUDGET_RECEIPT_CONTRACT or receipt.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("DoD budget receipt contract mismatch")
    if receipt.get("publisher") != "Office of the Under Secretary of Defense (Comptroller)":
        raise ValueError("DoD budget receipt publisher mismatch")
    fiscal_year = receipt.get("fiscal_year")
    if isinstance(fiscal_year, bool) or not isinstance(fiscal_year, int) or not 2000 <= fiscal_year <= 2100:
        raise ValueError("DoD budget receipt fiscal year mismatch")
    if receipt.get("document_stage") != DOCUMENT_STAGE:
        raise ValueError("DoD budget receipt stage mismatch")
    exhibit = str(receipt.get("exhibit") or "").casefold()
    if exhibit not in ALLOWED_EXHIBITS:
        raise ValueError("DoD budget receipt exhibit mismatch")
    _official_https_url(receipt.get("source_url"))
    _official_https_url(receipt.get("final_url"))
    document_sha = _text(receipt.get("content_sha256"), label="document sha256").lower()
    if not re.fullmatch(r"[a-f0-9]{64}", document_sha):
        raise ValueError("DoD budget receipt content hash is invalid")
    if receipt.get("response_sha256") != document_sha:
        raise ValueError("DoD budget receipt response hash mismatch")
    if receipt.get("receipt_id") != _receipt_identity(receipt):
        raise ValueError("DoD budget receipt identity mismatch")
    if receipt.get("immutable_object_key") != f"{IMMUTABLE_R2_PREFIX}{document_sha}.pdf":
        raise ValueError("DoD budget receipt immutable-object binding mismatch")
    if receipt.get("raw_response_bodies_persisted") is not False:
        raise ValueError("DoD budget receipt must not claim raw response persistence")
    page_hashes = receipt.get("page_text_sha256s")
    if (
        not isinstance(receipt.get("page_count"), int)
        or receipt["page_count"] < 1
        or not isinstance(page_hashes, list)
        or len(page_hashes) != receipt["page_count"]
        or any(not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None for value in page_hashes)
    ):
        raise ValueError("DoD budget receipt page count is invalid")
    if receipt.get("extraction_semantic_sha256") != _extraction_semantic_sha256(page_hashes):
        raise ValueError("DoD budget receipt extraction manifest mismatch")
    if receipt.get("request_sha256") != _sha256_json({"source_url": receipt["source_url"]}):
        raise ValueError("DoD budget receipt request hash mismatch")
    for key in ("extractor_version", "parser_version"):
        value = receipt.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise ValueError(f"DoD budget receipt {key} mismatch")
    _utc_iso(receipt.get("observed_at"))


def verify_extraction_manifest(pages: Sequence[str], receipt: Mapping[str, Any]) -> None:
    validate_document_receipt(receipt)
    hashes = _page_text_sha256s(pages)
    if len(hashes) != receipt["page_count"] or hashes != receipt["page_text_sha256s"]:
        raise ValueError("DoD budget extracted pages do not match the immutable receipt")
    if _extraction_semantic_sha256(hashes) != receipt["extraction_semantic_sha256"]:
        raise ValueError("DoD budget extraction manifest mismatch")


def merge_receipts(existing: Iterable[Mapping[str, Any]], incoming: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Append receipt records immutably; repeated IDs must have identical bytes."""
    merged: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    for row in list(existing) + list(incoming):
        validate_document_receipt(row)
        canonical = _canonical_json(dict(row))
        receipt_id = str(row["receipt_id"])
        previous = merged.get(receipt_id)
        if previous is not None and previous != canonical:
            raise ValueError("DoD budget receipt ID is bound to conflicting evidence")
        if previous is None:
            merged[receipt_id] = canonical
            records.append(dict(row))
    return records


def _amounts_from_fields(fields: Mapping[str, str], *, fiscal_year: int) -> list[dict[str, Any]]:
    values = (
        (fiscal_year - 2, "historical_actual", fields.get("actual"), False),
        (fiscal_year - 1, "prior_year_enacted_reference", fields.get("enacted"), False),
        (fiscal_year, "discretionary_request", fields.get("disc_request"), True),
        (fiscal_year, "reconciliation_request", fields.get("recon_request"), True),
        (fiscal_year, "president_budget_request_total", fields.get("total_request"), False),
    )
    result: list[dict[str, Any]] = []
    for cell_year, semantic, raw, nullable in values:
        value = _number(raw, label=semantic, nullable=nullable)
        if value is not None:
            value *= 1_000.0  # official P-1/R-1 fixture values are dollars in thousands
        result.append({"fiscal_year": cell_year, "semantic": semantic, "amount_usd": value})
    return result


def _quantities_from_fields(fields: Mapping[str, str], *, fiscal_year: int) -> list[dict[str, Any]]:
    """Preserve the P-1 Qty columns by fiscal/stage semantic; R-1 remains empty."""
    values = (
        (fiscal_year - 2, "historical_actual", fields.get("actual_quantity")),
        (fiscal_year - 1, "prior_year_enacted_reference", fields.get("enacted_quantity")),
        (fiscal_year, "discretionary_request", fields.get("disc_request_quantity")),
        (fiscal_year, "reconciliation_request", fields.get("recon_request_quantity")),
        (fiscal_year, "president_budget_request_total", fields.get("total_request_quantity")),
    )
    result: list[dict[str, Any]] = []
    for cell_year, semantic, raw in values:
        value = _number(raw, label=f"{semantic} quantity", nullable=True)
        result.append({"fiscal_year": cell_year, "semantic": semantic, "quantity": value})
    return result


def _line_identity(*, exhibit: str, component: str, appropriation_code: str, native_kind: str, native_value: str, fiscal_year: int) -> tuple[str, str]:
    family = ":".join((
        "dod-family", exhibit, _slug(component), _slug(appropriation_code),
        _slug(native_kind), _slug(native_value),
    ))
    line = ":".join((
        "dod", exhibit, _slug(component), _slug(appropriation_code),
        _slug(native_kind), _slug(native_value), f"fy{fiscal_year}", DOCUMENT_STAGE,
    ))
    return line, family


def _line_state_sha256(row: Mapping[str, Any]) -> str:
    keys = (
        "line_key", "fiscal_year", "document_stage", "exhibit", "component", "appropriation",
        "appropriation_code", "budget_activity", "native_identifier", "program_name", "amounts",
        "quantities", "source", "provenance", "effective_at", "known_at", "first_seen_at",
    )
    return _sha256_json({key: row.get(key) for key in keys})


def _pipe_fields(value: str, *, expected: str) -> dict[str, str]:
    pieces = [item.strip() for item in value.split("|")]
    if not pieces or pieces[0].casefold() != expected:
        raise ValueError("fixture parser record type mismatch")
    result: dict[str, str] = {}
    for item in pieces[1:]:
        if "=" not in item:
            raise ValueError("fixture parser field is malformed")
        key, raw = item.split("=", 1)
        key, raw = key.strip(), raw.strip()
        if not key or key in result:
            raise ValueError("fixture parser has duplicate or blank field")
        result[key] = raw
    return result


def _normalized_line(
    *,
    fields: Mapping[str, str],
    receipt: Mapping[str, Any],
    page_number: int,
    page_text: str,
    source_line_number: int,
) -> dict[str, Any]:
    exhibit = str(receipt["exhibit"])
    fiscal_year = int(receipt["fiscal_year"])
    required = ("component", "appropriation", "appropriation_code", "activity", "name")
    for key in required:
        _text(fields.get(key), label=f"budget line {key}")
    if exhibit == "p1":
        native_kind, native_value = "p1_line_item", _text(fields.get("line"), label="P-1 line item")
    else:
        native_kind, native_value = "program_element", _text(fields.get("pe"), label="R-1 program element")
    line_key, line_family_key = _line_identity(
        exhibit=exhibit,
        component=fields["component"],
        appropriation_code=fields["appropriation_code"],
        native_kind=native_kind,
        native_value=native_value,
        fiscal_year=fiscal_year,
    )
    observed = _utc_iso(receipt["observed_at"])
    row = {
        "contract": DOD_BUDGET_SNAPSHOT_CONTRACT,
        "line_key": line_key,
        "line_family_key": line_family_key,
        "fiscal_year": fiscal_year,
        "document_stage": DOCUMENT_STAGE,
        "exhibit": exhibit,
        "component": fields["component"],
        "appropriation": fields["appropriation"],
        "appropriation_code": fields["appropriation_code"],
        "budget_activity": fields["activity"],
        "native_identifier": {"kind": native_kind, "value": native_value},
        "program_name": fields["name"],
        "amounts": _amounts_from_fields(fields, fiscal_year=fiscal_year),
        "quantities": _quantities_from_fields(fields, fiscal_year=fiscal_year),
        "source": {
            "publisher": "Office of the Under Secretary of Defense (Comptroller)",
            "source_url": receipt["final_url"],
            "document_sha256": receipt["content_sha256"],
            "receipt_id": receipt["receipt_id"],
        },
        "provenance": {
            "page_number": page_number,
            "page_text_sha256": _sha256(page_text),
            "source_span": f"extracted-page:{page_number}:line:{source_line_number}",
            "parser_version": receipt["parser_version"],
        },
        "line_state_sha256": "",
        "effective_at": observed,
        "known_at": observed,
        "first_seen_at": observed,
    }
    row["line_state_sha256"] = _line_state_sha256(row)
    return row


def parse_budget_document(pages: Sequence[str], receipt: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the deterministic fixture grammar and bind every row to one PDF page.

    The live adapter must convert PDF text into this same narrow intermediate
    grammar.  Any unrecognized detail/total record rejects the whole document
    rather than emitting a plausible but untraceable amount.
    """
    verify_extraction_manifest(pages, receipt)
    verify_document_header(pages, fiscal_year=int(receipt["fiscal_year"]), exhibit=str(receipt["exhibit"]))
    lines: list[dict[str, Any]] = []
    totals: list[dict[str, Any]] = []
    for page_number, page_text in enumerate(pages, start=1):
        for source_line_number, raw in enumerate(page_text.splitlines(), start=1):
            record = raw.strip()
            if not record or record.startswith("#"):
                continue
            lowered = record.casefold()
            if lowered.startswith("line|"):
                lines.append(_normalized_line(
                    fields=_pipe_fields(record, expected="line"), receipt=receipt,
                    page_number=page_number, page_text=page_text,
                    source_line_number=source_line_number,
                ))
            elif lowered.startswith("total|"):
                fields = _pipe_fields(record, expected="total")
                for key in ("appropriation_code", "activity"):
                    _text(fields.get(key), label=f"budget total {key}")
                totals.append({
                    "exhibit": str(receipt["exhibit"]),
                    "appropriation_code": fields["appropriation_code"],
                    "budget_activity": fields["activity"],
                    "amounts": _amounts_from_fields(fields, fiscal_year=int(receipt["fiscal_year"])),
                    "page_number": page_number,
                    "page_text_sha256": _sha256(page_text),
                })
            elif "|" in record:
                raise ValueError("unrecognized DoD budget fixture record")
    if not lines or not totals:
        raise ValueError("DoD budget document lacks receipt-bound lines or totals")
    reconcile_line_totals(lines, totals)
    return lines, totals


def _amount_map(row: Mapping[str, Any]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for amount in row.get("amounts") or []:
        if not isinstance(amount, Mapping):
            raise ValueError("DoD budget amount record is malformed")
        semantic = str(amount.get("semantic") or "")
        if semantic not in AMOUNT_SEMANTICS or semantic in result:
            raise ValueError("DoD budget amount semantic is malformed")
        value = amount.get("amount_usd")
        result[semantic] = _number(value, label=f"{semantic} amount", nullable=True)
    return result


def reconcile_line_totals(lines: Sequence[Mapping[str, Any]], totals: Sequence[Mapping[str, Any]]) -> None:
    """Fail closed unless every published partition matches its printed source total."""
    grouped: dict[tuple[str, str, str | None], list[Mapping[str, Any]]] = {}
    for row in lines:
        key = (str(row.get("exhibit")), str(row.get("appropriation_code")), row.get("budget_activity"))
        grouped.setdefault(key, []).append(row)
    total_map: dict[tuple[str, str, str | None], Mapping[str, Any]] = {}
    for total in totals:
        key = (str(total.get("exhibit")), str(total.get("appropriation_code")), total.get("budget_activity"))
        if key in total_map:
            raise ValueError("DoD budget has duplicate source total partition")
        total_map[key] = total
    if set(grouped) != set(total_map):
        raise ValueError("DoD budget detail partitions do not match printed source totals")
    for key, rows in grouped.items():
        expected = _amount_map(total_map[key])
        for semantic in AMOUNT_SEMANTICS:
            values = [_amount_map(row).get(semantic) for row in rows]
            actual = sum(value for value in values if value is not None)
            wanted = expected.get(semantic)
            if wanted is None:
                if any(value is not None for value in values):
                    raise ValueError("DoD budget total omits a populated amount semantic")
                continue
            if not math.isclose(actual, wanted, rel_tol=0.0, abs_tol=0.01):
                raise ValueError(f"DoD budget source total mismatch for {key} {semantic}")


def append_line_snapshot_versions(existing: Iterable[Mapping[str, Any]], incoming: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Append only a changed latest state, preserving A → B → A evidence history."""
    result = [dict(row) for row in existing]
    latest: dict[str, Mapping[str, Any]] = {}
    for row in result:
        key = _text(row.get("line_key"), label="line snapshot key")
        latest[key] = row
    for raw in incoming:
        row = dict(raw)
        if row.get("contract") != DOD_BUDGET_SNAPSHOT_CONTRACT:
            raise ValueError("DoD budget line snapshot contract mismatch")
        expected = _line_state_sha256(row)
        if row.get("line_state_sha256") != expected:
            raise ValueError("DoD budget line snapshot state hash mismatch")
        key = _text(row.get("line_key"), label="line snapshot key")
        prior = latest.get(key)
        if prior is not None:
            row["first_seen_at"] = prior.get("first_seen_at")
            row["line_state_sha256"] = _line_state_sha256(row)
        if prior is not None and prior.get("line_state_sha256") == row["line_state_sha256"]:
            continue
        result.append(row)
        latest[key] = row
    return result


def budget_projection_state(lines: Sequence[Mapping[str, Any]], receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the ledger generation that a downstream graph must verify."""
    for receipt in receipts:
        validate_document_receipt(receipt)
    receipt_index = {str(receipt["receipt_id"]): dict(receipt) for receipt in receipts}
    if len(receipt_index) != len(receipts):
        raise ValueError("DoD budget projection has duplicate receipt identities")
    receipt_ids = set(receipt_index)
    referenced_receipt_ids: set[str] = set()
    normalized_lines: list[dict[str, Any]] = []
    for raw in lines:
        row = dict(raw)
        if row.get("contract") != DOD_BUDGET_SNAPSHOT_CONTRACT:
            raise ValueError("DoD budget projection has invalid line contract")
        source = row.get("source")
        provenance = row.get("provenance")
        if not isinstance(source, Mapping) or not isinstance(provenance, Mapping):
            raise ValueError("DoD budget line lacks source provenance")
        receipt_id = source.get("receipt_id")
        if receipt_id not in receipt_ids:
            raise ValueError("DoD budget line lacks a retained immutable receipt")
        receipt = receipt_index[str(receipt_id)]
        page_number = provenance.get("page_number")
        known_at = _utc_iso(row.get("known_at"))
        effective_at = _utc_iso(row.get("effective_at"))
        first_seen_at = _utc_iso(row.get("first_seen_at"))
        if (
            source.get("publisher") != receipt["publisher"]
            or source.get("source_url") != receipt["final_url"]
            or source.get("document_sha256") != receipt["content_sha256"]
            or row.get("fiscal_year") != receipt["fiscal_year"]
            or row.get("exhibit") != receipt["exhibit"]
            or row.get("document_stage") != receipt["document_stage"]
            or provenance.get("parser_version") != receipt["parser_version"]
            or isinstance(page_number, bool)
            or not isinstance(page_number, int)
            or not 1 <= page_number <= receipt["page_count"]
            or provenance.get("page_text_sha256") != receipt["page_text_sha256s"][page_number - 1]
            or known_at != receipt["observed_at"]
            or effective_at != receipt["observed_at"]
            or first_seen_at > known_at
        ):
            raise ValueError("DoD budget line provenance does not reconcile to its receipt")
        if row.get("line_state_sha256") != _line_state_sha256(row):
            raise ValueError("DoD budget line state hash mismatch")
        referenced_receipt_ids.add(str(receipt_id))
        normalized_lines.append(row)
    if referenced_receipt_ids != receipt_ids:
        raise ValueError("DoD budget projection contains an unused document receipt")
    fingerprint = {
        "line_state_sha256": sorted(str(row["line_state_sha256"]) for row in normalized_lines),
        "receipt_ids": sorted(receipt_ids),
    }
    digest = _sha256_json(fingerprint)
    return {
        "contract": DOD_BUDGET_PROJECTION_STATE_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "line_snapshot_count": len(normalized_lines),
        "receipt_count": len(receipt_ids),
        "semantic_sha256": digest,
        "projection_generation_id": f"dod-budget-{digest[:24]}",
    }


def projection_state_matches(state: Mapping[str, Any], lines: Sequence[Mapping[str, Any]], receipts: Sequence[Mapping[str, Any]]) -> bool:
    try:
        expected = budget_projection_state(lines, receipts)
    except (TypeError, ValueError):
        return False
    return _canonical_json(dict(state)) == _canonical_json(expected)


def fixture_documents_from_directory(path: Path) -> list[dict[str, Any]]:
    """Read only local test fixtures; a live acquisition path is intentionally absent."""
    docs: list[dict[str, Any]] = []
    for source in sorted(Path(path).glob("*.json")):
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"invalid DoD budget fixture: {source}") from exc
        if not isinstance(value, Mapping):
            raise ValueError(f"DoD budget fixture must be an object: {source}")
        docs.append(dict(value))
    if not docs:
        raise ValueError("DoD budget fixture directory is empty")
    return docs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate local DoD budget collection fixtures")
    parser.add_argument("--fixture-dir", required=True, help="local fixture directory; live collection is intentionally unavailable")
    args = parser.parse_args(argv)
    docs = fixture_documents_from_directory(Path(args.fixture_dir))
    print(f"DoD budget foundation loaded {len(docs)} local fixture document(s); no live collection performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
