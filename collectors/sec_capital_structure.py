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
import html as stdlib_html
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo
from xml.etree import ElementTree

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from engine.capital_structure.source_identity import (
    ChildOccurrenceUnbound,
    EvidenceIdentityError,
    classify_bundle_against_published,
    document_inner_spans,
    evidence_id_for,
    manifest_id_for,
    merge_manifest_ledgers,
    published_first_known_at,
    validate_manifest_identity,
    validate_manifest_ledger,
    writable_child_occurrence,
)
from engine.capital_structure.ingestion_health import (
    INGESTION_RUN_FILENAME,
    build_ingestion_run,
    source_high_watermark,
)
from engine.capital_structure.sec_discovery_clock import (
    DISCOVERY_CLOCK_POLICY_VERSION,
    SEC_TIMEZONE,
    daily_reconciliation_updated_boundary,
    is_sec_calendar_closed,
    latest_expected_daily_index_date,
    latest_expected_realtime_filing_date,
)
from engine.capital_structure.source_ledger_io import (
    read_source_ledger,
    source_ledger_path,
    write_source_ledger,
)
from engine.capital_structure.source_store import format_store_failure

log = logging.getLogger(__name__)

_DAILY_IDX = "https://www.sec.gov/Archives/edgar/daily-index/{yr}/QTR{q}/form.{ds}.idx"
_LATEST_FILINGS = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom&count={count}&start={start}"
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
    "policy_version": "capital-structure-sec-form-policy/1.2.0",
    "wave1_discovery": sorted(TARGET_FORMS),
    # Reconciliation forms are never blanket-collected.  They are admitted only
    # for an issuer that already has a retained/discovered in-policy registration
    # or issuance filing (including a same-index registration).  Keeping the old
    # field below preserves the explicit distinction between that scoped lane and
    # a claim of market-wide coverage.
    "issuer_scoped_reconciliation": sorted(DECLARED_WAVE2_RECONCILIATION_FORMS),
    "wave2_declared_not_collected": sorted(DECLARED_WAVE2_RECONCILIATION_FORMS),
    "capital_relevant_declared_not_collected": sorted(
        CAPITAL_RELEVANT_DECLARED_NOT_COLLECTED
    ),
}

LOOKBACK_DAYS_FIRST = 90
LOOKBACK_DAYS_NIGHTLY = 7
RETRIEVAL_QUEUE_AGING_DAYS = 7
INDEX_NOT_PUBLISHED_GRACE_DAYS = 7
PACE_SECONDS = 0.12
LATEST_FILINGS_PAGE_SIZE = 100
MAX_LATEST_FILINGS_PAGES = 200
GROUP = "capital_structure"

# The collector must make bounded progress across every evidence family rather
# than repeatedly spending a whole run on the most numerous form type.  The
# slots are a deterministic weighted round-robin schedule, rotated by UTC date
# so a small run has no permanently privileged lane.  Within each lane, aged
# filings are always considered before new filings.
RETRIEVAL_LANE_WEIGHTS = {
    "registration": 4,
    "state": 2,
    "prospectus": 2,
    "reg_a": 1,
    "issuer_current_report": 2,
    "issuer_periodic": 2,
    "issuer_proxy": 1,
}
RETRIEVAL_LANE_ORDER = tuple(RETRIEVAL_LANE_WEIGHTS)
DISCOVERY_SCOPE_REGISTRATION = "registration_issuance"
DISCOVERY_SCOPE_RECONCILIATION = "issuer_reconciliation"

# W2 scheduler metadata is deliberately kept out of the source/evidence/event
# identity plane.  W2B keeps the reservations as the one canonical retrieval
# capacity configuration: the global ceiling is their sum, so a cap and its
# class guarantees cannot drift independently.  This changes no queue, cadence,
# source, evidence store, or publication authority.
WORK_CLASS_ORDER = (
    "LIVE_TAIL",
    "RECOVERY",
    "HISTORICAL_BACKFILL",
)
WORK_CLASS_RESERVATIONS = {
    "LIVE_TAIL": 500,
    "RECOVERY": 20,
    "HISTORICAL_BACKFILL": 20,
}
MAX_FILINGS_PER_RUN = sum(WORK_CLASS_RESERVATIONS.values())
LIVE_TAIL_SESSION_COUNT = 5
RECOVERY_SESSION_COUNT = 20

# A filing whose retrieval keeps failing may not be retried forever.  Before this
# bound, a systematic defect (the 2026-08-06 NaN manifest abort below) re-deferred
# the SAME filings every night: 130 identical warnings on 2026-08-06, and the count
# could only grow, because nothing ever left the queue.  That is the creep shape —
# an unbounded backlog whose only symptom is log volume.
#
# Three recorded unclosed attempts park an accession.  Parking is a QUEUE
# decision, never an evidence decision: no manifest, attempt row, or discovery row
# is deleted or rewritten, so a parked filing is still fully auditable and raising
# ``CS_MAX_RETRIEVAL_ATTEMPTS`` picks it straight back up.  The parked count is
# printed every run, so a bounded backlog stays visible instead of going quiet.
MAX_RETRIEVAL_ATTEMPTS = 3
MAX_RETRIEVAL_ATTEMPTS_ENV = "CS_MAX_RETRIEVAL_ATTEMPTS"
# ``storage_deferred``/``transient_error`` retained NOTHING: the retrieval itself
# failed and the attempt row is the only thing left to show for it.
_RETRIEVAL_FAILURE_STATES = frozenset({"storage_deferred", "transient_error"})
# What the bound must count is an attempt that left the queue item OPEN, and that
# is a strictly larger set.  ``stored`` closes the item through ``have_complete``.
# ``stored_parser_deferred`` does NOT: it retained the bytes, but
# ``_eligible_complete_accessions`` admits only ``eligible``/``clean`` manifests,
# so a parser-deferred filing is never in ``have_complete`` and re-enters the
# queue every night.  Counting only the two retrieval failures therefore left the
# WORST class of filing — an SEC error page, a corrupt bundle, suspect bytes — as
# the one backlog the bound could never close.  That is the same creep shape,
# reopened for exactly the filings least likely to heal on their own.
_UNCLOSED_ATTEMPT_STATES = _RETRIEVAL_FAILURE_STATES | {"stored_parser_deferred"}

_DISCOVERY_COLUMNS = [
    "accession", "cik", "ticker", "company_name", "form", "filing_date",
    "file_path", "canonical_url", "collection_scope", "_first_seen",
    "discovery_channel", "latest_filings_updated_at", "latest_filings_role",
    "reconciled_at",
]
_COVERAGE_COLUMNS = [
    "index_date", "status", "target_count", "attempt_count", "last_attempt_at",
    "last_error", "policy_version", "coverage_kind", "observed_through",
    "discovery_clock_policy_version",
]
_ATTEMPT_COLUMNS = [
    "attempt_id", "accession", "source_id", "canonical_url", "attempted_at",
    "state", "error", "content_sha256", "retrieval_lane", "collection_scope",
    "http_status", "storage_operation", "store_id", "error_class",
    "observed_evidence_ids", "retained_available_at", "work_class",
]

class IndexNotPublished(RuntimeError):
    """A historical SEC daily-index object has no published archive object."""

    def __init__(self, value: date, status_code: int) -> None:
        self.index_date = value
        self.status_code = status_code
        super().__init__(f"SEC daily index HTTP {status_code}: {value}")


class LatestFilingsTraversalIncomplete(RuntimeError):
    """The bounded Atom traversal could not prove a durable-watermark boundary."""


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


