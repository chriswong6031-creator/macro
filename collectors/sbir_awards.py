"""Append-only SBIR.gov Phase I/II award observation collector.

Official public endpoint only::

    GET https://api.www.sbir.gov/public/api/awards?agency=<code>&year=<yyyy>&rows=<n>&start=<offset>

Probed live 2026-08-08 (recorded verbatim in the coverage manifest):

* the response envelope is a bare JSON **array** of award objects — there is no
  wrapper object and, critically, **no pagination metadata at all**: no total,
  no ``hasNext``.  Source exhaustion is therefore provable only by a *short*
  page (fewer rows returned than requested).  A full page at the declared cap is
  a complete *bounded sample*, never corpus completion;
* paging is offset-based (``start``), ``rows`` defaults to 100, and sorting is
  fixed to award date descending — the published docs state sorting cannot be
  changed;
* the public rate limit is **10 requests per 10 minutes**.  Exceeding it returns
  HTTP 403 with a **plain-text** body ("You've exceeded the rate limit for API
  usage..."), and the upstream AWS API Gateway separately returns HTTP 429 with
  a JSON ``TooManyRequestsError`` body while the shared public tier is
  saturated.  Neither is JSON-shaped award data and neither may ever read as an
  empty result, so both fail closed and preserve the last-good bundle;
* SBIR.gov's own API page currently carries a maintenance banner, so an
  unavailable source is the expected steady state rather than an exception.

Identity is source-native and exact: ``agency_tracking_number``, which the
official Award data dictionary defines as unique across all of TECH-Net.  A row
without it is refused rather than given a synthesized key.

The ledger is append-only.  A re-run may append a new semantic version of an
observation; it may never rewrite or delete accrued history.

Phase I / Phase II movement is **evidence of programmatic progression only**.
SBIR.gov publishes no parent/child link between a Phase I and a Phase II award,
so progression is never production conversion, and never revenue, backlog,
bookings, obligation, or outlay.  That judgement is made in
``engine.government_revenue.sbir_progression``; this collector only records what
the source said and when we could first see it.

Personally identifying source fields (point-of-contact and principal-
investigator names/phones/emails, street address, ZIP) are deliberately never
persisted — see ``PII_SOURCE_FIELDS_NEVER_PERSISTED``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config

SBIR_AWARDS_URL = "https://api.www.sbir.gov/public/api/awards"
SBIR_API_DOC_URL = "https://www.sbir.gov/api"
SBIR_AWARD_DICTIONARY_URL = "https://www.sbir.gov/data-resources/data-dictionary/award"
DEFAULT_USER_AGENT = "MastermindX Government Revenue Foresight contact@mastermind-x.com"

SCHEMA_VERSION = "1.0.0"
SBIR_OBSERVATION_SCHEMA = "government_revenue.sbir_award_observation.v1"
SBIR_PROJECTION_STATE_SCHEMA = "government_revenue.sbir_projection_state.v1"
SBIR_COLLECTION_RECEIPT_SCHEMA = "government_revenue.sbir_collection_receipt.v1"
SBIR_INGEST_STATUS_SCHEMA = "government_revenue.sbir_ingest_status.v1"
SBIR_COVERAGE_MANIFEST_SCHEMA = "government_revenue.sbir_coverage_manifest.v1"

SBIR_OBSERVATIONS_FILENAME = "sbir_award_observations.parquet"
SBIR_COLLECTION_RECEIPTS_FILENAME = "sbir_collection_receipts.jsonl"
SBIR_PROJECTION_STATE_FILENAME = "sbir_projection_state.json"
SBIR_INGEST_STATUS_FILENAME = "sbir_ingest_status.json"
SBIR_COLLECTOR_HEARTBEAT_FILENAME = "sbir_collector_heartbeat.parquet"

# Probed 2026-08-08 from the official API page: the public tier permits ten
# requests per ten minutes.  The collector paces strictly *below* that and caps
# its own per-run request budget, because the penalty for exceeding it is a
# plain-text 403 that would otherwise look like an unavailable source.
PUBLISHED_RATE_LIMIT_REQUESTS = 10
PUBLISHED_RATE_LIMIT_WINDOW_SECONDS = 600
MIN_REQUEST_PACING_SECONDS = 63.0
MAX_REQUESTS_PER_RUN = 8

PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
MAX_PAGES_PER_CELL = 2
MAX_CELLS_PER_RUN = 4
MAX_ROWS_PER_RUN = PAGE_SIZE * MAX_PAGES_PER_CELL * MAX_CELLS_PER_RUN
MAX_TEXT_UTF8_BYTES = 1_000

# Valid ``agency`` query values published on the API page, probed 2026-08-08.
# "DOD" is absent from the current query list (the page now names DOW =
# Department of War) but the Award data dictionary still references "DOD" for the
# branch rule, so it is accepted in *responses* while never used as a query.
PROBED_VALID_AGENCY_QUERY_CODES = (
    "DOW", "HHS", "NASA", "NSF", "DOE", "USDA", "EPA", "DOC", "ED", "DOT", "DHS",
)
LEGACY_RESPONSE_AGENCY_CODES = ("DOD",)
DEFAULT_AGENCY_QUERY_CODES = ("DOW",)

# Source fields that are never written to any artifact, receipt, or log.
PII_SOURCE_FIELDS_NEVER_PERSISTED = (
    "poc_name", "poc_title", "poc_phone", "poc_email",
    "pi_name", "pi_phone", "pi_email",
    "ri_poc_name", "ri_poc_phone",
    "address1", "address2", "city", "zip",
)

SBIR_OBSERVATION_COLUMNS = [
    "sbir_award_key",
    "source_award_identity_kind",
    "agency_tracking_number",
    "contract",
    "firm",
    "uei",
    "duns",
    "agency",
    "branch",
    "program",
    "phase",
    "phase_source_value",
    "topic_code",
    "solicitation_number",
    "solicitation_year",
    "award_year",
    "award_amount",
    "award_title",
    "research_institution",
    "state",
    "award_link",
    "observation_state_sha256",
    "source_at",
    "source_at_field",
    "source_fiscal_year",
    "effective_at",
    "contract_end_date",
    "observed_at",
    "known_at",
    "first_seen_at",
    "source_url",
    "source_query",
    "source_receipt_id",
    "source_response_sha256",
    "receipt_verified",
]

# The immutable semantic state of one observation.  A re-run whose row hashes
# identically is not a new version; a changed cell appends one.
SBIR_OBSERVATION_STATE_FIELDS = (
    "sbir_award_key",
    "agency_tracking_number",
    "contract",
    "firm",
    "uei",
    "duns",
    "agency",
    "branch",
    "program",
    "phase",
    "phase_source_value",
    "topic_code",
    "solicitation_number",
    "solicitation_year",
    "award_year",
    "award_amount",
    "award_title",
    "research_institution",
    "state",
    "award_link",
    "source_at",
    "effective_at",
    "contract_end_date",
)

SBIR_PROJECTION_GENERATION_FIELDS = (
    "projection_generation_id",
    "sbir_award_observations_semantic_sha256",
    "sbir_award_observations_row_count",
    "projection_semantic_sha256",
)

_NUMERIC_LEDGER_COLS = ("award_amount",)
_BOOLEAN_LEDGER_COLS = ("receipt_verified",)
# Pandas 3 refuses a string write into an all-NaN float64 column loaded from a
# legacy parquet, so every string-bearing nullable column is pinned to object at
# each frame-assembly point.  Column set is complete by construction.
_OBJECT_COLS = tuple(
    column
    for column in SBIR_OBSERVATION_COLUMNS
    if column not in _NUMERIC_LEDGER_COLS and column not in _BOOLEAN_LEDGER_COLS
)

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}

COVERAGE_SCOPE = (
    "Bounded offset-paged SBIR.gov award observations for the declared agency/year "
    "query cells only; never a complete SBIR/STTR corpus, never issuer attribution, "
    "and never a production-conversion claim."
)
PROGRESSION_LIMITATION = (
    "Phase I to Phase II movement is progression evidence only. SBIR.gov publishes no "
    "parent/child link between a Phase I and a Phase II award, so phase movement is "
    "never production conversion, revenue, backlog, bookings, obligation, or outlay."
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# The official UEI alphabet omits I and O so they cannot be confused with 1 and
# 0.  This must stay identical to the reviewed recipient graph's own identifier
# rule (``entity_resolution._valid_graph_identifier``): a looser alphabet here
# would store identifiers that can never join anything, which reads as coverage.
_UEI = re.compile(r"^[A-HJ-NP-Z0-9]{12}$")
_DUNS = re.compile(r"^[0-9]{9}$")
_FISCAL_YEAR = re.compile(r"^(19|20)\d{2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_FORBIDDEN_RECEIPT_KEY = re.compile(
    r"(?i)(authorization|credential|password|secret|token|api[\s_-]?key|"
    r"^(?:raw[\s_-]?)?(?:request|response|body|headers?)$|"
    r"(?:request|response).*(?:body|headers?|payload|raw)|"
    r"raw.*(?:request|response|body|headers?))"
)
# One expression, one leading flag: a second inline ``(?i)`` mid-pattern is a
# hard ``re.error`` on modern Python, which would turn this guard into an import
# failure rather than a check.
_PII_KEY = re.compile(
    r"(?i)(?:^|_)(?:poc|pi|ri_poc|address\d?|city|zip|postal|phone|email)(?:_|$)"
)


def _canonical_json_bytes(value: Any) -> bytes:
    """Stable bytes for every receipt, state hash, and generation binding."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


