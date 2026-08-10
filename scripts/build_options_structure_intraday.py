#!/usr/bin/env python3
"""Build and publish MSC R2.2-A Light U-CHAIN packets.

Private inputs remain under ``data/chain_snapshots``. Publication writes and
verifies every immutable root/bucket packet first, then monotonically commits
the complete ``index.json`` manifest as the sole authoritative discovery
object. Per-root ``current.json`` pointers are derivative conveniences repaired
only after that commit. No publication path rolls back or deletes remote data.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import fcntl
from hashlib import sha256
import io
import json
import logging
import os
from pathlib import Path
from numbers import Integral
import re
import resource
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine import chain_snapshot_completion as bucket_completion
from engine import chain_snapshot_evidence
from engine.options_structure_intraday import (
    CURRENT_SCHEMA,
    INDEX_SCHEMA,
    OptionsStructureIntradayError,
    build_current_pointer,
    build_index,
    build_packet,
    canonical_json_bytes,
    current_key,
    index_key,
    object_receipt,
    packet_key,
    strict_json_object,
)
from lib import config, nyse_calendar


log = logging.getLogger("build_options_structure_intraday")
_PACKET_SCHEMA_PATH = (
    _REPO_ROOT / "contracts" / "options" / "options.contract_eligibility.v1.schema.json"
)
_PACKET_VALIDATOR: Any | None = None
_AWARE_CLOCK_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)
_BUCKET_RE = re.compile(r"^(?:0\d|1\d|2[0-3]):(?:00|15|30|45)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BUCKET_ID_RE = re.compile(r"^csb_[0-9a-f]{24}$")
_BUCKET_RECEIPT_ID_RE = re.compile(r"^csbr_[0-9a-f]{24}$")
PUBLICATION_ACK_SCHEMA = "options_structure.publisher_ack/v1"
PUBLICATION_CURSOR_SCHEMA = "options_structure.publisher_cursor/v1"
PUBLICATION_SCAN_CURSOR_SCHEMA = "options_structure.publisher_scan_cursor/v1"


class PublicationError(RuntimeError):
    """R2 publication could not preserve or prove the discovery contract."""


class ImmutableCollisionError(PublicationError):
    """A dated R2 address already carries different bytes."""


class EpochRegressionError(PublicationError):
    """A mutable discovery target is older than the already published epoch."""


class EpochCollisionError(PublicationError):
    """One epoch already exists with different immutable bindings."""


class PublicationCommitUncertainError(PublicationError):
    """The global commit may have landed, but its exact remote state is unproved."""


class PublicationRepairNeededError(PublicationError):
    """The global index committed while derivative current repair was incomplete."""

    def __init__(self, failures: Sequence[str]) -> None:
        self.index_committed = True
        self.failures = tuple(failures)
        super().__init__(
            "global index committed; derivative current repair needed: "
            + "; ".join(self.failures)
        )


class LocalCommitUncertainError(PublicationError):
    """A local mirror mutation could not prove crash-durable completion."""


@dataclass(frozen=True)
class Artifact:
    key: str
    body: bytes
    sha256: str

    @classmethod
    def from_payload(cls, key: str, payload: Mapping[str, Any]) -> "Artifact":
        body = canonical_json_bytes(payload)
        # Decode what will actually be published.  This catches duplicate keys,
        # NaN and non-object roots before any filesystem or R2 mutation.
        strict_json_object(body)
        return cls(key=key, body=body, sha256=sha256(body).hexdigest())


@dataclass(frozen=True)
class PublicationBundle:
    packets: Mapping[str, Mapping[str, Any]]
    immutable: Mapping[str, Artifact]
    currents: Mapping[str, Artifact]
    index: Artifact


@dataclass(frozen=True)
class PublicationResult:
    index_status: str
    currents_repaired: tuple[str, ...]
    currents_idempotent: tuple[str, ...]
    currents_superseded: tuple[str, ...]


@dataclass(frozen=True)
class RemoteObject:
    body: bytes
    metadata: Mapping[str, str]
    content_length: int
    etag: str | None


@dataclass(frozen=True)
class CompletionRequest:
    session_date: str
    snapshot_bucket: str
    roots: tuple[str, ...]
    cadence_minutes: int
    observed_at: str
    available_at: str
    root_evidence: tuple["RootCompletionEvidence", ...]


@dataclass(frozen=True)
class RootCompletionEvidence:
    root: str
    bucket_rows: int
    bucket_content_sha256: str
    oi_total_rows: int
    oi_parquet_sha256: str


def _safe_root(value: object) -> str:
    # The core owns the authoritative validation; packet_key is a dependency-
    # free way to invoke it without importing a private helper.
    if (
        not isinstance(value, str)
        or value != value.strip()
        or value != value.upper()
    ):
        raise OptionsStructureIntradayError(f"unsafe root: {value!r}")
    root = value
    packet_key(root, "2000-01-03", "09:30")
    return root


def _control_integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise OptionsStructureIntradayError(f"{field} must be an integer")
    return int(value)


def _canonical_aware_clock(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _AWARE_CLOCK_RE.fullmatch(value):
        raise OptionsStructureIntradayError(f"{field} must be a canonical aware timestamp")
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise OptionsStructureIntradayError(f"{field} is not a timestamp") from exc
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise OptionsStructureIntradayError(f"{field} must be timezone-aware")
    return value


def _read_stable_parquet_receipt(path: Path) -> tuple[pd.DataFrame, str]:
    """Read one stable Parquet object and bind its exact serialized bytes."""
    try:
        before = path.stat()
    except OSError as exc:
        raise OptionsStructureIntradayError(f"source missing or unreadable: {path}") from exc
    if not path.is_file() or before.st_size <= 0:
        raise OptionsStructureIntradayError(f"source is not a non-empty file: {path}")
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - any malformed source fails the bucket
        raise OptionsStructureIntradayError(f"malformed parquet source: {path}: {exc}") from exc
    try:
        serialized_sha256 = chain_snapshot_evidence.file_sha256(path)
        after = path.stat()
    except OSError as exc:
        raise OptionsStructureIntradayError(f"source disappeared while reading: {path}") from exc
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise OptionsStructureIntradayError(f"source changed while reading: {path}")
    return frame, serialized_sha256


def _read_stable_parquet(path: Path) -> pd.DataFrame:
    """Read one atomically-written Parquet object or fail on a concurrent swap."""
    frame, _serialized_sha256 = _read_stable_parquet_receipt(path)
    return frame


def _strict_json_path(path: Path) -> dict[str, Any]:
    try:
        return strict_json_object(path.read_bytes())
    except OSError as exc:
        raise OptionsStructureIntradayError(f"JSON source missing or unreadable: {path}") from exc


def _validate_packet_schema(packet: Mapping[str, Any]) -> None:
    global _PACKET_VALIDATOR
    if _PACKET_VALIDATOR is None:
        try:
            from jsonschema import Draft202012Validator, FormatChecker  # noqa: PLC0415
            schema = strict_json_object(_PACKET_SCHEMA_PATH.read_bytes())
            _PACKET_VALIDATOR = Draft202012Validator(schema, format_checker=FormatChecker())
        except Exception as exc:  # noqa: BLE001
            raise OptionsStructureIntradayError(f"packet schema could not be loaded: {exc}") from exc
    errors = sorted(_PACKET_VALIDATOR.iter_errors(packet), key=lambda error: list(error.path))
    if errors:
        summary = "; ".join(error.message for error in errors[:5])
        raise OptionsStructureIntradayError(f"packet schema validation failed: {summary}")


def validate_complete_meta(
    meta: Mapping[str, Any],
    *,
    session_date: str,
    snapshot_bucket: str,
    roots: Sequence[str],
) -> int:
    """Require the poller's latest cycle to attest one complete root universe."""
    requested_roots = [_safe_root(root) for root in roots]
    packet_key("META", session_date, snapshot_bucket)
    if meta.get("schema") != "chain_snapshots.meta/v1":
        raise OptionsStructureIntradayError("_meta.json schema mismatch")
    if meta.get("session_date") != session_date or meta.get("bucket") != snapshot_bucket:
        raise OptionsStructureIntradayError("_meta.json does not describe the requested session bucket")
    try:
        universe_n = _control_integer(meta["universe_n"], field="_meta.json universe_n")
        roots_ok = _control_integer(meta["roots_ok"], field="_meta.json roots_ok")
        roots_failed = _control_integer(meta["roots_failed"], field="_meta.json roots_failed")
        cadence = _control_integer(meta["cadence_min"], field="_meta.json cadence_min")
    except KeyError as exc:
        raise OptionsStructureIntradayError("_meta.json completeness counters are malformed") from exc
    if universe_n <= 0 or roots_failed != 0 or roots_ok != universe_n:
        raise OptionsStructureIntradayError(
            f"incomplete U-CHAIN bucket: ok={roots_ok} failed={roots_failed} universe={universe_n}"
        )
    if len(requested_roots) != universe_n or len(set(requested_roots)) != universe_n:
        raise OptionsStructureIntradayError(
            f"root set does not bind complete meta universe: roots={len(set(requested_roots))} universe={universe_n}"
        )
    raw_meta_roots = meta.get("roots")
    if not isinstance(raw_meta_roots, list):
        raise OptionsStructureIntradayError("_meta.json roots must bind the exact root identities")
    meta_roots = [_safe_root(value) for value in raw_meta_roots]
    if len(meta_roots) != len(set(meta_roots)) or sorted(meta_roots) != sorted(requested_roots):
        raise OptionsStructureIntradayError("_meta.json roots do not match the exact requested root set")
    if cadence != 15:
        raise OptionsStructureIntradayError("_meta.json cadence_min must be 15 for MSC R2.2-A")
    _canonical_aware_clock(meta.get("asof"), field="_meta.json asof")
    return cadence


