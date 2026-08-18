"""Bounded rolling ingestion for newly filed institutional Form 13F reports.

The rolling lane is deliberately a discovery and publication coordinator.  SEC
source parsing, immutable evidence storage, and catalog publication remain in
their dedicated modules.  This module joins those frozen contracts without
introducing a second authority surface:

* Latest Filings Atom is the fast discovery lane.
* A caller-supplied daily/full master index may backstop Atom's ephemeral view.
* Every exact SEC response body is retained in a deterministic frame before a
  normalized catalog generation is prepared.
* New accessions are appended to the current report-period generation in one
  batch; amendments remain independent immutable accessions.

No object-store prefix listing is used.  A period's current pointer is the sole
catalog discovery authority, and absence is established only by a bounded read.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import pandas as pd

from engine.research_vault.r2_store import (
    StrictBoundedReadStore,
    StrictConditionalWriteStore,
    VersionedBytes,
)

from .catalog import (
    HARD_MAX_CATALOG_POINTER_BYTES,
    PublishedCatalogGeneration,
    load_catalog_generation,
    prepare_catalog_generation,
    publish_catalog_generation,
)
from .models import (
    EVIDENCE_PREFIX,
    RawEvidenceReceipt,
    canonical_json_bytes,
    catalog_pointer_key,
    decode_canonical_json,
    normalize_accession,
    normalize_cik,
    normalize_form,
    normalize_report_period,
    normalize_utc,
    utc_datetime,
    validate_version,
)
from .sec_sources import (
    ATOM_EPHEMERAL_ENTRY_LIMIT,
    AtomScanResult,
    BulkTables,
    FilingDiscovery,
    parse_master_index,
    read_filing_package,
    scan_latest_filings_atom,
    validate_bulk_invariants,
)
from .storage import HARD_MAX_RAW_EVIDENCE_BYTES, publish_raw_evidence

ROLLING_RECEIPT_SCHEMA = "institutional_13f.rolling_receipt/v1"
ROLLING_CHECKPOINT_SCHEMA = "institutional_13f.rolling_checkpoint/v1"
PRODUCER_VERSION = "institutional-13f-rolling/1.0.0"
MAX_ACCESSIONS = 750
MAX_REQUESTS_PER_SECOND = 8.0
MAX_SEC_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_SEC_RUN_RESPONSE_BYTES = 2 * 1024 * 1024 * 1024
MAX_MASTER_INDEX_BYTES = 256 * 1024 * 1024
MAX_RECEIPT_DETAILS = 100
MAX_ERROR_REASON_CHARS = 240
MAX_CHECKPOINT_ACCESSIONS = 12_000
MAX_CHECKPOINT_BYTES = 2 * 1024 * 1024
CHECKPOINT_CAS_ATTEMPTS = 3
SYNTHETIC_INFOTABLE_SK_BASE = 1 << 62
SEC_ARCHIVES_ROOT = "https://www.sec.gov/Archives/"
SEC_EASTERN = ZoneInfo("America/New_York")
ROLLING_CHECKPOINT_KEY = f"{EVIDENCE_PREFIX}/rolling/checkpoint/current.json"

_URL_RE = re.compile(r"(?i)\b[A-Z][A-Z0-9+.-]{1,31}://[^\s<>'\"]+")
_ENV_ASSIGNMENT_RE = re.compile(
    r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_ENV_NAME_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:token|secret|password|passwd|api[_-]?key|access[_-]?key(?:[_-]?id)?|"
    r"secret[_-]?access[_-]?key|credentials?)\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_AUTHORIZATION_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[^\s,;]+")
_WINDOWS_PATH_RE = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:\\[^\r\n,;)\]}>\"']+")
_POSIX_PATH_RE = re.compile(r"(?<![A-Za-z0-9])(?:~/|/)[^\r\n,;)\]}>\"']+")
_RELATIVE_PATH_RE = re.compile(r"(?<![A-Za-z0-9])(?:\.\.?/)+[^\r\n,;)\]}>\"']+")
_AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_LONG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{32,}")


class Institutional13FRollingError(RuntimeError):
    """A rolling run could not preserve its evidence or catalog invariants."""


@dataclass(frozen=True)
class _Checkpoint:
    entries: Mapping[str, str]
    updated_at: str | None
    version: str | None


def _decode_checkpoint(observed: VersionedBytes) -> _Checkpoint:
    if observed.data is None:
        return _Checkpoint({}, None, None)
    if len(observed.data) > MAX_CHECKPOINT_BYTES:
        raise Institutional13FRollingError(
            "rolling checkpoint exceeds its byte ceiling"
        )
    try:
        value = decode_canonical_json(
            observed.data, label="institutional 13F rolling checkpoint"
        )
    except Exception as exc:
        raise Institutional13FRollingError("rolling checkpoint is invalid") from exc
    if set(value) != {"schema", "updated_at", "entries"}:
        raise Institutional13FRollingError("rolling checkpoint shape is invalid")
    if value.get("schema") != ROLLING_CHECKPOINT_SCHEMA:
        raise Institutional13FRollingError("rolling checkpoint schema is unsupported")
    updated_at = normalize_utc(value.get("updated_at"), field="checkpoint updated_at")
    raw_entries = value.get("entries")
    if (
        not isinstance(raw_entries, list)
        or len(raw_entries) > MAX_CHECKPOINT_ACCESSIONS
    ):
        raise Institutional13FRollingError("rolling checkpoint entries are invalid")
    entries: dict[str, str] = {}
    for item in raw_entries:
        if not isinstance(item, Mapping) or set(item) != {"accession", "accepted_at"}:
            raise Institutional13FRollingError(
                "rolling checkpoint entry shape is invalid"
            )
        accession = normalize_accession(str(item.get("accession") or ""))
        accepted_at = normalize_utc(
            item.get("accepted_at"), field="checkpoint accepted_at"
        )
        if accession in entries:
            raise Institutional13FRollingError(
                "rolling checkpoint contains a duplicate accession"
            )
        entries[accession] = accepted_at
    if entries and utc_datetime(
        max(entries.values()), field="checkpoint accepted_at"
    ) > utc_datetime(updated_at, field="checkpoint updated_at"):
        raise Institutional13FRollingError(
            "rolling checkpoint predates a retained filing acceptance"
        )
    canonical_entries = sorted(
        entries.items(), key=lambda item: (item[1], item[0]), reverse=True
    )
    if raw_entries != [
        {"accession": accession, "accepted_at": accepted_at}
        for accession, accepted_at in canonical_entries
    ]:
        raise Institutional13FRollingError(
            "rolling checkpoint entries are not canonically ordered"
        )
    return _Checkpoint(entries, updated_at, observed.version)


def _load_checkpoint(store: StrictConditionalWriteStore) -> _Checkpoint:
    try:
        observed = store.get_bytes_strict_bounded_versioned(
            ROLLING_CHECKPOINT_KEY, MAX_CHECKPOINT_BYTES
        )
    except Exception as exc:
        raise Institutional13FRollingError(
            "rolling checkpoint bounded versioned read failed"
        ) from exc
    if type(observed) is not VersionedBytes:
        raise Institutional13FRollingError(
            "rolling checkpoint versioned read returned an invalid value"
        )
    return _decode_checkpoint(observed)


def _checkpoint_payload(entries: Mapping[str, str], *, updated_at: str) -> bytes:
    normalized = {
        normalize_accession(accession): normalize_utc(
            accepted_at, field="checkpoint accepted_at"
        )
        for accession, accepted_at in entries.items()
    }
    normalized_updated_at = normalize_utc(updated_at, field="checkpoint updated_at")
    if normalized and utc_datetime(
        max(normalized.values()), field="checkpoint accepted_at"
    ) > utc_datetime(normalized_updated_at, field="checkpoint updated_at"):
        raise Institutional13FRollingError(
            "rolling checkpoint predates a retained filing acceptance"
        )
    ordered = sorted(
        normalized.items(), key=lambda item: (item[1], item[0]), reverse=True
    )[:MAX_CHECKPOINT_ACCESSIONS]
    payload = canonical_json_bytes(
        {
            "schema": ROLLING_CHECKPOINT_SCHEMA,
            "updated_at": normalized_updated_at,
            "entries": [
                {"accession": accession, "accepted_at": accepted_at}
                for accession, accepted_at in ordered
            ],
        }
    )
    if len(payload) > MAX_CHECKPOINT_BYTES:
        raise Institutional13FRollingError(
            "rolling checkpoint exceeds its byte ceiling"
        )
    return payload


def _trim_checkpoint_entries(entries: Mapping[str, str]) -> dict[str, str]:
    normalized = {
        normalize_accession(accession): normalize_utc(
            accepted_at, field="checkpoint accepted_at"
        )
        for accession, accepted_at in entries.items()
    }
    return dict(
        sorted(normalized.items(), key=lambda item: (item[1], item[0]), reverse=True)[
            :MAX_CHECKPOINT_ACCESSIONS
        ]
    )


def _publish_checkpoint(
    store: StrictConditionalWriteStore,
    additions: Mapping[str, str],
    *,
    updated_at: str,
) -> tuple[_Checkpoint, bool]:
    if not additions:
        return _load_checkpoint(store), False
    normalized_additions = {
        normalize_accession(accession): normalize_utc(
            accepted_at, field="checkpoint accepted_at"
        )
        for accession, accepted_at in additions.items()
    }
    for _attempt in range(CHECKPOINT_CAS_ATTEMPTS):
        current = _load_checkpoint(store)
        conflicts = [
            accession
            for accession, accepted_at in normalized_additions.items()
            if accession in current.entries
            and current.entries[accession] != accepted_at
        ]
        if conflicts:
            raise Institutional13FRollingError(
                f"rolling checkpoint acceptance conflict: {conflicts[0]}"
            )
        if all(
            current.entries.get(accession) == accepted_at
            for accession, accepted_at in normalized_additions.items()
        ):
            return current, False
        merged = {**current.entries, **normalized_additions}
        desired_entries = _trim_checkpoint_entries(merged)
        if desired_entries == dict(current.entries):
            return current, False
        effective_updated_at = normalize_utc(updated_at, field="checkpoint updated_at")
        if current.updated_at and utc_datetime(
            effective_updated_at, field="checkpoint updated_at"
        ) < utc_datetime(current.updated_at, field="checkpoint updated_at"):
            effective_updated_at = current.updated_at
        payload = _checkpoint_payload(desired_entries, updated_at=effective_updated_at)
        required_additions = {
            accession: accepted_at
            for accession, accepted_at in normalized_additions.items()
            if desired_entries.get(accession) == accepted_at
        }
        try:
            written = store.put_bytes_strict_conditional(
                ROLLING_CHECKPOINT_KEY,
                payload,
                expected_version=current.version,
                content_type="application/json",
            )
        except Exception as exc:
            # A remote write may have committed before acknowledgement loss.
            reconciled = _load_checkpoint(store)
            if all(
                reconciled.entries.get(accession) == accepted_at
                for accession, accepted_at in required_additions.items()
            ):
                return reconciled, True
            raise Institutional13FRollingError("rolling checkpoint CAS failed") from exc
        if written is True:
            reconciled = _load_checkpoint(store)
            if all(
                reconciled.entries.get(accession) == accepted_at
                for accession, accepted_at in required_additions.items()
            ):
                return reconciled, True
            raise Institutional13FRollingError(
                "rolling checkpoint CAS write did not verify"
            )
        if written is not False:
            raise Institutional13FRollingError(
                "rolling checkpoint CAS returned a non-boolean result"
            )
    raise Institutional13FRollingError("rolling checkpoint CAS retry limit reached")


def _fetch_bytes(result: Any) -> bytes:
    if isinstance(result, bytes):
        return result
    if isinstance(result, str):
        return result.encode("utf-8")
    if isinstance(result, Mapping):
        # Match the SEC reader's injected-fetch coercion exactly.
        return json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    content = getattr(result, "content", None)
    if isinstance(content, bytes):
        return content
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text.encode("utf-8")
    raise TypeError("fetch must return bytes, str, mapping, or response-like object")


class PacedFetch:
    """Single-lane bounded fetcher whose request starts never exceed eight/sec."""

    def __init__(
        self,
        fetch: Callable[[str], Any],
        *,
        requests_per_second: float = MAX_REQUESTS_PER_SECOND,
        maximum_bytes: int = MAX_SEC_RESPONSE_BYTES,
        maximum_total_bytes: int = MAX_SEC_RUN_RESPONSE_BYTES,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not callable(fetch):
            raise TypeError("fetch must be callable")
        if isinstance(requests_per_second, bool) or not isinstance(
            requests_per_second, (int, float)
        ):
            raise TypeError("requests_per_second must be numeric")
        rate = float(requests_per_second)
        if rate <= 0 or rate > MAX_REQUESTS_PER_SECOND:
            raise ValueError(
                f"requests_per_second must be above zero and at most {MAX_REQUESTS_PER_SECOND:g}"
            )
        if (
            isinstance(maximum_bytes, bool)
            or not isinstance(maximum_bytes, int)
            or maximum_bytes <= 0
            or maximum_bytes > MAX_SEC_RESPONSE_BYTES
        ):
            raise ValueError("maximum_bytes exceeds the SEC response ceiling")
        if (
            isinstance(maximum_total_bytes, bool)
            or not isinstance(maximum_total_bytes, int)
            or maximum_total_bytes <= 0
            or maximum_total_bytes > MAX_SEC_RUN_RESPONSE_BYTES
        ):
            raise ValueError("maximum_total_bytes exceeds the SEC run ceiling")
        self._fetch = fetch
        self._interval = 1.0 / rate
        self._maximum_bytes = maximum_bytes
        self._maximum_total_bytes = maximum_total_bytes
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_started: float | None = None
        self.request_count = 0
        self.response_bytes = 0

    def __call__(self, url: str) -> bytes:
        if self.response_bytes >= self._maximum_total_bytes:
            raise Institutional13FRollingError(
                "SEC cumulative response byte budget is exhausted"
            )
        now = self._monotonic()
        if self._last_started is not None:
            remaining = self._interval - (now - self._last_started)
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_started = now
        self.request_count += 1
        body = _fetch_bytes(self._fetch(url))
        self.response_bytes += len(body)
        if len(body) > self._maximum_bytes:
            raise Institutional13FRollingError(
                f"SEC response exceeds {self._maximum_bytes} bytes"
            )
        if self.response_bytes > self._maximum_total_bytes:
            raise Institutional13FRollingError(
                "SEC cumulative response byte budget is exhausted"
            )
        return body


def _part_name(url: str) -> str:
    parsed = urlparse(url)
    name = unquote(parsed.path.rsplit("/", 1)[-1])
    if name == "index.json":
        return name
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise Institutional13FRollingError(f"unsafe SEC response part name: {url}")
    return name


class _RecordingFetch:
    """Capture the exact bodies consumed by one ``read_filing_package`` call."""

    def __init__(self, fetch: Callable[[str], bytes]) -> None:
        self._fetch = fetch
        self.parts: dict[str, bytes] = {}

    def __call__(self, url: str) -> bytes:
        body = self._fetch(url)
        name = _part_name(url)
        prior = self.parts.get(name)
        if prior is not None and prior != body:
            raise Institutional13FRollingError(
                f"SEC returned two bodies for the same filing part: {name}"
            )
        self.parts[name] = body
        return body


def encode_framed_evidence(parts: Mapping[str, bytes]) -> bytes:
    """Encode lossless SEC response bodies using the parser's digest framing."""

    if not isinstance(parts, Mapping) or not parts:
        raise Institutional13FRollingError("filing evidence parts are empty")
    framed = bytearray()
    for name, body in sorted(parts.items()):
        if not isinstance(name, str) or not name:
            raise Institutional13FRollingError("filing evidence part name is invalid")
        if type(body) is not bytes:
            raise Institutional13FRollingError(
                "filing evidence part must be exact bytes"
            )
        name_bytes = name.encode("utf-8")
        framed.extend(len(name_bytes).to_bytes(8, "big"))
        framed.extend(name_bytes)
        framed.extend(len(body).to_bytes(8, "big"))
        framed.extend(body)
    result = bytes(framed)
    if len(result) > HARD_MAX_RAW_EVIDENCE_BYTES:
        raise Institutional13FRollingError(
            "framed filing evidence exceeds its byte ceiling"
        )
    return result


