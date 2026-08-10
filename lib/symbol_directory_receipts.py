"""Prospective completion receipts for symbol-directory artifacts.

The receipt is an operational observation boundary, not a historical upgrade.
Only the collector transaction that first publishes an artifact may publish its
sidecar.  A legacy parquet without a sidecar therefore stays reconstruction-only
forever; readers must never synthesize a receipt from filenames, mtimes, Git, or
the current contents of an old file.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar, cast

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

CompletionKind = Literal["listing_snapshot", "sec_registrant_map"]

COMPLETION_RECEIPT_SCHEMA = "symbol_directory.completion_receipt.v1"
COMPLETION_RECEIPT_PROFILE = "symbol_directory.operational_capture.v1"
COMPLETION_RECEIPT_PRODUCER = "collectors.symbol_directory.SymbolDirectoryAdapter"
COMPLETION_RECEIPT_PRODUCER_VERSION = "symbol_directory.collector.2026-08-10.v3"

NASDAQ_LISTED_SOURCE_ID = "nasdaq_trader.nasdaqlisted"
OTHER_LISTED_SOURCE_ID = "nasdaq_trader.otherlisted"
SEC_TICKERS_SOURCE_ID = "sec.company_tickers"

# Versioned completeness floors derived from the 24 tracked daily snapshots
# ending 2026-08-10.  Observed post-dedupe source ranges were 5,554--5,584
# nasdaqlisted and 7,461--7,530 otherlisted; SPY's zero-based otherlisted
# position was 6,168--6,224.  These lower bounds retain at least 10% headroom
# for honest roster drift while failing closed on a structurally valid but
# materially truncated response (including a historical-order prefix ending
# before SPY).  A legitimate breach requires an explicit reviewed
# profile/producer revision; it must never mint operational absence evidence
# silently.
NASDAQ_LISTED_ARTIFACT_MIN_ROWS = 5_000
OTHER_LISTED_ARTIFACT_MIN_ROWS = 6_500
SEC_TICKERS_ARTIFACT_MIN_ROWS = 1

_SOURCE_ARTIFACT_ROW_FLOORS = {
    NASDAQ_LISTED_SOURCE_ID: NASDAQ_LISTED_ARTIFACT_MIN_ROWS,
    OTHER_LISTED_SOURCE_ID: OTHER_LISTED_ARTIFACT_MIN_ROWS,
    SEC_TICKERS_SOURCE_ID: SEC_TICKERS_ARTIFACT_MIN_ROWS,
}

_MAX_RECEIPT_BYTES = 512 * 1024
_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024

_EXPECTED_SCHEMA: dict[CompletionKind, list[dict[str, str]]] = {
    "listing_snapshot": [
        {"name": "date", "dtype": "string"},
        {"name": "symbol", "dtype": "string"},
        {"name": "security_name", "dtype": "string"},
        {"name": "exchange", "dtype": "string"},
        {"name": "etf", "dtype": "bool"},
        {"name": "test_issue", "dtype": "bool"},
        {"name": "is_preferred", "dtype": "bool"},
        {"name": "source", "dtype": "string"},
    ],
    "sec_registrant_map": [
        {"name": "ticker", "dtype": "string"},
        {"name": "cik", "dtype": "int64"},
        {"name": "title", "dtype": "string"},
    ],
}

_T = TypeVar("_T")


class ReceiptValidationError(ValueError):
    """The completion receipt or its authenticated artifact is invalid."""


@dataclass(frozen=True, slots=True)
class SourceFetch(Generic[_T]):
    """A decoded response together with the exact ``response.content`` bytes.

    ``value`` preserves the legacy fetcher's decoded return value.  ``content``
    is deliberately separate: re-encoding ``value`` would not reproduce the
    exact upstream response and is never accepted as response evidence.
    """

    value: _T
    content: bytes
    requested_url: str
    started_at: str
    completed_at: str
    http_status: int = 200

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError(
                "SourceFetch.content must contain exact non-empty response bytes"
            )
        if self.http_status != 200:
            raise ValueError(
                "SourceFetch only represents a successful HTTP 200 response"
            )
        _parse_canonical_utc(self.started_at, field="SourceFetch.started_at")
        _parse_canonical_utc(self.completed_at, field="SourceFetch.completed_at")
        if _parse_canonical_utc(
            self.started_at, field="SourceFetch.started_at"
        ) > _parse_canonical_utc(self.completed_at, field="SourceFetch.completed_at"):
            raise ValueError("SourceFetch.started_at must not follow completed_at")


def canonical_utc_now() -> str:
    """Return the receipt profile's one canonical UTC representation."""

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def completion_receipt_path(
    symbol_directory_root: Path,
    *,
    kind: CompletionKind,
    observation_date: str,
) -> Path:
    """Return the prospective sidecar path for a newly written artifact."""

    lane = "snapshots" if kind == "listing_snapshot" else "cik_map"
    return symbol_directory_root / "receipts" / lane / f"{observation_date}.json"


