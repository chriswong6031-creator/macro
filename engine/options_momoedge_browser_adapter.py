"""Observe-only MomoEdge browser evidence validation and private persistence.

This module is intentionally independent of the prospective NBBO cohort. It
cannot arm a producer, enroll an event, or count a capture as coverage. Its sole
job is to validate a fresh page-runtime response, preserve exact private source
bytes, and write a debranded, fail-closed observation journal.
"""

from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, BinaryIO, Iterator, Mapping, Sequence
from zoneinfo import ZoneInfo


OBSERVATION_SCHEMA = "options.momoedge_browser_observation/v1"
PAGE_CAPTURE_SCHEMA = "options.momoedge_browser_page_capture/v1"
JOURNAL_SCHEMA = "options.momoedge_browser_observe_journal/v1"
ACK_SCHEMA = "options.momoedge_browser_native_ack/v1"
PROJECTION_SCHEMA = "options.momoedge_browser_projection/v1"
REQUEST_CONTRACT = "signals_active_plus_source_today_closed_fresh_fetch/v1"
RESPONSE_SCHEMA = "momoedge_signals_json_array/v1"
EXTENSION_VERSION = "0.1.0"
CADENCE_SECONDS = 300
MAX_NATIVE_MESSAGE_BYTES = 950_000
MAX_RESPONSE_BYTES = 600_000
MAX_PROJECTION_BYTES = 750_000
MAX_SIGNAL_ROWS = 2_000
MAX_CONTRACTS_PER_SIGNAL = 16
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 50_000
MAX_JSON_KEY_LENGTH = 128
MAX_JSON_STRING_LENGTH = 100_000
MAX_JSON_NUMBER_LENGTH = 128
MAX_RAW_OBJECTS = 10_000
MAX_RAW_TOTAL_BYTES = 5_000_000_000
MAX_JOURNAL_FILES = 20_000
MAX_QUARANTINE_FILES = 1_000
PRIVATE_ROOT_DEFAULT = Path.home() / ".mastermind_private" / "momoedge_browser_observe_v1"

FALSE_AUTHORITY = {
    "may_count_coverage": False,
    "may_enroll": False,
    "may_score": False,
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
}

UNAVAILABLE_REASONS = frozenset(
    {
        "alarm_late",
        "capture_in_flight",
        "capture_timeout",
        "fetch_wrapper_restore_failed",
        "fresh_request_not_observed",
        "http_error",
        "invalid_fresh_response",
        "invalid_response_json",
        "invalid_response_shape",
        "multiple_matching_responses",
        "no_matching_tab",
        "page_execution_failed",
        "page_fetch_missing",
        "page_load_failed",
        "page_origin_path_mismatch",
        "page_runtime_missing",
        "response_too_large",
        "runtime_fallback_or_missing",
        "runtime_response_mismatch",
        "sensitive_key_rejected",
        "tab_not_ready",
    }
)

_SENSITIVE_MARKERS = frozenset(
    {
        "authorization",
        "auth",
        "bearer",
        "cookie",
        "csrf",
        "xsrf",
        "setcookie",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "password",
        "passwd",
        "secret",
        "apikey",
        "credential",
        "credentials",
        "session",
        "sessionid",
        "clientsecret",
        "privatekey",
        "jwt",
        "localstorage",
        "sessionstorage",
        "token",
    }
)


class MomoEdgeObserveError(ValueError):
    """Base error for an invalid or unsafe observation."""


class SensitiveSourceError(MomoEdgeObserveError):
    """The source body contained a key that must never be persisted."""


class PrivateStoreError(MomoEdgeObserveError):
    """Private storage ownership, topology, or durability is unsafe."""


