#!/usr/bin/env python3
"""Price-blind Cell B V2 SEC source-capacity census.

This is a source adjudicator, not an event study.  Its population is the exact
non-amended Form 8-K denominator in official quarterly EDGAR master indexes for
2022-03-01 through 2026-06-30.  It never calls SEC full-text search and never
opens a market-data or prior Cell-B result path.

The network run is deliberately resumable under a caller-owned scratch root.
Only immutable SEC archive bytes, official Submissions metadata, the repository's
identity masters, and deterministic cache receipts enter the result.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.edgar_forensics import (  # noqa: E402
    SecForensicsCollector,
    full_master_index_url,
)
from engine.session_digest import session_window_et  # noqa: E402
from lib import nyse_calendar  # noqa: E402


SCHEMA = "cell_b.buyback_source_census.v2"
PROTOCOL = "cell_b_buyback_incorporation_preregistration.v2"
FAMILY = "standalone_new_dollar_buyback_authorization_closed_market.v2"
PARSER_VERSION = "cell-b-v2-buyback-source-census/2.0.0"
START = date(2022, 3, 1)
END = date(2026, 6, 30)
DEV_END = date(2024, 12, 31)
CONFIRM_START = date(2025, 1, 1)
CONFIRM_END = date(2025, 12, 31)
REPLICATION_START = date(2026, 1, 1)
REPLICATION_END = END
SEC_ARCHIVES = "https://www.sec.gov/Archives/"
SEC_DATA = "https://data.sec.gov/submissions/"
ET = ZoneInfo("America/New_York")

VERDICTS = frozenset(
    {
        "SOURCE_CENSUS_CENTER_CAPACITY_PASS",
        "SOURCE_CENSUS_UNDERPOWERED",
        "SOURCE_CENSUS_CLOCK_BLOCKED",
        "SOURCE_CENSUS_IDENTITY_OR_RIGHTS_BLOCKED",
    }
)

REFUSALS = (
    "AMENDMENT_OR_NON_8K",
    "NOT_NEW_AUTHORIZATION",
    "INCREASE_EXTENSION_RENEWAL_OR_REMAINING",
    "AMOUNT_UNESTIMABLE",
    "TENDER_ASR_OR_NON_DISCRETIONARY",
    "DEBT_PREFERRED_OR_EMPLOYEE_WITHHOLDING",
    "COMPLETED_PURCHASE_ONLY",
    "FINANCIAL_ISSUER",
    "NON_US_COMMON_OPERATING_ISSUER",
    "BUNDLED_EARNINGS_RESULTS_OR_GUIDANCE",
    "OVERLAP_MA_OR_MATERIAL_AGREEMENT",
    "OVERLAP_FINANCING",
    "OVERLAP_MANAGEMENT",
    "OVERLAP_RESTRUCTURING",
    "OVERLAP_REGULATORY_OR_CLINICAL",
    "SOURCE_ROOT_UNRESOLVED",
    "CLOCK_UNESTIMABLE",
    "INTRADAY_PUBLICATION",
    "IDENTITY_UNESTIMABLE",
    "RIGHTS_UNESTIMABLE",
)

_ITEM_SCREEN = frozenset({"7.01", "8.01"})
_ITEM_REFUSALS = (
    (frozenset({"2.02"}), "BUNDLED_EARNINGS_RESULTS_OR_GUIDANCE"),
    (frozenset({"1.01", "2.01"}), "OVERLAP_MA_OR_MATERIAL_AGREEMENT"),
    (frozenset({"2.03", "3.02"}), "OVERLAP_FINANCING"),
    (frozenset({"5.02"}), "OVERLAP_MANAGEMENT"),
    (frozenset({"2.05", "2.06"}), "OVERLAP_RESTRUCTURING"),
)

_SEMANTIC_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:board(?:\s+of\s+directors)?\s+)?(?:has\s+)?(?:authorized|approved|adopted|established)\b.{0,360}?\b(?:share|stock|common\s+stock)\s+repurchase\s+(?:program|plan)\b",
        r"\b(?:new|newly\s+authorized)\b.{0,180}?\b(?:share|stock|common\s+stock)\s+repurchase\s+(?:program|plan)\b",
        r"\b(?:share|stock|common\s+stock)\s+repurchase\s+(?:program|plan)\b.{0,240}?\b(?:authorized|approved|adopted)\b",
        r"\b(?:authorized|approved)\s+(?:the\s+)?repurchase\s+of\s+(?:up\s+to\s+)?",
        r"\b(?:authorized|approved)\b.{0,180}?\b(?:share|stock|common\s+stock)\s+repurchase\s+authorization\b",
    )
)
_BUYBACK_MENTION = re.compile(
    r"\b(?:share|stock|common\s+stock)\s+(?:repurchase|buyback)|\brepurchase\s+(?:program|authorization|plan)\b|\brepurchased\b.{0,80}?\b(?:shares?|stock)\b",
    re.IGNORECASE,
)
_NOT_NEW = re.compile(
    r"\b(?:increase(?:d|s)?|additional|expand(?:ed|s)?|extend(?:ed|s|ing)?|extension|renew(?:ed|s|al)?|remaining|replenish(?:ed|es)?)\b",
    re.IGNORECASE,
)
_NON_DISCRETIONARY = re.compile(
    r"\b(?:tender\s+offer|dutch\s+auction|accelerated\s+share\s+repurchase|ASR\s+(?:agreement|program|transaction)|privately\s+negotiated\s+repurchase)\b",
    re.IGNORECASE,
)
_WRONG_INSTRUMENT = re.compile(
    r"\b(?:employee\s+(?:tax\s+)?withholding|withhold(?:ing)?\s+shares|debt\s+repurchase|repurchase\s+of\s+(?:notes|bonds|debt|preferred)|preferred\s+(?:share|stock)\s+repurchase|for\s+preferred\s+(?:shares?|stock))\b",
    re.IGNORECASE,
)
_COMPLETED_ONLY = re.compile(
    r"(?:\b(?:repurchased|purchased)\b.{0,100}?\b(?:during|quarter|year|period|completed)\b|\b(?:during|quarter|year|period)\b.{0,100}?\b(?:repurchased|purchased)\b)",
    re.IGNORECASE,
)
_TEXT_BUNDLES = (
    (
        re.compile(r"\b(?:quarterly|annual|full[- ]year)\s+(?:financial\s+)?results\b|\bearnings\s+(?:release|results)\b|\b(?:revenue|earnings)\s+guidance\b", re.I),
        "BUNDLED_EARNINGS_RESULTS_OR_GUIDANCE",
    ),
    (
        re.compile(r"\b(?:merger|acquisition|acquire[ds]?|definitive\s+agreement|material\s+agreement)\b", re.I),
        "OVERLAP_MA_OR_MATERIAL_AGREEMENT",
    ),
    (
        re.compile(r"\b(?:public\s+offering|private\s+placement|capital\s+raise|credit\s+facility|term\s+loan|notes\s+offering)\b", re.I),
        "OVERLAP_FINANCING",
    ),
    (
        re.compile(r"\b(?:chief\s+executive|chief\s+financial|resignation|appointed|management\s+transition)\b", re.I),
        "OVERLAP_MANAGEMENT",
    ),
    (
        re.compile(r"\b(?:restructuring|reorganization|workforce\s+reduction|impairment\s+charge)\b", re.I),
        "OVERLAP_RESTRUCTURING",
    ),
    (
        re.compile(r"\b(?:FDA|clinical\s+trial|regulatory\s+approval|complete\s+response\s+letter)\b", re.I),
        "OVERLAP_REGULATORY_OR_CLINICAL",
    ),
)
_AMOUNT = re.compile(
    r"(?P<prefix>\b(?:up\s+to|aggregate(?:\s+amount)?\s+of|approximately|about)?\s*)"
    r"(?P<currency>US\s*\$|USD\s*|\$)\s*"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<scale>billion|million|thousand|bn|mm|m|b)?\b",
    re.IGNORECASE,
)
_PERCENT_SHARES = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(?:the\s+)?(?:company(?:'s)?\s+)?(?:outstanding\s+)?(?:common\s+)?shares",
    re.IGNORECASE,
)
_TIMESTAMP = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s*,\s*(?P<year>20\d{2})"
    r".{0,180}?"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?:\s*:\s*\d{2})?\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?)\s*"
    r"(?P<zone>ET|EST|EDT|Eastern\s+(?:Standard|Daylight)\s+Time)\b",
    re.IGNORECASE | re.DOTALL,
)


class CensusError(RuntimeError):
    """A source or invariant prevents a complete deterministic census."""


@dataclass(frozen=True)
class FilingRow:
    cik: str
    company_name: str
    form: str
    filing_date: str
    filename: str
    accession: str


@dataclass(frozen=True)
class IdentityRow:
    economic_issuer_id: str
    security_id: str
    listing_id: str
    mic: str


@dataclass(frozen=True)
class SourceDocument:
    source_document_id: str
    document_type: str
    sequence: str
    filename: str
    description: str
    text: str
    sha256: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(body)
    os.replace(temporary, path)


def _accession_from_filename(filename: str) -> str:
    leaf = filename.rsplit("/", 1)[-1]
    compact = leaf.removesuffix(".txt")
    if not re.fullmatch(r"\d{18}", compact):
        raise CensusError(f"master-index filename has no canonical accession: {filename}")
    return f"{compact[:10]}-{compact[10:12]}-{compact[12:]}"


def parse_master_index_archive(path: Path) -> tuple[list[FilingRow], dict[str, Any]]:
    body = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        if members != ["master.idx"]:
            raise CensusError(f"{path}: expected sole master.idx, got {members!r}")
        index_body = archive.read("master.idx")
    text = index_body.decode("latin-1")
    header = "CIK|Company Name|Form Type|Date Filed|Filename"
    start = text.find(header)
    if start < 0:
        raise CensusError(f"{path}: master.idx header absent")
    rows: list[FilingRow] = []
    for line in text[start + len(header) :].splitlines():
        if not line or line.startswith("-"):
            continue
        fields = line.split("|")
        if len(fields) != 5:
            continue
        cik, company, form, filed, filename = fields
        if form != "8-K" or not (START.isoformat() <= filed <= END.isoformat()):
            continue
        rows.append(
            FilingRow(
                cik=str(cik).zfill(10),
                company_name=company.strip(),
                form=form,
                filing_date=filed,
                filename=filename.strip(),
                accession=_accession_from_filename(filename.strip()),
            )
        )
    rows.sort(key=lambda row: (row.filing_date, row.cik, row.accession))
    receipt = {
        "url": full_master_index_url(int(path.name[:4]), int(re.search(r"QTR([1-4])", path.name).group(1))),
        "archive_bytes": len(body),
        "archive_sha256": sha256_bytes(body),
        "index_bytes": len(index_body),
        "index_sha256": sha256_bytes(index_body),
        "eligible_rows": len(rows),
    }
    return rows, receipt


def build_denominator(master_root: Path) -> tuple[list[FilingRow], list[dict[str, Any]]]:
    archives = sorted(master_root.glob("*-QTR[1-4]-master.zip"))
    expected = [(year, quarter) for year in range(2022, 2027) for quarter in range(1, 5)]
    expected = [(year, quarter) for year, quarter in expected if (year, quarter) <= (2026, 2)]
    actual = [(int(path.name[:4]), int(re.search(r"QTR([1-4])", path.name).group(1))) for path in archives]
    if actual != expected:
        raise CensusError(f"official master-index set mismatch: expected {expected}, got {actual}")
    rows: list[FilingRow] = []
    receipts: list[dict[str, Any]] = []
    for archive in archives:
        part, receipt = parse_master_index_archive(archive)
        rows.extend(part)
        receipts.append(receipt)
    rows.sort(key=lambda row: (row.filing_date, row.cik, row.accession))
    accessions = [row.accession for row in rows]
    if len(accessions) != len(set(accessions)):
        raise CensusError("master-index denominator contains duplicate accessions")
    return rows, receipts


def load_identity_rows(identity_root: Path) -> tuple[dict[str, list[IdentityRow]], dict[str, Any]]:
    issuer_path = identity_root / "issuer_master.parquet"
    security_path = identity_root / "security_master.parquet"
    issuer_frame = pd.read_parquet(issuer_path)
    security_frame = pd.read_parquet(security_path)
    issuers = {
        str(row.cik).zfill(10): str(row.issuer_id)
        for row in issuer_frame.itertuples(index=False)
        if pd.notna(row.cik) and str(getattr(row, "status", "active")) == "active"
    }
    mapped: dict[str, list[IdentityRow]] = defaultdict(list)
    for row in security_frame.itertuples(index=False):
        cik = str(row.issuer_cik).zfill(10) if pd.notna(row.issuer_cik) else ""
        if cik not in issuers or str(row.country) != "US" or str(row.mic) not in {"XNYS", "XNAS", "XASE"}:
            continue
        if pd.notna(getattr(row, "superseded_by", None)):
            continue
        listing = str(row.listing_key)
        mapped[cik].append(
            IdentityRow(
                economic_issuer_id=issuers[cik],
                security_id=str(row.security_id),
                listing_id=listing,
                mic=str(row.mic),
            )
        )
    for cik in mapped:
        mapped[cik] = sorted(set(mapped[cik]), key=lambda item: (item.listing_id, item.security_id))
    receipt = {
        "issuer_master_sha256": sha256_bytes(issuer_path.read_bytes()),
        "security_master_sha256": sha256_bytes(security_path.read_bytes()),
        "resolved_ciks": len(mapped),
        "resolved_listings": sum(len(value) for value in mapped.values()),
    }
    return dict(mapped), receipt


def _column_rows(columns: Mapping[str, Any]) -> list[dict[str, Any]]:
    forms = columns.get("form") or []
    if not isinstance(forms, list):
        return []
    out: list[dict[str, Any]] = []
    keys = (
        "accessionNumber",
        "filingDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
        "primaryDocDescription",
        "items",
    )
    for index in range(len(forms)):
        row = {}
        for key in keys:
            values = columns.get(key) or []
            row[key] = values[index] if isinstance(values, list) and index < len(values) else ""
        if row["accessionNumber"]:
            out.append(row)
    return out


def _overlaps_range(record: Mapping[str, Any]) -> bool:
    start = str(record.get("filingFrom") or "0000-00-00")
    end = str(record.get("filingTo") or "9999-99-99")
    return start <= END.isoformat() and end >= START.isoformat()


def _load_or_fetch_json(
    collector: SecForensicsCollector,
    cache_path: Path,
    *,
    cik: str,
    historical_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if cache_path.is_file():
        body = cache_path.read_bytes()
        source = (
            f"{SEC_DATA}{historical_name}"
            if historical_name
            else f"{SEC_DATA}CIK{cik}.json"
        )
    else:
        if historical_name:
            body, headers = collector.retrieve_historical_submissions_file(
                cik, historical_name, max_response_bytes=32 * 1024 * 1024
            )
            source = str(headers["url"])
        else:
            body, headers = collector.retrieve_current(
                cik, "submissions", max_response_bytes=32 * 1024 * 1024
            )
            source = str(headers["url"])
        _atomic_write(cache_path, body)
    payload = json.loads(body)
    return payload, {"url": source, "bytes": len(body), "sha256": sha256_bytes(body)}


def load_submissions_for_cik(
    collector: SecForensicsCollector,
    cache_root: Path,
    cik: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    current_path = cache_root / f"CIK{cik}.json"
    current, current_receipt = _load_or_fetch_json(collector, current_path, cik=cik)
    top = {
        "entity_type": str(current.get("entityType") or ""),
        "sic": str(current.get("sic") or ""),
        "name": str(current.get("name") or ""),
    }
    rows = _column_rows(((current.get("filings") or {}).get("recent") or {}))
    receipts = [current_receipt]
    files = ((current.get("filings") or {}).get("files") or [])
    for record in files:
        if not isinstance(record, Mapping) or not _overlaps_range(record):
            continue
        name = str(record.get("name") or "")
        if not re.fullmatch(r"CIK\d{10}-submissions-\d{3}\.json", name):
            raise CensusError(f"CIK {cik} declares unsafe historical submissions name {name!r}")
        payload, receipt = _load_or_fetch_json(
            collector,
            cache_root / "historical" / name,
            cik=cik,
            historical_name=name,
        )
        rows.extend(_column_rows(payload))
        receipts.append(receipt)
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        accession = str(row.get("accessionNumber") or "")
        if not accession or accession in indexed:
            continue
        indexed[accession] = {**top, **row}
    receipt = {
        "cik": cik,
        "sources": sorted(receipts, key=lambda item: item["url"]),
        "joined_accessions": len(indexed),
    }
    return indexed, receipt


def parse_items(value: Any) -> frozenset[str]:
    return frozenset(re.findall(r"\d+\.\d+", str(value or "")))


def structurally_possible(items: frozenset[str]) -> bool:
    return not items or bool(items & _ITEM_SCREEN)


def structural_refusal(items: frozenset[str]) -> str | None:
    for codes, refusal in _ITEM_REFUSALS:
        if items & codes:
            return refusal
    return None


def _header(body: str, field: str) -> str:
    match = re.search(rf"(?im)^<{re.escape(field)}>\s*([^\r\n<]*)", body)
    return match.group(1).strip() if match else ""


def parse_submission_documents(accession: str, body: bytes) -> list[SourceDocument]:
    decoded = body.decode("latin-1", errors="replace")
    blocks = re.findall(r"(?is)<DOCUMENT>(.*?)</DOCUMENT>", decoded)
    documents: list[SourceDocument] = []
    for index, block in enumerate(blocks, start=1):
        text_match = re.search(r"(?is)<TEXT>(.*)</TEXT>", block)
        text = text_match.group(1) if text_match else block
        filename = _header(block, "FILENAME") or f"document-{index}.txt"
        doc_type = _header(block, "TYPE") or "UNKNOWN"
        sequence = _header(block, "SEQUENCE") or str(index)
        description = _header(block, "DESCRIPTION")
        digest = sha256_bytes(text.encode("latin-1", errors="replace"))
        source_id = f"{accession}:{sequence}:{filename}:{digest[:16]}"
        documents.append(
            SourceDocument(
                source_document_id=source_id,
                document_type=doc_type,
                sequence=sequence,
                filename=filename,
                description=description,
                text=text,
                sha256=digest,
            )
        )
    if not documents:
        digest = sha256_bytes(body)
        documents.append(
            SourceDocument(
                source_document_id=f"{accession}:0:complete-submission.txt:{digest[:16]}",
                document_type="COMPLETE-SUBMISSION",
                sequence="0",
                filename="complete-submission.txt",
                description="",
                text=decoded,
                sha256=digest,
            )
        )
    return documents


def visible_text_with_map(raw: str) -> tuple[str, list[int]]:
    visible: list[str] = []
    offsets: list[int] = []
    index = 0
    in_tag = False
    while index < len(raw):
        char = raw[index]
        if in_tag:
            if char == ">":
                in_tag = False
                visible.append(" ")
                offsets.append(index)
            index += 1
            continue
        if char == "<":
            in_tag = True
            index += 1
            continue
        if char == "&":
            match = re.match(r"&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z]+);", raw[index : index + 24])
            if match:
                decoded = html.unescape(match.group(0))
                for out in decoded:
                    visible.append(out)
                    offsets.append(index)
                index += len(match.group(0))
                continue
        visible.append(char)
        offsets.append(index)
        index += 1
    collapsed: list[str] = []
    collapsed_offsets: list[int] = []
    was_space = False
    for char, offset in zip(visible, offsets):
        if char.isspace():
            if not was_space:
                collapsed.append(" ")
                collapsed_offsets.append(offset)
            was_space = True
        else:
            collapsed.append(char)
            collapsed_offsets.append(offset)
            was_space = False
    return "".join(collapsed), collapsed_offsets


def _raw_span(offsets: Sequence[int], start: int, end: int) -> dict[str, int]:
    if not offsets:
        return {"byte_start": 0, "byte_end": 0}
    bounded_start = min(max(start, 0), len(offsets) - 1)
    bounded_end = min(max(end - 1, bounded_start), len(offsets) - 1)
    return {"byte_start": offsets[bounded_start], "byte_end": offsets[bounded_end] + 1}


def _money_value(match: re.Match[str]) -> int | None:
    try:
        number = float(match.group("number").replace(",", ""))
    except ValueError:
        return None
    scale = (match.group("scale") or "").lower()
    multiplier = {
        "": 1,
        "thousand": 1_000,
        "million": 1_000_000,
        "m": 1_000_000,
        "mm": 1_000_000,
        "billion": 1_000_000_000,
        "b": 1_000_000_000,
        "bn": 1_000_000_000,
    }.get(scale)
    if multiplier is None:
        return None
    value = number * multiplier
    if not math.isfinite(value) or value < 1_000_000 or value > 1_000_000_000_000:
        return None
    return int(round(value))


def extract_amount(text: str, semantic: re.Match[str]) -> tuple[int, re.Match[str]] | None:
    start = max(0, semantic.start() - 450)
    end = min(len(text), semantic.end() + 700)
    candidates: list[tuple[int, int, re.Match[str]]] = []
    for match in _AMOUNT.finditer(text, start, end):
        value = _money_value(match)
        if value is None:
            continue
        distance = min(abs(match.start() - semantic.end()), abs(semantic.start() - match.end()))
        candidates.append((distance, -value, match))
    if not candidates:
        return None
    _, _, chosen = min(candidates, key=lambda item: (item[0], item[1], item[2].start()))
    value = _money_value(chosen)
    return (value, chosen) if value is not None else None


def extract_source_timestamp(text: str) -> tuple[datetime, re.Match[str]] | None:
    for match in _TIMESTAMP.finditer(text[:12000]):
        zone = match.group("zone").lower()
        if "daylight" in zone or zone == "edt":
            tz = timezone(timedelta(hours=-4))
        elif "standard" in zone or zone == "est":
            tz = timezone(timedelta(hours=-5))
        else:
            tz = ET
        stamp = datetime.strptime(
            f"{match.group('month')} {match.group('day')} {match.group('year')} "
            f"{match.group('hour')}:{match.group('minute')} {match.group('ampm').replace('.', '')}",
            "%B %d %Y %I:%M %p",
        ).replace(tzinfo=tz)
        return stamp.astimezone(ET), match
    return None


def next_session(value: date) -> date:
    candidate = value
    for _ in range(15):
        if nyse_calendar.is_session(candidate):
            return candidate
        candidate += timedelta(days=1)
    raise CensusError(f"no US cash-equity session near {value}")


def publication_bucket(stamp_et: datetime) -> tuple[str, str | None]:
    day = stamp_et.date()
    if not nyse_calendar.is_session(day):
        return "AFTER_CLOSE_CERTIFIED", next_session(day + timedelta(days=1)).isoformat()
    session_open, session_close = session_window_et(day)
    if stamp_et < session_open:
        return "PREOPEN_CERTIFIED", day.isoformat()
    if stamp_et >= session_close:
        return "AFTER_CLOSE_CERTIFIED", next_session(day + timedelta(days=1)).isoformat()
    return "INTRADAY_PUBLICATION", None


def _source_url(cik: str, accession: str, filename: str) -> str:
    compact = accession.replace("-", "")
    return f"{SEC_ARCHIVES}edgar/data/{int(cik)}/{compact}/{filename}"


def _root_url(row: FilingRow) -> str:
    return f"{SEC_ARCHIVES}{row.filename}"


class SecArchiveClient:
    def __init__(self, *, user_agent: str, min_interval_seconds: float = 0.11, timeout_seconds: float = 45.0) -> None:
        if "@" not in user_agent:
            raise ValueError("SEC user agent must identify an application and contact email")
        self.user_agent = user_agent
        self.min_interval_seconds = max(0.1, float(min_interval_seconds))
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self._last_request = 0.0

    def fetch(self, url: str, *, max_bytes: int = 64 * 1024 * 1024) -> bytes:
        if not url.startswith(SEC_ARCHIVES):
            raise CensusError(f"non-SEC archive source refused: {url}")
        last_error: Exception | None = None
        for attempt in range(4):
            wait = self.min_interval_seconds - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            response = None
            try:
                response = self.session.get(
                    url,
                    headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
                    timeout=self.timeout_seconds,
                    stream=True,
                    allow_redirects=False,
                )
                self._last_request = time.monotonic()
                if response.url != url or 300 <= response.status_code < 400:
                    raise CensusError(f"SEC archive redirect/source mismatch for {url}")
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"SEC transient HTTP {response.status_code}")
                response.raise_for_status()
                chunks: list[bytes] = []
                received = 0
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > max_bytes:
                        raise CensusError(f"SEC archive source exceeds {max_bytes} bytes: {url}")
                    chunks.append(chunk)
                return b"".join(chunks)
            except CensusError:
                raise
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(min(2**attempt, 4))
            finally:
                if response is not None:
                    response.close()
        raise CensusError(f"SEC archive fetch failed after retries for {url}: {last_error}")


def _candidate_documents(documents: Sequence[SourceDocument]) -> list[tuple[SourceDocument, str, list[int], re.Match[str]]]:
    matches: list[tuple[SourceDocument, str, list[int], re.Match[str]]] = []
    for document in documents:
        visible, offsets = visible_text_with_map(document.text)
        for pattern in _SEMANTIC_PATTERNS:
            match = pattern.search(visible)
            if match:
                matches.append((document, visible, offsets, match))
                break
    return matches


def _base_row(filing: FilingRow, dependence_root_id: str) -> dict[str, Any]:
    return {
        "episode_id": f"cell-b-v2:{dependence_root_id.split(':')[-1]}",
        "economic_issuer_id": None,
        "security_id": None,
        "listing_id": None,
        "cik": filing.cik,
        "accession": filing.accession,
        "dependence_root_id": dependence_root_id,
        "source_document_ids": [],
        "source_sha256s": [],
        "semantic_span": None,
        "amount_span": None,
        "authorization_amount_usd": None,
        "source_native_percent_shares": None,
        "publication_bucket": None,
        "first_public_evidence_interval": None,
        "event_session": None,
        "rights_profile": None,
        "status": "REFUSED",
        "refusal_reason": None,
        "correction_of": None,
        "superseded_by": None,
        "filing_date": filing.filing_date,
    }


def classify_filing(
    filing: FilingRow,
    metadata: Mapping[str, Any],
    identities: Sequence[IdentityRow],
    body: bytes,
) -> dict[str, Any]:
    full_digest = sha256_bytes(body)
    root_seed = f"{filing.cik}|{filing.accession}|{full_digest}".encode()
    dependence_root_id = f"root:cell-b-v2:{sha256_bytes(root_seed)[:24]}"
    row = _base_row(filing, dependence_root_id)
    if filing.form != "8-K":
        row["refusal_reason"] = "AMENDMENT_OR_NON_8K"
        return row
    documents = parse_submission_documents(filing.accession, body)
    candidates = _candidate_documents(documents)
    if not candidates:
        for document in documents:
            visible, _offsets = visible_text_with_map(document.text)
            if not _BUYBACK_MENTION.search(visible):
                continue
            if _NOT_NEW.search(visible):
                row["refusal_reason"] = "INCREASE_EXTENSION_RENEWAL_OR_REMAINING"
                return row
            if _NON_DISCRETIONARY.search(visible):
                row["refusal_reason"] = "TENDER_ASR_OR_NON_DISCRETIONARY"
                return row
            if _WRONG_INSTRUMENT.search(visible):
                row["refusal_reason"] = "DEBT_PREFERRED_OR_EMPLOYEE_WITHHOLDING"
                return row
            if _COMPLETED_ONLY.search(visible):
                row["refusal_reason"] = "COMPLETED_PURCHASE_ONLY"
                return row
        row["refusal_reason"] = "NOT_NEW_AUTHORIZATION"
        return row
    document, visible, offsets, semantic = candidates[0]
    context = visible[max(0, semantic.start() - 700) : min(len(visible), semantic.end() + 1200)]
    row["source_document_ids"] = [document.source_document_id]
    row["source_sha256s"] = [document.sha256]
    row["semantic_span"] = {
        "source_document_id": document.source_document_id,
        **_raw_span(offsets, semantic.start(), semantic.end()),
        "text_sha256": sha256_bytes(semantic.group(0).encode("utf-8")),
    }
    if _NOT_NEW.search(context):
        row["refusal_reason"] = "INCREASE_EXTENSION_RENEWAL_OR_REMAINING"
        return row
    if _NON_DISCRETIONARY.search(context):
        row["refusal_reason"] = "TENDER_ASR_OR_NON_DISCRETIONARY"
        return row
    if _WRONG_INSTRUMENT.search(context):
        row["refusal_reason"] = "DEBT_PREFERRED_OR_EMPLOYEE_WITHHOLDING"
        return row
    items = parse_items(metadata.get("items"))
    item_refusal = structural_refusal(items)
    if item_refusal:
        row["refusal_reason"] = item_refusal
        return row
    for pattern, refusal in _TEXT_BUNDLES:
        if pattern.search(context):
            row["refusal_reason"] = refusal
            return row
    sic = str(metadata.get("sic") or "")
    if sic.isdigit() and 6000 <= int(sic) <= 6999:
        row["refusal_reason"] = "FINANCIAL_ISSUER"
        return row
    if str(metadata.get("entity_type") or "").lower() not in {"operating", ""}:
        row["refusal_reason"] = "NON_US_COMMON_OPERATING_ISSUER"
        return row
    if len(identities) != 1:
        row["refusal_reason"] = "IDENTITY_UNESTIMABLE"
        return row
    identity = identities[0]
    row.update(
        economic_issuer_id=identity.economic_issuer_id,
        security_id=identity.security_id,
        listing_id=identity.listing_id,
    )
    amount = extract_amount(visible, semantic)
    if amount is None:
        row["refusal_reason"] = "AMOUNT_UNESTIMABLE"
        return row
    amount_usd, amount_match = amount
    row["authorization_amount_usd"] = amount_usd
    row["amount_span"] = {
        "source_document_id": document.source_document_id,
        **_raw_span(offsets, amount_match.start(), amount_match.end()),
        "text_sha256": sha256_bytes(amount_match.group(0).encode("utf-8")),
    }
    percent = _PERCENT_SHARES.search(context)
    if percent:
        row["source_native_percent_shares"] = float(percent.group("number"))
    source_url = _source_url(filing.cik, filing.accession, document.filename)
    if not source_url.startswith(SEC_ARCHIVES) or not document.sha256:
        row["refusal_reason"] = "RIGHTS_UNESTIMABLE"
        return row
    row["rights_profile"] = {
        "rights_class": "public_source_link",
        "source_system": "sec_edgar",
        "source_url": source_url,
    }
    timestamp = extract_source_timestamp(visible)
    if timestamp is None:
        row["refusal_reason"] = "CLOCK_UNESTIMABLE"
        return row
    stamp_et, timestamp_match = timestamp
    bucket, event_session = publication_bucket(stamp_et)
    row["publication_bucket"] = bucket
    row["first_public_evidence_interval"] = {
        "start": stamp_et.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "end": stamp_et.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_document_id": document.source_document_id,
        **_raw_span(offsets, timestamp_match.start(), timestamp_match.end()),
    }
    if bucket == "INTRADAY_PUBLICATION":
        row["refusal_reason"] = "INTRADAY_PUBLICATION"
        return row
    row["event_session"] = event_session
    row["status"] = "ADMITTED"
    row["refusal_reason"] = None
    return row


def _cache_key(filing: FilingRow) -> str:
    return filing.accession.replace("-", "")


def scan_filing(
    client: SecArchiveClient,
    cache_root: Path,
    filing: FilingRow,
    metadata: Mapping[str, Any],
    identities: Sequence[IdentityRow],
    *,
    reuse_cache: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cache_path = cache_root / filing.filing_date[:4] / f"{_cache_key(filing)}.json"
    if reuse_cache and cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("parser_version") == PARSER_VERSION and cached.get("source_url") == _root_url(filing):
            return cached["row"], cached["receipt"]
    source_url = _root_url(filing)
    try:
        body = client.fetch(source_url)
        row = classify_filing(filing, metadata, identities, body)
        receipt = {
            "accession": filing.accession,
            "url": source_url,
            "bytes": len(body),
            "sha256": sha256_bytes(body),
            "screen": "OFFICIAL_ITEMS_7_01_OR_8_01_OR_UNDECLARED",
        }
    except Exception as exc:
        digest = sha256_bytes(f"{type(exc).__name__}:{exc}".encode("utf-8"))
        row = _base_row(filing, f"root:cell-b-v2:unresolved-{digest[:24]}")
        row["refusal_reason"] = "SOURCE_ROOT_UNRESOLVED"
        receipt = {
            "accession": filing.accession,
            "url": source_url,
            "error_class": type(exc).__name__,
            "error_digest": digest,
            "screen": "OFFICIAL_ITEMS_7_01_OR_8_01_OR_UNDECLARED",
        }
    cached = {
        "parser_version": PARSER_VERSION,
        "source_url": source_url,
        "row": row,
        "receipt": receipt,
    }
    _atomic_write(cache_path, canonical_json_bytes(cached))
    return row, receipt


def collapse_dependence_roots(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        semantic = row.get("semantic_span") or {}
        key = (
            row["cik"],
            row["filing_date"],
            row.get("authorization_amount_usd"),
            semantic.get("text_sha256"),
        )
        grouped[key].append(dict(row))
    out: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda item: tuple("" if value is None else str(value) for value in item)):
        members = sorted(
            grouped[key],
            key=lambda item: (item.get("status") != "ADMITTED", item["accession"]),
        )
        chosen = members[0]
        accessions = [member["accession"] for member in members]
        root_digest = sha256_bytes("|".join(str(value) for value in key).encode("utf-8"))[:24]
        chosen["dependence_root_id"] = f"root:cell-b-v2:{root_digest}"
        chosen["episode_id"] = f"cell-b-v2:{root_digest}"
        if len(accessions) > 1:
            chosen["duplicate_accessions"] = accessions[1:]
            chosen["source_document_ids"] = sorted(
                {value for member in members for value in member.get("source_document_ids", [])}
            )
            chosen["source_sha256s"] = sorted(
                {value for member in members for value in member.get("source_sha256s", [])}
            )
        out.append(chosen)
    return sorted(out, key=lambda item: (item["filing_date"], item["cik"], item["accession"]))


def apply_correction_supersession(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    copied = [dict(row) for row in rows]
    by_episode = {row["episode_id"]: row for row in copied}
    for row in copied:
        parent = row.get("correction_of")
        if parent:
            if parent not in by_episode:
                raise CensusError(f"correction points outside manifest: {parent}")
            by_episode[parent]["superseded_by"] = row["episode_id"]
    return copied


def kish_effective_n(values: Iterable[str]) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    weights = [count / total for count in counts.values()]
    return 1.0 / sum(weight * weight for weight in weights)


def support_stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    admitted = [row for row in rows if row.get("status") == "ADMITTED"]
    issuer_n = kish_effective_n(str(row["economic_issuer_id"]) for row in admitted)
    date_n = kish_effective_n(str(row["event_session"]) for row in admitted)
    return {
        "events": len(admitted),
        "unique_economic_issuers": len({row["economic_issuer_id"] for row in admitted}),
        "unique_event_dates": len({row["event_session"] for row in admitted}),
        "kish_n_by_economic_issuer": round(issuer_n, 6),
        "kish_n_by_event_date": round(date_n, 6),
        "source_n_eff": round(min(issuer_n, date_n), 6),
    }


def center_clears(stats: Mapping[str, Any]) -> bool:
    return (
        int(stats["events"]) >= 80
        and int(stats["unique_economic_issuers"]) >= 50
        and int(stats["unique_event_dates"]) >= 50
        and float(stats["source_n_eff"]) >= 60
    )


def tail_clears_source_floor(stats: Mapping[str, Any]) -> bool:
    return (
        int(stats["events"]) >= 160
        and int(stats["unique_economic_issuers"]) >= 80
        and int(stats["unique_event_dates"]) >= 80
        and float(stats["source_n_eff"]) >= 120
    )


def _period(row: Mapping[str, Any]) -> str:
    filed = date.fromisoformat(str(row["filing_date"]))
    if filed <= DEV_END:
        return "development_through_2024"
    if filed <= CONFIRM_END:
        return "confirmatory_2025"
    return "replication_2026_h1"


def _leave_one_issuer_worst(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    admitted = [row for row in rows if row.get("status") == "ADMITTED"]
    issuers = sorted({row["economic_issuer_id"] for row in admitted})
    if not issuers:
        return support_stats([])
    candidates = [support_stats([row for row in admitted if row["economic_issuer_id"] != issuer]) for issuer in issuers]
    return min(candidates, key=lambda stats: (stats["events"], stats["source_n_eff"], stats["unique_event_dates"]))


def amount_distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = sorted(
        int(row["authorization_amount_usd"])
        for row in rows
        if row.get("authorization_amount_usd") is not None
    )
    if not values:
        return {"count": 0, "minimum": None, "median": None, "maximum": None}
    return {"count": len(values), "minimum": values[0], "median": int(median(values)), "maximum": values[-1]}


def summarize(rows: Sequence[dict[str, Any]], denominator: Sequence[FilingRow]) -> dict[str, Any]:
    periods: dict[str, dict[str, Any]] = {}
    for period in ("development_through_2024", "confirmatory_2025", "replication_2026_h1"):
        subset = [row for row in rows if _period(row) == period]
        stats = support_stats(subset)
        refusals = Counter(row.get("refusal_reason") for row in subset if row.get("refusal_reason"))
        periods[period] = {
            "raw_discovered_roots": len(subset),
            "admitted_roots": stats["events"],
            "refusal_counts": {reason: refusals.get(reason, 0) for reason in REFUSALS},
            "support": stats,
            "center_source_floor_clears": center_clears(stats),
            "tail_source_floor_clears": tail_clears_source_floor(stats),
            "leave_one_issuer_worst_case_support": _leave_one_issuer_worst(subset),
            "amount_distribution": amount_distribution(subset),
            "clock_certification_rate": round(
                sum(row.get("publication_bucket") in {"AFTER_CLOSE_CERTIFIED", "PREOPEN_CERTIFIED"} for row in subset)
                / len(subset),
                6,
            ) if subset else 0.0,
            "identity_resolution_rate": round(sum(bool(row.get("economic_issuer_id")) for row in subset) / len(subset), 6) if subset else 0.0,
            "rights_resolution_rate": round(sum(bool(row.get("rights_profile")) for row in subset) / len(subset), 6) if subset else 0.0,
        }
    return {
        "denominator": {
            "rows": len(denominator),
            "unique_ciks": len({row.cik for row in denominator}),
            "unique_filing_dates": len({row.filing_date for row in denominator}),
            "by_year": dict(sorted(Counter(row.filing_date[:4] for row in denominator).items())),
        },
        "periods": periods,
    }


def verdict_for(rows: Sequence[dict[str, Any]]) -> str:
    development = [row for row in rows if date.fromisoformat(row["filing_date"]) <= DEV_END]
    admitted = support_stats(development)
    if center_clears(admitted):
        return "SOURCE_CENSUS_CENTER_CAPACITY_PASS"
    clock_possible = [
        {**row, "status": "ADMITTED", "refusal_reason": None, "event_session": row.get("event_session") or row["filing_date"]}
        for row in development
        if row.get("status") == "ADMITTED" or row.get("refusal_reason") in {"CLOCK_UNESTIMABLE", "INTRADAY_PUBLICATION"}
    ]
    if center_clears(support_stats(clock_possible)):
        return "SOURCE_CENSUS_CLOCK_BLOCKED"
    identity_possible = [
        {
            **row,
            "status": "ADMITTED",
            "refusal_reason": None,
            "economic_issuer_id": row.get("economic_issuer_id") or f"unresolved:{row['cik']}",
            "event_session": row.get("event_session") or row["filing_date"],
        }
        for row in development
        if row.get("status") == "ADMITTED" or row.get("refusal_reason") in {"IDENTITY_UNESTIMABLE", "RIGHTS_UNESTIMABLE"}
    ]
    if center_clears(support_stats(identity_possible)):
        return "SOURCE_CENSUS_IDENTITY_OR_RIGHTS_BLOCKED"
    return "SOURCE_CENSUS_UNDERPOWERED"


def build_manifest(
    *,
    rows: Sequence[dict[str, Any]],
    denominator: Sequence[FilingRow],
    master_receipts: Sequence[dict[str, Any]],
    submissions_receipts: Sequence[dict[str, Any]],
    scan_receipts: Sequence[dict[str, Any]],
    identity_receipt: Mapping[str, Any],
    repository: str,
    base_commit: str,
    code_commit: str,
) -> dict[str, Any]:
    summary = summarize(rows, denominator)
    source_receipt_set = {
        "master_indexes": list(master_receipts),
        "submissions": sorted(submissions_receipts, key=lambda item: item["cik"]),
        "filing_scans": sorted(scan_receipts, key=lambda item: item["accession"]),
    }
    receipt_sha = sha256_bytes(canonical_json_bytes(source_receipt_set))
    verdict = verdict_for(rows)
    if verdict not in VERDICTS:
        raise CensusError(f"illegal verdict {verdict}")
    manifest = {
        "schema": SCHEMA,
        "protocol": PROTOCOL,
        "family": FAMILY,
        "authority": {
            "ceiling": "SPEC_ONLY",
            "market_outcomes_inspected": False,
            "production_authority": False,
        },
        "population": {
            "form": "8-K",
            "amendments_included": False,
            "start": START.isoformat(),
            "end": END.isoformat(),
            "denominator_source": "official_quarterly_edgar_master_indexes",
            "sec_full_text_search_used": False,
        },
        "determinism": {
            "canonical_json": "UTF-8;sorted-keys;separators-comma-colon;no-NaN",
            "parser_version": PARSER_VERSION,
            "repository": repository,
            "base_commit": base_commit,
            "code_commit": code_commit,
            "source_receipt_set_sha256": receipt_sha,
        },
        "identity_receipt": dict(identity_receipt),
        "summary": summary,
        "verdict": verdict,
        "rows": list(rows),
        "source_receipt_set": source_receipt_set,
    }
    manifest["determinism"]["manifest_payload_sha256"] = sha256_bytes(canonical_json_bytes(manifest))
    return manifest


def render_report(manifest: Mapping[str, Any], manifest_file_sha256: str) -> str:
    summary = manifest["summary"]
    lines = [
        "# Cell B V2 buyback source census — 2026-08-22",
        "",
        f"Scientific source-capacity verdict: `{manifest['verdict']}`",
        "",
        "This is the commissioned price-blind source census. It does not inspect any market outcome, does not change P0, and grants no Prophet/Fusion/Availability/trade/sizing authority.",
        "",
        "## Frozen receipts",
        "",
        f"- repository/base: `{manifest['determinism']['repository']}@{manifest['determinism']['base_commit']}`",
        f"- census code commit: `{manifest['determinism']['code_commit']}`",
        f"- canonical manifest file SHA-256: `{manifest_file_sha256}`",
        f"- source-receipt-set SHA-256: `{manifest['determinism']['source_receipt_set_sha256']}`",
        f"- parser: `{manifest['determinism']['parser_version']}`",
        "",
        "## Exhaustive denominator",
        "",
        f"- exact non-amended Form 8-K rows: **{summary['denominator']['rows']:,}**",
        f"- unique CIKs: **{summary['denominator']['unique_ciks']:,}**",
        f"- unique filing dates: **{summary['denominator']['unique_filing_dates']:,}**",
        f"- range: `{manifest['population']['start']}..{manifest['population']['end']}`",
        "- source: all 18 official quarterly EDGAR master indexes; SEC full-text search was not used.",
        "",
        "## Source capacity by frozen period",
        "",
        "| period | discovered roots | admitted | issuers | dates | source N_eff | center floor | tail source floor |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for period, data in summary["periods"].items():
        stats = data["support"]
        lines.append(
            f"| {period} | {data['raw_discovered_roots']} | {data['admitted_roots']} | "
            f"{stats['unique_economic_issuers']} | {stats['unique_event_dates']} | "
            f"{stats['source_n_eff']:.3f} | {data['center_source_floor_clears']} | "
            f"{data['tail_source_floor_clears']} |"
        )
    lines.extend(["", "## Refusal ledger", ""])
    for period, data in summary["periods"].items():
        lines.append(f"### {period}")
        lines.append("")
        nonzero = [(reason, count) for reason, count in data["refusal_counts"].items() if count]
        if not nonzero:
            lines.append("No refused discovered roots.")
        else:
            for reason, count in nonzero:
                lines.append(f"- `{reason}`: {count:,}")
        lines.append("")
    lines.extend(
        [
            "## Interpretation and limits",
            "",
            "- The 300,995-row denominator is exhaustive. Content acquisition is fail-closed behind official Submissions item metadata: every identity-resolved 7.01/8.01 (or item-undeclared) root is retrieved from the exact SEC archive filename; all other denominator rows remain denominator negatives rather than discovered family roots.",
            "- A current ticker is never used as identity. Only exact repository issuer/security/listing rows are eligible; missing historical/delisted coverage is disclosed through denominator-versus-identity counts and cannot be silently promoted.",
            "- SEC acceptance time alone never certifies the family clock. A row is admitted only when an official source document states an exact dated Eastern timestamp that maps wholly to a closed-market interval on the canonical US cash-equity calendar, including early closes and holidays.",
            "- The tail line is source capacity only. It is not a classification or promotion result; any later response-valid subset would have to re-clear its separately frozen gates.",
            "- Adverse or null capacity is accepted as the scientific result. No exclusion, clock rule, amount rule, or family boundary was broadened after the scan.",
            "",
        ]
    )
    return "\n".join(lines)


def _git_output(args: Sequence[str]) -> str:
    import subprocess

    result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _user_agent() -> str:
    config = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8")) or {}
    value = str(((config.get("edgar") or {}).get("user_agent") or "")).strip()
    if "@" not in value:
        raise CensusError("config.yml edgar.user_agent must identify an application and contact email")
    return value


def run(args: argparse.Namespace) -> dict[str, Any]:
    scratch = args.scratch_root.resolve()
    denominator, master_receipts = build_denominator(scratch / "master-indexes")
    identities, identity_receipt = load_identity_rows(args.identity_root.resolve())
    user_agent = _user_agent()
    collector = SecForensicsCollector(
        scratch / "unused-owner-native-raw",
        user_agent=user_agent,
        min_interval_seconds=args.min_interval,
        timeout_seconds=45.0,
    )
    archive_client = SecArchiveClient(user_agent=user_agent, min_interval_seconds=args.min_interval)
    denominator_by_cik: dict[str, list[FilingRow]] = defaultdict(list)
    for filing in denominator:
        denominator_by_cik[filing.cik].append(filing)
    relevant_ciks = sorted(set(denominator_by_cik) & set(identities))
    submissions_receipts: list[dict[str, Any]] = []
    scanned_rows: list[dict[str, Any]] = []
    scan_receipts: list[dict[str, Any]] = []
    counters = Counter()
    for cik_index, cik in enumerate(relevant_ciks, start=1):
        metadata_rows, receipt = load_submissions_for_cik(
            collector, scratch / "submissions", cik
        )
        submissions_receipts.append(receipt)
        for filing in denominator_by_cik[cik]:
            metadata = metadata_rows.get(filing.accession)
            if metadata is None:
                counters["metadata_unresolved"] += 1
                continue
            items = parse_items(metadata.get("items"))
            if not structurally_possible(items):
                counters["structural_negative"] += 1
                continue
            row, scan_receipt = scan_filing(
                archive_client,
                scratch / "scan-cache",
                filing,
                metadata,
                identities[cik],
                reuse_cache=args.reuse_cache,
            )
            scanned_rows.append(row)
            scan_receipts.append(scan_receipt)
            counters["scanned"] += 1
            if counters["scanned"] % args.progress_every == 0:
                print(
                    f"CELL_B_V2_PROGRESS scanned={counters['scanned']} "
                    f"roots={len(scanned_rows)} ciks={cik_index}/{len(relevant_ciks)}",
                    flush=True,
                )
        if cik_index % 50 == 0:
            print(
                f"CELL_B_V2_METADATA ciks={cik_index}/{len(relevant_ciks)} "
                f"structural_negative={counters['structural_negative']} "
                f"metadata_unresolved={counters['metadata_unresolved']}",
                flush=True,
            )
    rows = apply_correction_supersession(collapse_dependence_roots(scanned_rows))
    identity_receipt = {
        **identity_receipt,
        "denominator_rows_with_resolved_cik": sum(len(denominator_by_cik[cik]) for cik in relevant_ciks),
        "denominator_rows_without_resolved_cik": len(denominator) - sum(len(denominator_by_cik[cik]) for cik in relevant_ciks),
        "official_metadata_unresolved_rows": counters["metadata_unresolved"],
        "structural_negative_rows": counters["structural_negative"],
        "content_scanned_rows": counters["scanned"],
    }
    manifest = build_manifest(
        rows=rows,
        denominator=denominator,
        master_receipts=master_receipts,
        submissions_receipts=submissions_receipts,
        scan_receipts=scan_receipts,
        identity_receipt=identity_receipt,
        repository=args.repository,
        base_commit=args.base_commit,
        code_commit=args.code_commit,
    )
    manifest_body = canonical_json_bytes(manifest)
    _atomic_write(args.manifest, manifest_body)
    report = render_report(manifest, sha256_bytes(manifest_body))
    _atomic_write(args.report, report.encode("utf-8"))
    print(f"CELL_B_V2_VERDICT {manifest['verdict']}", flush=True)
    print(f"CELL_B_V2_MANIFEST_SHA256 {sha256_bytes(manifest_body)}", flush=True)
    print(f"CELL_B_V2_SOURCE_RECEIPTS_SHA256 {manifest['determinism']['source_receipt_set_sha256']}", flush=True)
    print(json.dumps(manifest["summary"], sort_keys=True), flush=True)
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--identity-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "research/prophet_v4/flagship_cells/cell_b_v2_buyback_source_census_manifest.v2.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "research/prophet_v4/flagship_cells/CELL_B_V2_BUYBACK_SOURCE_CENSUS_2026-08-22.md",
    )
    parser.add_argument("--repository", default="mastermindx-market-intelligence/macro")
    parser.add_argument("--base-commit", default=None)
    parser.add_argument("--code-commit", default=None)
    parser.add_argument("--min-interval", type=float, default=0.11)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--reuse-cache", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    if args.base_commit is None:
        args.base_commit = _git_output(["merge-base", "HEAD", "origin/main"])
    if args.code_commit is None:
        args.code_commit = _git_output(["rev-parse", "HEAD"])
    if args.progress_every < 1:
        parser.error("--progress-every must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