def parquet_schema(frame: pd.DataFrame) -> list[dict[str, str]]:
    """Return the ordered, pandas-version-neutral logical parquet schema."""

    return [
        {"name": str(column), "dtype": _logical_dtype(frame[column].dtype)}
        for column in frame.columns
    ]


def _logical_dtype(dtype: Any) -> str:
    rendered = str(dtype)
    if rendered == "object" or rendered == "str" or rendered.startswith("string"):
        return "string"
    return rendered


def footer_diagnostic(*, source_id: str, text: str) -> dict[str, Any]:
    """Hash bounded, explicitly non-authoritative Nasdaq footer diagnostics."""

    lines = [
        line for line in text.splitlines() if line.startswith("File Creation Time")
    ]
    return {
        "source_id": source_id,
        "matching_line_count": len(lines),
        "line_sha256s": [
            hashlib.sha256(line.encode("utf-8")).hexdigest() for line in lines
        ],
        "authoritative": False,
    }


def durable_atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    """Publish a parquet with temp-write, fsync, absent-only link, and parent fsync."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, index=False)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def build_symbol_directory_completion_receipt(
    *,
    kind: CompletionKind,
    observation_date: str,
    artifact_path: Path,
    source_fetches: Sequence[tuple[str, SourceFetch[Any]]],
    collector_started_at: str,
    collector_completed_at: str,
    pre_dedupe_rows: int,
    duplicate_occurrences: int,
    duplicate_key_count: int,
    source_row_counts: Sequence[tuple[str, int]],
    pre_dedupe_spy_occurrences: Sequence[Mapping[str, Any]],
    non_authoritative_footers: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build and validate a receipt for an already-durable new artifact."""

    if kind == "listing_snapshot" and len(pre_dedupe_spy_occurrences) != 1:
        raise ReceiptValidationError(
            "operational listing receipt requires exactly one SPY occurrence"
        )

    artifact_bytes = artifact_path.read_bytes()
    frame = pd.read_parquet(artifact_path)
    artifact_key = _artifact_key(kind, observation_date)
    row_floor = 8_000 if kind == "listing_snapshot" else 1
    artifact_source_rows = _artifact_source_row_counts(kind, frame)

    diagnostics: dict[str, Any] = {
        "kind": kind,
        "pre_dedupe_spy_occurrence_count": len(pre_dedupe_spy_occurrences),
        "pre_dedupe_spy_occurrences": [
            dict(item) for item in pre_dedupe_spy_occurrences
        ],
    }
    if kind == "listing_snapshot":
        diagnostics["non_authoritative_footers"] = [
            dict(item) for item in non_authoritative_footers
        ]

    authority = {
        "lane": (
            "listing_observation"
            if kind == "listing_snapshot"
            else "sec_registrant_reference"
        ),
        "listing_identity_observation_eligible": kind == "listing_snapshot",
        "sec_registrant_reference_eligible": kind == "sec_registrant_map",
        "listing_sec_identity_binding_eligible": False,
        "context_only": True,
        "signal_eligible": False,
        "training_eligible": False,
        "promotion_eligible": False,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_trade": False,
    }

    value: dict[str, Any] = {
        "schema": COMPLETION_RECEIPT_SCHEMA,
        "profile": COMPLETION_RECEIPT_PROFILE,
        "producer": {
            "id": COMPLETION_RECEIPT_PRODUCER,
            "version": COMPLETION_RECEIPT_PRODUCER_VERSION,
        },
        "observation_date": observation_date,
        "artifact": {
            "kind": kind,
            "key": artifact_key,
            "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
            "bytes": len(artifact_bytes),
            "rows": len(frame),
            "parquet_schema": parquet_schema(frame),
        },
        "sources": [
            _source_receipt_record(source_id=source_id, fetched=fetched)
            for source_id, fetched in source_fetches
        ],
        "clocks": {
            "collector_started_at": collector_started_at,
            "collector_completed_at": collector_completed_at,
        },
        "completeness": {
            "status": "complete",
            "required_sources_complete": True,
            "parse_complete": True,
            "row_floor": row_floor,
            "row_floor_satisfied": len(frame) >= row_floor,
            "pre_dedupe_rows": pre_dedupe_rows,
            "post_dedupe_rows": len(frame),
            "duplicate_occurrences": duplicate_occurrences,
            "duplicate_key_count": duplicate_key_count,
            "source_row_counts": [
                {
                    "source_id": source_id,
                    "parsed_rows": rows,
                    "artifact_rows": artifact_source_rows.get(source_id, 0),
                    "minimum_artifact_rows": _SOURCE_ARTIFACT_ROW_FLOORS[source_id],
                }
                for source_id, rows in source_row_counts
            ],
        },
        "diagnostics": diagnostics,
        "evidence_policy": {
            "evidence_basis": "live_captured_source_response",
            "artifact_integrity": "sha256_bytes_rows_ordered_schema.v1",
            "source_response_integrity": "sha256_bytes_commitment_at_capture.v1",
            "source_response_bytes_retained": False,
            "source_response_replay_verifiable": False,
            "filename_git_mtime_authoritative": False,
            "prospective_only": True,
            "historical_continuity_inferred": False,
        },
        "authority": authority,
    }
    value["receipt_id"] = _receipt_id(value)
    return validate_symbol_directory_completion_receipt(
        value,
        artifact_path,
        expected_kind=kind,
    )


