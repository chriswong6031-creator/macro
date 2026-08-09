"""Fail-closed W0b focused vendor-snapshot quote contracts.

This module has no authority to select an underlying or option, rank a row,
issue a signal, size a position, or describe a quote as executable.  Its input
is an explicitly ordered list of one to twelve already-eligible W0a contract
identities. It first binds the exact W0a-B producer-complete ledger state, then
verifies the W0a index and every immutable packet before authorizing one
full-chain ThetaData first-order snapshot call per unique requested root.

Only vendor snapshot bid/ask values are projected.  The endpoint does not carry
the size, venue, or condition evidence needed to claim NBBO/live/current/
executable semantics.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from engine import chain_snapshot_completion as w0a_completion


SCHEMA = "options.focused_quote_attempt/v1"
W0A_INDEX_SCHEMA = "options.contract_eligibility.index/v1"
W0A_PACKET_SCHEMA = "options.contract_eligibility/v1"
W0A_INDEX_KEY = "options_structure/msc_intraday/index.json"
W0A_COMPLETION_LEDGER_PREFIX = "chain_snapshots/_bucket_receipts"
W0A_PACKET_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts/options/options.contract_eligibility.v1.schema.json"
)
W0A_INDEX_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts/options/options.contract_eligibility.index.v1.schema.json"
)

SOURCE_ENDPOINT = "/v3/option/snapshot/greeks/first_order"
SOURCE_QUOTE_LABEL = "vendor_snapshot_bid_ask"
RECOVERY_DEADLINE_SECONDS = 300
MAX_INPUTS = 12
W0A_AUTHORITY_KEYS = frozenset({
    "rank_authority",
    "gate_authority",
    "sizing_authority",
    "issue_authority",
    "trade_authority",
    "prophet_authority",
})

_ROOT_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9.-]{0,13}[A-Z0-9])?$")
_OCC_ROOT_RE = re.compile(r"^[A-Z0-9]{1,6}$")
_PROFILE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CONTRACT_ID_RE = re.compile(r"^contract:uchain:[a-f0-9]{64}$")
_PACKET_ID_RE = re.compile(r"^packet:uchain:[a-f0-9]{64}$")
_INDEX_ID_RE = re.compile(r"^index:uchain:[a-f0-9]{64}$")
_SHA_RE = re.compile(r"^[a-f0-9]{64}$")
_EPOCH_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})/((?:0\d|1\d|2[0-3]):(?:00|15|30|45))$"
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DECIMAL_RE = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?$")
_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)
_ATTEMPT_RE = re.compile(r"^attempt:focused_quote:[a-f0-9]{64}$")
_DECISION_RE = re.compile(r"^decision:focused_quote:[a-f0-9]{64}$")
_RECEIPT_RE = re.compile(r"^receipt:focused_quote:[a-f0-9]{64}$")

ET = ZoneInfo("America/New_York")
_W0A_VALIDATORS: dict[str, Any] = {}


class FocusedQuoteError(ValueError):
    """The W0b attempt or one of its causal inputs violates the contract."""


class W0AAttestationError(FocusedQuoteError):
    """Exact W0a bytes, identities, or receipts could not be verified."""


class FocusedQuoteClockError(FocusedQuoteError):
    """A clock is malformed, non-causal, or cannot be represented exactly."""


def authority_block() -> dict[str, bool]:
    """All downstream decision authority is false by construction."""
    return {
        "rank_authority": False,
        "gate_authority": False,
        "sizing_authority": False,
        "issue_authority": False,
        "trade_authority": False,
        "prophet_authority": False,
        "neural_web_authority": False,
    }


def quote_semantics() -> dict[str, object]:
    """The strongest truthful label supported by the first-order endpoint."""
    return {
        "endpoint": SOURCE_ENDPOINT,
        "label": SOURCE_QUOTE_LABEL,
        "nbbo": False,
        "live": False,
        "current": False,
        "executable": False,
        "sizes_available": False,
        "venues_available": False,
        "conditions_available": False,
        "trade_quote_spliced": False,
    }


def canonical_json_bytes(payload: object) -> bytes:
    """Encode strict deterministic JSON with one final newline."""
    try:
        return (
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise FocusedQuoteError(f"payload is not strict canonical JSON: {exc}") from exc


def strict_json_value(body: bytes) -> Any:
    """Decode strict UTF-8 JSON, rejecting duplicate keys and NaN constants."""
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in values:
            if key in out:
                raise FocusedQuoteError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def constant(value: str) -> None:
        raise FocusedQuoteError(f"non-finite JSON number: {value}")

    try:
        return json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FocusedQuoteError(f"invalid JSON: {exc}") from exc


def strict_json_object(body: bytes) -> dict[str, Any]:
    value = strict_json_value(body)
    if not isinstance(value, dict):
        raise FocusedQuoteError("JSON root must be an object")
    return value


def _w0a_schema_validator(kind: str) -> Any:
    cached = _W0A_VALIDATORS.get(kind)
    if cached is not None:
        return cached
    paths = {
        "index": W0A_INDEX_SCHEMA_PATH,
        "packet": W0A_PACKET_SCHEMA_PATH,
    }
    schema_path = paths.get(kind)
    if schema_path is None:
        raise W0AAttestationError(f"unknown W0a schema kind: {kind}")
    try:
        from jsonschema import Draft202012Validator, FormatChecker  # noqa: PLC0415

        schema = strict_json_object(schema_path.read_bytes())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )
    except Exception as exc:  # noqa: BLE001 - schema availability is mandatory
        raise W0AAttestationError(
            f"W0a {kind} schema unavailable or invalid: {schema_path}: {exc}"
        ) from exc
    _W0A_VALIDATORS[kind] = validator
    return validator


def _validate_w0a_schema(
    payload: Mapping[str, Any],
    *,
    kind: str,
    label: str,
) -> None:
    try:
        errors = sorted(
            _w0a_schema_validator(kind).iter_errors(payload),
            key=lambda error: "/".join(str(item) for item in error.path),
        )
    except W0AAttestationError:
        raise
    except Exception as exc:  # noqa: BLE001 - validator execution fails closed
        raise W0AAttestationError(f"{label} schema validation failed: {exc}") from exc
    if errors:
        summary = "; ".join(
            f"{'/'.join(str(item) for item in error.path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise W0AAttestationError(f"{label} schema validation failed: {summary}")


def _require_canonical_object(body: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = strict_json_object(body)
    except FocusedQuoteError as exc:
        raise W0AAttestationError(f"{label} is not strict JSON: {exc}") from exc
    if canonical_json_bytes(payload) != body:
        raise W0AAttestationError(f"{label} bytes are not canonical JSON")
    return payload


def _safe_root(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or value != value.upper()
        or not _ROOT_RE.fullmatch(value)
        or ".." in value
    ):
        raise FocusedQuoteError(f"unsafe root: {value!r}")
    return value


def _safe_profile(value: object) -> str:
    if not isinstance(value, str) or not _PROFILE_RE.fullmatch(value):
        raise FocusedQuoteError(f"invalid profile_id: {value!r}")
    return value


def _safe_contract_id(value: object) -> str:
    if not isinstance(value, str) or not _CONTRACT_ID_RE.fullmatch(value):
        raise FocusedQuoteError(f"invalid contract_id: {value!r}")
    return value


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise W0AAttestationError(f"invalid {field}: {value!r}")
    return value


def _exact_utc(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        raise FocusedQuoteClockError(f"invalid {field}: {value!r}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FocusedQuoteClockError(f"invalid {field}: {value!r}") from exc
    if _iso_utc(parsed) != value:
        raise FocusedQuoteClockError(f"non-canonical {field}: {value!r}")
    return parsed


def _utc_clock(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise FocusedQuoteClockError(f"{field} must be timezone-aware")
    if value.utcoffset() is None:
        raise FocusedQuoteClockError(f"{field} has no UTC offset")
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _date(value: object, *, field: str) -> date:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise W0AAttestationError(f"invalid {field}: {value!r}")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise W0AAttestationError(f"invalid {field}: {value!r}") from exc
    if parsed.isoformat() != value:
        raise W0AAttestationError(f"non-canonical {field}: {value!r}")
    return parsed


def _canonical_positive_decimal(value: object, *, field: str) -> tuple[Decimal, str]:
    if not isinstance(value, str) or not _DECIMAL_RE.fullmatch(value):
        raise W0AAttestationError(f"invalid {field}: {value!r}")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise W0AAttestationError(f"invalid {field}: {value!r}") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise W0AAttestationError(f"invalid {field}: {value!r}")
    canonical = format(parsed, "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    if canonical != value:
        raise W0AAttestationError(f"non-canonical {field}: {value!r}")
    return parsed, canonical


def _identity_digest(prefix: str, payload: Mapping[str, Any], identity_key: str) -> str:
    identity = dict(payload)
    identity.pop(identity_key, None)
    return f"{prefix}{sha256(canonical_json_bytes(identity)).hexdigest()}"


def _require_false_authority(value: object, *, label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != W0A_AUTHORITY_KEYS:
        raise W0AAttestationError(f"{label} authority shape is malformed")
    if any(value[key] is not False for key in W0A_AUTHORITY_KEYS):
        raise W0AAttestationError(f"{label} carries non-false authority")


def _unique_ids(
    value: object,
    *,
    pattern: re.Pattern[str],
    label: str,
) -> list[str]:
    if not isinstance(value, list):
        raise W0AAttestationError(f"{label} is not an array")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not pattern.fullmatch(item):
            raise W0AAttestationError(f"{label} carries a malformed identity")
        if item in seen:
            raise W0AAttestationError(f"{label} carries a duplicate identity")
        seen.add(item)
        out.append(item)
    return out


def normalize_inputs(values: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Validate and preserve an exact one-to-twelve input order."""
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise FocusedQuoteError("inputs must be an ordered array")
    if not 1 <= len(values) <= MAX_INPUTS:
        raise FocusedQuoteError(f"inputs must contain 1..{MAX_INPUTS} rows")
    out: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for ordinal, raw in enumerate(values, start=1):
        if not isinstance(raw, Mapping) or set(raw) != {
            "root", "profile_id", "contract_id"
        }:
            raise FocusedQuoteError(
                f"input {ordinal} must contain exactly root, profile_id, contract_id"
            )
        root = _safe_root(raw["root"])
        profile_id = _safe_profile(raw["profile_id"])
        contract_id = _safe_contract_id(raw["contract_id"])
        identity = (root, profile_id, contract_id)
        if identity in seen:
            raise FocusedQuoteError(f"duplicate explicit input at ordinal {ordinal}")
        seen.add(identity)
        out.append({
            "ordinal": ordinal,
            "root": root,
            "profile_id": profile_id,
            "contract_id": contract_id,
        })
    return out