def completion_request(packet: object) -> CompletionRequest:
    """Resolve exact build inputs from a validated producer completion packet."""
    try:
        state = bucket_completion.validate_completion_packet(packet)
    except bucket_completion.BucketStateError as exc:
        raise OptionsStructureIntradayError(
            f"invalid producer completion packet: {exc}"
        ) from exc
    if state.decision is None or state.availability is None:
        raise OptionsStructureIntradayError("completion packet is not terminally available")
    evidence = tuple(
        RootCompletionEvidence(
            root=result["root"],
            bucket_rows=result["bucket_rows"],
            bucket_content_sha256=result["bucket_content_sha256"],
            oi_total_rows=result["oi_total_rows"],
            oi_parquet_sha256=result["oi_parquet_sha256"],
        )
        for result in state.decision["completion"]["root_results"]
    )
    return CompletionRequest(
        session_date=state.intent["session_date"],
        snapshot_bucket=state.intent["bucket"],
        roots=tuple(state.intent["roots"]),
        cadence_minutes=state.intent["cadence_min"],
        observed_at=state.decision["decision_at"],
        available_at=state.availability["availability_at"],
        root_evidence=evidence,
    )


def publication_ack_path(out_dir: Path, packet: object) -> Path:
    """Return the deterministic local-only acknowledgement path."""
    request = completion_request(packet)
    return (
        Path(out_dir)
        / "options_structure"
        / "msc_intraday"
        / "_publication_receipts"
        / request.session_date
        / f"{request.snapshot_bucket.replace(':', '')}.json"
    )


def publication_index_receipt_path(out_dir: Path, packet: object) -> Path:
    """Return the immutable local copy of the exact committed index bytes."""
    return publication_ack_path(out_dir, packet).with_suffix(".index.json")


def publication_cursor_path(out_dir: Path) -> Path:
    """Return the local-only contiguous delivery cursor path."""
    return (
        Path(out_dir)
        / "options_structure"
        / "msc_intraday"
        / "_publication_receipts"
        / "cursor.json"
    )


def publication_scan_cursor_path(out_dir: Path) -> Path:
    """Return the local-only bounded source-ledger scan checkpoint path."""
    return publication_cursor_path(out_dir).with_name("scan_cursor.json")


def _canonical_nyse_session(value: object, field: str) -> str:
    if type(value) is not str:
        raise PublicationError(f"{field} must be a canonical NYSE session")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PublicationError(f"{field} must be a canonical NYSE session") from exc
    if parsed.isoformat() != value or not nyse_calendar.is_session(parsed):
        raise PublicationError(f"{field} must be a canonical NYSE session")
    return value


def _publication_ack_payload(
    packet: object,
    bundle: PublicationBundle,
) -> dict[str, Any]:
    request = completion_request(packet)
    state = bucket_completion.validate_completion_packet(packet)
    if state.decision is None or state.availability is None:
        raise OptionsStructureIntradayError("publication acknowledgement needs availability")
    objects = [
        {
            "root": root,
            "key": bundle.immutable[root].key,
            "sha256": bundle.immutable[root].sha256,
            "bytes": len(bundle.immutable[root].body),
            "packet_id": bundle.packets[root]["packet_id"],
        }
        for root in sorted(bundle.immutable)
    ]
    if tuple(item["root"] for item in objects) != tuple(sorted(request.roots)):
        raise PublicationError("publication acknowledgement root set drifted")
    return {
        "schema": PUBLICATION_ACK_SCHEMA,
        "session_date": request.session_date,
        "snapshot_bucket": request.snapshot_bucket,
        "bucket_id": state.intent["bucket_id"],
        "decision_receipt_id": state.decision["receipt_id"],
        "availability_receipt_id": state.availability["receipt_id"],
        "completion_result_sha256": state.decision["completion"]["result_sha256"],
        "completion_packet_sha256": sha256(
            bucket_completion.canonical_bytes(packet)
        ).hexdigest(),
        "index_key": bundle.index.key,
        "index_sha256": bundle.index.sha256,
        "objects": objects,
    }


def _validate_publication_ack(payload: object, packet: object) -> None:
    request = completion_request(packet)
    state = bucket_completion.validate_completion_packet(packet)
    if state.decision is None or state.availability is None:
        raise PublicationError("publication acknowledgement packet is incomplete")
    expected_keys = {
        "schema", "session_date", "snapshot_bucket", "bucket_id",
        "decision_receipt_id", "availability_receipt_id",
        "completion_result_sha256", "completion_packet_sha256",
        "index_key", "index_sha256", "objects",
    }
    if type(payload) is not dict or set(payload) != expected_keys:
        raise PublicationError("invalid local publication acknowledgement shape")
    expected_identity = {
        "schema": PUBLICATION_ACK_SCHEMA,
        "session_date": request.session_date,
        "snapshot_bucket": request.snapshot_bucket,
        "bucket_id": state.intent["bucket_id"],
        "decision_receipt_id": state.decision["receipt_id"],
        "availability_receipt_id": state.availability["receipt_id"],
        "completion_result_sha256": state.decision["completion"]["result_sha256"],
        "completion_packet_sha256": sha256(
            bucket_completion.canonical_bytes(packet)
        ).hexdigest(),
        "index_key": index_key(),
    }
    for field, expected in expected_identity.items():
        if payload.get(field) != expected:
            raise PublicationError(
                f"local publication acknowledgement {field} mismatch"
            )
    if type(payload.get("index_sha256")) is not str or not _SHA256_RE.fullmatch(
        payload["index_sha256"]
    ):
        raise PublicationError("local publication acknowledgement index hash is invalid")
    objects = payload.get("objects")
    if type(objects) is not list or len(objects) != len(request.roots):
        raise PublicationError("local publication acknowledgement object coverage drifted")
    expected_roots = sorted(request.roots)
    for root, item in zip(expected_roots, objects, strict=True):
        if type(item) is not dict or set(item) != {
            "root", "key", "sha256", "bytes", "packet_id",
        }:
            raise PublicationError("invalid local publication object receipt shape")
        if item.get("root") != root or item.get("key") != packet_key(
            root, request.session_date, request.snapshot_bucket
        ):
            raise PublicationError("local publication object receipt identity drifted")
        if type(item.get("sha256")) is not str or not _SHA256_RE.fullmatch(
            item["sha256"]
        ):
            raise PublicationError("local publication object hash is invalid")
        if type(item.get("bytes")) is not int or item["bytes"] <= 0:
            raise PublicationError("local publication object byte count is invalid")
        if (
            type(item.get("packet_id")) is not str
            or not item["packet_id"].startswith("packet:uchain:")
            or not _SHA256_RE.fullmatch(item["packet_id"].removeprefix("packet:uchain:"))
        ):
            raise PublicationError("local publication packet id is invalid")