class ObservationConflict(MomoEdgeObserveError):
    """A slot already has different immutable journal bytes."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _reject_constant(value: str) -> None:
    raise MomoEdgeObserveError(f"non-finite JSON constant rejected: {value}")


def _reject_duplicate_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MomoEdgeObserveError(f"duplicate JSON key rejected: {key}")
        result[key] = value
    return result


def _parse_json_int(value: str) -> int:
    if len(value) > MAX_JSON_NUMBER_LENGTH:
        raise MomoEdgeObserveError("JSON integer length exceeds the bound")
    try:
        return int(value)
    except ValueError as exc:
        raise MomoEdgeObserveError("invalid JSON integer") from exc


def _parse_json_decimal(value: str) -> Decimal:
    if len(value) > MAX_JSON_NUMBER_LENGTH:
        raise MomoEdgeObserveError("JSON decimal length exceeds the bound")
    try:
        parsed = Decimal(value)
    except (ValueError, ArithmeticError) as exc:
        raise MomoEdgeObserveError("invalid JSON decimal") from exc
    if not parsed.is_finite() or (
        parsed != 0 and (parsed.adjusted() > 308 or parsed.adjusted() < -324)
    ):
        raise MomoEdgeObserveError("JSON decimal magnitude exceeds the bound")
    return parsed


def strict_json_loads(payload: bytes) -> Any:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MomoEdgeObserveError("JSON is not strict UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=_parse_json_decimal,
            parse_int=_parse_json_int,
            parse_constant=_reject_constant,
        )
    except MomoEdgeObserveError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise MomoEdgeObserveError("invalid JSON") from exc


def validate_json_complexity(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise MomoEdgeObserveError("JSON node count exceeds the bound")
        if depth > MAX_JSON_DEPTH:
            raise MomoEdgeObserveError("JSON depth exceeds the bound")
        if isinstance(current, Mapping):
            for key, child in current.items():
                if len(str(key)) > MAX_JSON_KEY_LENGTH:
                    raise MomoEdgeObserveError("JSON key length exceeds the bound")
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)
        elif isinstance(current, str) and len(current) > MAX_JSON_STRING_LENGTH:
            raise MomoEdgeObserveError("JSON string length exceeds the bound")


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(child) for child in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _json_compatible(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _normalize_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def reject_sensitive_keys(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for key, child in current.items():
                normalized = _normalize_key(key)
                if any(marker in normalized for marker in _SENSITIVE_MARKERS):
                    raise SensitiveSourceError("sensitive source key rejected")
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)


def _expect_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise MomoEdgeObserveError(
            f"{label} keys mismatch; missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not re.search(r"(?:Z|[+-]\d\d:\d\d)$", value):
        raise MomoEdgeObserveError(f"{label} must be an RFC3339 timestamp with offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MomoEdgeObserveError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise MomoEdgeObserveError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _validate_clock(value: Any, label: str) -> datetime:
    if not isinstance(value, Mapping):
        raise MomoEdgeObserveError(f"{label} must be an object")
    _expect_exact_keys(value, {"utc", "epoch_ms"}, label)
    parsed = _parse_timestamp(value["utc"], f"{label}.utc")
    epoch_ms = value["epoch_ms"]
    if not isinstance(epoch_ms, (int, Decimal)) or isinstance(epoch_ms, bool):
        raise MomoEdgeObserveError(f"{label}.epoch_ms must be numeric")
    observed = Decimal(str(parsed.timestamp())) * Decimal("1000")
    if abs(observed - Decimal(epoch_ms)) > Decimal("2"):
        raise MomoEdgeObserveError(f"{label} UTC and epoch clocks disagree")
    return parsed


def _validate_common_observation(message: Any) -> tuple[datetime, datetime, datetime]:
    if not isinstance(message, Mapping):
        raise MomoEdgeObserveError("observation must be an object")
    _expect_exact_keys(
        message,
        {
            "schema",
            "mode",
            "extension_version",
            "scheduled_at",
            "attempted_at",
            "completed_at",
            "disposition",
            "reason",
            "capture",
            "coverage_eligible",
            "authority",
        },
        "observation",
    )
    if message["schema"] != OBSERVATION_SCHEMA:
        raise MomoEdgeObserveError("unexpected observation schema")
    if message["mode"] != "observe_only":
        raise MomoEdgeObserveError("only observe_only mode is accepted")
    if message["extension_version"] != EXTENSION_VERSION:
        raise MomoEdgeObserveError("unexpected extension version")
    if message["coverage_eligible"] is not False:
        raise MomoEdgeObserveError("observe-only evidence can never be coverage eligible")
    if message["authority"] != FALSE_AUTHORITY:
        raise MomoEdgeObserveError("all authority flags must remain false")

    scheduled = _parse_timestamp(message["scheduled_at"], "scheduled_at")
    attempted = _parse_timestamp(message["attempted_at"], "attempted_at")
    completed = _parse_timestamp(message["completed_at"], "completed_at")
    scheduled_ms = int(scheduled.timestamp() * 1000)
    if scheduled_ms % (CADENCE_SECONDS * 1000) != 0:
        raise MomoEdgeObserveError("scheduled_at must be on the exact 300-second grid")
    if attempted < scheduled or completed < attempted:
        raise MomoEdgeObserveError("observation clocks are not causal")

    disposition = message["disposition"]
    if disposition == "fresh_response":
        if message["reason"] is not None or not isinstance(message["capture"], Mapping):
            raise MomoEdgeObserveError("fresh_response requires capture and null reason")
        if completed >= scheduled + timedelta(seconds=CADENCE_SECONDS):
            raise MomoEdgeObserveError("fresh response completed outside its scheduled slot")
    elif disposition == "unavailable":
        reason = message["reason"]
        if (
            not isinstance(reason, str)
            or reason not in UNAVAILABLE_REASONS
            or message["capture"] is not None
        ):
            raise MomoEdgeObserveError("unavailable observation has invalid reason or capture")
    else:
        raise MomoEdgeObserveError("invalid observation disposition")
    return scheduled, attempted, completed


def _validate_row_shape(rows: Any, closed_cutoff: datetime) -> tuple[int, int]:
    if not isinstance(rows, list):
        raise MomoEdgeObserveError("signals response must be a JSON array")
    if len(rows) > MAX_SIGNAL_ROWS:
        raise MomoEdgeObserveError("signals response row count exceeds the bound")
    active_count = 0
    closed_count = 0
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise MomoEdgeObserveError("each signal row must be an object")
        raw_id = row.get("id")
        valid_string_id = (
            isinstance(raw_id, str)
            and 0 < len(raw_id) <= 256
            and bool(raw_id.strip())
            and re.search(r"[\x00-\x1f\x7f]", raw_id) is None
        )
        valid_integer_id = (
            isinstance(raw_id, int)
            and not isinstance(raw_id, bool)
            and abs(raw_id) <= 9_007_199_254_740_991
        )
        if not (valid_string_id or valid_integer_id):
            raise MomoEdgeObserveError("signal row is missing stable source id")
        source_id = str(row["id"])
        if source_id in seen_ids:
            raise MomoEdgeObserveError("duplicate signal source id rejected")
        seen_ids.add(source_id)
        if not isinstance(row.get("is_active"), bool):
            raise MomoEdgeObserveError("signal row is missing boolean is_active")
        _parse_timestamp(row.get("created_at"), "signal.created_at")
        if row["is_active"]:
            active_count += 1
        else:
            closed_at = _parse_timestamp(row.get("closed_at"), "signal.closed_at")
            if closed_at < closed_cutoff:
                raise MomoEdgeObserveError("closed row predates the proven today-closed cutoff")
            closed_count += 1
    return active_count, closed_count


def _decimal_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (Decimal, int, str)):
        text = str(value).strip()
        return text or None
    return str(value)


def _bounded_text(value: Any, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) > maximum:
        raise MomoEdgeObserveError(f"{label} length exceeds the bound")
    return text


def _ticker_from_row(row: Mapping[str, Any]) -> str | None:
    candidate = row.get("ticker") or row.get("asset") or row.get("symbol")
    if not isinstance(candidate, str):
        return None
    if len(candidate) > 64:
        raise MomoEdgeObserveError("signal ticker field length exceeds the bound")
    pieces = candidate.strip().split()
    if not pieces:
        raise MomoEdgeObserveError("signal ticker cannot be whitespace-only")
    ticker = pieces[0].upper()
    return ticker if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", ticker) else None


def _parse_option_contracts(row: Mapping[str, Any], ticker: str | None) -> list[dict[str, Any]]:
    source = row.get("option_contracts")
    if source in (None, "", []):
        return []
    if isinstance(source, str):
        if len(source) > MAX_JSON_STRING_LENGTH:
            raise MomoEdgeObserveError("encoded option_contracts exceeds the bound")
        source = strict_json_loads(source.encode("utf-8"))
    if not isinstance(source, list):
        raise MomoEdgeObserveError("option_contracts must be a list or encoded list")
    validate_json_complexity(source)
    if len(source) > MAX_CONTRACTS_PER_SIGNAL:
        raise MomoEdgeObserveError("option contract count exceeds the bound")
    reject_sensitive_keys(source)
    projected: list[dict[str, Any]] = []
    for contract in source:
        if not isinstance(contract, Mapping):
            raise MomoEdgeObserveError("option contract must be an object")
        option_type = contract.get("type") or contract.get("option_type") or contract.get("right")
        type_text = _bounded_text(option_type, "option_type", 32)
        type_text = type_text.strip() if type_text is not None else None
        upper = type_text.upper() if type_text else ""
        right = "C" if upper.startswith("C") else ("P" if upper.startswith("P") else None)
        root = contract.get("root") or contract.get("ticker") or contract.get("underlying") or ticker
        projected.append(
            {
                "root": (
                    _bounded_text(root, "option root", 32).strip().upper() if root is not None else None
                ),
                "option_type": type_text,
                "right": right,
                "strike": _bounded_text(_decimal_text(contract.get("strike")), "option strike", 64),
                "expiry": _bounded_text(contract.get("expiry"), "option expiry", 64),
                "premium": _bounded_text(_decimal_text(contract.get("premium")), "option premium", 64),
            }
        )
    return projected


def build_debranded_projection(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    for row in rows:
        source_id = str(row["id"])
        ticker = _ticker_from_row(row)
        row_bytes = canonical_json_bytes(row)
        signals.append(
            {
                "stable_signal_id": sha256_bytes(
                    b"mastermind:momoedge:observe:stable-signal:v1\x00" + source_id.encode("utf-8")
                ),
                "source_row_sha256": sha256_bytes(row_bytes),
                "state": "active" if row["is_active"] else "closed",
                "ticker": ticker,
                "direction": _bounded_text(row.get("direction"), "signal direction", 128),
                "issued_at": row.get("created_at"),
                "closed_at": row.get("closed_at") if not row["is_active"] else None,
                "option_symbol": (
                    _bounded_text(row.get("option_symbol"), "option symbol", 128)
                ),
                "option_contracts": _parse_option_contracts(row, ticker),
            }
        )
    signals.sort(key=lambda signal: (signal["stable_signal_id"], signal["state"]))
    return {
        "schema": PROJECTION_SCHEMA,
        "debranded": True,
        "signals": signals,
    }


def _validate_fresh_capture(
    message: Mapping[str, Any], attempted: datetime, completed: datetime
) -> tuple[bytes, dict[str, Any], Mapping[str, Any]]:
    capture = message["capture"]
    assert isinstance(capture, Mapping)
    _expect_exact_keys(
        capture,
        {
            "request_contract",
            "response_schema",
            "source_closed_cutoff_at",
            "request_started_at",
            "response_completed_at",
            "http_status",
            "response_body_base64",
            "response_byte_count",
            "response_sha256",
            "row_count",
            "active_count",
            "closed_count",
            "proof",
        },
        "capture",
    )
    if capture["request_contract"] != REQUEST_CONTRACT or capture["response_schema"] != RESPONSE_SCHEMA:
        raise MomoEdgeObserveError("fresh response contract is not frozen")
    request_started = _validate_clock(capture["request_started_at"], "request_started_at")
    response_completed = _validate_clock(capture["response_completed_at"], "response_completed_at")
    if request_started < attempted - timedelta(seconds=1) or response_completed < request_started:
        raise MomoEdgeObserveError("page request/response clocks are not causal")
    if response_completed > completed + timedelta(seconds=1):
        raise MomoEdgeObserveError("page response completes after extension observation")
    status_code = capture["http_status"]
    if not isinstance(status_code, int) or isinstance(status_code, bool) or not 200 <= status_code < 300:
        raise MomoEdgeObserveError("fresh response requires exact 2xx status")
    if not isinstance(capture["response_body_base64"], str):
        raise MomoEdgeObserveError("response body must be base64 text")
    try:
        raw = base64.b64decode(capture["response_body_base64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MomoEdgeObserveError("invalid response body base64") from exc
    if len(raw) > MAX_RESPONSE_BYTES or capture["response_byte_count"] != len(raw):
        raise MomoEdgeObserveError("response byte count exceeds or disagrees with bound")
    if capture["response_sha256"] != sha256_bytes(raw):
        raise MomoEdgeObserveError("response digest mismatch")
    rows = strict_json_loads(raw)
    validate_json_complexity(rows)
    reject_sensitive_keys(rows)
    source_cutoff_text = capture["source_closed_cutoff_at"]
    closed_cutoff = _parse_timestamp(source_cutoff_text, "source_closed_cutoff_at")
    request_day = request_started.astimezone(ZoneInfo("America/New_York")).date()
    source_offset = "-04:00" if 3 <= request_day.month <= 11 else "-05:00"
    expected_source_cutoff = f"{request_day.isoformat()}T00:00:00{source_offset}"
    if source_cutoff_text != expected_source_cutoff:
        raise MomoEdgeObserveError("closed cutoff does not match the exact source-defined lexical contract")
    active_count, closed_count = _validate_row_shape(rows, closed_cutoff)
    if (
        capture["row_count"] != len(rows)
        or capture["active_count"] != active_count
        or capture["closed_count"] != closed_count
    ):
        raise MomoEdgeObserveError("response row counts disagree with exact body")
    expected_proof = {
        "fresh_request_observed": True,
        "active_and_source_today_closed_scope": True,
        "complete_new_york_day_proven": False,
        "runtime_response_reconciled": True,
        "sensitive_keys_absent": True,
        "fetch_wrapper_restored": True,
    }
    if capture["proof"] != expected_proof:
        raise MomoEdgeObserveError("fresh response proof is incomplete")
    projection = build_debranded_projection(rows)
    if len(canonical_json_bytes(projection)) > MAX_PROJECTION_BYTES:
        raise MomoEdgeObserveError("debranded projection exceeds the bound")
    return raw, projection, capture


def _validate_private_dir(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise PrivateStoreError(f"private path is not a real directory: {path}")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise PrivateStoreError(f"private directory must be mode 0700: {path}")
    if info.st_uid != os.getuid():
        raise PrivateStoreError(f"private directory owner mismatch: {path}")


def _assert_private_root_scope(root: Path) -> None:
    if not root.is_absolute() or root.name != "momoedge_browser_observe_v1":
        raise PrivateStoreError("private root must be absolute and use the frozen observer directory name")
    if root in {Path("/"), Path.home(), Path.home() / ".mastermind_private"}:
        raise PrivateStoreError("private root is too broad")
    lexical_root = Path(os.path.abspath(root))
    repo_root = Path(__file__).resolve().parents[1]
    cohort_root = Path.home() / ".mastermind_private" / "options_nbbo_cohort_v1"
    for forbidden in (repo_root, cohort_root):
        try:
            common = Path(os.path.commonpath((str(lexical_root), str(forbidden))))
        except ValueError:
            continue
        if common == forbidden:
            raise PrivateStoreError(f"private observer root must be disjoint from {forbidden}")
    for candidate in reversed(root.parents):
        if candidate == Path("/") or (not candidate.exists() and not candidate.is_symlink()):
            continue
        info = candidate.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise PrivateStoreError(f"private root ancestor is a symlink: {candidate}")


def _ensure_private_dir(path: Path) -> None:
    if path.exists() or path.is_symlink():
        _validate_private_dir(path)
        _fsync_directory(path.parent)
        return
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    _validate_private_dir(path)
    _fsync_directory(path.parent)


def _fsync_owned_directory(path: Path) -> None:
    """Fsync an owned real directory whose mode is outside our control."""

    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise PrivateStoreError(f"directory link parent is not a safe owned directory: {path}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) or opened.st_uid != os.getuid():
            raise PrivateStoreError(f"directory link parent descriptor mismatch: {path}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare_private_root(root: Path) -> None:
    _assert_private_root_scope(root)
    old_umask = os.umask(0o077)
    try:
        if not root.parent.exists():
            if root.parent != Path.home() / ".mastermind_private":
                raise PrivateStoreError("private root parent must already exist")
            try:
                root.parent.mkdir(mode=0o700)
            except FileExistsError:
                pass
        _validate_private_dir(root.parent)
        # Re-sync even on recovery: a prior process may have died between the
        # default parent mkdir and its parent-link fsync. Custom parents must
        # pre-exist and are never created by this receiver.
        if root.parent == Path.home() / ".mastermind_private":
            _fsync_owned_directory(root.parent.parent)
        if root.exists() or root.is_symlink():
            _validate_private_dir(root)
            _fsync_directory(root.parent)
        else:
            try:
                root.mkdir(mode=0o700)
            except FileExistsError:
                pass
            _validate_private_dir(root)
            _fsync_directory(root.parent)
        _ensure_private_dir(root / "raw")
        _ensure_private_dir(root / "raw" / "sha256")
        _ensure_private_dir(root / "journal")
        _ensure_private_dir(root / "quarantine")
    finally:
        os.umask(old_umask)


def _validate_private_file(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PrivateStoreError(f"private path is not a regular file: {path}")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise PrivateStoreError(f"private file must be mode 0600: {path}")
    if info.st_uid != os.getuid() or info.st_nlink != 1:
        raise PrivateStoreError(f"private file owner/link count mismatch: {path}")


def _validate_private_fd(descriptor: int, label: str, *, allowed_links: set[int] | None = None) -> None:
    info = os.fstat(descriptor)
    links = allowed_links or {1}
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise PrivateStoreError(f"private descriptor must be a mode-0600 regular file: {label}")
    if info.st_uid != os.getuid() or info.st_nlink not in links:
        raise PrivateStoreError(f"private descriptor owner/link count mismatch: {label}")


def _read_private_file(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        _validate_private_fd(descriptor, str(path))
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_NATIVE_MESSAGE_BYTES:
                raise PrivateStoreError(f"private file exceeds the allowed bound: {path}")
            chunks.append(chunk)
        _validate_private_fd(descriptor, str(path))
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    _validate_private_dir(path)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise PrivateStoreError(f"private directory descriptor mismatch: {path}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reconcile_staging_for(path: Path) -> None:
    """Remove only this writer's bounded temp links after an interrupted write."""

    prefix = f".{path.name}."
    expected_name = re.compile(
        rf"^{re.escape(prefix)}[0-9]{{1,12}}\.[a-f0-9]{{16}}\.tmp$"
    )
    changed = False
    target_info = path.lstat() if path.exists() and not path.is_symlink() else None
    for candidate in path.parent.iterdir():
        if not candidate.name.startswith(prefix):
            continue
        if expected_name.fullmatch(candidate.name) is None:
            raise PrivateStoreError(f"unsafe interrupted staging name: {candidate}")
        info = candidate.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_nlink not in {1, 2}
            or info.st_size > MAX_NATIVE_MESSAGE_BYTES
        ):
            raise PrivateStoreError(f"unsafe interrupted staging object: {candidate}")
        if info.st_nlink == 2:
            if target_info is None or info.st_ino != target_info.st_ino or info.st_dev != target_info.st_dev:
                raise PrivateStoreError(f"staging hardlink does not bind the expected target: {candidate}")
        candidate.unlink()
        changed = True
    if changed:
        _fsync_directory(path.parent)
    if path.exists() or path.is_symlink():
        _validate_private_file(path)
        # A previous process may have linked the immutable target and then lost
        # power (or received an fsync error) before proving the directory link.
        # Re-sync on every recovery/replay before any exact-existing ACK.
        _fsync_directory(path.parent)