def write_symbol_directory_completion_receipt(
    receipt_path: Path,
    value: Mapping[str, Any],
    artifact_path: Path,
    *,
    expected_kind: CompletionKind,
) -> None:
    """Validate and publish an absent-only receipt after its artifact exists."""

    validated = validate_symbol_directory_completion_receipt(
        value,
        artifact_path,
        expected_kind=expected_kind,
    )
    encoded = _canonical_json_bytes(validated) + b"\n"
    _durable_absent_only_write(receipt_path, encoded)


def load_symbol_directory_completion_receipt(
    receipt_path: Path,
    artifact_path: Path,
    *,
    expected_kind: CompletionKind,
) -> dict[str, Any]:
    """Load exact files, validate their bytes, then enforce path/key binding."""

    receipt_body = _read_regular_file(
        receipt_path,
        label="completion receipt",
        limit=_MAX_RECEIPT_BYTES,
    )
    artifact_body = _read_regular_file(
        artifact_path,
        label="artifact",
        limit=_MAX_ARTIFACT_BYTES,
    )
    value = _decode_receipt_body(receipt_body)
    validated = validate_symbol_directory_completion_receipt_bytes(
        value,
        receipt_body,
        artifact_body,
        expected_kind=expected_kind,
    )
    _validate_artifact_path(validated, artifact_path)
    return validated


def validate_symbol_directory_completion_receipt(
    value: Mapping[str, Any],
    artifact_path: Path,
    *,
    expected_kind: CompletionKind | None = None,
) -> dict[str, Any]:
    """Validate a mapping against an artifact path.

    Callers that already hold stable-read bytes must use
    :func:`validate_symbol_directory_completion_receipt_bytes` so validation
    cannot race a second filesystem read.
    """

    artifact_body = _read_regular_file(
        artifact_path,
        label="artifact",
        limit=_MAX_ARTIFACT_BYTES,
    )
    normalized = _normalize_json_mapping(value)
    receipt_body = _canonical_json_bytes(normalized) + b"\n"
    validated = validate_symbol_directory_completion_receipt_bytes(
        normalized,
        receipt_body,
        artifact_body,
        expected_kind=expected_kind,
    )
    _validate_artifact_path(validated, artifact_path)
    return validated