def publication_acknowledged(out_dir: Path, packet: object) -> bool:
    """Re-prove a successful prior R2+local commit for one completion packet."""
    target = publication_ack_path(out_dir, packet)
    if not target.exists():
        return False
    try:
        ack_body = _durable_read(target)
        payload = strict_json_object(ack_body)
    except OptionsStructureIntradayError as exc:
        raise PublicationError(
            f"invalid local publication acknowledgement: {target}: {exc}"
        ) from exc
    _validate_publication_ack(payload, packet)
    if canonical_json_bytes(payload) != ack_body:
        raise PublicationError(
            f"local publication acknowledgement is not canonical: {target}"
        )
    index_receipt = _durable_read(publication_index_receipt_path(out_dir, packet))
    if sha256(index_receipt).hexdigest() != payload["index_sha256"]:
        raise PublicationError("local publication index receipt hash drifted")
    index_payload = strict_json_object(index_receipt)
    _epoch(index_payload, schema=INDEX_SCHEMA, key=payload["index_key"])
    index_identity = dict(index_payload)
    index_identity.pop("index_id", None)
    expected_index_id = (
        "index:uchain:" + sha256(canonical_json_bytes(index_identity)).hexdigest()
    )
    if index_payload.get("index_id") != expected_index_id:
        raise PublicationError("local publication index receipt id drifted")
    index_roots = index_payload.get("roots")
    if type(index_roots) is not list:
        raise PublicationError("local publication index roots are malformed")
    index_objects = {
        item["root"]: item["object"]
        for item in index_roots
        if type(item) is dict and type(item.get("root")) is str
    }
    if len(index_objects) != len(payload["objects"]):
        raise PublicationError("local publication index receipt root coverage drifted")
    for item in payload["objects"]:
        body = _durable_read(Path(out_dir) / item["key"])
        if len(body) != item["bytes"] or sha256(body).hexdigest() != item["sha256"]:
            raise PublicationError(
                f"local immutable object drift for acknowledged key: {item['key']}"
            )
        object_payload = strict_json_object(body)
        expected_object_receipt = {
            "key": item["key"],
            "sha256": item["sha256"],
            "bytes": item["bytes"],
            "packet_id": item["packet_id"],
        }
        if object_payload.get("packet_id") != item["packet_id"]:
            raise PublicationError(
                f"local immutable packet id drift for acknowledged key: {item['key']}"
            )
        if index_objects.get(item["root"]) != expected_object_receipt:
            raise PublicationError(
                f"local publication index object receipt drift for {item['root']}"
            )
    return True


def publication_prefix_receipt(packets: Sequence[object]) -> dict[str, Any]:
    """Hash one session's exact chronological complete-packet cursor prefix."""
    rows: list[dict[str, str]] = []
    epochs: list[tuple[date, int]] = []
    prefix_session: str | None = None
    for packet in packets:
        state = bucket_completion.validate_completion_packet(packet)
        if state.availability is None:
            raise PublicationError("publication prefix contains an incomplete packet")
        if prefix_session is None:
            prefix_session = state.intent["session_date"]
        elif state.intent["session_date"] != prefix_session:
            raise PublicationError("publication prefix crosses a session boundary")
        epoch = (
            date.fromisoformat(state.intent["session_date"]),
            int(state.intent["bucket"].split(":")[0]) * 60
            + int(state.intent["bucket"].split(":")[1]),
        )
        if epochs and epoch <= epochs[-1]:
            raise PublicationError("publication prefix is not strictly chronological")
        epochs.append(epoch)
        rows.append({
            "session_date": state.intent["session_date"],
            "snapshot_bucket": state.intent["bucket"],
            "bucket_id": state.intent["bucket_id"],
            "availability_receipt_id": state.availability["receipt_id"],
            "completion_packet_sha256": sha256(
                bucket_completion.canonical_bytes(packet)
            ).hexdigest(),
        })
    return {
        "complete_prefix_count": len(rows),
        "complete_prefix_sha256": sha256(canonical_json_bytes(rows)).hexdigest(),
    }


def _publication_cursor_payload(
    out_dir: Path,
    packet: object,
    prefix_packets: Sequence[object],
    activation_session: str,
) -> dict[str, Any]:
    state = bucket_completion.validate_completion_packet(packet)
    if state.decision is None or state.availability is None:
        raise PublicationError("publication cursor packet is incomplete")
    ack_body = _durable_read(publication_ack_path(out_dir, packet))
    activation = _canonical_nyse_session(
        activation_session, "publication cursor activation_session",
    )
    if state.intent["session_date"] < activation:
        raise PublicationError("publication cursor packet precedes activation")
    prefix = publication_prefix_receipt(prefix_packets)
    if not prefix_packets or not publication_cursor_matches(
        {
            "session_date": state.intent["session_date"],
            "snapshot_bucket": state.intent["bucket"],
            "bucket_id": state.intent["bucket_id"],
            "availability_receipt_id": state.availability["receipt_id"],
            "completion_packet_sha256": sha256(
                bucket_completion.canonical_bytes(packet)
            ).hexdigest(),
        },
        prefix_packets[-1],
    ):
        raise PublicationError("publication cursor is not the end of its prefix")
    return {
        "schema": PUBLICATION_CURSOR_SCHEMA,
        "activation_session": activation,
        "session_date": state.intent["session_date"],
        "snapshot_bucket": state.intent["bucket"],
        "bucket_id": state.intent["bucket_id"],
        "availability_receipt_id": state.availability["receipt_id"],
        "completion_packet_sha256": sha256(
            bucket_completion.canonical_bytes(packet)
        ).hexdigest(),
        "ack_sha256": sha256(ack_body).hexdigest(),
        **prefix,
    }


def read_publication_cursor(out_dir: Path) -> dict[str, Any] | None:
    """Read and strictly validate the durable contiguous delivery cursor."""
    target = publication_cursor_path(out_dir)
    if not target.exists():
        return None
    try:
        body = _durable_read(target)
        payload = strict_json_object(body)
    except OptionsStructureIntradayError as exc:
        raise PublicationError(f"invalid local publication cursor: {exc}") from exc
    expected_keys = {
        "schema", "activation_session", "session_date", "snapshot_bucket", "bucket_id",
        "availability_receipt_id", "completion_packet_sha256", "ack_sha256",
        "complete_prefix_count", "complete_prefix_sha256",
    }
    if type(payload) is not dict or set(payload) != expected_keys:
        raise PublicationError("invalid local publication cursor shape")
    if canonical_json_bytes(payload) != body:
        raise PublicationError("local publication cursor is not canonical")
    if payload.get("schema") != PUBLICATION_CURSOR_SCHEMA:
        raise PublicationError("local publication cursor schema mismatch")
    activation = _canonical_nyse_session(
        payload.get("activation_session"), "publication cursor activation_session",
    )
    packet_key("CURSOR", payload.get("session_date"), payload.get("snapshot_bucket"))
    if payload["session_date"] < activation:
        raise PublicationError("local publication cursor precedes activation")
    for field in (
        "completion_packet_sha256", "ack_sha256", "complete_prefix_sha256",
    ):
        if type(payload.get(field)) is not str or not _SHA256_RE.fullmatch(payload[field]):
            raise PublicationError(f"local publication cursor {field} is invalid")
    if (
        type(payload.get("complete_prefix_count")) is not int
        or payload["complete_prefix_count"] <= 0
    ):
        raise PublicationError("local publication cursor prefix count is invalid")
    if (
        type(payload.get("bucket_id")) is not str
        or not _BUCKET_ID_RE.fullmatch(payload["bucket_id"])
    ):
        raise PublicationError("local publication cursor bucket_id is invalid")
    if (
        type(payload.get("availability_receipt_id")) is not str
        or not _BUCKET_RECEIPT_ID_RE.fullmatch(payload["availability_receipt_id"])
    ):
        raise PublicationError(
            "local publication cursor availability_receipt_id is invalid"
        )
    ack_target = (
        target.parent
        / payload["session_date"]
        / f"{payload['snapshot_bucket'].replace(':', '')}.json"
    )
    if sha256(_durable_read(ack_target)).hexdigest() != payload["ack_sha256"]:
        raise PublicationError("local publication cursor ack hash drifted")
    return payload