def decode_framed_evidence(payload: bytes) -> dict[str, bytes]:
    """Decode a retained filing frame; primarily useful for evidence inspection."""

    if type(payload) is not bytes or not payload:
        raise Institutional13FRollingError(
            "framed filing evidence must be non-empty bytes"
        )
    cursor = 0
    result: dict[str, bytes] = {}
    while cursor < len(payload):
        if len(payload) - cursor < 8:
            raise Institutional13FRollingError("truncated filing evidence name length")
        name_length = int.from_bytes(payload[cursor : cursor + 8], "big")
        cursor += 8
        if name_length <= 0 or len(payload) - cursor < name_length + 8:
            raise Institutional13FRollingError("truncated filing evidence name")
        try:
            name = payload[cursor : cursor + name_length].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Institutional13FRollingError(
                "filing evidence name is not UTF-8"
            ) from exc
        cursor += name_length
        body_length = int.from_bytes(payload[cursor : cursor + 8], "big")
        cursor += 8
        if body_length > len(payload) - cursor:
            raise Institutional13FRollingError("truncated filing evidence body")
        body = payload[cursor : cursor + body_length]
        cursor += body_length
        if name in result:
            raise Institutional13FRollingError("duplicate filing evidence part")
        result[name] = body
    if encode_framed_evidence(result) != payload:
        raise Institutional13FRollingError("filing evidence frame is not canonical")
    return result


