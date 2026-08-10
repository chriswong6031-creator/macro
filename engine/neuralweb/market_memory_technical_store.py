"""Private append-only storage for the W1B.3B SPY technical actual output.

This module deliberately does not publish an as-known-at packet or add a
trusted feature.  It owns a separate ``technicals-v1`` state tree whose only
payload is the current credential-free public-R2 SPY raw-close ratio, captured
exactly as observed.  The stable network transaction, pinned license/config/
calendar evidence, clock-free source object, and derived feature object are
content-addressed.  A cumulative immutable generation is published before
``HEAD.json`` advances.

The first availability clock belongs to this writer.  It is sampled only after
the detached projection bundle has been fully revalidated and is immediately
sealed in a create-once prepared record.  A crash retry therefore reuses the
same clock and content identities instead of manufacturing a later vintage.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from engine.neuralweb import (
    market_memory_pit,
)
from engine.neuralweb import (
    market_memory_technical_observation as technical,
)

STORE_PROFILE = "market_memory.private.spy_raw_technical_actual_output.v1"
STORE_SCHEMA = "market_memory.technicals_actual_output_store.v1"
PREPARED_SCHEMA = "market_memory.technicals_actual_output_prepared.v1"
CAPTURE_RECEIPT_SCHEMA = "market_memory.technicals_actual_output_capture_receipt.v1"
GENERATION_SCHEMA = "market_memory.actual_output_store_generation.v1"
HEAD_SCHEMA = "market_memory.actual_output_store_head.v1"
_SOURCE_OBSERVATION_SCHEMA_V1 = technical.SOURCE_OBSERVATION_SCHEMA
_FEATURE_OBJECT_SCHEMA_V1 = technical.SNAPSHOT_SCHEMA

_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_PREPARED_BYTES = 128 * 1024
_MAX_RECEIPT_BYTES = 128 * 1024
_MAX_SOURCE_OBJECT_BYTES = 128 * 1024
_MAX_FEATURE_OBJECT_BYTES = 128 * 1024
_MAX_GENERATION_BYTES = 4 * 1024 * 1024
_MAX_GENERATION_CAPTURES = 4_096
_MAX_HEAD_BYTES = 16 * 1024
_SOURCE_LIMITS = {
    "publish_manifest": 512 * 1024,
    "spy_daily_parquet": 8 * 1024 * 1024,
    "canary_identity_config": 32 * 1024,
    "xnys_calendar_module": 256 * 1024,
    "massive_entitlement_record": 64 * 1024,
    "technical_price_basis_contract": 32 * 1024,
}
_SOURCE_ROLES = tuple(_SOURCE_LIMITS)
_REMOTE_SOURCE_ROLES = ("publish_manifest", "spy_daily_parquet")
_GIT_SOURCE_ROLES = (
    "canary_identity_config",
    "xnys_calendar_module",
    "massive_entitlement_record",
    "technical_price_basis_contract",
)
_GIT_SOURCE_SHA256 = {
    "canary_identity_config": (
        "5e7823e48866b2c0828122b65f684ed5872c6816a6224f61e44db4c03d129b33"
    ),
    "xnys_calendar_module": (
        "7c9167fd416babb64c3067ae7e6237615011ad79e26d826e57005486496410ce"
    ),
    "massive_entitlement_record": (
        "82ad971b46d4159739117d3defe19a25a2a24ede45e5e8d28494c5849e757891"
    ),
    "technical_price_basis_contract": (
        "ce0244d9c18e3fdcb621c7ced6e3700cb8cb43ff0952b355b82d0542ed6b1be9"
    ),
}
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_STORE_ID = re.compile(r"mmactualstore_[a-f0-9]{64}\Z")
_PREPARED_ID = re.compile(r"mmprepared_[a-f0-9]{64}\Z")
_CAPTURE_ID = re.compile(r"mmactualcapture_[a-f0-9]{64}\Z")
_REVISION_ID = re.compile(r"mmtechrev_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmactualgeneration_[a-f0-9]{64}\Z")
_SOURCE_ID = re.compile(r"mmtechsrc_[a-f0-9]{64}\Z")
_SNAPSHOT_ID = re.compile(r"mmtechsnap_[a-f0-9]{64}\Z")
_SESSION = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_FRESHNESS_POLICY = "r2_manifest_26h_prior_xnys_0200z_finality_max_one_lag.v1"
_AUTHORITY_V1: Mapping[str, Any] = MappingProxyType(
    {
        "tier": "display",
        "horizon_role": "context",
        "context_only": True,
        "proposal_weight": 0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_escalate": False,
        "may_trade": False,
        "may_originate": False,
        "may_select_options_candidate": False,
        "may_execute": False,
        "may_write_options_episode": False,
        "may_append_outcome": False,
        "may_train_prophet": False,
    }
)
_EVIDENCE_POLICY_V1: Mapping[str, Any] = MappingProxyType(
    {
        "actual_output_only": True,
        "current_tip_only": True,
        "contract_validated": True,
        "exact_source_bodies_authenticated": True,
        "stable_network_transaction": True,
        "license_entitlement_record_bound": True,
        "provider_price_basis_contract_bound": True,
        "basis_authenticated_by_shape": False,
        "raw_unadjusted_close_ratio": True,
        "economic_return": False,
        "point_in_time_corporate_actions": False,
        "context_only": True,
        "training_eligible": False,
        "promotion_eligible": False,
    }
)


class MarketMemoryTechnicalStoreError(market_memory_pit.MarketMemoryStoreError):
    """The private actual-output store is unavailable or corrupted."""


class MarketMemoryTechnicalCaptureError(MarketMemoryTechnicalStoreError):
    """A candidate actual output cannot enter the private store."""


@dataclass(frozen=True)
class StoredTechnicalActualOutput:
    """One capture reloaded and reprojected from its exact stored source CAS."""

    generation_id: str
    capture_receipt: dict[str, Any]
    bundle: technical.TechnicalSnapshotBundle


@dataclass(frozen=True)
class _StoreState:
    manifest: dict[str, Any]
    head: dict[str, Any]
    generation: dict[str, Any]


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
        raise MarketMemoryTechnicalStoreError(
            "actual-output value is not finite canonical JSON"
        ) from exc


def _digest(body: bytes) -> str:
    return sha256(body).hexdigest()


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + _digest(_canonical_bytes(core))


def _exact_utc(value: object, *, field: str) -> str:
    if type(value) is not str or not _RFC3339_UTC.fullmatch(value):
        raise MarketMemoryTechnicalStoreError(
            f"actual-output {field} is not exact RFC3339 UTC"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryTechnicalStoreError(
            f"actual-output {field} is not a real timestamp"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        raise MarketMemoryTechnicalStoreError(f"actual-output {field} must be UTC")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sample_first_observed_at() -> str:
    sampled = _utc_now()
    if not isinstance(sampled, datetime) or sampled.tzinfo is None:
        raise MarketMemoryTechnicalCaptureError(
            "actual-output writer clock must be timezone-aware"
        )
    return _exact_utc(
        sampled.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        field="first_observed_at",
    )


def _is_frozen_session(value: date) -> bool:
    try:
        return technical.is_frozen_v1_xnys_session(value)
    except technical.MarketMemoryTechnicalObservationError as exc:
        raise MarketMemoryTechnicalCaptureError(
            "technical freshness date is outside the frozen XNYS calendar"
        ) from exc


def _previous_frozen_session(value: date) -> date:
    candidate = value - timedelta(days=1)
    for _ in range(31):
        if _is_frozen_session(candidate):
            return candidate
        candidate -= timedelta(days=1)
    raise MarketMemoryTechnicalCaptureError(
        "technical freshness cannot resolve a prior frozen XNYS session"
    )


def _freshness_receipt(
    *,
    session: str,
    manifest_last_modified: str,
    first_observed_at: str,
) -> dict[str, Any]:
    """Admit a fresh manifest and at most one completed-session source lag.

    The observed UTC date is never admitted as completed: Massive daily
    aggregates may include eligible extended-hours trades and a momentarily
    stable object is not proof that a same-day bar is final.  A prior session
    becomes eligible only at 02:00 UTC on the following calendar day, which is
    after the documented 20:00 ET extended-hours end in both EST and EDT.  The
    source manifest must also be no newer than the writer clock and no older
    than 26 hours.  Calendar semantics come only from the exact reviewed
    frozen-v1 evaluator whose module bytes are in this capture's private CAS.
    """

    observed_at = _exact_utc(first_observed_at, field="freshness first_observed_at")
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    try:
        manifest_modified = parsedate_to_datetime(manifest_last_modified)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketMemoryTechnicalCaptureError(
            "technical manifest Last-Modified is malformed"
        ) from exc
    if (
        type(manifest_last_modified) is not str
        or manifest_modified.tzinfo is None
        or manifest_modified.utcoffset() != timedelta(0)
        or format_datetime(manifest_modified.astimezone(timezone.utc), usegmt=True)
        != manifest_last_modified
    ):
        raise MarketMemoryTechnicalCaptureError(
            "technical manifest Last-Modified is not canonical IMF-fixdate"
        )
    manifest_modified = manifest_modified.astimezone(timezone.utc)
    manifest_age = observed - manifest_modified
    if manifest_age < timedelta(0):
        raise MarketMemoryTechnicalCaptureError(
            "technical manifest Last-Modified is newer than the store clock"
        )
    if manifest_age > timedelta(hours=26):
        raise MarketMemoryTechnicalCaptureError(
            "technical manifest Last-Modified exceeds the 26-hour freshness bound"
        )

    observed_date = observed.date()
    try:
        actual_session = date.fromisoformat(session)
    except (TypeError, ValueError) as exc:
        raise MarketMemoryTechnicalCaptureError(
            "technical session is not a real calendar date"
        ) from exc
    if session != actual_session.isoformat() or not _is_frozen_session(actual_session):
        raise MarketMemoryTechnicalCaptureError(
            "technical session is not an XNYS session"
        )

    latest_completed = _previous_frozen_session(observed_date)
    latest_completed_not_before = datetime.combine(
        latest_completed + timedelta(days=1),
        time(hour=2),
        tzinfo=timezone.utc,
    )
    if observed < latest_completed_not_before:
        latest_completed = _previous_frozen_session(latest_completed)
        latest_completed_not_before = datetime.combine(
            latest_completed + timedelta(days=1),
            time(hour=2),
            tzinfo=timezone.utc,
        )
    latest_completed_via = "prior_session_after_0200z_finality_buffer"
    previous_completed = _previous_frozen_session(latest_completed)
    if actual_session == latest_completed:
        session_lag = 0
        accepted_via = "latest_completed_session"
    elif actual_session == previous_completed:
        session_lag = 1
        accepted_via = "one_completed_session_lag"
    else:
        raise MarketMemoryTechnicalCaptureError(
            "technical session exceeds the one-completed-session freshness bound"
        )
    return {
        "policy": _FRESHNESS_POLICY,
        "observed_utc_date": observed_date.isoformat(),
        "manifest_last_modified": manifest_last_modified,
        "manifest_age_seconds": int(manifest_age.total_seconds()),
        "manifest_max_age_seconds": 26 * 60 * 60,
        "latest_completed_session": latest_completed.isoformat(),
        "previous_completed_session": previous_completed.isoformat(),
        "latest_completed_via": latest_completed_via,
        "latest_completed_not_before": latest_completed_not_before.isoformat().replace(
            "+00:00", "Z"
        ),
        "accepted_session": session,
        "session_lag": session_lag,
        "accepted_via": accepted_via,
    }


def _require_digest(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise MarketMemoryTechnicalStoreError(
            f"actual-output {field} is not lowercase SHA-256"
        )
    return value


def _require_int(value: object, *, field: str, minimum: int = 1, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MarketMemoryTechnicalStoreError(
            f"actual-output {field} is outside its integer bound"
        )
    return value


def validate_technical_actual_output_store_root(
    root: str | Path, *, repository_root: str | Path | None = None
) -> Path:
    """Require the dedicated private ``technicals-v1`` root and reject public roots."""

    unresolved = Path(root).expanduser()
    absolute_unresolved = Path(os.path.abspath(os.fspath(unresolved)))
    cursor = absolute_unresolved
    while True:
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise MarketMemoryTechnicalStoreError(
                "actual-output store path components cannot be inspected"
            ) from exc
        else:
            if stat.S_ISLNK(metadata.st_mode):
                raise MarketMemoryTechnicalStoreError(
                    "actual-output store root and parents cannot be symlinks"
                )
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    try:
        candidate = market_memory_pit.validate_store_root(
            absolute_unresolved, repository_root=repository_root
        )
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryTechnicalStoreError(str(exc)) from exc
    if repository_root is not None:
        repository = Path(repository_root).expanduser().resolve()
        if candidate == repository or repository in candidate.parents:
            raise MarketMemoryTechnicalStoreError(
                "actual-output store cannot use the repository or its descendants"
            )
    canonical_base = Path("/var/lib/macro-market-memory").resolve(strict=False)
    if candidate == canonical_base or canonical_base in candidate.parents:
        canonical_profile = canonical_base / "state" / "technicals-v1"
        if candidate != canonical_profile:
            raise MarketMemoryTechnicalStoreError(
                "canonical Market Memory storage permits only state/technicals-v1"
            )
    if candidate.name != "technicals-v1":
        raise MarketMemoryTechnicalStoreError(
            "actual-output store root must be the dedicated technicals-v1 directory"
        )
    if "public" in candidate.parts or any(
        part in {"trusted-v1", "w1a-v1"} for part in candidate.parts
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output store cannot use a public or trusted serving tree"
        )
    if candidate.exists():
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise MarketMemoryTechnicalStoreError(
                "actual-output store root cannot be inspected"
            ) from exc
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise MarketMemoryTechnicalStoreError(
                "actual-output store root must be a real directory"
            )
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise MarketMemoryTechnicalStoreError(
                "actual-output store root must not grant group or world access"
            )
    return candidate


def default_technical_actual_output_store_root(repository_root: str | Path) -> Path:
    """Return the profile-owned production root (or isolated local analogue)."""

    repository = Path(repository_root).expanduser().resolve()
    override = os.environ.get("MARKET_MEMORY_TECHNICAL_STORE_DIR", "").strip()
    if override:
        candidate = Path(override).expanduser()
    elif repository == Path("/opt/macro"):
        candidate = Path("/var/lib/macro-market-memory/state/technicals-v1")
    else:
        candidate = (
            Path.home()
            / ".local"
            / "state"
            / "macro-market-memory"
            / _digest(os.fsencode(repository))[:16]
            / "technicals-v1"
        )
    return validate_technical_actual_output_store_root(
        candidate, repository_root=repository
    )


def _safe_path(root: Path, *parts: str) -> Path:
    try:
        return market_memory_pit._safe_store_path(root, *parts)
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryTechnicalStoreError(str(exc)) from exc


def _manifest_path(root: Path) -> Path:
    return _safe_path(root, "store_manifest.json")


def _head_path(root: Path) -> Path:
    return _safe_path(root, "HEAD.json")


def _prepared_path(root: Path, prepared_id: str) -> Path:
    if type(prepared_id) is not str or not _PREPARED_ID.fullmatch(prepared_id):
        raise MarketMemoryTechnicalStoreError("prepared_id is malformed")
    digest = prepared_id.removeprefix("mmprepared_")
    return _safe_path(root, "prepared", digest[:2], f"{prepared_id}.json")


def _source_body_path(root: Path, digest: str) -> Path:
    _require_digest(digest, field="source body digest")
    return _safe_path(root, "source_bodies", digest[:2], f"{digest}.bin")


def _source_object_path(root: Path, source_observation_id: str) -> Path:
    if type(source_observation_id) is not str or not _SOURCE_ID.fullmatch(
        source_observation_id
    ):
        raise MarketMemoryTechnicalStoreError("source_observation_id is malformed")
    digest = source_observation_id.removeprefix("mmtechsrc_")
    return _safe_path(
        root,
        "source_observations",
        digest[:2],
        f"{source_observation_id}.json",
    )


def _feature_object_path(root: Path, snapshot_id: str) -> Path:
    if type(snapshot_id) is not str or not _SNAPSHOT_ID.fullmatch(snapshot_id):
        raise MarketMemoryTechnicalStoreError("snapshot_id is malformed")
    digest = snapshot_id.removeprefix("mmtechsnap_")
    return _safe_path(root, "feature_objects", digest[:2], f"{snapshot_id}.json")


def _capture_path(root: Path, capture_id: str) -> Path:
    if type(capture_id) is not str or not _CAPTURE_ID.fullmatch(capture_id):
        raise MarketMemoryTechnicalStoreError("capture_id is malformed")
    digest = capture_id.removeprefix("mmactualcapture_")
    return _safe_path(root, "capture_receipts", digest[:2], f"{capture_id}.json")


def _generation_path(root: Path, generation_id: str) -> Path:
    if type(generation_id) is not str or not _GENERATION_ID.fullmatch(generation_id):
        raise MarketMemoryTechnicalStoreError("generation_id is malformed")
    digest = generation_id.removeprefix("mmactualgeneration_")
    return _safe_path(root, "generations", digest[:2], f"{generation_id}.json")


def _object_key(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:  # pragma: no cover - paths are built above
        raise MarketMemoryTechnicalStoreError(
            "actual-output object key escaped its store"
        ) from exc


def _mkdir(path: Path) -> None:
    try:
        market_memory_pit._mkdir_durable(path)
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryTechnicalStoreError(str(exc)) from exc


def _write_json_create_once(
    root: Path, path: Path, body: bytes, *, label: str, limit: int
) -> bool:
    if type(body) is not bytes or not body or len(body) > limit:
        raise MarketMemoryTechnicalCaptureError(
            f"{label} is empty or exceeds its byte bound"
        )
    try:
        written = market_memory_pit._write_create_once(root, path, body, label=label)
    except market_memory_pit.MarketMemoryCaptureError as exc:
        raise MarketMemoryTechnicalCaptureError(str(exc)) from exc
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryTechnicalStoreError(str(exc)) from exc
    return written


def _read_json(path: Path, *, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        return market_memory_pit._read_canonical_object(path, limit=limit, label=label)
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryTechnicalStoreError(str(exc)) from exc


def _read_raw(
    path: Path, *, digest: str, expected_bytes: int, limit: int, label: str
) -> bytes:
    _require_digest(digest, field=f"{label} digest")
    _require_int(
        expected_bytes,
        field=f"{label} bytes",
        maximum=limit,
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryTechnicalStoreError(
            f"{label} cannot be opened safely"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MarketMemoryTechnicalStoreError(f"{label} is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > limit:
            raise MarketMemoryTechnicalStoreError(
                f"{label} exceeds its safe size bound"
            )
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise MarketMemoryTechnicalStoreError(f"{label} cannot be read") from exc
    finally:
        os.close(descriptor)
    body = b"".join(chunks)
    if (
        metadata.st_dev != after.st_dev
        or metadata.st_ino != after.st_ino
        or metadata.st_size != after.st_size
        or metadata.st_mtime_ns != after.st_mtime_ns
        or len(body) != metadata.st_size
        or len(body) != expected_bytes
        or len(body) > limit
        or _digest(body) != digest
    ):
        raise MarketMemoryTechnicalStoreError(
            f"{label} changed or differs from its receipt"
        )
    return body


def _write_raw_create_once(
    root: Path,
    path: Path,
    body: bytes,
    *,
    digest: str,
    label: str,
    limit: int,
) -> bool:
    if (
        type(body) is not bytes
        or not body
        or len(body) > limit
        or _digest(body) != digest
    ):
        raise MarketMemoryTechnicalCaptureError(
            f"{label} is empty, oversized, or does not match its digest"
        )
    try:
        path.parent.relative_to(root)
    except ValueError as exc:
        raise MarketMemoryTechnicalStoreError(
            "raw immutable write escaped the actual-output root"
        ) from exc
    _mkdir(path.parent)
    if path.exists() or path.is_symlink():
        existing = _read_raw(
            path,
            digest=digest,
            expected_bytes=len(body),
            limit=limit,
            label=f"existing {label}",
        )
        if existing != body:  # digest collision defence
            raise MarketMemoryTechnicalCaptureError(f"immutable {label} collision")
        return False
    temporary = path.parent / f".{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
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
            market_memory_pit._directory_fsync(path.parent)
            return True
        except FileExistsError:
            existing = _read_raw(
                path,
                digest=digest,
                expected_bytes=len(body),
                limit=limit,
                label=f"raced {label}",
            )
            if existing != body:
                raise MarketMemoryTechnicalCaptureError(
                    f"immutable {label} collision"
                ) from None
            return False
    except (MarketMemoryTechnicalStoreError, MarketMemoryTechnicalCaptureError):
        raise
    except OSError as exc:
        raise MarketMemoryTechnicalStoreError(
            f"cannot publish immutable {label}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _replace_head(root: Path, head: Mapping[str, Any]) -> None:
    body = _canonical_bytes(head)
    if len(body) > _MAX_HEAD_BYTES:
        raise MarketMemoryTechnicalStoreError(
            "actual-output HEAD exceeds its safe size bound"
        )
    path = _head_path(root)
    if path.is_symlink():
        raise MarketMemoryTechnicalStoreError("actual-output HEAD cannot be a symlink")
    temporary = root / f".HEAD.json.tmp.{os.getpid()}.{uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, path)
        market_memory_pit._directory_fsync(root)
    except OSError as exc:
        raise MarketMemoryTechnicalStoreError(
            "cannot advance actual-output HEAD"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _new_manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": STORE_SCHEMA,
        "store_id": "",
        "nonce": uuid4().hex,
        "profile": STORE_PROFILE,
        "prepared_schema": PREPARED_SCHEMA,
        "capture_receipt_schema": CAPTURE_RECEIPT_SCHEMA,
        "source_observation_schema": _SOURCE_OBSERVATION_SCHEMA_V1,
        "feature_object_schema": _FEATURE_OBJECT_SCHEMA_V1,
        "generation_schema": GENERATION_SCHEMA,
        "head_schema": HEAD_SCHEMA,
        "mode": "private_actual_output_current_tip",
        "evidence_policy": dict(_EVIDENCE_POLICY_V1),
        "authority": dict(_AUTHORITY_V1),
    }
    manifest["store_id"] = _content_id("mmactualstore_", manifest, field="store_id")
    return manifest


def _validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "schema",
        "store_id",
        "nonce",
        "profile",
        "prepared_schema",
        "capture_receipt_schema",
        "source_observation_schema",
        "feature_object_schema",
        "generation_schema",
        "head_schema",
        "mode",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryTechnicalStoreError(
            "actual-output store manifest fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    expected = {
        "schema": STORE_SCHEMA,
        "profile": STORE_PROFILE,
        "prepared_schema": PREPARED_SCHEMA,
        "capture_receipt_schema": CAPTURE_RECEIPT_SCHEMA,
        "source_observation_schema": _SOURCE_OBSERVATION_SCHEMA_V1,
        "feature_object_schema": _FEATURE_OBJECT_SCHEMA_V1,
        "generation_schema": GENERATION_SCHEMA,
        "head_schema": HEAD_SCHEMA,
        "mode": "private_actual_output_current_tip",
        "evidence_policy": dict(_EVIDENCE_POLICY_V1),
        "authority": dict(_AUTHORITY_V1),
    }
    for field, wanted in expected.items():
        if clean.get(field) != wanted:
            raise MarketMemoryTechnicalStoreError(f"actual-output store {field} drift")
    if type(clean.get("nonce")) is not str or not re.fullmatch(
        r"[a-f0-9]{32}", clean["nonce"]
    ):
        raise MarketMemoryTechnicalStoreError("actual-output store nonce is malformed")
    store_id = clean.get("store_id")
    if type(store_id) is not str or not _STORE_ID.fullmatch(store_id):
        raise MarketMemoryTechnicalStoreError("actual-output store_id is malformed")
    if _content_id("mmactualstore_", clean, field="store_id") != store_id:
        raise MarketMemoryTechnicalStoreError(
            "actual-output store_id does not bind its manifest"
        )
    return clean


def _new_generation(
    *,
    store_id: str,
    previous_generation_id: str | None,
    captures: list[Mapping[str, Any]],
) -> dict[str, Any]:
    generation: dict[str, Any] = {
        "schema": GENERATION_SCHEMA,
        "generation_id": "",
        "store_id": store_id,
        "previous_generation_id": previous_generation_id,
        "captures": sorted(
            (copy.deepcopy(dict(row)) for row in captures),
            key=lambda row: (
                row["session"],
                row["first_observed_at"],
                row["capture_id"],
            ),
        ),
    }
    generation["generation_id"] = _content_id(
        "mmactualgeneration_", generation, field="generation_id"
    )
    return generation


def _validate_generation(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    fields = {
        "schema",
        "generation_id",
        "store_id",
        "previous_generation_id",
        "captures",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryTechnicalStoreError(
            "actual-output generation fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != GENERATION_SCHEMA or clean.get("store_id") != store_id:
        raise MarketMemoryTechnicalStoreError(
            "actual-output generation schema or store mismatch"
        )
    generation_id = clean.get("generation_id")
    if type(generation_id) is not str or not _GENERATION_ID.fullmatch(generation_id):
        raise MarketMemoryTechnicalStoreError(
            "actual-output generation_id is malformed"
        )
    previous = clean.get("previous_generation_id")
    if previous is not None and (
        type(previous) is not str or not _GENERATION_ID.fullmatch(previous)
    ):
        raise MarketMemoryTechnicalStoreError(
            "previous actual-output generation_id is malformed"
        )
    captures = clean.get("captures")
    if not isinstance(captures, list) or len(captures) > _MAX_GENERATION_CAPTURES:
        raise MarketMemoryTechnicalStoreError(
            "actual-output generation exceeds its capture bound"
        )
    entry_fields = {
        "capture_id",
        "session",
        "revision_id",
        "source_observation_id",
        "snapshot_id",
        "first_observed_at",
        "receipt_sha256",
    }
    sort_keys: list[tuple[str, str, str]] = []
    capture_ids: list[str] = []
    revisions: list[str] = []
    for entry in captures:
        if not isinstance(entry, Mapping) or set(entry) != entry_fields:
            raise MarketMemoryTechnicalStoreError(
                "actual-output generation entry is not canonical"
            )
        if type(entry.get("capture_id")) is not str or not _CAPTURE_ID.fullmatch(
            entry["capture_id"]
        ):
            raise MarketMemoryTechnicalStoreError(
                "actual-output generation capture_id is malformed"
            )
        if type(entry.get("session")) is not str or not _SESSION.fullmatch(
            entry["session"]
        ):
            raise MarketMemoryTechnicalStoreError(
                "actual-output generation session is malformed"
            )
        if type(entry.get("revision_id")) is not str or not _REVISION_ID.fullmatch(
            entry["revision_id"]
        ):
            raise MarketMemoryTechnicalStoreError(
                "actual-output generation revision_id is malformed"
            )
        if type(
            entry.get("source_observation_id")
        ) is not str or not _SOURCE_ID.fullmatch(entry["source_observation_id"]):
            raise MarketMemoryTechnicalStoreError(
                "actual-output generation source ID is malformed"
            )
        if type(entry.get("snapshot_id")) is not str or not _SNAPSHOT_ID.fullmatch(
            entry["snapshot_id"]
        ):
            raise MarketMemoryTechnicalStoreError(
                "actual-output generation snapshot ID is malformed"
            )
        _exact_utc(entry.get("first_observed_at"), field="first_observed_at")
        _require_digest(entry.get("receipt_sha256"), field="receipt digest")
        sort_keys.append(
            (
                entry["session"],
                entry["first_observed_at"],
                entry["capture_id"],
            )
        )
        capture_ids.append(entry["capture_id"])
        revisions.append(entry["revision_id"])
    if sort_keys != sorted(sort_keys) or len(capture_ids) != len(set(capture_ids)):
        raise MarketMemoryTechnicalStoreError(
            "actual-output generation capture index is not canonical"
        )
    if len(revisions) != len(set(revisions)):
        raise MarketMemoryTechnicalStoreError(
            "actual-output generation revision index is ambiguous"
        )
    if (
        _content_id("mmactualgeneration_", clean, field="generation_id")
        != generation_id
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output generation_id does not bind its generation"
        )
    return clean


def _new_head(generation: Mapping[str, Any], *, body: bytes) -> dict[str, Any]:
    return {
        "schema": HEAD_SCHEMA,
        "store_id": generation["store_id"],
        "generation_id": generation["generation_id"],
        "generation_sha256": _digest(body),
    }


def _validate_head(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    fields = {"schema", "store_id", "generation_id", "generation_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryTechnicalStoreError(
            "actual-output HEAD fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != HEAD_SCHEMA or clean.get("store_id") != store_id:
        raise MarketMemoryTechnicalStoreError(
            "actual-output HEAD schema or store mismatch"
        )
    if type(clean.get("generation_id")) is not str or not _GENERATION_ID.fullmatch(
        clean["generation_id"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output HEAD generation_id is malformed"
        )
    _require_digest(clean.get("generation_sha256"), field="HEAD generation digest")
    return clean


def _initialize_or_load(root: Path) -> _StoreState:
    manifest_path = _manifest_path(root)
    head_path = _head_path(root)
    if head_path.exists() or head_path.is_symlink():
        return _load_state(root)
    immutable_roots = (
        "prepared",
        "source_bodies",
        "source_observations",
        "feature_objects",
        "capture_receipts",
    )
    if not (manifest_path.exists() or manifest_path.is_symlink()):
        for name in ("generations", *immutable_roots):
            path = _safe_path(root, name)
            if path.exists() or path.is_symlink():
                raise MarketMemoryTechnicalStoreError(
                    "actual-output store initialization is partial"
                )
        manifest = _new_manifest()
        _write_json_create_once(
            root,
            manifest_path,
            _canonical_bytes(manifest),
            label="actual-output store manifest",
            limit=_MAX_MANIFEST_BYTES,
        )
    else:
        for name in immutable_roots:
            path = _safe_path(root, name)
            if path.exists() or path.is_symlink():
                raise MarketMemoryTechnicalStoreError(
                    "actual-output store has captures without an active HEAD"
                )
        manifest_raw, _ = _read_json(
            manifest_path,
            limit=_MAX_MANIFEST_BYTES,
            label="actual-output store manifest",
        )
        manifest = _validate_manifest(manifest_raw)
    clean_manifest = _validate_manifest(manifest)
    generation = _new_generation(
        store_id=clean_manifest["store_id"],
        previous_generation_id=None,
        captures=[],
    )
    generation_body = _canonical_bytes(generation)
    _write_json_create_once(
        root,
        _generation_path(root, generation["generation_id"]),
        generation_body,
        label="empty actual-output generation",
        limit=_MAX_GENERATION_BYTES,
    )
    head = _new_head(generation, body=generation_body)
    _replace_head(root, head)
    return _StoreState(clean_manifest, head, generation)


def _load_state(root: Path) -> _StoreState:
    manifest_raw, _ = _read_json(
        _manifest_path(root),
        limit=_MAX_MANIFEST_BYTES,
        label="actual-output store manifest",
    )
    manifest = _validate_manifest(manifest_raw)
    head_raw, _ = _read_json(
        _head_path(root), limit=_MAX_HEAD_BYTES, label="actual-output HEAD"
    )
    head = _validate_head(head_raw, store_id=manifest["store_id"])
    generation_raw, generation_body = _read_json(
        _generation_path(root, head["generation_id"]),
        limit=_MAX_GENERATION_BYTES,
        label="active actual-output generation",
    )
    if _digest(generation_body) != head["generation_sha256"]:
        raise MarketMemoryTechnicalStoreError(
            "actual-output HEAD generation digest mismatch"
        )
    generation = _validate_generation(generation_raw, store_id=manifest["store_id"])
    if generation["generation_id"] != head["generation_id"]:
        raise MarketMemoryTechnicalStoreError(
            "actual-output HEAD generation identity mismatch"
        )
    return _StoreState(manifest, head, generation)


def _source_refs(
    root: Path, bundle: technical.TechnicalSnapshotBundle
) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for role in _REMOTE_SOURCE_ROLES:
        artifact = bundle.source_observation["remote_sources"][role]
        path = _source_body_path(root, artifact["sha256"])
        refs[role] = {
            "url": artifact["url"],
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
            "etag_md5": artifact["etag_md5"],
            "last_modified": artifact["last_modified"],
            "content_type": artifact["content_type"],
            "object_key": _object_key(path, root=root),
        }
    for role in _GIT_SOURCE_ROLES:
        artifact = bundle.source_observation["git_sources"][role]
        path = _source_body_path(root, artifact["sha256"])
        refs[role] = {
            "repo_path": artifact["repo_path"],
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
            "git_blob_oid": artifact["git_blob_oid"],
            "object_key": _object_key(path, root=root),
        }
    return refs


def _bundle_source_bodies(
    bundle: technical.TechnicalSnapshotBundle,
) -> dict[str, bytes]:
    return {
        "publish_manifest": bundle.pinned_inputs.fetched.manifest_body,
        "spy_daily_parquet": bundle.pinned_inputs.fetched.spy_body,
        "canary_identity_config": (
            bundle.pinned_inputs.pinned_sources.canary_config_body
        ),
        "xnys_calendar_module": (
            bundle.pinned_inputs.pinned_sources.calendar_module_body
        ),
        "massive_entitlement_record": (
            bundle.pinned_inputs.pinned_sources.license_record_body
        ),
        "technical_price_basis_contract": (
            bundle.pinned_inputs.pinned_sources.price_basis_contract_body
        ),
    }


def _object_ref(
    root: Path,
    *,
    object_id: str,
    body: bytes,
    path: Path,
    schema: str,
    id_field: str,
) -> dict[str, Any]:
    return {
        id_field: object_id,
        "schema": schema,
        "sha256": _digest(body),
        "bytes": len(body),
        "object_key": _object_key(path, root=root),
    }


def _prepared_id(bundle: technical.TechnicalSnapshotBundle) -> str:
    core = {
        "profile": STORE_PROFILE,
        "session": bundle.feature_object["session"],
        "source_observation_id": bundle.source_observation["source_observation_id"],
        "snapshot_id": bundle.feature_object["snapshot_id"],
    }
    return "mmprepared_" + _digest(_canonical_bytes(core))


def _revision_id(bundle: technical.TechnicalSnapshotBundle) -> str:
    core = {
        "profile": STORE_PROFILE,
        "session": bundle.feature_object["session"],
        "source_observation_id": bundle.source_observation["source_observation_id"],
        "snapshot_id": bundle.feature_object["snapshot_id"],
    }
    return "mmtechrev_" + _digest(_canonical_bytes(core))


def _new_prepared(
    root: Path,
    bundle: technical.TechnicalSnapshotBundle,
    *,
    first_observed_at: str,
) -> dict[str, Any]:
    prepared_id = _prepared_id(bundle)
    source_id = bundle.source_observation["source_observation_id"]
    snapshot_id = bundle.feature_object["snapshot_id"]
    freshness = _freshness_receipt(
        session=bundle.feature_object["session"],
        manifest_last_modified=bundle.source_observation["remote_sources"][
            "publish_manifest"
        ]["last_modified"],
        first_observed_at=first_observed_at,
    )
    return {
        "schema": PREPARED_SCHEMA,
        "prepared_id": prepared_id,
        "profile": STORE_PROFILE,
        "session": bundle.feature_object["session"],
        "source_commit": bundle.pinned_inputs.pinned_sources.pinned_commit,
        "source_observation_id": source_id,
        "snapshot_id": snapshot_id,
        "revision_id": _revision_id(bundle),
        "source_bodies": _source_refs(root, bundle),
        "source_observation": _object_ref(
            root,
            object_id=source_id,
            body=bundle.source_observation_bytes,
            path=_source_object_path(root, source_id),
            schema=_SOURCE_OBSERVATION_SCHEMA_V1,
            id_field="source_observation_id",
        ),
        "feature_object": _object_ref(
            root,
            object_id=snapshot_id,
            body=bundle.feature_object_bytes,
            path=_feature_object_path(root, snapshot_id),
            schema=_FEATURE_OBJECT_SCHEMA_V1,
            id_field="snapshot_id",
        ),
        "first_observed_at": first_observed_at,
        "available_at": first_observed_at,
        "freshness": freshness,
        "evidence_policy": dict(_EVIDENCE_POLICY_V1),
        "authority": dict(_AUTHORITY_V1),
    }


def _validate_source_refs(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != set(_SOURCE_ROLES):
        raise MarketMemoryTechnicalStoreError(
            "actual-output source body roles are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    expected_paths = {
        "canary_identity_config": "config/market_memory_canary.v1.json",
        "xnys_calendar_module": "lib/nyse_calendar.py",
        "massive_entitlement_record": (
            "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md"
        ),
        "technical_price_basis_contract": (
            "config/market_memory_technical_price_basis.v1.json"
        ),
    }
    expected_urls = {
        "publish_manifest": technical.MANIFEST_URL,
        "spy_daily_parquet": technical.SPY_PARQUET_URL,
    }
    remote_fields = {
        "url",
        "sha256",
        "bytes",
        "etag_md5",
        "last_modified",
        "content_type",
        "object_key",
    }
    for role in _REMOTE_SOURCE_ROLES:
        ref = clean[role]
        if not isinstance(ref, Mapping) or set(ref) != remote_fields:
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} reference fields are not canonical"
            )
        if ref.get("url") != expected_urls[role]:
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} source URL drift"
            )
        digest = _require_digest(ref.get("sha256"), field=f"{role} digest")
        byte_count = _require_int(
            ref.get("bytes"), field=f"{role} bytes", maximum=_SOURCE_LIMITS[role]
        )
        if type(ref.get("etag_md5")) is not str or not re.fullmatch(
            r"[a-f0-9]{32}", ref["etag_md5"]
        ):
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} ETag is malformed"
            )
        expected_content_type = (
            "application/json"
            if role == "publish_manifest"
            else "application/octet-stream"
        )
        if ref.get("content_type") != expected_content_type:
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} content type drift"
            )
        # The detached projector enforces canonical IMF-fixdate.  Reparse here
        # so a standalone receipt cannot carry an arbitrary timestamp string.
        try:
            modified = parsedate_to_datetime(ref.get("last_modified"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} Last-Modified is malformed"
            ) from exc
        if (
            modified.tzinfo is None
            or modified.utcoffset() != timedelta(0)
            or format_datetime(modified.astimezone(timezone.utc), usegmt=True)
            != ref.get("last_modified")
        ):
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} Last-Modified is noncanonical"
            )
        if byte_count < 1:  # pragma: no cover - enforced by _require_int
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} bytes are empty"
            )
        if ref.get("object_key") != f"source_bodies/{digest[:2]}/{digest}.bin":
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} object key is not canonical"
            )

    git_fields = {"repo_path", "sha256", "bytes", "git_blob_oid", "object_key"}
    for role in _GIT_SOURCE_ROLES:
        ref = clean[role]
        if not isinstance(ref, Mapping) or set(ref) != git_fields:
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} reference fields are not canonical"
            )
        if ref.get("repo_path") != expected_paths[role]:
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} repository path drift"
            )
        digest = _require_digest(ref.get("sha256"), field=f"{role} digest")
        if digest != _GIT_SOURCE_SHA256[role]:
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} reviewed digest drift"
            )
        _require_int(
            ref.get("bytes"), field=f"{role} bytes", maximum=_SOURCE_LIMITS[role]
        )
        oid = ref.get("git_blob_oid")
        if type(oid) is not str or not _COMMIT.fullmatch(oid):
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} Git blob OID is malformed"
            )
        if ref.get("object_key") != f"source_bodies/{digest[:2]}/{digest}.bin":
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} object key is not canonical"
            )
    return clean


def _validate_object_ref(
    value: object,
    *,
    id_field: str,
    id_pattern: re.Pattern[str],
    schema: str,
    directory: str,
    maximum: int,
) -> dict[str, Any]:
    fields = {id_field, "schema", "sha256", "bytes", "object_key"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryTechnicalStoreError(
            f"actual-output {id_field} reference fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    object_id = clean.get(id_field)
    if type(object_id) is not str or not id_pattern.fullmatch(object_id):
        raise MarketMemoryTechnicalStoreError(
            f"actual-output {id_field} reference is malformed"
        )
    if clean.get("schema") != schema:
        raise MarketMemoryTechnicalStoreError(f"actual-output {id_field} schema drift")
    _require_digest(clean.get("sha256"), field=f"{id_field} digest")
    _require_int(clean.get("bytes"), field=f"{id_field} bytes", maximum=maximum)
    identity_digest = object_id.rsplit("_", 1)[-1]
    if clean.get("object_key") != (
        f"{directory}/{identity_digest[:2]}/{object_id}.json"
    ):
        raise MarketMemoryTechnicalStoreError(
            f"actual-output {id_field} object key is not canonical"
        )
    return clean


def _validate_prepared(
    value: Mapping[str, Any],
    *,
    expected_bundle: technical.TechnicalSnapshotBundle | None = None,
) -> dict[str, Any]:
    fields = {
        "schema",
        "prepared_id",
        "profile",
        "session",
        "source_commit",
        "source_observation_id",
        "snapshot_id",
        "revision_id",
        "source_bodies",
        "source_observation",
        "feature_object",
        "first_observed_at",
        "available_at",
        "freshness",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared record fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != PREPARED_SCHEMA or clean.get("profile") != STORE_PROFILE:
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared schema or profile drift"
        )
    if type(clean.get("session")) is not str or not _SESSION.fullmatch(
        clean["session"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared session is malformed"
        )
    if type(clean.get("source_commit")) is not str or not _COMMIT.fullmatch(
        clean["source_commit"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared source commit is malformed"
        )
    if type(clean.get("source_observation_id")) is not str or not _SOURCE_ID.fullmatch(
        clean["source_observation_id"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared source ID is malformed"
        )
    if type(clean.get("snapshot_id")) is not str or not _SNAPSHOT_ID.fullmatch(
        clean["snapshot_id"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared snapshot ID is malformed"
        )
    if type(clean.get("revision_id")) is not str or not _REVISION_ID.fullmatch(
        clean["revision_id"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared revision ID is malformed"
        )
    sources = _validate_source_refs(clean.get("source_bodies"))
    source_ref = _validate_object_ref(
        clean.get("source_observation"),
        id_field="source_observation_id",
        id_pattern=_SOURCE_ID,
        schema=_SOURCE_OBSERVATION_SCHEMA_V1,
        directory="source_observations",
        maximum=_MAX_SOURCE_OBJECT_BYTES,
    )
    feature_ref = _validate_object_ref(
        clean.get("feature_object"),
        id_field="snapshot_id",
        id_pattern=_SNAPSHOT_ID,
        schema=_FEATURE_OBJECT_SCHEMA_V1,
        directory="feature_objects",
        maximum=_MAX_FEATURE_OBJECT_BYTES,
    )
    if (
        source_ref["source_observation_id"] != clean["source_observation_id"]
        or feature_ref["snapshot_id"] != clean["snapshot_id"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared object identities disagree"
        )
    first = _exact_utc(
        clean.get("first_observed_at"), field="prepared first_observed_at"
    )
    available = _exact_utc(clean.get("available_at"), field="prepared available_at")
    if first != available:
        raise MarketMemoryTechnicalStoreError(
            "actual-output first availability clocks must be identical"
        )
    expected_freshness = _freshness_receipt(
        session=clean["session"],
        manifest_last_modified=sources["publish_manifest"]["last_modified"],
        first_observed_at=first,
    )
    if clean.get("freshness") != expected_freshness:
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared freshness receipt drift"
        )
    if clean.get("evidence_policy") != _EVIDENCE_POLICY_V1:
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared evidence policy drift"
        )
    if clean.get("authority") != _AUTHORITY_V1:
        raise MarketMemoryTechnicalStoreError("actual-output prepared authority drift")
    core = {
        "profile": STORE_PROFILE,
        "session": clean["session"],
        "source_observation_id": clean["source_observation_id"],
        "snapshot_id": clean["snapshot_id"],
    }
    expected_prepared_id = "mmprepared_" + _digest(_canonical_bytes(core))
    expected_revision_id = "mmtechrev_" + _digest(_canonical_bytes(core))
    if (
        clean.get("prepared_id") != expected_prepared_id
        or clean.get("revision_id") != expected_revision_id
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared identities do not bind their core"
        )
    if expected_bundle is not None:
        expected = _new_prepared(
            Path("/unused/technicals-v1"),
            expected_bundle,
            first_observed_at=first,
        )
        # The first source commit is provenance, not semantic identity.  A
        # code-only commit with the same three Git blobs remains idempotent.
        expected["source_commit"] = clean["source_commit"]
        if clean != expected:
            raise MarketMemoryTechnicalCaptureError(
                "existing prepared record differs from the validated bundle"
            )
    clean["source_bodies"] = sources
    clean["source_observation"] = source_ref
    clean["feature_object"] = feature_ref
    return clean


def _load_or_create_prepared(
    root: Path,
    bundle: technical.TechnicalSnapshotBundle,
    *,
    attempt_observed_at: str | None,
) -> dict[str, Any]:
    prepared_id = _prepared_id(bundle)
    path = _prepared_path(root, prepared_id)
    if path.exists() or path.is_symlink():
        raw, _ = _read_json(
            path,
            limit=_MAX_PREPARED_BYTES,
            label="existing actual-output prepared record",
        )
        return _validate_prepared(raw, expected_bundle=bundle)
    if attempt_observed_at is None:
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared record disappeared under the writer lock"
        )
    # The current-attempt clock was sampled after detached validation and its
    # freshness was admitted before any store mutation.  This is the first
    # per-capture durable write and therefore owns first_observed_at.
    prepared = _new_prepared(root, bundle, first_observed_at=attempt_observed_at)
    body = _canonical_bytes(prepared)
    _write_json_create_once(
        root,
        path,
        body,
        label="actual-output prepared record",
        limit=_MAX_PREPARED_BYTES,
    )
    return _validate_prepared(prepared, expected_bundle=bundle)


def _build_receipt(
    root: Path,
    *,
    store_id: str,
    prepared: Mapping[str, Any],
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": CAPTURE_RECEIPT_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": store_id,
        "capture_id": "",
        "prepared_id": prepared["prepared_id"],
        "prepared_object_key": _object_key(
            _prepared_path(root, prepared["prepared_id"]), root=root
        ),
        "session": prepared["session"],
        "revision_id": prepared["revision_id"],
        "source_commit": prepared["source_commit"],
        "source_bodies": copy.deepcopy(prepared["source_bodies"]),
        "source_observation": copy.deepcopy(prepared["source_observation"]),
        "feature_object": copy.deepcopy(prepared["feature_object"]),
        "freshness": copy.deepcopy(prepared["freshness"]),
        "clocks": {
            "first_observed_at": prepared["first_observed_at"],
            "available_at": prepared["available_at"],
        },
        "mode": "private_actual_output_current_tip",
        "actual_output_capture": True,
        "evidence_policy": dict(_EVIDENCE_POLICY_V1),
        "authority": dict(_AUTHORITY_V1),
    }
    receipt["capture_id"] = _content_id("mmactualcapture_", receipt, field="capture_id")
    return receipt


def _validate_receipt(
    value: Mapping[str, Any], *, store_id: str | None = None
) -> dict[str, Any]:
    fields = {
        "schema",
        "profile",
        "store_id",
        "capture_id",
        "prepared_id",
        "prepared_object_key",
        "session",
        "revision_id",
        "source_commit",
        "source_bodies",
        "source_observation",
        "feature_object",
        "freshness",
        "clocks",
        "mode",
        "actual_output_capture",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryTechnicalStoreError(
            "actual-output capture receipt fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if (
        clean.get("schema") != CAPTURE_RECEIPT_SCHEMA
        or clean.get("profile") != STORE_PROFILE
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output capture schema or profile drift"
        )
    receipt_store = clean.get("store_id")
    if type(receipt_store) is not str or not _STORE_ID.fullmatch(receipt_store):
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt store_id is malformed"
        )
    if store_id is not None and receipt_store != store_id:
        raise MarketMemoryTechnicalStoreError(
            "actual-output capture belongs to another store"
        )
    if type(clean.get("prepared_id")) is not str or not _PREPARED_ID.fullmatch(
        clean["prepared_id"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt prepared_id is malformed"
        )
    prepared_digest = clean["prepared_id"].removeprefix("mmprepared_")
    if clean.get("prepared_object_key") != (
        f"prepared/{prepared_digest[:2]}/{clean['prepared_id']}.json"
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt prepared key is not canonical"
        )
    if type(clean.get("session")) is not str or not _SESSION.fullmatch(
        clean["session"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt session is malformed"
        )
    if type(clean.get("revision_id")) is not str or not _REVISION_ID.fullmatch(
        clean["revision_id"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt revision_id is malformed"
        )
    if type(clean.get("source_commit")) is not str or not _COMMIT.fullmatch(
        clean["source_commit"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt source commit is malformed"
        )
    sources = _validate_source_refs(clean.get("source_bodies"))
    source_ref = _validate_object_ref(
        clean.get("source_observation"),
        id_field="source_observation_id",
        id_pattern=_SOURCE_ID,
        schema=_SOURCE_OBSERVATION_SCHEMA_V1,
        directory="source_observations",
        maximum=_MAX_SOURCE_OBJECT_BYTES,
    )
    feature_ref = _validate_object_ref(
        clean.get("feature_object"),
        id_field="snapshot_id",
        id_pattern=_SNAPSHOT_ID,
        schema=_FEATURE_OBJECT_SCHEMA_V1,
        directory="feature_objects",
        maximum=_MAX_FEATURE_OBJECT_BYTES,
    )
    clocks = clean.get("clocks")
    if not isinstance(clocks, Mapping) or set(clocks) != {
        "first_observed_at",
        "available_at",
    }:
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt clocks are not canonical"
        )
    first = _exact_utc(
        clocks.get("first_observed_at"), field="receipt first_observed_at"
    )
    available = _exact_utc(clocks.get("available_at"), field="receipt available_at")
    if first != available:
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt availability clocks disagree"
        )
    expected_freshness = _freshness_receipt(
        session=clean["session"],
        manifest_last_modified=sources["publish_manifest"]["last_modified"],
        first_observed_at=first,
    )
    if clean.get("freshness") != expected_freshness:
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt freshness receipt drift"
        )
    if clean.get("mode") != "private_actual_output_current_tip":
        raise MarketMemoryTechnicalStoreError("actual-output receipt mode drift")
    if clean.get("actual_output_capture") is not True:
        raise MarketMemoryTechnicalStoreError(
            "actual-output capture receipt must assert its durable capture"
        )
    if clean.get("evidence_policy") != _EVIDENCE_POLICY_V1:
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt evidence policy drift"
        )
    if clean.get("authority") != _AUTHORITY_V1:
        raise MarketMemoryTechnicalStoreError("actual-output receipt authority drift")
    capture_id = clean.get("capture_id")
    if type(capture_id) is not str or not _CAPTURE_ID.fullmatch(capture_id):
        raise MarketMemoryTechnicalStoreError("actual-output capture_id is malformed")
    if _content_id("mmactualcapture_", clean, field="capture_id") != capture_id:
        raise MarketMemoryTechnicalStoreError(
            "actual-output capture_id does not bind its receipt"
        )
    clean["source_bodies"] = sources
    clean["source_observation"] = source_ref
    clean["feature_object"] = feature_ref
    clean["clocks"] = dict(clocks)
    return clean


def _generation_entry(receipt: Mapping[str, Any], *, body: bytes) -> dict[str, Any]:
    return {
        "capture_id": receipt["capture_id"],
        "session": receipt["session"],
        "revision_id": receipt["revision_id"],
        "source_observation_id": receipt["source_observation"]["source_observation_id"],
        "snapshot_id": receipt["feature_object"]["snapshot_id"],
        "first_observed_at": receipt["clocks"]["first_observed_at"],
        "receipt_sha256": _digest(body),
    }


def _load_generation(
    root: Path, *, manifest: Mapping[str, Any], generation_id: str | None
) -> tuple[dict[str, Any], bytes]:
    if generation_id is None:
        state = _load_state(root)
        return state.generation, _canonical_bytes(state.generation)
    raw, body = _read_json(
        _generation_path(root, generation_id),
        limit=_MAX_GENERATION_BYTES,
        label="pinned actual-output generation",
    )
    clean = _validate_generation(raw, store_id=manifest["store_id"])
    if clean["generation_id"] != generation_id:
        raise MarketMemoryTechnicalStoreError(
            "pinned actual-output generation differs from its object key"
        )
    return clean, body


def _load_capture(
    root: Path,
    *,
    manifest: Mapping[str, Any],
    generation: Mapping[str, Any],
    capture_id: str,
) -> StoredTechnicalActualOutput:
    matches = [
        dict(entry)
        for entry in generation["captures"]
        if entry["capture_id"] == capture_id
    ]
    if len(matches) != 1:
        raise MarketMemoryTechnicalStoreError(
            "capture is absent or ambiguous in the pinned generation"
        )
    entry = matches[0]
    receipt_raw, receipt_body = _read_json(
        _capture_path(root, capture_id),
        limit=_MAX_RECEIPT_BYTES,
        label="actual-output capture receipt",
    )
    receipt = _validate_receipt(receipt_raw, store_id=manifest["store_id"])
    if _generation_entry(receipt, body=receipt_body) != entry:
        raise MarketMemoryTechnicalStoreError(
            "actual-output capture receipt differs from its generation entry"
        )
    prepared_raw, prepared_body = _read_json(
        _prepared_path(root, receipt["prepared_id"]),
        limit=_MAX_PREPARED_BYTES,
        label="actual-output prepared record",
    )
    prepared = _validate_prepared(prepared_raw)
    if _digest(prepared_body) == receipt["capture_id"]:
        # Impossible with the distinct namespaces; retain an explicit
        # cross-object guard so a caller cannot treat one hash as another.
        raise MarketMemoryTechnicalStoreError(
            "actual-output prepared and capture identities are aliased"
        )
    expected_from_prepared = _build_receipt(
        root,
        store_id=manifest["store_id"],
        prepared=prepared,
    )
    if expected_from_prepared != receipt:
        raise MarketMemoryTechnicalStoreError(
            "actual-output receipt differs from its prepared record"
        )

    bodies: dict[str, bytes] = {}
    for role in _SOURCE_ROLES:
        ref = receipt["source_bodies"][role]
        path = _source_body_path(root, ref["sha256"])
        if _object_key(path, root=root) != ref["object_key"]:
            raise MarketMemoryTechnicalStoreError(
                f"actual-output {role} path differs from its receipt"
            )
        bodies[role] = _read_raw(
            path,
            digest=ref["sha256"],
            expected_bytes=ref["bytes"],
            limit=_SOURCE_LIMITS[role],
            label=f"stored {role}",
        )
    source_ref = receipt["source_observation"]
    source_raw, source_body = _read_json(
        _source_object_path(root, source_ref["source_observation_id"]),
        limit=_MAX_SOURCE_OBJECT_BYTES,
        label="stored technical source observation",
    )
    if (
        len(source_body) != source_ref["bytes"]
        or _digest(source_body) != source_ref["sha256"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "stored source observation differs from its receipt"
        )
    feature_ref = receipt["feature_object"]
    feature_raw, feature_body = _read_json(
        _feature_object_path(root, feature_ref["snapshot_id"]),
        limit=_MAX_FEATURE_OBJECT_BYTES,
        label="stored technical feature object",
    )
    if (
        len(feature_body) != feature_ref["bytes"]
        or _digest(feature_body) != feature_ref["sha256"]
    ):
        raise MarketMemoryTechnicalStoreError(
            "stored feature object differs from its receipt"
        )

    def stored_headers(role: str) -> tuple[tuple[str, str], ...]:
        ref = receipt["source_bodies"][role]
        return (
            ("content-type", ref["content_type"]),
            ("content-length", str(ref["bytes"])),
            ("etag", f'"{ref["etag_md5"]}"'),
            ("last-modified", ref["last_modified"]),
        )

    pinned_inputs = technical.PinnedTechnicalInputs(
        fetched=technical.FetchedSpyDailyInputs(
            manifest_body=bodies["publish_manifest"],
            manifest_headers=stored_headers("publish_manifest"),
            spy_body=bodies["spy_daily_parquet"],
            spy_headers=stored_headers("spy_daily_parquet"),
        ),
        pinned_sources=technical.PinnedTechnicalSources(
            pinned_commit=receipt["source_commit"],
            canary_config_body=bodies["canary_identity_config"],
            calendar_module_body=bodies["xnys_calendar_module"],
            license_record_body=bodies["massive_entitlement_record"],
            price_basis_contract_body=bodies["technical_price_basis_contract"],
            git_blob_oids=tuple(
                (role, receipt["source_bodies"][role]["git_blob_oid"])
                for role in _GIT_SOURCE_ROLES
            ),
        ),
    )
    candidate = technical.TechnicalSnapshotBundle(
        pinned_inputs=pinned_inputs,
        source_observation=source_raw,
        source_observation_bytes=source_body,
        feature_object=feature_raw,
        feature_object_bytes=feature_body,
    )
    try:
        checked = technical.validate_technical_snapshot_bundle(candidate)
    except technical.MarketMemoryTechnicalObservationError as exc:
        raise MarketMemoryTechnicalStoreError(
            "stored technical bundle fails detached reprojection"
        ) from exc
    _validate_prepared(prepared, expected_bundle=checked)
    return StoredTechnicalActualOutput(
        generation_id=generation["generation_id"],
        capture_receipt=receipt,
        bundle=checked,
    )


def initialize_technical_actual_output_store(root: str | Path) -> dict[str, Any]:
    """Create or validate the complete empty private technical generation."""

    store_root = validate_technical_actual_output_store_root(root)
    _mkdir(store_root)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(store_root, flags)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        state = _initialize_or_load(store_root)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return {
        "schema": state.manifest["schema"],
        "profile": state.manifest["profile"],
        "store_id": state.manifest["store_id"],
        "generation_id": state.generation["generation_id"],
        "capture_count": len(state.generation["captures"]),
    }


def load_technical_actual_output_generation(
    root: str | Path, *, generation_id: str | None = None
) -> dict[str, Any]:
    """Load the active or an explicitly pinned immutable generation."""

    store_root = validate_technical_actual_output_store_root(root)
    state = _load_state(store_root)
    generation, _ = _load_generation(
        store_root,
        manifest=state.manifest,
        generation_id=generation_id,
    )
    return copy.deepcopy(generation)


def load_technical_actual_output_capture(
    root: str | Path,
    *,
    capture_id: str,
    generation_id: str | None = None,
) -> StoredTechnicalActualOutput:
    """Reload one capture only if named by the selected complete generation."""

    store_root = validate_technical_actual_output_store_root(root)
    state = _load_state(store_root)
    generation, _ = _load_generation(
        store_root,
        manifest=state.manifest,
        generation_id=generation_id,
    )
    return _load_capture(
        store_root,
        manifest=state.manifest,
        generation=generation,
        capture_id=capture_id,
    )


def capture_technical_actual_output(
    root: str | Path,
    *,
    bundle: technical.TechnicalSnapshotBundle,
) -> StoredTechnicalActualOutput:
    """Validate and append one exact current technical actual-output revision."""

    # No filesystem mutation or wall-clock sample may precede this detached
    # raw-byte reprojection boundary.
    try:
        checked = technical.validate_technical_snapshot_bundle(bundle)
    except technical.MarketMemoryTechnicalObservationError as exc:
        raise MarketMemoryTechnicalCaptureError(
            "technical bundle failed detached validation before store entry"
        ) from exc
    if (
        checked.source_observation.get("schema") != _SOURCE_OBSERVATION_SCHEMA_V1
        or checked.feature_object.get("schema") != _FEATURE_OBJECT_SCHEMA_V1
    ):
        raise MarketMemoryTechnicalCaptureError(
            "technical bundle is not the frozen actual-output store v1 contract"
        )
    store_root = validate_technical_actual_output_store_root(root)
    _mkdir(store_root)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(store_root, flags)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        state = _initialize_or_load(store_root)
        source_id = checked.source_observation["source_observation_id"]
        snapshot_id = checked.feature_object["snapshot_id"]
        matching = [
            dict(entry)
            for entry in state.generation["captures"]
            if entry["source_observation_id"] == source_id
            or entry["snapshot_id"] == snapshot_id
        ]
        if matching:
            if len(matching) != 1 or (
                matching[0]["source_observation_id"] != source_id
                or matching[0]["snapshot_id"] != snapshot_id
            ):
                raise MarketMemoryTechnicalStoreError(
                    "actual-output generation contains an ambiguous identity match"
                )
            # An already-active idempotent recapture is a new success claim and
            # must prove that the tip remains fresh at this attempt's clock.
            active_attempt_observed_at = _sample_first_observed_at()
            _freshness_receipt(
                session=checked.feature_object["session"],
                manifest_last_modified=checked.source_observation["remote_sources"][
                    "publish_manifest"
                ]["last_modified"],
                first_observed_at=active_attempt_observed_at,
            )
            stored = _load_capture(
                store_root,
                manifest=state.manifest,
                generation=state.generation,
                capture_id=matching[0]["capture_id"],
            )
            if (
                stored.bundle.source_observation_bytes
                != checked.source_observation_bytes
                or stored.bundle.feature_object_bytes != checked.feature_object_bytes
                or _bundle_source_bodies(stored.bundle)
                != _bundle_source_bodies(checked)
            ):
                raise MarketMemoryTechnicalStoreError(
                    "idempotent technical identity differs from stored exact bytes"
                )
            return stored

        prepared_path = _prepared_path(store_root, _prepared_id(checked))
        if prepared_path.exists() or prepared_path.is_symlink():
            # A sealed prepared record proves the original attempt passed
            # freshness before its first durable write.  Resume that exact
            # attempt without manufacturing or applying a later clock.
            attempt_observed_at = None
        else:
            # This is a genuinely new attempt.  Admit current freshness under
            # the writer lock, then make its prepared record the first
            # per-capture durable write.
            attempt_observed_at = _sample_first_observed_at()
            _freshness_receipt(
                session=checked.feature_object["session"],
                manifest_last_modified=checked.source_observation["remote_sources"][
                    "publish_manifest"
                ]["last_modified"],
                first_observed_at=attempt_observed_at,
            )
        prepared = _load_or_create_prepared(
            store_root,
            checked,
            attempt_observed_at=attempt_observed_at,
        )
        receipt = _build_receipt(
            store_root,
            store_id=state.manifest["store_id"],
            prepared=prepared,
        )
        receipt = _validate_receipt(receipt, store_id=state.manifest["store_id"])
        receipt_body = _canonical_bytes(receipt)
        if len(receipt_body) > _MAX_RECEIPT_BYTES:
            raise MarketMemoryTechnicalCaptureError(
                "actual-output capture receipt exceeds its byte bound"
            )
        if len(state.generation["captures"]) >= _MAX_GENERATION_CAPTURES:
            raise MarketMemoryTechnicalCaptureError(
                "actual-output generation reached its pilot capture bound"
            )
        entry = _generation_entry(receipt, body=receipt_body)
        generation = _new_generation(
            store_id=state.manifest["store_id"],
            previous_generation_id=state.generation["generation_id"],
            captures=[
                *[dict(item) for item in state.generation["captures"]],
                entry,
            ],
        )
        generation_body = _canonical_bytes(generation)
        if len(generation_body) > _MAX_GENERATION_BYTES:
            raise MarketMemoryTechnicalCaptureError(
                "actual-output generation exceeds its byte bound"
            )

        bodies = _bundle_source_bodies(checked)
        # The prepared record is already durable.  Only now may CAS objects be
        # linked.  Every immutable file is fsynced before the cumulative
        # generation, and HEAD is the final mutable write.
        for role in _SOURCE_ROLES:
            ref = receipt["source_bodies"][role]
            _write_raw_create_once(
                store_root,
                _source_body_path(store_root, ref["sha256"]),
                bodies[role],
                digest=ref["sha256"],
                label=f"{role} source body",
                limit=_SOURCE_LIMITS[role],
            )
        _write_json_create_once(
            store_root,
            _source_object_path(store_root, source_id),
            checked.source_observation_bytes,
            label="technical source observation",
            limit=_MAX_SOURCE_OBJECT_BYTES,
        )
        _write_json_create_once(
            store_root,
            _feature_object_path(store_root, snapshot_id),
            checked.feature_object_bytes,
            label="technical feature object",
            limit=_MAX_FEATURE_OBJECT_BYTES,
        )
        _write_json_create_once(
            store_root,
            _capture_path(store_root, receipt["capture_id"]),
            receipt_body,
            label="actual-output capture receipt",
            limit=_MAX_RECEIPT_BYTES,
        )
        _write_json_create_once(
            store_root,
            _generation_path(store_root, generation["generation_id"]),
            generation_body,
            label="actual-output generation",
            limit=_MAX_GENERATION_BYTES,
        )
        _replace_head(
            store_root,
            _new_head(generation, body=generation_body),
        )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return load_technical_actual_output_capture(
        store_root,
        capture_id=receipt["capture_id"],
        generation_id=generation["generation_id"],
    )


__all__ = [
    "CAPTURE_RECEIPT_SCHEMA",
    "GENERATION_SCHEMA",
    "HEAD_SCHEMA",
    "PREPARED_SCHEMA",
    "STORE_PROFILE",
    "STORE_SCHEMA",
    "MarketMemoryTechnicalCaptureError",
    "MarketMemoryTechnicalStoreError",
    "StoredTechnicalActualOutput",
    "capture_technical_actual_output",
    "default_technical_actual_output_store_root",
    "initialize_technical_actual_output_store",
    "load_technical_actual_output_capture",
    "load_technical_actual_output_generation",
    "validate_technical_actual_output_store_root",
]