def read_publication_scan_cursor(out_dir: Path) -> dict[str, Any] | None:
    """Read the durable floor used to bound forward receipt-ledger decoding."""
    target = publication_scan_cursor_path(out_dir)
    if not target.exists():
        return None
    try:
        body = _durable_read(target)
        payload = strict_json_object(body)
    except OptionsStructureIntradayError as exc:
        raise PublicationError(f"invalid local publication scan cursor: {exc}") from exc
    expected_keys = {
        "schema", "activation_session", "scan_session", "sealed_session",
        "sealed_ledger_sha256", "sealed_complete_count",
        "sealed_complete_prefix_sha256", "sealed_ack_prefix_sha256",
        "sealed_last_bucket",
        "sealed_last_availability_receipt_id", "sealed_last_ack_sha256",
    }
    if type(payload) is not dict or set(payload) != expected_keys:
        raise PublicationError("invalid local publication scan cursor shape")
    if canonical_json_bytes(payload) != body:
        raise PublicationError("local publication scan cursor is not canonical")
    if payload.get("schema") != PUBLICATION_SCAN_CURSOR_SCHEMA:
        raise PublicationError("local publication scan cursor schema mismatch")
    activation = _canonical_nyse_session(
        payload.get("activation_session"), "scan cursor activation_session",
    )
    scan = _canonical_nyse_session(
        payload.get("scan_session"), "scan cursor scan_session",
    )
    sealed = _canonical_nyse_session(
        payload.get("sealed_session"), "scan cursor sealed_session",
    )
    if sealed < activation or scan <= sealed:
        raise PublicationError("local publication scan cursor step is not forward")
    for field in (
        "sealed_ledger_sha256", "sealed_complete_prefix_sha256",
        "sealed_ack_prefix_sha256",
    ):
        if type(payload.get(field)) is not str or not _SHA256_RE.fullmatch(payload[field]):
            raise PublicationError(f"local publication scan cursor {field} is invalid")
    count = payload.get("sealed_complete_count")
    if type(count) is not int or count < 0:
        raise PublicationError("local publication scan cursor complete count is invalid")
    if count == 0:
        if any(payload.get(field) is not None for field in (
            "sealed_last_bucket", "sealed_last_availability_receipt_id",
            "sealed_last_ack_sha256",
        )):
            raise PublicationError("empty sealed session cannot bind a last delivery")
        if payload["sealed_complete_prefix_sha256"] != publication_prefix_receipt([])[
            "complete_prefix_sha256"
        ]:
            raise PublicationError("empty sealed session prefix hash is invalid")
        if payload["sealed_ack_prefix_sha256"] != sha256(
            canonical_json_bytes([])
        ).hexdigest():
            raise PublicationError("empty sealed session ack prefix hash is invalid")
    else:
        if (
            type(payload.get("sealed_last_bucket")) is not str
            or not _BUCKET_RE.fullmatch(payload["sealed_last_bucket"])
            or type(payload.get("sealed_last_availability_receipt_id")) is not str
            or not _BUCKET_RECEIPT_ID_RE.fullmatch(
                payload["sealed_last_availability_receipt_id"]
            )
            or type(payload.get("sealed_last_ack_sha256")) is not str
            or not _SHA256_RE.fullmatch(payload["sealed_last_ack_sha256"])
        ):
            raise PublicationError("sealed session last delivery binding is invalid")
        ack_target = (
            publication_cursor_path(out_dir).parent
            / sealed
            / f"{payload['sealed_last_bucket'].replace(':', '')}.json"
        )
        if sha256(_durable_read(ack_target)).hexdigest() != payload[
            "sealed_last_ack_sha256"
        ]:
            raise PublicationError("sealed session acknowledgement hash drifted")
    return payload


def _scan_cursor_delivery_binding(
    out_dir: Path,
    sealed_packets: Sequence[object],
    *,
    deep: bool,
) -> dict[str, Any]:
    prefix = publication_prefix_receipt(sealed_packets)
    if not sealed_packets:
        return {
            "sealed_complete_count": 0,
            "sealed_complete_prefix_sha256": prefix["complete_prefix_sha256"],
            "sealed_ack_prefix_sha256": sha256(
                canonical_json_bytes([])
            ).hexdigest(),
            "sealed_last_bucket": None,
            "sealed_last_availability_receipt_id": None,
            "sealed_last_ack_sha256": None,
        }
    ack_rows: list[dict[str, str]] = []
    last_state = None
    last_ack_body = b""
    for packet in sealed_packets:
        state = bucket_completion.validate_completion_packet(packet)
        if state.availability is None:
            raise PublicationError("sealed session completion is incomplete")
        if deep and not publication_acknowledged(out_dir, packet):
            raise PublicationError(
                "sealed session completion is not acknowledged: "
                f"{state.intent['session_date']}/{state.intent['bucket']}"
            )
        ack_body = _durable_read(publication_ack_path(out_dir, packet))
        ack_rows.append({
            "snapshot_bucket": state.intent["bucket"],
            "availability_receipt_id": state.availability["receipt_id"],
            "ack_sha256": sha256(ack_body).hexdigest(),
        })
        last_state = state
        last_ack_body = ack_body
    if last_state is None:
        raise PublicationError("sealed session acknowledgement prefix is empty")
    return {
        "sealed_complete_count": prefix["complete_prefix_count"],
        "sealed_complete_prefix_sha256": prefix["complete_prefix_sha256"],
        "sealed_ack_prefix_sha256": sha256(
            canonical_json_bytes(ack_rows)
        ).hexdigest(),
        "sealed_last_bucket": last_state.intent["bucket"],
        "sealed_last_availability_receipt_id": last_state.availability["receipt_id"],
        "sealed_last_ack_sha256": sha256(last_ack_body).hexdigest(),
    }


def publication_scan_cursor_matches(
    out_dir: Path,
    cursor: Mapping[str, Any],
    sealed_packets: Sequence[object],
) -> bool:
    """Deeply bind a scan checkpoint to its exact delivered source prefix."""
    binding = _scan_cursor_delivery_binding(
        out_dir, sealed_packets, deep=False,
    )
    if sealed_packets:
        state = bucket_completion.validate_completion_packet(sealed_packets[-1])
        if state.intent["session_date"] != cursor.get("sealed_session"):
            return False
    return all(cursor.get(field) == value for field, value in binding.items())


def advance_publication_scan_cursor(
    out_dir: Path,
    *,
    activation_session: str,
    from_session: str,
    to_session: str,
    sealed_session: str,
    sealed_ledger_sha256: str,
    sealed_packets: Sequence[object],
) -> Path:
    """Persist one verified terminal-ledger step without fabricating delivery."""
    activation = _canonical_nyse_session(
        activation_session, "scan cursor activation_session",
    )
    previous = _canonical_nyse_session(from_session, "scan cursor from_session")
    following = _canonical_nyse_session(to_session, "scan cursor to_session")
    sealed = _canonical_nyse_session(sealed_session, "scan cursor sealed_session")
    if (
        type(sealed_ledger_sha256) is not str
        or not _SHA256_RE.fullmatch(sealed_ledger_sha256)
    ):
        raise PublicationError("scan cursor sealed ledger hash is invalid")
    if previous < activation or sealed < previous or following <= sealed:
        raise PublicationError("publication scan cursor step is not forward-contiguous")
    for packet in sealed_packets:
        state = bucket_completion.validate_completion_packet(packet)
        if state.intent["session_date"] != sealed:
            raise PublicationError("scan cursor sealed packet session drifted")
    desired = {
        "schema": PUBLICATION_SCAN_CURSOR_SCHEMA,
        "activation_session": activation,
        "scan_session": following,
        "sealed_session": sealed,
        "sealed_ledger_sha256": sealed_ledger_sha256,
        **_scan_cursor_delivery_binding(out_dir, sealed_packets, deep=True),
    }
    target = publication_scan_cursor_path(out_dir)
    lock_path = Path(out_dir) / "options_structure" / "msc_intraday" / ".publish.lock"
    _ensure_durable_directory(lock_path.parent)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        current = read_publication_scan_cursor(out_dir)
        if current == desired:
            return target
        if current is not None and (
            current["activation_session"] != activation
            or current["scan_session"] != previous
        ):
            raise PublicationError(
                "publication scan cursor does not extend its exact prior floor"
            )
        _atomic_write(target, canonical_json_bytes(desired))
    if read_publication_scan_cursor(out_dir) != desired:
        raise LocalCommitUncertainError(
            "local publication scan cursor could not be re-proved"
        )
    return target