def _first_root_order(inputs: Sequence[Mapping[str, object]]) -> list[str]:
    seen: set[str] = set()
    roots: list[str] = []
    for item in inputs:
        root = str(item["root"])
        if root not in seen:
            seen.add(root)
            roots.append(root)
    return roots


def _verify_index(index_key: str, body: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    if index_key != W0A_INDEX_KEY:
        raise W0AAttestationError(f"unexpected W0a index key: {index_key!r}")
    payload = _require_canonical_object(body, label="W0a index")
    _validate_w0a_schema(payload, kind="index", label="W0a index")
    if payload.get("schema") != W0A_INDEX_SCHEMA:
        raise W0AAttestationError("W0a index schema mismatch")
    index_id = payload.get("index_id")
    if not isinstance(index_id, str) or not _INDEX_ID_RE.fullmatch(index_id):
        raise W0AAttestationError("W0a index_id is malformed")
    if index_id != _identity_digest("index:uchain:", payload, "index_id"):
        raise W0AAttestationError("W0a index_id does not bind the exact index bytes")
    epoch = payload.get("epoch")
    if not isinstance(epoch, str) or not _EPOCH_RE.fullmatch(epoch):
        raise W0AAttestationError("W0a index epoch is malformed")
    epoch_match = _EPOCH_RE.fullmatch(epoch)
    assert epoch_match is not None
    session_date, snapshot_bucket = epoch_match.groups()
    _date(session_date, field="W0a index epoch date")
    if payload.get("session_date") != session_date:
        raise W0AAttestationError("W0a index session_date/epoch mismatch")
    if payload.get("snapshot_bucket") != snapshot_bucket:
        raise W0AAttestationError("W0a index snapshot_bucket/epoch mismatch")
    _exact_utc(payload.get("available_at"), field="W0a index available_at")
    if payload.get("complete_bucket") is not True:
        raise W0AAttestationError("W0a index is not a complete bucket")
    if payload.get("authoritative_discovery") is not True:
        raise W0AAttestationError("W0a index is not the authoritative discovery commit")
    if payload.get("commit_role") != "sole_authoritative_global_index":
        raise W0AAttestationError("W0a index commit role is malformed")
    roots = payload.get("roots")
    if not isinstance(roots, list) or not roots:
        raise W0AAttestationError("W0a index roots are absent")
    if _exact_int(payload.get("root_count"), field="W0a root_count", minimum=1) != len(roots):
        raise W0AAttestationError("W0a index root_count mismatch")
    _require_false_authority(payload.get("authority"), label="W0a index")
    attestation = {
        "key": index_key,
        "sha256": sha256(body).hexdigest(),
        "bytes": len(body),
        "index_id": index_id,
        "epoch": epoch,
    }
    return payload, attestation


def _verify_object_receipt(
    raw: object,
    *,
    root: str,
    epoch: str,
) -> dict[str, object]:
    if not isinstance(raw, Mapping) or set(raw) != {
        "key", "sha256", "bytes", "packet_id"
    }:
        raise W0AAttestationError(f"W0a object receipt for {root} is malformed")
    key = raw.get("key")
    digest = raw.get("sha256")
    size = raw.get("bytes")
    packet_id = raw.get("packet_id")
    if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
        raise W0AAttestationError(f"W0a object sha256 for {root} is malformed")
    if not isinstance(packet_id, str) or not _PACKET_ID_RE.fullmatch(packet_id):
        raise W0AAttestationError(f"W0a packet_id for {root} is malformed")
    size = _exact_int(size, field=f"W0a object bytes for {root}", minimum=1)
    match = _EPOCH_RE.fullmatch(epoch)
    assert match is not None
    session_date, bucket = match.groups()
    expected_key = (
        f"options_structure/msc_intraday/{root}/{session_date}/"
        f"{bucket.replace(':', '')}.json"
    )
    if key != expected_key:
        raise W0AAttestationError(f"W0a immutable packet key mismatch for {root}")
    return {"key": key, "sha256": digest, "bytes": size, "packet_id": packet_id}


def _verify_packet(
    body: bytes,
    receipt: Mapping[str, object],
    *,
    root: str,
    epoch: str,
    index_available_at: str,
) -> dict[str, Any]:
    if len(body) != receipt["bytes"]:
        raise W0AAttestationError(f"W0a packet byte count mismatch for {root}")
    if sha256(body).hexdigest() != receipt["sha256"]:
        raise W0AAttestationError(f"W0a packet digest mismatch for {root}")
    payload = _require_canonical_object(body, label=f"W0a packet {root}")
    _validate_w0a_schema(payload, kind="packet", label=f"W0a packet {root}")
    if payload.get("schema") != W0A_PACKET_SCHEMA:
        raise W0AAttestationError(f"W0a packet schema mismatch for {root}")
    if payload.get("packet_id") != receipt["packet_id"]:
        raise W0AAttestationError(f"W0a packet receipt identity mismatch for {root}")
    if payload.get("packet_id") != _identity_digest(
        "packet:uchain:", payload, "packet_id"
    ):
        raise W0AAttestationError(f"W0a packet_id does not bind exact bytes for {root}")
    if payload.get("root") != root:
        raise W0AAttestationError(f"W0a packet root mismatch for {root}")
    match = _EPOCH_RE.fullmatch(epoch)
    assert match is not None
    session_date, bucket = match.groups()
    session = payload.get("session")
    if not isinstance(session, Mapping):
        raise W0AAttestationError(f"W0a packet session is malformed for {root}")
    if session.get("date") != session_date or session.get("snapshot_bucket") != bucket:
        raise W0AAttestationError(f"W0a packet epoch mismatch for {root}")
    clocks = payload.get("clocks")
    if not isinstance(clocks, Mapping):
        raise W0AAttestationError(f"W0a packet clocks are malformed for {root}")
    _exact_utc(clocks.get("available_at"), field=f"W0a packet available_at for {root}")
    if clocks.get("available_at") != index_available_at:
        raise W0AAttestationError(f"W0a packet/index available_at mismatch for {root}")
    _require_false_authority(payload.get("authority"), label=f"W0a packet {root}")
    return payload


def _verify_completion_ledger(
    body: bytes,
    *,
    index: Mapping[str, Any],
    indexed_root_order: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    """Decode and bind the exact producer-complete state for this W0a epoch."""
    if not isinstance(body, bytes):
        raise W0AAttestationError("W0a completion ledger input must be exact bytes")
    session_date = str(index["session_date"])
    snapshot_bucket = str(index["snapshot_bucket"])
    ledger_key = f"{W0A_COMPLETION_LEDGER_PREFIX}/{session_date}.jsonl"
    try:
        states = w0a_completion.decode_ledger(body, Path(f"{session_date}.jsonl"))
    except (w0a_completion.BucketStateError, OSError, ValueError) as exc:
        raise W0AAttestationError("W0a completion ledger is invalid") from exc
    matches = [
        state for state in states
        if state.key == (session_date, snapshot_bucket)
    ]
    if len(matches) != 1 or matches[0].status != "complete":
        raise W0AAttestationError(
            "W0a epoch lacks one exact producer-complete ledger state"
        )
    state = matches[0]
    if state.decision is None or state.availability is None:
        raise W0AAttestationError("W0a producer completion state is incomplete")
    intent = state.intent
    decision = state.decision
    availability = state.availability
    completion_roots = list(intent["roots"])
    if (
        len(completion_roots) != len(indexed_root_order)
        or set(completion_roots) != set(indexed_root_order)
        or int(decision["completion"]["universe_n"]) != len(indexed_root_order)
    ):
        raise W0AAttestationError(
            "W0a index roots do not exactly match producer completion roots"
        )
    index_available = _exact_utc(
        index.get("available_at"), field="W0a index available_at"
    )
    producer_available = _exact_utc(
        availability.get("availability_at"),
        field="W0a producer availability_at",
    )
    if index_available < producer_available:
        raise W0AAttestationError(
            "W0a index available_at predates producer availability"
        )
    root_results = {
        str(result["root"]): result
        for result in decision["completion"]["root_results"]
    }
    if set(root_results) != set(indexed_root_order):
        raise W0AAttestationError(
            "W0a completion results do not exactly cover index roots"
        )

    records = (intent, decision, availability)
    record_bodies = [w0a_completion.canonical_bytes(record) for record in records]
    state_body = b"".join(record_body + b"\n" for record_body in record_bodies)
    attestation = {
        "schema": w0a_completion.SCHEMA_ID,
        "ledger_key": ledger_key,
        "state": "complete",
        "state_sha256": sha256(state_body).hexdigest(),
        "state_bytes": len(state_body),
        "bucket_id": intent["bucket_id"],
        "session_date": session_date,
        "snapshot_bucket": snapshot_bucket,
        "cadence_minutes": intent["cadence_min"],
        "root_count": len(completion_roots),
        "roots": completion_roots,
        "intent": {
            "receipt_id": intent["receipt_id"],
            "sha256": sha256(record_bodies[0]).hexdigest(),
            "intent_at": intent["intent_at"],
        },
        "decision": {
            "receipt_id": decision["receipt_id"],
            "sha256": sha256(record_bodies[1]).hexdigest(),
            "decision_at": decision["decision_at"],
            "completion_result_sha256": decision["completion"]["result_sha256"],
        },
        "availability": {
            "receipt_id": availability["receipt_id"],
            "sha256": sha256(record_bodies[2]).hexdigest(),
            "availability_at": availability["availability_at"],
        },
    }
    return attestation, root_results


def _verify_packet_completion(
    packet: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    root: str,
    cadence_minutes: int,
) -> None:
    session = packet.get("session")
    source = packet.get("source_receipt")
    chain = source.get("chain") if isinstance(source, Mapping) else None
    clocks = packet.get("clocks")
    if (
        not isinstance(session, Mapping)
        or session.get("cadence_minutes") != cadence_minutes
        or not isinstance(chain, Mapping)
        or not isinstance(clocks, Mapping)
    ):
        raise W0AAttestationError(
            f"W0a packet lacks completion evidence for {root}"
        )
    if chain.get("bucket_row_count") != result.get("bucket_rows"):
        raise W0AAttestationError(
            f"W0a packet/completion bucket row count mismatch for {root}"
        )
    if (
        clocks.get("vendor_snapshot_ts_min") != result.get("first_vendor_min_at")
        or clocks.get("vendor_snapshot_ts_max") != result.get("first_vendor_max_at")
    ):
        raise W0AAttestationError(
            f"W0a packet/completion first-vendor clock mismatch for {root}"
        )


def _contract_hash(root: str, expiration: str, right: str, strike: str) -> str:
    raw = f"{root}|{expiration}|{right}|{strike}".encode("ascii")
    return f"contract:uchain:{sha256(raw).hexdigest()}"


def _occ_symbol(root: str, expiration: date, right: str, strike_millis: int) -> str | None:
    if not _OCC_ROOT_RE.fullmatch(root) or right not in {"C", "P"}:
        return None
    if strike_millis <= 0 or strike_millis > 99_999_999:
        return None
    return f"{root:<6}{expiration:%y%m%d}{right}{strike_millis:08d}"


def _parse_occ(symbol: str) -> tuple[str, date, str, int] | None:
    if not isinstance(symbol, str) or len(symbol) != 21:
        return None
    root = symbol[:6].rstrip()
    right = symbol[12]
    strike_text = symbol[13:]
    try:
        expiration = datetime.strptime(symbol[6:12], "%y%m%d").date()
        strike_millis = int(strike_text)
    except (TypeError, ValueError):
        return None
    if (
        not _OCC_ROOT_RE.fullmatch(root)
        or right not in {"C", "P"}
        or len(strike_text) != 8
        or not strike_text.isdigit()
    ):
        return None
    return root, expiration, right, strike_millis


def _requested_contract(
    input_row: Mapping[str, object],
    packet: Mapping[str, Any],
) -> tuple[dict[str, object], str | None]:
    root = str(input_row["root"])
    profile_id = str(input_row["profile_id"])
    contract_id = str(input_row["contract_id"])
    profiles = packet.get("profiles")
    if not isinstance(profiles, Mapping) or profile_id not in profiles:
        raise W0AAttestationError(f"profile {profile_id} is absent from W0a packet {root}")
    profile = profiles[profile_id]
    eligible = _unique_ids(
        profile.get("eligible_contract_ids") if isinstance(profile, Mapping) else None,
        pattern=_CONTRACT_ID_RE,
        label=f"eligible contract list for {root}/{profile_id}",
    )
    if contract_id not in eligible:
        raise W0AAttestationError(
            f"contract {contract_id} is not explicitly eligible for {root}/{profile_id}"
        )
    contracts = packet.get("contracts")
    if not isinstance(contracts, list):
        raise W0AAttestationError(f"W0a packet contracts are malformed for {root}")
    matches = [row for row in contracts if isinstance(row, Mapping) and row.get("contract_id") == contract_id]
    if len(matches) != 1:
        raise W0AAttestationError(f"W0a contract identity is absent or ambiguous for {contract_id}")
    row = matches[0]
    contract = row.get("contract")
    if not isinstance(contract, Mapping):
        raise W0AAttestationError(f"W0a contract block is malformed for {contract_id}")
    if contract.get("root") != root:
        raise W0AAttestationError(f"W0a contract root mismatch for {contract_id}")
    expiration_text = contract.get("expiration")
    expiration = _date(expiration_text, field=f"expiration for {contract_id}")
    right = contract.get("right")
    if right not in {"C", "P"}:
        raise W0AAttestationError(f"W0a contract right is malformed for {contract_id}")
    strike, strike_canonical = _canonical_positive_decimal(
        contract.get("strike_canonical"), field=f"strike_canonical for {contract_id}"
    )
    numeric_strike = contract.get("strike")
    if isinstance(numeric_strike, bool) or not isinstance(numeric_strike, (int, float)):
        raise W0AAttestationError(f"W0a numeric strike is malformed for {contract_id}")
    try:
        if Decimal(str(numeric_strike)) != strike:
            raise W0AAttestationError(f"W0a numeric/canonical strike mismatch for {contract_id}")
    except InvalidOperation as exc:
        raise W0AAttestationError(f"W0a numeric strike is malformed for {contract_id}") from exc
    if _contract_hash(root, expiration_text, right, strike_canonical) != contract_id:
        raise W0AAttestationError(f"W0a contract_id does not bind identity for {contract_id}")
    profile_matches = _unique_ids(
        row.get("profile_matches"),
        pattern=_PROFILE_RE,
        label=f"profile_matches for {contract_id}",
    )
    if profile_id not in profile_matches:
        raise W0AAttestationError(f"W0a profile membership mismatch for {contract_id}")

    millis_decimal = strike * Decimal(1000)
    reason: str | None = None
    strike_millis: int | None
    occ: str | None
    if millis_decimal != millis_decimal.to_integral_value():
        strike_millis = None
        occ = None
        reason = "NON_MILLISTRIKE_CONTRACT"
    else:
        strike_millis = int(millis_decimal)
        occ = _occ_symbol(root, expiration, right, strike_millis)
        if occ is None or _parse_occ(occ) != (root, expiration, right, strike_millis):
            reason = "OCC_ROUNDTRIP_FAILED"
    if contract.get("occ_symbol") != occ:
        raise W0AAttestationError(f"W0a OCC identity mismatch for {contract_id}")
    return ({
        "ordinal": input_row["ordinal"],
        "root": root,
        "profile_id": profile_id,
        "contract_id": contract_id,
        "expiration": expiration_text,
        "right": right,
        "strike_canonical": strike_canonical,
        "strike_millis": strike_millis,
        "occ_symbol": occ,
    }, reason)


def attempt_keys(attempt_id: str) -> dict[str, str]:
    if not isinstance(attempt_id, str) or not _ATTEMPT_RE.fullmatch(attempt_id):
        raise FocusedQuoteError(f"invalid attempt_id: {attempt_id!r}")
    digest = attempt_id.rsplit(":", 1)[1]
    prefix = f"private/options_focused_quote/v1/attempts/{digest}"
    return {
        "decision": f"{prefix}/decision.json",
        "receipt": f"{prefix}/receipt.json",
    }


def prepare_attempt(
    inputs: Sequence[Mapping[str, object]],
    *,
    index_key: str,
    index_bytes: bytes,
    completion_ledger_bytes: bytes,
    packet_loader: Callable[[str], bytes],
) -> dict[str, Any]:
    """Verify W0a and return a clock-free semantic attempt plan."""
    ordered_inputs = normalize_inputs(inputs)
    index, index_attestation = _verify_index(index_key, index_bytes)
    indexed_roots: dict[str, Mapping[str, Any]] = {}
    indexed_root_order: list[str] = []
    for position, raw in enumerate(index["roots"], start=1):
        if not isinstance(raw, Mapping) or set(raw) != {
            "root", "derivative_current_key", "object"
        }:
            raise W0AAttestationError(f"W0a index root row {position} is malformed")
        root = _safe_root(raw.get("root"))
        if root in indexed_roots:
            raise W0AAttestationError(f"duplicate W0a index root: {root}")
        if raw.get("derivative_current_key") != (
            f"options_structure/msc_intraday/{root}/current.json"
        ):
            raise W0AAttestationError(f"W0a derivative current key mismatch for {root}")
        indexed_roots[root] = raw
        indexed_root_order.append(root)
    if indexed_root_order != sorted(indexed_root_order):
        raise W0AAttestationError("W0a index roots are not in canonical root order")
    if index.get("profile_ordering") != "none_across_profiles":
        raise W0AAttestationError("W0a index profile ordering is malformed")
    for root in _first_root_order(ordered_inputs):
        if root not in indexed_roots:
            raise W0AAttestationError(
                f"requested root absent from exact W0a index: {root}"
            )
    completion_attestation, completion_results = _verify_completion_ledger(
        completion_ledger_bytes,
        index=index,
        indexed_root_order=indexed_root_order,
    )

    packet_attestations: list[dict[str, object]] = []
    packets: dict[str, dict[str, Any]] = {}
    for root in indexed_root_order:
        index_row = indexed_roots[root]
        receipt = _verify_object_receipt(
            index_row.get("object"), root=root, epoch=index_attestation["epoch"]
        )
        try:
            body = packet_loader(str(receipt["key"]))
        except Exception as exc:  # noqa: BLE001 - loader boundary fails closed
            raise W0AAttestationError(f"cannot load W0a immutable packet for {root}") from exc
        if not isinstance(body, bytes):
            raise W0AAttestationError(f"W0a packet loader did not return bytes for {root}")
        packet = _verify_packet(
            body,
            receipt,
            root=root,
            epoch=str(index_attestation["epoch"]),
            index_available_at=str(index["available_at"]),
        )
        _verify_packet_completion(
            packet,
            completion_results[root],
            root=root,
            cadence_minutes=int(completion_attestation["cadence_minutes"]),
        )
        packets[root] = packet
        packet_attestations.append({
            "root": root,
            "key": receipt["key"],
            "sha256": receipt["sha256"],
            "bytes": receipt["bytes"],
            "packet_id": receipt["packet_id"],
            "epoch": index_attestation["epoch"],
        })

    requested: list[dict[str, object]] = []
    preflight_reason: str | None = None
    for item in ordered_inputs:
        contract, reason = _requested_contract(item, packets[str(item["root"])])
        requested.append(contract)
        if preflight_reason is None and reason is not None:
            preflight_reason = reason

    semantic = {
        "inputs": ordered_inputs,
        "w0a": {
            "completion": completion_attestation,
            "index": index_attestation,
            "packets": packet_attestations,
        },
        "requested_contracts": requested,
    }
    attempt_id = (
        "attempt:focused_quote:"
        + sha256(canonical_json_bytes(semantic)).hexdigest()
    )
    keys = attempt_keys(attempt_id)
    return {
        "attempt_id": attempt_id,
        **semantic,
        "preflight": {
            "status": "poll" if preflight_reason is None else "abstain",
            "abstention_reason": preflight_reason,
            "unique_roots": _first_root_order(ordered_inputs),
            "endpoint": SOURCE_ENDPOINT,
            "calls_per_root": 1,
            "selection_performed": False,
        },
        "publication": {
            "visibility": "private",
            "immutable_only": True,
            "current_pointer": False,
            "discovery_pointer": False,
            "decision_key": keys["decision"],
            "receipt_key": keys["receipt"],
        },
        "authority": authority_block(),
    }


def _plan_view(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "attempt_id", "inputs", "w0a", "requested_contracts", "preflight",
            "publication", "authority",
        )
    }


def decision_matches_plan(decision: Mapping[str, Any], plan: Mapping[str, Any]) -> bool:
    return _plan_view(decision) == _plan_view(plan)


def build_decision(plan: Mapping[str, Any], *, decided_at: datetime) -> dict[str, Any]:
    clock = _utc_clock(decided_at, field="decided_at")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "record_type": "decision",
        "decision_id": None,
        "decided_at": _iso_utc(clock),
        **_plan_view(plan),
    }
    payload["decision_id"] = _identity_digest(
        "decision:focused_quote:", payload, "decision_id"
    )
    strict_json_object(canonical_json_bytes(payload))
    return payload


