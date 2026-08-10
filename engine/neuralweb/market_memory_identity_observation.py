"""Bounded SPY listing observations for the private Market Memory identity lane.

This module is deliberately not a historical security master.  It projects one
exact symbol-directory snapshot into either ``present_in_snapshot`` or
``symbol_absent_from_complete_snapshot`` for the already-configured SPY canary.
It never infers continuity, a delisting, a rename, a corporate action, or a SEC
registrant binding.

Legacy repository snapshots have no contemporaneous completion receipt and are
therefore reconstruction evidence only.  A strictly validated receipt created
after the W1B.2 cutoff can establish a go-forward operational observation, but
its filename, partition date, collector start time, and filesystem metadata can
never backdate Market Memory availability.  ``available_at`` and ``observed_at``
are sampled once, after the receipt/artifact/receipt stable-read boundary.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

from engine.neuralweb import market_memory, market_memory_identity

LISTING_OBJECT_SCHEMA = "market_memory.spy_listing_object.v1"
LISTING_OBSERVATION_SCHEMA = "market_memory.spy_listing_observation.v1"
OPERATIONAL_RECEIPT_CUTOFF = date(2026, 8, 10)

_MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
_MAX_RECEIPT_BYTES = 512 * 1024
_MAX_LISTING_OBJECT_BYTES = 64 * 1024
_MAX_OBSERVATION_BYTES = 256 * 1024
_MIN_COMPLETE_ROWS = 8_000
_MAX_SNAPSHOT_ROWS = 30_000
_EXPECTED_COLUMNS = (
    "date",
    "symbol",
    "security_name",
    "exchange",
    "etf",
    "test_issue",
    "is_preferred",
    "source",
)
_BOOLEAN_COLUMNS = frozenset({"etf", "test_issue", "is_preferred"})
_TEXT_COLUMNS = frozenset(_EXPECTED_COLUMNS) - _BOOLEAN_COLUMNS
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_RECEIPT_ID = re.compile(r"sdreceipt_[a-f0-9]{64}\Z")
_OBJECT_ID = re.compile(r"mmidobj_[a-f0-9]{64}\Z")
_OBSERVATION_ID = re.compile(r"mmidobs_[a-f0-9]{64}\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")

_FROZEN_SUBJECT = {
    "subject_id": (
        "mmsecurity_5fc37e8db34f74314b654c910ea8bacfa7de8b5d2d067f2e5421c9d5745ceb4c"
    ),
    "instrument_id": (
        "mmsecurity_6f361f5bad9f06a3b2ff157585d5728f55f77198420959aadd8922d1045c3fea"
    ),
    "identity_version": (
        "mmidentityv_65ec5e55473e953b55fa2d146f40e8b56dfae2e68a3df7423405db1034d16903"
    ),
}
_SEMANTIC_LIMITS = {
    "historical_identity_resolution": False,
    "listing_continuity": False,
    "delisting": False,
    "rename": False,
    "corporate_action": False,
    "sec_registrant_binding": False,
}
_OBJECT_EVIDENCE_POLICY = {
    "actual_output_only": True,
    "identity_claim": "local_canary_anchor_only",
    "historical_resolver": False,
    "training_eligible": False,
    "promotion_eligible": False,
    "role": "context_only",
}

_OBJECT_FIELDS = frozenset(
    {
        "schema",
        "listing_object_id",
        "subject",
        "symbol",
        "state",
        "listing",
        "semantic_limits",
        "evidence_policy",
        "authority",
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "schema",
        "source_observation_id",
        "listing_object_id",
        "subject",
        "date_partition",
        "partition_bounds",
        "listing_state",
        "source_artifact",
        "completion_receipt",
        "pit_basis",
        "operational",
        "measurement_time",
        "available_at",
        "observed_at",
        "evidence_policy",
        "authority",
    }
)
_SOURCE_ARTIFACT_FIELDS = frozenset(
    {"kind", "sha256", "bytes", "rows", "parquet_columns"}
)
_COMPLETION_REFERENCE_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "receipt_id",
        "sha256",
        "bytes",
        "collector_started_at",
        "collector_completed_at",
    }
)


class MarketMemoryIdentityObservationError(ValueError):
    """A source snapshot cannot support the bounded SPY observation contract."""


class SnapshotMissing(MarketMemoryIdentityObservationError):
    """The exact requested partition is missing, which is not an observation."""

    status = "snapshot_missing"


@dataclass(frozen=True)
class SpyListingObservation:
    """Detached exact source bytes plus their label-free SPY projection."""

    snapshot_path: Path
    snapshot_bytes: bytes
    listing_object: dict[str, Any]
    listing_object_bytes: bytes
    observation: dict[str, Any]
    observation_bytes: bytes
    completion_receipt: dict[str, Any] | None
    completion_receipt_bytes: bytes | None

    def detached(self) -> SpyListingObservation:
        """Return a deep copy so callers cannot mutate validated evidence."""

        return copy.deepcopy(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryIdentityObservationError(
            "identity observation must be finite canonical JSON"
        ) from exc


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _require_exact_bytes(value: object, *, field: str, limit: int) -> bytes:
    if type(value) is not bytes:
        raise MarketMemoryIdentityObservationError(
            f"{field} must be exact immutable bytes"
        )
    if not value or len(value) > limit:
        raise MarketMemoryIdentityObservationError(
            f"{field} is empty or exceeds its byte bound"
        )
    return value


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + _sha256(_canonical_bytes(core))


def _source_observation_id(value: Mapping[str, Any]) -> str:
    """Identify the upstream occurrence, not a retry's local read clock."""

    core = copy.deepcopy(dict(value))
    core["source_observation_id"] = ""
    core["available_at"] = ""
    core["observed_at"] = ""
    return "mmidobs_" + _sha256(_canonical_bytes(core))