_SAFE_ERROR_MAX_CHARS = 800
_SAFE_ERROR_ELISION = "...[{elided} chars elided]..."


def _safe_error(exc: Exception | str, *, limit: int = _SAFE_ERROR_MAX_CHARS) -> str:
    """Bound a stored diagnostic while keeping both ends of the message.

    A plain head truncation throws away the half of a Python exception that
    names the failing *type* — the 2026-08-06 Government Revenue incident lost
    ``for dtype 'float64'`` exactly that way and sent the review at the wrong
    hypothesis.  Head+tail with an explicit elision marker keeps the diagnosis;
    the marker's own length is charged against the limit so the result is still
    bounded.
    """
    text = re.sub(
        r"(?i)(api[\s_-]?key|authorization|token|secret|password)\s*[=:]\s*[^,;\n]+",
        r"\1=[redacted]",
        str(exc),
    )
    if len(text) <= limit:
        return text
    reserve = len(_SAFE_ERROR_ELISION.format(elided=len(text)))
    budget = max(2, limit - reserve)
    head_len = max(1, budget * 3 // 5)
    tail_len = max(1, budget - head_len)
    elided = len(text) - head_len - tail_len
    return text[:head_len] + _SAFE_ERROR_ELISION.format(elided=elided) + text[-tail_len:]


def _utc_iso(value: str | datetime | None = None) -> str:
    if value is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"none", "nan", "nat", "null"} else None


def _bounded_text(value: Any, *, max_bytes: int = MAX_TEXT_UTF8_BYTES) -> str | None:
    text = _text(value)
    if text is None:
        return None
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _number(value: Any) -> float | None:
    """Parse a source award amount without inventing one.

    The dictionary permits "plain or formatted" dollars, so ``$1,234.00`` is a
    legitimate source spelling; anything that is not a finite number after
    stripping currency punctuation stays null rather than becoming zero.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        candidate = float(value)
    else:
        text = _text(value)
        if text is None:
            return None
        stripped = re.sub(r"[,$\s]", "", text)
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
            return None
        candidate = float(stripped)
    if not pd.notna(candidate) or candidate in {float("inf"), float("-inf")}:
        return None
    return candidate


def _iso_date(value: Any) -> str | None:
    """Accept only an unambiguous ISO date; never guess an ordering."""
    text = _text(value)
    if text is None:
        return None
    head = text.split("T", 1)[0].strip()
    if not _ISO_DATE.fullmatch(head):
        return None
    try:
        datetime.strptime(head, "%Y-%m-%d")
    except ValueError:
        return None
    return head


def _fiscal_year(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    head = text.split(".", 1)[0].strip()
    return head if _FISCAL_YEAR.fullmatch(head) else None


def _uei(value: Any) -> str | None:
    """Return a well-formed 12-character UEI, upper-cased, or nothing.

    A malformed identifier is dropped rather than stored, because every
    downstream issuer join is exact-identifier-only: a half-valid UEI in the
    ledger is a future false attribution.
    """
    text = _text(value)
    if text is None:
        return None
    candidate = text.upper().replace(" ", "")
    return candidate if _UEI.fullmatch(candidate) else None


def _duns(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    candidate = re.sub(r"[\s-]", "", text)
    return candidate if _DUNS.fullmatch(candidate) else None


def normalize_phase(value: Any) -> str | None:
    """Canonicalize the source phase spelling to ``I``/``II`` or nothing.

    The Award data dictionary describes the submitted form value as "1" or "2"
    while the published API examples show "Phase I"/"Phase II"; both spellings
    are accepted and the verbatim source value is retained alongside.  An
    unrecognized spelling yields ``None`` rather than a guess, so a Phase III or
    a future phase label can never be silently read as Phase II.
    """
    text = _text(value)
    if text is None:
        return None
    compact = re.sub(r"[\s\-_.]", "", text).upper()
    if compact in {"1", "I", "PHASE1", "PHASEI"}:
        return "I"
    if compact in {"2", "II", "PHASE2", "PHASEII"}:
        return "II"
    return None


def _coerce_object_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Force string-bearing nullable ledger columns to object dtype (NaN → None).

    Pandas 3.x refuses string writes to an all-NaN float64 column materialized
    by a reindex over a parquet written before that column existed.  Called at
    every frame-assembly point so an accrued ledger that predates a canonical
    column can still be appended to.
    """
    for col in _OBJECT_COLS:
        if col in df.columns and df[col].dtype != object:
            coerced = df[col].astype(object)
            df[col] = coerced.where(pd.notna(coerced), None)
    return df