def publication_cursor_matches(cursor: Mapping[str, Any], packet: object) -> bool:
    """Return whether one validated cursor identifies this exact packet."""
    state = bucket_completion.validate_completion_packet(packet)
    if state.availability is None:
        return False
    expected = {
        "session_date": state.intent["session_date"],
        "snapshot_bucket": state.intent["bucket"],
        "bucket_id": state.intent["bucket_id"],
        "availability_receipt_id": state.availability["receipt_id"],
        "completion_packet_sha256": sha256(
            bucket_completion.canonical_bytes(packet)
        ).hexdigest(),
    }
    return all(cursor.get(field) == value for field, value in expected.items())


def publication_cursor_prefix_matches(
    cursor: Mapping[str, Any],
    prefix_packets: Sequence[object],
) -> bool:
    """Detect any newly-complete/reordered packet before the durable cursor."""
    prefix = publication_prefix_receipt(prefix_packets)
    return all(cursor.get(field) == value for field, value in prefix.items())


def _cursor_epoch(payload: Mapping[str, Any]) -> tuple[date, int]:
    session = date.fromisoformat(str(payload["session_date"]))
    hour, minute = (int(part) for part in str(payload["snapshot_bucket"]).split(":"))
    return session, hour * 60 + minute


def advance_publication_cursor(
    out_dir: Path,
    packet: object,
    *,
    prefix_packets: Sequence[object],
    activation_session: str,
) -> Path:
    """Advance the derivative cursor after deep acknowledgement reproof."""
    if not publication_acknowledged(out_dir, packet):
        raise PublicationError("cannot advance publication cursor without acknowledgement")
    desired = _publication_cursor_payload(
        out_dir, packet, prefix_packets, activation_session,
    )
    body = canonical_json_bytes(desired)
    target = publication_cursor_path(out_dir)
    lock_path = Path(out_dir) / "options_structure" / "msc_intraday" / ".publish.lock"
    _ensure_durable_directory(lock_path.parent)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        current = read_publication_cursor(out_dir)
        if current is not None:
            if current["activation_session"] != desired["activation_session"]:
                raise PublicationError(
                    "local publication cursor activation cannot change"
                )
            if _cursor_epoch(current) > _cursor_epoch(desired):
                raise EpochRegressionError("local publication cursor cannot regress")
            if _cursor_epoch(current) == _cursor_epoch(desired):
                if current != desired:
                    raise EpochCollisionError(
                        "same local publication cursor epoch has different bytes"
                    )
                return target
            if current["session_date"] == desired["session_date"]:
                if (
                    desired["complete_prefix_count"]
                    != current["complete_prefix_count"] + 1
                ):
                    raise PublicationError(
                        "local publication cursor may advance by exactly one packet"
                    )
                prior_prefix = list(prefix_packets[:-1])
                if (
                    not prior_prefix
                    or not publication_cursor_matches(current, prior_prefix[-1])
                    or not publication_cursor_prefix_matches(current, prior_prefix)
                ):
                    raise PublicationError(
                        "local publication cursor advance does not extend its exact prefix"
                    )
            elif desired["complete_prefix_count"] != 1:
                raise PublicationError(
                    "local publication cursor must reset to one at a new session"
                )
        elif desired["complete_prefix_count"] != 1:
            raise PublicationError("local publication cursor genesis must have one packet")
        _atomic_write(target, body)
    if read_publication_cursor(out_dir) != desired:
        raise LocalCommitUncertainError("local publication cursor could not be re-proved")
    return target


def write_publication_ack(
    out_dir: Path,
    packet: object,
    bundle: PublicationBundle,
) -> Path:
    """Durably acknowledge only a verified R2 and local-mirror publication."""
    payload = _publication_ack_payload(packet, bundle)
    _validate_publication_ack(payload, packet)
    body = canonical_json_bytes(payload)
    target = publication_ack_path(out_dir, packet)
    index_receipt_target = publication_index_receipt_path(out_dir, packet)
    lock_path = Path(out_dir) / "options_structure" / "msc_intraday" / ".publish.lock"
    _ensure_durable_directory(lock_path.parent)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        if index_receipt_target.exists():
            if _durable_read(index_receipt_target) != bundle.index.body:
                raise ImmutableCollisionError(
                    f"local publication index receipt collision: {index_receipt_target}"
                )
        else:
            _atomic_write(index_receipt_target, bundle.index.body)
        if target.exists():
            if _durable_read(target) != body:
                raise ImmutableCollisionError(
                    f"local publication acknowledgement collision: {target}"
                )
        else:
            _atomic_write(target, body)
    if not publication_acknowledged(out_dir, packet):
        raise LocalCommitUncertainError(
            f"local publication acknowledgement could not be re-proved: {target}"
        )
    return target


def _source_input_bytes(data_root: Path, roots: Sequence[str], session_date: str) -> int:
    total = 0
    for root in roots:
        safe_root = _safe_root(root)
        for suffix in (".parquet", "_oi.parquet"):
            path = data_root / safe_root / f"{session_date}{suffix}"
            try:
                stat = path.stat()
            except OSError as exc:
                raise OptionsStructureIntradayError(
                    f"cannot measure source input: {path}"
                ) from exc
            if not path.is_file() or stat.st_size <= 0:
                raise OptionsStructureIntradayError(
                    f"source input is not a non-empty file: {path}"
                )
            total += stat.st_size
    return total


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux reports KiB.
    return value if sys.platform == "darwin" else value * 1024