def _acquire_filing(
    discovery: FilingDiscovery,
    fetch: Callable[[str], bytes],
) -> tuple[BulkTables, bytes]:
    recording = _RecordingFetch(fetch)
    tables = read_filing_package(
        discovery.index_url,
        recording,
        discovery=discovery,
    )
    payload = encode_framed_evidence(recording.parts)
    if "index.json" not in recording.parts:
        raise Institutional13FRollingError("filing evidence lacks index.json")
    if sha256(payload).hexdigest() != tables.source_sha256:
        raise Institutional13FRollingError(
            "retained filing evidence does not match parser source_sha256"
        )
    if sum(len(body) for body in recording.parts.values()) != tables.source_bytes:
        raise Institutional13FRollingError(
            "retained filing evidence does not match parser source_bytes"
        )
    return tables, payload


def _native(value: Any) -> Any:
    if value is None:
        return None
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, bool) and missing:
        return None
    item = getattr(value, "item", None)
    if callable(item):
        value = item()
    return value


def _optional_text(value: Any) -> str | None:
    value = _native(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    value = _native(value)
    if value is None:
        return None
    if isinstance(value, bool):
        raise Institutional13FRollingError("boolean cannot be normalized as an integer")
    return int(value)


def _optional_bool(value: Any) -> bool | None:
    value = _native(value)
    if value is None:
        return None
    if type(value) is not bool:
        raise Institutional13FRollingError("non-boolean source value")
    return value


def _one_row(frame: pd.DataFrame, label: str) -> Mapping[str, Any]:
    if len(frame) != 1:
        raise Institutional13FRollingError(f"{label} must contain exactly one row")
    return frame.iloc[0].to_dict()


def _normalize_accepted_at(
    *, discovery: FilingDiscovery, submission: Mapping[str, Any]
) -> str:
    """Resolve exact SEC acceptance time, normalizing SGML local time to UTC."""

    atom_value = discovery.accepted_at
    atom_utc = normalize_utc(atom_value, field="accepted_at") if atom_value else None
    submission_value = _optional_text(submission.get("accepted_at"))
    submission_utc: str | None = None
    if submission_value:
        parsed = datetime.fromisoformat(
            submission_value[:-1] + "+00:00"
            if submission_value.endswith("Z")
            else submission_value
        )
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=SEC_EASTERN)
        submission_utc = normalize_utc(parsed, field="accepted_at")
    if atom_utc and submission_utc and atom_utc != submission_utc:
        raise Institutional13FRollingError(
            f"acceptance mismatch: discovery={atom_utc}, submission={submission_utc}"
        )
    accepted_at = atom_utc or submission_utc
    if accepted_at is None:
        raise Institutional13FRollingError("filing lacks an exact acceptance timestamp")
    return accepted_at