def validate_symbol_directory_completion_receipt_bytes(
    value: Mapping[str, Any],
    receipt_body: bytes,
    artifact_body: bytes,
    *,
    expected_kind: CompletionKind | None = None,
) -> dict[str, Any]:
    """Validate the exact stable-read receipt and parquet bytes in memory.

    This function performs JSON-Schema validation plus the cross-field and
    artifact checks JSON Schema cannot express: exact bytes, ordered parquet
    schema, row count, canonical receipt serialization, monotonic clocks,
    dedupe arithmetic, unique output keys, and exact SPY diagnostic agreement.
    It never reopens a path.
    """

    if type(receipt_body) is not bytes or not receipt_body:
        raise ReceiptValidationError("receipt_body must be exact non-empty bytes")
    if len(receipt_body) > _MAX_RECEIPT_BYTES:
        raise ReceiptValidationError(
            "receipt_body exceeds the completion receipt bound"
        )
    if type(artifact_body) is not bytes or not artifact_body:
        raise ReceiptValidationError("artifact_body must be exact non-empty bytes")
    if len(artifact_body) > _MAX_ARTIFACT_BYTES:
        raise ReceiptValidationError("artifact_body exceeds the parquet artifact bound")

    normalized = _normalize_json_mapping(value)
    decoded = _decode_receipt_body(receipt_body)
    if decoded != normalized:
        raise ReceiptValidationError(
            "receipt mapping does not equal the exact supplied receipt bytes"
        )
    if receipt_body != _canonical_json_bytes(normalized) + b"\n":
        raise ReceiptValidationError(
            "completion receipt bytes are not canonical JSON with one terminal newline"
        )

    errors = sorted(
        _validator().iter_errors(normalized), key=lambda item: list(item.path)
    )
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise ReceiptValidationError(f"completion receipt schema violation: {detail}")

    kind = cast(CompletionKind, normalized["artifact"]["kind"])
    if normalized["receipt_id"] != _receipt_id(normalized):
        raise ReceiptValidationError(
            "receipt_id does not match canonical receipt content"
        )
    if expected_kind is not None and kind != expected_kind:
        raise ReceiptValidationError(
            f"completion receipt kind {kind!r} does not match {expected_kind!r}"
        )

    expected_key = _artifact_key(kind, normalized["observation_date"])
    if normalized["artifact"]["key"] != expected_key:
        raise ReceiptValidationError("artifact key is not canonical for kind/date")
    if len(artifact_body) != normalized["artifact"]["bytes"]:
        raise ReceiptValidationError("artifact byte count does not match receipt")
    if hashlib.sha256(artifact_body).hexdigest() != normalized["artifact"]["sha256"]:
        raise ReceiptValidationError("artifact SHA-256 does not match receipt")

    try:
        frame = pd.read_parquet(io.BytesIO(artifact_body))
    except Exception as exc:
        raise ReceiptValidationError(
            f"authenticated artifact is not readable parquet: {exc}"
        ) from exc
    if len(frame) != normalized["artifact"]["rows"]:
        raise ReceiptValidationError("artifact row count does not match receipt")
    actual_schema = parquet_schema(frame)
    if actual_schema != normalized["artifact"]["parquet_schema"]:
        raise ReceiptValidationError(
            "artifact ordered parquet schema does not match receipt"
        )
    if actual_schema != _EXPECTED_SCHEMA[kind]:
        raise ReceiptValidationError(
            "artifact ordered parquet schema is not the profile schema"
        )
    for column in (
        (
            "date",
            "symbol",
            "security_name",
            "exchange",
            "source",
        )
        if kind == "listing_snapshot"
        else ("ticker", "title")
    ):
        if not frame[column].map(lambda item: isinstance(item, str)).all():
            raise ReceiptValidationError(
                f"artifact logical string column contains a non-string value: {column}"
            )

    _validate_clocks(normalized)
    _validate_completeness(normalized, frame)
    _validate_artifact_semantics(normalized, frame)
    return normalized


def _validate_artifact_path(value: Mapping[str, Any], artifact_path: Path) -> None:
    expected_key = _artifact_key(
        cast(CompletionKind, value["artifact"]["kind"]),
        cast(str, value["observation_date"]),
    )
    if (
        artifact_path.name != Path(expected_key).name
        or artifact_path.parent.name != Path(expected_key).parent.name
    ):
        raise ReceiptValidationError(
            "artifact path does not match authenticated artifact key"
        )


def _source_receipt_record(
    *, source_id: str, fetched: SourceFetch[Any]
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "requested_url": fetched.requested_url,
        "response_sha256": hashlib.sha256(fetched.content).hexdigest(),
        "response_bytes": len(fetched.content),
        "response_started_at": fetched.started_at,
        "response_completed_at": fetched.completed_at,
        "response_bytes_retained": False,
    }


def _artifact_key(kind: CompletionKind, observation_date: str) -> str:
    lane = "snapshots" if kind == "listing_snapshot" else "cik_map"
    return f"{lane}/{observation_date}.parquet"


def _artifact_source_row_counts(
    kind: CompletionKind, frame: pd.DataFrame
) -> dict[str, int]:
    """Return artifact-verifiable post-dedupe row counts for each source."""

    if kind == "sec_registrant_map":
        return {SEC_TICKERS_SOURCE_ID: len(frame)}
    counts = frame["source"].value_counts().to_dict()
    return {
        NASDAQ_LISTED_SOURCE_ID: int(counts.get("nasdaqlisted", 0)),
        OTHER_LISTED_SOURCE_ID: int(counts.get("otherlisted", 0)),
    }