def discover_roots(data_root: Path, session_date: str) -> list[str]:
    roots: list[str] = []
    if not data_root.is_dir():
        raise OptionsStructureIntradayError(f"chain snapshot directory absent: {data_root}")
    for child in sorted(data_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        root = _safe_root(child.name)
        if (child / f"{session_date}.parquet").is_file():
            roots.append(root)
    if not roots:
        raise OptionsStructureIntradayError(f"no roots discovered for {session_date}")
    if len(roots) != len(set(roots)):
        raise OptionsStructureIntradayError("duplicate normalized roots discovered")
    return roots


def load_prophet_context(path: Path | None) -> dict[str, Mapping[str, Any]]:
    if path is None:
        return {}
    payload = _strict_json_path(path)
    out: dict[str, Mapping[str, Any]] = {}
    for raw_root, request in payload.items():
        root = _safe_root(raw_root)
        if root in out:
            raise OptionsStructureIntradayError(f"duplicate normalized Prophet root: {root}")
        if not isinstance(request, Mapping):
            raise OptionsStructureIntradayError(f"Prophet context for {root} must be an object")
        out[root] = request
    return out


def prepare_bundle(
    data_root: Path,
    *,
    roots: Sequence[str],
    session_date: str,
    snapshot_bucket: str,
    observed_at: str | datetime,
    available_at: str | datetime | None = None,
    cadence_minutes: int = 15,
    prophet_context: Mapping[str, Mapping[str, Any]] | None = None,
    completion_evidence: Sequence[RootCompletionEvidence] | None = None,
) -> PublicationBundle:
    """Read every root first and produce a complete, mutation-free bundle."""
    normalized_roots = sorted(_safe_root(root) for root in roots)
    if not normalized_roots or len(normalized_roots) != len(set(normalized_roots)):
        raise OptionsStructureIntradayError("roots must be a non-empty unique set")
    contexts = prophet_context or {}
    unknown_context = sorted(set(contexts).difference(normalized_roots))
    if unknown_context:
        raise OptionsStructureIntradayError(
            f"Prophet context contains roots outside the bucket: {', '.join(unknown_context)}"
        )
    evidence_by_root: dict[str, RootCompletionEvidence] = {}
    if completion_evidence is not None:
        for evidence in completion_evidence:
            if not isinstance(evidence, RootCompletionEvidence):
                raise OptionsStructureIntradayError(
                    "completion source evidence has an invalid entry"
                )
            if evidence.root in evidence_by_root:
                raise OptionsStructureIntradayError(
                    f"completion source evidence duplicates {evidence.root}"
                )
            evidence_by_root[evidence.root] = evidence
        if set(evidence_by_root) != set(normalized_roots):
            raise OptionsStructureIntradayError(
                "completion source evidence does not bind the exact root set"
            )

    packets: dict[str, Mapping[str, Any]] = {}
    immutable: dict[str, Artifact] = {}
    receipts: dict[str, Mapping[str, Any]] = {}
    for root in normalized_roots:
        root_dir = data_root / root
        chain, _chain_file_sha256 = _read_stable_parquet_receipt(
            root_dir / f"{session_date}.parquet"
        )
        oi, oi_file_sha256 = _read_stable_parquet_receipt(
            root_dir / f"{session_date}_oi.parquet"
        )
        if completion_evidence is not None:
            expected = evidence_by_root[root]
            try:
                target = chain_snapshot_evidence.target_bucket_frame(
                    chain,
                    root,
                    snapshot_bucket,
                    dedup_key=chain_snapshot_evidence.CHAIN_SNAPSHOT_DEDUP_KEY,
                )
                bucket_content_sha256 = chain_snapshot_evidence.frame_content_sha256(
                    target,
                    dedup_key=chain_snapshot_evidence.CHAIN_SNAPSHOT_DEDUP_KEY,
                )
            except RuntimeError as exc:
                raise OptionsStructureIntradayError(
                    f"cannot re-prove completion evidence for {root}: {exc}"
                ) from exc
            mismatches: list[str] = []
            if len(target) != expected.bucket_rows:
                mismatches.append("bucket_rows")
            if bucket_content_sha256 != expected.bucket_content_sha256:
                mismatches.append("bucket_content_sha256")
            if len(oi) != expected.oi_total_rows:
                mismatches.append("oi_total_rows")
            if oi_file_sha256 != expected.oi_parquet_sha256:
                mismatches.append("oi_parquet_sha256")
            if mismatches:
                raise OptionsStructureIntradayError(
                    f"producer completion evidence drift for {root}: "
                    + ", ".join(mismatches)
                )
        packet = build_packet(
            chain,
            oi,
            root=root,
            session_date=session_date,
            snapshot_bucket=snapshot_bucket,
            observed_at=observed_at,
            available_at=available_at,
            cadence_minutes=cadence_minutes,
            prophet_request=contexts.get(root),
        )
        _validate_packet_schema(packet)
        key = packet_key(root, session_date, snapshot_bucket)
        artifact = Artifact.from_payload(key, packet)
        packets[root] = packet
        immutable[root] = artifact
        receipts[root] = object_receipt(key, artifact.body, packet)

    index_payload = build_index(list(packets.values()), receipts)
    index_artifact = Artifact.from_payload(index_key(), index_payload)
    currents: dict[str, Artifact] = {}
    for root in normalized_roots:
        pointer = build_current_pointer(
            packets[root], receipts[root], index_id=index_payload["index_id"]
        )
        currents[root] = Artifact.from_payload(current_key(root), pointer)
    return PublicationBundle(
        packets=packets,
        immutable=immutable,
        currents=currents,
        index=index_artifact,
    )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise LocalCommitUncertainError(
            f"cannot open local directory for durability proof: {path}"
        ) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise LocalCommitUncertainError(
            f"local directory durability is uncertain: {path}"
        ) from exc
    finally:
        os.close(descriptor)


def _ensure_durable_directory(path: Path) -> None:
    """Create each missing component and persist every parent entry."""
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise LocalCommitUncertainError(
                f"cannot locate an existing ancestor for local directory: {path}"
            )
        cursor = parent
    if not cursor.is_dir():
        raise LocalCommitUncertainError(
            f"local directory ancestor is not a directory: {cursor}"
        )

    # If a prior attempt created ``cursor`` but failed while syncing its parent,
    # this first fence turns an exact retry into a durability proof.
    if cursor.parent != cursor:
        _fsync_directory(cursor.parent)
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError:
            if not directory.is_dir():
                raise LocalCommitUncertainError(
                    f"local directory path is not a directory: {directory}"
                )
        except OSError as exc:
            raise LocalCommitUncertainError(
                f"cannot create local directory: {directory}"
            ) from exc
        _fsync_directory(directory.parent)


def _durable_read(path: Path) -> bytes:
    """Read and re-fsync one exact local artifact plus its parent entry."""
    try:
        with path.open("rb") as handle:
            body = handle.read()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
        return body
    except LocalCommitUncertainError:
        raise
    except OSError as exc:
        raise LocalCommitUncertainError(
            f"local artifact durability is uncertain: {path}"
        ) from exc


def _atomic_write(path: Path, body: bytes) -> None:
    """Atomically replace one local artifact and make the rename durable."""
    _ensure_durable_directory(path.parent)
    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.tmp-",
            delete=False,
        ) as handle:
            tmp = Path(handle.name)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        tmp = None
        _fsync_directory(path.parent)
    except LocalCommitUncertainError:
        raise
    except OSError as exc:
        raise LocalCommitUncertainError(
            f"local atomic commit is uncertain: {path}"
        ) from exc
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def write_local_bundle(bundle: PublicationBundle, out_dir: Path) -> None:
    """Write immutable objects, the authoritative index, then derivative currents."""
    lock_path = out_dir / "options_structure" / "msc_intraday" / ".publish.lock"
    _ensure_durable_directory(lock_path.parent)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        for root in sorted(bundle.immutable):
            artifact = bundle.immutable[root]
            target = out_dir / artifact.key
            if target.exists():
                existing = _durable_read(target)
                if existing != artifact.body:
                    raise ImmutableCollisionError(
                        f"immutable local key collision: {artifact.key}"
                    )
            else:
                _atomic_write(target, artifact.body)

        index_target = out_dir / bundle.index.key
        index_status = _classify_local(index_target, bundle.index, schema=INDEX_SCHEMA)
        if index_status == "superseded":
            raise EpochRegressionError(
                f"local authoritative index already has a newer epoch: {bundle.index.key}"
            )
        if index_status == "advance":
            _atomic_write(index_target, bundle.index.body)

        for root in sorted(bundle.currents):
            artifact = bundle.currents[root]
            target = out_dir / artifact.key
            status = _classify_local(target, artifact, schema=CURRENT_SCHEMA)
            if status == "advance":
                _atomic_write(target, artifact.body)


def _classify_local(path: Path, artifact: Artifact, *, schema: str) -> str:
    if not path.exists():
        return "advance"
    body = _durable_read(path)
    current = _epoch(strict_json_object(body), schema=schema, key=str(path))
    desired = _desired_epoch(artifact, schema=schema)
    if current > desired:
        return "superseded"
    if current == desired:
        if body == artifact.body:
            return "idempotent"
        raise EpochCollisionError(f"same local discovery epoch has different bytes: {path}")
    return "advance"


def _r2_client() -> Any | None:
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and access_key and secret_key):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
    except ImportError:
        return None
    kwargs: dict[str, Any] = {
        "region_name": "auto",
        "signature_version": "s3v4",
        "retries": {"max_attempts": 4, "mode": "standard"},
    }
    try:
        client_config = Config(
            **kwargs,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:
        client_config = Config(**kwargs)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=client_config,
    )


def _error_code(exc: Exception) -> tuple[str, int]:
    response = getattr(exc, "response", {})
    if not isinstance(response, Mapping):
        return "", 0
    error = response.get("Error") or {}
    metadata = response.get("ResponseMetadata") or {}
    code = str(error.get("Code") or "") if isinstance(error, Mapping) else ""
    try:
        status = int(metadata.get("HTTPStatusCode") or 0) if isinstance(metadata, Mapping) else 0
    except (TypeError, ValueError):
        status = 0
    return code, status