def _lineage_state(form: str, amendment_type: str | None) -> str:
    if form == "13F-HR":
        return "original"
    if form == "13F-NT":
        return "notice"
    if form == "13F-NT/A":
        return "notice_amendment"
    normalized = (amendment_type or "").strip().upper()
    if normalized == "NEW HOLDINGS":
        return "amendment_new_holdings"
    if normalized == "RESTATEMENT":
        return "amendment_restatement"
    return "amendment"


@dataclass(frozen=True)
class CatalogRows:
    filing: Mapping[str, Any]
    holdings: tuple[Mapping[str, Any], ...]
    manager_relationships: tuple[Mapping[str, Any], ...]
    invariant_findings: tuple[Mapping[str, str | None], ...]


def project_catalog_rows(
    tables: BulkTables,
    discovery: FilingDiscovery,
    receipt: RawEvidenceReceipt,
    *,
    retained_at: str,
    parser_version: str = PRODUCER_VERSION,
) -> CatalogRows:
    """Convert one parsed filing to the frozen catalog row contracts."""

    submission = _one_row(tables.submissions, "submission")
    cover = _one_row(tables.cover_pages, "cover page")
    accession = normalize_accession(str(submission.get("accession") or ""))
    if (
        accession != normalize_accession(discovery.accession)
        or accession != receipt.accession
    ):
        raise Institutional13FRollingError("filing accession provenance mismatch")
    form = normalize_form(str(submission.get("form") or ""))
    filer_cik = normalize_cik(str(submission.get("cik") or ""))
    if form != normalize_form(discovery.form) or form != receipt.form:
        raise Institutional13FRollingError("filing form provenance mismatch")
    if filer_cik != normalize_cik(discovery.cik) or filer_cik != receipt.filer_cik:
        raise Institutional13FRollingError("filing CIK provenance mismatch")
    report_period = normalize_report_period(str(submission.get("period_end") or ""))
    if report_period != str(receipt.clocks.report_period):
        raise Institutional13FRollingError("filing report-period provenance mismatch")
    accepted_at = _normalize_accepted_at(discovery=discovery, submission=submission)
    if accepted_at != str(receipt.clocks.accepted_at):
        raise Institutional13FRollingError("filing acceptance provenance mismatch")
    retained_at = normalize_utc(retained_at, field="retained_at")
    if retained_at != str(receipt.clocks.retained_at):
        raise Institutional13FRollingError("filing retention provenance mismatch")
    if receipt.raw_object.sha256 != tables.source_sha256:
        raise Institutional13FRollingError(
            "raw receipt does not bind parser source_sha256"
        )

    is_amendment = form.endswith("/A")
    cover_amendment = _optional_bool(cover.get("is_amendment"))
    if cover_amendment is not None and cover_amendment != is_amendment:
        raise Institutional13FRollingError(
            "form and cover-page amendment flags disagree"
        )
    amendment_number = _optional_int(cover.get("amendment_number"))
    amendment_type = _optional_text(cover.get("amendment_type"))
    if not is_amendment and (
        amendment_number is not None or amendment_type is not None
    ):
        raise Institutional13FRollingError("original filing carries amendment metadata")

    findings = tuple(
        {
            "code": item.code,
            "severity": item.severity,
            "detail": item.detail,
        }
        for item in validate_bulk_invariants(tables)
    )
    errors = [item for item in findings if item["severity"] == "error"]
    if errors:
        raise Institutional13FRollingError(
            f"filing invariant failed: {errors[0]['code']}: {errors[0]['detail']}"
        )

    is_notice = form.startswith("13F-NT")
    if is_notice and not tables.holdings.empty:
        raise Institutional13FRollingError("Form 13F-NT cannot publish holding rows")
    summary: Mapping[str, Any] = {}
    if len(tables.summary_pages) > 1:
        raise Institutional13FRollingError("summary page contains multiple rows")
    if len(tables.summary_pages) == 1:
        summary = tables.summary_pages.iloc[0].to_dict()
    holding_rows: list[dict[str, Any]] = []
    explicit_holding_keys = {
        value
        for value in (
            _optional_int(item)
            for item in tables.holdings.get(
                "info_table_sk", pd.Series(dtype="Int64")
            ).tolist()
        )
        if value is not None
    }
    if any(value >= SYNTHETIC_INFOTABLE_SK_BASE for value in explicit_holding_keys):
        raise Institutional13FRollingError(
            "SEC infotable_sk collides with the reserved synthetic-key range"
        )
    for source_position, raw in enumerate(
        tables.holdings.to_dict(orient="records"), start=1
    ):
        raw_value = _optional_int(raw.get("value"))
        info_table_sk = _optional_int(raw.get("info_table_sk"))
        if info_table_sk is None:
            source_ordinal = _optional_int(raw.get("source_ordinal")) or source_position
            if source_ordinal >= SYNTHETIC_INFOTABLE_SK_BASE:
                raise Institutional13FRollingError(
                    "source ordinal exceeds the synthetic infotable_sk range"
                )
            info_table_sk = SYNTHETIC_INFOTABLE_SK_BASE + source_ordinal
            if info_table_sk in explicit_holding_keys:
                raise Institutional13FRollingError(
                    "synthetic infotable_sk collides with an SEC-provided key"
                )
        row = {
            "accession": accession,
            "infotable_sk": info_table_sk,
            "name_of_issuer": _optional_text(raw.get("issuer_name")),
            "title_of_class": _optional_text(raw.get("title_of_class")),
            "cusip": _optional_text(raw.get("cusip")),
            "figi": _optional_text(raw.get("figi")),
            "value_reported": None if raw_value is None else str(raw_value),
            # Live filing XML carries no reliable unit flag and the population
            # contains both current-dollar and legacy-thousands exporters.  Raw
            # reported values remain useful evidence; USD authority stays null
            # until a separately provenance-aware resolver establishes a unit.
            "value_unit": "unresolved",
            "value_usd": None,
            "ssh_prn_amt": (
                None
                if _optional_int(raw.get("shares_or_principal_amount")) is None
                else str(_optional_int(raw.get("shares_or_principal_amount")))
            ),
            "ssh_prn_type": _optional_text(raw.get("shares_or_principal_amount_type")),
            "put_call": _optional_text(raw.get("put_call")),
            "investment_discretion": _optional_text(raw.get("investment_discretion")),
            "other_manager": _optional_text(raw.get("other_manager")),
            "voting_authority_sole": _optional_int(raw.get("voting_authority_sole")),
            "voting_authority_shared": _optional_int(
                raw.get("voting_authority_shared")
            ),
            "voting_authority_none": _optional_int(raw.get("voting_authority_none")),
        }
        row["row_hash"] = sha256(canonical_json_bytes(row)).hexdigest()
        holding_rows.append(row)

    relationship_rows: list[dict[str, Any]] = []
    for source_position, raw in enumerate(
        tables.reported_by.to_dict(orient="records"), start=1
    ):
        source_ordinal = _optional_int(raw.get("source_ordinal")) or source_position
        other_manager_sk = _optional_int(raw.get("other_manager_sk"))
        if other_manager_sk is None:
            other_manager_sk = source_ordinal
        relationship_rows.append(
            {
                "accession": accession,
                "relationship_kind": "reported_by_manager",
                "source_table": "OTHERMANAGER",
                "manager_sequence": None,
                "other_manager_sk": other_manager_sk,
                "manager_cik": _optional_text(raw.get("reporting_manager_cik")),
                "manager_name": _optional_text(raw.get("manager_name")),
                "form13f_file_number": _optional_text(raw.get("form_13f_file_number")),
                "crd_number": _optional_text(raw.get("crd_number")),
                "sec_file_number": _optional_text(raw.get("sec_file_number")),
            }
        )
    for source_position, raw in enumerate(
        tables.included_managers.to_dict(orient="records"), start=1
    ):
        # SEC manager sequence numbers are not unique.  The source ordinal is
        # retained in ``other_manager_sk`` to keep the catalog key lossless.
        source_ordinal = _optional_int(raw.get("source_ordinal")) or source_position
        relationship_rows.append(
            {
                "accession": accession,
                "relationship_kind": "included_manager",
                "source_table": "OTHERMANAGER2",
                "manager_sequence": _optional_int(raw.get("sequence_number")),
                "other_manager_sk": source_ordinal,
                "manager_cik": _optional_text(raw.get("included_manager_cik")),
                "manager_name": _optional_text(raw.get("manager_name")),
                "form13f_file_number": _optional_text(raw.get("form_13f_file_number")),
                "crd_number": _optional_text(raw.get("crd_number")),
                "sec_file_number": _optional_text(raw.get("sec_file_number")),
            }
        )

    table_entry_total = _optional_int(summary.get("table_entry_total"))
    other_manager_count = _optional_int(summary.get("other_included_managers_count"))
    confidential_omitted = _optional_bool(summary.get("is_confidential_omitted"))
    if is_notice:
        # A notice delegates holdings; zero is not an observed zero-position
        # portfolio.  Keep these metrics unknown so it cannot contaminate AUM or
        # breadth denominators.
        table_entry_total = None
        table_value_total_usd = None
        confidential_omitted = None
        quality_state = "notice_only_no_holdings"
    else:
        table_value_total_usd = None
        quality_state = (
            "unit_unresolved"
            if not findings
            else "unit_unresolved_with_source_warnings"
        )

    normalization_id = (
        "norm_"
        + sha256(
            canonical_json_bytes(
                {
                    "accession": accession,
                    "parser_version": parser_version,
                    "source_sha256": tables.source_sha256,
                    "value_unit": "unresolved",
                }
            )
        ).hexdigest()
    )
    filing = {
        "accession": accession,
        "filer_cik": filer_cik,
        "filer_name": _optional_text(cover.get("filing_manager_name")),
        "form": form,
        "filing_date": _optional_text(submission.get("filing_date")),
        "accepted_at": accepted_at,
        "report_period": report_period,
        "report_type": _optional_text(cover.get("report_type")),
        "form13f_file_number": _optional_text(cover.get("form_13f_file_number")),
        "is_amendment": is_amendment,
        "amendment_number": amendment_number,
        "amendment_type": amendment_type,
        "amends_accession": None,
        "lineage_state": _lineage_state(form, amendment_type),
        "confidential_omitted": confidential_omitted,
        "table_entry_total": table_entry_total,
        "table_value_total_usd": table_value_total_usd,
        "other_manager_count": other_manager_count,
        "source_receipt_id": receipt.receipt_id,
        "normalization_id": normalization_id,
        "raw_sha256": receipt.raw_object.sha256,
        "first_seen_at": retained_at,
        "retained_at": retained_at,
        "parser_version": parser_version,
        "quality_state": quality_state,
    }
    return CatalogRows(
        filing=filing,
        holdings=tuple(holding_rows),
        manager_relationships=tuple(relationship_rows),
        invariant_findings=findings,
    )