def _format_utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MarketMemoryIdentityObservationError("observation clock must be UTC")
    if value.utcoffset() != timedelta(0) or value.year >= 9999:
        raise MarketMemoryIdentityObservationError("observation clock must be UTC")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_utc(value: object, *, field: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise MarketMemoryIdentityObservationError(
            f"{field} must be a canonical microsecond UTC timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise MarketMemoryIdentityObservationError(
            f"{field} is not a valid UTC timestamp"
        ) from exc
    if _format_utc(parsed) != value:
        raise MarketMemoryIdentityObservationError(f"{field} is not canonical UTC")
    return parsed, value


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON token {value}")


def _strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise MarketMemoryIdentityObservationError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise MarketMemoryIdentityObservationError(f"{label} must be a JSON object")
    return value


def _stable_read(
    path: Path, *, limit: int, label: str, missing_is_snapshot: bool = False
) -> bytes:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        if missing_is_snapshot:
            raise SnapshotMissing(f"{label} is missing") from exc
        raise MarketMemoryIdentityObservationError(f"{label} is missing") from exc
    except OSError as exc:
        raise MarketMemoryIdentityObservationError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MarketMemoryIdentityObservationError(
            f"{label} must be a regular non-symlink file"
        )
    if metadata.st_size <= 0 or metadata.st_size > limit:
        raise MarketMemoryIdentityObservationError(
            f"{label} is empty or exceeds its byte bound"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryIdentityObservationError(
            f"{label} could not be opened safely"
        ) from exc
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise MarketMemoryIdentityObservationError(
            f"{label} could not be read"
        ) from exc
    finally:
        os.close(descriptor)
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or len(body) != after.st_size
        or len(body) > limit
    ):
        raise MarketMemoryIdentityObservationError(
            f"{label} changed during its stable read"
        )
    return body


def _partition_from_path(path: Path) -> date:
    if path.suffix != ".parquet" or path.name != f"{path.stem}.parquet":
        raise MarketMemoryIdentityObservationError(
            "snapshot name must be exactly YYYY-MM-DD.parquet"
        )
    try:
        parsed = date.fromisoformat(path.stem)
    except ValueError as exc:
        raise MarketMemoryIdentityObservationError(
            "snapshot name must be exactly YYYY-MM-DD.parquet"
        ) from exc
    if parsed.isoformat() != path.stem:
        raise MarketMemoryIdentityObservationError(
            "snapshot name must be exactly YYYY-MM-DD.parquet"
        )
    return parsed


def infer_listing_completion_receipt_path(snapshot_path: str | Path) -> Path:
    """Return the sole receipt path allowed for one snapshot partition."""

    snapshot = Path(snapshot_path)
    _partition_from_path(snapshot)
    if snapshot.parent.name != "snapshots":
        raise MarketMemoryIdentityObservationError(
            "listing snapshot must live under a snapshots directory"
        )
    return snapshot.parent.parent / "receipts" / "snapshots" / f"{snapshot.stem}.json"


def _load_anchor(config_path: Path) -> dict[str, str]:
    try:
        raw, _body = market_memory_identity._read_config(config_path)
        config = market_memory_identity._validate_config(raw)
    except market_memory_identity.MarketMemoryIdentityError as exc:
        raise MarketMemoryIdentityObservationError(
            "W1B.1 canary identity anchor is unavailable or drifted"
        ) from exc
    subject = config["subject"]
    anchor = {
        "subject_id": subject["subject_id"],
        "instrument_id": subject["instrument_id"],
        "identity_version": subject["identity_version"],
    }
    if (
        anchor != _FROZEN_SUBJECT
        or config.get("symbol") != "SPY"
        or subject.get("mic") != "ARCX"
        or subject.get("currency") != "USD"
    ):
        raise MarketMemoryIdentityObservationError(
            "W1B.1 SPY/ARCX/USD identity anchor drifted"
        )
    return anchor


def _validate_text(value: object, *, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > maximum
        or "\x00" in value
    ):
        raise MarketMemoryIdentityObservationError(
            f"snapshot {field} is not bounded exact text"
        )
    return value


def _project_snapshot(
    body: bytes, *, partition: date
) -> tuple[dict[str, Any] | None, int]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        parquet = pq.ParquetFile(io.BytesIO(body))
        metadata = parquet.metadata
        if metadata is None:
            raise ValueError("missing parquet metadata")
        if not _MIN_COMPLETE_ROWS <= metadata.num_rows <= _MAX_SNAPSHOT_ROWS:
            raise ValueError("row count is outside the complete-snapshot bound")
        if metadata.num_row_groups <= 0 or metadata.num_row_groups > 256:
            raise ValueError("row-group count is outside its bound")
        schema = parquet.schema_arrow
        if tuple(schema.names) != _EXPECTED_COLUMNS:
            raise ValueError("column names or order drifted")
        for field in schema:
            if field.name in _BOOLEAN_COLUMNS:
                if not pa.types.is_boolean(field.type):
                    raise ValueError(f"{field.name} is not physical boolean")
            elif field.name in _TEXT_COLUMNS and not (
                pa.types.is_string(field.type) or pa.types.is_large_string(field.type)
            ):
                raise ValueError(f"{field.name} is not physical UTF-8 text")
        table = parquet.read()
    except Exception as exc:
        raise MarketMemoryIdentityObservationError(
            "snapshot is not a bounded canonical symbol-directory parquet"
        ) from exc
    if table.num_rows != metadata.num_rows:
        raise MarketMemoryIdentityObservationError(
            "snapshot row count differs from its parquet metadata"
        )
    expected_date = partition.isoformat()
    decoded: dict[str, list[Any]] = {}
    try:
        for field in _EXPECTED_COLUMNS:
            column = table.column(field)
            if column.null_count:
                raise MarketMemoryIdentityObservationError(
                    f"snapshot {field} contains null values"
                )
            values = column.to_pylist()
            if field in _TEXT_COLUMNS:
                maximum = 1_024 if field == "security_name" else 128
                for row_number, value in enumerate(values):
                    _validate_text(
                        value,
                        field=f"row {row_number} {field}",
                        maximum=maximum,
                    )
            elif not all(type(value) is bool for value in values):
                raise MarketMemoryIdentityObservationError(
                    f"snapshot {field} contains a non-boolean value"
                )
            decoded[field] = values
    except MarketMemoryIdentityObservationError:
        raise
    except Exception as exc:
        raise MarketMemoryIdentityObservationError(
            "snapshot rows could not be decoded"
        ) from exc
    if any(value != expected_date for value in decoded["date"]):
        raise MarketMemoryIdentityObservationError(
            "snapshot row date differs from its date partition"
        )
    symbols = decoded["symbol"]
    if len(symbols) != len(set(symbols)):
        raise MarketMemoryIdentityObservationError(
            "snapshot contains duplicate post-dedupe symbols"
        )
    spy_indexes = [index for index, symbol in enumerate(symbols) if symbol == "SPY"]
    if len(spy_indexes) > 1:
        raise MarketMemoryIdentityObservationError(
            "snapshot contains more than one pre-consumer SPY row"
        )
    spy_row = (
        {field: decoded[field][spy_indexes[0]] for field in _EXPECTED_COLUMNS}
        if spy_indexes
        else None
    )
    return spy_row, table.num_rows


def _listing_object(
    *, anchor: Mapping[str, str], row: Mapping[str, Any] | None
) -> dict[str, Any]:
    if row is None:
        state = "symbol_absent_from_complete_snapshot"
        listing = None
    else:
        if (
            row.get("symbol") != "SPY"
            or row.get("source") != "otherlisted"
            or row.get("exchange") != "P"
            or row.get("etf") is not True
            or row.get("test_issue") is not False
            or row.get("is_preferred") is not False
        ):
            raise MarketMemoryIdentityObservationError(
                "SPY listing row drifted from the frozen otherlisted/P/ETF anchor"
            )
        state = "present_in_snapshot"
        listing = {
            "security_name": row["security_name"],
            "source": "otherlisted",
            "raw_exchange_code": "P",
            "mic": "ARCX",
            "currency": "USD",
            "etf": True,
            "test_issue": False,
            "is_preferred": False,
        }
    value: dict[str, Any] = {
        "schema": LISTING_OBJECT_SCHEMA,
        "listing_object_id": "",
        "subject": dict(anchor),
        "symbol": "SPY",
        "state": state,
        "listing": listing,
        "semantic_limits": copy.deepcopy(_SEMANTIC_LIMITS),
        "evidence_policy": copy.deepcopy(_OBJECT_EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    value["listing_object_id"] = _content_id(
        "mmidobj_", value, field="listing_object_id"
    )
    return value


def _validate_completion_receipt_payload(
    value: Mapping[str, Any],
    body: bytes,
    *,
    partition: date,
    artifact: bytes,
    rows: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = copy.deepcopy(dict(value))
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not _RECEIPT_ID.fullmatch(receipt_id):
        raise MarketMemoryIdentityObservationError("completion receipt_id is malformed")
    core = copy.deepcopy(receipt)
    core["receipt_id"] = ""
    expected_receipt_id = "sdreceipt_" + _sha256(_canonical_bytes(core))
    if receipt_id != expected_receipt_id:
        raise MarketMemoryIdentityObservationError(
            "completion receipt_id does not bind its canonical payload"
        )
    artifact_ref = receipt.get("artifact")
    clocks = receipt.get("clocks")
    if not isinstance(artifact_ref, Mapping) or not isinstance(clocks, Mapping):
        raise MarketMemoryIdentityObservationError(
            "completion receipt artifact or clocks are malformed"
        )
    if (
        receipt.get("observation_date") != partition.isoformat()
        or artifact_ref.get("kind") != "listing_snapshot"
        or artifact_ref.get("sha256") != _sha256(artifact)
        or artifact_ref.get("bytes") != len(artifact)
        or artifact_ref.get("rows") != rows
    ):
        raise MarketMemoryIdentityObservationError(
            "completion receipt does not bind the exact snapshot partition"
        )
    if partition <= OPERATIONAL_RECEIPT_CUTOFF:
        raise MarketMemoryIdentityObservationError(
            "receipt at or before the W1B.2 cutoff cannot upgrade a legacy snapshot"
        )
    started_dt, started = _parse_utc(
        clocks.get("collector_started_at"), field="collector_started_at"
    )
    completed_dt, completed = _parse_utc(
        clocks.get("collector_completed_at"), field="collector_completed_at"
    )
    if completed_dt < started_dt:
        raise MarketMemoryIdentityObservationError(
            "completion receipt finishes before collection starts"
        )
    reference = {
        "schema": receipt.get("schema"),
        "profile": receipt.get("profile"),
        "receipt_id": receipt_id,
        "sha256": _sha256(body),
        "bytes": len(body),
        "collector_started_at": started,
        "collector_completed_at": completed,
    }
    if not all(
        isinstance(reference[field], str) and reference[field]
        for field in ("schema", "profile")
    ):
        raise MarketMemoryIdentityObservationError(
            "completion receipt schema or profile is malformed"
        )
    return receipt, reference


def _partition_bounds(partition: date) -> dict[str, str]:
    lower = datetime.combine(partition, time.min, tzinfo=timezone.utc)
    upper = lower + timedelta(days=1)
    return {
        "precision": "date_partition",
        "lower_bound": _format_utc(lower),
        "upper_bound_exclusive": _format_utc(upper),
    }


def _observation_policy(*, operational: bool) -> dict[str, Any]:
    return {
        "actual_output_only": True,
        "source_artifact_bytes_bound": True,
        "completion_receipt_authenticated": operational,
        "historical_resolver": False,
        "training_eligible": False,
        "promotion_eligible": False,
        "role": "context_only",
    }


def build_spy_listing_observation(
    snapshot_path: str | Path,
    *,
    completion_receipt_path: str | Path | None = None,
    config_path: str | Path = market_memory_identity.DEFAULT_CONFIG_PATH,
) -> SpyListingObservation:
    """Read and project one exact SPY listing snapshot.

    Omitting ``completion_receipt_path`` means "use the sole inferred sidecar if
    it exists", not "ignore receipts".  A present malformed, partial, orphaned,
    or legacy-cutoff sidecar is fatal and can never silently downgrade to
    reconstruction evidence.
    """

    snapshot = Path(snapshot_path)
    partition = _partition_from_path(snapshot)
    inferred_receipt = infer_listing_completion_receipt_path(snapshot)
    explicit_receipt = completion_receipt_path is not None
    receipt_path = (
        Path(completion_receipt_path)
        if completion_receipt_path is not None
        else inferred_receipt
    )
    if explicit_receipt and os.path.abspath(receipt_path) != os.path.abspath(
        inferred_receipt
    ):
        raise MarketMemoryIdentityObservationError(
            "completion receipt path is not the snapshot's canonical sidecar"
        )

    receipt_present = receipt_path.exists() or receipt_path.is_symlink()
    if explicit_receipt and not receipt_present:
        raise MarketMemoryIdentityObservationError(
            "explicit completion receipt is missing"
        )

    receipt_body: bytes | None = None
    receipt: dict[str, Any] | None = None
    receipt_reference: dict[str, Any] | None = None
    if receipt_present:
        receipt_before = _stable_read(
            receipt_path, limit=_MAX_RECEIPT_BYTES, label="completion receipt"
        )
        snapshot_body = _stable_read(
            snapshot,
            limit=_MAX_SNAPSHOT_BYTES,
            label="symbol-directory snapshot",
            missing_is_snapshot=True,
        )
        row, rows = _project_snapshot(snapshot_body, partition=partition)
        try:
            from lib.symbol_directory_receipts import (
                load_symbol_directory_completion_receipt,
            )

            loaded = load_symbol_directory_completion_receipt(
                receipt_path,
                snapshot,
                expected_kind="listing_snapshot",
            )
        except Exception as exc:
            raise MarketMemoryIdentityObservationError(
                "completion receipt failed strict source validation"
            ) from exc
        receipt_after = _stable_read(
            receipt_path, limit=_MAX_RECEIPT_BYTES, label="completion receipt"
        )
        snapshot_after = _stable_read(
            snapshot,
            limit=_MAX_SNAPSHOT_BYTES,
            label="symbol-directory snapshot",
            missing_is_snapshot=True,
        )
        if receipt_before != receipt_after or snapshot_body != snapshot_after:
            raise MarketMemoryIdentityObservationError(
                "receipt or snapshot changed across the receipt-artifact-receipt boundary"
            )
        raw_receipt = _strict_json_object(receipt_before, label="completion receipt")
        if not isinstance(loaded, Mapping) or dict(loaded) != raw_receipt:
            raise MarketMemoryIdentityObservationError(
                "completion receipt loader changed the exact payload"
            )
        receipt, receipt_reference = _validate_completion_receipt_payload(
            raw_receipt,
            receipt_before,
            partition=partition,
            artifact=snapshot_body,
            rows=rows,
        )
        receipt_body = receipt_before
    else:
        snapshot_body = _stable_read(
            snapshot,
            limit=_MAX_SNAPSHOT_BYTES,
            label="symbol-directory snapshot",
            missing_is_snapshot=True,
        )
        row, rows = _project_snapshot(snapshot_body, partition=partition)
        if receipt_path.exists() or receipt_path.is_symlink():
            raise MarketMemoryIdentityObservationError(
                "completion receipt appeared during an unreceipted read; retry"
            )

    anchor = _load_anchor(Path(config_path))
    listing_object = _listing_object(anchor=anchor, row=row)
    listing_object_body = _canonical_bytes(listing_object)
    observed_dt = _utc_now()
    observed_at = _format_utc(observed_dt)
    operational = receipt_reference is not None
    measurement_time: str | None = None
    if receipt_reference is not None:
        completed_dt, measurement_time = _parse_utc(
            receipt_reference["collector_completed_at"],
            field="collector_completed_at",
        )
        if observed_dt < completed_dt:
            raise MarketMemoryIdentityObservationError(
                "Market Memory observed the snapshot before collector completion"
            )
    source_artifact = {
        "kind": "listing_snapshot",
        "sha256": _sha256(snapshot_body),
        "bytes": len(snapshot_body),
        "rows": rows,
        "parquet_columns": list(_EXPECTED_COLUMNS),
    }
    observation: dict[str, Any] = {
        "schema": LISTING_OBSERVATION_SCHEMA,
        "source_observation_id": "",
        "listing_object_id": listing_object["listing_object_id"],
        "subject": dict(anchor),
        "date_partition": partition.isoformat(),
        "partition_bounds": _partition_bounds(partition),
        "listing_state": listing_object["state"],
        "source_artifact": source_artifact,
        "completion_receipt": receipt_reference,
        "pit_basis": "live_captured" if operational else "public_reconstruction",
        "operational": operational,
        "measurement_time": measurement_time,
        "available_at": observed_at,
        "observed_at": observed_at,
        "evidence_policy": _observation_policy(operational=operational),
        "authority": dict(market_memory.AUTHORITY),
    }
    observation["source_observation_id"] = _source_observation_id(observation)
    bundle = SpyListingObservation(
        snapshot_path=snapshot,
        snapshot_bytes=snapshot_body,
        listing_object=listing_object,
        listing_object_bytes=listing_object_body,
        observation=observation,
        observation_bytes=_canonical_bytes(observation),
        completion_receipt=receipt,
        completion_receipt_bytes=receipt_body,
    )
    return validate_spy_listing_observation(bundle)


def _validate_listing_object(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OBJECT_FIELDS:
        raise MarketMemoryIdentityObservationError(
            "listing object fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    object_id = clean.get("listing_object_id")
    if clean.get("schema") != LISTING_OBJECT_SCHEMA:
        raise MarketMemoryIdentityObservationError("listing object schema drift")
    if not isinstance(object_id, str) or not _OBJECT_ID.fullmatch(object_id):
        raise MarketMemoryIdentityObservationError("listing_object_id is malformed")
    if _content_id("mmidobj_", clean, field="listing_object_id") != object_id:
        raise MarketMemoryIdentityObservationError(
            "listing_object_id does not bind semantic content"
        )
    if clean.get("subject") != _FROZEN_SUBJECT or clean.get("symbol") != "SPY":
        raise MarketMemoryIdentityObservationError("listing object anchor drift")
    state = clean.get("state")
    listing = clean.get("listing")
    if state == "symbol_absent_from_complete_snapshot":
        if listing is not None:
            raise MarketMemoryIdentityObservationError(
                "absent listing object must not carry a listing"
            )
    elif state == "present_in_snapshot":
        expected_listing_fields = {
            "security_name",
            "source",
            "raw_exchange_code",
            "mic",
            "currency",
            "etf",
            "test_issue",
            "is_preferred",
        }
        if not isinstance(listing, Mapping) or set(listing) != expected_listing_fields:
            raise MarketMemoryIdentityObservationError(
                "present listing fields are not canonical"
            )
        if (
            listing.get("source") != "otherlisted"
            or listing.get("raw_exchange_code") != "P"
            or listing.get("mic") != "ARCX"
            or listing.get("currency") != "USD"
            or listing.get("etf") is not True
            or listing.get("test_issue") is not False
            or listing.get("is_preferred") is not False
        ):
            raise MarketMemoryIdentityObservationError("listing anchor drift")
        _validate_text(
            listing.get("security_name"), field="listing security_name", maximum=1_024
        )
    else:
        raise MarketMemoryIdentityObservationError("listing state is unsupported")
    if clean.get("semantic_limits") != _SEMANTIC_LIMITS:
        raise MarketMemoryIdentityObservationError("semantic limits drift")
    if clean.get("evidence_policy") != _OBJECT_EVIDENCE_POLICY:
        raise MarketMemoryIdentityObservationError("listing evidence policy drift")
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise MarketMemoryIdentityObservationError("listing authority drift")
    return clean


def _validate_observation(
    value: Mapping[str, Any],
    *,
    listing_object: Mapping[str, Any],
    snapshot_body: bytes,
    rows: int,
    completion_receipt: Mapping[str, Any] | None,
    completion_receipt_body: bytes | None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_FIELDS:
        raise MarketMemoryIdentityObservationError(
            "listing observation fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    observation_id = clean.get("source_observation_id")
    if clean.get("schema") != LISTING_OBSERVATION_SCHEMA:
        raise MarketMemoryIdentityObservationError("listing observation schema drift")
    if not isinstance(observation_id, str) or not _OBSERVATION_ID.fullmatch(
        observation_id
    ):
        raise MarketMemoryIdentityObservationError("source_observation_id is malformed")
    if _source_observation_id(clean) != observation_id:
        raise MarketMemoryIdentityObservationError(
            "source_observation_id does not bind its upstream occurrence"
        )
    if (
        clean.get("listing_object_id") != listing_object["listing_object_id"]
        or clean.get("subject") != _FROZEN_SUBJECT
        or clean.get("listing_state") != listing_object["state"]
    ):
        raise MarketMemoryIdentityObservationError(
            "observation differs from its listing object"
        )
    partition_value = clean.get("date_partition")
    if not isinstance(partition_value, str):
        raise MarketMemoryIdentityObservationError("date_partition is malformed")
    try:
        partition = date.fromisoformat(partition_value)
    except ValueError as exc:
        raise MarketMemoryIdentityObservationError(
            "date_partition is malformed"
        ) from exc
    if partition.isoformat() != partition_value:
        raise MarketMemoryIdentityObservationError("date_partition is not canonical")
    if clean.get("partition_bounds") != _partition_bounds(partition):
        raise MarketMemoryIdentityObservationError("date partition bounds drift")
    source = clean.get("source_artifact")
    expected_source = {
        "kind": "listing_snapshot",
        "sha256": _sha256(snapshot_body),
        "bytes": len(snapshot_body),
        "rows": rows,
        "parquet_columns": list(_EXPECTED_COLUMNS),
    }
    if (
        not isinstance(source, Mapping)
        or set(source) != _SOURCE_ARTIFACT_FIELDS
        or dict(source) != expected_source
    ):
        raise MarketMemoryIdentityObservationError(
            "observation does not bind exact snapshot bytes"
        )
    observed_dt, observed = _parse_utc(clean.get("observed_at"), field="observed_at")
    available_dt, available = _parse_utc(
        clean.get("available_at"), field="available_at"
    )
    if available != observed or available_dt != observed_dt:
        raise MarketMemoryIdentityObservationError(
            "available_at and observed_at must share the post-read process clock"
        )
    operational = clean.get("operational")
    if type(operational) is not bool:
        raise MarketMemoryIdentityObservationError("operational must be boolean")
    expected_policy = _observation_policy(operational=operational)
    if clean.get("evidence_policy") != expected_policy:
        raise MarketMemoryIdentityObservationError("observation evidence policy drift")
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise MarketMemoryIdentityObservationError("observation authority drift")

    reference = clean.get("completion_receipt")
    if completion_receipt is None or completion_receipt_body is None:
        if completion_receipt is not None or completion_receipt_body is not None:
            raise MarketMemoryIdentityObservationError(
                "completion receipt payload and bytes must be paired"
            )
        if (
            reference is not None
            or clean.get("pit_basis") != "public_reconstruction"
            or operational is not False
            or clean.get("measurement_time") is not None
        ):
            raise MarketMemoryIdentityObservationError(
                "unreceipted snapshot cannot claim operational availability"
            )
    else:
        if (
            not isinstance(reference, Mapping)
            or set(reference) != _COMPLETION_REFERENCE_FIELDS
        ):
            raise MarketMemoryIdentityObservationError(
                "completion receipt reference fields are not canonical"
            )
        try:
            from lib.symbol_directory_receipts import (
                validate_symbol_directory_completion_receipt_bytes,
            )

            full_receipt = validate_symbol_directory_completion_receipt_bytes(
                completion_receipt,
                completion_receipt_body,
                snapshot_body,
                expected_kind="listing_snapshot",
            )
        except Exception as exc:
            raise MarketMemoryIdentityObservationError(
                "completion receipt fails full exact-byte source validation"
            ) from exc
        if full_receipt != dict(completion_receipt):
            raise MarketMemoryIdentityObservationError(
                "completion receipt validator changed the exact payload"
            )
        validated_receipt, expected_reference = _validate_completion_receipt_payload(
            completion_receipt,
            completion_receipt_body,
            partition=partition,
            artifact=snapshot_body,
            rows=rows,
        )
        if (
            validated_receipt != dict(completion_receipt)
            or dict(reference) != expected_reference
        ):
            raise MarketMemoryIdentityObservationError(
                "completion receipt reference differs from exact receipt bytes"
            )
        completed_dt, completed = _parse_utc(
            expected_reference["collector_completed_at"],
            field="collector_completed_at",
        )
        if (
            clean.get("pit_basis") != "live_captured"
            or operational is not True
            or clean.get("measurement_time") != completed
            or observed_dt < completed_dt
        ):
            raise MarketMemoryIdentityObservationError(
                "receipt-backed observation has impossible availability clocks"
            )
    return clean


def validate_spy_listing_observation(
    bundle: SpyListingObservation,
) -> SpyListingObservation:
    """Recompute every semantic ID, source binding, clock, and exact byte link."""

    if not isinstance(bundle, SpyListingObservation):
        raise MarketMemoryIdentityObservationError(
            "SPY listing observation bundle type is invalid"
        )
    _require_exact_bytes(
        bundle.snapshot_bytes,
        field="snapshot_bytes",
        limit=_MAX_SNAPSHOT_BYTES,
    )
    _require_exact_bytes(
        bundle.listing_object_bytes,
        field="listing_object_bytes",
        limit=_MAX_LISTING_OBJECT_BYTES,
    )
    _require_exact_bytes(
        bundle.observation_bytes,
        field="observation_bytes",
        limit=_MAX_OBSERVATION_BYTES,
    )
    if bundle.completion_receipt_bytes is not None:
        _require_exact_bytes(
            bundle.completion_receipt_bytes,
            field="completion_receipt_bytes",
            limit=_MAX_RECEIPT_BYTES,
        )
    partition = _partition_from_path(bundle.snapshot_path)
    row, rows = _project_snapshot(bundle.snapshot_bytes, partition=partition)
    listing = _validate_listing_object(bundle.listing_object)
    if _canonical_bytes(listing) != bundle.listing_object_bytes:
        raise MarketMemoryIdentityObservationError(
            "listing object bytes differ from canonical content"
        )
    expected_listing = _listing_object(anchor=_FROZEN_SUBJECT, row=row)
    if listing != expected_listing:
        raise MarketMemoryIdentityObservationError(
            "listing object differs from exact snapshot output"
        )
    observation = _validate_observation(
        bundle.observation,
        listing_object=listing,
        snapshot_body=bundle.snapshot_bytes,
        rows=rows,
        completion_receipt=bundle.completion_receipt,
        completion_receipt_body=bundle.completion_receipt_bytes,
    )
    if observation["date_partition"] != partition.isoformat():
        raise MarketMemoryIdentityObservationError(
            "observation partition differs from snapshot key"
        )
    if _canonical_bytes(observation) != bundle.observation_bytes:
        raise MarketMemoryIdentityObservationError(
            "listing observation bytes differ from canonical content"
        )
    return bundle.detached()


__all__ = [
    "LISTING_OBJECT_SCHEMA",
    "LISTING_OBSERVATION_SCHEMA",
    "OPERATIONAL_RECEIPT_CUTOFF",
    "MarketMemoryIdentityObservationError",
    "SnapshotMissing",
    "SpyListingObservation",
    "build_spy_listing_observation",
    "infer_listing_completion_receipt_path",
    "validate_spy_listing_observation",
]