def _is_not_found(exc: Exception) -> bool:
    code, status = _error_code(exc)
    return (
        code.lower() in {"404", "nosuchkey", "notfound", "no_such_key"}
        or status == 404
        or (type(exc) is RuntimeError and str(exc).strip().lower() in {"missing", "not found"})
    )


def _is_precondition_failed(exc: Exception) -> bool:
    code, status = _error_code(exc)
    return code.lower() in {"412", "preconditionfailed"} or status == 412


def _read_body(response: Mapping[str, Any], *, key: str) -> bytes:
    stream = response.get("Body")
    try:
        body = stream.read() if hasattr(stream, "read") else stream
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    if not isinstance(body, bytes):
        raise PublicationError(f"R2 object did not return bytes: {key}")
    return body


def _remote_object(client: Any, bucket: str, key: str) -> RemoteObject | None:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = _read_body(response, key=key)
    except Exception as exc:  # noqa: BLE001
        if _is_not_found(exc):
            return None
        if isinstance(exc, PublicationError):
            raise
        raise PublicationError(f"cannot read R2 key: {key}") from exc
    # One coherent GET response owns body, metadata, length, and version token.
    # Never combine a stale HEAD with a newer body from an unconditional GET.
    metadata = response.get("Metadata") or {}
    length = response.get("ContentLength")
    if not isinstance(metadata, Mapping) or isinstance(length, bool) or not isinstance(length, int):
        raise PublicationError(f"invalid R2 GET response: {key}")
    if length != len(body):
        raise PublicationError(f"R2 GET body/length mismatch: {key}")
    etag = response.get("ETag")
    return RemoteObject(
        body=body,
        metadata={str(k): str(v) for k, v in metadata.items()},
        content_length=length,
        etag=str(etag) if etag else None,
    )


def _remote_matches(remote: RemoteObject, artifact: Artifact) -> bool:
    return (
        remote.content_length == len(artifact.body)
        and remote.metadata.get("sha256") == artifact.sha256
        and sha256(remote.body).hexdigest() == artifact.sha256
        and remote.body == artifact.body
    )


def _verify_remote(client: Any, bucket: str, artifact: Artifact) -> RemoteObject:
    remote = _remote_object(client, bucket, artifact.key)
    if remote is None or not _remote_matches(remote, artifact):
        raise PublicationError(f"R2 verification failed: {artifact.key}")
    return remote


def _put_immutable(client: Any, bucket: str, artifact: Artifact) -> None:
    remote = _remote_object(client, bucket, artifact.key)
    if remote is not None:
        if not _remote_matches(remote, artifact):
            raise ImmutableCollisionError(f"immutable R2 key collision: {artifact.key}")
        return
    try:
        client.put_object(
            Bucket=bucket,
            Key=artifact.key,
            Body=artifact.body,
            ContentType="application/json",
            CacheControl="public, max-age=31536000, immutable",
            Metadata={"sha256": artifact.sha256},
            IfNoneMatch="*",
        )
    except Exception as exc:  # noqa: BLE001
        if _is_precondition_failed(exc):
            raced = _remote_object(client, bucket, artifact.key)
            if raced is not None and _remote_matches(raced, artifact):
                return
        raise PublicationError(f"immutable R2 write failed: {artifact.key}") from exc
    _verify_remote(client, bucket, artifact)


def _epoch(payload: Mapping[str, Any], *, schema: str, key: str) -> tuple[date, int]:
    if payload.get("schema") != schema:
        raise PublicationError(f"mutable discovery schema mismatch: {key}")
    session_raw = payload.get("session_date")
    bucket_raw = payload.get("snapshot_bucket")
    if not isinstance(session_raw, str) or not isinstance(bucket_raw, str):
        raise PublicationError(f"mutable discovery epoch fields missing: {key}")
    try:
        session = date.fromisoformat(session_raw)
    except ValueError as exc:
        raise PublicationError(f"mutable discovery date malformed: {key}") from exc
    if session.isoformat() != session_raw or not _BUCKET_RE.fullmatch(bucket_raw):
        raise PublicationError(f"mutable discovery epoch non-canonical: {key}")
    expected_label = f"{session_raw}/{bucket_raw}"
    if payload.get("epoch") != expected_label:
        raise PublicationError(f"mutable discovery epoch label mismatch: {key}")
    hour, minute = (int(part) for part in bucket_raw.split(":"))
    return session, hour * 60 + minute


def _remote_epoch(
    remote: RemoteObject,
    *,
    schema: str,
    key: str,
) -> tuple[tuple[date, int], Mapping[str, Any]]:
    body_sha = sha256(remote.body).hexdigest()
    if remote.metadata.get("sha256") != body_sha:
        raise PublicationError(f"mutable discovery receipt hash mismatch: {key}")
    payload = strict_json_object(remote.body)
    return _epoch(payload, schema=schema, key=key), payload


def _desired_epoch(artifact: Artifact, *, schema: str) -> tuple[date, int]:
    return _epoch(strict_json_object(artifact.body), schema=schema, key=artifact.key)


def _mutable_put_arguments(
    artifact: Artifact,
    prior: RemoteObject | None,
    *,
    bucket: str,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "Bucket": bucket,
        "Key": artifact.key,
        "Body": artifact.body,
        "ContentType": "application/json",
        "CacheControl": "no-cache",
        "Metadata": {"sha256": artifact.sha256},
    }
    if prior is None:
        arguments["IfNoneMatch"] = "*"
    elif prior.etag:
        arguments["IfMatch"] = prior.etag
    else:
        raise PublicationError(
            f"mutable discovery key lacks ETag for compare-and-swap: {artifact.key}"
        )
    return arguments


def _classify_existing(
    remote: RemoteObject,
    artifact: Artifact,
    *,
    schema: str,
) -> str:
    desired = _desired_epoch(artifact, schema=schema)
    current, _payload = _remote_epoch(remote, schema=schema, key=artifact.key)
    if current > desired:
        return "superseded"
    if current == desired:
        if _remote_matches(remote, artifact):
            return "idempotent"
        raise EpochCollisionError(f"same discovery epoch has different bytes: {artifact.key}")
    return "advance"


def _commit_index(client: Any, bucket: str, artifact: Artifact) -> str:
    """Commit the sole authoritative discovery object with monotonic CAS."""
    for _attempt in range(2):
        prior = _remote_object(client, bucket, artifact.key)
        if prior is not None:
            classification = _classify_existing(prior, artifact, schema=INDEX_SCHEMA)
            if classification == "idempotent":
                return classification
            if classification == "superseded":
                raise EpochRegressionError(
                    f"authoritative index already has a newer epoch: {artifact.key}"
                )
        arguments = _mutable_put_arguments(artifact, prior, bucket=bucket)
        try:
            response = client.put_object(**arguments)
        except Exception as exc:  # noqa: BLE001
            if _is_precondition_failed(exc):
                continue
            raise PublicationCommitUncertainError(
                f"global index commit outcome is uncertain: {artifact.key}: {exc}"
            ) from exc
        etag = response.get("ETag") if isinstance(response, Mapping) else None
        if not etag:
            raise PublicationCommitUncertainError(
                f"global index commit returned no ETag: {artifact.key}"
            )
        try:
            verified = _verify_remote(client, bucket, artifact)
        except Exception as exc:  # noqa: BLE001
            raise PublicationCommitUncertainError(
                f"global index commit could not be verified: {artifact.key}: {exc}"
            ) from exc
        if verified.etag != str(etag):
            raise PublicationCommitUncertainError(
                f"global index version changed during verification: {artifact.key}"
            )
        return "committed"
    raced = _remote_object(client, bucket, artifact.key)
    if raced is None:
        raise PublicationError(f"global index CAS lost without a visible winner: {artifact.key}")
    classification = _classify_existing(raced, artifact, schema=INDEX_SCHEMA)
    if classification == "idempotent":
        return classification
    if classification == "superseded":
        raise EpochRegressionError(
            f"global index CAS lost to a newer epoch: {artifact.key}"
        )
    raise PublicationError(f"global index CAS repeatedly lost to an older epoch: {artifact.key}")


