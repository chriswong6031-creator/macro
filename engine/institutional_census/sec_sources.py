"""Pure SEC source readers for the institutional-manager Form 13F census.

This module deliberately owns no persistence, scheduling, aggregation, or public
projection.  It converts official SEC source artifacts into deterministic pandas
tables while preserving the as-filed rows needed for later reconciliation.

The two manager relationships in Form 13F are intentionally separate:

``reported_by``
    The filing manager's holdings are reported by another manager.  These rows
    come from ``OTHERMANAGER.tsv`` / ``otherManagersInfo`` and occur on notices
    and combination reports.

``included_managers``
    The report includes holdings for another manager.  These rows come from
    ``OTHERMANAGER2.tsv`` / ``otherManagers2Info``.  Sequence numbers are *not*
    unique in real SEC filings, so ``source_ordinal`` is the retained row key.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

import pandas as pd


FORM_TYPES = frozenset({"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"})

LATEST_FILINGS_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=13F"
    "&company=&dateb=&owner=include&start=0&count=100&output=atom"
)
ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
ATOM_PAGE_SIZE = 100
# EDGAR's current-filings listing is an ephemeral discovery surface.  The
# scanner must hand completeness off to daily/full indexes after this boundary.
ATOM_EPHEMERAL_ENTRY_LIMIT = 930


class SecSourceError(ValueError):
    """An SEC artifact violates the source contract required for parsing."""


@dataclass(frozen=True)
class FilingDiscovery:
    """One accession discovered through Latest Filings or a master index."""

    accession: str
    cik: str
    form: str
    filing_date: str | None
    accepted_at: str | None
    index_url: str
    company_name: str | None = None
    source_ordinal: int = 0


@dataclass(frozen=True)
class AtomScanResult:
    entries: tuple[FilingDiscovery, ...]
    pages_fetched: int
    complete: bool
    stop_reason: str


@dataclass(frozen=True)
class FilingIndexDocument:
    source_ordinal: int
    name: str
    url: str
    size: int | None
    last_modified: str | None


@dataclass(frozen=True)
class BulkInvariantFinding:
    code: str
    accession: str | None
    detail: str
    severity: str = "warning"


SUBMISSION_COLUMNS = [
    "accession",
    "filing_date",
    "form",
    "cik",
    "period_end",
    "accepted_at",
]

COVER_PAGE_COLUMNS = [
    "source_ordinal",
    "accession",
    "report_calendar_or_quarter",
    "is_amendment",
    "amendment_number",
    "amendment_type",
    "confidential_denied_or_expired",
    "date_denied_or_expired",
    "date_reported",
    "reason_for_non_confidentiality",
    "filing_manager_name",
    "filing_manager_street1",
    "filing_manager_street2",
    "filing_manager_city",
    "filing_manager_state_or_country",
    "filing_manager_zipcode",
    "report_type",
    "form_13f_file_number",
    "crd_number",
    "sec_file_number",
    "provide_info_for_instruction5",
    "additional_information",
]

SUMMARY_PAGE_COLUMNS = [
    "source_ordinal",
    "accession",
    "other_included_managers_count",
    "table_entry_total",
    "table_value_total",
    "is_confidential_omitted",
]

HOLDING_COLUMNS = [
    "source_ordinal",
    "accession",
    "info_table_sk",
    "issuer_name",
    "title_of_class",
    "cusip",
    "figi",
    "value",
    "shares_or_principal_amount",
    "shares_or_principal_amount_type",
    "put_call",
    "investment_discretion",
    "other_manager",
    "voting_authority_sole",
    "voting_authority_shared",
    "voting_authority_none",
]

REPORTED_BY_COLUMNS = [
    "source_ordinal",
    "accession",
    "filer_cik",
    "other_manager_sk",
    "reporting_manager_cik",
    "form_13f_file_number",
    "crd_number",
    "sec_file_number",
    "manager_name",
    "relation_type",
]

INCLUDED_MANAGER_COLUMNS = [
    "source_ordinal",
    "accession",
    "filer_cik",
    "sequence_number",
    "included_manager_cik",
    "form_13f_file_number",
    "crd_number",
    "sec_file_number",
    "manager_name",
    "relation_type",
]

_INTEGER_TABLE_COLUMNS = frozenset(
    {
        "amendment_number",
        "other_included_managers_count",
        "table_entry_total",
        "table_value_total",
        "info_table_sk",
        "value",
        "shares_or_principal_amount",
        "voting_authority_sole",
        "voting_authority_shared",
        "voting_authority_none",
        "other_manager_sk",
        "sequence_number",
    }
)
_BOOLEAN_TABLE_COLUMNS = frozenset(
    {
        "is_amendment",
        "confidential_denied_or_expired",
        "provide_info_for_instruction5",
        "is_confidential_omitted",
    }
)


@dataclass(frozen=True)
class BulkTables:
    """Normalized tables from one official bulk ZIP or one live filing.

    ``source_bytes`` is the number of bytes hashed by ``source_sha256``.  For a
    bulk package that is the exact ZIP body.  For a live filing it is the sum of
    the canonical index and fetched document bodies; their URL/length framing is
    included in the digest to avoid concatenation ambiguity.
    """

    submissions: pd.DataFrame
    cover_pages: pd.DataFrame
    summary_pages: pd.DataFrame
    holdings: pd.DataFrame
    reported_by: pd.DataFrame
    included_managers: pd.DataFrame
    source_sha256: str
    source_bytes: int

    def joined_holdings(self) -> pd.DataFrame:
        """Return holdings with the minimal accession metadata downstream needs."""

        metadata_columns = [
            "accession",
            "cik",
            "period_end",
            "filing_date",
            "form",
            "accepted_at",
        ]
        metadata = self.submissions.loc[:, metadata_columns]
        if metadata["accession"].duplicated().any():
            raise SecSourceError("submission accession is not unique")
        joined = self.holdings.merge(
            metadata,
            on="accession",
            how="left",
            sort=False,
            validate="many_to_one",
        )
        return joined.loc[:, [*HOLDING_COLUMNS, *metadata_columns[1:]]]


_BULK_HEADERS: dict[str, list[str]] = {
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
}

_BULK_MEMBERS = frozenset(
    {
        *_BULK_HEADERS,
        "FORM13F_metadata.json",
        "FORM13F_readme.htm",
    }
)

_ACCESSION_RE = re.compile(r"\b(\d{10}-\d{2}-\d{6})\b")
_ACCESSION_NODASH_RE = re.compile(r"^\d{18}$")
_ARCHIVE_LINK_RE = re.compile(
    r"/Archives/edgar/data/(?P<cik>\d{1,10})/(?P<directory>\d{18})/",
    re.IGNORECASE,
)


def _read_source_bytes(source: bytes | bytearray | memoryview | Path) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (bytearray, memoryview)):
        return bytes(source)
    if isinstance(source, Path):
        return source.read_bytes()
    raise TypeError("source must be bytes or pathlib.Path")


def _text(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    # pandas may materialize a missing Arrow/string value as float NaN during
    # ``Series.map``.  Normalize every scalar missing representation here so a
    # later uppercase pass never attempts ``nan.upper()``.
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    value = str(value).strip()
    return value or None


def normalize_cik(value: Any) -> str | None:
    raw = _text(value)
    if raw is None:
        return None
    if not raw.isdigit() or len(raw) > 10:
        raise SecSourceError(f"invalid CIK: {raw!r}")
    return raw.zfill(10)


def normalize_accession(value: Any) -> str:
    raw = _text(value)
    if raw is None:
        raise SecSourceError("missing accession number")
    if _ACCESSION_RE.fullmatch(raw):
        return raw
    compact = raw.replace("-", "")
    if _ACCESSION_NODASH_RE.fullmatch(compact):
        return f"{compact[:10]}-{compact[10:12]}-{compact[12:]}"
    raise SecSourceError(f"invalid accession number: {raw!r}")


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y%m%d",
    "%d-%b-%Y",
    "%m-%d-%Y",
    "%m/%d/%Y",
)


def normalize_date(value: Any) -> str | None:
    raw = _text(value)
    if raw is None:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise SecSourceError(f"invalid SEC date: {raw!r}")


def normalize_timestamp(value: Any) -> str | None:
    raw = _text(value)
    if raw is None:
        return None
    if raw.isdigit() and len(raw) >= 14:
        try:
            # EDGAR's ACCEPTANCE-DATETIME is local Eastern time.  Attach the
            # historical DST-aware offset so the filing-time clock is never
            # represented as an ambiguous naive timestamp.
            return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(
                tzinfo=ZoneInfo("America/New_York")
            ).isoformat()
        except ValueError as exc:
            raise SecSourceError(f"invalid SEC acceptance timestamp: {raw!r}") from exc
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
    except ValueError as exc:
        raise SecSourceError(f"invalid SEC acceptance timestamp: {raw!r}") from exc


def _bool(value: Any) -> bool | None:
    raw = (_text(value) or "").upper()
    if not raw:
        return None
    if raw in {"Y", "YES", "TRUE", "1"}:
        return True
    if raw in {"N", "NO", "FALSE", "0"}:
        return False
    raise SecSourceError(f"invalid SEC boolean: {value!r}")


def _int(value: Any) -> int | None:
    raw = _text(value)
    if raw is None:
        return None
    cleaned = raw.replace(",", "")
    if not re.fullmatch(r"[+-]?\d+", cleaned):
        raise SecSourceError(f"invalid SEC integer: {raw!r}")
    return int(cleaned)


def _string_series(series: pd.Series, *, upper: bool = False) -> pd.Series:
    values = series.map(_text)
    if upper:
        values = values.map(
            lambda value: normalized.upper()
            if (normalized := _text(value)) is not None
            else None
        )
    return values.astype("object")


def _date_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_date).astype("object")


def _cik_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_cik).astype("object")


def _accession_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_accession).astype("object")


def _integer_series(series: pd.Series) -> pd.Series:
    return pd.Series(pd.array(series.map(_int), dtype="Int64"), index=series.index)


def _boolean_series(series: pd.Series) -> pd.Series:
    return pd.Series(pd.array(series.map(_bool), dtype="boolean"), index=series.index)


def _empty_frame(columns: Sequence[str]) -> pd.DataFrame:
    data: dict[str, pd.Series] = {}
    for column in columns:
        if column == "source_ordinal":
            data[column] = pd.Series(dtype="int64")
        elif column in _INTEGER_TABLE_COLUMNS:
            data[column] = pd.Series(dtype="Int64")
        elif column in _BOOLEAN_TABLE_COLUMNS:
            data[column] = pd.Series(dtype="boolean")
        else:
            data[column] = pd.Series(dtype="object")
    return pd.DataFrame(data, columns=list(columns))


def _select(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise SecSourceError(f"normalized table missing columns: {missing}")
    return frame.loc[:, list(columns)].reset_index(drop=True)


def _validate_zip_members(archive: ZipFile) -> None:
    files = [item.filename for item in archive.infolist() if not item.is_dir()]
    if len(files) != len(set(files)):
        raise SecSourceError("bulk ZIP contains duplicate member names")
    names = set(files)
    missing = sorted(_BULK_MEMBERS - names)
    unexpected = sorted(names - _BULK_MEMBERS)
    if missing or unexpected:
        raise SecSourceError(
            f"bulk ZIP member mismatch; missing={missing}, unexpected={unexpected}"
        )
    if any("/" in name or "\\" in name for name in names):
        raise SecSourceError("bulk ZIP members must be at archive root")


def _iter_raw_zip_table(
    archive: ZipFile,
    name: str,
    *,
    chunk_size: int,
) -> Iterator[pd.DataFrame]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    expected = _BULK_HEADERS[name]
    ordinal = 1
    with archive.open(name) as handle:
        reader = pd.read_csv(
            handle,
            sep="\t",
            encoding="utf-8-sig",
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            chunksize=chunk_size,
        )
        emitted = False
        for chunk in reader:
            emitted = True
            if list(chunk.columns) != expected:
                raise SecSourceError(
                    f"{name} header mismatch: {list(chunk.columns)!r} != {expected!r}"
                )
            chunk.insert(0, "__source_ordinal", range(ordinal, ordinal + len(chunk)))
            ordinal += len(chunk)
            yield chunk
        if not emitted:
            # pandas still validates the header before yielding no chunks.
            empty = pd.DataFrame(columns=["__source_ordinal", *expected])
            yield empty


def _read_raw_zip_table(
    archive: ZipFile,
    name: str,
    *,
    chunk_size: int = 100_000,
) -> pd.DataFrame:
    chunks = list(_iter_raw_zip_table(archive, name, chunk_size=chunk_size))
    if len(chunks) == 1:
        return chunks[0]
    return pd.concat(chunks, ignore_index=True)


def _read_normalized_zip_table(
    archive: ZipFile,
    name: str,
    normalize: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    chunk_size: int = 100_000,
) -> pd.DataFrame:
    """Normalize each TSV chunk before concatenation to bound raw-table memory."""

    normalized = [
        normalize(raw)
        for raw in _iter_raw_zip_table(archive, name, chunk_size=chunk_size)
    ]
    if len(normalized) == 1:
        return normalized[0]
    return pd.concat(normalized, ignore_index=True, copy=False)


def _normalize_submissions(raw: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "accession": _accession_series(raw["ACCESSION_NUMBER"]),
            "filing_date": _date_series(raw["FILING_DATE"]),
            "form": _string_series(raw["SUBMISSIONTYPE"], upper=True),
            "cik": _cik_series(raw["CIK"]),
            "period_end": _date_series(raw["PERIODOFREPORT"]),
            "accepted_at": pd.Series([None] * len(raw), dtype="object"),
        }
    )
    return _select(frame, SUBMISSION_COLUMNS)


def _normalize_cover_pages(raw: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "source_ordinal": raw["__source_ordinal"].astype("int64"),
            "accession": _accession_series(raw["ACCESSION_NUMBER"]),
            "report_calendar_or_quarter": _date_series(raw["REPORTCALENDARORQUARTER"]),
            "is_amendment": _boolean_series(raw["ISAMENDMENT"]),
            "amendment_number": _integer_series(raw["AMENDMENTNO"]),
            "amendment_type": _string_series(raw["AMENDMENTTYPE"], upper=True),
            "confidential_denied_or_expired": _boolean_series(raw["CONFDENIEDEXPIRED"]),
            "date_denied_or_expired": _date_series(raw["DATEDENIEDEXPIRED"]),
            "date_reported": _date_series(raw["DATEREPORTED"]),
            "reason_for_non_confidentiality": _string_series(
                raw["REASONFORNONCONFIDENTIALITY"]
            ),
            "filing_manager_name": _string_series(raw["FILINGMANAGER_NAME"]),
            "filing_manager_street1": _string_series(raw["FILINGMANAGER_STREET1"]),
            "filing_manager_street2": _string_series(raw["FILINGMANAGER_STREET2"]),
            "filing_manager_city": _string_series(raw["FILINGMANAGER_CITY"]),
            "filing_manager_state_or_country": _string_series(
                raw["FILINGMANAGER_STATEORCOUNTRY"]
            ),
            "filing_manager_zipcode": _string_series(raw["FILINGMANAGER_ZIPCODE"]),
            "report_type": _string_series(raw["REPORTTYPE"], upper=True),
            "form_13f_file_number": _string_series(raw["FORM13FFILENUMBER"]),
            "crd_number": _string_series(raw["CRDNUMBER"]),
            "sec_file_number": _string_series(raw["SECFILENUMBER"]),
            "provide_info_for_instruction5": _boolean_series(
                raw["PROVIDEINFOFORINSTRUCTION5"]
            ),
            "additional_information": _string_series(raw["ADDITIONALINFORMATION"]),
        }
    )
    return _select(frame, COVER_PAGE_COLUMNS)


def _normalize_summary_pages(raw: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "source_ordinal": raw["__source_ordinal"].astype("int64"),
            "accession": _accession_series(raw["ACCESSION_NUMBER"]),
            "other_included_managers_count": _integer_series(
                raw["OTHERINCLUDEDMANAGERSCOUNT"]
            ),
            "table_entry_total": _integer_series(raw["TABLEENTRYTOTAL"]),
            "table_value_total": _integer_series(raw["TABLEVALUETOTAL"]),
            "is_confidential_omitted": _boolean_series(raw["ISCONFIDENTIALOMITTED"]),
        }
    )
    return _select(frame, SUMMARY_PAGE_COLUMNS)


def _normalize_holdings(raw: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "source_ordinal": raw["__source_ordinal"].astype("int64"),
            "accession": _accession_series(raw["ACCESSION_NUMBER"]),
            "info_table_sk": _integer_series(raw["INFOTABLE_SK"]),
            "issuer_name": _string_series(raw["NAMEOFISSUER"]),
            "title_of_class": _string_series(raw["TITLEOFCLASS"]),
            "cusip": _string_series(raw["CUSIP"], upper=True),
            "figi": _string_series(raw["FIGI"], upper=True),
            "value": _integer_series(raw["VALUE"]),
            "shares_or_principal_amount": _integer_series(raw["SSHPRNAMT"]),
            "shares_or_principal_amount_type": _string_series(
                raw["SSHPRNAMTTYPE"], upper=True
            ),
            "put_call": _string_series(raw["PUTCALL"], upper=True),
            "investment_discretion": _string_series(
                raw["INVESTMENTDISCRETION"], upper=True
            ),
            # Preserve the as-filed manager reference.  Real rows include names,
            # sentinels, leading zeroes, and multi-sequence strings.
            "other_manager": _string_series(raw["OTHERMANAGER"]),
            "voting_authority_sole": _integer_series(raw["VOTING_AUTH_SOLE"]),
            "voting_authority_shared": _integer_series(raw["VOTING_AUTH_SHARED"]),
            "voting_authority_none": _integer_series(raw["VOTING_AUTH_NONE"]),
        }
    )
    return _select(frame, HOLDING_COLUMNS)


def _submission_cik_map(submissions: pd.DataFrame) -> dict[str, str | None]:
    return dict(zip(submissions["accession"], submissions["cik"], strict=True))


def _normalize_reported_by(
    raw: pd.DataFrame,
    submissions: pd.DataFrame,
) -> pd.DataFrame:
    accessions = _accession_series(raw["ACCESSION_NUMBER"])
    cik_by_accession = _submission_cik_map(submissions)
    frame = pd.DataFrame(
        {
            "source_ordinal": raw["__source_ordinal"].astype("int64"),
            "accession": accessions,
            "filer_cik": accessions.map(cik_by_accession).astype("object"),
            "other_manager_sk": _integer_series(raw["OTHERMANAGER_SK"]),
            "reporting_manager_cik": _cik_series(raw["CIK"]),
            "form_13f_file_number": _string_series(raw["FORM13FFILENUMBER"]),
            "crd_number": _string_series(raw["CRDNUMBER"]),
            "sec_file_number": _string_series(raw["SECFILENUMBER"]),
            "manager_name": _string_series(raw["NAME"]),
            "relation_type": pd.Series(
                ["filer_holdings_reported_by_manager"] * len(raw), dtype="object"
            ),
        }
    )
    return _select(frame, REPORTED_BY_COLUMNS)


def _normalize_included_managers(
    raw: pd.DataFrame,
    submissions: pd.DataFrame,
) -> pd.DataFrame:
    accessions = _accession_series(raw["ACCESSION_NUMBER"])
    cik_by_accession = _submission_cik_map(submissions)
    frame = pd.DataFrame(
        {
            "source_ordinal": raw["__source_ordinal"].astype("int64"),
            "accession": accessions,
            "filer_cik": accessions.map(cik_by_accession).astype("object"),
            # Sequence is intentionally an attribute, not a primary key.
            "sequence_number": _integer_series(raw["SEQUENCENUMBER"]),
            "included_manager_cik": _cik_series(raw["CIK"]),
            "form_13f_file_number": _string_series(raw["FORM13FFILENUMBER"]),
            "crd_number": _string_series(raw["CRDNUMBER"]),
            "sec_file_number": _string_series(raw["SECFILENUMBER"]),
            "manager_name": _string_series(raw["NAME"]),
            "relation_type": pd.Series(
                ["manager_included_in_filing"] * len(raw), dtype="object"
            ),
        }
    )
    return _select(frame, INCLUDED_MANAGER_COLUMNS)


def _validate_normalized_structure(tables: BulkTables) -> None:
    submissions = tables.submissions
    if submissions["accession"].duplicated().any():
        raise SecSourceError("SUBMISSION accession must be unique")
    unsupported = sorted(set(submissions["form"].dropna()) - FORM_TYPES)
    if unsupported:
        raise SecSourceError(f"unsupported Form 13F submission types: {unsupported}")
    known = set(submissions["accession"])
    for name, frame in (
        ("cover_pages", tables.cover_pages),
        ("summary_pages", tables.summary_pages),
        ("holdings", tables.holdings),
        ("reported_by", tables.reported_by),
        ("included_managers", tables.included_managers),
    ):
        unknown = sorted(set(frame["accession"]) - known)
        if unknown:
            raise SecSourceError(f"{name} contains unknown accessions: {unknown[:5]}")
    if tables.cover_pages["accession"].duplicated().any():
        raise SecSourceError("COVERPAGE accession must be unique")
    if tables.summary_pages["accession"].duplicated().any():
        raise SecSourceError("SUMMARYPAGE accession must be unique")
    keyed_holdings = tables.holdings[tables.holdings["info_table_sk"].notna()]
    if keyed_holdings.duplicated(["accession", "info_table_sk"]).any():
        raise SecSourceError("INFOTABLE accession/info_table_sk must be unique")
    keyed_reported_by = tables.reported_by[
        tables.reported_by["other_manager_sk"].notna()
    ]
    if keyed_reported_by.duplicated(["accession", "other_manager_sk"]).any():
        raise SecSourceError("OTHERMANAGER accession/other_manager_sk must be unique")
    # There is deliberately no uniqueness assertion on included-manager sequence.


def validate_bulk_invariants(tables: BulkTables) -> tuple[BulkInvariantFinding, ...]:
    """Return non-destructive semantic findings for an as-filed package.

    SEC bulk data is a faithful flattening of filer-provided rows, including
    malformed manager sequences and internally inconsistent summary totals.
    Structural failures raise during parsing; report-level inconsistencies are
    warning findings so official as-filed evidence is retained for quarantine
    or downstream exclusion instead of blocking the entire census.
    """

    findings: list[BulkInvariantFinding] = []
    holdings_count = tables.holdings.groupby("accession", sort=False).size().to_dict()
    holdings_value = (
        tables.holdings.groupby("accession", sort=False)["value"].sum(min_count=1).to_dict()
    )
    included_count = (
        tables.included_managers.groupby("accession", sort=False).size().to_dict()
    )
    def int_or_zero(value: Any) -> int:
        return 0 if value is None or pd.isna(value) else int(value)

    for row in tables.summary_pages.itertuples(index=False):
        expected_entries = int_or_zero(row.table_entry_total)
        actual_entries = int(holdings_count.get(row.accession, 0))
        if expected_entries != actual_entries:
            findings.append(
                BulkInvariantFinding(
                    "table_entry_total_mismatch",
                    row.accession,
                    f"summary={expected_entries}, rows={actual_entries}",
                )
            )
        expected_value = int_or_zero(row.table_value_total)
        actual_value = int_or_zero(holdings_value.get(row.accession, 0))
        if expected_value != actual_value:
            findings.append(
                BulkInvariantFinding(
                    "table_value_total_mismatch",
                    row.accession,
                    f"summary={expected_value}, rows={actual_value}",
                )
            )
        expected_managers = int_or_zero(row.other_included_managers_count)
        actual_managers = int(included_count.get(row.accession, 0))
        if expected_managers != actual_managers:
            findings.append(
                BulkInvariantFinding(
                    "included_manager_count_mismatch",
                    row.accession,
                    f"summary={expected_managers}, rows={actual_managers}",
                )
            )
    duplicate_sequences = tables.included_managers[
        tables.included_managers.duplicated(
            ["accession", "sequence_number"], keep=False
        )
    ]
    for accession, group in duplicate_sequences.groupby("accession", sort=False):
        sequences = sorted({int(value) for value in group["sequence_number"].dropna()})
        findings.append(
            BulkInvariantFinding(
                "duplicate_included_manager_sequence",
                accession,
                f"duplicate sequence values retained: {sequences}",
            )
        )
    return tuple(findings)


def read_bulk_package(source: bytes | Path) -> BulkTables:
    """Read and validate one official SEC Form 13F bulk ZIP package."""

    body = _read_source_bytes(source)
    digest = sha256(body).hexdigest()
    try:
        with ZipFile(BytesIO(body)) as archive:
            _validate_zip_members(archive)
            submissions = _read_normalized_zip_table(
                archive, "SUBMISSION.tsv", _normalize_submissions
            )
            cover_pages = _read_normalized_zip_table(
                archive, "COVERPAGE.tsv", _normalize_cover_pages
            )
            summary_pages = _read_normalized_zip_table(
                archive, "SUMMARYPAGE.tsv", _normalize_summary_pages
            )
            holdings = _read_normalized_zip_table(
                archive, "INFOTABLE.tsv", _normalize_holdings
            )
            reported_by = _read_normalized_zip_table(
                archive,
                "OTHERMANAGER.tsv",
                lambda raw: _normalize_reported_by(raw, submissions),
            )
            included_managers = _read_normalized_zip_table(
                archive,
                "OTHERMANAGER2.tsv",
                lambda raw: _normalize_included_managers(raw, submissions),
            )
            # SIGNATURE is part of package validation even though downstream census
            # aggregation does not need signatory personal data.
            for _ in _iter_raw_zip_table(
                archive, "SIGNATURE.tsv", chunk_size=100_000
            ):
                pass
            json.loads(archive.read("FORM13F_metadata.json"))
            archive.read("FORM13F_readme.htm").decode("utf-8", errors="strict")
    except (BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecSourceError(f"invalid Form 13F bulk package: {exc}") from exc

    tables = BulkTables(
        submissions=submissions,
        cover_pages=cover_pages,
        summary_pages=summary_pages,
        holdings=holdings,
        reported_by=reported_by,
        included_managers=included_managers,
        source_sha256=digest,
        source_bytes=len(body),
    )
    _validate_normalized_structure(tables)
    return tables


def iter_bulk_holding_chunks(
    source: bytes | Path,
    *,
    chunk_size: int = 100_000,
) -> Iterator[pd.DataFrame]:
    """Yield normalized holding chunks with package-global source ordinals."""

    body = _read_source_bytes(source)
    try:
        with ZipFile(BytesIO(body)) as archive:
            _validate_zip_members(archive)
            for raw in _iter_raw_zip_table(
                archive, "INFOTABLE.tsv", chunk_size=chunk_size
            ):
                yield _normalize_holdings(raw)
    except BadZipFile as exc:
        raise SecSourceError(f"invalid Form 13F bulk package: {exc}") from exc


def _xml_source(source: bytes | str) -> bytes | str:
    if isinstance(source, bytes):
        return source
    # A Python string is already Unicode.  Keeping a legacy SEC declaration
    # such as ISO-8859-1 while re-encoding it as UTF-8 mojibakes non-ASCII filer
    # names, so remove only the now-inapplicable encoding pseudo-attribute.
    return re.sub(
        r"(<\?xml\s+[^?>]*?)\s+encoding=(?:\"[^\"]+\"|'[^']+')",
        r"\1",
        source,
        count=1,
        flags=re.IGNORECASE,
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child(node: ET.Element | None, name: str) -> ET.Element | None:
    if node is None:
        return None
    return next((item for item in list(node) if _local_name(item.tag) == name), None)


def _descendant(node: ET.Element | None, name: str) -> ET.Element | None:
    if node is None:
        return None
    return next((item for item in node.iter() if _local_name(item.tag) == name), None)


def _children(node: ET.Element | None, name: str) -> list[ET.Element]:
    if node is None:
        return []
    return [item for item in list(node) if _local_name(item.tag) == name]


def _node_text(node: ET.Element | None) -> str | None:
    return _text(node.text if node is not None else None)


def _child_text(node: ET.Element | None, name: str) -> str | None:
    return _node_text(_child(node, name))


def parse_latest_filings_atom(source: bytes | str) -> tuple[FilingDiscovery, ...]:
    """Parse one SEC Latest Filings Atom page.

    Filer CIK comes from the archive path and is cross-checked against the title;
    the accession prefix is never treated as filer identity.
    """

    try:
        root = ET.fromstring(_xml_source(source))
    except ET.ParseError as exc:
        raise SecSourceError(f"invalid Latest Filings Atom: {exc}") from exc
    namespace = {"atom": ATOM_NAMESPACE}
    entries: list[FilingDiscovery] = []
    for ordinal, entry in enumerate(root.findall("atom:entry", namespace), start=1):
        category = entry.find("atom:category", namespace)
        form = (
            _text(category.get("term") if category is not None else None) or ""
        ).upper()
        if form not in FORM_TYPES:
            continue
        link_node = next(
            (
                item
                for item in entry.findall("atom:link", namespace)
                if item.get("rel") == "alternate"
            ),
            None,
        )
        index_url = _text(link_node.get("href") if link_node is not None else None)
        if not index_url:
            raise SecSourceError("Atom entry lacks alternate filing link")
        archive_match = _ARCHIVE_LINK_RE.search(index_url)
        if not archive_match:
            raise SecSourceError(f"Atom filing link has unexpected archive path: {index_url}")
        link_cik = normalize_cik(archive_match.group("cik"))

        title = _text(entry.findtext("atom:title", namespaces=namespace)) or ""
        title_match = re.match(
            r"^\s*(?P<form>13F-(?:HR|NT)(?:/A)?)\s+-\s+"
            r"(?P<name>.*?)\s+\((?P<cik>\d{1,10})\)\s+\(Filer\)\s*$",
            title,
            re.IGNORECASE,
        )
        title_cik = normalize_cik(title_match.group("cik")) if title_match else None
        if title_cik and title_cik != link_cik:
            raise SecSourceError(
                f"Atom filer CIK mismatch between title ({title_cik}) and link ({link_cik})"
            )
        if title_match and title_match.group("form").upper() != form:
            raise SecSourceError("Atom form mismatch between title and category")

        identity = _text(entry.findtext("atom:id", namespaces=namespace)) or ""
        summary_html = unescape(
            _text(entry.findtext("atom:summary", namespaces=namespace)) or ""
        )
        summary_text = re.sub(r"<[^>]+>", " ", summary_html)
        accession_candidates = [
            *(_ACCESSION_RE.findall(identity)),
            *(_ACCESSION_RE.findall(summary_text)),
            *(_ACCESSION_RE.findall(index_url)),
        ]
        if not accession_candidates:
            raise SecSourceError("Atom entry lacks accession number")
        accessions = {normalize_accession(value) for value in accession_candidates}
        if len(accessions) != 1:
            raise SecSourceError(f"Atom accession mismatch: {sorted(accessions)}")
        accession = next(iter(accessions))

        filing_match = re.search(r"\bFiled:\s*(\d{4}-\d{2}-\d{2})\b", summary_text)
        filing_date = normalize_date(filing_match.group(1)) if filing_match else None
        accepted_at = normalize_timestamp(
            entry.findtext("atom:updated", namespaces=namespace)
        )
        company_name = _text(title_match.group("name")) if title_match else None
        entries.append(
            FilingDiscovery(
                accession=accession,
                cik=link_cik or title_cik or "",
                form=form,
                filing_date=filing_date,
                accepted_at=accepted_at,
                index_url=index_url,
                company_name=company_name,
                source_ordinal=ordinal,
            )
        )
    return tuple(entries)


def _fetch_bytes(fetch: Callable[[str], Any], url: str) -> bytes:
    result = fetch(url)
    if isinstance(result, bytes):
        return result
    if isinstance(result, str):
        return result.encode("utf-8")
    if isinstance(result, Mapping):
        return json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    content = getattr(result, "content", None)
    if isinstance(content, bytes):
        return content
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text.encode("utf-8")
    raise TypeError("fetch must return bytes, str, mapping, or response-like object")


def _atom_page_url(base_url: str, *, start: int, count: int) -> str:
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "action": "getcurrent",
            "type": "13F",
            "start": str(start),
            "count": str(count),
            "output": "atom",
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def scan_latest_filings_atom(
    fetch: Callable[[str], Any],
    *,
    base_url: str = LATEST_FILINGS_ATOM_URL,
    page_size: int = ATOM_PAGE_SIZE,
    entry_limit: int = ATOM_EPHEMERAL_ENTRY_LIMIT,
    known_accessions: Iterable[str] = (),
    overlap_before: str | None = None,
) -> AtomScanResult:
    """Page the ephemeral Atom surface with a hard 930-entry safety boundary."""

    if page_size <= 0 or page_size > ATOM_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {ATOM_PAGE_SIZE}")
    if entry_limit <= 0 or entry_limit > ATOM_EPHEMERAL_ENTRY_LIMIT:
        raise ValueError(
            f"entry_limit must be between 1 and {ATOM_EPHEMERAL_ENTRY_LIMIT}"
        )
    known = {normalize_accession(value) for value in known_accessions}
    boundary = None
    if overlap_before:
        boundary = datetime.fromisoformat(overlap_before.replace("Z", "+00:00"))
        if boundary.tzinfo is None:
            boundary = boundary.replace(tzinfo=timezone.utc)
    collected: list[FilingDiscovery] = []
    seen: set[str] = set()
    pages = 0
    start = 0
    while start < entry_limit:
        count = min(page_size, entry_limit - start)
        url = _atom_page_url(base_url, start=start, count=count)
        page = parse_latest_filings_atom(_fetch_bytes(fetch, url))
        pages += 1
        if not page:
            return AtomScanResult(tuple(collected), pages, True, "short_page")
        page_accessions = {entry.accession for entry in page}
        new_count = 0
        for offset, entry in enumerate(page, start=start + 1):
            if entry.accession in seen:
                continue
            seen.add(entry.accession)
            collected.append(replace(entry, source_ordinal=offset))
            new_count += 1
        if len(page) < count:
            return AtomScanResult(tuple(collected), pages, True, "short_page")
        if boundary and page_accessions and page_accessions.issubset(known):
            stamps = []
            for entry in page:
                if not entry.accepted_at:
                    continue
                stamp = datetime.fromisoformat(entry.accepted_at)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                stamps.append(stamp)
            if stamps and min(stamps) < boundary:
                return AtomScanResult(tuple(collected), pages, True, "known_overlap")
        if new_count == 0:
            return AtomScanResult(tuple(collected), pages, False, "stalled")
        start += count
    return AtomScanResult(tuple(collected), pages, False, "ephemeral_limit")


def parse_master_index(source: bytes | str) -> pd.DataFrame:
    """Parse the 13F family from a daily or full EDGAR master index."""

    text = source.decode("latin-1") if isinstance(source, bytes) else source
    lines = text.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().lower()
            in {
                "cik|company name|form type|date filed|file name",
                "cik|company name|form type|date filed|filename",
            }
        ),
        None,
    )
    if header_index is None:
        raise SecSourceError("master index header not found")
    records: list[dict[str, Any]] = []
    source_ordinal = 0
    for line in lines[header_index + 1 :]:
        if not line.strip() or set(line.strip()) == {"-"}:
            continue
        parts = line.split("|", 4)
        if len(parts) != 5:
            raise SecSourceError(f"invalid master-index row: {line!r}")
        source_ordinal += 1
        cik_raw, company_name, form, filed, file_name = parts
        form = form.strip().upper()
        if form not in FORM_TYPES:
            continue
        accession_match = _ACCESSION_RE.search(file_name)
        if not accession_match:
            raise SecSourceError(f"13F master row lacks accession path: {line!r}")
        records.append(
            {
                "source_ordinal": source_ordinal,
                "cik": normalize_cik(cik_raw),
                "company_name": _text(company_name),
                "form": form,
                "filing_date": normalize_date(filed),
                "file_name": file_name.strip(),
                "accession": normalize_accession(accession_match.group(1)),
            }
        )
    return pd.DataFrame.from_records(
        records,
        columns=[
            "source_ordinal",
            "cik",
            "company_name",
            "form",
            "filing_date",
            "file_name",
            "accession",
        ],
    )


def _index_json_url(index_url: str) -> tuple[str, str]:
    parsed = urlparse(index_url)
    if parsed.path.endswith("/index.json"):
        base = index_url.rsplit("/", 1)[0] + "/"
        return index_url, base
    base = index_url.rsplit("/", 1)[0] + "/"
    return urljoin(base, "index.json"), base


def _json_mapping(source: bytes | str | Mapping[str, Any]) -> tuple[Mapping[str, Any], bytes]:
    if isinstance(source, Mapping):
        body = json.dumps(source, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return source, body
    body = source if isinstance(source, bytes) else source.encode("utf-8")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SecSourceError(f"invalid filing index JSON: {exc}") from exc
    if not isinstance(parsed, Mapping):
        raise SecSourceError("filing index JSON must be an object")
    return parsed, body


def parse_filing_index(
    source: bytes | str | Mapping[str, Any],
    *,
    index_url: str,
) -> tuple[FilingIndexDocument, ...]:
    """Parse one archive ``index.json`` into safe document descriptors."""

    payload, _ = _json_mapping(source)
    items = ((payload.get("directory") or {}).get("item") or [])
    if not isinstance(items, list):
        raise SecSourceError("filing index directory.item must be a list")
    _, base = _index_json_url(index_url)
    documents: list[FilingIndexDocument] = []
    for ordinal, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            raise SecSourceError("filing index item must be an object")
        name = _text(item.get("name"))
        if not name or Path(name).name != name or name in {".", ".."}:
            raise SecSourceError(f"unsafe filing document name: {name!r}")
        documents.append(
            FilingIndexDocument(
                source_ordinal=ordinal,
                name=name,
                url=urljoin(base, name),
                size=_int(item.get("size")),
                last_modified=_text(item.get("last-modified")),
            )
        )
    return tuple(documents)


def _submission_header(source: bytes | str | None) -> dict[str, str | None]:
    if source is None:
        return {}
    text = source.decode("latin-1") if isinstance(source, bytes) else source
    text = unescape(text)
    patterns = {
        "accepted_at": r"<ACCEPTANCE-DATETIME>\s*(\d{14})",
        "accession": r"^\s*ACCESSION NUMBER:\s*([^\r\n]+)",
        "form": r"^\s*CONFORMED SUBMISSION TYPE:\s*([^\r\n]+)",
        "period_end": r"^\s*CONFORMED PERIOD OF REPORT:\s*([^\r\n]+)",
        "filing_date": r"^\s*FILED AS OF DATE:\s*([^\r\n]+)",
    }
    values: dict[str, str | None] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        values[key] = _text(match.group(1)) if match else None
    if values.get("accepted_at"):
        values["accepted_at"] = normalize_timestamp(values["accepted_at"])
    if values.get("accession"):
        values["accession"] = normalize_accession(values["accession"])
    if values.get("form"):
        values["form"] = values["form"].upper()
    if values.get("period_end"):
        values["period_end"] = normalize_date(values["period_end"])
    if values.get("filing_date"):
        values["filing_date"] = normalize_date(values["filing_date"])
    return values


def _accession_from_index_url(index_url: str) -> str | None:
    matches = _ACCESSION_RE.findall(index_url)
    if matches:
        return normalize_accession(matches[-1])
    parsed = urlparse(index_url)
    for part in reversed(parsed.path.split("/")):
        compact = part.replace("-", "")
        if _ACCESSION_NODASH_RE.fullmatch(compact):
            return normalize_accession(compact)
    return None


def _frame_from_records(records: list[dict[str, Any]], columns: Sequence[str]) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(records, columns=list(columns))
    if frame.empty:
        return _empty_frame(columns)
    for column in _INTEGER_TABLE_COLUMNS.intersection(frame.columns):
        frame[column] = pd.array(frame[column], dtype="Int64")
    for column in _BOOLEAN_TABLE_COLUMNS.intersection(frame.columns):
        frame[column] = pd.array(frame[column], dtype="boolean")
    if "source_ordinal" in frame:
        frame["source_ordinal"] = frame["source_ordinal"].astype("int64")
    typed_columns = {
        "source_ordinal",
        *_INTEGER_TABLE_COLUMNS,
        *_BOOLEAN_TABLE_COLUMNS,
    }
    for column in set(frame.columns) - typed_columns:
        normalized = frame[column].map(_text).astype("object")
        frame[column] = normalized.where(normalized.notna(), None)
    return frame.loc[:, list(columns)]


def _parse_primary_xml(
    root: ET.Element,
    *,
    accession: str,
    filing_date: str | None,
    accepted_at: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    header = _descendant(root, "headerData")
    filer_info = _descendant(header, "filerInfo")
    credentials = _descendant(filer_info, "credentials")
    cik = normalize_cik(_child_text(credentials, "cik"))
    form = (_child_text(header, "submissionType") or "").upper()
    period_end = normalize_date(_child_text(filer_info, "periodOfReport"))
    if form not in FORM_TYPES:
        raise SecSourceError(f"unsupported filing submission type: {form!r}")
    submission = pd.DataFrame.from_records(
        [
            {
                "accession": accession,
                "filing_date": filing_date,
                "form": form,
                "cik": cik,
                "period_end": period_end,
                "accepted_at": accepted_at,
            }
        ],
        columns=SUBMISSION_COLUMNS,
    )

    form_data = _descendant(root, "formData")
    cover = _child(form_data, "coverPage")
    if cover is None:
        raise SecSourceError("primary Form 13F XML lacks coverPage")
    filing_manager = _child(cover, "filingManager")
    address = _child(filing_manager, "address")
    amendment_info = _child(cover, "amendmentInfo")
    cover_record = {
        "source_ordinal": 1,
        "accession": accession,
        "report_calendar_or_quarter": normalize_date(
            _child_text(cover, "reportCalendarOrQuarter")
        ),
        "is_amendment": _bool(_child_text(cover, "isAmendment")),
        "amendment_number": _int(_child_text(cover, "amendmentNo")),
        "amendment_type": (
            _text(_child_text(amendment_info, "amendmentType"))
            or _text(_child_text(cover, "amendmentType"))
            or ""
        ).upper()
        or None,
        "confidential_denied_or_expired": _bool(
            _child_text(amendment_info, "confDeniedExpired")
            or _child_text(amendment_info, "confDeniedExpiredFlag")
            or _child_text(cover, "confDeniedExpired")
            or _child_text(cover, "confDeniedExpiredFlag")
        ),
        "date_denied_or_expired": normalize_date(
            _child_text(amendment_info, "dateDeniedExpired")
            or _child_text(cover, "dateDeniedExpired")
        ),
        "date_reported": normalize_date(
            _child_text(amendment_info, "dateReported")
            or _child_text(cover, "dateReported")
        ),
        "reason_for_non_confidentiality": _text(
            _child_text(amendment_info, "reasonForNonConfidentiality")
            or _child_text(cover, "reasonForNonConfidentiality")
        ),
        "filing_manager_name": _text(_child_text(filing_manager, "name")),
        "filing_manager_street1": _text(_child_text(address, "street1")),
        "filing_manager_street2": _text(_child_text(address, "street2")),
        "filing_manager_city": _text(_child_text(address, "city")),
        "filing_manager_state_or_country": _text(
            _child_text(address, "stateOrCountry")
        ),
        "filing_manager_zipcode": _text(_child_text(address, "zipCode")),
        "report_type": (_text(_child_text(cover, "reportType")) or "").upper() or None,
        "form_13f_file_number": _text(_child_text(cover, "form13FFileNumber")),
        "crd_number": _text(_child_text(cover, "crdNumber")),
        "sec_file_number": _text(_child_text(cover, "secFileNumber")),
        "provide_info_for_instruction5": _bool(
            _child_text(cover, "provideInfoForInstruction5")
        ),
        "additional_information": _text(_child_text(cover, "additionalInformation")),
    }
    cover_pages = _frame_from_records([cover_record], COVER_PAGE_COLUMNS)

    reported_records: list[dict[str, Any]] = []
    other_info = _child(cover, "otherManagersInfo")
    for ordinal, manager in enumerate(_children(other_info, "otherManager"), start=1):
        reported_records.append(
            {
                "source_ordinal": ordinal,
                "accession": accession,
                "filer_cik": cik,
                "other_manager_sk": None,
                "reporting_manager_cik": normalize_cik(_child_text(manager, "cik")),
                "form_13f_file_number": _text(
                    _child_text(manager, "form13FFileNumber")
                ),
                "crd_number": _text(_child_text(manager, "crdNumber")),
                "sec_file_number": _text(_child_text(manager, "secFileNumber")),
                "manager_name": _text(_child_text(manager, "name")),
                "relation_type": "filer_holdings_reported_by_manager",
            }
        )
    reported_by = _frame_from_records(reported_records, REPORTED_BY_COLUMNS)

    summary = _child(form_data, "summaryPage")
    summary_records: list[dict[str, Any]] = []
    included_records: list[dict[str, Any]] = []
    if summary is not None:
        summary_records.append(
            {
                "source_ordinal": 1,
                "accession": accession,
                "other_included_managers_count": _int(
                    _child_text(summary, "otherIncludedManagersCount")
                ),
                "table_entry_total": _int(_child_text(summary, "tableEntryTotal")),
                "table_value_total": _int(_child_text(summary, "tableValueTotal")),
                "is_confidential_omitted": _bool(
                    _child_text(summary, "isConfidentialOmitted")
                ),
            }
        )
        managers2 = _child(summary, "otherManagers2Info")
        for ordinal, manager in enumerate(
            _children(managers2, "otherManager2"), start=1
        ):
            # X0202 puts identity inside an inner otherManager while the
            # sequence stays on the outer otherManager2 row.  Older filings can
            # expose the identity fields directly, so retain that fallback.
            manager_identity = _child(manager, "otherManager")
            if manager_identity is None:
                manager_identity = manager
            included_records.append(
                {
                    "source_ordinal": ordinal,
                    "accession": accession,
                    "filer_cik": cik,
                    "sequence_number": _int(_child_text(manager, "sequenceNumber")),
                    "included_manager_cik": normalize_cik(
                        _child_text(manager_identity, "cik")
                    ),
                    "form_13f_file_number": _text(
                        _child_text(manager_identity, "form13FFileNumber")
                    ),
                    "crd_number": _text(
                        _child_text(manager_identity, "crdNumber")
                    ),
                    "sec_file_number": _text(
                        _child_text(manager_identity, "secFileNumber")
                    ),
                    "manager_name": _text(_child_text(manager_identity, "name")),
                    "relation_type": "manager_included_in_filing",
                }
            )
    return (
        submission,
        cover_pages,
        _frame_from_records(summary_records, SUMMARY_PAGE_COLUMNS),
        reported_by,
        _frame_from_records(included_records, INCLUDED_MANAGER_COLUMNS),
    )


def _parse_information_xml(
    roots: Sequence[ET.Element],
    *,
    accession: str,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for root in roots:
        for row in root.iter():
            if _local_name(row.tag) != "infoTable":
                continue
            amount = _child(row, "shrsOrPrnAmt")
            votes = _child(row, "votingAuthority")
            records.append(
                {
                    "source_ordinal": len(records) + 1,
                    "accession": accession,
                    "info_table_sk": None,
                    "issuer_name": _text(_child_text(row, "nameOfIssuer")),
                    "title_of_class": _text(_child_text(row, "titleOfClass")),
                    "cusip": (_text(_child_text(row, "cusip")) or "").upper() or None,
                    "figi": (_text(_child_text(row, "figi")) or "").upper() or None,
                    "value": _int(_child_text(row, "value")),
                    "shares_or_principal_amount": _int(
                        _child_text(amount, "sshPrnamt")
                    ),
                    "shares_or_principal_amount_type": (
                        _text(_child_text(amount, "sshPrnamtType")) or ""
                    ).upper()
                    or None,
                    "put_call": (_text(_child_text(row, "putCall")) or "").upper()
                    or None,
                    "investment_discretion": (
                        _text(_child_text(row, "investmentDiscretion")) or ""
                    ).upper()
                    or None,
                    "other_manager": _text(_child_text(row, "otherManager")),
                    "voting_authority_sole": _int(_child_text(votes, "Sole")),
                    "voting_authority_shared": _int(_child_text(votes, "Shared")),
                    "voting_authority_none": _int(_child_text(votes, "None")),
                }
            )
    return _frame_from_records(records, HOLDING_COLUMNS)


def _framed_digest(parts: Sequence[tuple[str, bytes]]) -> str:
    digest = sha256()
    for name, body in sorted(parts, key=lambda item: item[0]):
        name_bytes = name.encode("utf-8")
        digest.update(len(name_bytes).to_bytes(8, "big"))
        digest.update(name_bytes)
        digest.update(len(body).to_bytes(8, "big"))
        digest.update(body)
    return digest.hexdigest()


def parse_filing_package(
    *,
    index_url: str,
    index_source: bytes | str | Mapping[str, Any],
    documents: Mapping[str, bytes | str],
    discovery: FilingDiscovery | None = None,
) -> BulkTables:
    """Parse one archive index plus its fetched XML/text documents."""

    index_payload, index_body = _json_mapping(index_source)
    descriptors = parse_filing_index(index_payload, index_url=index_url)
    descriptor_by_name = {item.name: item for item in descriptors}
    expected_names = {item.name for item in descriptors}
    unknown = sorted(set(documents) - expected_names)
    if unknown:
        raise SecSourceError(f"documents absent from filing index: {unknown}")
    body_by_name = {
        name: value if isinstance(value, bytes) else value.encode("utf-8")
        for name, value in documents.items()
    }
    missing_xml = sorted(
        item.name
        for item in descriptors
        if item.name.lower().endswith(".xml") and item.name not in body_by_name
    )
    if missing_xml:
        raise SecSourceError(f"indexed filing XML was not supplied: {missing_xml}")
    for name, body in body_by_name.items():
        expected_size = descriptor_by_name[name].size
        if expected_size is not None and len(body) != expected_size:
            # SEC's index.json `size` is advisory: it provably disagrees with
            # SEC's own Content-Length and served bytes (block-rounded values
            # observed in production). Transport truncation is gated
            # authoritatively at fetch time against Content-Length.
            print(
                "::warning title=sec-index-size-mismatch::"
                f"{index_url} {name}: index={expected_size}, "
                f"body={len(body)}",
                flush=True,
            )

    header_name = next(
        (
            name
            for name in body_by_name
            if name.lower().endswith("-index-headers.html")
        ),
        None,
    )
    if header_name is None:
        header_name = next(
            (name for name in body_by_name if name.lower().endswith(".txt")), None
        )
    header = _submission_header(
        body_by_name.get(header_name) if header_name is not None else None
    )
    accession_candidates = {
        label: normalize_accession(value)
        for label, value in (
            ("header", header.get("accession")),
            ("discovery", discovery.accession if discovery else None),
            ("index_url", _accession_from_index_url(index_url)),
        )
        if value
    }
    unique_accessions = set(accession_candidates.values())
    if not unique_accessions:
        raise SecSourceError("could not determine filing accession")
    if len(unique_accessions) != 1:
        raise SecSourceError(f"filing accession mismatch: {accession_candidates}")
    accession = next(iter(unique_accessions))

    archive_match = _ARCHIVE_LINK_RE.search(index_url)
    archive_cik = None
    if archive_match:
        archive_cik = normalize_cik(archive_match.group("cik"))
        if archive_match.group("directory") != accession.replace("-", ""):
            raise SecSourceError(
                "filing archive directory does not match accession number"
            )

    filing_dates = {
        value
        for value in (
            header.get("filing_date"),
            normalize_date(discovery.filing_date) if discovery else None,
        )
        if value
    }
    if len(filing_dates) > 1:
        raise SecSourceError(f"filing date mismatch: {sorted(filing_dates)}")
    filing_date = next(iter(filing_dates), None)
    acceptance_times = {
        value
        for value in (
            header.get("accepted_at"),
            normalize_timestamp(discovery.accepted_at) if discovery else None,
        )
        if value
    }
    if len(acceptance_times) > 1:
        raise SecSourceError(
            f"filing acceptance timestamp mismatch: {sorted(acceptance_times)}"
        )
    accepted_at = next(iter(acceptance_times), None)

    primary_root: ET.Element | None = None
    information_roots: list[ET.Element] = []
    for descriptor in descriptors:
        if not descriptor.name.lower().endswith(".xml"):
            continue
        body = body_by_name.get(descriptor.name)
        if body is None:
            continue
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise SecSourceError(
                f"invalid filing XML {descriptor.name}: {exc}"
            ) from exc
        if _descendant(root, "headerData") is not None and _descendant(
            root, "formData"
        ) is not None:
            if primary_root is not None:
                raise SecSourceError("filing contains multiple primary Form 13F XML files")
            primary_root = root
        elif any(_local_name(item.tag) == "infoTable" for item in root.iter()):
            information_roots.append(root)
    if primary_root is None:
        raise SecSourceError("filing index contains no primary Form 13F XML")

    (
        submissions,
        cover_pages,
        summary_pages,
        reported_by,
        included_managers,
    ) = _parse_primary_xml(
        primary_root,
        accession=accession,
        filing_date=filing_date,
        accepted_at=accepted_at,
    )
    if discovery:
        row = submissions.iloc[0]
        if row["cik"] != normalize_cik(discovery.cik):
            raise SecSourceError(
                f"filing CIK mismatch: XML={row['cik']}, discovery={discovery.cik}"
            )
        if row["form"] != discovery.form.upper():
            raise SecSourceError(
                f"filing form mismatch: XML={row['form']}, discovery={discovery.form}"
            )
    if header.get("form") and submissions.iloc[0]["form"] != header["form"]:
        raise SecSourceError("filing form mismatch between SGML header and primary XML")
    if header.get("period_end") and submissions.iloc[0]["period_end"] != header["period_end"]:
        raise SecSourceError("filing period mismatch between SGML header and primary XML")
    if archive_cik and submissions.iloc[0]["cik"] != archive_cik:
        raise SecSourceError(
            f"filing CIK mismatch: XML={submissions.iloc[0]['cik']}, "
            f"archive_path={archive_cik}"
        )

    holdings = _parse_information_xml(information_roots, accession=accession)
    if submissions.iloc[0]["form"].startswith("13F-HR") and not summary_pages.empty:
        expected_entries = summary_pages.iloc[0]["table_entry_total"]
        if not pd.isna(expected_entries) and int(expected_entries) > 0 and holdings.empty:
            raise SecSourceError(
                "holdings report has a positive tableEntryTotal but no information rows"
            )
    digest_parts = [("index.json", index_body), *body_by_name.items()]
    tables = BulkTables(
        submissions=submissions,
        cover_pages=cover_pages,
        summary_pages=summary_pages,
        holdings=holdings,
        reported_by=reported_by,
        included_managers=included_managers,
        source_sha256=_framed_digest(digest_parts),
        source_bytes=sum(len(body) for _, body in digest_parts),
    )
    _validate_normalized_structure(tables)
    return tables


def read_filing_package(
    index_url: str,
    fetch: Callable[[str], Any],
    *,
    discovery: FilingDiscovery | None = None,
) -> BulkTables:
    """Fetch through an injected callable and parse one filing package."""

    json_url, _ = _index_json_url(index_url)
    index_body = _fetch_bytes(fetch, json_url)
    descriptors = parse_filing_index(index_body, index_url=json_url)
    documents: dict[str, bytes] = {}
    has_header_document = any(
        item.name.lower().endswith("-index-headers.html") for item in descriptors
    )
    for descriptor in descriptors:
        lower = descriptor.name.lower()
        should_fetch = (
            lower.endswith(".xml")
            or lower.endswith("-index-headers.html")
            or (lower.endswith(".txt") and not has_header_document)
        )
        if should_fetch:
            documents[descriptor.name] = _fetch_bytes(fetch, descriptor.url)
    return parse_filing_package(
        index_url=index_url,
        index_source=index_body,
        documents=documents,
        discovery=discovery,
    )


__all__ = [
    "ATOM_EPHEMERAL_ENTRY_LIMIT",
    "ATOM_PAGE_SIZE",
    "BulkInvariantFinding",
    "BulkTables",
    "FilingDiscovery",
    "FilingIndexDocument",
    "FORM_TYPES",
    "HOLDING_COLUMNS",
    "INCLUDED_MANAGER_COLUMNS",
    "LATEST_FILINGS_ATOM_URL",
    "REPORTED_BY_COLUMNS",
    "SecSourceError",
    "AtomScanResult",
    "iter_bulk_holding_chunks",
    "normalize_accession",
    "normalize_cik",
    "normalize_date",
    "parse_filing_index",
    "parse_filing_package",
    "parse_latest_filings_atom",
    "parse_master_index",
    "read_bulk_package",
    "read_filing_package",
    "scan_latest_filings_atom",
    "validate_bulk_invariants",
]