def _validate_clocks(value: dict[str, Any]) -> None:
    started = _parse_canonical_utc(
        value["clocks"]["collector_started_at"], field="clocks.collector_started_at"
    )
    completed = _parse_canonical_utc(
        value["clocks"]["collector_completed_at"], field="clocks.collector_completed_at"
    )
    if started > completed:
        raise ReceiptValidationError(
            "collector_started_at must not follow collector_completed_at"
        )
    if started.date().isoformat() != value["observation_date"]:
        raise ReceiptValidationError(
            "observation_date must equal collector_started_at UTC date"
        )

    for index, source in enumerate(value["sources"]):
        source_started = _parse_canonical_utc(
            source["response_started_at"], field=f"sources[{index}].response_started_at"
        )
        source_completed = _parse_canonical_utc(
            source["response_completed_at"],
            field=f"sources[{index}].response_completed_at",
        )
        if not (started <= source_started <= source_completed <= completed):
            raise ReceiptValidationError(
                f"sources[{index}] clocks must be inside the collector interval"
            )


def _validate_completeness(value: dict[str, Any], frame: pd.DataFrame) -> None:
    completeness = value["completeness"]
    source_row_counts = completeness["source_row_counts"]
    source_rows = [item["parsed_rows"] for item in source_row_counts]
    if sum(source_rows) != completeness["pre_dedupe_rows"]:
        raise ReceiptValidationError("source row counts do not sum to pre_dedupe_rows")
    if completeness["post_dedupe_rows"] != len(frame):
        raise ReceiptValidationError("post_dedupe_rows does not match artifact rows")
    if (
        completeness["pre_dedupe_rows"] - completeness["post_dedupe_rows"]
        != completeness["duplicate_occurrences"]
    ):
        raise ReceiptValidationError("duplicate occurrence arithmetic is inconsistent")
    if completeness["duplicate_key_count"] > completeness["duplicate_occurrences"]:
        raise ReceiptValidationError(
            "duplicate_key_count exceeds duplicate occurrences"
        )
    if completeness["post_dedupe_rows"] < completeness["row_floor"]:
        raise ReceiptValidationError("artifact does not satisfy the profile row floor")
    source_ids = [source["source_id"] for source in value["sources"]]
    count_ids = [item["source_id"] for item in source_row_counts]
    if source_ids != count_ids:
        raise ReceiptValidationError(
            "source_row_counts order/identity does not match sources"
        )
    kind = cast(CompletionKind, value["artifact"]["kind"])
    actual_artifact_rows = _artifact_source_row_counts(kind, frame)
    if sum(item["artifact_rows"] for item in source_row_counts) != len(frame):
        raise ReceiptValidationError(
            "source artifact row counts do not sum to post_dedupe_rows"
        )
    for item in source_row_counts:
        source_id = item["source_id"]
        if item["minimum_artifact_rows"] != _SOURCE_ARTIFACT_ROW_FLOORS[source_id]:
            raise ReceiptValidationError(
                f"source artifact row floor is not canonical: {source_id}"
            )
        if item["artifact_rows"] != actual_artifact_rows[source_id]:
            raise ReceiptValidationError(
                f"source artifact row count does not match parquet: {source_id}"
            )
        if item["parsed_rows"] < item["artifact_rows"]:
            raise ReceiptValidationError(
                f"parsed source rows are below artifact rows: {source_id}"
            )
        if item["artifact_rows"] < item["minimum_artifact_rows"]:
            raise ReceiptValidationError(
                f"source artifact rows do not satisfy completeness floor: {source_id}"
            )