def _repair_current(client: Any, bucket: str, artifact: Artifact) -> str:
    """Repair one non-authoritative convenience pointer without regression."""
    for _attempt in range(2):
        prior = _remote_object(client, bucket, artifact.key)
        if prior is not None:
            classification = _classify_existing(prior, artifact, schema=CURRENT_SCHEMA)
            if classification in {"idempotent", "superseded"}:
                return classification
        arguments = _mutable_put_arguments(artifact, prior, bucket=bucket)
        try:
            response = client.put_object(**arguments)
        except Exception as exc:  # noqa: BLE001
            if _is_precondition_failed(exc):
                continue
            raise PublicationError(f"derivative current repair failed: {artifact.key}") from exc
        etag = response.get("ETag") if isinstance(response, Mapping) else None
        if not etag:
            raise PublicationError(f"derivative current repair returned no ETag: {artifact.key}")
        verified = _verify_remote(client, bucket, artifact)
        if verified.etag != str(etag):
            raise PublicationError(
                f"derivative current changed during verification: {artifact.key}"
            )
        return "repaired"
    raced = _remote_object(client, bucket, artifact.key)
    if raced is None:
        raise PublicationError(f"derivative current CAS lost without a winner: {artifact.key}")
    classification = _classify_existing(raced, artifact, schema=CURRENT_SCHEMA)
    if classification in {"idempotent", "superseded"}:
        return classification
    raise PublicationError(f"derivative current CAS repeatedly lost: {artifact.key}")


def publish_bundle(
    bundle: PublicationBundle,
    *,
    client: Any,
    bucket: str,
) -> PublicationResult:
    """Commit one monotonic global index, then repair derivative root currents."""
    if not bucket:
        raise PublicationError("R2 bucket is required")
    # Immutable packet orphans are safe until the global index directly binds
    # their key/hash/size receipts.
    for root in sorted(bundle.immutable):
        _put_immutable(client, bucket, bundle.immutable[root])

    index_status = _commit_index(client, bucket, bundle.index)
    repaired: list[str] = []
    idempotent: list[str] = []
    superseded: list[str] = []
    failures: list[str] = []
    for root in sorted(bundle.currents):
        artifact = bundle.currents[root]
        try:
            status = _repair_current(client, bucket, artifact)
        except PublicationError as exc:
            failures.append(f"{artifact.key}: {exc}")
            continue
        if status == "repaired":
            repaired.append(root)
        elif status == "idempotent":
            idempotent.append(root)
        else:
            superseded.append(root)
    if failures:
        raise PublicationRepairNeededError(failures)
    return PublicationResult(
        index_status=index_status,
        currents_repaired=tuple(repaired),
        currents_idempotent=tuple(idempotent),
        currents_superseded=tuple(superseded),
    )


def _resolve_clock(value: str | None) -> str:
    if not value:
        raise OptionsStructureIntradayError(
            "a durable logical-run clock is required (pass --observed-at or use _meta.json asof)"
        )
    return _canonical_aware_clock(value, field="logical-run clock")


def _parse_session(value: str | None) -> str:
    if value:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise OptionsStructureIntradayError(f"invalid --session: {value!r}") from exc
        if parsed.isoformat() != value:
            raise OptionsStructureIntradayError(f"non-canonical --session: {value!r}")
        return value
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def main(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=config.data_dir() / "chain_snapshots",
        help="Private chain_snapshots directory",
    )
    parser.add_argument("--session", help="NYSE session date (YYYY-MM-DD)")
    parser.add_argument("--bucket", help="15-minute ET bucket (HH:MM); default: _meta.json")
    parser.add_argument("--roots", nargs="+", help="Exact complete root universe; default: discover session files")
    parser.add_argument("--meta", type=Path, help="Poller _meta.json; default: DATA_ROOT/_meta.json")
    parser.add_argument("--prophet-context", type=Path, help="Optional strict JSON object keyed by root")
    parser.add_argument("--observed-at", help="UTC builder clock override for deterministic replay")
    parser.add_argument(
        "--completion-packet-stdin",
        action="store_true",
        help="Read the producer's strict completion packet from stdin and bind all build inputs to it",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=config.data_dir() / "options_structure_intraday_r2",
        help="Local light-projection mirror root",
    )
    parser.add_argument("--no-local", action="store_true", help="Skip local mirror write")
    parser.add_argument("--publish", action="store_true", help="Publish the verified bundle to R2")
    parser.add_argument("--r2-bucket", help="R2 bucket override; default: R2_BUCKET")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        completion_packet: object | None = None
        if args.completion_packet_stdin:
            conflicting = {
                "--session": args.session,
                "--bucket": args.bucket,
                "--roots": args.roots,
                "--meta": args.meta,
                "--observed-at": args.observed_at,
            }
            named_conflicts = [name for name, value in conflicting.items() if value is not None]
            if named_conflicts:
                raise OptionsStructureIntradayError(
                    "completion packet owns build identity; remove "
                    + ", ".join(named_conflicts)
                )
            try:
                raw_packet = bucket_completion.strict_json_loads(sys.stdin.buffer.read())
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise OptionsStructureIntradayError(
                    f"invalid completion packet JSON: {exc}"
                ) from exc
            request = completion_request(raw_packet)
            completion_packet = raw_packet
            session_date = request.session_date
            snapshot_bucket = request.snapshot_bucket
            roots = list(request.roots)
            cadence = request.cadence_minutes
            observed_at = request.observed_at
            available_at = request.available_at
        else:
            meta_path = args.meta or args.data_root / "_meta.json"
            meta = _strict_json_path(meta_path)
            session_date = _parse_session(args.session or str(meta.get("session_date") or ""))
            snapshot_bucket = args.bucket or str(meta.get("bucket") or "")
            roots = (
                sorted(_safe_root(root) for root in args.roots)
                if args.roots
                else discover_roots(args.data_root, session_date)
            )
            cadence = validate_complete_meta(
                meta,
                session_date=session_date,
                snapshot_bucket=snapshot_bucket,
                roots=roots,
            )
            # Standalone/manual mode retains the legacy mutable-meta bridge.
            # The production hook always uses --completion-packet-stdin above.
            observed_at = _resolve_clock(args.observed_at or str(meta.get("asof") or ""))
            available_at = observed_at
        source_bytes = _source_input_bytes(args.data_root, roots, session_date)
        bundle = prepare_bundle(
            args.data_root,
            roots=roots,
            session_date=session_date,
            snapshot_bucket=snapshot_bucket,
            observed_at=observed_at,
            available_at=available_at,
            cadence_minutes=cadence,
            prophet_context=load_prophet_context(args.prophet_context),
            completion_evidence=(
                request.root_evidence if args.completion_packet_stdin else None
            ),
        )
        repair_error: PublicationRepairNeededError | None = None
        if args.publish:
            client = _r2_client()
            if client is None:
                raise PublicationError("R2 credentials or boto3 unavailable")
            bucket = args.r2_bucket or os.environ.get("R2_BUCKET", "")
            try:
                publish_bundle(bundle, client=client, bucket=bucket)
            except PublicationRepairNeededError as exc:
                # The authoritative index is already committed. Mirror it
                # locally, then return the honest repair-needed failure.
                repair_error = exc
        if not args.no_local:
            write_local_bundle(bundle, args.out_dir)
        if repair_error is not None:
            raise repair_error
        if args.publish and completion_packet is not None:
            if args.no_local:
                raise PublicationError(
                    "receipt-bound publication requires its durable local acknowledgement"
                )
            write_publication_ack(args.out_dir, completion_packet, bundle)
        log.info(
            "Light U-CHAIN ready: session=%s bucket=%s roots=%d packet_rows=%d "
            "publish=%s source_bytes=%d wall_sec=%.3f peak_rss_bytes=%d",
            session_date,
            snapshot_bucket,
            len(bundle.packets),
            sum(len(packet["contracts"]) for packet in bundle.packets.values()),
            args.publish,
            source_bytes,
            time.perf_counter() - started,
            _peak_rss_bytes(),
        )
        return 0
    except (OptionsStructureIntradayError, PublicationError) as exc:
        log.error("Light U-CHAIN failed closed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
