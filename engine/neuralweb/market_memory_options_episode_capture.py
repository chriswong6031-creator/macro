"""Prospective owner-time W1A capture requests for option episodes.

The live-flow poller is the first process that can prove both halves of the
owner clock: it fsyncs a decision receipt, then samples and fsyncs the separate
``available_at`` receipt.  This module lets that producer create a private,
missing-only Market Memory packet at that exact boundary.  It never writes the
episode ledger; the nightly owner remains the sole episode advancer.

Only the predeclared SPY canary is supported.  A session identity anchor must
be created before the regular-session open, and every request is rebuilt from
the exact owner event plus that anchor before admission.  Requests travel over
a forced-command SSH key to the production W1A writer.  Failed or late
transport remains an explicit abstention; no historical retry can backdate a
packet after the 15-minute W1A window.
"""

from __future__ import annotations

import base64
import copy
import fcntl
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from engine import options_signal_episode
from engine.neuralweb import market_memory, market_memory_identity, market_memory_pit
from engine.session_digest import session_window_et
from lib import nyse_calendar

ANCHOR_SCHEMA = "market_memory.options_context_session_identity_anchor/v1"
REQUEST_SCHEMA = "market_memory.options_context_capture_request/v1"
RESPONSE_SCHEMA = "market_memory.options_context_capture_response/v1"
TRANSPORT_RECEIPT_SCHEMA = "market_memory.options_context_transport_receipt/v1"
TRANSPORT_BATCH_INTENT_SCHEMA = (
    "market_memory.options_context_transport_batch_intent/v1"
)
OWNER_AVAILABILITY_SCHEMA = "market_memory.options_context_owner_availability/v1"
PUBLICATION_PROOF_SCHEMA = "market_memory.options_context_publication_proof/v1"