def _validate_artifact_semantics(value: dict[str, Any], frame: pd.DataFrame) -> None:
    diagnostics = value["diagnostics"]
    occurrences = diagnostics["pre_dedupe_spy_occurrences"]
    if diagnostics["pre_dedupe_spy_occurrence_count"] != len(occurrences):
        raise ReceiptValidationError(
            "SPY occurrence count does not match diagnostic rows"
        )
    if frame.isna().any(axis=None):
        raise ReceiptValidationError("authenticated artifact contains null values")

    if value["artifact"]["kind"] == "listing_snapshot":
        if frame["symbol"].duplicated().any():
            raise ReceiptValidationError("listing artifact contains duplicate symbols")
        if not frame["date"].map(str).eq(value["observation_date"]).all():
            raise ReceiptValidationError(
                "listing artifact date column is not the observation date"
            )
        if not set(frame["source"].map(str)).issubset({"nasdaqlisted", "otherlisted"}):
            raise ReceiptValidationError(
                "listing artifact contains an unknown source label"
            )
        spy = frame[frame["symbol"] == "SPY"]
        if len(spy) != 1:
            raise ReceiptValidationError(
                "operational listing receipt requires exactly one artifact SPY row"
            )
        if len(occurrences) != 1:
            raise ReceiptValidationError(
                "listing artifact contains SPY but its pre-dedupe diagnostic is absent"
            )
        row = spy.iloc[0]
        occurrence = occurrences[0]
        expected = {
            "source_id": (
                NASDAQ_LISTED_SOURCE_ID
                if row["source"] == "nasdaqlisted"
                else OTHER_LISTED_SOURCE_ID
            ),
            "symbol": str(row["symbol"]),
            "security_name": str(row["security_name"]),
            "exchange": str(row["exchange"]),
            "etf": bool(row["etf"]),
            "test_issue": bool(row["test_issue"]),
            "is_preferred": bool(row["is_preferred"]),
        }
        if occurrence != expected:
            raise ReceiptValidationError(
                "listing SPY diagnostic does not match artifact SPY row"
            )
        return

    if frame["ticker"].duplicated().any():
        raise ReceiptValidationError("registrant artifact contains duplicate tickers")
    spy = frame[frame["ticker"] == "SPY"]
    if len(spy) != 1:
        raise ReceiptValidationError(
            "registrant artifact must contain exactly one SPY row"
        )
    row = spy.iloc[0]
    expected = {
        "source_id": SEC_TICKERS_SOURCE_ID,
        "ticker": str(row["ticker"]),
        "cik": int(row["cik"]),
        "title": str(row["title"]),
    }
    if occurrences[0] != expected:
        raise ReceiptValidationError(
            "registrant SPY diagnostic does not match artifact SPY row"
        )


def _read_regular_file(path: Path, *, label: str, limit: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ReceiptValidationError(f"{label} is not a regular file: {path}")
    try:
        if path.stat().st_size > limit:
            raise ReceiptValidationError(f"{label} exceeds its byte bound")
        body = path.read_bytes()
    except ReceiptValidationError:
        raise
    except OSError as exc:
        raise ReceiptValidationError(f"could not read {label}: {exc}") from exc
    if not body:
        raise ReceiptValidationError(f"{label} is empty")
    if len(body) > limit:
        raise ReceiptValidationError(f"{label} exceeds its byte bound")
    return body


def _decode_receipt_body(receipt_body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(receipt_body, object_pairs_hook=_unique_object)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ReceiptValidationError,
    ) as exc:
        if isinstance(exc, ReceiptValidationError):
            raise
        raise ReceiptValidationError(
            f"could not decode completion receipt bytes: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ReceiptValidationError("completion receipt root must be an object")
    return value


def _normalize_json_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        normalized = json.loads(encoded, object_pairs_hook=_unique_object)
    except (TypeError, ValueError, ReceiptValidationError) as exc:
        if isinstance(exc, ReceiptValidationError):
            raise
        raise ReceiptValidationError(
            f"completion receipt is not strict JSON: {exc}"
        ) from exc
    if not isinstance(normalized, dict):
        raise ReceiptValidationError("completion receipt root must be an object")
    return normalized


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise ReceiptValidationError(f"duplicate JSON field: {key}")
        result[key] = item
    return result


def _parse_canonical_utc(value: str, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ReceiptValidationError(f"{field} must be a canonical UTC string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise ReceiptValidationError(f"{field} is not canonical UTC") from exc
    canonical = parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if canonical != value:
        raise ReceiptValidationError(f"{field} is not canonical UTC")
    return parsed


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _receipt_id(value: Mapping[str, Any]) -> str:
    basis = dict(value)
    basis["receipt_id"] = ""
    return f"sdreceipt_{hashlib.sha256(_canonical_json_bytes(basis)).hexdigest()}"


def _durable_absent_only_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise ReceiptValidationError(
                f"completion receipt already exists; refusing to overwrite: {path}"
            ) from None
        temporary.unlink()
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema_path = (
        Path(__file__).resolve().parent.parent
        / "contracts"
        / "symbol_directory"
        / "symbol_directory_completion_receipt.v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())