def _master_source(
    source: bytes | str | Path | None,
    fetch: Callable[[str], bytes],
) -> tuple[bytes | None, str | None]:
    if source is None:
        return None, None
    if isinstance(source, bytes):
        body = source
        label = "supplied-bytes"
    else:
        text = str(source)
        parsed = urlparse(text)
        if parsed.scheme:
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or not (
                host == "sec.gov" or host.endswith(".sec.gov")
            ):
                raise Institutional13FRollingError(
                    "master index URL must be an HTTPS SEC URL"
                )
            body = fetch(text)
            label = text
        else:
            path = Path(source).expanduser().resolve()
            size = path.stat().st_size
            if size > MAX_MASTER_INDEX_BYTES:
                raise Institutional13FRollingError(
                    "master index exceeds its byte ceiling"
                )
            body = path.read_bytes()
            label = path.as_uri()
    if not body:
        raise Institutional13FRollingError("master index is empty")
    if len(body) > MAX_MASTER_INDEX_BYTES:
        raise Institutional13FRollingError("master index exceeds its byte ceiling")
    return body, label


def _master_discoveries(body: bytes) -> tuple[FilingDiscovery, ...]:
    frame = parse_master_index(body)
    entries: list[FilingDiscovery] = []
    for raw in frame.to_dict(orient="records"):
        accession = normalize_accession(str(raw["accession"]))
        cik = normalize_cik(str(raw["cik"]))
        # Master indexes point at the complete-submission ``.txt`` outside the
        # accession directory.  ``read_filing_package`` needs the canonical
        # archive directory so it can resolve that filing's index.json.
        index_url = (
            f"{SEC_ARCHIVES_ROOT}edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{accession}-index.htm"
        )
        entries.append(
            FilingDiscovery(
                accession=accession,
                cik=cik,
                form=normalize_form(str(raw["form"])),
                filing_date=_optional_text(raw.get("filing_date")),
                accepted_at=None,
                index_url=index_url,
                company_name=_optional_text(raw.get("company_name")),
                source_ordinal=_optional_int(raw.get("source_ordinal")) or 0,
            )
        )
    return tuple(entries)