def _write_once(path: Path, payload: bytes) -> bool:
    """Create immutable bytes with fsync; return False for exact existing bytes."""

    if not payload or len(payload) > MAX_NATIVE_MESSAGE_BYTES:
        raise PrivateStoreError("private immutable object length is outside the allowed bound")
    _validate_private_dir(path.parent)
    _reconcile_staging_for(path)
    if path.exists() or path.is_symlink():
        if _read_private_file(path) != payload:
            raise ObservationConflict(f"immutable private object conflicts: {path.name}")
        return False

    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _validate_private_fd(descriptor, str(temporary))
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            if _read_private_file(path) != payload:
                raise ObservationConflict(f"immutable private object conflicts: {path.name}")
        finally:
            temporary.unlink(missing_ok=True)
        _fsync_directory(path.parent)
        _validate_private_file(path)
        return True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink(missing_ok=True)


@contextmanager
def private_store_lock(root: Path) -> Iterator[None]:
    prepare_private_root(root)
    lock_path = root / ".receiver.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    existed = lock_path.exists() or lock_path.is_symlink()
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        _validate_private_fd(descriptor, str(lock_path))
        if not existed:
            os.fsync(descriptor)
            _fsync_directory(root)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
        os.fsync(descriptor)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _raw_path(root: Path, digest: str) -> Path:
    first = root / "raw" / "sha256" / digest[:2]
    second = first / digest[2:4]
    _ensure_private_dir(first)
    _ensure_private_dir(second)
    return second / f"{digest}.json"