def validate_decision(decision: Mapping[str, Any]) -> None:
    if decision.get("schema") != SCHEMA or decision.get("record_type") != "decision":
        raise FocusedQuoteError("focused quote decision discriminator mismatch")
    attempt_id = decision.get("attempt_id")
    decision_id = decision.get("decision_id")
    if not isinstance(attempt_id, str) or not _ATTEMPT_RE.fullmatch(attempt_id):
        raise FocusedQuoteError("focused quote attempt_id is malformed")
    if not isinstance(decision_id, str) or not _DECISION_RE.fullmatch(decision_id):
        raise FocusedQuoteError("focused quote decision_id is malformed")
    if decision_id != _identity_digest(
        "decision:focused_quote:", decision, "decision_id"
    ):
        raise FocusedQuoteError("focused quote decision_id mismatch")
    _exact_utc(decision.get("decided_at"), field="focused quote decided_at")
    inputs = decision.get("inputs")
    requested = decision.get("requested_contracts")
    w0a = decision.get("w0a")
    if not isinstance(inputs, list) or not isinstance(requested, list) or not isinstance(w0a, Mapping):
        raise FocusedQuoteError("focused quote decision semantic fields are malformed")
    if not 1 <= len(inputs) <= MAX_INPUTS or len(requested) != len(inputs):
        raise FocusedQuoteError("focused quote decision input cardinality mismatch")
    roots: list[str] = []
    seen_roots: set[str] = set()
    expected_reason: str | None = None
    for ordinal, (input_row, contract) in enumerate(zip(inputs, requested), start=1):
        if not isinstance(input_row, Mapping) or not isinstance(contract, Mapping):
            raise FocusedQuoteError("focused quote decision rows are malformed")
        if input_row.get("ordinal") != ordinal or contract.get("ordinal") != ordinal:
            raise FocusedQuoteError("focused quote decision order is not contiguous")
        for field in ("root", "profile_id", "contract_id"):
            if input_row.get(field) != contract.get(field):
                raise FocusedQuoteError(f"focused quote decision {field} binding mismatch")
        root = _safe_root(input_row.get("root"))
        _safe_profile(input_row.get("profile_id"))
        _safe_contract_id(input_row.get("contract_id"))
        if root not in seen_roots:
            seen_roots.add(root)
            roots.append(root)
        strike, _canonical = _canonical_positive_decimal(
            contract.get("strike_canonical"), field="decision strike_canonical"
        )
        millis_decimal = strike * Decimal(1000)
        if millis_decimal != millis_decimal.to_integral_value():
            row_reason = "NON_MILLISTRIKE_CONTRACT"
            if contract.get("strike_millis") is not None or contract.get("occ_symbol") is not None:
                raise FocusedQuoteError("non-millistrike decision carries OCC identity")
        else:
            millis = int(millis_decimal)
            if contract.get("strike_millis") != millis:
                raise FocusedQuoteError("focused quote decision millistrike mismatch")
            try:
                expiration = date.fromisoformat(str(contract.get("expiration")))
            except ValueError as exc:
                raise FocusedQuoteError("focused quote decision expiration mismatch") from exc
            right = contract.get("right")
            occ = contract.get("occ_symbol")
            if (
                not isinstance(occ, str)
                or _parse_occ(occ) != (root, expiration, right, millis)
            ):
                row_reason = "OCC_ROUNDTRIP_FAILED"
                if occ is not None:
                    raise FocusedQuoteError("focused quote decision OCC roundtrip mismatch")
            else:
                row_reason = None
        if expected_reason is None and row_reason is not None:
            expected_reason = row_reason
    semantic = {"inputs": inputs, "w0a": w0a, "requested_contracts": requested}
    expected_attempt_id = (
        "attempt:focused_quote:" + sha256(canonical_json_bytes(semantic)).hexdigest()
    )
    if attempt_id != expected_attempt_id:
        raise FocusedQuoteError("focused quote attempt_id semantic mismatch")
    expected_preflight = {
        "status": "poll" if expected_reason is None else "abstain",
        "abstention_reason": expected_reason,
        "unique_roots": roots,
        "endpoint": SOURCE_ENDPOINT,
        "calls_per_root": 1,
        "selection_performed": False,
    }
    if decision.get("preflight") != expected_preflight:
        raise FocusedQuoteError("focused quote decision preflight mismatch")
    if decision.get("publication", {}).get("decision_key") != attempt_keys(attempt_id)["decision"]:
        raise FocusedQuoteError("focused quote decision key mismatch")
    if decision.get("publication", {}).get("receipt_key") != attempt_keys(attempt_id)["receipt"]:
        raise FocusedQuoteError("focused quote receipt key mismatch")
    if decision.get("authority") != authority_block():
        raise FocusedQuoteError("focused quote decision authority mismatch")


