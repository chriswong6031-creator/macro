"""Durable producer-owned completion state for U-CHAIN snapshot buckets.

This module owns only the local M1 receipt protocol.  It deliberately has no
R2 client, publication path, consumer registration, or model authority.  The
physical ledger for one NYSE session is an append-only JSONL state machine:

    intent -> decision -> availability
       |          |
       +----------+-> incomplete

Only an ``availability`` terminal is a completed bucket.  ``incomplete`` is a
truthful terminal for an intent (or a decision whose availability receipt was
not captured) after its live bucket/session elapsed.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

from engine.session_digest import session_window_et
from lib import nyse_calendar


SCHEMA_ID = "chain_snapshots.bucket_completion/v1"
ET = ZoneInfo("America/New_York")
INTENT_CLOSE_GRACE = timedelta(minutes=1)
COMPLETION_CLOSE_WINDOW = timedelta(minutes=20)
# Cadences must produce a real-session bucket at the open+5 admission edge and
# an exact 13:00/16:00 close bucket on the midnight wall grid.  This small,
# governed set also prevents coercion of arbitrary config into bucket identity.
ALLOWED_CADENCE_MIN = (1, 2, 3, 4, 5, 6, 10, 15, 30)

_CLOCK_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_BUCKET_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_ROOT_RE = re.compile(r"^(?=.*[A-Z0-9])[A-Z0-9.^=-]{1,32}$")
_BUCKET_ID_RE = re.compile(r"^csb_[a-f0-9]{24}$")
_RECEIPT_ID_RE = re.compile(r"^csbr_[a-f0-9]{24}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_QUARANTINE_NAME_RE = re.compile(
    r"^[A-Za-z0-9._-]+\.corrupt-\d{8}T\d{12}Z\.parquet$"
)


class BucketStateError(RuntimeError):
    """The durable receipt state is corrupt, conflicting, or inadmissible."""


def _reject_duplicate_object_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON object key {key!r}")
        out[key] = value
    return out


def strict_json_loads(value: str | bytes):
    """Decode strict JSON: duplicate keys and non-finite constants are fatal."""
    return json.loads(
        value,
        object_pairs_hook=_reject_duplicate_object_pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {token}")
        ),
    )


def canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BucketStateError("bucket receipt requires strict finite JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _derived_id(prefix: str, payload: object) -> str:
    return prefix + hashlib.sha256(canonical_bytes(payload)).hexdigest()[:24]


def bucket_id(session_date: str, bucket: str) -> str:
    return _derived_id("csb_", [session_date, bucket])


def _with_receipt_id(payload: dict) -> dict:
    row = dict(payload)
    row["receipt_id"] = _derived_id("csbr_", payload)
    return row


def canonical_roots(roots: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Normalize and de-duplicate producer roots while preserving first order."""
    if not isinstance(roots, (list, tuple)):
        raise BucketStateError("bucket roots must be a list or tuple")
    seen: set[str] = set()
    out: list[str] = []
    for raw in roots:
        if type(raw) is not str:
            raise BucketStateError("bucket root must be a string")
        root = raw.strip().upper()
        if not root or not _ROOT_RE.fullmatch(root):
            raise BucketStateError(f"invalid canonical bucket root: {raw!r}")
        if root not in seen:
            seen.add(root)
            out.append(root)
    if not out:
        raise BucketStateError("bucket intent requires at least one root")
    return tuple(out)


def utc_microseconds(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise BucketStateError("bucket clock must be a timezone-aware datetime")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_clock(value: object, field: str) -> datetime:
    if type(value) is not str or not _CLOCK_RE.fullmatch(value):
        raise BucketStateError(f"{field} must be canonical UTC microseconds")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc,
        )
    except ValueError as exc:
        raise BucketStateError(f"{field} is not a real UTC clock") from exc
    if utc_microseconds(parsed) != value:
        raise BucketStateError(f"{field} must be canonical UTC microseconds")
    return parsed