def _contains_forbidden_receipt_key(value: Any) -> bool:
    """Reject raw-body, credential, and PII key shapes recursively."""
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() not in {"request_sha256", "response_sha256"} and (
                _FORBIDDEN_RECEIPT_KEY.search(key_text)
            ):
                return True
            if _PII_KEY.search(key_text):
                return True
            if _contains_forbidden_receipt_key(item):
                return True
    elif isinstance(value, (list, tuple, set)):
        return any(_contains_forbidden_receipt_key(item) for item in value)
    return False


def _generation_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {
            str(key): _generation_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_generation_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_generation_value(item) for item in value), key=_canonical_json_bytes)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return _utc_iso(value)
    if isinstance(value, float):
        return value if value not in {float("inf"), float("-inf")} else str(value)
    if isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return _generation_value(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def sbir_coverage_manifest(
    cells: Iterable[dict[str, Any]],
    *,
    page_size: int,
    max_pages_per_cell: int,
    max_cells_per_run: int,
    max_rows_per_run: int,
    request_pacing_seconds: float,
) -> dict[str, Any]:
    """Describe the declared collection universe and its honest omissions.

    This is a configuration manifest, not a run log: it states the query-cell
    rule and the safety caps so a reader can tell exactly what the lane promised
    to look at, and what it never claims to have seen.
    """
    declared = [
        {
            "agency": str(cell.get("agency") or "").upper(),
            "year": _fiscal_year(cell.get("year")),
        }
        for cell in cells
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": SBIR_COVERAGE_MANIFEST_SCHEMA,
        "coverage_scope": COVERAGE_SCOPE,
        "endpoint": SBIR_AWARDS_URL,
        "documentation": [SBIR_API_DOC_URL, SBIR_AWARD_DICTIONARY_URL],
        "query_cells": declared,
        "probed_at": "2026-08-08",
        "probed_valid_agency_query_codes": list(PROBED_VALID_AGENCY_QUERY_CODES),
        "legacy_response_agency_codes": list(LEGACY_RESPONSE_AGENCY_CODES),
        "paging": {
            "kind": "offset_based_start_parameter",
            "page_size": int(page_size),
            "max_pages_per_cell": int(max_pages_per_cell),
            "sort": "award_date_desc_fixed_by_source",
            "sort_is_configurable": False,
            "pagination_metadata_available": False,
            "total_record_count_available": False,
            "source_exhaustion_signal": "short_page_only",
        },
        "safety_caps": {
            "max_cells_per_run": int(max_cells_per_run),
            "max_rows_per_run": int(max_rows_per_run),
            "max_requests_per_run": MAX_REQUESTS_PER_RUN,
            "request_pacing_seconds": float(request_pacing_seconds),
            "published_rate_limit_requests": PUBLISHED_RATE_LIMIT_REQUESTS,
            "published_rate_limit_window_seconds": PUBLISHED_RATE_LIMIT_WINDOW_SECONDS,
        },
        "identity": {
            "source_native_key": "agency_tracking_number",
            "key_definition": "unique across all of TECH-Net per the official Award data dictionary",
            "rows_without_key_are_refused": True,
            "issuer_join": "exact_uei_only_against_reviewed_recipient_graph",
            "name_association_is_attribution": False,
        },
        "clocks": {
            "source_at": "proposal_award_date (first day of contract performance, per source)",
            "effective_at": "proposal_award_date",
            "observed_at": "collector retrieval instant",
            "known_at": "collector retrieval instant; knowledge is observation-bound and never backdated",
            "source_publication_clock_available": False,
            "source_reporting_lag_note": (
                "SBIR.gov states newly added awards need at least 24 hours to appear and that "
                "annual completeness lags; absence of a recent award is not evidence of no award."
            ),
        },
        "omissions": {
            "full_sbir_corpus": False,
            "bulk_download_used": False,
            "bulk_download_urls": [
                "https://data.www.sbir.gov/awarddatapublic/award_data.csv",
                "https://data.www.sbir.gov/mod_awarddatapublic_no_abstract/award_data_no_abstract.csv",
            ],
            "abstract_persisted": False,
            "pii_source_fields_never_persisted": list(PII_SOURCE_FIELDS_NEVER_PERSISTED),
        },
        "limitations": [PROGRESSION_LIMITATION],
    }


def sbir_coverage_manifest_id(manifest: dict[str, Any]) -> str:
    return "sbir-coverage-" + _sha256_json(manifest)


def _observation_state_sha256(row: dict | pd.Series) -> str:
    return _sha256_json({
        field: _generation_value(row.get(field))
        for field in SBIR_OBSERVATION_STATE_FIELDS
    })


def sbir_projection_generation(frame: pd.DataFrame) -> dict[str, str | int]:
    """Return an order-independent binding for the complete observation ledger."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("sbir observations must be a pandas DataFrame")
    missing = [column for column in SBIR_OBSERVATION_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(
            "sbir observations are missing canonical projection columns: " + ", ".join(missing)
        )
    records = [
        _canonical_json_bytes({
            column: _generation_value(row.get(column))
            for column in SBIR_OBSERVATION_COLUMNS
        })
        for _, row in frame.loc[:, SBIR_OBSERVATION_COLUMNS].iterrows()
    ]
    records.sort()
    hasher = hashlib.sha256()
    hasher.update(_canonical_json_bytes({
        "schema_version": SCHEMA_VERSION,
        "contract": SBIR_OBSERVATION_SCHEMA,
        "columns": SBIR_OBSERVATION_COLUMNS,
        "row_count": len(records),
    }))
    for record in records:
        hasher.update(b"\n")
        hasher.update(record)
    observations_digest = hasher.hexdigest()
    projection_digest = _sha256_json({
        "schema_version": SCHEMA_VERSION,
        "contract": SBIR_PROJECTION_STATE_SCHEMA,
        "sbir_award_observations_semantic_sha256": observations_digest,
        "sbir_award_observations_row_count": len(records),
    })
    return {
        "projection_generation_id": f"sbir-{projection_digest[:24]}",
        "sbir_award_observations_semantic_sha256": observations_digest,
        "sbir_award_observations_row_count": len(records),
        "projection_semantic_sha256": projection_digest,
    }


def sbir_projection_generation_matches(state: dict | None, frame: pd.DataFrame) -> bool:
    """Return whether ``state`` activates exactly the supplied full ledger."""
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != SCHEMA_VERSION
        or state.get("contract") != SBIR_PROJECTION_STATE_SCHEMA
        or state.get("activation_state") != "live"
        or state.get("projection_eligible") is not True
    ):
        return False
    try:
        generation = sbir_projection_generation(frame)
    except (TypeError, ValueError):
        return False
    return all(
        state.get(field) == generation[field]
        for field in SBIR_PROJECTION_GENERATION_FIELDS
    )


def _validated_receipt(receipt: Any, observed_at: str) -> tuple[str, str]:
    """Require the exact page receipt that contained this row."""
    if not isinstance(receipt, dict):
        raise ValueError("sbir observation is missing its source page receipt")
    receipt_id = _text(receipt.get("receipt_id"))
    response_sha256 = _text(receipt.get("response_sha256"))
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("contract") != SBIR_COLLECTION_RECEIPT_SCHEMA
        or receipt.get("rail") != "sbir_awards"
        or receipt.get("endpoint") != SBIR_AWARDS_URL
        or _text(receipt.get("observed_at")) is None
        or _utc_iso(str(receipt.get("observed_at"))) != observed_at
        or not receipt_id
        or not response_sha256
        or not _SHA256.fullmatch(response_sha256)
    ):
        raise ValueError("sbir observation has an invalid source page receipt binding")
    return receipt_id, response_sha256


def normalize_sbir_award_observation(
    raw: dict,
    receipt: dict,
    observed_at: str | datetime,
) -> dict[str, Any]:
    """Normalize one official award row without changing its source semantics.

    Refuses a row with no ``agency_tracking_number``: the exact source-native key
    is the whole basis of append-only identity, and a synthesized substitute
    would let two different awards collapse into one accrued history.
    """
    if not isinstance(raw, dict):
        raise TypeError("sbir award result must be an object")
    tracking_number = _text(raw.get("agency_tracking_number"))
    if tracking_number is None:
        raise ValueError("sbir award result is missing its exact agency_tracking_number identity")
    known_at = _utc_iso(observed_at)
    receipt_id, response_sha256 = _validated_receipt(receipt, known_at)
    source_at = _iso_date(raw.get("proposal_award_date"))
    agency = _text(raw.get("agency"))
    row: dict[str, Any] = {
        "sbir_award_key": tracking_number,
        "source_award_identity_kind": "agency_tracking_number",
        "agency_tracking_number": tracking_number,
        "contract": _text(raw.get("contract")),
        "firm": _bounded_text(raw.get("firm")),
        "uei": _uei(raw.get("uei")),
        "duns": _duns(raw.get("duns")),
        "agency": agency.upper() if agency else None,
        "branch": _text(raw.get("branch")),
        "program": (_text(raw.get("program")) or "").upper() or None,
        "phase": normalize_phase(raw.get("phase")),
        "phase_source_value": _text(raw.get("phase")),
        "topic_code": _text(raw.get("topic_code")),
        "solicitation_number": _text(raw.get("solicitation_number")),
        "solicitation_year": _fiscal_year(raw.get("solicitation_year")),
        "award_year": _fiscal_year(raw.get("award_year")),
        "award_amount": _number(raw.get("award_amount")),
        "award_title": _bounded_text(raw.get("award_title")),
        "research_institution": _bounded_text(raw.get("ri_name")),
        "state": _text(raw.get("state")),
        "award_link": _bounded_text(raw.get("award_link")),
        "observation_state_sha256": None,
        "source_at": source_at,
        "source_at_field": "proposal_award_date" if source_at else None,
        "source_fiscal_year": _fiscal_year(raw.get("award_year")),
        "effective_at": source_at,
        "contract_end_date": _iso_date(raw.get("contract_end_date")),
        "observed_at": known_at,
        "known_at": known_at,
        "first_seen_at": known_at,
        "source_url": SBIR_AWARDS_URL,
        "source_query": _text(receipt.get("query")),
        "source_receipt_id": receipt_id,
        "source_response_sha256": response_sha256,
        "receipt_verified": True,
    }
    row["observation_state_sha256"] = _observation_state_sha256(row)
    normalized = {column: row.get(column) for column in SBIR_OBSERVATION_COLUMNS}
    # Fail closed rather than trusting the column list: a future column whose
    # name matches a contact/address shape must never reach an artifact.
    leaked = [column for column in normalized if _PII_KEY.search(column)]
    if leaked:
        raise ValueError(f"sbir observation would persist PII columns: {', '.join(sorted(leaked))}")
    return normalized


def append_sbir_award_observations(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    """Append semantic versions by exact source key; never rewrite or delete.

    Every accrued row is retained verbatim, including a reverted A-B-A state.
    An incoming row whose semantic state matches the latest accrued state for
    that key is not a new version and is dropped; a changed state appends one
    and inherits the immutable ``first_seen_at`` of the first observation.
    """
    existing_frame = _coerce_object_cols(
        existing.reindex(columns=SBIR_OBSERVATION_COLUMNS).copy()
        if isinstance(existing, pd.DataFrame)
        else pd.DataFrame(columns=SBIR_OBSERVATION_COLUMNS)
    )
    incoming_frame = _coerce_object_cols(
        incoming.reindex(columns=SBIR_OBSERVATION_COLUMNS).copy()
        if isinstance(incoming, pd.DataFrame)
        else pd.DataFrame(columns=SBIR_OBSERVATION_COLUMNS)
    )
    retained = existing_frame.to_dict("records")
    latest: dict[str, dict[str, Any]] = {}
    for row in retained:
        key = _text(row.get("sbir_award_key"))
        if key:
            latest[key] = row

    additions: list[dict[str, Any]] = []
    for candidate in incoming_frame.to_dict("records"):
        key = _text(candidate.get("sbir_award_key"))
        if not key:
            raise ValueError("sbir observation identity requires an exact agency_tracking_number")
        candidate["sbir_award_key"] = key
        candidate["observation_state_sha256"] = _observation_state_sha256(candidate)
        prior = latest.get(key)
        if prior is not None:
            candidate["first_seen_at"] = prior.get("first_seen_at") or candidate.get("first_seen_at")
            if _text(prior.get("observation_state_sha256")) == candidate["observation_state_sha256"]:
                continue
            prior_clock = _utc_iso(str(prior.get("known_at")))
            candidate_clock = _utc_iso(str(candidate.get("known_at")))
            if candidate_clock <= prior_clock:
                raise ValueError(
                    "sbir semantic versions require a strictly increasing evidence clock"
                )
        additions.append(candidate)
        latest[key] = candidate

    merged = pd.DataFrame(
        [*retained, *additions],
        columns=SBIR_OBSERVATION_COLUMNS,
    ).reindex(columns=SBIR_OBSERVATION_COLUMNS).reset_index(drop=True)
    return _coerce_object_cols(merged)


def default_query_cells(
    *,
    as_of: str | datetime | None = None,
    agencies: Iterable[str] | None = None,
    years: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the declared query cells for one run.

    Default universe: the configured agencies for the current and prior federal
    fiscal year.  It is deliberately small — the public tier allows ten requests
    per ten minutes, so a wide universe would not be collectable at all.
    """
    observed = datetime.fromisoformat(_utc_iso(as_of))
    # Federal fiscal year rolls on 1 October.
    current_fy = observed.year + 1 if observed.month >= 10 else observed.year
    codes = tuple(str(code).upper() for code in (agencies or DEFAULT_AGENCY_QUERY_CODES))
    year_values = (
        tuple(str(year) for year in years)
        if years is not None
        else (str(current_fy), str(current_fy - 1))
    )
    cells = [
        {"agency": agency, "year": year}
        for agency in codes
        for year in year_values
    ]
    return cells[:MAX_CELLS_PER_RUN]


def heartbeat_frame(status: dict) -> pd.DataFrame:
    """Build the runner-owned dated heartbeat only for a successful activation."""
    if not isinstance(status, dict) or status.get("status") != "ok":
        raise ValueError("sbir heartbeat requires a successful collection status")
    observed = pd.Timestamp(status["observed_at"])
    if observed.tzinfo is not None:
        observed = observed.tz_convert(None)
    observed = observed.normalize()
    row = {
        "collection_complete": 1.0,
        "cells_declared": float(status.get("cells_declared", 0)),
        "cells_collected": float(status.get("cells_collected", 0)),
        "cells_source_exhausted": float(status.get("cells_source_exhausted", 0)),
        "cells_truncated_by_page_cap": float(status.get("cells_truncated_by_page_cap", 0)),
        "requests_this_run": float(status.get("requests_this_run", 0)),
        "rows_seen": float(status.get("rows_seen", 0)),
        "rows_accepted": float(status.get("rows_accepted", 0)),
        "rows_rejected_without_identity": float(status.get("rows_rejected_without_identity", 0)),
        "observations_total": float(status.get("observations_total", 0)),
        "errors": float(len(status.get("errors") or [])),
    }
    return pd.DataFrame([row], index=[observed])


def _read_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=SBIR_OBSERVATION_COLUMNS)
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - accrued history must fail closed
        raise RuntimeError(
            f"refusing to overwrite unreadable sbir observation ledger: {path}: {_safe_error(exc)}"
        ) from exc
    unknown = [column for column in frame.columns if column not in SBIR_OBSERVATION_COLUMNS]
    if unknown:
        raise RuntimeError(
            f"refusing to overwrite incompatible sbir observation ledger {path}: "
            f"unknown columns {', '.join(sorted(unknown))}"
        )
    return _coerce_object_cols(frame.reindex(columns=SBIR_OBSERVATION_COLUMNS))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - last-good state is never silently replaced
        raise RuntimeError(
            f"refusing to overwrite unreadable sbir state: {path}: {_safe_error(exc)}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"refusing to overwrite non-object sbir state: {path}")
    return payload


def _staging_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _stage_parquet(frame: pd.DataFrame, path: Path) -> tuple[Path, Path]:
    """Write one artifact to its temp file without touching the live artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _staging_path(path)
    frame.to_parquet(tmp, index=False)
    return tmp, path


def _stage_json(payload: dict[str, Any], path: Path) -> tuple[Path, Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _staging_path(path)
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return tmp, path


def _verify_staged_parquet(tmp: Path, frame: pd.DataFrame) -> pd.DataFrame:
    """Re-read a staged artifact and prove it round-tripped before anything commits.

    A frame that serializes without raising can still land unreadable, short, or
    missing a canonical column — and a reader that discovers that is reading a
    live artifact the collector has already replaced.  Verifying the staged copy
    moves the discovery to a point where every live artifact is still last-good.
    """
    replayed = pd.read_parquet(tmp)
    if len(replayed) != len(frame):
        raise RuntimeError(
            f"staged artifact did not round-trip: {tmp.name} has {len(replayed)} rows, "
            f"expected {len(frame)}"
        )
    absent = [column for column in SBIR_OBSERVATION_COLUMNS if column not in replayed.columns]
    if absent:
        raise RuntimeError(
            f"staged artifact dropped canonical columns: {tmp.name}: {', '.join(absent)}"
        )
    return replayed


def _commit_staged(staged: Iterable[tuple[Path, Path]]) -> None:
    for tmp, path in staged:
        os.replace(tmp, path)


def _discard_staged(staged: Iterable[tuple[Path, Path]]) -> None:
    for tmp, _path in staged:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - cleanup must never mask the real failure
            pass


def _append_receipts(receipts: Iterable[dict[str, Any]], path: Path) -> int:
    """Append immutable hash-only receipts; no bodies, headers, credentials, or PII."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = ""
    existing_receipts: dict[str, str] = {}
    if path.exists():
        try:
            existing_text = path.read_text(encoding="utf-8")
            for raw_line in existing_text.splitlines():
                if not raw_line.strip():
                    continue
                row = json.loads(raw_line)
                if not isinstance(row, dict) or not _text(row.get("receipt_id")):
                    raise ValueError("receipt record missing receipt_id")
                if _contains_forbidden_receipt_key(row):
                    raise ValueError("raw, sensitive, or PII receipt field is forbidden")
                canonical = json.dumps(row, sort_keys=True, separators=(",", ":"))
                receipt_id = str(row["receipt_id"])
                previous = existing_receipts.get(receipt_id)
                if previous is not None and previous != canonical:
                    raise ValueError("receipt ID is bound to conflicting evidence")
                existing_receipts[receipt_id] = canonical
        except Exception as exc:  # noqa: BLE001 - preserve immutable receipt history
            raise RuntimeError(
                f"refusing to overwrite unreadable sbir receipt ledger: {path}: {_safe_error(exc)}"
            ) from exc

    new_lines: list[str] = []
    for receipt in receipts:
        receipt_id = _text(receipt.get("receipt_id"))
        if not receipt_id:
            raise ValueError("sbir collection receipt missing receipt_id")
        if _contains_forbidden_receipt_key(receipt):
            raise ValueError("raw, sensitive, or PII receipt field is forbidden")
        canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        previous = existing_receipts.get(receipt_id)
        if previous is not None:
            if previous != canonical:
                raise ValueError("receipt ID is bound to conflicting evidence")
            continue
        new_lines.append(canonical)
        existing_receipts[receipt_id] = canonical
    if not new_lines:
        return 0

    separator = "" if not existing_text or existing_text.endswith("\n") else "\n"
    content = existing_text + separator + "\n".join(new_lines) + "\n"
    tmp = _staging_path(path)
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return len(new_lines)


class SbirRateLimitError(RuntimeError):
    """The published 10-requests-per-10-minutes public limit was refused upstream.

    Raised as its own type because a rate-limit body is *not* award data and must
    never be interpreted as an empty page: a silent empty read would retract
    every observation the ledger already holds for that cell.
    """


class SbirAwardsCollector:
    """Bounded append-only SBIR.gov award observation collector.

    The public tier permits ten requests per ten minutes, so the run is paced
    above that floor and its request budget is hard-capped.  A source failure
    leaves the accrued ledger, activation state, and status exactly as they were.
    """

    def __init__(
        self,
        root: Path | None = None,
        session: requests.Session | None = None,
        *,
        page_size: int = PAGE_SIZE,
        max_pages_per_cell: int = MAX_PAGES_PER_CELL,
        max_cells_per_run: int = MAX_CELLS_PER_RUN,
        request_pacing_seconds: float = MIN_REQUEST_PACING_SECONDS,
        allow_rate_limit_override: bool = False,
        user_agent: str | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else Path(config.ROOT).resolve()
        self.session = session or requests.Session()
        self.page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        self.max_pages_per_cell = max(1, min(int(max_pages_per_cell), MAX_PAGES_PER_CELL))
        self.max_cells_per_run = max(0, min(int(max_cells_per_run), MAX_CELLS_PER_RUN))
        pacing = max(0.0, float(request_pacing_seconds))
        if pacing < MIN_REQUEST_PACING_SECONDS and not allow_rate_limit_override:
            raise ValueError(
                "sbir request pacing must be at least "
                f"{MIN_REQUEST_PACING_SECONDS}s to respect the published "
                f"{PUBLISHED_RATE_LIMIT_REQUESTS} requests per "
                f"{PUBLISHED_RATE_LIMIT_WINDOW_SECONDS}s public limit; "
                "pass allow_rate_limit_override=True only for hermetic tests"
            )
        self.request_pacing_seconds = pacing
        self.headers = {
            "User-Agent": user_agent or os.getenv("SBIR_USER_AGENT", DEFAULT_USER_AGENT),
            "Accept": "application/json",
        }
        self._requests_this_run = 0

    # ---------------------------------------------------------------- requests

    def _budget(self) -> None:
        if self._requests_this_run >= MAX_REQUESTS_PER_RUN:
            raise RuntimeError(
                f"sbir run exceeded its {MAX_REQUESTS_PER_RUN}-request hard cap"
            )

    def _request_rows(self, query: dict[str, Any], *, timeout: int = 60) -> list[dict[str, Any]]:
        """Fetch one offset page and require a JSON array of objects.

        The endpoint answers a rate-limit refusal with a *plain-text* 403 and the
        fronting API Gateway answers a saturated public tier with a JSON 429, so
        neither status may fall through to ``.json()`` and neither may be read as
        zero results.
        """
        self._budget()
        url = f"{SBIR_AWARDS_URL}?{urlencode(query)}"
        self._requests_this_run += 1
        response = self.session.get(url, headers=self.headers, timeout=timeout)
        status = int(getattr(response, "status_code", 0) or 0)
        if status in {403, 429}:
            raise SbirRateLimitError(
                f"SBIR public API refused the request with HTTP {status}; "
                "the published limit is "
                f"{PUBLISHED_RATE_LIMIT_REQUESTS} requests per "
                f"{PUBLISHED_RATE_LIMIT_WINDOW_SECONDS}s"
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - a non-JSON body is never an empty page
            raise ValueError(
                f"SBIR award response from {SBIR_AWARDS_URL} was not JSON: {_safe_error(exc)}"
            ) from exc
        if not isinstance(payload, list):
            raise ValueError(
                "SBIR award response envelope must be a JSON array of award objects"
            )
        if len(payload) > self.page_size:
            raise ValueError("SBIR award page exceeded the requested row limit")
        if any(not isinstance(row, dict) for row in payload):
            raise ValueError("SBIR award page contains a non-object result")
        return payload

    @staticmethod
    def _receipt(
        *,
        query: dict[str, Any],
        response_payload: list[dict[str, Any]],
        cell: dict[str, Any],
        observed_at: str,
        page: int,
        record_count: int,
        short_page: bool,
    ) -> dict[str, Any]:
        """Bind canonical request/response hashes without persisting either body."""
        query_string = urlencode(query)
        request_sha256 = _sha256_json({"method": "GET", "endpoint": SBIR_AWARDS_URL, "query": query})
        response_sha256 = _sha256_json(response_payload)
        receipt_digest = _sha256_json({
            "observed_at": observed_at,
            "rail": "sbir_awards",
            "endpoint": SBIR_AWARDS_URL,
            "query": query_string,
            "page": int(page),
            "record_count": int(record_count),
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        })
        return {
            "schema_version": SCHEMA_VERSION,
            "contract": SBIR_COLLECTION_RECEIPT_SCHEMA,
            "receipt_id": f"sbir-award:{receipt_digest}",
            "observed_at": observed_at,
            "rail": "sbir_awards",
            "endpoint": SBIR_AWARDS_URL,
            "query": query_string,
            "agency": _text(cell.get("agency")),
            "year": _text(cell.get("year")),
            "page": int(page),
            "offset": int(query.get("start") or 0),
            "record_count": int(record_count),
            "short_page": bool(short_page),
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        }

    def fetch_cell_page(
        self,
        cell: dict[str, Any],
        page: int,
        *,
        observed_at: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch one declared offset page for one query cell."""
        agency = _text(cell.get("agency"))
        if agency is None:
            raise ValueError("sbir query cell requires an agency code")
        agency = agency.upper()
        if agency not in PROBED_VALID_AGENCY_QUERY_CODES:
            raise ValueError(
                f"sbir agency query code {agency} is not in the probed valid set: "
                + ", ".join(PROBED_VALID_AGENCY_QUERY_CODES)
            )
        page_int = int(page)
        if page_int < 1 or page_int > self.max_pages_per_cell:
            raise ValueError("sbir page exceeds the declared per-cell page cap")
        query: dict[str, Any] = {
            "agency": agency,
            "rows": self.page_size,
            "start": (page_int - 1) * self.page_size,
        }
        year = _fiscal_year(cell.get("year"))
        if year is not None:
            query["year"] = year
        rows = self._request_rows(query)
        receipt = self._receipt(
            query=query,
            response_payload=rows,
            cell={"agency": agency, "year": year},
            observed_at=observed_at,
            page=page_int,
            record_count=len(rows),
            short_page=len(rows) < self.page_size,
        )
        return rows, receipt

    # ------------------------------------------------------------------ paths

    def _paths(self) -> dict[str, Path]:
        data_dir = self.root / "data" / "government_revenue"
        return {
            "observations": data_dir / SBIR_OBSERVATIONS_FILENAME,
            "receipts": data_dir / SBIR_COLLECTION_RECEIPTS_FILENAME,
            "state": data_dir / SBIR_PROJECTION_STATE_FILENAME,
            "status": data_dir / SBIR_INGEST_STATUS_FILENAME,
        }

    # ---------------------------------------------------------------- collect

    def collect(
        self,
        *,
        observed_at: str | datetime | None = None,
        cells: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run one bounded collection, or leave the accrued bundle unchanged."""
        observed = _utc_iso(observed_at)
        paths = self._paths()
        self._requests_this_run = 0

        declared_cells = list(cells) if cells is not None else default_query_cells(as_of=observed)
        declared_cells = declared_cells[: self.max_cells_per_run]
        manifest = sbir_coverage_manifest(
            declared_cells,
            page_size=self.page_size,
            max_pages_per_cell=self.max_pages_per_cell,
            max_cells_per_run=self.max_cells_per_run,
            max_rows_per_run=MAX_ROWS_PER_RUN,
            request_pacing_seconds=self.request_pacing_seconds,
        )
        manifest_id = sbir_coverage_manifest_id(manifest)

        previous_observations = _read_existing(paths["observations"])
        previous_state = _read_json(paths["state"])
        if previous_state and (
            previous_state.get("schema_version") != SCHEMA_VERSION
            or previous_state.get("contract") != SBIR_PROJECTION_STATE_SCHEMA
            or previous_state.get("activation_state") != "live"
        ):
            raise RuntimeError("refusing to replace unknown or inactive sbir projection state")
        if previous_state.get("activation_state") == "live" and not (
            sbir_projection_generation_matches(previous_state, previous_observations)
        ):
            raise RuntimeError(
                "active sbir projection state does not match its observation ledger"
            )
        first_baseline = previous_observations.empty and not previous_state

        run_id = "sbir-" + _sha256_json({
            "observed_at": observed,
            "coverage_manifest_id": manifest_id,
        })[:24]

        receipts: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        cell_states: list[dict[str, Any]] = []
        rows_seen = 0
        rows_rejected_without_identity = 0
        seen_keys: set[str] = set()
        try:
            for cell in declared_cells:
                pages_fetched = 0
                cell_rows_seen = 0
                cell_rows_accepted = 0
                source_exhausted = False
                cell_receipt_ids: list[str] = []
                for page in range(1, self.max_pages_per_cell + 1):
                    if self.request_pacing_seconds and self._requests_this_run:
                        time.sleep(self.request_pacing_seconds)
                    raw_rows, receipt = self.fetch_cell_page(cell, page, observed_at=observed)
                    receipts.append(receipt)
                    cell_receipt_ids.append(str(receipt["receipt_id"]))
                    pages_fetched += 1
                    cell_rows_seen += len(raw_rows)
                    rows_seen += len(raw_rows)
                    for raw in raw_rows:
                        try:
                            normalized = normalize_sbir_award_observation(raw, receipt, observed)
                        except ValueError:
                            # A row with no exact source-native identity is
                            # counted, never keyed by a substitute.
                            rows_rejected_without_identity += 1
                            continue
                        key = normalized["sbir_award_key"]
                        if key in seen_keys:
                            # Offset paging over a live, award-date-sorted index
                            # can legitimately repeat a row when the index shifts
                            # between pages.  Keep the first observation of the
                            # run; a duplicate is not a new semantic version.
                            continue
                        seen_keys.add(key)
                        rows.append(normalized)
                        cell_rows_accepted += 1
                    if len(raw_rows) < self.page_size:
                        source_exhausted = True
                        break
                cell_states.append({
                    "agency": str(_text(cell.get("agency")) or "").upper(),
                    "year": _fiscal_year(cell.get("year")),
                    "pages_fetched": int(pages_fetched),
                    "rows_seen": int(cell_rows_seen),
                    "rows_accepted": int(cell_rows_accepted),
                    "source_exhausted": bool(source_exhausted),
                    "truncated_by_page_cap": bool(
                        not source_exhausted and pages_fetched == self.max_pages_per_cell
                    ),
                    "bounded_sample_complete": True,
                    "receipt_ids": cell_receipt_ids,
                })
        except Exception:
            # A successful page remains immutable evidence even when the run as a
            # whole fails, but no ledger, activation state, status, or heartbeat
            # is published from a partial collection.
            if receipts:
                _append_receipts(receipts, paths["receipts"])
            raise

        if len(rows) > MAX_ROWS_PER_RUN:
            raise RuntimeError(f"sbir run exceeded its {MAX_ROWS_PER_RUN}-row hard cap")

        incoming = _coerce_object_cols(pd.DataFrame(rows, columns=SBIR_OBSERVATION_COLUMNS))
        merged = append_sbir_award_observations(previous_observations, incoming)
        if len(merged) < len(previous_observations):
            raise RuntimeError("sbir merge would drop accrued observations; refusing to write")
        generation = sbir_projection_generation(merged)

        phase_counts = {
            "I": int(sum(1 for row in rows if row.get("phase") == "I")),
            "II": int(sum(1 for row in rows if row.get("phase") == "II")),
            "unrecognized": int(sum(1 for row in rows if row.get("phase") is None)),
        }
        state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "contract": SBIR_PROJECTION_STATE_SCHEMA,
            "activation_state": "live",
            "bounded_collection_complete": True,
            "projection_eligible": True,
            "run_id": run_id,
            "observed_at": observed,
            "last_successful_observed_at": observed,
            "coverage_manifest_id": manifest_id,
            "coverage_manifest": manifest,
            "cells": cell_states,
            "first_baseline": bool(first_baseline),
            "history_synthesized": False,
            "emits_forward_events": False,
            "candidate_family_preregistered": False,
            "authority": dict(AUTHORITY),
            **generation,
        }
        status: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "contract": SBIR_INGEST_STATUS_SCHEMA,
            "status": "ok",
            "partial": False,
            "collection_complete": True,
            "projection_eligible": True,
            "observed_at": observed,
            "effective_at": observed,
            "known_at": observed,
            "last_successful_observed_at": observed,
            "freshness": {"state": "fresh", "last_good_at": observed},
            "run_id": run_id,
            "projection_generation_id": generation["projection_generation_id"],
            "coverage_manifest_id": manifest_id,
            "coverage_manifest": manifest,
            "bounded": True,
            "source_only": True,
            "first_baseline": bool(first_baseline),
            "history_synthesized": False,
            "cells_declared": int(len(declared_cells)),
            "cells_collected": int(len(cell_states)),
            "cells_source_exhausted": int(
                sum(1 for row in cell_states if row["source_exhausted"])
            ),
            "cells_truncated_by_page_cap": int(
                sum(1 for row in cell_states if row["truncated_by_page_cap"])
            ),
            "requests_this_run": int(self._requests_this_run),
            "rows_seen": int(rows_seen),
            "rows_accepted": int(len(rows)),
            "rows_rejected_without_identity": int(rows_rejected_without_identity),
            "observations_new_this_run": int(len(merged) - len(previous_observations)),
            "observations_total": int(len(merged)),
            "phase_counts_this_run": phase_counts,
            "completeness": {
                "state": "complete",
                "full_sbir_corpus": False,
                "bounded_sample_complete": True,
                "source_exhausted": bool(
                    cell_states and all(row["source_exhausted"] for row in cell_states)
                ),
                "truncated_by_page_cap": bool(
                    any(row["truncated_by_page_cap"] for row in cell_states)
                ),
                "pagination_metadata_available": False,
                "scope": COVERAGE_SCOPE,
                "claim": (
                    "source exhaustion is provable only by a short page; a fully retrieved "
                    "declared page cap is a complete bounded sample, not corpus completion"
                ),
            },
            "receipts_this_run": int(len(receipts)),
            "errors": [],
            "source_urls": [SBIR_AWARDS_URL],
            "limitations": [PROGRESSION_LIMITATION],
            "authority": dict(AUTHORITY),
        }

        # Receipt evidence lands before the ledger; the state and status are the
        # activation markers and land only after the full ledger does.
        _append_receipts(receipts, paths["receipts"])
        staged: list[tuple[Path, Path]] = []
        try:
            staged.append(_stage_parquet(merged, paths["observations"]))
            replayed = _verify_staged_parquet(staged[0][0], merged)
            if not sbir_projection_generation_matches({**state}, replayed):
                raise RuntimeError(
                    "staged sbir observation ledger does not reproduce its generation binding"
                )
            staged.append(_stage_json(state, paths["state"]))
            staged.append(_stage_json(status, paths["status"]))
            _commit_staged(staged)
        finally:
            _discard_staged(staged)
        return status


class SbirAwardsAdapter(Adapter):
    """Slow-lane source-only adapter; the heartbeat exists only after success."""

    name = "sbir_awards"
    group = "government_revenue"
    stale_after_days = 7

    def stored_series(self) -> list[str]:
        return [Path(SBIR_COLLECTOR_HEARTBEAT_FILENAME).stem]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        del full_history  # bounded daily lane has no historical expansion mode
        status = SbirAwardsCollector(root=config.ROOT).collect()
        if status.get("status") != "ok":
            raise RuntimeError("sbir collector did not activate a complete bundle")
        return {Path(SBIR_COLLECTOR_HEARTBEAT_FILENAME).stem: heartbeat_frame(status)}


def write_heartbeat(status: dict[str, Any], root: Path) -> Path:
    """Persist direct-CLI health at the same path the standard runner uses."""
    path = Path(root) / "data" / "government_revenue" / SBIR_COLLECTOR_HEARTBEAT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _staging_path(path)
    try:
        heartbeat_frame(status).to_parquet(tmp, index=True)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--agency", action="append", dest="agencies")
    parser.add_argument("--year", action="append", dest="years")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_PER_CELL)
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    parser.add_argument(
        "--pacing-seconds",
        type=float,
        default=MIN_REQUEST_PACING_SECONDS,
        help=(
            "seconds between requests; must respect the published "
            f"{PUBLISHED_RATE_LIMIT_REQUESTS}/{PUBLISHED_RATE_LIMIT_WINDOW_SECONDS}s limit"
        ),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    collector = SbirAwardsCollector(
        root=args.root,
        page_size=args.page_size,
        max_pages_per_cell=args.max_pages,
        request_pacing_seconds=args.pacing_seconds,
    )
    status = collector.collect(
        cells=default_query_cells(agencies=args.agencies, years=args.years)
    )
    write_heartbeat(status, args.root)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