def _normalized_cik(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw.isdigit() or len(raw) > 10:
        return None
    return raw.zfill(10)


def _issuer_scope_ciks(discovery: pd.DataFrame) -> set[str]:
    """Return only issuers anchored by the registration/issuance form policy."""
    if discovery.empty or not {"form", "cik"}.issubset(discovery.columns):
        return set()
    return {
        cik
        for form, raw_cik in zip(discovery["form"], discovery["cik"])
        if str(form or "").upper() in TARGET_FORMS
        if (cik := _normalized_cik(raw_cik)) is not None
    }


def parse_form_index(
    text: str,
    *,
    target_forms: set[str] | None = None,
    reconciliation_ciks: Iterable[str] | None = None,
    include_same_index_issuers: bool = False,
) -> list[dict]:
    """Parse target rows from an EDGAR ``form.YYYYMMDD.idx`` file.

    The function is pure and retains the archive path so the exact source can be
    retrieved later. The response structure and every filing row are validated
    before an empty target result can be treated as a successful zero-target day.
    """
    wanted = TARGET_FORMS if target_forms is None else {
        str(form).upper() for form in target_forms
    }
    scoped_ciks = {
        normalized
        for raw_cik in (reconciliation_ciks or ())
        if (normalized := _normalized_cik(raw_cik)) is not None
    }
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

    parsed_rows: list[dict] = []
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
        accession = Path(file_path).stem
        parsed_rows.append({
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
    if include_same_index_issuers:
        scoped_ciks.update(
            row["cik"] for row in parsed_rows if row["form"] in wanted
        )

    rows: list[dict] = []
    for row in parsed_rows:
        form = row["form"]
        if form in wanted:
            rows.append(row | {"collection_scope": DISCOVERY_SCOPE_REGISTRATION})
        elif (
            form in DECLARED_WAVE2_RECONCILIATION_FORMS
            and row["cik"] in scoped_ciks
        ):
            rows.append(row | {"collection_scope": DISCOVERY_SCOPE_RECONCILIATION})
    return rows


_ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
_ATOM_ACCESSION_RE = re.compile(r"accession-number=(\d{10}-\d{2}-\d{6})$")
_ATOM_SUMMARY_RE = re.compile(
    r"Filed:\s*(\d{4}-\d{2}-\d{2})\s+AccNo:\s*(\d{10}-\d{2}-\d{6})\b",
    re.I,
)
_ATOM_TITLE_RE = re.compile(
    r"^(.+?)\s+-\s+(.+)\s+\((\d{1,10})\)\s+\(([^()]+)\)$",
)


def _aware_datetime(value: object, *, field: str) -> datetime:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_latest_filings_atom(text: str) -> dict[str, Any]:
    """Parse and strictly validate one official SEC Latest Filings Atom page."""
    payload = re.sub(r"^\s*<\?xml[^>]*\?>", "", str(text), count=1).strip()
    if not payload:
        raise ValueError("SEC Latest Filings response is empty")
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError("SEC Latest Filings response is not valid Atom XML") from exc
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ValueError("SEC Latest Filings response has no Atom feed root")
    feed_updated = root.findtext("atom:updated", default="", namespaces=_ATOM_NAMESPACE)
    observed_through = _utc_iso(
        _aware_datetime(feed_updated, field="Latest Filings feed.updated"),
    )
    entries: list[dict[str, Any]] = []
    for order, element in enumerate(root.findall("atom:entry", _ATOM_NAMESPACE)):
        entry_id = element.findtext("atom:id", default="", namespaces=_ATOM_NAMESPACE)
        accession_match = _ATOM_ACCESSION_RE.search(entry_id.strip())
        if not accession_match:
            raise ValueError("SEC Latest Filings entry has no canonical accession id")
        accession = accession_match.group(1)
        category = element.find("atom:category", _ATOM_NAMESPACE)
        form = str(category.get("term") if category is not None else "").strip().upper()
        title = element.findtext("atom:title", default="", namespaces=_ATOM_NAMESPACE).strip()
        title_match = _ATOM_TITLE_RE.fullmatch(title)
        if not title_match:
            raise ValueError(f"SEC Latest Filings title is malformed for {accession}")
        title_form, company_name, cik, role = title_match.groups()
        if title_form.strip().upper() != form or not form:
            raise ValueError(f"SEC Latest Filings form identity disagrees for {accession}")
        summary = element.findtext(
            "atom:summary", default="", namespaces=_ATOM_NAMESPACE,
        )
        summary_text = re.sub(r"<[^>]+>", " ", stdlib_html.unescape(summary))
        summary_text = re.sub(r"\s+", " ", summary_text).strip()
        summary_match = _ATOM_SUMMARY_RE.search(summary_text)
        if not summary_match or summary_match.group(2) != accession:
            raise ValueError(f"SEC Latest Filings summary identity disagrees for {accession}")
        filing_date = summary_match.group(1)
        try:
            date.fromisoformat(filing_date)
        except ValueError as exc:
            raise ValueError(
                f"SEC Latest Filings filing date is invalid for {accession}",
            ) from exc
        updated = _utc_iso(_aware_datetime(
            element.findtext("atom:updated", default="", namespaces=_ATOM_NAMESPACE),
            field=f"Latest Filings entry.updated {accession}",
        ))
        entries.append({
            "accession": accession,
            "cik": cik.zfill(10),
            "company_name": company_name.strip(),
            "form": form,
            "filing_date": filing_date,
            "latest_filings_updated_at": updated,
            "latest_filings_role": role.strip(),
            "_feed_order": order,
        })
    updated_values = [
        _aware_datetime(row["latest_filings_updated_at"], field="entry.updated")
        for row in entries
    ]
    if any(older > newer for newer, older in zip(updated_values, updated_values[1:])):
        raise ValueError("SEC Latest Filings entries are not newest-first")
    return {"observed_through": observed_through, "entries": entries}


def _role_rank(value: object) -> int:
    return {"filer": 0, "issuer": 1}.get(str(value or "").strip().lower(), 2)


def _first_entry_per_accession(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in entries:
        row = dict(raw)
        grouped.setdefault(str(row.get("accession") or ""), []).append(row)
    selected = [
        min(
            candidates,
            key=lambda row: (
                _role_rank(row.get("latest_filings_role")),
                int(row.get("_scan_order") or row.get("_feed_order") or 0),
            ),
        )
        for accession, candidates in grouped.items()
        if accession
    ]
    return sorted(
        selected,
        key=lambda row: int(row.get("_scan_order") or row.get("_feed_order") or 0),
    )


def latest_filings_discovery_rows(
    entries: Sequence[Mapping[str, Any]],
    *,
    existing_discovery: pd.DataFrame,
    cik_tickers: Mapping[int, str],
    first_seen: str,
) -> list[dict[str, Any]]:
    """Apply the unchanged form and issuer-scope law to provisional Atom rows."""
    target_entries = [
        dict(row) for row in entries
        if str(row.get("form") or "").upper() in TARGET_FORMS
    ]
    selected_targets = _first_entry_per_accession(target_entries)
    scoped_ciks = _issuer_scope_ciks(existing_discovery)
    scoped_ciks.update(str(row["cik"]) for row in selected_targets)
    reconciliation_entries = [
        dict(row) for row in entries
        if str(row.get("form") or "").upper()
        in DECLARED_WAVE2_RECONCILIATION_FORMS
        and _normalized_cik(row.get("cik")) in scoped_ciks
    ]
    selected = _first_entry_per_accession([
        *selected_targets, *reconciliation_entries,
    ])
    rows: list[dict[str, Any]] = []
    for entry in selected:
        accession = str(entry["accession"])
        cik = str(entry["cik"]).zfill(10)
        compact = accession.replace("-", "")
        file_path = f"edgar/data/{int(cik)}/{compact}/{accession}.txt"
        form = str(entry["form"]).upper()
        rows.append({
            "accession": accession,
            "cik": cik,
            "ticker": cik_tickers.get(int(cik)),
            "company_name": str(entry["company_name"]),
            "form": form,
            "filing_date": str(entry["filing_date"]),
            "file_path": file_path,
            "canonical_url": _ARCHIVES + file_path,
            "collection_scope": (
                DISCOVERY_SCOPE_REGISTRATION
                if form in TARGET_FORMS else DISCOVERY_SCOPE_RECONCILIATION
            ),
            "_first_seen": first_seen,
            "discovery_channel": "latest_filings",
            "latest_filings_updated_at": entry["latest_filings_updated_at"],
            "latest_filings_role": entry["latest_filings_role"],
            "reconciled_at": None,
        })
    return rows


def reconcile_discovery_rows(
    existing: pd.DataFrame,
    *,
    overlay_rows: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
    reconciled_at: str,
) -> pd.DataFrame:
    """Deduplicate by accession and let the daily index reconcile metadata."""
    frame = existing.copy()
    for column in _DISCOVERY_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    ordered: list[str] = []
    by_accession: dict[str, dict[str, Any]] = {}
    for raw in frame[_DISCOVERY_COLUMNS].to_dict("records"):
        accession = str(raw.get("accession") or "")
        if not accession or accession in by_accession:
            continue
        ordered.append(accession)
        by_accession[accession] = dict(raw)
    for raw in overlay_rows:
        row = {column: raw.get(column) for column in _DISCOVERY_COLUMNS}
        accession = str(row.get("accession") or "")
        if not accession or accession in by_accession:
            continue
        ordered.append(accession)
        by_accession[accession] = row
    for raw in daily_rows:
        accession = str(raw.get("accession") or "")
        if not accession:
            raise ValueError("daily-index discovery row has no accession")
        prior = by_accession.get(accession, {})
        if accession not in by_accession:
            ordered.append(accession)
        row = {column: raw.get(column) for column in _DISCOVERY_COLUMNS}
        row["_first_seen"] = prior.get("_first_seen") or raw.get("_first_seen")
        row["discovery_channel"] = "daily_index"
        row["latest_filings_updated_at"] = prior.get(
            "latest_filings_updated_at",
        )
        row["latest_filings_role"] = prior.get("latest_filings_role")
        row["reconciled_at"] = reconciled_at
        by_accession[accession] = row
    return pd.DataFrame(
        [by_accession[accession] for accession in ordered],
        columns=_DISCOVERY_COLUMNS,
    )


def _coverage_kind(row: Mapping[str, Any]) -> str:
    value = str(row.get("coverage_kind") or "").strip()
    return value or "daily_index"


def _latest_filings_boundary(coverage: pd.DataFrame) -> datetime | None:
    if coverage.empty:
        return None
    rows = coverage.to_dict("records")
    overlay_times = [
        _aware_datetime(row.get("observed_through"), field="coverage.observed_through")
        for row in rows
        if _coverage_kind(row) == "latest_filings"
        and str(row.get("status") or "") == "complete"
        and str(row.get("observed_through") or "").strip()
    ]
    if overlay_times:
        return max(overlay_times)
    completed_dates = [
        date.fromisoformat(str(row.get("index_date")))
        for row in rows
        if _coverage_kind(row) == "daily_index"
        and str(row.get("status") or "") == "complete"
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("index_date") or ""))
    ]
    if not completed_dates:
        return None
    return daily_reconciliation_updated_boundary(max(completed_dates)).astimezone(
        timezone.utc,
    )


def _latest_entry_identity(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("accession") or ""),
        str(row.get("cik") or ""),
        str(row.get("latest_filings_role") or ""),
        str(row.get("latest_filings_updated_at") or ""),
    )


def collect_latest_filings_overlay(
    fetch_page: Callable[[int, int], str],
    *,
    discovery: pd.DataFrame,
    coverage: pd.DataFrame,
    cik_tickers: Mapping[int, str],
    observed_at: datetime,
) -> dict[str, Any]:
    """Exhaustively traverse new Atom updates within a fixed bounded budget."""
    if observed_at.tzinfo is None:
        raise ValueError("Latest Filings observed_at must be timezone-aware")
    boundary = _latest_filings_boundary(coverage)
    seen: set[tuple[str, str, str, str]] = set()
    entries: list[dict[str, Any]] = []
    oldest_seen: datetime | None = None
    first_page: dict[str, Any] | None = None
    boundary_reached = False
    pages_scanned = 0
    for page_number in range(MAX_LATEST_FILINGS_PAGES):
        start = page_number * LATEST_FILINGS_PAGE_SIZE
        parsed = parse_latest_filings_atom(
            fetch_page(start, LATEST_FILINGS_PAGE_SIZE),
        )
        pages_scanned += 1
        if first_page is None:
            first_page = parsed
        page_entries = [dict(row) for row in parsed["entries"]]
        page_times = [
            _aware_datetime(row["latest_filings_updated_at"], field="entry.updated")
            for row in page_entries
        ]
        new_rows: list[dict[str, Any]] = []
        for row, updated in zip(page_entries, page_times, strict=True):
            identity = _latest_entry_identity(row)
            if identity in seen:
                continue
            if oldest_seen is not None and updated > oldest_seen:
                raise LatestFilingsTraversalIncomplete(
                    "Latest Filings pagination order moved across an unseen entry",
                )
            seen.add(identity)
            row["_scan_order"] = len(entries) + len(new_rows)
            new_rows.append(row)
        entries.extend(new_rows)
        if page_times:
            page_oldest = min(page_times)
            oldest_seen = (
                page_oldest if oldest_seen is None else min(oldest_seen, page_oldest)
            )
            if boundary is not None and page_oldest < boundary:
                boundary_reached = True
        if not page_entries or len(page_entries) < LATEST_FILINGS_PAGE_SIZE:
            boundary_reached = True
        if boundary_reached:
            break
        time.sleep(PACE_SECONDS)
    if not boundary_reached:
        raise LatestFilingsTraversalIncomplete(
            f"Latest Filings boundary not reached in {MAX_LATEST_FILINGS_PAGES} pages",
        )
    assert first_page is not None
    time.sleep(PACE_SECONDS)
    final_page = parse_latest_filings_atom(
        fetch_page(0, LATEST_FILINGS_PAGE_SIZE),
    )
    initial_entries = first_page["entries"]
    final_entries = final_page["entries"]
    if initial_entries:
        anchor = _latest_entry_identity(initial_entries[0])
        if anchor not in {_latest_entry_identity(row) for row in final_entries}:
            raise LatestFilingsTraversalIncomplete(
                "Latest Filings leading anchor moved beyond the bounded first page",
            )
    elif final_entries:
        raise LatestFilingsTraversalIncomplete(
            "Latest Filings changed from empty during traversal",
        )
    for raw in final_entries:
        row = dict(raw)
        identity = _latest_entry_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        row["_scan_order"] = len(entries)
        entries.append(row)
    entries.sort(
        key=lambda row: (
            -_aware_datetime(
                row["latest_filings_updated_at"], field="entry.updated",
            ).timestamp(),
            int(row.get("_scan_order") or 0),
        ),
    )
    bounded_entries = [
        row for row in entries
        if boundary is None
        or _aware_datetime(row["latest_filings_updated_at"], field="entry.updated")
        >= boundary
    ]
    first_seen = _utc_iso(observed_at)
    rows = latest_filings_discovery_rows(
        bounded_entries,
        existing_discovery=discovery,
        cik_tickers=cik_tickers,
        first_seen=first_seen,
    )
    return {
        "rows": rows,
        "observed_through": final_page["observed_through"],
        "pages_scanned": pages_scanned,
        "entries_scanned": len(entries),
        "boundary": _utc_iso(boundary) if boundary is not None else None,
    }


_HEADER_FIELD_RE = {
    "accepted_at": re.compile(br"<ACCEPTANCE-DATETIME>\s*(\d{14})", re.I),
    "file_number": re.compile(br"<FILE-NUMBER>\s*([^\r\n<]+)", re.I),
}
_DOCUMENT_RE = re.compile(br"<DOCUMENT>(.*?)</DOCUMENT>", re.I | re.S)
_SEC_HEADER_FILE_NUMBER_RE = re.compile(
    br"(?:^|[\r\n])\s*SEC\s+FILE\s+NUMBER\s*:\s*([^\r\n<]+)",
    re.I,
)
_EFFECT_XML_FILE_NUMBER_RE = re.compile(
    br"<(?:[A-Za-z_][\w.-]*:)?fileNumber\b[^>]*>\s*([^<]+?)\s*</(?:[A-Za-z_][\w.-]*:)?fileNumber\s*>",
    re.I,
)
_SEC_FILE_NUMBER_TOKEN_RE = re.compile(
    r"(?<!\d)(\d{1,3}\s*-\s*\d{1,10}(?:\s*-\s*\d{1,6})?)(?!\d)"
)


@dataclass(frozen=True)
class SubmissionDocument:
    sequence: str | None
    document_type: str | None
    filename: str | None
    description: str | None
    raw: bytes
    byte_start: int | None = None
    byte_end: int | None = None


@dataclass(frozen=True)
class SubmissionBundle:
    accepted_at: str | None
    file_number: str | None
    file_number_provenance: dict[str, object]
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


def _sec_file_number_candidates(value: bytes) -> tuple[str, ...]:
    """Return every canonical SEC file number in a bounded header/tag value.

    We accept the ordinary numeric SEC registration pattern only.  A document
    can repeat the same number across legacy and modern encodings.  Preserving
    every distinct token is load-bearing: a malformed field containing two
    different valid numbers must make the whole observation ambiguous rather
    than disappearing and allowing a different source to win silently.
    """
    text = value.decode("utf-8", errors="replace")
    matches = _SEC_FILE_NUMBER_TOKEN_RE.findall(text)
    return tuple(sorted({re.sub(r"\s+", "", match) for match in matches}))


def _file_number_observation(raw: bytes) -> tuple[str | None, dict[str, object]]:
    """Extract legacy, modern-header, and EFFECT XML file-number evidence.

    The modern header search is intentionally constrained to the submission
    header, before the first ``<DOCUMENT>`` block.  XML ``fileNumber`` is an
    explicit EFFECT payload field and may live inside that document.  If those
    authoritative encodings disagree, the graph key is null and provenance
    records the ambiguity; no later phase may silently pick one.
    """
    header = raw.split(b"<DOCUMENT", 1)[0]
    candidates: list[tuple[str, str]] = []
    for source, pattern, payload in (
        ("legacy_sgml_file_number", _HEADER_FIELD_RE["file_number"], header),
        ("sec_header_file_number", _SEC_HEADER_FILE_NUMBER_RE, header),
        ("effect_xml_file_number", _EFFECT_XML_FILE_NUMBER_RE, raw),
    ):
        for match in pattern.finditer(payload):
            for value in _sec_file_number_candidates(match.group(1)):
                candidates.append((source, value))

    values = sorted({value for _, value in candidates})
    sources = sorted({source for source, _ in candidates})
    if len(values) == 1:
        state = "observed"
        value: str | None = values[0]
    elif len(values) > 1:
        state = "ambiguous"
        value = None
    else:
        state = "unavailable"
        value = None
    return value, {
        "state": state,
        "value": value,
        "candidate_values": values,
        "sources": sources,
    }


def file_number_provenance_errors(filing: dict | object) -> list[str]:
    """Return cross-field source-provenance violations for a manifest filing.

    Older immutable rows predate this optional field and remain valid.  Every
    new collector-produced row carries it and must satisfy the observed/null
    law below before it can enter the append-only source ledger.
    """
    if not isinstance(filing, dict):
        return ["filing must be an object"]
    provenance = filing.get("file_number_provenance")
    if provenance is None:
        return []
    if not isinstance(provenance, dict):
        return ["filing.file_number_provenance must be an object"]
    state = provenance.get("state")
    filing_value = filing.get("file_number")
    value = provenance.get("value")
    candidates = provenance.get("candidate_values")
    sources = provenance.get("sources")

    def _array_values(value: object) -> list[object] | None:
        """Normalize a JSON array after a Parquet nested-value round trip."""
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            converted = tolist()
            if isinstance(converted, list):
                return converted
        return None

    candidates = _array_values(candidates)
    sources = _array_values(sources)
    if candidates is None or sources is None:
        return ["filing.file_number_provenance candidates/sources must be arrays"]
    if candidates != sorted(set(candidates)) or sources != sorted(set(sources)):
        return ["filing.file_number_provenance arrays must be sorted unique"]
    if state == "observed":
        if not isinstance(value, str) or value not in candidates or filing_value != value:
            return ["observed file-number provenance must bind filing.file_number"]
        if len(candidates) != 1 or not sources:
            return ["observed file-number provenance requires one value and a source"]
    elif state in {"unavailable", "ambiguous"}:
        if value is not None or filing_value is not None:
            return ["non-observed file-number provenance requires null filing.file_number"]
        if state == "unavailable" and (candidates or sources):
            return ["unavailable file-number provenance cannot contain candidates"]
        if state == "ambiguous" and len(candidates) < 2:
            return ["ambiguous file-number provenance requires multiple candidates"]
    else:
        return ["file-number provenance has an invalid state"]
    return []


def parse_submission(raw: bytes) -> SubmissionBundle:
    """Parse SEC submission header fields and raw ``<DOCUMENT>`` blocks.

    key_format 1: each DOCUMENT is stamped with ``(byte_start, byte_end)`` from
    ``document_inner_spans`` so child evidence identities are bound to exact bytes.
    Spans are attached only when count and content-equality checks pass; individual
    failures leave the document's span fields as ``None``. The writer must then
    defer the bundle — never mint ``legacy:{source_id}`` as a new occurrence key.
    """
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
    file_number, file_number_provenance = _file_number_observation(raw)
    blocks = _DOCUMENT_RE.findall(raw)
    # Attempt to bind exact inner spans for key_format 1 child occurrences.
    spans: tuple[tuple[int, int], ...] = ()
    try:
        candidate_spans = document_inner_spans(raw)
        if len(candidate_spans) == len(blocks) and all(
            raw[s:e] == block
            for (s, e), block in zip(candidate_spans, blocks)
        ):
            spans = candidate_spans
    except EvidenceIdentityError:
        pass
    documents = tuple(
        SubmissionDocument(
            sequence=_sgml_value(block, b"SEQUENCE"),
            document_type=_sgml_value(block, b"TYPE"),
            filename=_sgml_value(block, b"FILENAME"),
            description=_sgml_value(block, b"DESCRIPTION"),
            raw=block,
            byte_start=spans[i][0] if spans else None,
            byte_end=spans[i][1] if spans else None,
        )
        for i, block in enumerate(blocks)
    )
    return SubmissionBundle(
        accepted_at=accepted_at,
        file_number=file_number,
        file_number_provenance=file_number_provenance,
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
        elif re.match(r"^EX-1(\.|$)", doc_type):
            role = "underwriting_exhibit"
        elif re.match(r"^EX-FILING\s+FEES?(\.|$)", doc_type):
            role = "filing_fee_exhibit"
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


RECONCILIATION_CURRENT_REPORT_FORMS = frozenset({"8-K", "8-K/A", "6-K", "6-K/A"})
RECONCILIATION_PERIODIC_FORMS = frozenset({
    "10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A",
})
RECONCILIATION_PROXY_FORMS = frozenset({"PRE 14A", "DEF 14A", "PRE 14C", "DEF 14C"})


def retrieval_lane(
    form: object,
    *,
    collection_scope: object = None,
    issuer_is_scoped: bool = False,
) -> str | None:
    """Return one bounded retrieval lane, denying broad forms by default."""
    normalized = str(form or "").upper()
    if normalized in REGISTRATION_FORMS:
        return "registration"
    if normalized in STATE_FORMS:
        return "state"
    if normalized in PROSPECTUS_FORMS:
        return "prospectus"
    if normalized in REG_A_FORMS:
        return "reg_a"
    if (
        collection_scope != DISCOVERY_SCOPE_RECONCILIATION
        or not issuer_is_scoped
    ):
        return None
    if normalized in RECONCILIATION_CURRENT_REPORT_FORMS:
        return "issuer_current_report"
    if normalized in RECONCILIATION_PERIODIC_FORMS:
        return "issuer_periodic"
    if normalized in RECONCILIATION_PROXY_FORMS:
        return "issuer_proxy"
    return None


def _lane_slot_order(*, slots: int, now: datetime) -> list[str]:
    """Build the deterministic, UTC-date-rotated weighted quota schedule."""
    if slots <= 0:
        return []
    cycle = [
        lane
        for lane in RETRIEVAL_LANE_ORDER
        for _ in range(RETRIEVAL_LANE_WEIGHTS[lane])
    ]
    if not cycle:
        return []
    stamp = pd.Timestamp(now)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    offset = stamp.date().toordinal() % len(cycle)
    return [cycle[(offset + index) % len(cycle)] for index in range(slots)]


def retrieval_lane_quotas(*, max_filings: int, now: datetime) -> dict[str, int]:
    """Expose date-rotated quota slots for audit and deterministic tests."""
    quotas = {lane: 0 for lane in RETRIEVAL_LANE_ORDER}
    for lane in _lane_slot_order(slots=max_filings, now=now):
        quotas[lane] += 1
    return quotas


def _fair_lane_rows(
    frame: pd.DataFrame,
    *,
    slots: int,
    now: datetime,
) -> list[dict]:
    """Take bounded, weighted-fair rows without wasting turns on empty lanes."""
    if frame.empty or slots <= 0:
        return []
    by_lane = {
        lane: frame.loc[frame["_retrieval_lane"].eq(lane)].to_dict(orient="records")
        for lane in RETRIEVAL_LANE_ORDER
    }
    # Use a full rotation to locate the next non-empty lane even if this run has
    # fewer slots than the number of lane weights.  ``slots`` still limits how
    # many records are selected; it never truncates the search horizon.
    schedule = _lane_slot_order(
        slots=sum(RETRIEVAL_LANE_WEIGHTS.values()), now=now
    )
    selected: list[dict] = []
    cursor = 0
    while len(selected) < slots and any(by_lane.values()):
        selected_lane = None
        for offset in range(len(schedule)):
            lane = schedule[(cursor + offset) % len(schedule)]
            if by_lane[lane]:
                selected_lane = lane
                cursor = (cursor + offset + 1) % len(schedule)
                break
        if selected_lane is None:
            break
        selected.append(by_lane[selected_lane].pop(0))
    return selected


def _max_retrieval_attempts() -> int:
    """Resolve the parking bound, honouring the operator override at the point of use.

    Read per call rather than frozen at import, so ``CS_MAX_RETRIEVAL_ATTEMPTS``
    exported for one manual run — or set in the workflow after a systematic defect
    is fixed — takes effect without an edit and a deploy.  This is the ONLY lever
    that unparks a filing; there is no ``--rebuild`` flag on this collector.

    An unparsable or non-positive value falls back to the default instead of
    raising: a typo in a workflow variable must not abort the night, and it must
    not silently uncap the backlog the bound exists to close either.
    """
    raw = (os.environ.get(MAX_RETRIEVAL_ATTEMPTS_ENV) or "").strip()
    if not raw:
        return MAX_RETRIEVAL_ATTEMPTS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        log.warning(
            "sec_capital_structure: %s=%r is not a positive integer — using the "
            "default bound %d", MAX_RETRIEVAL_ATTEMPTS_ENV, raw, MAX_RETRIEVAL_ATTEMPTS,
        )
        return MAX_RETRIEVAL_ATTEMPTS
    return value


def parked_accessions(
    attempts: pd.DataFrame, *, max_attempts: int | None = None
) -> set[str]:
    """Accessions with ``max_attempts`` attempts that never closed the queue item.

    A ``stored`` attempt is terminal for the queue — the bytes land in
    ``have_complete`` and the accession never comes back — so every OTHER recorded
    attempt for a still-queued accession is by construction a *consecutive* unclosed
    attempt.  A plain count is therefore the consecutive count, with no ordering to
    get wrong.  ``stored_parser_deferred`` counts: it retained the bytes but cannot
    be ``eligible``/``clean``, so it never reaches ``have_complete`` and the filing
    comes back tomorrow night unless the bound holds it.

    This bounds the BACKLOG, not the evidence: parking hides a filing from the
    retrieval queue and deletes nothing.  Raising ``CS_MAX_RETRIEVAL_ATTEMPTS``
    brings it straight back.
    """
    if max_attempts is None:
        max_attempts = _max_retrieval_attempts()
    if attempts.empty or "accession" not in attempts.columns or max_attempts <= 0:
        return set()
    unclosed = attempts.loc[attempts["state"].isin(_UNCLOSED_ATTEMPT_STATES)]
    if unclosed.empty:
        return set()
    counts = unclosed["accession"].astype(str).value_counts()
    return set(counts.loc[counts >= int(max_attempts)].index)


def _retrieval_queue_candidates(
    discovery: pd.DataFrame,
    *,
    have_complete: set[str],
    parked: set[str] | frozenset[str] = frozenset(),
) -> pd.DataFrame:
    """Build fail-closed eligible candidates and their auditable lane labels."""
    if not {"form", "accession"}.issubset(discovery.columns):
        raise ValueError("discovery ledger is missing form/accession columns")
    queue = discovery.copy()
    if "collection_scope" not in queue:
        queue["collection_scope"] = None
    if "cik" not in queue:
        queue["cik"] = None
    scope_ciks = _issuer_scope_ciks(discovery)
    queue["_issuer_is_scoped"] = queue["cik"].map(
        lambda value: _normalized_cik(value) in scope_ciks
    )
    queue["_retrieval_lane"] = [
        retrieval_lane(
            form,
            collection_scope=scope,
            issuer_is_scoped=bool(issuer_is_scoped),
        )
        for form, scope, issuer_is_scoped in zip(
            queue["form"], queue["collection_scope"], queue["_issuer_is_scoped"]
        )
    ]
    return queue.loc[
        queue["_retrieval_lane"].notna()
        & ~queue["accession"].astype(str).isin(have_complete)
        & ~queue["accession"].astype(str).isin(parked)
    ].copy()


def _completed_sec_sessions(coverage: pd.DataFrame, *, limit: int) -> set[str]:
    """Return the latest policy-current completed SEC index sessions.

    Calendar subtraction is intentionally not used: the daily-index ledger is
    the evidence of which SEC sessions were actually observed successfully.
    """
    if coverage.empty or limit <= 0 or not {
        "index_date", "status", "policy_version"
    }.issubset(coverage.columns):
        return set()
    rows = coverage.loc[
        coverage["status"].astype(str).eq("complete")
        & coverage["policy_version"].astype(str).eq(FORM_POLICY["policy_version"]),
        "index_date",
    ]
    dates = sorted({str(value)[:10] for value in rows if str(value)}, reverse=True)
    return set(dates[:limit])


def _latest_open_attempt_states(attempts: pd.DataFrame) -> dict[str, str]:
    """Return each accession's latest recorded queue-open state, if any."""
    if attempts.empty or not {"accession", "state"}.issubset(attempts.columns):
        return {}
    ordered = attempts.copy()
    if "attempted_at" not in ordered:
        ordered["attempted_at"] = ""
    ordered = ordered.sort_values(
        ["accession", "attempted_at"], kind="stable", na_position="last"
    )
    latest = ordered.drop_duplicates("accession", keep="last")
    return {
        str(row["accession"]): str(row["state"])
        for row in latest.to_dict(orient="records")
        if str(row.get("state") or "") in _UNCLOSED_ATTEMPT_STATES
    }


def _classify_work_classes(
    candidates: pd.DataFrame,
    *,
    coverage: pd.DataFrame | None,
    attempts: pd.DataFrame | None,
    current_run_arrivals: set[str] | frozenset[str],
) -> pd.DataFrame:
    """Attach deterministic operational classes without changing discovery rows."""
    queue = candidates.copy()
    coverage = coverage if coverage is not None else pd.DataFrame()
    attempts = attempts if attempts is not None else pd.DataFrame()
    live_sessions = _completed_sec_sessions(coverage, limit=LIVE_TAIL_SESSION_COUNT)
    recovery_sessions = _completed_sec_sessions(coverage, limit=RECOVERY_SESSION_COUNT)
    latest_open = _latest_open_attempt_states(attempts)
    filing_dates = queue.get("filing_date", pd.Series(index=queue.index, dtype=object))
    filing_dates = filing_dates.astype(str).str[:10]
    queue["_live_session"] = filing_dates.isin(live_sessions)
    queue["_current_run_arrival"] = (
        queue["accession"].astype(str).isin(current_run_arrivals)
        & queue["_live_session"]
    )

    def classify(accession: object, filing_date: object) -> str:
        filing_session = str(filing_date)[:10]
        # Recovery precedes live-tail by law: a current retry consumes the
        # bounded recovery reserve while live-session backlog stays separately
        # observable through _live_session.
        if (
            latest_open.get(str(accession)) in _UNCLOSED_ATTEMPT_STATES
            and filing_session in recovery_sessions
        ):
            return "RECOVERY"
        if filing_session in live_sessions:
            return "LIVE_TAIL"
        return "HISTORICAL_BACKFILL"

    queue["_work_class"] = [
        classify(accession, filing_date)
        for accession, filing_date in zip(queue["accession"], filing_dates)
    ]
    return queue


def _class_reservations(max_filings: int) -> dict[str, int]:
    """Fit the fixed W2 reservations under the existing global ceiling."""
    remaining = max(0, min(int(max_filings), MAX_FILINGS_PER_RUN))
    reservations: dict[str, int] = {}
    for work_class in WORK_CLASS_ORDER:
        slots = min(WORK_CLASS_RESERVATIONS[work_class], remaining)
        reservations[work_class] = slots
        remaining -= slots
    return reservations


def _class_allocation(
    queue: pd.DataFrame, *, max_filings: int
) -> tuple[dict[str, int], dict[str, int], dict[str, int], list[dict[str, object]]]:
    """Allocate reserves, then spill unused donor capacity deterministically."""
    reserved = _class_reservations(max_filings)
    pending = {
        work_class: int(queue["_work_class"].eq(work_class).sum())
        for work_class in WORK_CLASS_ORDER
    }
    quotas = {work_class: min(reserved[work_class], pending[work_class]) for work_class in WORK_CLASS_ORDER}
    spill_in = {work_class: 0 for work_class in WORK_CLASS_ORDER}
    spill_out = {work_class: 0 for work_class in WORK_CLASS_ORDER}
    transfers: list[dict[str, object]] = []
    for donor in WORK_CLASS_ORDER:
        unused = reserved[donor] - quotas[donor]
        if unused <= 0:
            continue
        for recipient in WORK_CLASS_ORDER:
            if recipient == donor or unused <= 0:
                continue
            capacity = pending[recipient] - quotas[recipient]
            moved = min(unused, max(0, capacity))
            if moved <= 0:
                continue
            quotas[recipient] += moved
            spill_in[recipient] += moved
            spill_out[donor] += moved
            transfers.append({"donor": donor, "recipient": recipient, "slots": moved})
            unused -= moved
    return quotas, spill_in, spill_out, transfers


def _lane_distribution(frame: pd.DataFrame, selected: Sequence[Mapping[str, object]]) -> list[dict]:
    selected_counts = pd.Series(
        [str(row.get("_retrieval_lane")) for row in selected], dtype="object"
    ).value_counts()
    return [
        {
            "lane": lane,
            "pending_count": int(frame["_retrieval_lane"].eq(lane).sum()),
            "selected_count": int(selected_counts.get(lane, 0)),
        }
        for lane in RETRIEVAL_LANE_ORDER
    ]


def _queue_receipt(
    candidates: pd.DataFrame,
    selected: list[dict],
    *,
    max_filings: int,
    now: datetime,
    in_policy_discovery: pd.DataFrame | None = None,
    class_reservations: Mapping[str, int] | None = None,
    class_quotas: Mapping[str, int] | None = None,
    spill_in: Mapping[str, int] | None = None,
    spill_out: Mapping[str, int] | None = None,
    spill_transfers: Sequence[Mapping[str, object]] = (),
) -> dict:
    """Publish operational queue fairness without converting it into issuer truth."""
    stamp = pd.Timestamp(now)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    lanes: list[dict] = []
    for lane in RETRIEVAL_LANE_ORDER:
        lane_rows = candidates.loc[candidates["_retrieval_lane"].eq(lane)]
        pending = len(lane_rows)
        selected_count = sum(
            1 for row in selected if row.get("_retrieval_lane") == lane
        )
        first_seen = pd.to_datetime(lane_rows.get("_first_seen"), errors="coerce", utc=True)
        observed = first_seen.dropna()
        oldest = observed.min() if not observed.empty else None
        age_days = (
            max(0, int((stamp - oldest).total_seconds() // 86400))
            if oldest is not None else None
        )
        lanes.append({
            "lane": lane,
            "pending_count": pending,
            "selected_count": selected_count,
            "deferred_count": pending - selected_count,
            "oldest_pending_first_seen": oldest.isoformat().replace("+00:00", "Z") if oldest is not None else None,
            "oldest_pending_age_days": age_days,
            "unknown_first_seen_count": int(first_seen.isna().sum()),
        })
    class_reservations = class_reservations or _class_reservations(max_filings)
    class_quotas = class_quotas or {work_class: 0 for work_class in WORK_CLASS_ORDER}
    spill_in = spill_in or {work_class: 0 for work_class in WORK_CLASS_ORDER}
    spill_out = spill_out or {work_class: 0 for work_class in WORK_CLASS_ORDER}
    classes: list[dict] = []
    for work_class in WORK_CLASS_ORDER:
        rows = candidates.loc[candidates.get("_work_class", pd.Series(index=candidates.index, dtype=object)).eq(work_class)]
        selected_rows = [row for row in selected if row.get("_work_class") == work_class]
        filing_dates = pd.to_datetime(rows.get("filing_date"), errors="coerce", utc=True)
        valid_dates = filing_dates.dropna()
        live_pending = int(rows.get("_live_session", pd.Series(False, index=rows.index)).sum())
        live_selected = sum(1 for row in selected_rows if row.get("_live_session"))
        classes.append({
            "work_class": work_class,
            "reserved_slots": int(class_reservations[work_class]),
            "quota_slots": int(class_quotas[work_class]),
            "reserved_selected_count": min(len(selected_rows), int(class_reservations[work_class])),
            "spill_in_slots": int(spill_in[work_class]),
            "spill_out_slots": int(spill_out[work_class]),
            "unused_reserved_slots": int(class_reservations[work_class]) - min(
                int(class_reservations[work_class]), len(selected_rows)
            ),
            "pending_count": len(rows),
            "selected_count": len(selected_rows),
            "deferred_count": len(rows) - len(selected_rows),
            "oldest_filing_date": valid_dates.min().date().isoformat() if not valid_dates.empty else None,
            "newest_filing_date": valid_dates.max().date().isoformat() if not valid_dates.empty else None,
            "current_run_arrivals": int(rows.get("_current_run_arrival", pd.Series(False, index=rows.index)).sum()),
            "live_session_pending_count": live_pending,
            "live_session_unserved_count": live_pending - live_selected,
            "lanes": _lane_distribution(rows, selected_rows),
        })
    live_pending_total = int(candidates.get("_live_session", pd.Series(False, index=candidates.index)).sum())
    live_selected_total = sum(1 for row in selected if row.get("_live_session"))
    live_arrivals_total = int(
        candidates.get(
            "_current_run_arrival", pd.Series(False, index=candidates.index)
        ).sum()
    )
    live_effective_capacity = int(class_quotas.get("LIVE_TAIL", 0))
    admitted = (
        in_policy_discovery
        if isinstance(in_policy_discovery, pd.DataFrame)
        else pd.DataFrame()
    )
    admitted_dates = pd.to_datetime(
        admitted.get(
            "filing_date", pd.Series(index=admitted.index, dtype="object")
        ),
        errors="coerce", utc=True,
    )
    latest_admitted_date = (
        admitted_dates.dropna().max() if admitted_dates.notna().any() else None
    )
    latest_admitted_mask = (
        admitted_dates.eq(latest_admitted_date)
        if latest_admitted_date is not None
        else pd.Series(False, index=admitted.index)
    )
    latest_admitted_rows = admitted.loc[latest_admitted_mask]
    admitted_observed = pd.to_datetime(
        latest_admitted_rows.get(
            "_first_seen",
            pd.Series(index=latest_admitted_rows.index, dtype="object"),
        ),
        errors="coerce", utc=True,
    ).dropna()
    return {
        "schema": "capital_structure.retrieval_queue_receipt.v1",
        "as_of": stamp.isoformat().replace("+00:00", "Z"),
        "policy_version": FORM_POLICY["policy_version"],
        "discovery_clock_policy_version": DISCOVERY_CLOCK_POLICY_VERSION,
        "max_filings": int(max_filings),
        "selected_count": len(selected),
        "deferred_count": len(candidates) - len(selected),
        "lane_quota_slots": retrieval_lane_quotas(max_filings=max_filings, now=now),
        "lanes": lanes,
        "class_quota_slots": {work_class: int(class_quotas[work_class]) for work_class in WORK_CLASS_ORDER},
        "spill_transfers": [dict(row) for row in spill_transfers],
        "work_classes": classes,
        "live_tail_arrivals_current_run": live_arrivals_total,
        "live_tail_effective_capacity": live_effective_capacity,
        "live_tail_arrival_overflow": max(
            0, live_arrivals_total - live_effective_capacity
        ),
        "live_tail_pending_before_selection": live_pending_total,
        "live_tail_selected": live_selected_total,
        "live_tail_unserved_after_selection": (
            live_pending_total - live_selected_total
        ),
        # This policy-filtered discovery watermark is computed before complete
        # and parked rows are removed. Health consumes this exact collector-law
        # fact instead of duplicating the evolving form/scope policy.
        "latest_discovered_in_policy_filing_date": (
            latest_admitted_date.date().isoformat()
            if latest_admitted_date is not None else None
        ),
        "latest_discovered_in_policy_observed_at": (
            admitted_observed.max().isoformat().replace("+00:00", "Z")
            if not admitted_observed.empty else None
        ),
        "live_session_pending_count": live_pending_total,
        "live_session_unserved_count": live_pending_total - live_selected_total,
        "authority": {
            "is_context_only": True,
            "rank_authority": False,
            "sizing_authority": False,
            "entry_authority": False,
            "prophet_authority": False,
        },
    }


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
    if not coverage.empty and "coverage_kind" in coverage.columns:
        kinds = coverage["coverage_kind"].fillna("").astype(str)
        coverage = coverage.loc[kinds.isin({"", "daily_index"})].copy()
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
    parked: set[str] | frozenset[str] = frozenset(),
    coverage: pd.DataFrame | None = None,
    attempts: pd.DataFrame | None = None,
    current_run_arrivals: set[str] | frozenset[str] = frozenset(),
) -> pd.DataFrame:
    """Select the bounded work-class queue with lane fairness inside each class.

    Every selected turn is allocated by the existing fair lane rotation.
    LIVE_TAIL serves newest filing sessions first within a lane and uses
    current-run arrival as the same-session tie-break; RECOVERY and
    HISTORICAL_BACKFILL retain the prior aged-first debt order. Therefore
    neither an old class nor an old saturated lane can continually displace the
    newest admitted filing horizon.
    """
    columns = list(discovery.columns)
    in_policy_discovery = _retrieval_queue_candidates(
        discovery, have_complete=set(), parked=frozenset()
    )
    queue = _retrieval_queue_candidates(
        discovery, have_complete=have_complete, parked=parked
    )
    queue = _classify_work_classes(
        queue,
        coverage=coverage,
        attempts=attempts,
        current_run_arrivals=current_run_arrivals,
    )
    selection_cap = max(0, min(int(max_filings), MAX_FILINGS_PER_RUN))
    if queue.empty or max_filings <= 0:
        empty = queue.head(0)[columns]
        empty.attrs["retrieval_queue_receipt"] = _queue_receipt(
            queue, [], max_filings=selection_cap, now=now,
            in_policy_discovery=in_policy_discovery,
        )
        empty.attrs["retrieval_lanes_by_accession"] = {}
        empty.attrs["retrieval_work_classes_by_accession"] = {}
        return empty

    now_stamp = pd.Timestamp(now)
    now_stamp = (
        now_stamp.tz_localize("UTC")
        if now_stamp.tzinfo is None
        else now_stamp.tz_convert("UTC")
    )
    first_seen = pd.to_datetime(queue["_first_seen"], errors="coerce", utc=True)
    aging_cutoff = now_stamp - pd.Timedelta(days=RETRIEVAL_QUEUE_AGING_DAYS)
    queue["_aged"] = first_seen.isna() | first_seen.le(aging_cutoff)
    queue["_first_seen_sort"] = first_seen.fillna(
        pd.Timestamp("1970-01-01", tz="UTC")
    )
    queue["_filing_date"] = pd.to_datetime(
        queue["filing_date"], errors="coerce", utc=True
    )
    queue = queue.sort_values(
        ["_retrieval_lane", "_aged", "_first_seen_sort", "_filing_date", "accession"],
        ascending=[True, False, True, True, True],
        na_position="last",
        kind="stable",
    )
    # The W2 reserve/allocation happens before lane fairness.  Each class invokes
    # the existing lane selector exactly once, preserving date-rotated lane
    # rotation without allowing backlog to consume LIVE_TAIL capacity.
    class_quotas, spill_in, spill_out, transfers = _class_allocation(
        queue, max_filings=selection_cap
    )
    reservations = _class_reservations(selection_cap)
    selected: list[dict] = []
    for work_class in WORK_CLASS_ORDER:
        class_rows = queue.loc[queue["_work_class"].eq(work_class)]
        if work_class == "LIVE_TAIL":
            # The class reserve prevents historical debt from consuming live
            # slots; newest-first ordering inside each existing lane prevents
            # sustained >cap live arrivals from moving that starvation boundary
            # forward one session at a time. Lane rotation itself is unchanged.
            class_rows = class_rows.sort_values(
                [
                    "_retrieval_lane", "_filing_date", "_current_run_arrival",
                    "_first_seen_sort", "accession",
                ],
                ascending=[True, False, False, False, True],
                na_position="last",
                kind="stable",
            )
        selected.extend(_fair_lane_rows(
            class_rows, slots=class_quotas[work_class], now=now
        ))
    if len(selected) > selection_cap:
        raise ValueError("work-class selection exceeded global filing cap")
    if not selected:
        result = queue.head(0)[columns]
    else:
        result = pd.DataFrame(selected)[columns].reset_index(drop=True)
    result.attrs["retrieval_queue_receipt"] = _queue_receipt(
        queue,
        selected,
        max_filings=selection_cap,
        now=now,
        in_policy_discovery=in_policy_discovery,
        class_reservations=reservations,
        class_quotas=class_quotas,
        spill_in=spill_in,
        spill_out=spill_out,
        spill_transfers=transfers,
    )
    result.attrs["retrieval_lanes_by_accession"] = {
        str(row["accession"]): str(row["_retrieval_lane"])
        for row in selected
    }
    result.attrs["retrieval_work_classes_by_accession"] = {
        str(row["accession"]): str(row["_work_class"])
        for row in selected
    }
    return result


def _manifest_scalar(
    value: Any, *, field: str | None = None, sanitized: list[str] | None = None,
) -> Any:
    """Normalize a pandas missing-value sentinel to the JSON ``null`` the contract declares.

    Discovery rows reach ``_manifest_record`` from a pandas frame, and pandas
    represents an absent scalar as ``float('nan')`` — a *sentinel*, not a number.
    Every discovery-sourced field in the manifest is declared ``["string", "null"]``
    by ``contracts/capital_structure_source_manifest.schema.json`` (``collection_scope``
    even lists ``null`` in its enum), so ``None`` is the contract-correct value and
    NaN is not a legal value at all.

    Left unconverted the sentinel reaches ``canonical_manifest_bytes`` →
    ``_native`` and raises ``TypeError: non-finite numbers are not canonical
    manifest values`` (``engine/capital_structure/source_identity.py:112``), which
    the retrieval loop's broad ``except Exception`` records as a per-filing
    deferral — so the filing retries and fails identically every night.  That is
    the 2026-08-06 nightly (130 deferrals in one run).

    Never coerce to ``0.0`` or ``""``: nulling records "we do not know", while a
    zero would publish a fabricated observation into immutable evidence.  Nothing
    this touches is a measurement, so there is no number to lose.

    ``field``/``sanitized`` are the disclosure channel.  The 2026-08-06 storm said
    only "non-finite numbers are not canonical manifest values" — 130 times, naming
    no field — and an undiagnosable repeat is why this ran six nights.  Only a REAL
    conversion is appended: a field that was already ``None`` is not reported, so
    "sanitized" never conflates with "legitimately absent" (``filing.file_number``
    is routinely null by contract).
    """
    if value is None:
        return value
    converted = False
    if isinstance(value, float):
        converted = not math.isfinite(value)
    elif not isinstance(value, (str, bytes, bool, int, list, tuple, dict)):
        # ``pd.NA``/``NaT`` are not floats.  ``pd.isna`` is array-aware, so it is
        # reached only for scalars — a list (``issuer.aliases``) would raise here.
        try:
            converted = bool(pd.isna(value))
        except (TypeError, ValueError):
            converted = False
    if not converted:
        return value
    if sanitized is not None and field:
        sanitized.append(field)
    return None


def _read_table(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"capital-structure store unreadable: {path}: {exc}") from exc
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[columns]


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _atomic_write_json(record: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _validate_retrieval_queue_receipt(record: dict) -> None:
    """Fail closed before operational fairness evidence is published."""
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = Path(__file__).resolve().parents[1] / "contracts" / (
        "capital_structure_retrieval_queue_receipt.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
        key=lambda error: list(error.path),
    )
    if errors:
        raise ValueError(
            "retrieval queue receipt contract violation: "
            + "; ".join(error.message for error in errors[:5])
        )
    lanes = record.get("lanes") or []
    lane_names = [row.get("lane") for row in lanes if isinstance(row, dict)]
    if lane_names != list(RETRIEVAL_LANE_ORDER):
        raise ValueError("retrieval queue receipt lanes must be complete and canonical")
    if sum(int(value) for value in (record.get("lane_quota_slots") or {}).values()) != int(
        record.get("max_filings") or 0
    ):
        raise ValueError("retrieval queue receipt quota slots must sum to max_filings")
    selected_total = 0
    deferred_total = 0
    for row in lanes:
        pending = int(row["pending_count"])
        selected = int(row["selected_count"])
        deferred = int(row["deferred_count"])
        if selected > pending or deferred != pending - selected:
            raise ValueError("retrieval queue receipt lane counts are inconsistent")
        selected_total += selected
        deferred_total += deferred
    if selected_total != int(record["selected_count"]) or deferred_total != int(record["deferred_count"]):
        raise ValueError("retrieval queue receipt totals are inconsistent")
    work_classes = record.get("work_classes")
    if work_classes is None:
        # Historical v1 receipts remain readable; every new collector write emits
        # the W2 fields below.
        return
    class_names = [row.get("work_class") for row in work_classes]
    if class_names != list(WORK_CLASS_ORDER):
        raise ValueError("retrieval queue receipt work classes must be complete and canonical")
    class_selected = 0
    class_deferred = 0
    for row in work_classes:
        pending = int(row["pending_count"])
        selected = int(row["selected_count"])
        deferred = int(row["deferred_count"])
        if selected > pending or deferred != pending - selected:
            raise ValueError("retrieval queue receipt work-class counts are inconsistent")
        if int(row["quota_slots"]) < selected:
            raise ValueError("retrieval queue receipt work-class selection exceeds quota")
        class_selected += selected
        class_deferred += deferred
    if class_selected != int(record["selected_count"]) or class_deferred != int(record["deferred_count"]):
        raise ValueError("retrieval queue receipt class totals are inconsistent")
    class_slots = record.get("class_quota_slots") or {}
    if [key for key in class_slots] != list(WORK_CLASS_ORDER):
        raise ValueError("retrieval queue receipt class quota slots must be canonical")
    if sum(int(value) for value in class_slots.values()) != int(record["selected_count"]):
        raise ValueError("retrieval queue receipt class quota slots must sum to selection")
    live_metrics = (
        "live_tail_arrivals_current_run",
        "live_tail_effective_capacity",
        "live_tail_arrival_overflow",
        "live_tail_pending_before_selection",
        "live_tail_selected",
        "live_tail_unserved_after_selection",
        "latest_discovered_in_policy_filing_date",
        "latest_discovered_in_policy_observed_at",
    )
    if any(name not in record for name in live_metrics):
        raise ValueError("retrieval queue receipt must emit the W2 live-tail metrics")
    if int(record["live_tail_arrival_overflow"]) != max(
        0,
        int(record["live_tail_arrivals_current_run"])
        - int(record["live_tail_effective_capacity"]),
    ):
        raise ValueError("retrieval queue receipt live-tail arrival overflow is inconsistent")
    if int(record["live_tail_unserved_after_selection"]) != (
        int(record["live_tail_pending_before_selection"])
        - int(record["live_tail_selected"])
    ):
        raise ValueError("retrieval queue receipt live-tail unserved count is inconsistent")


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
    semantic_errors = file_number_provenance_errors(record.get("filing"))
    if errors or semantic_errors:
        joined = "; ".join(
            [error.message for error in errors[:5]] + semantic_errors[:5]
        )
        raise ValueError(f"source manifest contract violation: {joined}")
    validate_manifest_identity(record)


def _append_manifests_strict(
    prior: Sequence[Mapping[str, Any]], fresh: list[dict]
) -> list[dict]:
    """Append immutable manifests without hiding identity collisions.

    Records stay as records end to end.  Routing them through a frame would
    reintroduce the column padding that made a manifest's stored body depend on
    the other rows it was written beside.
    """
    return merge_manifest_ledgers(list(prior), fresh)


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


def _eligible_complete_accessions(manifests: Sequence[Mapping[str, Any]]) -> set[str]:
    """Return filings with readable roots and hardened file-number provenance.

    A pre-Wave-2C complete submission remains valid immutable evidence, but it
    cannot close the retrieval queue: the old first-match SGML extractor did not
    record conflicts or modern/EFFECT encodings. Reusing the ordinary bounded
    queue gives those accessions one versioned provenance backfill. Once a new
    complete manifest carries a semantically valid provenance observation --
    including an explicit ``unavailable`` state -- the accession closes normally
    and cannot enter an infinite compatibility-refetch loop.
    """
    complete: set[str] = set()
    for record in manifests:
        filing = record.get("filing")
        document = record.get("document")
        parser = record.get("parser")
        if not all(isinstance(value, dict) for value in (filing, document, parser)):
            continue
        if (
            document.get("document_role") == "complete_submission"
            and parser.get("eligibility") == "eligible"
            and parser.get("corruption_state") == "clean"
            and isinstance(filing.get("file_number_provenance"), dict)
            and not file_number_provenance_errors(filing)
        ):
            complete.add(str(filing.get("accession")))
    return complete


def _next_bundle_document_version(
    manifests: Sequence[Mapping[str, Any]], accession: str
) -> int:
    """Advance one accession-wide version for a closed manifest bundle."""
    latest = 0
    for record in manifests:
        filing = record.get("filing")
        document = record.get("document")
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
    latest_filings_enabled = True

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
        return build_source_store(require_writable=True)

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

    def _fetch_latest_filings_page(self, start: int, count: int, ua: str) -> str:
        response = self.http_get(
            _LATEST_FILINGS.format(start=int(start), count=int(count)),
            retries=1,
            timeout=30,
            headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
        )
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
        sanitized: list[str] | None = None,
        parent_content_sha256: str | None = None,
        byte_start: int | None = None,
        byte_end: int | None = None,
        existing_manifests: "list[dict] | None" = None,
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
        # Named in the disclosure like every other sanitized field.  A NaN company
        # name silently DROPS the issuer alias below, and an undisclosed drop is
        # the shape that made the 08-06 storm undiagnosable in the first place.
        company_name = _manifest_scalar(
            discovery.get("company_name"), field="issuer.aliases", sanitized=sanitized,
        )

        def _scalar(value: Any, field: str) -> Any:
            return _manifest_scalar(value, field=field, sanitized=sanitized)

        record = {
            "schema": "capital_structure.source_manifest/v1",
            "source_system": "sec_edgar",
            "source_id": source_id,
            "issuer": {
                "issuer_id": f"sec:cik:{str(discovery['cik']).zfill(10)}",
                "cik": str(discovery["cik"]).lstrip("0") or "0",
                "ticker": ticker if isinstance(ticker, str) and ticker else None,
                # ``company_name`` is nulled BEFORE the truthiness test on purpose:
                # ``float('nan')`` is truthy, so the raw value used to publish the
                # alias ``["nan"]`` for every row whose name was absent.
                "aliases": [str(company_name)] if company_name else [],
            },
            "filing": {
                "accession": _scalar(discovery["accession"], "filing.accession"),
                "form": _scalar(discovery["form"], "filing.form"),
                "filing_date": _scalar(discovery["filing_date"], "filing.filing_date"),
                "accepted_at": _scalar(bundle.accepted_at, "filing.accepted_at"),
                "file_number": _scalar(bundle.file_number, "filing.file_number"),
                "file_number_provenance": bundle.file_number_provenance,
                "collection_scope": _scalar(
                    discovery.get("collection_scope"), "filing.collection_scope"
                ),
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
        # --- Evidence identity (key_format 1) stamped BEFORE manifest_id_for ---
        # occurrence: "submission" for complete submissions; child_occurrence
        # for documents with bound byte spans. New writes never fall back to
        # "legacy:{source_id}" — that projection is read-side only for v1 rows.
        accession_str = str(discovery.get("accession") or "")
        if document_role == "complete_submission":
            evidence_occurrence: Any = "submission"
        else:
            evidence_occurrence = writable_child_occurrence(
                parent_content_sha256=parent_content_sha256,
                byte_start=byte_start,
                byte_end=byte_end,
            )
        eid = evidence_id_for(
            source_system="sec_edgar",
            submission_accession=accession_str,
            occurrence=evidence_occurrence,
            content_sha256=digest,
        )
        # first_known_at: verified-retention clock of the first observation
        # of this evidence_id whose generation later became canonical. Copied
        # from the published row so a later competing local timestamp cannot
        # move the boundary backward. Not a Git commit timestamp.
        candidate_first_known_at = retrieved_at
        if existing_manifests:
            candidate_first_known_at = published_first_known_at(
                eid, existing_manifests, candidate_timestamp=retrieved_at
            )
        record["evidence_id"] = eid
        record["evidence_key_format"] = 1
        record["evidence_occurrence"] = evidence_occurrence
        record["first_known_at"] = candidate_first_known_at
        record["manifest_id"] = manifest_id_for(record)
        return record

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        root = _data_dir()
        discovery_path = root / "discovery.parquet"
        coverage_path = root / "index_coverage.parquet"
        attempts_path = root / "retrieval_attempts.parquet"
        manifests_path = source_ledger_path(root)
        queue_receipt_path = root / "retrieval_queue_receipt.json"

        discovery = _read_table(discovery_path, _DISCOVERY_COLUMNS)
        coverage = _read_table(coverage_path, _COVERAGE_COLUMNS)
        attempts = _read_table(attempts_path, _ATTEMPT_COLUMNS)
        known_discovery_accessions = set(discovery.get("accession", pd.Series(dtype=str)).astype(str))
        manifests = read_source_ledger(manifests_path)
        if manifests:
            validate_manifest_ledger(manifests)
        now = self._now_fn().astimezone(timezone.utc)
        now_et = now.astimezone(SEC_TIMEZONE)
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

        overlay_discovery: list[dict] = []
        daily_discovery: list[dict] = []
        coverage_updates: list[dict] = []

        def prior_coverage(kind: str, index_date: date) -> tuple[int, str]:
            if coverage.empty:
                return 0, ""
            kinds = coverage["coverage_kind"].fillna("").astype(str)
            expected_kinds = {"", "daily_index"} if kind == "daily_index" else {kind}
            matches = coverage.loc[
                coverage["index_date"].astype(str).eq(index_date.isoformat())
                & kinds.isin(expected_kinds)
            ]
            if matches.empty:
                return 0, ""
            return (
                int(matches.iloc[-1].get("attempt_count") or 0),
                str(matches.iloc[-1].get("last_error") or ""),
            )

        realtime_date = latest_expected_realtime_filing_date(now)
        if self.latest_filings_enabled:
            overlay_attempts, _ = prior_coverage("latest_filings", realtime_date)
            try:
                overlay = collect_latest_filings_overlay(
                    lambda start, count: self._fetch_latest_filings_page(
                        start, count, ua,
                    ),
                    discovery=discovery,
                    coverage=coverage,
                    cik_tickers=cik_tickers,
                    observed_at=now,
                )
                overlay_discovery = list(overlay["rows"])
                coverage_updates.append({
                    "index_date": realtime_date.isoformat(),
                    "status": "complete",
                    "target_count": len(overlay_discovery),
                    "attempt_count": overlay_attempts + 1,
                    "last_attempt_at": now_iso,
                    "last_error": None,
                    "policy_version": FORM_POLICY["policy_version"],
                    "coverage_kind": "latest_filings",
                    "observed_through": overlay["observed_through"],
                    "discovery_clock_policy_version": DISCOVERY_CLOCK_POLICY_VERSION,
                })
            except Exception as exc:  # noqa: BLE001
                coverage_updates.append({
                    "index_date": realtime_date.isoformat(),
                    "status": "retry",
                    "target_count": None,
                    "attempt_count": overlay_attempts + 1,
                    "last_attempt_at": now_iso,
                    "last_error": f"{type(exc).__name__}: {exc}",
                    "policy_version": FORM_POLICY["policy_version"],
                    "coverage_kind": "latest_filings",
                    "observed_through": None,
                    "discovery_clock_policy_version": DISCOVERY_CLOCK_POLICY_VERSION,
                })
        provisional_discovery = reconcile_discovery_rows(
            discovery,
            overlay_rows=overlay_discovery,
            daily_rows=[],
            reconciled_at=now_iso,
        )
        # Keep successful daily-index bytes until the window's registration
        # anchors are known.  ``due_index_dates`` deliberately visits the
        # current day before older days, so admitting reconciliation rows
        # immediately could discard a newer 8-K before an older S-3 for that
        # issuer is encountered later in the same run.  Resolve all in-window
        # anchors first, then make one issuer-scoped reconciliation pass.
        successful_indexes: list[tuple[date, str, int]] = []
        latest_ready_index_date = latest_expected_daily_index_date(now)
        for index_date in due_index_dates(
            coverage,
            today=latest_ready_index_date,
            lookback_days=lookback,
            full_history=full_history,
        ):
            prior_attempts, prior_error = prior_coverage("daily_index", index_date)
            if is_sec_calendar_closed(index_date):
                coverage_updates.append({
                    "index_date": index_date.isoformat(),
                    "status": "not_published",
                    "target_count": None,
                    "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now_iso,
                    "last_error": "SEC calendar closure: observed US federal holiday",
                    "policy_version": FORM_POLICY["policy_version"],
                    "coverage_kind": "daily_index",
                    "observed_through": None,
                    "discovery_clock_policy_version": DISCOVERY_CLOCK_POLICY_VERSION,
                })
                continue
            try:
                index_text = self._fetch_index(index_date, ua)
                # Parse once now so malformed/HTML indexes stay retryable at
                # the correct daily coverage row, rather than failing after
                # other successful dates have been persisted.
                parse_form_index(index_text)
                successful_indexes.append((index_date, index_text, prior_attempts))
            except IndexNotPublished as exc:
                is_aged = index_date <= (
                    now_et.date() - timedelta(days=INDEX_NOT_PUBLISHED_GRACE_DAYS)
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
                    "coverage_kind": "daily_index",
                    "observed_through": None,
                    "discovery_clock_policy_version": DISCOVERY_CLOCK_POLICY_VERSION,
                })
            except Exception as exc:  # noqa: BLE001
                if is_connection_error(exc):
                    raise
                coverage_updates.append({
                    "index_date": index_date.isoformat(), "status": "retry",
                    "target_count": None, "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now_iso, "last_error": f"{type(exc).__name__}: {exc}",
                    "policy_version": FORM_POLICY["policy_version"],
                    "coverage_kind": "daily_index",
                    "observed_through": None,
                    "discovery_clock_policy_version": DISCOVERY_CLOCK_POLICY_VERSION,
                })
            time.sleep(PACE_SECONDS)

        in_window_scope_ciks = _issuer_scope_ciks(provisional_discovery)
        for _, index_text, _ in successful_indexes:
            in_window_scope_ciks.update(
                row["cik"] for row in parse_form_index(index_text)
            )
        for index_date, index_text, prior_attempts in successful_indexes:
            rows = parse_form_index(
                index_text,
                reconciliation_ciks=in_window_scope_ciks,
            )
            for row in rows:
                cik_int = int(row["cik"])
                row["ticker"] = cik_tickers.get(cik_int)
                row["_first_seen"] = now_iso
                daily_discovery.append(row)
            coverage_updates.append({
                "index_date": index_date.isoformat(), "status": "complete",
                "target_count": len(rows), "attempt_count": prior_attempts + 1,
                "last_attempt_at": now_iso, "last_error": None,
                "policy_version": FORM_POLICY["policy_version"],
                "coverage_kind": "daily_index",
                "observed_through": None,
                "discovery_clock_policy_version": DISCOVERY_CLOCK_POLICY_VERSION,
            })

        discovery = reconcile_discovery_rows(
            provisional_discovery,
            overlay_rows=[],
            daily_rows=daily_discovery,
            reconciled_at=now_iso,
        )
        current_run_arrivals = set(discovery["accession"].astype(str)) - known_discovery_accessions
        if coverage_updates:
            updates = pd.DataFrame(coverage_updates)
            coverage = pd.concat([coverage, updates], ignore_index=True)
            coverage["coverage_kind"] = (
                coverage["coverage_kind"].fillna("").astype(str)
                .replace("", "daily_index")
            )
            coverage = coverage.drop_duplicates(
                ["coverage_kind", "index_date"], keep="last",
            )
            coverage = coverage[_COVERAGE_COLUMNS].sort_values(
                ["index_date", "coverage_kind"], kind="stable",
            ).reset_index(drop=True)
        _atomic_write(discovery, discovery_path)
        _atomic_write(coverage, coverage_path)

        # Suspect/deferred complete-submission bytes (for example an SEC error
        # page) remain retryable and cannot permanently close the queue item.
        have_complete = _eligible_complete_accessions(manifests)

        attempt_bound = _max_retrieval_attempts()
        parked = parked_accessions(attempts, max_attempts=attempt_bound)
        if parked:
            print(
                f"::warning title=capital-structure-retrieval-parked::"
                f"{len(parked)} filing(s) parked after {attempt_bound} retrieval "
                f"attempts each that never closed the queue item — bounded backlog, "
                f"evidence retained, not retried tonight; raise "
                f"{MAX_RETRIEVAL_ATTEMPTS_ENV} to pick them back up",
                flush=True,
            )
            log.warning(
                "sec_capital_structure: %d accession(s) parked at >=%d unclosed attempts: %s",
                len(parked), attempt_bound,
                ", ".join(sorted(parked)[:10]) + (" …" if len(parked) > 10 else ""),
            )

        queue = select_retrieval_queue(
            discovery,
            have_complete=have_complete,
            max_filings=self.max_filings_per_run,
            now=now,
            parked=parked,
            coverage=coverage,
            attempts=attempts,
            current_run_arrivals=current_run_arrivals,
        )
        queue_receipt = queue.attrs["retrieval_queue_receipt"]
        _validate_retrieval_queue_receipt(queue_receipt)
        _atomic_write_json(queue_receipt, queue_receipt_path)
        selected_lanes = queue.attrs["retrieval_lanes_by_accession"]
        selected_work_classes = queue.attrs["retrieval_work_classes_by_accession"]

        source_store = self._source_store()
        watermark_before = source_high_watermark(manifests)
        new_manifests: list[dict] = []
        new_attempts: list[dict] = []
        sanitized_fields: list[str] = []
        re_observed = 0
        # ``to_dict("records")`` rather than ``iterrows()``: ``iterrows`` builds a
        # per-row Series, and building it normalizes a ``None`` in an object column
        # into ``float('nan')``.  That laundering is the 2026-08-06 nightly abort —
        # ``collection_scope`` is legitimately ``None`` for every discovery row
        # written before Wave 2C added the column, and it arrived at the manifest
        # writer as NaN.  ``to_dict("records")`` preserves ``None`` (measured).
        for row in queue.to_dict("records"):
            accession = str(row["accession"])
            selected_lane = selected_lanes.get(accession)
            if selected_lane not in RETRIEVAL_LANE_ORDER:
                raise ValueError(f"{accession}: selected filing has no valid retrieval lane")
            selected_work_class = selected_work_classes.get(accession)
            if selected_work_class not in WORK_CLASS_ORDER:
                raise ValueError(f"{accession}: selected filing has no valid work class")
            url = str(row["canonical_url"])
            source_id = f"{accession}:0:complete-submission.txt"
            bundle_version = _next_bundle_document_version(manifests, accession)
            attempted_at = _iso(self._now_fn())
            attempt_observed_eids: list[str] = []
            retained_available_at: str | None = None
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
                # Fail closed: a production-eligible complete submission must have
                # bound spans so child occurrences are deterministic. Deferred
                # submissions (not eligible/clean) may proceed without spans.
                is_eligible_complete = (
                    complete_inspection.parser_eligibility == "eligible"
                    and complete_inspection.corruption_state == "clean"
                )
                if is_eligible_complete and not bundle.documents and not _DOCUMENT_RE.search(raw):
                    raise EvidenceIdentityError(
                        f"{accession}: no DOCUMENT blocks found in eligible complete submission"
                    )
                if is_eligible_complete:
                    # Verify spans; fail closed if they cannot be bound.
                    try:
                        candidate_spans = document_inner_spans(raw)
                        blocks = _DOCUMENT_RE.findall(raw)
                        if len(candidate_spans) != len(blocks):
                            raise EvidenceIdentityError(
                                f"{accession}: span count {len(candidate_spans)} != "
                                f"document block count {len(blocks)}"
                            )
                        for i, ((s, e), block) in enumerate(zip(candidate_spans, blocks)):
                            if raw[s:e] != block:
                                raise EvidenceIdentityError(
                                    f"{accession}: document[{i}] inner bytes do not "
                                    "match document_inner_spans"
                                )
                    except EvidenceIdentityError:
                        raise  # fail closed — re-raise to defer this filing

                receipt = source_store.put_verified(
                    raw, media_type=complete_inspection.media_type
                )
                if receipt is None:
                    raise RuntimeError(
                        format_store_failure(getattr(source_store, "last_failure", None))
                    )
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
                            format_store_failure(
                                getattr(source_store, "last_failure", None)
                            )
                            + f" for {document.filename or document.sequence}"
                        )
                    stored_children.append(
                        (role, document, filename, inspection, doc_receipt)
                    )

                # Both clocks begin only after every selected object's write and
                # readback has succeeded. A request-start timestamp would make
                # evidence appear system-visible before durable retention.
                retained_at = _iso(self._now_fn())
                # The combined published pool for first_known_at resolution includes
                # all already-committed rows plus manifests built earlier this run.
                combined_published = list(manifests) + new_manifests
                complete_sha256 = hashlib.sha256(raw).hexdigest()
                filing_manifests: list[dict] = []
                complete_manifest = self._manifest_record(
                    discovery=row, bundle=bundle, source_id=source_id,
                    canonical_url=url, document_name="complete-submission.txt",
                    document_type=str(row["form"]), document_role="complete_submission",
                    sequence="0", raw=raw, receipt=receipt, retrieved_at=retained_at,
                    inspection=complete_inspection,
                    first_seen_at=retained_at, document_version=bundle_version,
                    parent_manifest_id=None, sanitized=sanitized_fields,
                    existing_manifests=combined_published,
                )
                _validate_source_manifest(complete_manifest)
                attempt_observed_eids.append(complete_manifest["evidence_id"])

                # Closed-bundle law: every child in a newly persisted bundle
                # points at this run's candidate complete-submission manifest,
                # including when the complete occurrence+interpretation is
                # unchanged. A revision remints the whole accession-wide
                # version; re-observation persists nothing.
                parent_id = complete_manifest["manifest_id"]
                child_manifests: list[dict] = []
                for role, document, filename, inspection, doc_receipt in stored_children:
                    doc_source_id = f"{accession}:{document.sequence or 'unknown'}:{filename}"
                    document_manifest = self._manifest_record(
                        discovery=row, bundle=bundle,
                        source_id=doc_source_id,
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
                        parent_manifest_id=parent_id, sanitized=sanitized_fields,
                        parent_content_sha256=complete_sha256,
                        byte_start=document.byte_start,
                        byte_end=document.byte_end,
                        existing_manifests=combined_published,
                    )
                    _validate_source_manifest(document_manifest)
                    attempt_observed_eids.append(document_manifest["evidence_id"])
                    child_manifests.append(document_manifest)
                candidates = [complete_manifest, *child_manifests]
                decision = classify_bundle_against_published(
                    candidates, combined_published
                )
                if decision["status"] == "re_observed":
                    re_observed += 1
                    retained_available_at = retained_at
                    state, error = "stored", None
                    content_hash = complete_sha256
                    http_status = None
                    storage_operation = None
                    error_class = None
                    attempt_store_id = getattr(source_store, "store_id", None)
                    attempt_id = hashlib.sha256(
                        f"{source_id}|{attempted_at}|{state}".encode("utf-8")
                    ).hexdigest()
                    new_attempts.append({
                        "attempt_id": attempt_id, "accession": accession,
                        "source_id": source_id, "canonical_url": url,
                        "attempted_at": attempted_at, "state": state,
                        "error": error, "content_sha256": content_hash,
                        "retrieval_lane": selected_lane,
                        "collection_scope": row.get("collection_scope"),
                        "http_status": http_status,
                        "storage_operation": storage_operation,
                        "store_id": attempt_store_id,
                        "error_class": error_class,
                        "observed_evidence_ids": json.dumps(attempt_observed_eids),
                        "retained_available_at": retained_available_at,
                        "work_class": selected_work_class,
                    })
                    time.sleep(PACE_SECONDS)
                    continue
                # All selected evidence must verify before any manifest for the
                # filing is committed. A partially stored bundle stays retryable.
                # Revision persistence is bundle-atomic: the entire candidate
                # bundle at this accession-wide version, never changed members
                # alone.
                new_manifests.extend(decision["persist"])
                retained_available_at = _iso(self._now_fn())
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
                content_hash = complete_sha256
                http_status = None
                storage_operation = None
                error_class = None
                attempt_store_id = getattr(source_store, "store_id", None)
            except ChildOccurrenceUnbound as exc:
                state = "stored_parser_deferred"
                error = f"{type(exc).__name__}: {exc}"
                content_hash = complete_sha256
                error_class = type(exc).__name__
                http_status = None
                storage_operation = None
                attempt_store_id = getattr(source_store, "store_id", None)
                log.warning(
                    "sec_capital_structure: %s child occurrence unbound: %s",
                    accession, error,
                )
            except Exception as exc:  # noqa: BLE001
                state = "storage_deferred" if "store" in str(exc).lower() else "transient_error"
                error = f"{type(exc).__name__}: {exc}"
                content_hash = None
                error_class = type(exc).__name__
                http_status = None
                storage_operation = None
                attempt_store_id = getattr(source_store, "store_id", None)
                failure = getattr(source_store, "last_failure", None)
                if isinstance(failure, dict) and state == "storage_deferred":
                    http_status = failure.get("http_status")
                    storage_operation = failure.get("operation")
                    error_class = failure.get("error_class") or error_class
                    if failure.get("store_id"):
                        attempt_store_id = failure.get("store_id")
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                if http_status is None and isinstance(status_code, int):
                    http_status = status_code
                log.warning("sec_capital_structure: %s deferred: %s", accession, error)
            attempt_id = hashlib.sha256(
                f"{source_id}|{attempted_at}|{state}".encode("utf-8")
            ).hexdigest()
            new_attempts.append({
                "attempt_id": attempt_id, "accession": accession, "source_id": source_id,
                "canonical_url": url, "attempted_at": attempted_at, "state": state,
                "error": error, "content_sha256": content_hash,
                "retrieval_lane": selected_lane,
                "collection_scope": row.get("collection_scope"),
                "http_status": http_status,
                "storage_operation": storage_operation,
                "store_id": attempt_store_id,
                "error_class": error_class,
                "observed_evidence_ids": json.dumps(attempt_observed_eids) if attempt_observed_eids else None,
                "retained_available_at": retained_available_at,
                "work_class": selected_work_class,
            })
            time.sleep(PACE_SECONDS)

        if sanitized_fields:
            # Disclosure, not decoration: name the fields so an expected legacy gap
            # (``filing.collection_scope`` on pre-Wave-2C discovery rows) reads
            # differently from an alarm (``filing.accession``).  Bare print at line
            # start — a logger prefix would make GitHub silently drop the annotation.
            counts = ", ".join(
                f"{field}={sanitized_fields.count(field)}"
                for field in sorted(set(sanitized_fields))
            )
            print(
                f"::warning title=capital-structure-manifest-null-fields::"
                f"{len(sanitized_fields)} absent manifest field(s) recorded as null "
                f"instead of a pandas NaN sentinel: {counts}",
                flush=True,
            )

        manifests = _append_manifests_strict(manifests, new_manifests)
        attempts = _append_keep_first(
            attempts, new_attempts, key="attempt_id", columns=_ATTEMPT_COLUMNS
        )
        write_source_ledger(manifests, manifests_path)
        _atomic_write(attempts, attempts_path)

        successful = sum(1 for attempt in new_attempts if attempt["state"] == "stored")
        parser_deferred = sum(
            1 for attempt in new_attempts if attempt["state"] == "stored_parser_deferred"
        )
        storage_deferred = sum(
            1 for attempt in new_attempts if attempt["state"] == "storage_deferred"
        )
        verified_retained = sum(
            1
            for record in new_manifests
            if (record.get("document") or {}).get("document_role") == "complete_submission"
            and (record.get("parser") or {}).get("eligibility") == "eligible"
            and (record.get("parser") or {}).get("corruption_state") == "clean"
        )
        retained_after_run = _eligible_complete_accessions(manifests)
        # Recomputed from the POST-run attempts ledger, so tonight's failures count
        # toward the bound immediately rather than one night late.  The bound is the
        # one resolved before the queue was built, so a run reports against a single
        # bound even if the environment changes underneath it.
        parked_after_run = parked_accessions(attempts, max_attempts=attempt_bound)
        selected_count = int(queue_receipt.get("selected_count") or 0)
        no_new_work_proven = selected_count == 0
        work_class_progress = []
        for work_class in WORK_CLASS_ORDER:
            class_attempts = [
                attempt for attempt in new_attempts
                if attempt.get("work_class") == work_class
            ]
            work_class_progress.append({
                "work_class": work_class,
                "attempted_count": len(class_attempts),
                "retrieved_count": sum(
                    attempt.get("state") == "stored" for attempt in class_attempts
                ),
                "parser_deferred_count": sum(
                    attempt.get("state") == "stored_parser_deferred"
                    for attempt in class_attempts
                ),
                "storage_deferred_count": sum(
                    attempt.get("state") == "storage_deferred"
                    for attempt in class_attempts
                ),
                "transient_error_count": sum(
                    attempt.get("state") == "transient_error"
                    for attempt in class_attempts
                ),
            })
        ingestion_run = build_ingestion_run(
            as_of=now_iso,
            store_id=getattr(source_store, "store_id", None),
            selected=selected_count,
            retrieved=successful,
            verified_retained=verified_retained,
            manifested=len(new_manifests),
            deferred=len(new_attempts) - successful,
            parser_deferred=parser_deferred,
            storage_deferred=storage_deferred,
            parked=len(parked_after_run),
            re_observed=re_observed,
            watermark_before=watermark_before,
            watermark_after=source_high_watermark(manifests),
            no_new_work_proven=no_new_work_proven,
            no_new_work_reason=(
                "queue selected no new filings; already-known or empty work"
                if no_new_work_proven
                else None
            ),
            work_classes=work_class_progress,
        )
        _atomic_write_json(ingestion_run, root / INGESTION_RUN_FILENAME)
        if ingestion_run["verdict"] == "fail":
            print(
                "::warning title=capital-structure-zero-progress::"
                f"{ingestion_run['verdict_reason']} "
                f"selected={selected_count} manifested={len(new_manifests)} "
                f"storage_deferred={storage_deferred}",
                flush=True,
            )
        pending_after_run = _retrieval_queue_candidates(
            discovery, have_complete=retained_after_run, parked=parked_after_run,
        )
        heartbeat = pd.DataFrame(
            {
                "index_days_complete": [sum(
                    1 for row in coverage_updates
                    if row["status"] == "complete"
                    and row["coverage_kind"] == "daily_index"
                )],
                "discovered": [len(current_run_arrivals)],
                "retrieved": [successful],
                "deferred": [len(new_attempts) - successful],
                # ``backlog`` is the RETRYABLE queue; parking removes rows from it.
                # ``parked`` is published beside it precisely so that shrink can
                # never be mistaken for healing — a backlog that falls because the
                # collector stopped looking must say so in the same frame.
                "backlog": [len(pending_after_run)],
                "parked": [len(parked_after_run)],
            },
            index=[pd.Timestamp(now_et.date())],
        )
        return {"sec_evidence__ingest": heartbeat}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    SecCapitalStructureAdapter().fetch()