_REMOTE_TARGET = "root@146.190.142.17"
_ANCHOR_ID = re.compile(r"mmoptanchor_[a-f0-9]{64}\Z")
_REQUEST_ID = re.compile(r"mmoptrequest_[a-f0-9]{64}\Z")
_BATCH_ID = re.compile(r"mmoptbatch_[a-f0-9]{64}\Z")
_EPISODE_ID = re.compile(r"osep_[a-f0-9]{24}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_RFC3339_UTC = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)

MAX_CONFIG_BYTES = 32 * 1024
MAX_ANCHOR_BYTES = 64 * 1024
MAX_REQUEST_BYTES = 256 * 1024
MAX_BATCH_BYTES = 1024 * 1024
MAX_BATCH_REQUESTS = 8
MAX_PENDING_REQUESTS = 64
MAX_LIFETIME_REQUESTS = 4_096
MAX_ANCHORS = 64
MAX_DRAIN_BATCHES = MAX_PENDING_REQUESTS // MAX_BATCH_REQUESTS
MAX_ANCHOR_LEAD = timedelta(days=7)
# Leave transport and remote validation margin inside W1A's frozen 15 minutes.
MAX_SEND_AGE = timedelta(minutes=13)
MAX_FUTURE_SKEW = timedelta(seconds=5)

_EVIDENCE_POLICY = {
    "prospective_only": True,
    "durable_owner_decision_required": True,
    "durable_owner_availability_required": True,
    "exact_requested_as_of": True,
    "nearest_or_latest_fallback_allowed": False,
    "historical_backfill_allowed": False,
    "episode_ledger_write_allowed": False,
    "selector_impact_allowed": False,
    "retrieval_authority": False,
    "forecast_authority": False,
    "training_eligible": False,
    "promotion_eligible": False,
    "context_only": True,
}


class OptionsEpisodeContextCaptureError(RuntimeError):
    """A prospective option-context request or transport boundary failed."""


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
        raise OptionsEpisodeContextCaptureError(
            "options context value is not finite canonical JSON"
        ) from exc


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _strict_object(body: bytes, *, label: str, maximum: int) -> dict[str, Any]:
    if not body or len(body) > maximum:
        raise OptionsEpisodeContextCaptureError(f"{label} exceeds its byte bound")
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON token {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise OptionsEpisodeContextCaptureError(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise OptionsEpisodeContextCaptureError(f"{label} must be an object")
    return value


def _exact_utc(value: object, *, field: str) -> tuple[datetime, str]:
    if type(value) is not str or _RFC3339_UTC.fullmatch(value) is None:
        raise OptionsEpisodeContextCaptureError(
            f"{field} must be an exact RFC3339 UTC timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OptionsEpisodeContextCaptureError(f"{field} is not a real time") from exc
    if parsed.utcoffset() != timedelta(0):
        raise OptionsEpisodeContextCaptureError(f"{field} must be UTC")
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise OptionsEpisodeContextCaptureError(f"{field} is not canonical UTC")
    return parsed.astimezone(timezone.utc), canonical


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + sha256(_canonical_bytes(core)).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_private_directory(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise OptionsEpisodeContextCaptureError(
            f"cannot inspect {label} safely"
        ) from exc
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_uid != os.getuid()
    ):
        raise OptionsEpisodeContextCaptureError(
            f"{label} must be an owned private directory"
        )


def _mkdir_private_durable(path: Path) -> None:
    """Create missing private directories and persist every parent link."""

    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        if cursor.is_symlink():
            raise OptionsEpisodeContextCaptureError(
                "capture outbox path contains a symlink"
            )
        missing.append(cursor)
        if cursor == cursor.parent:
            raise OptionsEpisodeContextCaptureError(
                "capture outbox has no safe existing parent"
            )
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise OptionsEpisodeContextCaptureError(
            "capture outbox parent is not a directory"
        )
    for directory in reversed(missing):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            if directory.is_symlink() or not directory.is_dir():
                raise OptionsEpisodeContextCaptureError(
                    "capture outbox directory race was unsafe"
                ) from None
        _validate_private_directory(directory, label="new capture outbox directory")
        _fsync_directory(directory.parent)


def _private_directory(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise OptionsEpisodeContextCaptureError(
            "capture outbox root must be absolute"
        )
    cursor = Path(expanded.anchor)
    for part in expanded.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise OptionsEpisodeContextCaptureError(
                "capture outbox path contains a symlink"
            )
    candidate = expanded.resolve()
    if candidate == Path(candidate.anchor) or candidate == Path.home().resolve():
        raise OptionsEpisodeContextCaptureError("capture outbox root is too broad")
    if {"site", "site.served"}.intersection(candidate.parts):
        raise OptionsEpisodeContextCaptureError("capture outbox cannot use a public root")
    if path.is_symlink():
        raise OptionsEpisodeContextCaptureError("capture outbox root is a symlink")
    _mkdir_private_durable(candidate)
    _validate_private_directory(candidate, label="capture outbox root")
    # Re-prove an entry left visible by an interrupted mkdir parent fsync.
    _fsync_directory(candidate.parent)
    return candidate


def _private_child(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink():
        raise OptionsEpisodeContextCaptureError("capture outbox contains a symlink")
    _mkdir_private_durable(path)
    _validate_private_directory(path, label="capture outbox child")
    # Existing-but-unpersisted child links are harmless only after this proof.
    _fsync_directory(root)
    return path


def _unlink_durable(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


def _write_create_once(
    path: Path,
    body: bytes,
    *,
    label: str,
    recover_existing: bool = False,
) -> None:
    if len(body) <= 0:
        raise OptionsEpisodeContextCaptureError(f"{label} is empty")
    _validate_private_directory(path.parent, label=f"{label} parent")
    if path.exists() or path.is_symlink():
        existing = _read_file(path, maximum=len(body), label=f"existing {label}")
        if existing != body:
            raise OptionsEpisodeContextCaptureError(
                f"immutable {label} collision"
            )
        if not recover_existing:
            raise OptionsEpisodeContextCaptureError(
                f"{label} publication is not durably proven"
            )
        _fsync_directory(path.parent)
        return
    temporary = path.parent / f".{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    descriptor: int | None = None
    temporary_created = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        temporary_created = True
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - defensive OS boundary
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(temporary, path, follow_symlinks=False)
            _fsync_directory(path.parent)
        except FileExistsError:
            existing = _read_file(path, maximum=len(body), label=f"existing {label}")
            if existing != body:
                raise OptionsEpisodeContextCaptureError(
                    f"immutable {label} collision"
                )
            if not recover_existing:
                raise OptionsEpisodeContextCaptureError(
                    f"{label} publication is not durably proven"
                )
            _fsync_directory(path.parent)
    except OptionsEpisodeContextCaptureError:
        raise
    except OSError as exc:
        raise OptionsEpisodeContextCaptureError(
            f"cannot publish immutable {label}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_created and temporary.exists():
            try:
                temporary.unlink()
                _fsync_directory(path.parent)
            except OSError as exc:
                raise OptionsEpisodeContextCaptureError(
                    f"cannot durably clean temporary {label}"
                ) from exc


def _publication_proof(*, label: str, object_name: str, body: bytes) -> bytes:
    return _canonical_bytes(
        {
            "schema": PUBLICATION_PROOF_SCHEMA,
            "label": label,
            "object_name": object_name,
            "body_sha256": sha256(body).hexdigest(),
        }
    )


def _write_proven_create_once(
    path: Path,
    body: bytes,
    *,
    proof_path: Path,
    label: str,
    may_reprove_unproven: bool,
) -> bool:
    """Publish bytes plus a causal proof created only after parent durability."""

    proof = _publication_proof(label=label, object_name=path.name, body=body)
    if proof_path.exists() or proof_path.is_symlink():
        _write_create_once(
            proof_path,
            proof,
            label=f"{label} publication proof",
            recover_existing=True,
        )
        existing = _read_file(path, maximum=len(body), label=f"proven {label}")
        if existing != body:
            raise OptionsEpisodeContextCaptureError(
                f"proven {label} differs from its proof"
            )
        return True
    if path.exists() or path.is_symlink():
        if not may_reprove_unproven:
            return False
        _write_create_once(path, body, label=label, recover_existing=True)
    else:
        _write_create_once(path, body, label=label)
    _write_create_once(
        proof_path,
        proof,
        label=f"{label} publication proof",
        recover_existing=True,
    )
    return True


def _has_publication_proof(
    path: Path, body: bytes, *, proof_path: Path, label: str
) -> bool:
    if not proof_path.exists() and not proof_path.is_symlink():
        return False
    proof = _publication_proof(label=label, object_name=path.name, body=body)
    _write_create_once(
        proof_path,
        proof,
        label=f"{label} publication proof",
        recover_existing=True,
    )
    return True


def _read_file(path: Path, *, maximum: int, label: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise OptionsEpisodeContextCaptureError(f"cannot read {label} safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > maximum
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_uid != os.getuid()
        ):
            raise OptionsEpisodeContextCaptureError(
                f"{label} is not a bounded private regular file"
            )
        body = b""
        while len(body) <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - len(body)))
            if not chunk:
                break
            body += chunk
    finally:
        os.close(descriptor)
    if len(body) != metadata.st_size or len(body) > maximum:
        raise OptionsEpisodeContextCaptureError(f"{label} changed while reading")
    return body


def _read_source_file(path: Path, *, maximum: int, label: str) -> bytes:
    """Read one bounded immutable input without requiring private file mode."""

    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise OptionsEpisodeContextCaptureError(f"cannot read {label} safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= maximum:
            raise OptionsEpisodeContextCaptureError(
                f"{label} is not a bounded regular file"
            )
        body = b""
        while len(body) <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - len(body)))
            if not chunk:
                break
            body += chunk
    finally:
        os.close(descriptor)
    if len(body) != metadata.st_size or len(body) > maximum:
        raise OptionsEpisodeContextCaptureError(f"{label} changed while reading")
    return body


def _config_from_bytes(body: bytes) -> dict[str, Any]:
    value = _strict_object(body, label="canary identity config", maximum=MAX_CONFIG_BYTES)
    try:
        # Reuse the frozen config authority/opaque-ID validator.  The session
        # adapter changes validity clocks, not canary identity semantics.
        return market_memory_identity._validate_config(value)
    except market_memory_identity.MarketMemoryIdentityError as exc:
        raise OptionsEpisodeContextCaptureError(
            "canary identity config fails its frozen contract"
        ) from exc


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OptionsEpisodeContextCaptureError("session anchor clock must be UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _anchor_projection(
    *, session_date: str, config_body: bytes, observed_at: datetime
) -> dict[str, Any]:
    try:
        session = date.fromisoformat(session_date)
    except (TypeError, ValueError) as exc:
        raise OptionsEpisodeContextCaptureError("anchor session date is invalid") from exc
    if session.isoformat() != session_date or not nyse_calendar.is_session(session):
        raise OptionsEpisodeContextCaptureError("anchor requires an NYSE session")
    observed = observed_at.astimezone(timezone.utc)
    open_et, close_et = session_window_et(session)
    session_open = open_et.astimezone(timezone.utc)
    session_close = close_et.astimezone(timezone.utc)
    if observed >= session_open:
        raise OptionsEpisodeContextCaptureError(
            "session identity anchor must be observed before the market open"
        )
    if session_open - observed > MAX_ANCHOR_LEAD:
        raise OptionsEpisodeContextCaptureError(
            "session identity anchor is too far ahead of its session"
        )
    config = _config_from_bytes(config_body)
    config_sha = sha256(config_body).hexdigest()
    created_at = _format_utc(observed)
    valid_from = _format_utc(session_open)
    valid_through = _format_utc(session_close)
    subject = config["subject"]
    universe = config["universe"]
    calendar = config["calendar"]
    membership = {
        "schema": market_memory.CANONICAL_SOURCE_REGISTRY[
            market_memory_identity.MEMBERSHIP_SOURCE_ID
        ].source_schema,
        "source_id": market_memory_identity.MEMBERSHIP_SOURCE_ID,
        "config_sha256": config_sha,
        "symbol": market_memory_identity.CANARY_SYMBOL,
        "canonical_subject_key": subject["canonical_key"],
        "subject_id": subject["subject_id"],
        "instrument_key": subject["instrument_key"],
        "instrument_id": subject["instrument_id"],
        "identity_version": subject["identity_version"],
        "mic": market_memory_identity.CANARY_MIC,
        "currency": market_memory_identity.CANARY_CURRENCY,
        "universe_id": universe["universe_id"],
        "membership_status": market_memory_identity.CANARY_MEMBERSHIP_STATUS,
        "observed_at": created_at,
        "valid_from": valid_from,
        "valid_through": valid_through,
        "authority": copy.deepcopy(config["authority"]),
    }
    calendar_artifact = {
        "schema": market_memory.CANONICAL_SOURCE_REGISTRY[
            market_memory_identity.CALENDAR_SOURCE_ID
        ].source_schema,
        "source_id": market_memory_identity.CALENDAR_SOURCE_ID,
        "config_sha256": config_sha,
        "canonical_key": calendar["canonical_key"],
        "calendar_id": calendar["calendar_id"],
        "market_session": market_memory_identity.CANARY_SESSION,
        "rules_version": calendar["rules_version"],
        "coverage": calendar["coverage"],
        "observed_at": created_at,
        "valid_from": valid_from,
        "valid_through": valid_through,
        "quality": copy.deepcopy(calendar["quality"]),
        "authority": copy.deepcopy(config["authority"]),
    }
    anchor: dict[str, Any] = {
        "schema": ANCHOR_SCHEMA,
        "anchor_id": "",
        "session_date": session_date,
        "created_at": created_at,
        "valid_from": valid_from,
        "valid_through": valid_through,
        "config_body_base64": base64.b64encode(config_body).decode("ascii"),
        "config_sha256": config_sha,
        "subject": {
            "subject_id": subject["subject_id"],
            "instrument_id": subject["instrument_id"],
        },
        "membership_artifact": membership,
        "membership_artifact_sha256": sha256(_canonical_bytes(membership)).hexdigest(),
        "calendar_artifact": calendar_artifact,
        "calendar_artifact_sha256": sha256(
            _canonical_bytes(calendar_artifact)
        ).hexdigest(),
        "authority": dict(market_memory.AUTHORITY),
    }
    anchor["anchor_id"] = _content_id(
        "mmoptanchor_", anchor, field="anchor_id"
    )
    return anchor


def validate_session_anchor(value: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "schema",
        "anchor_id",
        "session_date",
        "created_at",
        "valid_from",
        "valid_through",
        "config_body_base64",
        "config_sha256",
        "subject",
        "membership_artifact",
        "membership_artifact_sha256",
        "calendar_artifact",
        "calendar_artifact_sha256",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise OptionsEpisodeContextCaptureError("session anchor fields drift")
    clean = copy.deepcopy(dict(value))
    if clean["schema"] != ANCHOR_SCHEMA:
        raise OptionsEpisodeContextCaptureError("session anchor schema drift")
    anchor_id = clean.get("anchor_id")
    if type(anchor_id) is not str or _ANCHOR_ID.fullmatch(anchor_id) is None:
        raise OptionsEpisodeContextCaptureError("session anchor id is malformed")
    encoded = clean.get("config_body_base64")
    if type(encoded) is not str or len(encoded) > MAX_CONFIG_BYTES * 2:
        raise OptionsEpisodeContextCaptureError("session anchor config encoding is invalid")
    try:
        config_body = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise OptionsEpisodeContextCaptureError(
            "session anchor config encoding is invalid"
        ) from exc
    created, _ = _exact_utc(clean.get("created_at"), field="anchor.created_at")
    expected = _anchor_projection(
        session_date=str(clean.get("session_date") or ""),
        config_body=config_body,
        observed_at=created,
    )
    if clean != expected:
        raise OptionsEpisodeContextCaptureError(
            "session anchor differs from its config, session, or source artifacts"
        )
    if _content_id("mmoptanchor_", clean, field="anchor_id") != anchor_id:
        raise OptionsEpisodeContextCaptureError("session anchor id does not bind content")
    if len(_canonical_bytes(clean)) > MAX_ANCHOR_BYTES:
        raise OptionsEpisodeContextCaptureError("session anchor exceeds its byte bound")
    return clean


def create_or_load_session_anchor(
    root: str | Path,
    *,
    session_date: str,
    config_path: str | Path = market_memory_identity.DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """Create today's identity anchor before open, or load its exact prior bytes."""

    store = _private_directory(Path(root))
    anchors = _private_child(store, "anchors")
    anchor_proofs = _private_child(store, "anchor_proofs")
    path = anchors / f"{session_date}.json"
    proof_path = anchor_proofs / f"{session_date}.json"
    descriptor = os.open(store, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if path.exists() or path.is_symlink():
            body = _read_file(path, maximum=MAX_ANCHOR_BYTES, label="session anchor")
            anchor = validate_session_anchor(
                _strict_object(body, label="session anchor", maximum=MAX_ANCHOR_BYTES)
            )
            session = date.fromisoformat(session_date)
            session_open = session_window_et(session)[0].astimezone(timezone.utc)
            if not _write_proven_create_once(
                path,
                body,
                proof_path=proof_path,
                label="session anchor",
                may_reprove_unproven=_utc_now().astimezone(timezone.utc) < session_open,
            ):
                raise OptionsEpisodeContextCaptureError(
                    "unproven session anchor after open permanently abstains"
                )
            return anchor
        anchor_files = sorted(anchors.iterdir(), key=lambda item: item.name)
        for anchor_file in anchor_files:
            if (
                anchor_file.is_symlink()
                or not anchor_file.is_file()
                or anchor_file.suffix != ".json"
                or _DATE.fullmatch(anchor_file.stem) is None
                or stat.S_IMODE(anchor_file.stat().st_mode) & 0o077
            ):
                raise OptionsEpisodeContextCaptureError(
                    "session anchor store contains an unowned path"
                )
        if len(anchor_files) >= MAX_ANCHORS:
            raise OptionsEpisodeContextCaptureError(
                "session anchor store reached its fixed pilot bound"
            )
        config_body = _read_source_file(
            Path(config_path),
            maximum=MAX_CONFIG_BYTES,
            label="canary identity config",
        )
        anchor = _anchor_projection(
            session_date=session_date,
            config_body=config_body,
            observed_at=_utc_now(),
        )
        body = _canonical_bytes(anchor)
        if not _write_proven_create_once(
            path,
            body,
            proof_path=proof_path,
            label="session anchor",
            may_reprove_unproven=True,
        ):  # pragma: no cover - a new path is always provable
            raise OptionsEpisodeContextCaptureError(
                "cannot prove prospective session anchor publication"
            )
        return validate_session_anchor(anchor)
    except OSError as exc:
        raise OptionsEpisodeContextCaptureError(
            "cannot create the prospective session identity anchor"
        ) from exc
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _source_receipt(
    *,
    anchor: Mapping[str, Any],
    source_id: str,
    artifact_sha256: str,
    identity_binding: dict[str, Any],
    quality: dict[str, Any],
    cutoff: datetime,
) -> dict[str, Any]:
    source_spec = market_memory.CANONICAL_SOURCE_REGISTRY[source_id]
    vintage_id, revision_id = market_memory_identity._source_version_ids(
        source_id, artifact_sha256
    )
    observed, observed_at = _exact_utc(
        anchor["created_at"], field="anchor.created_at"
    )
    receipt: dict[str, Any] = {
        "receipt_id": "mmsrc_" + "0" * 64,
        "source_id": source_id,
        "source_role": source_spec.source_role,
        "source_schema": source_spec.source_schema,
        "artifact_sha256": artifact_sha256,
        "event_time": observed_at,
        "measurement_end": observed_at,
        "available_at": observed_at,
        "observed_at": observed_at,
        "vintage_id": vintage_id,
        "revision_id": revision_id,
        "pit_basis": "live_captured",
        "availability_class": "revision",
        "availability_rule": source_spec.availability_rule,
        "market_session": market_memory_identity.CANARY_SESSION,
        "valid_from": anchor["valid_from"],
        "valid_through": anchor["valid_through"],
        "identity_binding": identity_binding,
        "quality": copy.deepcopy(quality),
        "age_at_cutoff_seconds": (cutoff - observed).total_seconds(),
    }
    identity_binding["content_sha256"] = market_memory._identity_binding_sha256(
        receipt, identity_binding
    )
    receipt["receipt_id"] = market_memory._source_receipt_id(receipt)
    return receipt


def _identity_inputs(
    anchor: Mapping[str, Any], *, cutoff: datetime
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    membership = anchor["membership_artifact"]
    calendar = anchor["calendar_artifact"]
    membership_binding = {
        "schema": "market_memory.security_membership_binding.v1",
        "subject_id": membership["subject_id"],
        "instrument_id": membership["instrument_id"],
        "identity_version": membership["identity_version"],
        "universe_id": membership["universe_id"],
        "membership_status": membership["membership_status"],
        "content_sha256": "0" * 64,
    }
    membership_receipt = _source_receipt(
        anchor=anchor,
        source_id=market_memory_identity.MEMBERSHIP_SOURCE_ID,
        artifact_sha256=anchor["membership_artifact_sha256"],
        identity_binding=membership_binding,
        quality={
            "status": "ok",
            "flags": [],
            "staleness_seconds": 0,
            "imputed": False,
        },
        cutoff=cutoff,
    )
    calendar_binding = {
        "schema": "market_memory.market_calendar_binding.v1",
        "calendar_id": calendar["calendar_id"],
        "market_session": calendar["market_session"],
        "content_sha256": "0" * 64,
    }
    calendar_receipt = _source_receipt(
        anchor=anchor,
        source_id=market_memory_identity.CALENDAR_SOURCE_ID,
        artifact_sha256=anchor["calendar_artifact_sha256"],
        identity_binding=calendar_binding,
        quality=calendar["quality"],
        cutoff=cutoff,
    )
    identity: dict[str, Any] = {
        "receipt_id": "mmidentity_" + "0" * 64,
        "subject_id": membership["subject_id"],
        "instrument_id": membership["instrument_id"],
        "identity_version": membership["identity_version"],
        "universe_id": membership["universe_id"],
        "membership_vintage_id": membership_receipt["vintage_id"],
        "membership_revision_id": membership_receipt["revision_id"],
        "membership_source_receipt_id": membership_receipt["receipt_id"],
        "membership_valid_from": anchor["valid_from"],
        "membership_valid_through": anchor["valid_through"],
        "calendar_id": calendar["calendar_id"],
        "calendar_version": calendar_receipt["vintage_id"],
        "calendar_revision_id": calendar_receipt["revision_id"],
        "calendar_source_receipt_id": calendar_receipt["receipt_id"],
        "calendar_valid_from": anchor["valid_from"],
        "calendar_valid_through": anchor["valid_through"],
        "membership_status": membership["membership_status"],
        "effective_at": anchor["valid_from"],
        "available_at": anchor["created_at"],
        "observed_at": anchor["created_at"],
        "pit_basis": "live_captured",
        "source_receipt_ids": sorted(
            [membership_receipt["receipt_id"], calendar_receipt["receipt_id"]]
        ),
        "quality": copy.deepcopy(calendar["quality"]),
    }
    identity["receipt_id"] = market_memory._identity_receipt_id(identity)
    return [membership_receipt, calendar_receipt], identity


def _missing_features(observed_at: str) -> list[dict[str, Any]]:
    return [
        {
            "feature_id": feature_id,
            "feature_role": "decision_time_context",
            "domain": spec.domain,
            "status": "missing",
            "value": None,
            "unit": spec.unit,
            "observed_at": observed_at,
            "pit_basis": "unknown",
            "transform_version": "market_memory.missing.v1",
            "source_receipt_ids": [],
            "missing_reason": "adapter_not_implemented",
            "quality": {
                "status": "missing",
                "flags": ["not_captured"],
                "staleness_seconds": None,
                "imputed": False,
            },
        }
        for feature_id, spec in market_memory.CANONICAL_FEATURE_REGISTRY.items()
    ]


def _request_projection(
    *, anchor: Mapping[str, Any], owner_event: Mapping[str, Any], session_date: str
) -> dict[str, Any] | None:
    clean_anchor = validate_session_anchor(anchor)
    if clean_anchor["session_date"] != session_date:
        raise OptionsEpisodeContextCaptureError(
            "owner event and identity anchor sessions differ"
        )
    event = copy.deepcopy(dict(owner_event))
    try:
        episode = options_signal_episode.episode_from_live_event(
            event,
            source_snapshot_asof=str(event.get("available_at") or ""),
            source_artifact=f"live_flow/events/{session_date}.jsonl",
        )
    except options_signal_episode.ContractError as exc:
        raise OptionsEpisodeContextCaptureError(
            "owner event does not project to a valid durable episode"
        ) from exc
    if episode["ticker"] != market_memory_identity.CANARY_SYMBOL:
        return None
    event_dt, event_time = _exact_utc(
        episode["event_time"], field="episode.event_time"
    )
    cutoff_dt, cutoff = _exact_utc(
        episode["available_at"], field="episode.available_at"
    )
    anchor_dt, _ = _exact_utc(
        clean_anchor["created_at"], field="anchor.created_at"
    )
    if not anchor_dt <= event_dt < cutoff_dt:
        raise OptionsEpisodeContextCaptureError(
            "capture requires distinct owner event and availability clocks after the anchor"
        )
    source_receipts, identity_receipt = _identity_inputs(
        clean_anchor, cutoff=cutoff_dt
    )
    try:
        packet = market_memory.build_as_known_at_context(
            subject=clean_anchor["subject"],
            event_time=event_time,
            as_known_at=cutoff,
            mode="operational_pit",
            source_receipts=source_receipts,
            identity_receipt=identity_receipt,
            feature_receipts=_missing_features(cutoff),
        )
    except market_memory.TemporalContractError as exc:
        raise OptionsEpisodeContextCaptureError(
            "owner-time packet fails the frozen W0 contract"
        ) from exc
    if any(row["status"] != "missing" for row in packet["feature_receipts"]):
        raise OptionsEpisodeContextCaptureError(
            "W1A request cannot carry observed features"
        )
    owner_event_body = _canonical_bytes(event)
    episode_body = _canonical_bytes(episode)
    request: dict[str, Any] = {
        "schema": REQUEST_SCHEMA,
        "request_id": "",
        "owner": {
            "schema": "live_flow.event_stage/v1",
            "source_event_id": episode["source_event_id"],
            "owner_event_sha256": sha256(owner_event_body).hexdigest(),
            "projected_episode_id": episode["episode_id"],
            "projected_episode_sha256": sha256(episode_body).hexdigest(),
            "session_date": session_date,
            "ticker": episode["ticker"],
            "event_time": event_time,
            "available_at": cutoff,
        },
        "owner_event": event,
        "identity_anchor": clean_anchor,
        "packet": packet,
        "evidence_policy": copy.deepcopy(_EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    request["request_id"] = _content_id(
        "mmoptrequest_", request, field="request_id"
    )
    if len(_canonical_bytes(request)) > MAX_REQUEST_BYTES:
        raise OptionsEpisodeContextCaptureError("capture request exceeds its byte bound")
    return request


def build_capture_request(
    *, anchor: Mapping[str, Any], owner_event: Mapping[str, Any], session_date: str
) -> dict[str, Any] | None:
    """Build one exact future-episode request; unsupported tickers return ``None``."""

    return _request_projection(
        anchor=anchor, owner_event=owner_event, session_date=session_date
    )


def validate_capture_request(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "schema",
        "request_id",
        "owner",
        "owner_event",
        "identity_anchor",
        "packet",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OptionsEpisodeContextCaptureError("capture request fields drift")
    clean = copy.deepcopy(dict(value))
    if clean["schema"] != REQUEST_SCHEMA:
        raise OptionsEpisodeContextCaptureError("capture request schema drift")
    request_id = clean.get("request_id")
    if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
        raise OptionsEpisodeContextCaptureError("capture request id is malformed")
    owner = clean.get("owner")
    if not isinstance(owner, Mapping) or set(owner) != {
        "schema",
        "source_event_id",
        "owner_event_sha256",
        "projected_episode_id",
        "projected_episode_sha256",
        "session_date",
        "ticker",
        "event_time",
        "available_at",
    }:
        raise OptionsEpisodeContextCaptureError("capture request owner fields drift")
    if (
        owner.get("schema") != "live_flow.event_stage/v1"
        or owner.get("ticker") != market_memory_identity.CANARY_SYMBOL
        or type(owner.get("projected_episode_id")) is not str
        or _EPISODE_ID.fullmatch(owner["projected_episode_id"]) is None
        or type(owner.get("owner_event_sha256")) is not str
        or _SHA256.fullmatch(owner["owner_event_sha256"]) is None
        or type(owner.get("projected_episode_sha256")) is not str
        or _SHA256.fullmatch(owner["projected_episode_sha256"]) is None
    ):
        raise OptionsEpisodeContextCaptureError("capture request owner identity drift")
    expected = _request_projection(
        anchor=clean["identity_anchor"],
        owner_event=clean["owner_event"],
        session_date=str(owner.get("session_date") or ""),
    )
    if expected is None or clean != expected:
        raise OptionsEpisodeContextCaptureError(
            "capture request differs from its owner event or identity anchor"
        )
    if clean["evidence_policy"] != _EVIDENCE_POLICY:
        raise OptionsEpisodeContextCaptureError("capture request evidence policy drift")
    if clean["authority"] != dict(market_memory.AUTHORITY):
        raise OptionsEpisodeContextCaptureError("capture request authority drift")
    if _content_id("mmoptrequest_", clean, field="request_id") != request_id:
        raise OptionsEpisodeContextCaptureError("capture request id does not bind content")
    return clean


def response_from_stored_capture(
    root: str | Path,
    *,
    request: Mapping[str, Any],
    stored: market_memory_pit.StoredMarketMemoryContext,
    generation: market_memory_pit.PinnedGenerationSnapshot | None = None,
) -> dict[str, Any]:
    """Authenticate a sole-writer result against the active W1A generation."""

    clean = validate_capture_request(request)
    receipt = stored.capture_receipt
    if generation is None:
        generation = market_memory_pit.FileAsKnownAtReader(
            root
        ).read_active_generation()
    if generation.profile != market_memory_pit.STORE_PROFILE:
        raise OptionsEpisodeContextCaptureError(
            "capture response generation belongs to another profile"
        )
    if not any(
        row.query_id == receipt["query_id"]
        and row.capture_id == receipt["capture_id"]
        and row.context_id == receipt["context_id"]
        and row.packet_sha256 == receipt["packet_sha256"]
        for row in generation.captures
    ):
        raise OptionsEpisodeContextCaptureError(
            "captured request is absent from the authenticated W1A generation"
        )
    response = {
        "schema": RESPONSE_SCHEMA,
        "status": "captured",
        "request_id": clean["request_id"],
        "capture_id": receipt["capture_id"],
        "query_id": receipt["query_id"],
        "context_id": receipt["context_id"],
        "packet_sha256": receipt["packet_sha256"],
        "event_time": receipt["clocks"]["event_time"],
        "as_known_at": receipt["clocks"]["as_known_at"],
        "store_id": generation.store_id,
        "generation_id": generation.generation_id,
        "generation_sha256": generation.generation_sha256,
        "generation_capture_count": len(generation.captures),
        "authority": dict(market_memory.AUTHORITY),
    }
    return validate_capture_response(response, request=clean)


def responses_from_stored_batch(
    root: str | Path,
    *,
    captures: list[
        tuple[Mapping[str, Any], market_memory_pit.StoredMarketMemoryContext]
    ],
) -> list[dict[str, Any]]:
    """Project every batch ACK from one final authenticated active HEAD pin."""

    if not captures or len(captures) > MAX_BATCH_REQUESTS:
        raise OptionsEpisodeContextCaptureError(
            "capture response batch count exceeds its bound"
        )
    generation = market_memory_pit.FileAsKnownAtReader(
        root
    ).read_active_generation()
    return [
        response_from_stored_capture(
            root,
            request=request,
            stored=stored,
            generation=generation,
        )
        for request, stored in captures
    ]


def validate_capture_response(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> dict[str, Any]:
    fields = {
        "schema",
        "status",
        "request_id",
        "capture_id",
        "query_id",
        "context_id",
        "packet_sha256",
        "event_time",
        "as_known_at",
        "store_id",
        "generation_id",
        "generation_sha256",
        "generation_capture_count",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OptionsEpisodeContextCaptureError("capture response fields drift")
    response = copy.deepcopy(dict(value))
    clean = validate_capture_request(request)
    packet = clean["packet"]
    packet_sha = sha256(_canonical_bytes(packet)).hexdigest()
    query, _event_dt, _cutoff_dt = market_memory_pit._normalize_query(
        subject=packet["subject"],
        event_time=packet["clocks"]["event_time"],
        as_known_at=packet["clocks"]["as_known_at"],
        mode="operational_pit",
        reject_future_cutoff=False,
    )
    query_id = market_memory_pit._query_id(query)
    if (
        response["schema"] != RESPONSE_SCHEMA
        or response["status"] != "captured"
        or response["request_id"] != clean["request_id"]
        or response["query_id"] != query_id
        or response["context_id"] != packet["context_id"]
        or response["packet_sha256"] != packet_sha
        or response["event_time"] != packet["clocks"]["event_time"]
        or response["as_known_at"] != packet["clocks"]["as_known_at"]
        or response["authority"] != dict(market_memory.AUTHORITY)
    ):
        raise OptionsEpisodeContextCaptureError(
            "capture response does not authenticate the exact request packet"
        )
    for field, prefix in (
        ("capture_id", "mmcapture_"),
        ("query_id", "mmquery_"),
        ("context_id", "mmctx_"),
        ("store_id", "mmstore_"),
        ("generation_id", "mmgeneration_"),
    ):
        item = response.get(field)
        if type(item) is not str or re.fullmatch(prefix + r"[a-f0-9]{64}", item) is None:
            raise OptionsEpisodeContextCaptureError(
                f"capture response {field} is malformed"
            )
    generation_sha = response.get("generation_sha256")
    capture_count = response.get("generation_capture_count")
    if (
        type(generation_sha) is not str
        or _SHA256.fullmatch(generation_sha) is None
        or type(capture_count) is not int
        or not 1 <= capture_count <= MAX_LIFETIME_REQUESTS
    ):
        raise OptionsEpisodeContextCaptureError(
            "capture response generation proof is malformed"
        )
    return response


def validate_transport_receipt(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> dict[str, Any]:
    fields = {
        "schema",
        "request_id",
        "request_sha256",
        "status",
        "completed_at",
        "response",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OptionsEpisodeContextCaptureError("transport receipt fields drift")
    receipt = copy.deepcopy(dict(value))
    clean = validate_capture_request(request)
    status_value = receipt.get("status")
    if status_value not in {
        "captured",
        "abstained_missing_proven_precommit",
        "abstained_unproven_precommit",
        "expired_before_transport",
        "expired_before_owner_availability",
        "pretransport_intent_publication_error",
        "pretransport_spawn_error",
        "outcome_unknown_after_durable_transport_intent",
    }:
        raise OptionsEpisodeContextCaptureError("transport receipt status drift")
    completed_at, _ = _exact_utc(
        receipt.get("completed_at"), field="transport_receipt.completed_at"
    )
    cutoff, _ = _exact_utc(
        clean["owner"]["available_at"], field="request.available_at"
    )
    if completed_at < cutoff - MAX_FUTURE_SKEW:
        raise OptionsEpisodeContextCaptureError(
            "transport receipt completion predates the owner cutoff"
        )
    if (
        receipt.get("schema") != TRANSPORT_RECEIPT_SCHEMA
        or receipt.get("request_id") != clean["request_id"]
        or receipt.get("request_sha256")
        != sha256(_canonical_bytes(clean)).hexdigest()
        or receipt.get("evidence_policy") != _EVIDENCE_POLICY
        or receipt.get("authority") != dict(market_memory.AUTHORITY)
    ):
        raise OptionsEpisodeContextCaptureError(
            "transport receipt does not bind the exact request"
        )
    response = receipt.get("response")
    if status_value == "captured":
        if not isinstance(response, Mapping):
            raise OptionsEpisodeContextCaptureError(
                "captured transport receipt has no response"
            )
        receipt["response"] = validate_capture_response(response, request=clean)
    elif response is not None:
        raise OptionsEpisodeContextCaptureError(
            "non-captured transport receipt cannot carry a response"
        )
    elif (
        status_value.startswith("expired_")
        and completed_at - cutoff <= MAX_SEND_AGE
    ):
        raise OptionsEpisodeContextCaptureError(
            "expired transport receipt is not a proven late abstention"
        )
    return receipt


def owner_availability_binding(request: Mapping[str, Any]) -> dict[str, str]:
    clean = validate_capture_request(request)
    return {
        "request_id": clean["request_id"],
        "request_sha256": sha256(_canonical_bytes(clean)).hexdigest(),
    }


def _owner_availability_receipt(request: Mapping[str, Any]) -> dict[str, Any]:
    clean = validate_capture_request(request)
    return {
        "schema": OWNER_AVAILABILITY_SCHEMA,
        **owner_availability_binding(clean),
        "owner_event_id": clean["owner"]["source_event_id"],
        "available_at": clean["owner"]["available_at"],
        "status": "owner_availability_durable",
        "evidence_policy": copy.deepcopy(_EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }


def validate_owner_availability_receipt(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> dict[str, Any]:
    expected = _owner_availability_receipt(request)
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise OptionsEpisodeContextCaptureError(
            "owner availability receipt does not bind the exact request"
        )
    return copy.deepcopy(expected)


def _batch_intent_projection(
    requests: list[Mapping[str, Any]], *, intended_at: datetime
) -> dict[str, Any]:
    clean = [validate_capture_request(request) for request in requests]
    rows = [owner_availability_binding(request) for request in clean]
    intent: dict[str, Any] = {
        "schema": TRANSPORT_BATCH_INTENT_SCHEMA,
        "batch_id": "mmoptbatch_" + "0" * 64,
        "requests": rows,
        "status": "durable_transport_intent",
        "intended_at": _format_utc(intended_at.astimezone(timezone.utc)),
        "ssh_target": _REMOTE_TARGET,
        "evidence_policy": copy.deepcopy(_EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    intent["batch_id"] = _content_id("mmoptbatch_", intent, field="batch_id")
    return intent


def _validate_transport_batch_intent_shape(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "schema",
        "batch_id",
        "requests",
        "status",
        "intended_at",
        "ssh_target",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OptionsEpisodeContextCaptureError("transport batch intent fields drift")
    intent = copy.deepcopy(dict(value))
    rows = intent.get("requests")
    if (
        not isinstance(rows, list)
        or not rows
        or len(rows) > MAX_BATCH_REQUESTS
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"request_id", "request_sha256"}
            or type(row.get("request_id")) is not str
            or _REQUEST_ID.fullmatch(row["request_id"]) is None
            or type(row.get("request_sha256")) is not str
            or _SHA256.fullmatch(row["request_sha256"]) is None
            for row in rows
        )
        or len({row["request_id"] for row in rows}) != len(rows)
        or intent.get("schema") != TRANSPORT_BATCH_INTENT_SCHEMA
        or intent.get("status") != "durable_transport_intent"
        or intent.get("ssh_target") != _REMOTE_TARGET
        or intent.get("evidence_policy") != _EVIDENCE_POLICY
        or intent.get("authority") != dict(market_memory.AUTHORITY)
        or type(intent.get("batch_id")) is not str
        or _BATCH_ID.fullmatch(intent["batch_id"]) is None
        or _content_id("mmoptbatch_", intent, field="batch_id")
        != intent["batch_id"]
    ):
        raise OptionsEpisodeContextCaptureError(
            "transport batch intent shape or identity drift"
        )
    _exact_utc(
        intent.get("intended_at"), field="transport_batch_intent.intended_at"
    )
    return intent


def validate_transport_batch_intent(
    value: Mapping[str, Any], *, requests: list[Mapping[str, Any]]
) -> dict[str, Any]:
    intent = _validate_transport_batch_intent_shape(value)
    if not requests or len(requests) > MAX_BATCH_REQUESTS:
        raise OptionsEpisodeContextCaptureError("transport batch intent count drift")
    clean = [validate_capture_request(request) for request in requests]
    intended_at, _ = _exact_utc(
        intent.get("intended_at"), field="transport_batch_intent.intended_at"
    )
    for request in clean:
        cutoff, _ = _exact_utc(
            request["owner"]["available_at"], field="request.available_at"
        )
        if not cutoff - MAX_FUTURE_SKEW <= intended_at <= cutoff + MAX_SEND_AGE:
            raise OptionsEpisodeContextCaptureError(
                "transport batch intent falls outside the contemporaneous send window"
            )
    expected = _batch_intent_projection(clean, intended_at=intended_at)
    if (
        intent != expected
    ):
        raise OptionsEpisodeContextCaptureError(
            "transport batch intent does not bind the ordered exact requests"
        )
    return intent


class OptionsContextDispatcher:
    """Private bounded outbox and forced-command transport for the M1 owner."""

    def __init__(
        self,
        root: str | Path,
        *,
        anchor: Mapping[str, Any],
        ssh_target: str,
        ssh_key: str | Path,
    ) -> None:
        if ssh_target != _REMOTE_TARGET:
            raise OptionsEpisodeContextCaptureError(
                "capture transport target is outside the reviewed host"
            )
        key = Path(ssh_key).expanduser()
        if not key.is_absolute():
            raise OptionsEpisodeContextCaptureError(
                "capture transport key path must be absolute"
            )
        self.root = _private_directory(Path(root))
        self.anchors = _private_child(self.root, "anchors")
        self.anchor_proofs = _private_child(self.root, "anchor_proofs")
        self.prepared = _private_child(self.root, "prepared")
        self.prepared_proofs = _private_child(self.root, "prepared_proofs")
        self.pending = _private_child(self.root, "pending")
        self.pending_proofs = _private_child(self.root, "pending_proofs")
        self.owner_available = _private_child(self.root, "owner_available")
        self.intents = _private_child(self.root, "transport_intents")
        self.intent_proofs = _private_child(self.root, "transport_intent_proofs")
        self.receipts = _private_child(self.root, "receipts")
        self.anchor = validate_session_anchor(anchor)
        self.ssh_target = ssh_target
        self.ssh_key = key

    def _lock(self) -> int:
        descriptor = os.open(
            self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor

    @staticmethod
    def _unlock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    def _files(self, directory: Path) -> list[Path]:
        files = sorted(directory.iterdir(), key=lambda item: item.name)
        for path in files:
            if (
                path.is_symlink()
                or not path.is_file()
                or _REQUEST_ID.fullmatch(path.stem) is None
                or path.suffix != ".json"
            ):
                raise OptionsEpisodeContextCaptureError(
                    "capture outbox contains an unowned path"
                )
        return files

    def _intent_files(self) -> list[Path]:
        files = sorted(self.intents.iterdir(), key=lambda item: item.name)
        for path in files:
            if (
                path.is_symlink()
                or not path.is_file()
                or _BATCH_ID.fullmatch(path.stem) is None
                or path.suffix != ".json"
            ):
                raise OptionsEpisodeContextCaptureError(
                    "transport intent store contains an unowned path"
                )
        return files

    @staticmethod
    def _remove_state(path: Path, proof_path: Path | None = None) -> None:
        if proof_path is not None:
            _unlink_durable(proof_path)
        _unlink_durable(path)

    def prepare(
        self, *, owner_event: Mapping[str, Any], session_date: str
    ) -> dict[str, Any] | None:
        """Observe exact missingness at the newly sampled owner cutoff."""

        return build_capture_request(
            anchor=self.anchor,
            owner_event=owner_event,
            session_date=session_date,
        )

    @staticmethod
    def availability_binding(request: Mapping[str, Any]) -> dict[str, str]:
        return owner_availability_binding(request)

    def stage(self, request: Mapping[str, Any] | None) -> str | None:
        """Durably precommit exact bytes before the owner availability fsync.

        A staged request is not transport-eligible.  This closes the crash seam
        between observing the new owner cutoff and fsyncing its availability
        receipt without allowing a replay to manufacture evidence later.
        """

        if request is None:
            return None
        request = validate_capture_request(request)
        body = _canonical_bytes(request)
        descriptor = self._lock()
        try:
            prepared = self._files(self.prepared)
            pending = self._files(self.pending)
            receipts = self._files(self.receipts)
            receipt_path = self.receipts / f"{request['request_id']}.json"
            if receipt_path.exists():
                _fsync_directory(self.receipts)
                validate_transport_receipt(
                    _strict_object(
                        _read_file(
                            receipt_path,
                            maximum=MAX_REQUEST_BYTES,
                            label="capture transport receipt",
                        ),
                        label="capture transport receipt",
                        maximum=MAX_REQUEST_BYTES,
                    ),
                    request=request,
                )
                return request["request_id"]
            pending_path = self.pending / f"{request['request_id']}.json"
            if pending_path.exists():
                existing = _read_file(
                    pending_path,
                    maximum=MAX_REQUEST_BYTES,
                    label="pending capture request",
                )
                if existing != body:
                    raise OptionsEpisodeContextCaptureError(
                        "immutable pending capture request collision"
                    )
                owner_path = self.owner_available / f"{request['request_id']}.json"
                owner = validate_owner_availability_receipt(
                    _strict_object(
                        _read_file(
                            owner_path,
                            maximum=MAX_REQUEST_BYTES,
                            label="owner availability receipt",
                        ),
                        label="owner availability receipt",
                        maximum=MAX_REQUEST_BYTES,
                    ),
                    request=request,
                )
                _write_create_once(
                    owner_path,
                    _canonical_bytes(owner),
                    label="owner availability receipt",
                    recover_existing=True,
                )
                if not _write_proven_create_once(
                    pending_path,
                    body,
                    proof_path=self.pending_proofs / f"{request['request_id']}.json",
                    label="pending capture request",
                    may_reprove_unproven=True,
                ):  # pragma: no cover - owner proof permits recovery
                    raise OptionsEpisodeContextCaptureError(
                        "cannot prove pending capture request"
                )
                return request["request_id"]
            path = self.prepared / f"{request['request_id']}.json"
            proof_path = self.prepared_proofs / f"{request['request_id']}.json"
            owner_path = self.owner_available / f"{request['request_id']}.json"
            if owner_path.exists() or owner_path.is_symlink():
                owner = validate_owner_availability_receipt(
                    _strict_object(
                        _read_file(
                            owner_path,
                            maximum=MAX_REQUEST_BYTES,
                            label="owner availability receipt",
                        ),
                        label="owner availability receipt",
                        maximum=MAX_REQUEST_BYTES,
                    ),
                    request=request,
                )
                _write_create_once(
                    owner_path,
                    _canonical_bytes(owner),
                    label="owner availability receipt",
                    recover_existing=True,
                )
                if not path.exists() or not _has_publication_proof(
                    path,
                    body,
                    proof_path=proof_path,
                    label="prepared capture request",
                ):
                    raise OptionsEpisodeContextCaptureError(
                        "stage cannot repair a precommit after owner availability"
                    )
                return request["request_id"]
            if not path.exists() and len(prepared) + len(pending) >= MAX_PENDING_REQUESTS:
                raise OptionsEpisodeContextCaptureError(
                    "capture outbox reached its uncompleted-request bound"
                )
            if (
                not path.exists()
                and len(prepared) + len(pending) + len(receipts)
                >= MAX_LIFETIME_REQUESTS
            ):
                raise OptionsEpisodeContextCaptureError(
                    "capture outbox reached its pilot lifetime bound"
                )
            if not _write_proven_create_once(
                path,
                body,
                proof_path=proof_path,
                label="prepared capture request",
                may_reprove_unproven=True,
            ):  # pragma: no cover - stage is the pre-availability recovery boundary
                raise OptionsEpisodeContextCaptureError(
                    "cannot prove prepared capture request"
                )
        finally:
            self._unlock(descriptor)
        return request["request_id"]

    def commit(
        self,
        request: Mapping[str, Any] | None,
        *,
        owner_binding: Mapping[str, Any] | None = None,
    ) -> str | None:
        """Promote only exact precommitted bytes after owner availability fsync."""

        if request is None:
            return None
        request = validate_capture_request(request)
        body = _canonical_bytes(request)
        request_id = request["request_id"]
        expected_binding = owner_availability_binding(request)
        if owner_binding is None:
            raise OptionsEpisodeContextCaptureError(
                "commit requires the durable owner availability binding"
            )
        if dict(owner_binding) != expected_binding:
            raise OptionsEpisodeContextCaptureError(
                "owner availability binding differs from the exact request"
            )
        descriptor = self._lock()
        try:
            prepared_path = self.prepared / f"{request_id}.json"
            prepared_proof = self.prepared_proofs / f"{request_id}.json"
            pending_path = self.pending / f"{request_id}.json"
            pending_proof = self.pending_proofs / f"{request_id}.json"
            receipt_path = self.receipts / f"{request_id}.json"
            owner_path = self.owner_available / f"{request_id}.json"
            owner_receipt = _owner_availability_receipt(request)
            if receipt_path.exists():
                _fsync_directory(self.receipts)
                validate_transport_receipt(
                    _strict_object(
                        _read_file(
                            receipt_path,
                            maximum=MAX_REQUEST_BYTES,
                            label="capture transport receipt",
                        ),
                        label="capture transport receipt",
                        maximum=MAX_REQUEST_BYTES,
                    ),
                    request=request,
                )
                if prepared_path.exists():
                    prepared = _read_file(
                        prepared_path,
                        maximum=MAX_REQUEST_BYTES,
                        label="prepared capture request",
                    )
                    if prepared != body:
                        raise OptionsEpisodeContextCaptureError(
                            "prepared capture request differs from its terminal receipt"
                        )
                    self._remove_state(prepared_path, prepared_proof)
                if pending_path.exists():
                    pending = _read_file(
                        pending_path,
                        maximum=MAX_REQUEST_BYTES,
                        label="pending capture request",
                    )
                    if pending != body:
                        raise OptionsEpisodeContextCaptureError(
                            "pending capture request differs from its terminal receipt"
                        )
                    self._remove_state(pending_path, pending_proof)
                return request_id
            _write_create_once(
                owner_path,
                _canonical_bytes(owner_receipt),
                label="owner availability receipt",
                recover_existing=True,
            )
            if pending_path.exists():
                existing = _read_file(
                    pending_path,
                    maximum=MAX_REQUEST_BYTES,
                    label="pending capture request",
                )
                if existing != body:
                    raise OptionsEpisodeContextCaptureError(
                        "immutable pending capture request collision"
                    )
                if not _write_proven_create_once(
                    pending_path,
                    body,
                    proof_path=pending_proof,
                    label="pending capture request",
                    may_reprove_unproven=True,
                ):  # pragma: no cover - durable owner receipt permits re-proof
                    raise OptionsEpisodeContextCaptureError(
                        "cannot prove pending capture request"
                    )
                if prepared_path.exists():
                    self._remove_state(prepared_path, prepared_proof)
                return request_id
            if not prepared_path.exists():
                self._complete(
                    path=prepared_path,
                    proof_path=prepared_proof,
                    request=request,
                    status="abstained_missing_proven_precommit",
                    response=None,
                    completed_at=_utc_now().astimezone(timezone.utc),
                )
                return request_id
            existing = _read_file(
                prepared_path,
                maximum=MAX_REQUEST_BYTES,
                label="prepared capture request",
            )
            if existing != body:
                raise OptionsEpisodeContextCaptureError(
                    "prepared capture request differs from the durable owner cutoff"
                )
            if not _has_publication_proof(
                prepared_path,
                body,
                proof_path=prepared_proof,
                label="prepared capture request",
            ):
                self._complete(
                    path=prepared_path,
                    proof_path=prepared_proof,
                    request=request,
                    status="abstained_unproven_precommit",
                    response=None,
                    completed_at=_utc_now().astimezone(timezone.utc),
                )
                return request_id
            if not _write_proven_create_once(
                pending_path,
                body,
                proof_path=pending_proof,
                label="pending capture request",
                may_reprove_unproven=True,
            ):  # pragma: no cover - durable owner receipt permits re-proof
                raise OptionsEpisodeContextCaptureError(
                    "cannot prove pending capture request"
                )
            self._remove_state(prepared_path, prepared_proof)
        except OSError as exc:
            raise OptionsEpisodeContextCaptureError(
                "cannot commit the prepared capture request"
            ) from exc
        finally:
            self._unlock(descriptor)
        return request_id

    def recover(
        self,
        *,
        owner_event: Mapping[str, Any],
        session_date: str,
        owner_binding: Mapping[str, Any] | None = None,
    ) -> str | None:
        """Promote a prior precommit; absence stays an explicit abstention."""

        expected = build_capture_request(
            anchor=self.anchor,
            owner_event=owner_event,
            session_date=session_date,
        )
        if expected is None:
            return None
        if owner_binding is None:
            # Legacy availability rows never bound a request and therefore can
            # only remain an explicit abstention; replay must not manufacture it.
            return None
        return self.commit(expected, owner_binding=owner_binding)

    def enqueue(self, *, owner_event: Mapping[str, Any], session_date: str) -> str | None:
        """Convenience wrapper for callers that already own a durable cutoff."""

        request = self.prepare(owner_event=owner_event, session_date=session_date)
        self.stage(request)
        return self.commit(
            request,
            owner_binding=(owner_availability_binding(request) if request else None),
        )

    def _transport_key_ready(self) -> None:
        try:
            metadata = self.ssh_key.lstat()
        except OSError as exc:
            raise OptionsEpisodeContextCaptureError(
                "capture transport key is unavailable"
            ) from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or self.ssh_key.is_symlink()
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_uid != os.getuid()
        ):
            raise OptionsEpisodeContextCaptureError(
                "capture transport key must be an owned private regular file"
            )

    def _transport_receipt(
        self,
        *,
        request: Mapping[str, Any],
        status: str,
        response: Mapping[str, Any] | None,
        completed_at: datetime,
    ) -> dict[str, Any]:
        receipt = {
            "schema": TRANSPORT_RECEIPT_SCHEMA,
            "request_id": request["request_id"],
            "request_sha256": sha256(_canonical_bytes(request)).hexdigest(),
            "status": status,
            "completed_at": _format_utc(completed_at.astimezone(timezone.utc)),
            "response": copy.deepcopy(dict(response)) if response is not None else None,
            "evidence_policy": copy.deepcopy(_EVIDENCE_POLICY),
            "authority": dict(market_memory.AUTHORITY),
        }
        return receipt

    def _start_batch_intent(
        self, *, requests: list[Mapping[str, Any]], intended_at: datetime
    ) -> tuple[dict[str, Any], Path, Path]:
        intent = validate_transport_batch_intent(
            _batch_intent_projection(requests, intended_at=intended_at),
            requests=requests,
        )
        path = self.intents / f"{intent['batch_id']}.json"
        proof_path = self.intent_proofs / f"{intent['batch_id']}.json"
        if not _write_proven_create_once(
            path,
            _canonical_bytes(intent),
            proof_path=proof_path,
            label="transport batch intent",
            may_reprove_unproven=False,
        ):
            raise OptionsEpisodeContextCaptureError(
                "transport batch intent is not durably proven"
            )
        return intent, path, proof_path

    def _intent_state_for(
        self, *, request: Mapping[str, Any]
    ) -> tuple[str, Path, Path] | None:
        binding = owner_availability_binding(request)
        matches: list[tuple[str, Path, Path]] = []
        for path in self._intent_files():
            body = _read_file(
                path,
                maximum=MAX_REQUEST_BYTES,
                label="transport batch intent",
            )
            intent = _validate_transport_batch_intent_shape(
                _strict_object(
                    body,
                    label="transport batch intent",
                    maximum=MAX_REQUEST_BYTES,
                )
            )
            if binding not in intent["requests"]:
                continue
            intended_at, _ = _exact_utc(
                intent["intended_at"], field="transport_batch_intent.intended_at"
            )
            cutoff, _ = _exact_utc(
                request["owner"]["available_at"], field="request.available_at"
            )
            if not cutoff - MAX_FUTURE_SKEW <= intended_at <= cutoff + MAX_SEND_AGE:
                raise OptionsEpisodeContextCaptureError(
                    "transport intent/request clock binding drift"
                )
            proof_path = self.intent_proofs / path.name
            proven = _has_publication_proof(
                path,
                body,
                proof_path=proof_path,
                label="transport batch intent",
            )
            matches.append(("proven" if proven else "unproven", path, proof_path))
        if len(matches) > 1:
            raise OptionsEpisodeContextCaptureError(
                "request is bound by multiple transport batch intents"
            )
        return matches[0] if matches else None

    def _reconcile_terminal(
        self,
        *,
        path: Path,
        proof_path: Path | None,
        request: Mapping[str, Any],
    ) -> bool:
        """Finish a crash-interrupted unlink after a terminal receipt fsync."""

        receipt_path = self.receipts / f"{request['request_id']}.json"
        if not receipt_path.exists():
            return False
        # A visible link after a failed receipt-parent fsync is not yet a
        # deletion license.  Re-establish that exact directory durability first.
        _fsync_directory(self.receipts)
        validate_transport_receipt(
            _strict_object(
                _read_file(
                    receipt_path,
                    maximum=MAX_REQUEST_BYTES,
                    label="capture transport receipt",
                ),
                label="capture transport receipt",
                maximum=MAX_REQUEST_BYTES,
            ),
            request=request,
        )
        self._remove_state(path, proof_path)
        return True

    def _complete(
        self,
        *,
        path: Path,
        proof_path: Path | None = None,
        request: Mapping[str, Any],
        status: str,
        response: Mapping[str, Any] | None,
        completed_at: datetime,
    ) -> None:
        receipt = self._transport_receipt(
            request=request,
            status=status,
            response=response,
            completed_at=completed_at,
        )
        receipt = validate_transport_receipt(receipt, request=request)
        receipt_path = self.receipts / f"{request['request_id']}.json"
        if receipt_path.exists():
            _fsync_directory(self.receipts)
            existing = validate_transport_receipt(
                _strict_object(
                    _read_file(
                        receipt_path,
                        maximum=MAX_REQUEST_BYTES,
                        label="capture transport receipt",
                    ),
                    label="capture transport receipt",
                    maximum=MAX_REQUEST_BYTES,
                ),
                request=request,
            )
            if (
                existing["status"] != receipt["status"]
                or existing["response"] != receipt["response"]
            ):
                raise OptionsEpisodeContextCaptureError(
                    "terminal capture receipt conflicts with retry outcome"
                )
        else:
            _write_create_once(
                receipt_path,
                _canonical_bytes(receipt),
                label="capture transport receipt",
                recover_existing=True,
            )
        # Re-sync even after a successful helper return so fault-injection at
        # the first parent sync cannot be laundered by deleting source state.
        _fsync_directory(self.receipts)
        self._remove_state(path, proof_path)

    def flush_pending(self) -> dict[str, int]:
        """Send at most eight fresh requests; expire late work without backfill."""

        descriptor = self._lock()
        try:
            now = _utc_now().astimezone(timezone.utc)
            selected: list[tuple[Path, dict[str, Any]]] = []
            expired = 0
            unknown = 0
            # A precommit is never sent.  A durable owner receipt, however, is a
            # replayable promotion obligation even if the live-flow caller died
            # after its availability ledger fsync and swallowed no exception.
            for path in self._files(self.prepared):
                body = _read_file(
                    path, maximum=MAX_REQUEST_BYTES, label="prepared capture request"
                )
                request = validate_capture_request(
                    _strict_object(
                        body,
                        label="prepared capture request",
                        maximum=MAX_REQUEST_BYTES,
                    )
                )
                proof_path = self.prepared_proofs / path.name
                if self._reconcile_terminal(
                    path=path, proof_path=proof_path, request=request
                ):
                    continue
                owner_path = self.owner_available / path.name
                if owner_path.exists() or owner_path.is_symlink():
                    owner = validate_owner_availability_receipt(
                        _strict_object(
                            _read_file(
                                owner_path,
                                maximum=MAX_REQUEST_BYTES,
                                label="owner availability receipt",
                            ),
                            label="owner availability receipt",
                            maximum=MAX_REQUEST_BYTES,
                        ),
                        request=request,
                    )
                    _write_create_once(
                        owner_path,
                        _canonical_bytes(owner),
                        label="owner availability receipt",
                        recover_existing=True,
                    )
                    if not _has_publication_proof(
                        path,
                        body,
                        proof_path=proof_path,
                        label="prepared capture request",
                    ):
                        self._complete(
                            path=path,
                            proof_path=proof_path,
                            request=request,
                            status="abstained_unproven_precommit",
                            response=None,
                            completed_at=now,
                        )
                        expired += 1
                        continue
                    pending_path = self.pending / path.name
                    pending_proof = self.pending_proofs / path.name
                    if not _write_proven_create_once(
                        pending_path,
                        body,
                        proof_path=pending_proof,
                        label="pending capture request",
                        may_reprove_unproven=True,
                    ):
                        raise OptionsEpisodeContextCaptureError(
                            "cannot recover pending capture publication"
                        )
                    self._remove_state(path, proof_path)
                    continue
                cutoff, _ = _exact_utc(
                    request["owner"]["available_at"], field="request.available_at"
                )
                if now - cutoff > MAX_SEND_AGE:
                    self._complete(
                        path=path,
                        proof_path=proof_path,
                        request=request,
                        status="expired_before_owner_availability",
                        response=None,
                        completed_at=now,
                    )
                    expired += 1
            for path in self._files(self.pending):
                body = _read_file(
                    path, maximum=MAX_REQUEST_BYTES, label="pending capture request"
                )
                request = validate_capture_request(
                    _strict_object(
                        body,
                        label="pending capture request",
                        maximum=MAX_REQUEST_BYTES,
                    )
                )
                proof_path = self.pending_proofs / path.name
                if self._reconcile_terminal(
                    path=path, proof_path=proof_path, request=request
                ):
                    continue
                owner_path = self.owner_available / path.name
                owner = validate_owner_availability_receipt(
                    _strict_object(
                        _read_file(
                            owner_path,
                            maximum=MAX_REQUEST_BYTES,
                            label="owner availability receipt",
                        ),
                        label="owner availability receipt",
                        maximum=MAX_REQUEST_BYTES,
                    ),
                    request=request,
                )
                _write_create_once(
                    owner_path,
                    _canonical_bytes(owner),
                    label="owner availability receipt",
                    recover_existing=True,
                )
                if not _write_proven_create_once(
                    path,
                    body,
                    proof_path=proof_path,
                    label="pending capture request",
                    may_reprove_unproven=True,
                ):
                    raise OptionsEpisodeContextCaptureError(
                        "cannot prove pending capture request"
                    )
                prior_intent = self._intent_state_for(request=request)
                if prior_intent is not None:
                    intent_state, intent_path, intent_proof = prior_intent
                    status = (
                        "outcome_unknown_after_durable_transport_intent"
                        if intent_state == "proven"
                        else "pretransport_intent_publication_error"
                    )
                    self._complete(
                        path=path,
                        proof_path=proof_path,
                        request=request,
                        status=status,
                        response=None,
                        completed_at=now,
                    )
                    if intent_state == "proven":
                        unknown += 1
                    else:
                        expired += 1
                        self._remove_state(intent_path, intent_proof)
                    continue
                cutoff, _ = _exact_utc(
                    request["owner"]["available_at"], field="request.available_at"
                )
                if now - cutoff > MAX_SEND_AGE:
                    self._complete(
                        path=path,
                        proof_path=proof_path,
                        request=request,
                        status="expired_before_transport",
                        response=None,
                        completed_at=now,
                    )
                    expired += 1
                    continue
                if cutoff > now + MAX_FUTURE_SKEW:
                    continue
                selected.append((path, request))
                if len(selected) >= MAX_BATCH_REQUESTS:
                    break
            if not selected:
                return {
                    "captured": 0,
                    "expired": expired,
                    "unknown": unknown,
                    "pending": len(self._files(self.pending)),
                }
            self._transport_key_ready()
            batch = b"".join(_canonical_bytes(request) + b"\n" for _path, request in selected)
            if len(batch) > MAX_BATCH_BYTES:
                raise OptionsEpisodeContextCaptureError(
                    "capture transport batch exceeds its byte bound"
                )
            command = [
                "/usr/bin/ssh",
                "-T",
                "-i",
                str(self.ssh_key),
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ClearAllForwardings=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "ConnectionAttempts=1",
                self.ssh_target,
            ]
            attempted_at = _utc_now().astimezone(timezone.utc)
            requests = [request for _path, request in selected]
            intent = _batch_intent_projection(requests, intended_at=attempted_at)
            intent_path = self.intents / f"{intent['batch_id']}.json"
            intent_proof = self.intent_proofs / intent_path.name
            try:
                self._start_batch_intent(
                    requests=requests, intended_at=attempted_at
                )
            except OptionsEpisodeContextCaptureError:
                completed = _utc_now().astimezone(timezone.utc)
                for path, request in selected:
                    self._complete(
                        path=path,
                        proof_path=self.pending_proofs / path.name,
                        request=request,
                        status="pretransport_intent_publication_error",
                        response=None,
                        completed_at=completed,
                    )
                self._remove_state(intent_path, intent_proof)
                return {
                    "captured": 0,
                    "expired": expired + len(selected),
                    "unknown": unknown,
                    "pending": len(self._files(self.pending)),
                }
            try:
                result = subprocess.run(
                    command,
                    input=batch,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
            except OSError:
                completed = _utc_now().astimezone(timezone.utc)
                for path, request in selected:
                    self._complete(
                        path=path,
                        proof_path=self.pending_proofs / path.name,
                        request=request,
                        status="pretransport_spawn_error",
                        response=None,
                        completed_at=completed,
                    )
                return {
                    "captured": 0,
                    "expired": expired + len(selected),
                    "unknown": unknown,
                    "pending": len(self._files(self.pending)),
                }
            except subprocess.SubprocessError:
                completed = _utc_now().astimezone(timezone.utc)
                for path, request in selected:
                    self._complete(
                        path=path,
                        proof_path=self.pending_proofs / path.name,
                        request=request,
                        status="outcome_unknown_after_durable_transport_intent",
                        response=None,
                        completed_at=completed,
                    )
                return {
                    "captured": 0,
                    "expired": expired,
                    "unknown": unknown + len(selected),
                    "pending": len(self._files(self.pending)),
                }
            requests_by_id = {
                request["request_id"]: (path, request) for path, request in selected
            }
            responses: dict[str, dict[str, Any]] = {}
            response_invalid = (
                len(result.stdout) > 64 * 1024 or len(result.stderr) > 64 * 1024
            )
            if not response_invalid:
                try:
                    for line in result.stdout.splitlines():
                        response = _strict_object(
                            line,
                            label="capture transport response",
                            maximum=16 * 1024,
                        )
                        request_id = response.get("request_id")
                        if (
                            request_id not in requests_by_id
                            or request_id in responses
                        ):
                            raise OptionsEpisodeContextCaptureError(
                                "capture transport returned an unrequested response"
                            )
                        responses[request_id] = validate_capture_response(
                            response, request=requests_by_id[request_id][1]
                        )
                except OptionsEpisodeContextCaptureError:
                    response_invalid = True
            completed = _utc_now().astimezone(timezone.utc)
            for request_id, response in responses.items():
                path, request = requests_by_id[request_id]
                self._complete(
                    path=path,
                    proof_path=self.pending_proofs / path.name,
                    request=request,
                    status="captured",
                    response=response,
                    completed_at=completed,
                )
            unresolved = [
                (path, request)
                for path, request in selected
                if request["request_id"] not in responses
            ]
            if response_invalid or result.returncode != 0 or unresolved:
                for path, request in unresolved:
                    self._complete(
                        path=path,
                        proof_path=self.pending_proofs / path.name,
                        request=request,
                        status="outcome_unknown_after_durable_transport_intent",
                        response=None,
                        completed_at=completed,
                    )
                unknown += len(unresolved)
            return {
                "captured": len(responses),
                "expired": expired,
                "unknown": unknown,
                "pending": len(self._files(self.pending)),
            }
        finally:
            self._unlock(descriptor)

    def drain_pending(self) -> dict[str, int]:
        """Drain the bounded outbox without depending on the next live cycle."""

        totals = {"captured": 0, "expired": 0, "unknown": 0, "pending": 0}
        for _batch in range(MAX_DRAIN_BATCHES):
            result = self.flush_pending()
            for field in ("captured", "expired", "unknown"):
                totals[field] += result[field]
            totals["pending"] = result["pending"]
            progress = sum(result[field] for field in ("captured", "expired", "unknown"))
            if totals["pending"] == 0 or progress == 0:
                break
        return totals


def initialize_dispatcher(
    root: str | Path,
    *,
    session_date: str,
    config_path: str | Path,
    ssh_target: str,
    ssh_key: str | Path,
) -> OptionsContextDispatcher:
    anchor = create_or_load_session_anchor(
        root, session_date=session_date, config_path=config_path
    )
    return OptionsContextDispatcher(
        root, anchor=anchor, ssh_target=ssh_target, ssh_key=ssh_key
    )


__all__ = [
    "ANCHOR_SCHEMA",
    "MAX_BATCH_BYTES",
    "MAX_BATCH_REQUESTS",
    "MAX_DRAIN_BATCHES",
    "MAX_REQUEST_BYTES",
    "OWNER_AVAILABILITY_SCHEMA",
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
    "TRANSPORT_BATCH_INTENT_SCHEMA",
    "TRANSPORT_RECEIPT_SCHEMA",
    "OptionsContextDispatcher",
    "OptionsEpisodeContextCaptureError",
    "build_capture_request",
    "create_or_load_session_anchor",
    "initialize_dispatcher",
    "owner_availability_binding",
    "response_from_stored_capture",
    "responses_from_stored_batch",
    "validate_capture_request",
    "validate_capture_response",
    "validate_owner_availability_receipt",
    "validate_session_anchor",
    "validate_transport_batch_intent",
    "validate_transport_receipt",
]