def decision_age_microseconds(decision: Mapping[str, Any], *, now: datetime) -> int:
    validate_decision(decision)
    decided_at = _exact_utc(decision["decided_at"], field="focused quote decided_at")
    current = _utc_clock(now, field="recovery clock")
    delta = current - decided_at
    microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    if microseconds < 0:
        raise FocusedQuoteClockError("recovery clock precedes durable decision clock")
    return microseconds


def _finite_quote_number(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not pd.api.types.is_scalar(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return 0.0 if number == 0 else number


def _source_expiration(value: object) -> str | None:
    if not pd.api.types.is_scalar(value):
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(stamp) or stamp.tzinfo is not None:
        return None
    if any((stamp.hour, stamp.minute, stamp.second, stamp.microsecond, stamp.nanosecond)):
        return None
    return stamp.date().isoformat()


def _source_millis(value: object) -> int | None:
    if value is None or isinstance(value, bool) or not pd.api.types.is_scalar(value):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    millis = parsed * Decimal(1000)
    if (
        not parsed.is_finite()
        or parsed <= 0
        or millis != millis.to_integral_value()
        or millis > 99_999_999
    ):
        return None
    return int(millis)


def _source_snapshot_clock(value: object) -> datetime | None:
    if not pd.api.types.is_scalar(value):
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(stamp) or stamp.nanosecond:
        return None
    try:
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(ET, ambiguous="raise", nonexistent="raise")
        stamp = stamp.tz_convert("UTC")
    except (TypeError, ValueError):
        return None
    return stamp.to_pydatetime()


def _empty_receipt(
    decision: Mapping[str, Any],
    *,
    verified_at: datetime,
    status: str,
    reason: str | None,
    source_calls: list[dict[str, object]],
    quotes: list[dict[str, object]],
    recovered_without_repoll: bool,
) -> dict[str, Any]:
    validate_decision(decision)
    verified = _utc_clock(verified_at, field="verified_available_at")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "record_type": "receipt",
        "receipt_id": None,
        "attempt_id": decision["attempt_id"],
        "decision_id": decision["decision_id"],
        "verified_available_at": _iso_utc(verified),
        "status": status,
        "abstention_reason": reason,
        "input_count": len(decision["inputs"]),
        "source_calls": source_calls,
        "quotes": quotes,
        "quote_semantics": quote_semantics(),
        "recovery": {
            "deadline_seconds": RECOVERY_DEADLINE_SECONDS,
            "recovered_without_repoll": recovered_without_repoll,
        },
        "publication": decision["publication"],
        "authority": authority_block(),
    }
    payload["receipt_id"] = _identity_digest(
        "receipt:focused_quote:", payload, "receipt_id"
    )
    strict_json_object(canonical_json_bytes(payload))
    return payload


def build_preflight_receipt(
    decision: Mapping[str, Any], *, verified_at: datetime
) -> dict[str, Any]:
    preflight = decision.get("preflight")
    if not isinstance(preflight, Mapping) or preflight.get("status") != "abstain":
        raise FocusedQuoteError("decision is not a preflight abstention")
    return _empty_receipt(
        decision,
        verified_at=verified_at,
        status="abstain",
        reason=str(preflight.get("abstention_reason")),
        source_calls=[],
        quotes=[],
        recovered_without_repoll=False,
    )


def build_recovery_receipt(
    decision: Mapping[str, Any], *, verified_at: datetime
) -> dict[str, Any]:
    age = decision_age_microseconds(decision, now=verified_at)
    if age < RECOVERY_DEADLINE_SECONDS * 1_000_000:
        raise FocusedQuoteError("recovery deadline has not elapsed")
    return _empty_receipt(
        decision,
        verified_at=verified_at,
        status="abstain",
        reason="RECOVERY_DEADLINE_EXCEEDED",
        source_calls=[],
        quotes=[],
        recovered_without_repoll=True,
    )


def build_source_receipt(
    decision: Mapping[str, Any],
    frames: Mapping[str, object],
    *,
    verified_at: datetime | Callable[[], datetime],
) -> dict[str, Any]:
    """Project exact requested rows from one already-fetched frame per root."""
    validate_decision(decision)
    preflight = decision.get("preflight")
    if not isinstance(preflight, Mapping) or preflight.get("status") != "poll":
        raise FocusedQuoteError("decision does not authorize source polling")
    roots = list(preflight.get("unique_roots") or [])
    if list(frames) != roots:
        raise FocusedQuoteError("source frame order/roots do not match the durable decision")
    requested_by_root: dict[str, list[Mapping[str, object]]] = {root: [] for root in roots}
    for contract in decision["requested_contracts"]:
        requested_by_root[str(contract["root"])].append(contract)

    candidates: dict[tuple[str, str, str, int], list[dict[str, object]]] = {}
    accepted: dict[tuple[str, str, str, int], list[dict[str, object]]] = {}
    matched_counts: dict[tuple[str, str, str, int], int] = {}
    source_calls: list[dict[str, object]] = []
    for root in roots:
        frame = frames[root]
        returned_count: int | None = None
        shape_valid = False
        requested_matches = 0
        accepted_matches = 0
        malformed_requested = 0
        target_keys = {
            (
                root,
                str(item["expiration"]),
                str(item["right"]),
                int(item["strike_millis"]),
            )
            for item in requested_by_root[root]
        }
        if isinstance(frame, pd.DataFrame):
            returned_count = len(frame)
            required = {"root", "expiration", "strike", "right", "snapshot_ts", "bid", "ask"}
            shape_valid = bool(frame.columns.is_unique) and required.issubset(
                frame.columns
            )
            if shape_valid:
                for _, row in frame.iterrows():
                    source_root = row.get("root")
                    expiration = _source_expiration(row.get("expiration"))
                    right = row.get("right")
                    millis = _source_millis(row.get("strike"))
                    if (
                        not isinstance(source_root, str)
                        or source_root != root
                        or expiration is None
                        or not isinstance(right, str)
                        or right not in {"C", "P"}
                        or millis is None
                    ):
                        continue
                    key = (root, expiration, str(right), millis)
                    if key not in target_keys:
                        continue
                    requested_matches += 1
                    matched_counts[key] = matched_counts.get(key, 0) + 1
                    bid = _finite_quote_number(row.get("bid"))
                    ask = _finite_quote_number(row.get("ask"))
                    snapshot = _source_snapshot_clock(row.get("snapshot_ts"))
                    if (
                        bid is None
                        or ask is None
                        or ask < bid
                        or snapshot is None
                    ):
                        malformed_requested += 1
                        continue
                    candidates.setdefault(key, []).append({
                        "bid": bid,
                        "ask": ask,
                        "snapshot": snapshot,
                    })
        source_calls.append({
            "root": root,
            "endpoint": SOURCE_ENDPOINT,
            "call_count": 1,
            "returned_row_count": returned_count,
            "source_shape_valid": shape_valid,
            "requested_match_row_count": requested_matches,
            "structurally_accepted_requested_row_count": accepted_matches,
            "malformed_requested_row_count": malformed_requested,
        })

    # Availability is verified only after every returned row has been locally
    # normalized.  The captured clock then binds the future-row check and the
    # exact freshness delta; no pre-verification timestamp can understate age.
    verification_clock = verified_at() if callable(verified_at) else verified_at
    verified = _utc_clock(verification_clock, field="verified_available_at")
    calls_by_root = {str(call["root"]): call for call in source_calls}
    for key, rows in candidates.items():
        call = calls_by_root[key[0]]
        for row in rows:
            snapshot = row["snapshot"]
            assert isinstance(snapshot, datetime)
            if snapshot > verified:
                call["malformed_requested_row_count"] = (
                    int(call["malformed_requested_row_count"]) + 1
                )
                continue
            age = verified - snapshot
            age_us = (
                age.days * 86_400_000_000
                + age.seconds * 1_000_000
                + age.microseconds
            )
            accepted.setdefault(key, []).append({
                "bid": row["bid"],
                "ask": row["ask"],
                "snapshot_ts": _iso_utc(snapshot),
                "age_microseconds": age_us,
            })
            call["structurally_accepted_requested_row_count"] = (
                int(call["structurally_accepted_requested_row_count"]) + 1
            )

    quotes: list[dict[str, object]] = []
    complete = True
    for contract in decision["requested_contracts"]:
        key = (
            str(contract["root"]),
            str(contract["expiration"]),
            str(contract["right"]),
            int(contract["strike_millis"]),
        )
        matches = accepted.get(key, [])
        if matched_counts.get(key, 0) != 1 or len(matches) != 1:
            complete = False
            break
        quote = matches[0]
        quotes.append({
            "ordinal": contract["ordinal"],
            "root": contract["root"],
            "profile_id": contract["profile_id"],
            "contract_id": contract["contract_id"],
            "occ_symbol": contract["occ_symbol"],
            "strike_millis": contract["strike_millis"],
            "vendor_snapshot": {
                "label": SOURCE_QUOTE_LABEL,
                "bid": quote["bid"],
                "ask": quote["ask"],
                "snapshot_ts": quote["snapshot_ts"],
                "freshness": {
                    "basis": "verified_available_at_minus_vendor_snapshot_ts",
                    "verified_available_at": _iso_utc(verified),
                    "age_microseconds": quote["age_microseconds"],
                },
            },
        })

    if not complete or len(quotes) != len(decision["inputs"]):
        return _empty_receipt(
            decision,
            verified_at=verified,
            status="abstain",
            reason="NO_STRUCTURALLY_ACCEPTED_SOURCE_ROW",
            source_calls=source_calls,
            quotes=[],
            recovered_without_repoll=False,
        )
    return _empty_receipt(
        decision,
        verified_at=verified,
        status="complete",
        reason=None,
        source_calls=source_calls,
        quotes=quotes,
        recovered_without_repoll=False,
    )


_SOURCE_CALL_FIELDS = frozenset({
    "root",
    "endpoint",
    "call_count",
    "returned_row_count",
    "source_shape_valid",
    "requested_match_row_count",
    "structurally_accepted_requested_row_count",
    "malformed_requested_row_count",
})


def _validate_polled_source_calls(
    source_calls: Sequence[object],
    decision: Mapping[str, Any],
) -> bool:
    expected_roots = list(decision["preflight"]["unique_roots"])
    expected_unique: dict[str, set[tuple[str, str, int]]] = {
        root: set() for root in expected_roots
    }
    for contract in decision["requested_contracts"]:
        if not isinstance(contract, Mapping):
            raise FocusedQuoteError("focused quote requested contract is malformed")
        root = contract.get("root")
        expiration = contract.get("expiration")
        right = contract.get("right")
        strike_millis = contract.get("strike_millis")
        if (
            root not in expected_unique
            or type(expiration) is not str
            or right not in {"C", "P"}
            or type(strike_millis) is not int
        ):
            raise FocusedQuoteError(
                "polled source calls require exact pollable requested contracts"
            )
        expected_unique[root].add((expiration, right, strike_millis))
    if len(source_calls) != len(expected_roots):
        raise FocusedQuoteError("focused quote source-call cardinality mismatch")
    complete = True
    for root, raw in zip(expected_roots, source_calls):
        if not isinstance(raw, Mapping) or set(raw) != _SOURCE_CALL_FIELDS:
            raise FocusedQuoteError("focused quote source-call shape mismatch")
        if (
            raw.get("root") != root
            or raw.get("endpoint") != SOURCE_ENDPOINT
            or raw.get("call_count") != 1
        ):
            raise FocusedQuoteError("focused quote source-call identity mismatch")
        shape_valid = raw.get("source_shape_valid")
        returned = raw.get("returned_row_count")
        counts = [
            raw.get("requested_match_row_count"),
            raw.get("structurally_accepted_requested_row_count"),
            raw.get("malformed_requested_row_count"),
        ]
        if type(shape_valid) is not bool or any(
            type(value) is not int or value < 0 for value in counts
        ):
            raise FocusedQuoteError("focused quote source-call counts are malformed")
        requested_count, accepted_count, malformed_count = counts
        if returned is None:
            if shape_valid or any(counts):
                raise FocusedQuoteError("focused quote null source-call count is incoherent")
        elif type(returned) is not int or returned < 0:
            raise FocusedQuoteError("focused quote returned-row count is malformed")
        elif (
            requested_count > returned
            or accepted_count > requested_count
            or malformed_count > requested_count
            or accepted_count + malformed_count > requested_count
        ):
            raise FocusedQuoteError("focused quote source-call count law is violated")
        if not shape_valid and any(counts):
            raise FocusedQuoteError("malformed source shape cannot carry accepted rows")
        expected_count = len(expected_unique[root])
        call_complete = (
            shape_valid
            and returned is not None
            and requested_count == expected_count
            and accepted_count == expected_count
            and malformed_count == 0
        )
        complete = complete and call_complete
    return complete


def validate_receipt(receipt: Mapping[str, Any], decision: Mapping[str, Any]) -> None:
    validate_decision(decision)
    if receipt.get("schema") != SCHEMA or receipt.get("record_type") != "receipt":
        raise FocusedQuoteError("focused quote receipt discriminator mismatch")
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not _RECEIPT_RE.fullmatch(receipt_id):
        raise FocusedQuoteError("focused quote receipt_id is malformed")
    if receipt_id != _identity_digest(
        "receipt:focused_quote:", receipt, "receipt_id"
    ):
        raise FocusedQuoteError("focused quote receipt_id mismatch")
    if receipt.get("attempt_id") != decision.get("attempt_id"):
        raise FocusedQuoteError("focused quote receipt attempt mismatch")
    if receipt.get("decision_id") != decision.get("decision_id"):
        raise FocusedQuoteError("focused quote receipt decision mismatch")
    verified_at = _exact_utc(
        receipt.get("verified_available_at"), field="verified_available_at"
    )
    decided_at = _exact_utc(decision.get("decided_at"), field="focused quote decided_at")
    if verified_at < decided_at:
        raise FocusedQuoteError("focused quote receipt predates its durable decision")
    if receipt.get("publication") != decision.get("publication"):
        raise FocusedQuoteError("focused quote receipt publication mismatch")
    if receipt.get("authority") != authority_block():
        raise FocusedQuoteError("focused quote receipt authority mismatch")
    if receipt.get("quote_semantics") != quote_semantics():
        raise FocusedQuoteError("focused quote receipt semantics mismatch")
    if receipt.get("input_count") != len(decision["inputs"]):
        raise FocusedQuoteError("focused quote receipt input_count mismatch")
    quotes = receipt.get("quotes")
    source_calls = receipt.get("source_calls")
    recovery = receipt.get("recovery")
    if not isinstance(quotes, list) or not isinstance(source_calls, list) or not isinstance(recovery, Mapping):
        raise FocusedQuoteError("focused quote receipt arrays are malformed")
    if (
        set(recovery) != {"deadline_seconds", "recovered_without_repoll"}
        or recovery.get("deadline_seconds") != RECOVERY_DEADLINE_SECONDS
        or type(recovery.get("recovered_without_repoll")) is not bool
    ):
        raise FocusedQuoteError("focused quote recovery block is malformed")
    reason = receipt.get("abstention_reason")
    status = receipt.get("status")
    preflight = decision.get("preflight")
    if not isinstance(preflight, Mapping):
        raise FocusedQuoteError("focused quote decision preflight is malformed")
    preflight_status = preflight.get("status")
    if status == "complete":
        if preflight_status != "poll":
            raise FocusedQuoteError("preflight abstention cannot carry a complete receipt")
        if reason is not None or len(quotes) != len(decision["requested_contracts"]):
            raise FocusedQuoteError("complete focused quote receipt cardinality mismatch")
        if recovery.get("recovered_without_repoll") is not False:
            raise FocusedQuoteError("complete focused quote receipt cannot be a recovery")
        if not _validate_polled_source_calls(source_calls, decision):
            raise FocusedQuoteError("complete receipt lacks complete source-call evidence")
        for quote, contract in zip(quotes, decision["requested_contracts"]):
            if not isinstance(quote, Mapping):
                raise FocusedQuoteError("focused quote row is malformed")
            for field in (
                "ordinal", "root", "profile_id", "contract_id", "occ_symbol", "strike_millis"
            ):
                if quote.get(field) != contract.get(field):
                    raise FocusedQuoteError(f"focused quote row {field} mismatch")
            vendor = quote.get("vendor_snapshot")
            if not isinstance(vendor, Mapping) or vendor.get("label") != SOURCE_QUOTE_LABEL:
                raise FocusedQuoteError("focused quote vendor snapshot is malformed")
            bid = _finite_quote_number(vendor.get("bid"))
            ask = _finite_quote_number(vendor.get("ask"))
            if bid is None or ask is None or ask < bid:
                raise FocusedQuoteError("focused quote vendor bid/ask is malformed")
            snapshot = _exact_utc(vendor.get("snapshot_ts"), field="vendor snapshot_ts")
            if snapshot > verified_at:
                raise FocusedQuoteError("focused quote vendor snapshot is from the future")
            freshness = vendor.get("freshness")
            if not isinstance(freshness, Mapping):
                raise FocusedQuoteError("focused quote freshness is malformed")
            age = verified_at - snapshot
            age_us = (
                age.days * 86_400_000_000
                + age.seconds * 1_000_000
                + age.microseconds
            )
            if (
                freshness.get("basis")
                != "verified_available_at_minus_vendor_snapshot_ts"
                or freshness.get("verified_available_at") != receipt.get("verified_available_at")
                or freshness.get("age_microseconds") != age_us
            ):
                raise FocusedQuoteError("focused quote freshness binding mismatch")
    elif status == "abstain":
        if quotes:
            raise FocusedQuoteError("abstention receipt cannot carry quotes")
        if reason in {"NON_MILLISTRIKE_CONTRACT", "OCC_ROUNDTRIP_FAILED"}:
            if (
                preflight_status != "abstain"
                or source_calls
                or reason != preflight.get("abstention_reason")
            ):
                raise FocusedQuoteError("preflight abstention receipt mismatch")
            if recovery.get("recovered_without_repoll") is not False:
                raise FocusedQuoteError("preflight abstention cannot be a recovery")
        elif reason == "NO_STRUCTURALLY_ACCEPTED_SOURCE_ROW":
            if preflight_status != "poll":
                raise FocusedQuoteError(
                    "preflight abstention cannot carry provider source-call evidence"
                )
            if _validate_polled_source_calls(source_calls, decision):
                raise FocusedQuoteError("source abstention contradicts complete source calls")
            if recovery.get("recovered_without_repoll") is not False:
                raise FocusedQuoteError("source abstention cannot be a recovery")
        elif reason == "RECOVERY_DEADLINE_EXCEEDED":
            if source_calls or recovery.get("recovered_without_repoll") is not True:
                raise FocusedQuoteError("recovery abstention receipt mismatch")
            if decision_age_microseconds(decision, now=verified_at) < RECOVERY_DEADLINE_SECONDS * 1_000_000:
                raise FocusedQuoteError("recovery abstention predates the 300s deadline")
        else:
            raise FocusedQuoteError("focused quote abstention reason is malformed")
    else:
        raise FocusedQuoteError("focused quote receipt status is malformed")