def derive_bucket(now_et: datetime, cadence_min: int) -> str:
    if not isinstance(now_et, datetime) or now_et.tzinfo is None:
        raise BucketStateError("bucket derivation requires an aware clock")
    validate_cadence_min(cadence_min)
    local = now_et.astimezone(ET)
    minutes = local.hour * 60 + local.minute
    floored = (minutes // cadence_min) * cadence_min
    return f"{floored // 60:02d}:{floored % 60:02d}"


def validate_cadence_min(value: object) -> int:
    if type(value) is not int or value not in ALLOWED_CADENCE_MIN:
        allowed = ", ".join(str(item) for item in ALLOWED_CADENCE_MIN)
        raise BucketStateError(f"cadence_min must be one of the exact integers: {allowed}")
    return value


def _session_date(value: object) -> date:
    if type(value) is not str:
        raise BucketStateError("session_date must be a canonical date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise BucketStateError("session_date must be a canonical date") from exc
    if parsed.isoformat() != value or not nyse_calendar.is_session(parsed):
        raise BucketStateError(f"not an NYSE session: {value}")
    return parsed


def _inside_intent_window(session: date, now_et: datetime) -> bool:
    if now_et.tzinfo is None:
        return False
    local = now_et.astimezone(ET)
    if local.date() != session:
        return False
    open_et, close_et = session_window_et(session)
    start_et = open_et + timedelta(minutes=5)
    return start_et <= local < close_et + INTENT_CLOSE_GRACE


def validate_current_bucket(
    session_date: str,
    bucket: str,
    cadence_min: int,
    now: datetime,
) -> datetime:
    """Require a request to describe the actual live NYSE wall-clock bucket."""
    session = _session_date(session_date)
    if type(bucket) is not str or not _BUCKET_RE.fullmatch(bucket):
        raise BucketStateError("bucket must be canonical HH:MM")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise BucketStateError("current bucket admission requires an aware clock")
    local = now.astimezone(ET)
    if not _inside_intent_window(session, local):
        raise BucketStateError(
            f"no live chain-snapshot bucket at {utc_microseconds(now)} for {session_date}"
        )
    if derive_bucket(local, cadence_min) != bucket:
        raise BucketStateError("requested bucket does not match the current cadence bucket")
    open_et, _close_et = session_window_et(session)
    hour, minute = (int(part) for part in bucket.split(":"))
    bucket_at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if bucket_at < open_et:
        raise BucketStateError("requested cadence derives a pre-open bucket")
    return local


def _inside_completion_window(intent: dict, now: datetime) -> bool:
    """Decision/availability clock law after an admitted source start.

    Regular buckets end at their next cadence edge.  The actual NYSE close
    bucket alone may finish through the governed close+20m window; this never
    authorizes a new or retried source call after the one-minute source grace.
    """
    try:
        validate_current_bucket(
            intent["session_date"], intent["bucket"], intent["cadence_min"], now,
        )
        return True
    except BucketStateError:
        pass
    session = _session_date(intent["session_date"])
    local = now.astimezone(ET)
    if local.date() != session:
        return False
    _open_et, close_et = session_window_et(session)
    if intent["bucket"] != close_et.strftime("%H:%M"):
        return False
    return close_et <= local < close_et + COMPLETION_CLOSE_WINDOW


def _inside_availability_window(intent: dict, decision: dict, now: datetime) -> bool:
    """A durable decision may become honestly available later the same session."""
    decision_at = _parse_clock(decision.get("decision_at"), "decision_at")
    if not _inside_completion_window(intent, decision_at) or now < decision_at:
        return False
    session = _session_date(intent["session_date"])
    local = now.astimezone(ET)
    if local.date() != session:
        return False
    _open_et, close_et = session_window_et(session)
    return local < close_et + COMPLETION_CLOSE_WINDOW


def _validate_base_ids(row: dict) -> None:
    if row.get("schema") != SCHEMA_ID:
        raise BucketStateError("wrong bucket receipt schema")
    if type(row.get("bucket_id")) is not str or not _BUCKET_ID_RE.fullmatch(
        row["bucket_id"],
    ):
        raise BucketStateError("invalid bucket_id")
    if row["bucket_id"] != bucket_id(row.get("session_date"), row.get("bucket")):
        raise BucketStateError("bucket_id is not deterministic")
    if type(row.get("receipt_id")) is not str or not _RECEIPT_ID_RE.fullmatch(
        row["receipt_id"],
    ):
        raise BucketStateError("invalid receipt_id")
    payload = {key: value for key, value in row.items() if key != "receipt_id"}
    if row["receipt_id"] != _derived_id("csbr_", payload):
        raise BucketStateError("receipt_id is not deterministic")


def _validate_intent(row: dict, *, file_session: str) -> None:
    expected = {
        "schema", "kind", "bucket_id", "receipt_id", "session_date", "bucket",
        "cadence_min", "roots", "preexisting_target_roots", "intent_at",
    }
    if set(row) != expected or row.get("kind") != "intent":
        raise BucketStateError("invalid intent receipt shape")
    if row.get("session_date") != file_session:
        raise BucketStateError("intent session disagrees with ledger filename")
    session = _session_date(row["session_date"])
    validate_cadence_min(row.get("cadence_min"))
    roots = canonical_roots(row.get("roots"))
    if list(roots) != row["roots"]:
        raise BucketStateError("intent roots are not canonical and unique")
    preexisting = row.get("preexisting_target_roots")
    if not isinstance(preexisting, list):
        raise BucketStateError("intent preexisting_target_roots must be a list")
    if preexisting:
        normalized_preexisting = canonical_roots(preexisting)
        if list(normalized_preexisting) != preexisting:
            raise BucketStateError("intent preexisting_target_roots are not canonical")
        if not set(normalized_preexisting).issubset(roots):
            raise BucketStateError("intent preexisting roots leave the frozen universe")
    intent_at = _parse_clock(row.get("intent_at"), "intent_at")
    local = intent_at.astimezone(ET)
    if not _inside_intent_window(session, local):
        raise BucketStateError("intent_at is outside its actual NYSE session window")
    if derive_bucket(local, row["cadence_min"]) != row.get("bucket"):
        raise BucketStateError("intent_at does not derive to its recorded bucket")
    _validate_base_ids(row)


def _exact_nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise BucketStateError(f"{field} must be an exact non-negative integer")
    return value


def _sha256_field(value: object, field: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise BucketStateError(f"{field} must be a canonical SHA-256")
    return value


def _quarantine_names(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise BucketStateError(f"{field} must be a list")
    if any(
        type(item) is not str
        or not item
        or item != Path(item).name
        or "/" in item
        or not _QUARANTINE_NAME_RE.fullmatch(item)
        for item in value
    ):
        raise BucketStateError(f"{field} contains an invalid quarantine name")
    if value != sorted(set(value)):
        raise BucketStateError(f"{field} must be sorted and unique")
    return value


def _validate_completion(completion: object, intent: dict) -> None:
    expected = {
        "roots", "universe_n", "roots_ok", "roots_failed", "rows_appended",
        "rows_total", "bucket_rows", "oi_rows", "oi_total_rows",
        "first_prebucket_rows", "first_at_or_after_bucket_rows",
        "second_clock_matched_rows", "second_clock_unmatched_rows",
        "root_results", "result_sha256",
    }
    if not isinstance(completion, dict) or set(completion) != expected:
        raise BucketStateError("invalid completion summary shape")
    if completion.get("roots") != intent["roots"]:
        raise BucketStateError("completion roots drifted from frozen intent")
    root_results = completion.get("root_results")
    if not isinstance(root_results, list) or len(root_results) != len(intent["roots"]):
        raise BucketStateError("completion root_results do not cover frozen roots")
    integer_fields = (
        "universe_n", "roots_ok", "roots_failed", "rows_appended", "rows_total",
        "bucket_rows", "oi_rows", "oi_total_rows", "first_prebucket_rows",
        "first_at_or_after_bucket_rows", "second_clock_matched_rows",
        "second_clock_unmatched_rows",
    )
    for field in integer_fields:
        _exact_nonnegative_int(completion.get(field), f"completion.{field}")
    if (
        completion["universe_n"] != len(intent["roots"])
        or completion["roots_ok"] != len(intent["roots"])
        or completion["roots_failed"] != 0
    ):
        raise BucketStateError("completion counts do not prove a 100% successful sweep")
    expected_result_keys = {
        "root", "status", "rows_appended", "rows_total", "bucket_rows",
        "bucket_content_sha256", "parquet_sha256", "oi_rows", "oi_total_rows",
        "oi_parquet_sha256", "first_vendor_min_at", "first_vendor_max_at",
        "first_prebucket_rows", "first_at_or_after_bucket_rows",
        "second_clock_matched_rows", "second_clock_unmatched_rows",
        "quarantined", "oi_quarantined",
    }
    for expected_root, result in zip(intent["roots"], root_results, strict=True):
        if not isinstance(result, dict) or set(result) != expected_result_keys:
            raise BucketStateError("invalid per-root completion result shape")
        if result.get("root") != expected_root or result.get("status") != "ok":
            raise BucketStateError("completion root result order/status is invalid")
        for field in (
            "rows_appended", "rows_total", "bucket_rows", "oi_rows",
            "oi_total_rows", "first_prebucket_rows",
            "first_at_or_after_bucket_rows", "second_clock_matched_rows",
            "second_clock_unmatched_rows",
        ):
            _exact_nonnegative_int(result.get(field), f"root_result.{field}")
        if result["bucket_rows"] <= 0:
            raise BucketStateError("root bucket_rows must prove installed target rows")
        if result["oi_total_rows"] <= 0:
            raise BucketStateError("root oi_total_rows must prove installed OI")
        if result["rows_total"] < result["rows_appended"]:
            raise BucketStateError("root rows_total cannot trail rows_appended")
        if result["oi_total_rows"] < result["oi_rows"]:
            raise BucketStateError("root oi_total_rows cannot trail oi_rows")
        if result["rows_total"] < result["bucket_rows"]:
            raise BucketStateError("root rows_total cannot trail target bucket rows")
        if (
            result["first_prebucket_rows"] + result["first_at_or_after_bucket_rows"]
            != result["bucket_rows"]
        ):
            raise BucketStateError("first-order bucket-relative counts do not cover target rows")
        if (
            result["second_clock_matched_rows"] + result["second_clock_unmatched_rows"]
            != result["bucket_rows"]
        ):
            raise BucketStateError("second-order coverage counts do not cover target rows")
        for field in ("bucket_content_sha256", "parquet_sha256", "oi_parquet_sha256"):
            _sha256_field(result.get(field), f"root_result.{field}")
        first_min = _parse_clock(result.get("first_vendor_min_at"), "first_vendor_min_at")
        first_max = _parse_clock(result.get("first_vendor_max_at"), "first_vendor_max_at")
        if first_max < first_min:
            raise BucketStateError("first-order vendor clock range is inverted")
        for field in ("quarantined", "oi_quarantined"):
            _quarantine_names(result.get(field), f"root_result.{field}")
    sums = {
        "rows_appended": sum(result["rows_appended"] for result in root_results),
        "rows_total": sum(result["rows_total"] for result in root_results),
        "bucket_rows": sum(result["bucket_rows"] for result in root_results),
        "oi_rows": sum(result["oi_rows"] for result in root_results),
        "oi_total_rows": sum(result["oi_total_rows"] for result in root_results),
        "first_prebucket_rows": sum(
            result["first_prebucket_rows"] for result in root_results
        ),
        "first_at_or_after_bucket_rows": sum(
            result["first_at_or_after_bucket_rows"] for result in root_results
        ),
        "second_clock_matched_rows": sum(
            result["second_clock_matched_rows"] for result in root_results
        ),
        "second_clock_unmatched_rows": sum(
            result["second_clock_unmatched_rows"] for result in root_results
        ),
    }
    for field, total in sums.items():
        if completion[field] != total:
            raise BucketStateError(f"completion.{field} disagrees with root results")
    digest = completion.get("result_sha256")
    if type(digest) is not str or not _SHA256_RE.fullmatch(digest):
        raise BucketStateError("completion result_sha256 is invalid")
    digest_payload = {key: value for key, value in completion.items() if key != "result_sha256"}
    if digest != _sha256(digest_payload):
        raise BucketStateError("completion result_sha256 is not canonical")


def _validate_decision(row: dict, intent: dict) -> None:
    expected = {
        "schema", "kind", "bucket_id", "receipt_id", "session_date", "bucket",
        "intent_receipt_id", "intent_sha256", "decision_at", "completion",
    }
    if set(row) != expected or row.get("kind") != "decision":
        raise BucketStateError("invalid decision receipt shape")
    if row.get("bucket_id") != intent["bucket_id"]:
        raise BucketStateError("decision bucket_id drifted from intent")
    if row.get("session_date") != intent["session_date"] or row.get("bucket") != intent["bucket"]:
        raise BucketStateError("decision key drifted from intent")
    if row.get("intent_receipt_id") != intent["receipt_id"]:
        raise BucketStateError("decision does not bind the intent receipt id")
    if row.get("intent_sha256") != _sha256(intent):
        raise BucketStateError("decision does not bind the exact intent bytes")
    decision_at = _parse_clock(row.get("decision_at"), "decision_at")
    intent_at = _parse_clock(intent["intent_at"], "intent_at")
    if decision_at < intent_at:
        raise BucketStateError("decision_at predates intent_at")
    if decision_at.astimezone(ET).date().isoformat() != intent["session_date"]:
        raise BucketStateError("decision_at leaves the intent session date")
    if not _inside_completion_window(intent, decision_at):
        raise BucketStateError("decision_at is outside its causal bucket completion window")
    _validate_completion(row.get("completion"), intent)
    for result in row["completion"]["root_results"]:
        if _parse_clock(result["first_vendor_max_at"], "first_vendor_max_at") > decision_at:
            raise BucketStateError("first-order vendor clock is later than decision_at")
    _validate_base_ids(row)


def _validate_availability(row: dict, intent: dict, decision: dict) -> None:
    expected = {
        "schema", "kind", "bucket_id", "receipt_id", "session_date", "bucket",
        "intent_receipt_id", "decision_receipt_id", "decision_at", "availability_at",
    }
    if set(row) != expected or row.get("kind") != "availability":
        raise BucketStateError("invalid availability receipt shape")
    if (
        row.get("bucket_id") != intent["bucket_id"]
        or row.get("session_date") != intent["session_date"]
        or row.get("bucket") != intent["bucket"]
        or row.get("intent_receipt_id") != intent["receipt_id"]
        or row.get("decision_receipt_id") != decision["receipt_id"]
        or row.get("decision_at") != decision["decision_at"]
    ):
        raise BucketStateError("availability does not bind its intent and decision")
    decision_at = _parse_clock(decision["decision_at"], "decision_at")
    available_at = _parse_clock(row.get("availability_at"), "availability_at")
    if available_at < decision_at:
        raise BucketStateError("availability_at predates decision_at")
    if available_at.astimezone(ET).date().isoformat() != intent["session_date"]:
        raise BucketStateError("availability_at leaves the intent session date")
    if not _inside_availability_window(intent, decision, available_at):
        raise BucketStateError("availability_at is outside its causal bucket completion window")
    _validate_base_ids(row)


def _validate_incomplete(row: dict, intent: dict, decision: dict | None) -> None:
    expected = {
        "schema", "kind", "bucket_id", "receipt_id", "session_date", "bucket",
        "intent_receipt_id", "decision_receipt_id", "reason", "incomplete_at",
    }
    if set(row) != expected or row.get("kind") != "incomplete":
        raise BucketStateError("invalid incomplete receipt shape")
    expected_decision_id = decision["receipt_id"] if decision is not None else None
    if (
        row.get("bucket_id") != intent["bucket_id"]
        or row.get("session_date") != intent["session_date"]
        or row.get("bucket") != intent["bucket"]
        or row.get("intent_receipt_id") != intent["receipt_id"]
        or row.get("decision_receipt_id") != expected_decision_id
    ):
        raise BucketStateError("incomplete receipt does not bind its durable prefix")
    if row.get("reason") not in {"bucket_window_elapsed", "session_elapsed"}:
        raise BucketStateError("invalid incomplete terminal reason")
    incomplete_at = _parse_clock(row.get("incomplete_at"), "incomplete_at")
    prior = _parse_clock(
        decision["decision_at"] if decision is not None else intent["intent_at"],
        "prior durable clock",
    )
    if incomplete_at < prior:
        raise BucketStateError("incomplete_at predates its durable prefix")
    incomplete_session = incomplete_at.astimezone(ET).date().isoformat()
    if row["reason"] == "session_elapsed":
        if incomplete_session == intent["session_date"]:
            raise BucketStateError("session_elapsed requires a later ET date")
    else:
        if incomplete_session != intent["session_date"]:
            raise BucketStateError("bucket_window_elapsed cannot leave the intent session")
        admissible = (
            _inside_availability_window(intent, decision, incomplete_at)
            if decision is not None
            else BucketCompletionStore._pending_admissible(
                BucketState(intent=intent), incomplete_at,
            )
        )
        if admissible:
            raise BucketStateError("bucket_window_elapsed was recorded while bucket was live")
    _validate_base_ids(row)


@dataclass(frozen=True)
class BucketState:
    intent: dict
    decision: dict | None = None
    availability: dict | None = None
    incomplete: dict | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.intent["session_date"], self.intent["bucket"]

    @property
    def status(self) -> str:
        if self.availability is not None:
            return "complete"
        if self.incomplete is not None:
            return "incomplete"
        if self.decision is not None:
            return "decision"
        return "intent"


def validate_completion_packet(packet: object) -> BucketState:
    """Validate one in-memory ``intent -> decision -> availability`` packet.

    The poller passes this exact shape to its synchronous post-availability
    hook.  Reusing the ledger validators here prevents a downstream publisher
    from accepting a merely plausible session/bucket/root tuple that is not
    hash-bound to the producer's append-once receipts.
    """
    if type(packet) is not dict or set(packet) != {
        "intent", "decision", "availability",
    }:
        raise BucketStateError("invalid completion packet shape")
    if any(type(packet.get(key)) is not dict for key in packet):
        raise BucketStateError("completion packet records must be objects")

    intent = dict(packet["intent"])
    decision = dict(packet["decision"])
    availability = dict(packet["availability"])
    file_session = intent.get("session_date")
    if type(file_session) is not str:
        raise BucketStateError("completion packet session_date is missing")
    _validate_intent(intent, file_session=file_session)
    _validate_decision(decision, intent)
    _validate_availability(availability, intent, decision)
    return BucketState(
        intent=intent,
        decision=decision,
        availability=availability,
    )


def decode_ledger(raw: bytes, path: Path) -> list[BucketState]:
    """Parse a complete physical ledger, rejecting every ambiguous prefix."""
    if not raw:
        raise BucketStateError(f"empty bucket receipt ledger: {path}")
    if not raw.endswith(b"\n"):
        raise BucketStateError(f"torn bucket receipt ledger: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BucketStateError(f"bucket receipt ledger is not UTF-8: {path}") from exc
    file_session = path.stem
    _session_date(file_session)
    states: list[BucketState] = []
    active: BucketState | None = None
    prior_bucket_minutes = -1
    seen_keys: set[tuple[str, str]] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise BucketStateError(f"blank bucket receipt line {path}:{lineno}")
        try:
            row = strict_json_loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise BucketStateError(f"malformed bucket receipt {path}:{lineno}") from exc
        if not isinstance(row, dict):
            raise BucketStateError(f"bucket receipt is not an object {path}:{lineno}")
        if line.encode("utf-8") != canonical_bytes(row):
            raise BucketStateError(f"non-canonical physical JSON {path}:{lineno}")
        kind = row.get("kind")
        if active is None or active.status in {"complete", "incomplete"}:
            if kind != "intent":
                raise BucketStateError(f"bucket ledger must begin a state with intent {path}:{lineno}")
            _validate_intent(row, file_session=file_session)
            key = (row["session_date"], row["bucket"])
            if key in seen_keys:
                raise BucketStateError(f"duplicate bucket key in ledger: {key}")
            hour, minute = (int(part) for part in row["bucket"].split(":"))
            bucket_minutes = hour * 60 + minute
            if bucket_minutes <= prior_bucket_minutes:
                raise BucketStateError("bucket intents must be physically increasing")
            prior_bucket_minutes = bucket_minutes
            seen_keys.add(key)
            active = BucketState(intent=row)
            states.append(active)
            continue
        if active.status == "intent":
            if kind == "decision":
                _validate_decision(row, active.intent)
                active = BucketState(intent=active.intent, decision=row)
            elif kind == "incomplete":
                _validate_incomplete(row, active.intent, None)
                active = BucketState(intent=active.intent, incomplete=row)
            else:
                raise BucketStateError(f"intent must be followed by decision/incomplete {path}:{lineno}")
        elif active.status == "decision":
            if kind == "availability":
                _validate_availability(row, active.intent, active.decision)
                active = BucketState(
                    intent=active.intent,
                    decision=active.decision,
                    availability=row,
                )
            elif kind == "incomplete":
                _validate_incomplete(row, active.intent, active.decision)
                active = BucketState(
                    intent=active.intent,
                    decision=active.decision,
                    incomplete=row,
                )
            else:
                raise BucketStateError(
                    f"decision must be followed by availability/incomplete {path}:{lineno}"
                )
        states[-1] = active
    return states


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_directory_durable(path: Path) -> Path:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise BucketStateError(f"cannot resolve a durable parent for {path}")
        cursor = parent
    if not cursor.is_dir():
        raise BucketStateError(f"bucket receipt parent is not a directory: {cursor}")
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        if not directory.is_dir():
            raise BucketStateError(f"durable path component is not a directory: {directory}")
        _fsync_directory(directory)
        _fsync_directory(directory.parent)
    if not path.is_dir():
        raise BucketStateError(f"bucket receipt path is not a directory: {path}")
    # Reconfirm both the directory object and its parent even when the target
    # was already visible after an uncertain parent fsync in a prior process.
    _fsync_directory(path)
    if path.parent != path:
        _fsync_directory(path.parent)
    return path


def _confirm_path_durable(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def build_completion_summary(frozen_roots: tuple[str, ...], results: list[dict]) -> dict:
    """Build the canonical full-root receipt for a successful source sweep."""
    roots = canonical_roots(frozen_roots)
    by_root: dict[str, dict] = {}
    for result in results:
        if not isinstance(result, dict):
            raise BucketStateError("source sweep returned a non-object root result")
        root = result.get("root")
        if root not in roots or root in by_root:
            raise BucketStateError("source sweep returned duplicate or unexpected roots")
        if result.get("error") is not None:
            raise BucketStateError("cannot complete a bucket with a failed root")
        completion_errors = result.get("completion_errors")
        if not isinstance(completion_errors, list) or completion_errors:
            raise BucketStateError("cannot complete a bucket with incomplete source evidence")
        by_root[root] = result
    if set(by_root) != set(roots):
        raise BucketStateError("source sweep did not return every frozen root")
    root_results: list[dict] = []
    for root in roots:
        source = by_root[root]
        row = {
            "root": root,
            "status": "ok",
            "rows_appended": _exact_nonnegative_int(source.get("rows"), "rows"),
            "rows_total": _exact_nonnegative_int(source.get("total_rows"), "total_rows"),
            "bucket_rows": _exact_nonnegative_int(source.get("bucket_rows"), "bucket_rows"),
            "bucket_content_sha256": _sha256_field(
                source.get("bucket_content_sha256"), "bucket_content_sha256",
            ),
            "parquet_sha256": _sha256_field(
                source.get("parquet_sha256"), "parquet_sha256",
            ),
            "oi_rows": _exact_nonnegative_int(source.get("oi_rows"), "oi_rows"),
            "oi_total_rows": _exact_nonnegative_int(
                source.get("oi_total_rows"), "oi_total_rows",
            ),
            "oi_parquet_sha256": _sha256_field(
                source.get("oi_parquet_sha256"), "oi_parquet_sha256",
            ),
            "first_vendor_min_at": utc_microseconds(
                _parse_clock(source.get("first_vendor_min_at"), "first_vendor_min_at"),
            ),
            "first_vendor_max_at": utc_microseconds(
                _parse_clock(source.get("first_vendor_max_at"), "first_vendor_max_at"),
            ),
            "first_prebucket_rows": _exact_nonnegative_int(
                source.get("first_prebucket_rows"), "first_prebucket_rows",
            ),
            "first_at_or_after_bucket_rows": _exact_nonnegative_int(
                source.get("first_at_or_after_bucket_rows"),
                "first_at_or_after_bucket_rows",
            ),
            "second_clock_matched_rows": _exact_nonnegative_int(
                source.get("second_clock_matched_rows"), "second_clock_matched_rows",
            ),
            "second_clock_unmatched_rows": _exact_nonnegative_int(
                source.get("second_clock_unmatched_rows"), "second_clock_unmatched_rows",
            ),
            "quarantined": list(
                _quarantine_names(source.get("quarantined"), "quarantined")
            ),
            "oi_quarantined": list(
                _quarantine_names(source.get("oi_quarantined"), "oi_quarantined")
            ),
        }
        root_results.append(row)
    summary = {
        "roots": list(roots),
        "universe_n": len(roots),
        "roots_ok": len(roots),
        "roots_failed": 0,
        "rows_appended": sum(row["rows_appended"] for row in root_results),
        "rows_total": sum(row["rows_total"] for row in root_results),
        "bucket_rows": sum(row["bucket_rows"] for row in root_results),
        "oi_rows": sum(row["oi_rows"] for row in root_results),
        "oi_total_rows": sum(row["oi_total_rows"] for row in root_results),
        "first_prebucket_rows": sum(row["first_prebucket_rows"] for row in root_results),
        "first_at_or_after_bucket_rows": sum(
            row["first_at_or_after_bucket_rows"] for row in root_results
        ),
        "second_clock_matched_rows": sum(
            row["second_clock_matched_rows"] for row in root_results
        ),
        "second_clock_unmatched_rows": sum(
            row["second_clock_unmatched_rows"] for row in root_results
        ),
        "root_results": root_results,
    }
    summary["result_sha256"] = _sha256(summary)
    _validate_completion(summary, {"roots": list(roots)})
    return summary


class BucketCompletionStore:
    """Exclusive producer transaction over every local bucket receipt ledger."""

    def __init__(self, root: Path, *, now_fn: Callable[[], datetime] | None = None):
        self.root = Path(root)
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._lock_handle = None
        self._last_now: datetime | None = None

    def __enter__(self) -> "BucketCompletionStore":
        ensure_directory_durable(self.root)
        lock_path = self.root / ".writer.lock"
        existed = lock_path.exists()
        handle = lock_path.open("a+b")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if not existed:
            handle.flush()
            os.fsync(handle.fileno())
            _fsync_directory(self.root)
        self._lock_handle = handle
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._lock_handle is not None:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            self._lock_handle.close()
            self._lock_handle = None

    def _require_lock(self) -> None:
        if self._lock_handle is None:
            raise BucketStateError("bucket completion store is not writer-locked")

    def _now(self) -> datetime:
        value = self._now_fn()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise BucketStateError("bucket completion clock must be timezone-aware")
        value = value.astimezone(timezone.utc)
        if self._last_now is not None and value < self._last_now:
            raise BucketStateError("bucket completion clock moved backwards")
        self._last_now = value
        return value

    def _ledger_path(self, session_date: str) -> Path:
        return self.root / f"{session_date}.jsonl"

    def _load_states(self) -> dict[tuple[str, str], BucketState]:
        self._require_lock()
        out: dict[tuple[str, str], BucketState] = {}
        for path in sorted(self.root.glob("*.jsonl")):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
                raise BucketStateError(f"unexpected bucket receipt ledger name: {path}")
            try:
                # A visible file may come from a prior process whose parent
                # directory fsync was uncertain.  Reconfirm it before using
                # the prefix for any transition or source authorization.
                _confirm_path_durable(path)
                states = decode_ledger(path.read_bytes(), path)
            except OSError as exc:
                raise BucketStateError(f"cannot read bucket receipt ledger: {path}") from exc
            for state in states:
                if state.key in out:
                    raise BucketStateError(f"duplicate bucket state across ledgers: {state.key}")
                out[state.key] = state
        return out

    def _append(self, row: dict) -> BucketState:
        self._require_lock()
        path = self._ledger_path(row["session_date"])
        existed = path.exists()
        try:
            raw = path.read_bytes() if existed else b""
        except OSError as exc:
            raise BucketStateError(f"cannot preflight bucket receipt ledger: {path}") from exc
        encoded = canonical_bytes(row) + b"\n"
        # Validate the exact prospective physical prefix before appending its
        # first byte.  A bad transition must never corrupt a previously-valid
        # append-only ledger.
        prospective = raw + encoded
        prospective_states = decode_ledger(prospective, path)
        with path.open("a+b") as handle:
            handle.seek(0)
            if handle.read() != raw:
                raise BucketStateError("bucket receipt ledger changed outside the writer lock")
            handle.seek(0, os.SEEK_END)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
        return prospective_states[-1]

    def _make_intent(
        self,
        session_date: str,
        bucket: str,
        cadence_min: int,
        roots: tuple[str, ...],
        preexisting_target_roots: tuple[str, ...],
        intent_now: datetime,
    ) -> dict:
        stamp = utc_microseconds(intent_now)
        payload = {
            "schema": SCHEMA_ID,
            "kind": "intent",
            "bucket_id": bucket_id(session_date, bucket),
            "session_date": session_date,
            "bucket": bucket,
            "cadence_min": cadence_min,
            "roots": list(roots),
            "preexisting_target_roots": list(preexisting_target_roots),
            "intent_at": stamp,
        }
        return _with_receipt_id(payload)

    def _make_incomplete(
        self,
        state: BucketState,
        reason: str,
        *,
        incomplete_now: datetime | None = None,
    ) -> dict:
        payload = {
            "schema": SCHEMA_ID,
            "kind": "incomplete",
            "bucket_id": state.intent["bucket_id"],
            "session_date": state.intent["session_date"],
            "bucket": state.intent["bucket"],
            "intent_receipt_id": state.intent["receipt_id"],
            "decision_receipt_id": (
                state.decision["receipt_id"] if state.decision is not None else None
            ),
            "reason": reason,
            "incomplete_at": utc_microseconds(incomplete_now or self._now()),
        }
        return _with_receipt_id(payload)

    @staticmethod
    def _pending_admissible(state: BucketState, now: datetime) -> bool:
        try:
            validate_current_bucket(
                state.intent["session_date"],
                state.intent["bucket"],
                state.intent["cadence_min"],
                now,
            )
            return True
        except BucketStateError:
            return False

    @staticmethod
    def _state_admissible(state: BucketState, now: datetime) -> bool:
        if state.status == "decision":
            return _inside_availability_window(state.intent, state.decision, now)
        return BucketCompletionStore._pending_admissible(state, now)

    @staticmethod
    def _elapsed_reason(state: BucketState, now: datetime) -> str:
        current = now.astimezone(ET).date().isoformat()
        return "session_elapsed" if current != state.intent["session_date"] else "bucket_window_elapsed"

    def admit_current(
        self,
        *,
        session_date: str,
        bucket: str,
        cadence_min: int,
        roots: list[str] | tuple[str, ...],
        now: datetime,
        pre_intent_target_roots: Callable[[str, str, tuple[str, ...]], list[str] | tuple[str, ...]] | None = None,
    ) -> "BucketLease":
        """Reconcile elapsed tails, then recover/admit exactly one live bucket."""
        self._require_lock()
        requested_session = _session_date(session_date)
        validate_cadence_min(cadence_min)
        proposed_roots = canonical_roots(roots)
        if type(bucket) is not str or not _BUCKET_RE.fullmatch(bucket):
            raise BucketStateError("bucket must be canonical HH:MM")
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise BucketStateError("current bucket admission requires an aware clock")
        # The caller-captured clock identifies its requested key but cannot
        # authorize work after waiting on the writer lock.  Sample the durable
        # clock under lock and use it for every admission decision.
        admission_now = self._now()
        states = self._load_states()
        terminalized: list[dict] = []

        pending = sorted(
            (
                state for state in states.values()
                if state.status in {"intent", "decision"}
            ),
            key=lambda state: state.key,
        )
        # An admissible pending tail wins over current config/universe drift.
        admissible = [
            state for state in pending if self._state_admissible(state, admission_now)
        ]
        if len(admissible) > 1:
            raise BucketStateError("multiple live pending chain-snapshot buckets")

        # Never backfill elapsed intent/decision tails with a later live snapshot.
        for state in pending:
            if state in admissible:
                continue
            reason = self._elapsed_reason(state, admission_now)
            terminal = self._make_incomplete(
                state,
                reason,
                incomplete_now=admission_now,
            )
            state = self._append(terminal)
            terminalized.append(state.incomplete)

        if admissible:
            state = admissible[0]
            _confirm_path_durable(self._ledger_path(state.intent["session_date"]))
            return BucketLease(self, state, terminalized=terminalized, recovered=True)

        states = self._load_states()
        validate_current_bucket(session_date, bucket, cadence_min, admission_now)
        key = (session_date, bucket)
        existing = states.get(key)
        if existing is not None:
            _confirm_path_durable(self._ledger_path(session_date))
            return BucketLease(self, existing, terminalized=terminalized, recovered=True)

        preexisting: tuple[str, ...] = ()
        if pre_intent_target_roots is not None:
            raw_preexisting = pre_intent_target_roots(
                session_date, bucket, proposed_roots,
            )
            if not isinstance(raw_preexisting, (list, tuple)):
                raise BucketStateError("pre-intent target guard must return a list or tuple")
            if raw_preexisting:
                preexisting = canonical_roots(raw_preexisting)
                if not set(preexisting).issubset(proposed_roots):
                    raise BucketStateError("pre-intent target guard returned an unknown root")
        intent = self._make_intent(
            session_date,
            bucket,
            cadence_min,
            proposed_roots,
            preexisting,
            admission_now,
        )
        _validate_intent(intent, file_session=session_date)
        state = self._append(intent)
        return BucketLease(self, state, terminalized=terminalized, recovered=False)

    def refresh_before_source(self, state: BucketState) -> tuple[BucketState, datetime | None]:
        """Re-sample under lock; elapsed intent becomes terminal without source."""
        self._require_lock()
        current = self._load_states().get(state.key)
        if current is None or current.status != "intent" or current != state:
            raise BucketStateError("bucket is not in the exact intent state")
        source_now = self._now()
        if not self._pending_admissible(current, source_now):
            terminal = self._make_incomplete(
                current,
                self._elapsed_reason(current, source_now),
                incomplete_now=source_now,
            )
            return self._append(terminal), None
        _confirm_path_durable(self._ledger_path(current.intent["session_date"]))
        return current, source_now

    def append_decision(
        self,
        state: BucketState,
        completion: dict,
        *,
        require_live_bucket: bool = True,
    ) -> BucketState:
        self._require_lock()
        current = self._load_states().get(state.key)
        if current is None or current.status != "intent" or current.intent != state.intent:
            raise BucketStateError("bucket is not in the exact intent state")
        _validate_completion(completion, current.intent)
        decision_now = self._now()
        if require_live_bucket and not _inside_completion_window(
            current.intent, decision_now,
        ):
            terminal = self._make_incomplete(
                current,
                self._elapsed_reason(current, decision_now),
                incomplete_now=decision_now,
            )
            return self._append(terminal)
        payload = {
            "schema": SCHEMA_ID,
            "kind": "decision",
            "bucket_id": current.intent["bucket_id"],
            "session_date": current.intent["session_date"],
            "bucket": current.intent["bucket"],
            "intent_receipt_id": current.intent["receipt_id"],
            "intent_sha256": _sha256(current.intent),
            "decision_at": utc_microseconds(decision_now),
            "completion": completion,
        }
        row = _with_receipt_id(payload)
        _validate_decision(row, current.intent)
        return self._append(row)

    def append_availability(
        self,
        state: BucketState,
        *,
        require_live_bucket: bool = False,
        available_now: datetime | None = None,
    ) -> BucketState:
        self._require_lock()
        current = self._load_states().get(state.key)
        if current is None or current.status != "decision" or current != state:
            raise BucketStateError("bucket is not in the exact decision-only state")
        # Reconfirm a decision that may only be visible after an uncertain fsync
        # before observing the learning/publication availability clock.
        _confirm_path_durable(self._ledger_path(current.intent["session_date"]))
        available_now = available_now or self._now()
        if require_live_bucket and not _inside_availability_window(
            current.intent, current.decision, available_now,
        ):
            terminal = self._make_incomplete(
                current,
                self._elapsed_reason(current, available_now),
                incomplete_now=available_now,
            )
            return self._append(terminal)
        payload = {
            "schema": SCHEMA_ID,
            "kind": "availability",
            "bucket_id": current.intent["bucket_id"],
            "session_date": current.intent["session_date"],
            "bucket": current.intent["bucket"],
            "intent_receipt_id": current.intent["receipt_id"],
            "decision_receipt_id": current.decision["receipt_id"],
            "decision_at": current.decision["decision_at"],
            "availability_at": utc_microseconds(available_now),
        }
        row = _with_receipt_id(payload)
        _validate_availability(row, current.intent, current.decision)
        return self._append(row)

    def reconcile_without_source(self) -> list[dict]:
        """Drain decision/elapsed tails without config, universe, or source I/O."""
        self._require_lock()
        reconcile_now = self._now()
        states = self._load_states()
        actions: list[dict] = []
        for state in sorted(states.values(), key=lambda item: item.key):
            if state.status not in {"intent", "decision"}:
                continue
            if state.status == "decision" and _inside_availability_window(
                state.intent, state.decision, reconcile_now,
            ):
                completed = self.append_availability(
                    state,
                    require_live_bucket=True,
                    available_now=reconcile_now,
                )
                actions.append({
                    "bucket_id": completed.intent["bucket_id"],
                    "session_date": completed.intent["session_date"],
                    "bucket": completed.intent["bucket"],
                    "cadence_min": completed.intent["cadence_min"],
                    "receipt_state": "decision_recovered",
                    "availability_at": completed.availability["availability_at"],
                })
                continue
            if state.status == "intent" and self._pending_admissible(
                state, reconcile_now,
            ):
                continue
            terminal = self._make_incomplete(
                state,
                self._elapsed_reason(state, reconcile_now),
                incomplete_now=reconcile_now,
            )
            terminal_state = self._append(terminal)
            actions.append({
                "bucket_id": terminal_state.intent["bucket_id"],
                "session_date": terminal_state.intent["session_date"],
                "bucket": terminal_state.intent["bucket"],
                "cadence_min": terminal_state.intent["cadence_min"],
                "receipt_state": "incomplete",
                "receipt_incomplete_reason": terminal_state.incomplete["reason"],
            })
        return actions

    def confirm_complete(self, state: BucketState) -> BucketState:
        self._require_lock()
        current = self._load_states().get(state.key)
        if current is None or current.status != "complete" or current != state:
            raise BucketStateError("bucket is not in the exact complete state")
        _confirm_path_durable(self._ledger_path(current.intent["session_date"]))
        return self._load_states()[state.key]

    def complete_packet(self, session_date: str, bucket: str) -> dict:
        """Return one exact complete packet while retaining the writer lock."""
        self._require_lock()
        _session_date(session_date)
        if type(bucket) is not str or not _BUCKET_RE.fullmatch(bucket):
            raise BucketStateError("bucket must be canonical HH:MM")
        key = (session_date, bucket)
        state = self._load_states().get(key)
        if state is None or state.status != "complete":
            raise BucketStateError(f"bucket is not complete: {key}")
        _confirm_path_durable(self._ledger_path(session_date))
        confirmed = self._load_states().get(key)
        if confirmed is None or confirmed.status != "complete":
            raise BucketStateError(f"bucket completion changed during confirmation: {key}")
        if confirmed.decision is None or confirmed.availability is None:
            raise BucketStateError(f"bucket completion is missing its terminal prefix: {key}")
        return {
            "intent": dict(confirmed.intent),
            "decision": dict(confirmed.decision),
            "availability": dict(confirmed.availability),
        }

    def complete_packets_from(
        self,
        start_session: str,
        *,
        max_sessions: int = 2,
        require_start: bool = False,
    ) -> tuple[list[dict], tuple[dict, ...], bool]:
        """Return a bounded chronological completion window.

        Only ``start_session`` and the immediately following ledger are
        decoded with the default bound.  Directory names are inspected to
        report whether more ledgers remain, but older ledger bytes are never
        opened or fsynced.  A prior session must be terminal before a later
        ledger may enter the window; this makes a late completion before a
        delivery cursor fail closed instead of silently reordering the stream.
        """
        self._require_lock()
        _session_date(start_session)
        floor = start_session
        if type(max_sessions) is not int or max_sessions <= 0:
            raise BucketStateError("max_sessions must be a positive exact integer")
        paths: list[Path] = []
        for path in sorted(self.root.glob("*.jsonl")):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
                raise BucketStateError(f"unexpected bucket receipt ledger name: {path}")
            _session_date(path.stem)
            if path.stem >= floor:
                paths.append(path)
        if require_start and (not paths or paths[0].stem != floor):
            raise BucketStateError(
                f"publication cursor session ledger is missing: {floor}"
            )
        selected = paths[:max_sessions]
        packets: list[dict] = []
        session_receipts: list[dict] = []
        has_more = len(paths) > len(selected)
        for index, path in enumerate(selected):
            try:
                _confirm_path_durable(path)
                raw = path.read_bytes()
                states = decode_ledger(raw, path)
            except OSError as exc:
                raise BucketStateError(
                    f"cannot read bucket receipt ledger: {path}"
                ) from exc
            if index < len(selected) - 1 or has_more:
                pending = [
                    state.key for state in states
                    if state.status in {"intent", "decision"}
                ]
                if pending:
                    raise BucketStateError(
                        "nonterminal receipt session precedes a later ledger: "
                        f"{path.stem} {pending}"
                    )
            for state in states:
                if state.status != "complete":
                    continue
                if state.decision is None or state.availability is None:
                    raise BucketStateError(
                        f"complete state is missing its terminal prefix: {state.key}"
                    )
                packets.append({
                    "intent": dict(state.intent),
                    "decision": dict(state.decision),
                    "availability": dict(state.availability),
                })
            session_receipts.append({
                "session_date": path.stem,
                "ledger_sha256": hashlib.sha256(raw).hexdigest(),
                "complete_count": sum(
                    state.status == "complete" for state in states
                ),
                "terminal": not any(
                    state.status in {"intent", "decision"} for state in states
                ),
            })
        return packets, tuple(session_receipts), has_more

    def confirm_terminal_session_step(
        self,
        *,
        sealed_session: str,
        sealed_ledger_sha256: str,
        next_session: str,
    ) -> tuple[list[dict], dict]:
        """Re-prove one bounded scan-cursor hop against source ledger bytes."""
        self._require_lock()
        _session_date(sealed_session)
        _session_date(next_session)
        if (
            type(sealed_ledger_sha256) is not str
            or not _SHA256_RE.fullmatch(sealed_ledger_sha256)
        ):
            raise BucketStateError("sealed ledger hash is invalid")
        if next_session <= sealed_session:
            raise BucketStateError("terminal session step must move forward")
        paths: list[Path] = []
        for path in sorted(self.root.glob("*.jsonl")):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
                raise BucketStateError(f"unexpected bucket receipt ledger name: {path}")
            _session_date(path.stem)
            paths.append(path)
        sealed_path = self._ledger_path(sealed_session)
        if sealed_path not in paths:
            raise BucketStateError(
                f"sealed publication scan ledger is missing: {sealed_session}"
            )
        following = [path.stem for path in paths if path.stem > sealed_session]
        if not following or following[0] != next_session:
            raise BucketStateError(
                "publication scan cursor skipped the immediate next source ledger"
            )
        _confirm_path_durable(sealed_path)
        raw = sealed_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sealed_ledger_sha256:
            raise BucketStateError("sealed publication scan ledger hash drifted")
        states = decode_ledger(raw, sealed_path)
        pending = [
            state.key for state in states
            if state.status in {"intent", "decision"}
        ]
        if pending:
            raise BucketStateError(
                f"sealed publication scan ledger is nonterminal: {pending}"
            )
        packets: list[dict] = []
        for state in states:
            if state.status != "complete":
                continue
            if state.decision is None or state.availability is None:
                raise BucketStateError(
                    f"complete state is missing its terminal prefix: {state.key}"
                )
            packets.append({
                "intent": dict(state.intent),
                "decision": dict(state.decision),
                "availability": dict(state.availability),
            })
        return packets, {
            "session_date": sealed_session,
            "ledger_sha256": sealed_ledger_sha256,
            "complete_count": len(packets),
            "terminal": True,
        }


@dataclass
class BucketLease:
    store: BucketCompletionStore
    state: BucketState
    terminalized: list[dict]
    recovered: bool

    @property
    def status(self) -> str:
        return self.state.status

    @property
    def roots(self) -> tuple[str, ...]:
        return tuple(self.state.intent["roots"])

    @property
    def session_date(self) -> str:
        return self.state.intent["session_date"]

    @property
    def bucket(self) -> str:
        return self.state.intent["bucket"]

    @property
    def cadence_min(self) -> int:
        return self.state.intent["cadence_min"]

    @property
    def preexisting_target_roots(self) -> tuple[str, ...]:
        return tuple(self.state.intent["preexisting_target_roots"])

    def refresh_before_source(self) -> datetime | None:
        self.state, source_now = self.store.refresh_before_source(self.state)
        return source_now

    def record_decision(
        self,
        completion: dict,
        *,
        require_live_bucket: bool = True,
    ) -> BucketState:
        self.state = self.store.append_decision(
            self.state,
            completion,
            require_live_bucket=require_live_bucket,
        )
        return self.state

    def record_availability(self, *, require_live_bucket: bool = True) -> BucketState:
        self.state = self.store.append_availability(
            self.state,
            require_live_bucket=require_live_bucket,
        )
        return self.state

    def confirm_complete(self) -> BucketState:
        self.state = self.store.confirm_complete(self.state)
        return self.state

    def packet(self) -> dict:
        if self.state.status != "complete":
            raise BucketStateError("only a durable availability state has a completion packet")
        return {
            "intent": dict(self.state.intent),
            "decision": dict(self.state.decision),
            "availability": dict(self.state.availability),
        }


@contextmanager
def locked_bucket_lease(
    root: Path,
    *,
    session_date: str,
    bucket: str,
    cadence_min: int,
    roots: list[str] | tuple[str, ...],
    now: datetime,
    now_fn: Callable[[], datetime] | None = None,
    pre_intent_target_roots: Callable[
        [str, str, tuple[str, ...]], list[str] | tuple[str, ...]
    ] | None = None,
) -> Iterator[BucketLease]:
    """Hold the sole-writer lock through source writes and any future hook."""
    with BucketCompletionStore(root, now_fn=now_fn) as store:
        yield store.admit_current(
            session_date=session_date,
            bucket=bucket,
            cadence_min=cadence_min,
            roots=roots,
            now=now,
            pre_intent_target_roots=pre_intent_target_roots,
        )


def reconcile_existing_receipts(
    root: Path,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> list[dict]:
    """Recovery-only startup drain; a missing receipt root is a true no-op."""
    path = Path(root)
    if not path.exists():
        return []
    if not path.is_dir():
        raise BucketStateError(f"bucket receipt root is not a directory: {path}")
    with BucketCompletionStore(path, now_fn=now_fn) as store:
        return store.reconcile_without_source()