def _discoveries_conflict(first: FilingDiscovery, second: FilingDiscovery) -> bool:
    return bool(
        normalize_cik(first.cik) != normalize_cik(second.cik)
        or normalize_form(first.form) != normalize_form(second.form)
        or (
            first.filing_date is not None
            and second.filing_date is not None
            and first.filing_date != second.filing_date
        )
    )


def _merge_discoveries(
    atom: Sequence[FilingDiscovery], master: Sequence[FilingDiscovery]
) -> tuple[list[FilingDiscovery], list[dict[str, Any]]]:
    merged: dict[str, FilingDiscovery] = {}
    order: list[str] = []
    conflicts: list[dict[str, Any]] = []
    conflicted: set[str] = set()
    for source, entries in (("atom", atom), ("master_index", master)):
        for item in entries:
            accession = normalize_accession(item.accession)
            prior = merged.get(accession)
            if prior is None:
                merged[accession] = item
                order.append(accession)
                continue
            if _discoveries_conflict(prior, item):
                conflicted.add(accession)
                conflicts.append(
                    {
                        "accession": accession,
                        "stage": "discovery_merge",
                        "error": f"{source} identity conflicts with prior discovery",
                    }
                )
    return [merged[item] for item in order if item not in conflicted], conflicts


@dataclass
class _PeriodState:
    report_period: str
    existing: PublishedCatalogGeneration | None
    filings: list[Mapping[str, Any]] = field(default_factory=list)
    holdings: list[Mapping[str, Any]] = field(default_factory=list)
    manager_relationships: list[Mapping[str, Any]] = field(default_factory=list)
    source_receipt_ids: set[str] = field(default_factory=set)
    new_accessions: list[str] = field(default_factory=list)
    warning_count: int = 0

    def __post_init__(self) -> None:
        if self.existing is None:
            return
        self.filings.extend(dict(item) for item in self.existing.filings)
        self.holdings.extend(dict(item) for item in self.existing.holdings)
        self.manager_relationships.extend(
            dict(item) for item in self.existing.manager_relationships
        )
        self.source_receipt_ids.update(
            str(item["source_receipt_id"]) for item in self.existing.filings
        )

    @property
    def existing_by_accession(self) -> dict[str, Mapping[str, Any]]:
        existing_rows = self.existing.filings if self.existing is not None else ()
        return {str(item["accession"]): item for item in existing_rows}


def _load_period_state(
    store: StrictBoundedReadStore, report_period: str
) -> _PeriodState:
    key = catalog_pointer_key(report_period)
    try:
        pointer = store.get_bytes_strict_bounded(key, HARD_MAX_CATALOG_POINTER_BYTES)
    except Exception as exc:
        raise Institutional13FRollingError(
            f"bounded catalog pointer read failed for {report_period}"
        ) from exc
    if pointer is None:
        return _PeriodState(report_period, None)
    if type(pointer) is not bytes or len(pointer) > HARD_MAX_CATALOG_POINTER_BYTES:
        raise Institutional13FRollingError("catalog pointer bounded read is invalid")
    return _PeriodState(
        report_period,
        load_catalog_generation(store, report_period=report_period),
    )


def _existing_matches(
    row: Mapping[str, Any],
    *,
    discovery: FilingDiscovery,
    report_period: str,
    accepted_at: str,
    raw_sha256: str,
) -> bool:
    return (
        str(row.get("accession")) == normalize_accession(discovery.accession)
        and str(row.get("filer_cik")) == normalize_cik(discovery.cik)
        and str(row.get("form")) == normalize_form(discovery.form)
        and str(row.get("report_period")) == report_period
        and str(row.get("accepted_at")) == accepted_at
        and str(row.get("raw_sha256")) == raw_sha256
    )