def _slot_name(scheduled: datetime) -> str:
    return scheduled.strftime("%Y%m%dT%H%M%S.%fZ")


def _validate_store_namespace(base: Path, path: Path, *, is_directory: bool) -> None:
    relative = path.relative_to(base)
    parts = relative.parts
    if base.name == "sha256":
        if is_directory:
            if len(parts) not in {1, 2} or any(not re.fullmatch(r"[a-f0-9]{2}", part) for part in parts):
                raise PrivateStoreError(f"unexpected raw evidence directory: {path}")
            return
        if len(parts) != 3 or not re.fullmatch(r"[a-f0-9]{64}\.json", parts[2]):
            raise PrivateStoreError(f"unexpected raw evidence filename: {path}")
        digest = parts[2][:-5]
        if parts[0] != digest[:2] or parts[1] != digest[2:4]:
            raise PrivateStoreError(f"raw evidence path does not match its digest namespace: {path}")
        return
    if is_directory:
        raise PrivateStoreError(f"unexpected nested private directory: {path}")
    if base.name == "journal" and not re.fullmatch(r"\d{8}T\d{6}\.\d{6}Z\.json", path.name):
        raise PrivateStoreError(f"unexpected journal filename: {path}")
    if base.name == "quarantine" and not re.fullmatch(
        r"\d{8}T\d{6}\.\d{6}Z\.[a-f0-9]{64}\.json", path.name
    ):
        raise PrivateStoreError(f"unexpected quarantine filename: {path}")


