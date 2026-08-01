"""Point-in-time SEC evidence collector for Capital Structure Intelligence.

This adapter is deliberately an evidence collector, not a financing analyzer.
It discovers a bounded, explicit form universe from EDGAR's daily form index,
stores the original submission and relevant documents by content hash, and
emits provenance manifests for an offline compiler.  Ambiguous filings remain
unclassified until the compiler can read their stored evidence.

The legacy ``edgar_dilution`` adapter remains the sole writer of
``data/edgar/dilution_events.parquet`` during the shadow-parity period.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from pandas.tseries.holiday import USFederalHolidayCalendar

from collectors.base import Adapter, is_connection_error
from engine.capital_structure.source_identity import (
    manifest_id_for,
    merge_manifest_ledgers,
    validate_manifest_identity,
    validate_manifest_ledger,
)

log = logging.getLogger(__name__)

_DAILY_IDX = "https://www.sec.gov/Archives/edgar/daily-index/{yr}/QTR{q}/form.{ds}.idx"
_ARCHIVES = "https://www.sec.gov/Archives/"

# Wave 1 is intentionally the registration / issuance family. Broad 8-K, 6-K,
# proxy, and periodic-report reconciliation is declared but not silently
# claimed as covered; those sources require issuer-aware routing to avoid an
# unbounded all-company evidence backlog.
REGISTRATION_FORMS = {
    "S-1", "S-1/A", "F-1", "F-1/A", "S-3", "S-3/A", "S-3ASR",
    "F-3", "F-3/A", "F-3ASR", "F-10", "F-10/A",
}
STATE_FORMS = {"EFFECT", "POS AM", "POSASR", "RW", "RW/A", "AW", "AW/A"}
PROSPECTUS_FORMS = {
    "424B1", "424B3", "424B4", "424B5", "424B7", "424B8",
}
REG_A_FORMS = {
    "1-A", "1-A/A", "1-A POS", "1-K", "1-K/A", "1-U",
    "253G1", "253G2", "253G3", "253G4",
}
TARGET_FORMS = REGISTRATION_FORMS | STATE_FORMS | PROSPECTUS_FORMS | REG_A_FORMS

DECLARED_WAVE2_RECONCILIATION_FORMS = {
    "8-K", "8-K/A", "6-K", "6-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A",
    "20-F", "20-F/A", "40-F", "40-F/A", "PRE 14A", "DEF 14A",
    "PRE 14C", "DEF 14C",
}

# Known capital-relevant SEC families intentionally outside the W1 allowlist.
# Naming them here prevents a bounded registration/issuance slice from being
# presented as complete merely because broad periodic reconciliation is also
# disclosed. Later waves can promote forms from this set with their own routing
# and corpus gates.
CAPITAL_RELEVANT_DECLARED_NOT_COLLECTED = {
    "S-8", "S-8 POS", "S-11", "S-11/A", "S-4", "S-4/A",
    "F-4", "F-4/A", "F-6", "F-6/A", "F-6EF", "F-6 POS",
    "N-2", "N-2/A", "N-2ASR", "N-2 POSASR",
    "S-3D", "F-3D", "424B2", "424B6", "424H", "424H/A", "424I",
}

FORM_POLICY = {
    "policy_version": "capital-structure-sec-form-policy/1.1.0",
    "wave1_discovery": sorted(TARGET_FORMS),
    "wave2_declared_not_collected": sorted(DECLARED_WAVE2_RECONCILIATION_FORMS),
    "capital_relevant_declared_not_collected": sorted(
        CAPITAL_RELEVANT_DECLARED_NOT_COLLECTED
    ),
}

LOOKBACK_DAYS_FIRST = 90
LOOKBACK_DAYS_NIGHTLY = 7
MAX_FILINGS_PER_RUN = 200
RETRIEVAL_QUEUE_AGING_DAYS = 7
INDEX_NOT_PUBLISHED_GRACE_DAYS = 7
PACE_SECONDS = 0.12
GROUP = "capital_structure"

_DISCOVERY_COLUMNS = [
    "accession", "cik", "ticker", "company_name", "form", "filing_date",
    "file_path", "canonical_url", "_first_seen",
]
_COVERAGE_COLUMNS = [
    "index_date", "status", "target_count", "attempt_count", "last_attempt_at",
    "last_error", "policy_version",
]
_ATTEMPT_COLUMNS = [
    "attempt_id", "accession", "source_id", "canonical_url", "attempted_at",
    "state", "error", "content_sha256",
]
_MANIFEST_COLUMNS = [
    "schema", "manifest_id", "source_system", "source_id", "issuer", "filing",
    "document", "retrieval", "storage", "rights", "privacy", "parser", "spans",
]


class IndexNotPublished(RuntimeError):
    """A historical SEC daily-index object has no published archive object."""

    def __init__(self, value: date, status_code: int) -> None:
        self.index_date = value
        self.status_code = status_code
        super().__init__(f"SEC daily index HTTP {status_code}: {value}")


@lru_cache(maxsize=512)
def is_sec_calendar_closed(value: date) -> bool:
    """Return true for an observed US federal weekday closure."""
    holidays = USFederalHolidayCalendar().holidays(
        start=pd.Timestamp(value), end=pd.Timestamp(value)
    )
    return not holidays.empty


def _qtr(value: date) -> int:
    return (value.month - 1) // 3 + 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _data_dir() -> Path:
    from lib import config
    return config.data_dir() / GROUP


def _ua() -> str:
    try:
        from collectors.edgar import _cfg
        return _cfg()["user_agent"]
    except Exception:  # noqa: BLE001
        return "Macro Dashboard research longr2512@gmail.com"


def _cik_map() -> dict[int, str]:
    try:
        from collectors.edgar_8k import _company_tickers
        data = _company_tickers() or {}
    except Exception:  # noqa: BLE001
        return {}
    out: dict[int, str] = {}
    for item in (data.values() if isinstance(data, dict) else data):
        try:
            cik = int(item.get("cik_str"))
            ticker = str(item.get("ticker") or "").upper()
        except (TypeError, ValueError):
            continue
        if ticker:
            out.setdefault(cik, ticker)
    return out


def parse_form_index(text: str, *, target_forms: set[str] | None = None) -> list[dict]:
    """Parse target rows from an EDGAR ``form.YYYYMMDD.idx`` file.

    The function is pure and retains the archive path so the exact source can be
    retrieved later. The response structure and every filing row are validated
    before an empty target result can be treated as a successful zero-target day.
    """
    wanted = TARGET_FORMS if target_forms is None else target_forms
    lowered = text[:16384].lower()
    if any(marker in lowered for marker in ("<!doctype html", "<html", "<body")):
        raise ValueError("SEC form index response is HTML, not a daily index")
    lines = text.splitlines()
    separator_index = next(
        (
            index
            for index, line in enumerate(lines)
            if len(line.strip()) >= 20 and set(line.strip()) == {"-"}
        ),
        None,
    )
    if separator_index is None:
        raise ValueError("SEC form index is missing its data separator")
    header_lines = [line.strip() for line in lines[:separator_index] if line.strip()]
    header = re.sub(r"\s+", " ", " ".join(header_lines[-2:])).strip()
    if not re.search(
        r"Form Type\s+Company Name\s+CIK\s+Date Filed\s+File\s*Name$",
        header,
        re.I,
    ):
        raise ValueError("SEC form index has an invalid column header")

    rows: list[dict] = []
    data_row_count = 0
    for line_number, line in enumerate(lines[separator_index + 1:], separator_index + 2):
        if not line.strip():
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5:
            raise ValueError(f"SEC form index row {line_number} has fewer than five columns")
        form = parts[0].strip().upper()
        company_name = "  ".join(part.strip() for part in parts[1:-3]).strip()
        cik = parts[-3].strip()
        filed = parts[-2].strip()
        file_path = parts[-1].strip().lstrip("/")
        valid_shape = (
            bool(form)
            and bool(company_name)
            and cik.isdigit()
            and len(filed) == 8
            and filed.isdigit()
            and file_path.lower().startswith("edgar/data/")
            and file_path.lower().endswith(".txt")
        )
        try:
            datetime.strptime(filed, "%Y%m%d")
        except ValueError:
            valid_shape = False
        if not valid_shape:
            raise ValueError(f"SEC form index row {line_number} is malformed")
        data_row_count += 1
        if form not in wanted:
            continue
        accession = Path(file_path).stem
        rows.append({
            "accession": accession,
            "cik": cik.zfill(10),
            "company_name": company_name,
            "form": form,
            "filing_date": f"{filed[:4]}-{filed[4:6]}-{filed[6:]}",
            "file_path": file_path,
            "canonical_url": _ARCHIVES + file_path,
        })
    if data_row_count == 0:
        raise ValueError("SEC form index contains no filing rows")
    return rows


_HEADER_FIELD_RE = {
    "accepted_at": re.compile(br"<ACCEPTANCE-DATETIME>\s*(\d{14})", re.I),
    "file_number": re.compile(br"<FILE-NUMBER>\s*([^\r\n<]+)", re.I),
}
_DOCUMENT_RE = re.compile(br"<DOCUMENT>(.*?)</DOCUMENT>", re.I | re.S)


@dataclass(frozen=True)
class SubmissionDocument:
    sequence: str | None
    document_type: str | None
    filename: str | None
    description: str | None
    raw: bytes


@dataclass(frozen=True)
class SubmissionBundle:
    accepted_at: str | None
    file_number: str | None
    documents: tuple[SubmissionDocument, ...]


@dataclass(frozen=True)
class DocumentInspection:
    """Truthful parser disposition for one exact retained byte stream."""

    media_type: str
    parser_eligibility: str
    corruption_state: str
    parser_version: str = "sec-source-inspector/1.0.0"


def _sgml_value(block: bytes, name: bytes) -> str | None:
    match = re.search(br"<" + name + br">\s*([^\r\n<]+)", block, re.I)
    if not match:
        return None
    return match.group(1).decode("utf-8", errors="replace").strip() or None


def parse_submission(raw: bytes) -> SubmissionBundle:
    """Parse SEC submission header fields and raw ``<DOCUMENT>`` blocks."""
    accepted_at = None
    accepted_match = _HEADER_FIELD_RE["accepted_at"].search(raw)
    if accepted_match:
        stamp = accepted_match.group(1).decode("ascii")
        try:
            # The legacy SGML ACCEPTANCE-DATETIME clock is SEC Eastern time,
            # unlike the UTC-stamped submissions JSON API. Convert explicitly;
            # labelling this field UTC would make public-clock replays 4–5h early.
            accepted_at = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(
                tzinfo=ZoneInfo("America/New_York")
            ).astimezone(timezone.utc).isoformat()
        except ValueError:
            accepted_at = None
    file_number_match = _HEADER_FIELD_RE["file_number"].search(raw)
    file_number = (
        file_number_match.group(1).decode("utf-8", errors="replace").strip()
        if file_number_match else None
    )
    documents = tuple(
        SubmissionDocument(
            sequence=_sgml_value(block, b"SEQUENCE"),
            document_type=_sgml_value(block, b"TYPE"),
            filename=_sgml_value(block, b"FILENAME"),
            description=_sgml_value(block, b"DESCRIPTION"),
            raw=block,
        )
        for block in _DOCUMENT_RE.findall(raw)
    )
    return SubmissionBundle(
        accepted_at=accepted_at,
        file_number=file_number,
        documents=documents,
    )


def select_relevant_documents(
    form: str, documents: Iterable[SubmissionDocument]
) -> list[tuple[str, SubmissionDocument]]:
    """Select a unique primary document plus capital-term-bearing exhibits."""
    docs = list(documents)
    normalized_form = form.upper().replace("/A", "")
    primary_index: int | None = None
    for index, doc in enumerate(docs):
        doc_type = (doc.document_type or "").upper()
        if doc_type == form.upper() or doc_type.replace("/A", "") == normalized_form:
            primary_index = index
            break

    selected: list[tuple[str, SubmissionDocument]] = []
    for index, doc in enumerate(docs):
        doc_type = (doc.document_type or "").upper()
        role = None
        if index == primary_index:
            role = "primary"
        elif re.match(r"^EX-(3|4|10|99)(\.|$)", doc_type):
            role = "exhibit"
        if role:
            selected.append((role, doc))
    return selected


_TEXT_PAYLOAD_RE = re.compile(br"<TEXT>\s*(.*?)(?:</TEXT>|$)", re.I | re.S)
_HTML_SUFFIXES = {".htm", ".html", ".xhtml"}
_XML_SUFFIXES = {".xml", ".xsd", ".xbrl"}
_PLAIN_TEXT_SUFFIXES = {".txt", ".text", ".sgml", ".csv"}
_UNSUPPORTED_MEDIA_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".zip": "application/zip",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _document_payload(raw: bytes) -> bytes:
    match = _TEXT_PAYLOAD_RE.search(raw)
    return (match.group(1) if match else raw).strip()


def _readable_text(raw: bytes) -> bool:
    if not raw or b"\x00" in raw:
        return False
    control_count = sum(byte < 32 and byte not in (9, 10, 13) for byte in raw)
    if control_count / len(raw) > 0.01:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw.decode("cp1252")
        except UnicodeDecodeError:
            return False
    return True


def _sniff_binary_media(payload: bytes) -> str | None:
    probe = payload.lstrip()
    upper = probe[:32].upper()
    if probe.startswith(b"%PDF-") or upper.startswith(b"<PDF>"):
        return "application/pdf"
    if probe.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if probe.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if probe.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if probe.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if probe.startswith(b"PK\x03\x04"):
        return "application/zip"
    return None


def inspect_source_document(
    raw: bytes, *, filename: str | None, document_role: str
) -> DocumentInspection:
    """Classify exact retained bytes without treating every filing as text.

    HTML, XML, and plain text are parser-eligible when readable. Recognized
    binary formats are retained but deferred; an extension/header conflict is
    marked suspect rather than silently called clean. Complete submissions have
    an additional SGML-structure check so an HTML error page cannot masquerade
    as usable filing evidence.
    """
    if not raw:
        return DocumentInspection(
            media_type="application/octet-stream",
            parser_eligibility="deferred",
            corruption_state="corrupt",
        )

    if document_role == "complete_submission":
        readable = _readable_text(raw)
        if not readable:
            return DocumentInspection(
                media_type="application/octet-stream",
                parser_eligibility="deferred",
                corruption_state="unreadable",
            )
        open_count = len(re.findall(br"<DOCUMENT>", raw, re.I))
        close_count = len(re.findall(br"</DOCUMENT>", raw, re.I))
        structurally_complete = open_count > 0 and open_count == close_count
        return DocumentInspection(
            media_type="text/plain",
            parser_eligibility="eligible" if structurally_complete else "deferred",
            corruption_state="clean" if structurally_complete else "suspect",
        )

    payload = _document_payload(raw)
    suffix = Path(filename or "").suffix.lower()
    binary_media = _sniff_binary_media(payload)
    suffix_binary_media = _UNSUPPORTED_MEDIA_BY_SUFFIX.get(suffix)
    suffix_text_media = (
        "text/html" if suffix in _HTML_SUFFIXES
        else "application/xml" if suffix in _XML_SUFFIXES
        else "text/plain" if suffix in _PLAIN_TEXT_SUFFIXES
        else None
    )
    declared_media = suffix_binary_media or suffix_text_media
    if binary_media or suffix_binary_media:
        media_type = binary_media or suffix_binary_media or "application/octet-stream"
        return DocumentInspection(
            media_type=media_type,
            parser_eligibility="deferred",
            corruption_state=(
                "clean"
                if binary_media and (not declared_media or binary_media == declared_media)
                else "suspect"
            ),
        )

    readable = _readable_text(payload)
    if not readable:
        return DocumentInspection(
            media_type="application/octet-stream",
            parser_eligibility="deferred",
            corruption_state="unreadable",
        )

    probe = payload.lstrip().lower()
    looks_html = any(
        marker in probe[:4096]
        for marker in (b"<!doctype html", b"<html", b"<body")
    )
    looks_xml = probe.startswith(b"<?xml") or any(
        probe.startswith(marker) for marker in (b"<xbrl", b"<xs:schema", b"<schema")
    )
    if suffix in _HTML_SUFFIXES or looks_html:
        has_markup = b"<" in payload and b">" in payload
        return DocumentInspection(
            "text/html",
            "eligible" if has_markup else "deferred",
            "clean" if has_markup else "suspect",
        )
    if suffix in _XML_SUFFIXES or looks_xml:
        has_markup = b"<" in payload and b">" in payload
        return DocumentInspection(
            "application/xml",
            "eligible" if has_markup else "deferred",
            "clean" if has_markup else "suspect",
        )
    return DocumentInspection("text/plain", "eligible", "clean")


def retrieval_priority(form: str) -> int:
    """Bounded evidence-fetch priority; lower is more capital-structure specific.

    424B2 is intentionally last: the form contains a very large structured-note
    population and must not starve registrations, withdrawals, EFFECT notices,
    or equity prospectuses inside the nightly budget.
    """
    normalized = str(form).upper()
    if normalized in STATE_FORMS or normalized in REGISTRATION_FORMS:
        return 0
    if normalized in (PROSPECTUS_FORMS - {"424B2"}) or normalized in REG_A_FORMS:
        return 1
    if normalized == "424B2":
        return 2
    return 3


def due_index_dates(
    coverage: pd.DataFrame,
    *,
    today: date,
    lookback_days: int,
    full_history: bool = False,
) -> list[date]:
    """Return due business-day indexes, including retries older than lookback.

    ``full_history`` only bypasses completed-day suppression inside the caller's
    bounded lookback. It does not enumerate the historical EDGAR archive.
    """
    complete: set[str] = set()
    if not coverage.empty and not full_history:
        policy_current = (
            coverage["policy_version"].astype(str).eq(FORM_POLICY["policy_version"])
            if "policy_version" in coverage.columns
            else pd.Series(False, index=coverage.index)
        )
        complete = set(
            coverage.loc[
                coverage["status"].isin({"complete", "not_published"})
                & policy_current,
                "index_date",
            ].astype(str)
        )
    window = [
        current
        for offset in range(lookback_days)
        if (current := today - timedelta(days=offset)).weekday() < 5
        and current.isoformat() not in complete
    ]
    carry_dates: set[date] = set()
    if not coverage.empty and {"status", "index_date"}.issubset(coverage.columns):
        retry_mask = coverage["status"].astype(str).eq("retry")
        policy_stale = (
            ~coverage["policy_version"].astype(str).eq(FORM_POLICY["policy_version"])
            if "policy_version" in coverage.columns
            else pd.Series(True, index=coverage.index)
        )
        stale_terminal_mask = (
            coverage["status"].isin({"complete", "not_published"}) & policy_stale
        )
        for raw_date in coverage.loc[
            retry_mask | stale_terminal_mask, "index_date"
        ].astype(str):
            try:
                carry_date = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValueError(f"invalid retry index_date {raw_date!r}") from exc
            if carry_date <= today and carry_date.weekday() < 5:
                carry_dates.add(carry_date)
    # Oldest failed indexes run first so a rolling seven-day window cannot age
    # a transient failure out of the collection schedule forever.
    retries_first = sorted(carry_dates)
    return retries_first + [value for value in window if value not in carry_dates]


def select_retrieval_queue(
    discovery: pd.DataFrame,
    *,
    have_complete: set[str],
    max_filings: int,
    now: datetime,
) -> pd.DataFrame:
    """Select a bounded queue with hard form priority and within-lane aging."""
    columns = list(discovery.columns)
    queue = discovery.loc[
        discovery["form"].astype(str).isin(TARGET_FORMS)
        & ~discovery["accession"].astype(str).isin(have_complete)
    ].copy()
    if queue.empty or max_filings <= 0:
        return queue.head(0)[columns]

    now_stamp = pd.Timestamp(now)
    now_stamp = (
        now_stamp.tz_localize("UTC")
        if now_stamp.tzinfo is None
        else now_stamp.tz_convert("UTC")
    )
    first_seen = pd.to_datetime(queue["_first_seen"], errors="coerce", utc=True)
    aging_cutoff = now_stamp - pd.Timedelta(days=RETRIEVAL_QUEUE_AGING_DAYS)
    queue["_priority"] = queue["form"].map(retrieval_priority)
    queue["_aged"] = first_seen.isna() | first_seen.le(aging_cutoff)
    queue["_aged_seen"] = first_seen.where(queue["_aged"], now_stamp).fillna(
        pd.Timestamp("1970-01-01", tz="UTC")
    )
    queue["_filing_date"] = pd.to_datetime(
        queue["filing_date"], errors="coerce", utc=True
    )
    queue = queue.sort_values(
        ["_priority", "_aged", "_aged_seen", "_filing_date", "accession"],
        ascending=[True, False, True, False, True],
        na_position="last",
        kind="stable",
    )
    return queue.head(max_filings)[columns].reset_index(drop=True)


def _read_table(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"capital-structure store unreadable: {path}: {exc}") from exc


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _validate_source_manifest(record: dict) -> None:
    """Hard-fail before a non-conforming evidence pointer enters the ledger."""
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = Path(__file__).resolve().parents[1] / "contracts" / (
        "capital_structure_source_manifest.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
        key=lambda error: list(error.path),
    )
    if errors:
        joined = "; ".join(error.message for error in errors[:5])
        raise ValueError(f"source manifest contract violation: {joined}")
    validate_manifest_identity(record)


def _append_manifests_strict(
    prior: pd.DataFrame, fresh: list[dict]
) -> pd.DataFrame:
    """Append immutable manifests without hiding identity collisions."""
    prior_records = prior.to_dict(orient="records") if not prior.empty else []
    merged = merge_manifest_ledgers(prior_records, fresh)
    out = pd.DataFrame(merged)
    if out.empty:
        return pd.DataFrame(columns=_MANIFEST_COLUMNS)
    for column in _MANIFEST_COLUMNS:
        if column not in out:
            out[column] = None
    return out[_MANIFEST_COLUMNS].reset_index(drop=True)


def _append_keep_first(
    prior: pd.DataFrame, fresh: list[dict], *, key: str, columns: list[str] | None = None
) -> pd.DataFrame:
    new = pd.DataFrame(fresh)
    if new.empty:
        out = prior.copy()
    elif prior.empty:
        out = new
    else:
        out = pd.concat([prior, new], ignore_index=True)
    if out.empty:
        return pd.DataFrame(columns=columns or list(prior.columns))
    out = out.drop_duplicates(key, keep="first").reset_index(drop=True)
    if columns:
        for column in columns:
            if column not in out:
                out[column] = None
        out = out[columns]
    return out


def _eligible_complete_accessions(manifests: pd.DataFrame) -> set[str]:
    """Return filings with retained, readable complete-submission evidence."""
    required = {"filing", "document", "parser"}
    if manifests.empty or not required.issubset(manifests.columns):
        return set()
    complete: set[str] = set()
    for filing, document, parser in zip(
        manifests["filing"], manifests["document"], manifests["parser"]
    ):
        if not all(isinstance(value, dict) for value in (filing, document, parser)):
            continue
        if (
            document.get("document_role") == "complete_submission"
            and parser.get("eligibility") == "eligible"
            and parser.get("corruption_state") == "clean"
        ):
            complete.add(str(filing.get("accession")))
    return complete


def _next_bundle_document_version(manifests: pd.DataFrame, accession: str) -> int:
    """Advance one accession-wide version for a closed manifest bundle."""
    if manifests.empty or not {"filing", "document"}.issubset(manifests.columns):
        return 1
    latest = 0
    for filing, document in zip(manifests["filing"], manifests["document"]):
        if not isinstance(filing, dict) or str(filing.get("accession")) != accession:
            continue
        if not isinstance(document, dict):
            raise ValueError(f"{accession}: retained manifest has no document object")
        raw_version = document.get("document_version")
        try:
            version = int(raw_version)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{accession}: invalid retained document_version {raw_version!r}"
            ) from exc
        if version < 1:
            raise ValueError(
                f"{accession}: invalid retained document_version {raw_version!r}"
            )
        latest = max(latest, version)
    return latest + 1


class SecCapitalStructureAdapter(Adapter):
    """Discover and retain immutable SEC capital-structure source evidence."""

    name = "sec_capital_structure"
    group = GROUP
    stale_after_days = 4

    def __init__(
        self,
        *,
        source_store=None,
        now_fn: Callable[[], datetime] = _utc_now,
        max_filings_per_run: int = MAX_FILINGS_PER_RUN,
    ) -> None:
        self._injected_source_store = source_store
        self._now_fn = now_fn
        self.max_filings_per_run = max(0, int(max_filings_per_run))

    def _source_store(self):
        if self._injected_source_store is not None:
            return self._injected_source_store
        from engine.capital_structure.source_store import build_source_store
        return build_source_store()

    def _fetch_index(self, value: date, ua: str) -> str:
        url = _DAILY_IDX.format(yr=value.year, q=_qtr(value), ds=value.strftime("%Y%m%d"))
        try:
            response = self.http_get(
                # Index misses have their own persisted retry/grace policy; do
                # not pay the generic exponential retry cost for each holiday.
                url, retries=1, timeout=30,
                headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
            )
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code == 404:
                raise IndexNotPublished(value, status_code) from exc
            raise
        return response.text

    def _fetch_submission(self, url: str, ua: str) -> bytes:
        response = self.http_get(
            url, retries=3, timeout=60,
            headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
        )
        return response.content

    @staticmethod
    def _manifest_record(
        *,
        discovery: dict,
        bundle: SubmissionBundle,
        source_id: str,
        canonical_url: str,
        document_name: str,
        document_type: str,
        document_role: str,
        sequence: str | None,
        raw: bytes,
        receipt,
        inspection: DocumentInspection,
        retrieved_at: str,
        first_seen_at: str,
        document_version: int,
        parent_manifest_id: str | None,
    ) -> dict:
        digest = hashlib.sha256(raw).hexdigest()
        from engine.capital_structure.source_store import object_key_for_sha256

        if (
            getattr(receipt, "sha256", None) != digest
            or getattr(receipt, "byte_length", None) != len(raw)
            or getattr(receipt, "object_key", None) != object_key_for_sha256(digest)
            or getattr(receipt, "media_type", None) != inspection.media_type
        ):
            raise ValueError("source-store receipt does not bind the exact manifest bytes")
        ticker = discovery.get("ticker")
        record = {
            "schema": "capital_structure.source_manifest/v1",
            "source_system": "sec_edgar",
            "source_id": source_id,
            "issuer": {
                "issuer_id": f"sec:cik:{str(discovery['cik']).zfill(10)}",
                "cik": str(discovery["cik"]).lstrip("0") or "0",
                "ticker": ticker if isinstance(ticker, str) and ticker else None,
                "aliases": [str(discovery.get("company_name") or "")]
                if discovery.get("company_name") else [],
            },
            "filing": {
                "accession": discovery["accession"],
                "form": discovery["form"],
                "filing_date": discovery["filing_date"],
                "accepted_at": bundle.accepted_at,
                "file_number": bundle.file_number,
            },
            "document": {
                "canonical_url": canonical_url,
                "document_name": document_name,
                "document_type": document_type,
                "document_role": document_role,
                "sequence": sequence,
                "media_type": inspection.media_type,
                "byte_length": len(raw),
                "document_version": document_version,
                "content_sha256": digest,
                "parent_manifest_id": parent_manifest_id,
                "root_locator": f"sha256:{digest}",
            },
            "retrieval": {
                "retrieved_at": retrieved_at,
                "first_seen_at": first_seen_at,
                "transport_status": "retrieved",
            },
            "storage": {
                "backend": getattr(receipt, "backend", "r2"),
                "store_id": receipt.store_id,
                "object_key": receipt.object_key,
                "content_addressed": True,
                "retention_state": "retained",
            },
            "rights": {
                "redistribution_class": "public_source_link",
                "attribution_required": True,
                "license_note": "United States SEC EDGAR public filing",
            },
            # Public filings routinely contain officer/director names and signatures.
            # Public availability does not make that personal-data flag false.
            "privacy": {"classification": "public", "contains_personal_data": True},
            "parser": {
                "eligibility": inspection.parser_eligibility,
                "corruption_state": inspection.corruption_state,
                "parser_version": inspection.parser_version,
            },
            "spans": [{
                "span_id": f"root:{digest}",
                "locator_type": "document",
                "locator": f"bytes:0-{len(raw)}",
                "text_sha256": digest,
            }],
        }
        record["manifest_id"] = manifest_id_for(record)
        return record

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        root = _data_dir()
        discovery_path = root / "discovery.parquet"
        coverage_path = root / "index_coverage.parquet"
        attempts_path = root / "retrieval_attempts.parquet"
        manifests_path = root / "source_manifest.parquet"

        discovery = _read_table(discovery_path, _DISCOVERY_COLUMNS)
        coverage = _read_table(coverage_path, _COVERAGE_COLUMNS)
        attempts = _read_table(attempts_path, _ATTEMPT_COLUMNS)
        manifests = _read_table(manifests_path, _MANIFEST_COLUMNS)
        if not manifests.empty:
            validate_manifest_ledger(manifests.to_dict(orient="records"))
        now = self._now_fn().astimezone(timezone.utc)
        now_iso = _iso(now)
        # ``full_history`` is the Adapter refresh flag; for this bounded W1
        # collector it revalidates the 90-day bootstrap, not all EDGAR history.
        lookback = (
            LOOKBACK_DAYS_FIRST
            if discovery.empty or full_history
            else LOOKBACK_DAYS_NIGHTLY
        )
        ua = _ua()
        cik_tickers = _cik_map()

        new_discovery: list[dict] = []
        coverage_updates: list[dict] = []
        for index_date in due_index_dates(
            coverage, today=now.date(), lookback_days=lookback, full_history=full_history
        ):
            prior_attempts = 0
            prior_error = ""
            if not coverage.empty:
                matches = coverage.loc[coverage["index_date"].astype(str) == index_date.isoformat()]
                if not matches.empty:
                    prior_attempts = int(matches.iloc[-1].get("attempt_count") or 0)
                    prior_error = str(matches.iloc[-1].get("last_error") or "")
            if is_sec_calendar_closed(index_date):
                coverage_updates.append({
                    "index_date": index_date.isoformat(),
                    "status": "not_published",
                    "target_count": None,
                    "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now_iso,
                    "last_error": "SEC calendar closure: observed US federal holiday",
                    "policy_version": FORM_POLICY["policy_version"],
                })
                continue
            try:
                rows = parse_form_index(self._fetch_index(index_date, ua))
                for row in rows:
                    cik_int = int(row["cik"])
                    row["ticker"] = cik_tickers.get(cik_int)
                    row["_first_seen"] = now_iso
                    new_discovery.append(row)
                coverage_updates.append({
                    "index_date": index_date.isoformat(), "status": "complete",
                    "target_count": len(rows), "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now_iso, "last_error": None,
                    "policy_version": FORM_POLICY["policy_version"],
                })
            except IndexNotPublished as exc:
                is_aged = index_date <= (
                    now.date() - timedelta(days=INDEX_NOT_PUBLISHED_GRACE_DAYS)
                )
                prior_was_missing_status = (
                    "IndexNotPublished" in prior_error
                    and "HTTP 404" in prior_error
                )
                terminal_missing = is_aged and prior_was_missing_status
                coverage_updates.append({
                    "index_date": index_date.isoformat(),
                    "status": "not_published" if terminal_missing else "retry",
                    "target_count": None,
                    "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now_iso,
                    "last_error": f"{type(exc).__name__}: {exc}",
                    "policy_version": FORM_POLICY["policy_version"],
                })
            except Exception as exc:  # noqa: BLE001
                if is_connection_error(exc):
                    raise
                coverage_updates.append({
                    "index_date": index_date.isoformat(), "status": "retry",
                    "target_count": None, "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now_iso, "last_error": f"{type(exc).__name__}: {exc}",
                    "policy_version": FORM_POLICY["policy_version"],
                })
            time.sleep(PACE_SECONDS)

        discovery = _append_keep_first(
            discovery, new_discovery, key="accession", columns=_DISCOVERY_COLUMNS
        )
        if coverage_updates:
            updates = pd.DataFrame(coverage_updates)
            coverage = pd.concat([coverage, updates], ignore_index=True)
            coverage = coverage.drop_duplicates("index_date", keep="last")
            coverage = coverage[_COVERAGE_COLUMNS].sort_values("index_date").reset_index(drop=True)
        _atomic_write(discovery, discovery_path)
        _atomic_write(coverage, coverage_path)

        # Suspect/deferred complete-submission bytes (for example an SEC error
        # page) remain retryable and cannot permanently close the queue item.
        have_complete = _eligible_complete_accessions(manifests)

        queue = select_retrieval_queue(
            discovery,
            have_complete=have_complete,
            max_filings=self.max_filings_per_run,
            now=now,
        )

        source_store = self._source_store()
        new_manifests: list[dict] = []
        new_attempts: list[dict] = []
        for _, series in queue.iterrows():
            row = series.to_dict()
            accession = str(row["accession"])
            url = str(row["canonical_url"])
            source_id = f"{accession}:0:complete-submission.txt"
            bundle_version = _next_bundle_document_version(manifests, accession)
            attempted_at = _iso(self._now_fn())
            try:
                if source_store is None:
                    raise RuntimeError("content-addressed source store unavailable")
                raw = self._fetch_submission(url, ua)
                if not raw:
                    raise RuntimeError("empty SEC submission")
                bundle = parse_submission(raw)
                complete_inspection = inspect_source_document(
                    raw,
                    filename="complete-submission.txt",
                    document_role="complete_submission",
                )
                receipt = source_store.put_verified(
                    raw, media_type=complete_inspection.media_type
                )
                if receipt is None:
                    raise RuntimeError("source-store write/readback verification failed")
                stored_children: list[tuple] = []
                for role, document in select_relevant_documents(
                    str(row["form"]), bundle.documents
                ):
                    filename = (
                        document.filename
                        or f"document-{document.sequence or 'unknown'}.txt"
                    )
                    inspection = inspect_source_document(
                        document.raw, filename=filename, document_role=role
                    )
                    doc_receipt = source_store.put_verified(
                        document.raw, media_type=inspection.media_type
                    )
                    if doc_receipt is None:
                        raise RuntimeError(
                            "source-store verification failed for "
                            f"{document.filename or document.sequence}"
                        )
                    stored_children.append(
                        (role, document, filename, inspection, doc_receipt)
                    )

                # Both clocks begin only after every selected object's write and
                # readback has succeeded. A request-start timestamp would make
                # evidence appear system-visible before durable retention.
                retained_at = _iso(self._now_fn())
                filing_manifests: list[dict] = []
                complete_manifest = self._manifest_record(
                    discovery=row, bundle=bundle, source_id=source_id,
                    canonical_url=url, document_name="complete-submission.txt",
                    document_type=str(row["form"]), document_role="complete_submission",
                    sequence="0", raw=raw, receipt=receipt, retrieved_at=retained_at,
                    inspection=complete_inspection,
                    first_seen_at=retained_at, document_version=bundle_version,
                    parent_manifest_id=None,
                )
                _validate_source_manifest(complete_manifest)
                filing_manifests.append(complete_manifest)
                parent_id = complete_manifest["manifest_id"]
                for role, document, filename, inspection, doc_receipt in stored_children:
                    document_manifest = self._manifest_record(
                        discovery=row, bundle=bundle,
                        source_id=f"{accession}:{document.sequence or 'unknown'}:{filename}",
                        # These exact bytes are the SGML document segment retained
                        # from the complete submission. Point at that source plus a
                        # stable segment fragment rather than pretending we fetched
                        # the separately served filename byte-for-byte.
                        canonical_url=f"{url}#document={document.sequence or 'unknown'}",
                        document_name=filename,
                        document_type=document.document_type or "UNKNOWN",
                        document_role=role, sequence=document.sequence,
                        raw=document.raw, receipt=doc_receipt, retrieved_at=retained_at,
                        inspection=inspection,
                        first_seen_at=retained_at, document_version=bundle_version,
                        parent_manifest_id=parent_id,
                    )
                    _validate_source_manifest(document_manifest)
                    filing_manifests.append(document_manifest)
                # All selected evidence must verify before any manifest for the
                # filing is committed. A partially stored bundle stays retryable.
                new_manifests.extend(filing_manifests)
                if (
                    complete_inspection.parser_eligibility == "eligible"
                    and complete_inspection.corruption_state == "clean"
                ):
                    state, error = "stored", None
                else:
                    state = "stored_parser_deferred"
                    error = (
                        "complete submission retained but parser deferred: "
                        f"eligibility={complete_inspection.parser_eligibility}; "
                        f"corruption_state={complete_inspection.corruption_state}"
                    )
                content_hash = hashlib.sha256(raw).hexdigest()
            except Exception as exc:  # noqa: BLE001
                state = "storage_deferred" if "store" in str(exc).lower() else "transient_error"
                error = f"{type(exc).__name__}: {exc}"
                content_hash = None
                log.warning("sec_capital_structure: %s deferred: %s", accession, error)
            attempt_id = hashlib.sha256(
                f"{source_id}|{attempted_at}|{state}".encode("utf-8")
            ).hexdigest()
            new_attempts.append({
                "attempt_id": attempt_id, "accession": accession, "source_id": source_id,
                "canonical_url": url, "attempted_at": attempted_at, "state": state,
                "error": error, "content_sha256": content_hash,
            })
            time.sleep(PACE_SECONDS)

        manifests = _append_manifests_strict(manifests, new_manifests)
        attempts = _append_keep_first(
            attempts, new_attempts, key="attempt_id", columns=_ATTEMPT_COLUMNS
        )
        _atomic_write(manifests, manifests_path)
        _atomic_write(attempts, attempts_path)

        successful = sum(1 for attempt in new_attempts if attempt["state"] == "stored")
        retained_after_run = _eligible_complete_accessions(manifests)
        pending_after_run = discovery.loc[
            discovery["form"].astype(str).isin(TARGET_FORMS)
            & ~discovery["accession"].astype(str).isin(retained_after_run)
        ]
        heartbeat = pd.DataFrame(
            {
                "index_days_complete": [sum(1 for row in coverage_updates if row["status"] == "complete")],
                "discovered": [len(new_discovery)],
                "retrieved": [successful],
                "deferred": [len(new_attempts) - successful],
                "backlog": [len(pending_after_run)],
            },
            index=[pd.Timestamp(now.date())],
        )
        return {"sec_evidence__ingest": heartbeat}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    SecCapitalStructureAdapter().fetch()