def _clock(now: Callable[[], datetime]) -> str:
    value = now()
    if not isinstance(value, datetime):
        raise Institutional13FRollingError("clock must return datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise Institutional13FRollingError("clock must return an aware datetime")
    return normalize_utc(value, field="run clock")


def _bounded_details(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in values[:MAX_RECEIPT_DETAILS]]


def safe_exception_fields(error: BaseException) -> dict[str, str]:
    """Return bounded receipt-safe exception type, reason code, and message."""

    error_type = type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", error_type):
        error_type = "Exception"
    reason_code = re.sub(r"(?<!^)(?=[A-Z])", "_", error_type).lower()
    reason_code = re.sub(r"[^a-z0-9_]+", "_", reason_code).strip("_")
    reason_code = (reason_code or "exception")[:80]
    try:
        reason = str(error)[:4096]
    except Exception:  # noqa: BLE001  # pragma: no cover - hostile exceptions.
        reason = "operation failed"
    reason = "".join(
        character if character.isprintable() else " " for character in reason
    )
    for pattern, replacement in (
        (_URL_RE, "[redacted-url]"),
        (_ENV_ASSIGNMENT_RE, "[redacted-env]"),
        (_CREDENTIAL_ASSIGNMENT_RE, "[redacted-credential]"),
        (_AUTHORIZATION_RE, "[redacted-credential]"),
        (_WINDOWS_PATH_RE, "[redacted-path]"),
        (_POSIX_PATH_RE, "[redacted-path]"),
        (_RELATIVE_PATH_RE, "[redacted-path]"),
        (_ENV_NAME_RE, "[redacted-env]"),
        (_AWS_ACCESS_KEY_RE, "[redacted-token]"),
        (_LONG_TOKEN_RE, "[redacted-token]"),
    ):
        reason = pattern.sub(replacement, reason)
    reason = " ".join(reason.split())
    if not reason:
        reason = "operation failed"
    if len(reason) > MAX_ERROR_REASON_CHARS:
        reason = reason[: MAX_ERROR_REASON_CHARS - 1].rstrip() + "…"
    return {
        "error": f"{error_type}: {reason}",
        "reason_code": reason_code,
    }


def _error_detail(
    error: BaseException,
    *,
    stage: str,
    accession: str | None = None,
    report_period: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {"stage": stage, **safe_exception_fields(error)}
    if accession is not None:
        detail["accession"] = accession
    if report_period is not None:
        detail["report_period"] = report_period
    return detail


def run_rolling_ingestion(
    *,
    store: StrictConditionalWriteStore,
    fetch: Callable[[str], Any],
    master_index_source: bytes | str | Path | None = None,
    max_accessions: int = MAX_ACCESSIONS,
    requests_per_second: float = MAX_REQUESTS_PER_SECOND,
    producer_version: str = PRODUCER_VERSION,
    now: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Discover, retain, and append new filings, returning a loud run receipt."""

    if not isinstance(store, StrictConditionalWriteStore):
        raise Institutional13FRollingError(
            "rolling ingestion requires a StrictConditionalWriteStore"
        )
    if (
        isinstance(max_accessions, bool)
        or not isinstance(max_accessions, int)
        or max_accessions <= 0
        or max_accessions > MAX_ACCESSIONS
    ):
        raise ValueError(f"max_accessions must be between 1 and {MAX_ACCESSIONS}")
    producer_version = validate_version(producer_version)
    try:
        store.validate_strict_conditional_write_capability()
    except Exception as exc:
        raise Institutional13FRollingError(
            "rolling store lacks strict conditional-write capability"
        ) from exc
    clock = now or (lambda: datetime.now(timezone.utc))
    run_started_at = _clock(clock)
    checkpoint_before = _load_checkpoint(store)
    checkpoint_overlap = (
        normalize_utc(
            utc_datetime(
                max(checkpoint_before.entries.values()),
                field="checkpoint accepted_at",
            )
            + timedelta(microseconds=1),
            field="checkpoint overlap",
        )
        if checkpoint_before.entries
        else None
    )
    paced = PacedFetch(
        fetch,
        requests_per_second=requests_per_second,
        monotonic=monotonic,
        sleep=sleep,
    )
    failures: list[dict[str, Any]] = []
    atom_result: AtomScanResult | None = None
    try:
        atom_result = scan_latest_filings_atom(
            paced,
            entry_limit=min(max_accessions, ATOM_EPHEMERAL_ENTRY_LIMIT),
            known_accessions=checkpoint_before.entries,
            overlap_before=checkpoint_overlap,
        )
    except Exception as exc:  # noqa: BLE001 - master may still be a valid backstop.
        failures.append(_error_detail(exc, stage="atom_discovery"))

    master_entries: tuple[FilingDiscovery, ...] = ()
    master_body: bytes | None = None
    master_label: str | None = None
    if master_index_source is not None:
        try:
            master_body, master_label = _master_source(master_index_source, paced)
            assert master_body is not None
            master_entries = _master_discoveries(master_body)
        except Exception as exc:  # noqa: BLE001 - Atom may still be usable.
            failures.append(_error_detail(exc, stage="master_index_discovery"))

    atom_entries = atom_result.entries if atom_result is not None else ()
    discoveries, conflicts = _merge_discoveries(atom_entries, master_entries)
    failures.extend(conflicts)
    unknown_discoveries: list[FilingDiscovery] = []
    checkpoint_filtered = 0
    for discovery in discoveries:
        accession = normalize_accession(discovery.accession)
        checkpoint_accepted = checkpoint_before.entries.get(accession)
        if checkpoint_accepted is None:
            unknown_discoveries.append(discovery)
            continue
        if discovery.accepted_at is not None:
            discovered_accepted = normalize_utc(
                discovery.accepted_at, field="discovery accepted_at"
            )
            if discovered_accepted != checkpoint_accepted:
                failures.append(
                    {
                        "stage": "checkpoint_filter",
                        "accession": accession,
                        "error": (
                            "discovery acceptance conflicts with the rolling checkpoint"
                        ),
                    }
                )
                continue
        checkpoint_filtered += 1
    selected = unknown_discoveries[:max_accessions]
    backlog = unknown_discoveries[max_accessions:]
    source_cutoff_at = _clock(clock)

    period_states: dict[str, _PeriodState] = {}
    newly_staged = 0
    existing_skipped = 0
    raw_receipts_published = 0
    checkpoint_eligible: dict[str, str] = {}
    staged_acceptance: dict[str, str] = {}
    for discovery in selected:
        accession = normalize_accession(discovery.accession)
        report_period: str | None = None
        try:
            tables, raw_payload = _acquire_filing(discovery, paced)
        except Exception as exc:  # noqa: BLE001 - accession failure is isolated.
            failures.append(
                _error_detail(exc, stage="filing_fetch_parse", accession=accession)
            )
            continue
        try:
            submission = _one_row(tables.submissions, "submission")
            report_period = normalize_report_period(
                str(submission.get("period_end") or "")
            )
            accepted_at = _normalize_accepted_at(
                discovery=discovery, submission=submission
            )
            retained_at = _clock(clock)
            if utc_datetime(retained_at, field="retained_at") < utc_datetime(
                accepted_at, field="accepted_at"
            ):
                raise Institutional13FRollingError(
                    "retained_at predates filing acceptance"
                )
            state = period_states.get(report_period)
            if state is None:
                state = _load_period_state(store, report_period)
                period_states[report_period] = state
            existing = state.existing_by_accession.get(accession)
            if existing is not None and _existing_matches(
                existing,
                discovery=discovery,
                report_period=report_period,
                accepted_at=accepted_at,
                raw_sha256=tables.source_sha256,
            ):
                existing_skipped += 1
                # The fully verified current catalog is already normalized
                # authority, so this operational checkpoint may safely learn
                # the accession without publishing a replacement generation.
                checkpoint_eligible[accession] = accepted_at
                continue

            # Exact response bytes and their receipt are durable before any
            # normalized row can enter a catalog batch.
            receipt = publish_raw_evidence(
                store,
                accession=accession,
                filer_cik=discovery.cik,
                form=discovery.form,
                report_period=report_period,
                accepted_at=accepted_at,
                retained_at=retained_at,
                source_url=discovery.index_url,
                payload=raw_payload,
                producer_version=producer_version,
            )
            raw_receipts_published += 1
            if existing is not None:
                raise Institutional13FRollingError(
                    "immutable accession differs from the current catalog; "
                    "new raw evidence retained but catalog row not replaced"
                )
            projected = project_catalog_rows(
                tables,
                discovery,
                receipt,
                retained_at=retained_at,
                parser_version=producer_version,
            )
            state.filings.append(projected.filing)
            state.holdings.extend(projected.holdings)
            state.manager_relationships.extend(projected.manager_relationships)
            state.source_receipt_ids.add(receipt.receipt_id)
            state.new_accessions.append(accession)
            staged_acceptance[accession] = accepted_at
            state.warning_count += len(projected.invariant_findings)
            newly_staged += 1
        except Exception as exc:  # noqa: BLE001 - preserve raw, isolate normalization.
            failures.append(
                _error_detail(
                    exc,
                    stage="evidence_or_projection",
                    accession=accession,
                    report_period=report_period,
                )
            )

    period_results: list[dict[str, Any]] = []
    published_new = 0
    for report_period in sorted(period_states):
        state = period_states[report_period]
        if not state.new_accessions:
            continue
        published_at = _clock(clock)
        coverage = {
            "authority": "diagnostic_only",
            "state": "rolling",
            "run_started_at": run_started_at,
            "source_cutoff_at": source_cutoff_at,
            "atom_complete": bool(atom_result and atom_result.complete),
            "atom_pages": atom_result.pages_fetched if atom_result else 0,
            "atom_stop_reason": atom_result.stop_reason if atom_result else "failed",
            "master_index_supplied": master_index_source is not None,
            "discovered_accessions": len(discoveries),
            "selected_accessions": len(selected),
            "backlog_accessions": len(backlog),
            "new_filings": len(state.new_accessions),
            "existing_filings": (
                len(state.existing.filings) if state.existing is not None else 0
            ),
            "warning_count": state.warning_count,
            "run_failure_count": len(failures),
        }
        try:
            prepared = prepare_catalog_generation(
                report_period=report_period,
                source_cutoff_at=source_cutoff_at,
                published_at=published_at,
                producer_version=producer_version,
                filings=state.filings,
                holdings=state.holdings,
                manager_relationships=state.manager_relationships,
                source_receipt_ids=sorted(state.source_receipt_ids),
                coverage=coverage,
            )
            published = publish_catalog_generation(store, prepared)
            if published.superseded:
                raise Institutional13FRollingError(
                    "catalog publication was superseded by a concurrent generation"
                )
            published_new += len(state.new_accessions)
            checkpoint_eligible.update(
                {
                    accession: staged_acceptance[accession]
                    for accession in state.new_accessions
                }
            )
            period_results.append(
                {
                    "report_period": report_period,
                    "generation_id": published.generation_id,
                    "current_generation_id": published.current_generation_id,
                    "pointer_updated": published.pointer_updated,
                    "new_accessions": len(state.new_accessions),
                    "filing_rows": len(published.filings),
                    "holding_rows": len(published.holdings),
                    "manager_relationship_rows": len(published.manager_relationships),
                }
            )
        except Exception as exc:  # noqa: BLE001 - failure is receipt-visible.
            failures.append(
                _error_detail(
                    exc, stage="catalog_publication", report_period=report_period
                )
            )

    checkpoint_after = checkpoint_before
    checkpoint_updated = False
    if checkpoint_eligible:
        try:
            checkpoint_after, checkpoint_updated = _publish_checkpoint(
                store,
                checkpoint_eligible,
                updated_at=_clock(clock),
            )
        except Exception as exc:  # noqa: BLE001 - catalog remains authoritative.
            failures.append(_error_detail(exc, stage="checkpoint_publication"))

    atom_complete = bool(atom_result and atom_result.complete)
    # A non-empty backlog means unknown_discoveries saturated the operator
    # bound (--max-accessions): deliberate throughput control, not a coverage
    # loss. The remainder is retried by the next scheduled run, so it must
    # not be conflated with a real coverage gap (atom incomplete / failures).
    has_coverage_gap = not atom_complete or bool(failures)
    if has_coverage_gap:
        status = "partial_failure" if published_new or existing_skipped else "failed"
    elif backlog:
        status = "bounded_backlog"
    elif published_new:
        status = "ok"
    else:
        status = "no_changes"
    run_completed_at = _clock(clock)
    return {
        "schema": ROLLING_RECEIPT_SCHEMA,
        "status": status,
        "producer_version": producer_version,
        "run_started_at": run_started_at,
        "source_cutoff_at": source_cutoff_at,
        "run_completed_at": run_completed_at,
        "discovery": {
            "atom": {
                "pages_fetched": atom_result.pages_fetched if atom_result else 0,
                "entries": len(atom_entries),
                "complete": atom_complete,
                "stop_reason": atom_result.stop_reason if atom_result else "failed",
            },
            "master_index": {
                "supplied": master_index_source is not None,
                "source": master_label,
                "sha256": sha256(master_body).hexdigest() if master_body else None,
                "byte_length": len(master_body) if master_body else 0,
                "entries": len(master_entries),
            },
            "merged_accessions": len(discoveries),
            "checkpoint_filtered_accessions": checkpoint_filtered,
            "selected_accessions": len(selected),
            "backlog_accessions": len(backlog),
        },
        "checkpoint": {
            "object_key": ROLLING_CHECKPOINT_KEY,
            "authority": "operational_discovery_only",
            "entries_before": len(checkpoint_before.entries),
            "entries_after": len(checkpoint_after.entries),
            "updated": checkpoint_updated,
            "updated_at": checkpoint_after.updated_at,
        },
        "counts": {
            "requests": paced.request_count,
            "sec_response_bytes": paced.response_bytes,
            "raw_receipts_published": raw_receipts_published,
            "new_filings_staged": newly_staged,
            "new_filings_published": published_new,
            "checkpoint_accessions_skipped": checkpoint_filtered,
            "existing_accessions_skipped": existing_skipped,
            "periods_published": len(period_results),
            "failures": len(failures),
        },
        "catalog_periods": period_results,
        "backlog": {
            "count": len(backlog),
            "details": [
                {
                    "accession": item.accession,
                    "cik": item.cik,
                    "form": item.form,
                    "filing_date": item.filing_date,
                }
                for item in backlog[:MAX_RECEIPT_DETAILS]
            ],
            "details_truncated": len(backlog) > MAX_RECEIPT_DETAILS,
        },
        "failures": {
            "count": len(failures),
            "details": _bounded_details(failures),
            "details_truncated": len(failures) > MAX_RECEIPT_DETAILS,
        },
    }


__all__ = [
    "MAX_ACCESSIONS",
    "MAX_REQUESTS_PER_SECOND",
    "MAX_SEC_RESPONSE_BYTES",
    "MAX_SEC_RUN_RESPONSE_BYTES",
    "PRODUCER_VERSION",
    "ROLLING_CHECKPOINT_KEY",
    "ROLLING_CHECKPOINT_SCHEMA",
    "ROLLING_RECEIPT_SCHEMA",
    "CatalogRows",
    "Institutional13FRollingError",
    "PacedFetch",
    "decode_framed_evidence",
    "encode_framed_evidence",
    "project_catalog_rows",
    "run_rolling_ingestion",
    "safe_exception_fields",
]