def _staging_target(path: Path) -> Path | None:
    match = re.fullmatch(r"\.(.+\.json)\.([0-9]{1,12})\.([a-f0-9]{16})\.tmp", path.name)
    return path.with_name(match.group(1)) if match is not None else None


def _reconcile_namespace_staging(base: Path) -> None:
    """Recover every strictly shaped interrupted object before capacity scans."""

    pending = [base]
    ordinary_files: list[Path] = []
    staged_targets: set[Path] = set()
    while pending:
        directory = pending.pop()
        _validate_private_dir(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise PrivateStoreError(f"symlink rejected in private tree: {path}")
                if stat.S_ISDIR(info.st_mode):
                    _validate_store_namespace(base, path, is_directory=True)
                    _validate_private_dir(path)
                    pending.append(path)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise PrivateStoreError(f"unexpected private tree node: {path}")
                target = _staging_target(path)
                if target is not None:
                    _validate_store_namespace(base, target, is_directory=False)
                    staged_targets.add(target)
                    continue
                _validate_store_namespace(base, path, is_directory=False)
                ordinary_files.append(path)

    for target in sorted(staged_targets):
        _reconcile_staging_for(target)
    for path in ordinary_files:
        if path.exists() or path.is_symlink():
            _validate_private_file(path)


def _reconcile_all_staging(root: Path) -> None:
    for relative in (Path("raw/sha256"), Path("journal"), Path("quarantine")):
        _reconcile_namespace_staging(root / relative)


def _private_tree_usage(base: Path) -> tuple[int, int]:
    count = 0
    total = 0
    pending = [base]
    while pending:
        directory = pending.pop()
        _validate_private_dir(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise PrivateStoreError(f"symlink rejected in private tree: {path}")
                if stat.S_ISDIR(info.st_mode):
                    _validate_store_namespace(base, path, is_directory=True)
                    _validate_private_dir(path)
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    _validate_store_namespace(base, path, is_directory=False)
                    _validate_private_file(path)
                    count += 1
                    total += info.st_size
                else:
                    raise PrivateStoreError(f"unexpected private tree node: {path}")
    return count, total


def _assert_capacity(root: Path, *, raw_bytes: int = 0, journal: bool = False, quarantine: bool = False) -> None:
    if raw_bytes:
        count, total = _private_tree_usage(root / "raw" / "sha256")
        if count >= MAX_RAW_OBJECTS or total + raw_bytes > MAX_RAW_TOTAL_BYTES:
            raise PrivateStoreError("private raw evidence capacity reached; operator archival is required")
    if journal:
        count, _ = _private_tree_usage(root / "journal")
        if count >= MAX_JOURNAL_FILES:
            raise PrivateStoreError("private journal capacity reached; operator archival is required")
    if quarantine:
        count, _ = _private_tree_usage(root / "quarantine")
        if count >= MAX_QUARANTINE_FILES:
            raise PrivateStoreError("private quarantine capacity reached; operator review is required")


def _safe_unavailable_journal(
    message: Mapping[str, Any], reason: str, message_sha256: str
) -> dict[str, Any]:
    return {
        "schema": JOURNAL_SCHEMA,
        "mode": "observe_only",
        "extension_version": message["extension_version"],
        "scheduled_at": message["scheduled_at"],
        "attempted_at": message["attempted_at"],
        "completed_at": message["completed_at"],
        "disposition": "unavailable",
        "reason": reason,
        "message_sha256": message_sha256,
        "capture": None,
        "coverage_eligible": False,
        "authority": dict(FALSE_AUTHORITY),
    }


def _fresh_journal(
    message: Mapping[str, Any], message_sha256: str, raw: bytes, projection: Mapping[str, Any], capture: Mapping[str, Any]
) -> dict[str, Any]:
    digest = sha256_bytes(raw)
    return {
        "schema": JOURNAL_SCHEMA,
        "mode": "observe_only",
        "extension_version": message["extension_version"],
        "scheduled_at": message["scheduled_at"],
        "attempted_at": message["attempted_at"],
        "completed_at": message["completed_at"],
        "disposition": "fresh_response",
        "reason": None,
        "message_sha256": message_sha256,
        "capture": {
            "request_contract": capture["request_contract"],
            "response_schema": capture["response_schema"],
            "source_closed_cutoff_at": capture["source_closed_cutoff_at"],
            "request_started_at": capture["request_started_at"],
            "response_completed_at": capture["response_completed_at"],
            "http_status": capture["http_status"],
            "raw_ref": {
                "sha256": digest,
                "byte_count": len(raw),
                "relative_path": f"raw/sha256/{digest[:2]}/{digest[2:4]}/{digest}.json",
            },
            "row_count": capture["row_count"],
            "active_count": capture["active_count"],
            "closed_count": capture["closed_count"],
            "proof": capture["proof"],
            "projection": projection,
        },
        "coverage_eligible": False,
        "authority": dict(FALSE_AUTHORITY),
    }


def persist_observation(message_bytes: bytes, root: Path = PRIVATE_ROOT_DEFAULT) -> dict[str, Any]:
    if not message_bytes or len(message_bytes) > MAX_NATIVE_MESSAGE_BYTES:
        raise MomoEdgeObserveError("native message length is outside the allowed bound")
    message = strict_json_loads(message_bytes)
    scheduled, attempted, completed = _validate_common_observation(message)
    del attempted, completed
    message_digest = sha256_bytes(message_bytes)

    with private_store_lock(root):
        _reconcile_all_staging(root)
        raw_to_write: bytes | None = None
        if message["disposition"] == "unavailable":
            journal = _safe_unavailable_journal(message, message["reason"], message_digest)
        else:
            try:
                raw, projection, capture = _validate_fresh_capture(
                    message,
                    _parse_timestamp(message["attempted_at"], "attempted_at"),
                    _parse_timestamp(message["completed_at"], "completed_at"),
                )
            except SensitiveSourceError:
                journal = _safe_unavailable_journal(message, "sensitive_key_rejected", message_digest)
            except MomoEdgeObserveError:
                journal = _safe_unavailable_journal(message, "invalid_fresh_response", message_digest)
            else:
                raw_to_write = raw
                journal = _fresh_journal(message, message_digest, raw, projection, capture)

        journal_bytes = canonical_json_bytes(journal)
        if len(journal_bytes) > MAX_NATIVE_MESSAGE_BYTES:
            raise PrivateStoreError("debranded journal exceeds the private object bound")
        journal_path = root / "journal" / f"{_slot_name(scheduled)}.json"
        _reconcile_staging_for(journal_path)
        if journal_path.exists() or journal_path.is_symlink():
            existing = _read_private_file(journal_path)
            if existing != journal_bytes:
                conflict = {
                    "schema": "options.momoedge_browser_observe_conflict/v1",
                    "scheduled_at": message["scheduled_at"],
                    "existing_journal_sha256": sha256_bytes(existing),
                    "incoming_journal_sha256": sha256_bytes(journal_bytes),
                    "incoming_message_sha256": message_digest,
                }
                conflict_bytes = canonical_json_bytes(conflict)
                conflict_path = root / "quarantine" / f"{_slot_name(scheduled)}.{sha256_bytes(conflict_bytes)}.json"
                _reconcile_staging_for(conflict_path)
                if not conflict_path.exists():
                    _assert_capacity(root, quarantine=True)
                _write_once(conflict_path, conflict_bytes)
                raise ObservationConflict("slot already contains different immutable journal bytes")
            if raw_to_write is not None:
                raw_digest = sha256_bytes(raw_to_write)
                raw_path = _raw_path(root, raw_digest)
                _reconcile_staging_for(raw_path)
                if not raw_path.exists():
                    _assert_capacity(root, raw_bytes=len(raw_to_write))
                _write_once(raw_path, raw_to_write)
            created = False
        else:
            _assert_capacity(root, journal=True)
            if raw_to_write is not None:
                raw_digest = sha256_bytes(raw_to_write)
                raw_path = _raw_path(root, raw_digest)
                _reconcile_staging_for(raw_path)
                if not raw_path.exists():
                    _assert_capacity(root, raw_bytes=len(raw_to_write))
                _write_once(raw_path, raw_to_write)
            created = _write_once(journal_path, journal_bytes)

        return {
            "schema": ACK_SCHEMA,
            "accepted": True,
            "created": created,
            "disposition": journal["disposition"],
            "reason": journal["reason"],
            "journal_sha256": sha256_bytes(journal_bytes),
            "raw_sha256": (
                journal["capture"]["raw_ref"]["sha256"] if journal["capture"] is not None else None
            ),
            "coverage_eligible": False,
        }


def read_native_frame(stream: BinaryIO) -> bytes:
    def read_exact(length: int, label: str) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            chunk = stream.read(remaining)
            if not chunk:
                raise MomoEdgeObserveError(f"native message frame {label} is incomplete")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    header = read_exact(4, "header")
    length = int.from_bytes(header, byteorder="little", signed=False)
    if length <= 0 or length > MAX_NATIVE_MESSAGE_BYTES:
        raise MomoEdgeObserveError("native message frame length is outside the allowed bound")
    return read_exact(length, "body")


def write_native_frame(stream: BinaryIO, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_NATIVE_MESSAGE_BYTES:
        raise MomoEdgeObserveError("native response frame exceeds the allowed bound")
    stream.write(len(payload).to_bytes(4, byteorder="little", signed=False))
    stream.write(payload)
    stream.flush()
