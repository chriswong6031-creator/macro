"""Private append-only storage for the W1B.5 option-OI availability canary.

This is deliberately a source-availability store, not an options feature
store.  It preserves the exact first-page response body, the two reviewed Git
source bodies, and the detached probe/source receipts in an isolated
``options-v1`` tree.  It never follows a continuation, infers a measurement
date or session, resolves contract identity, projects open-interest values or
totals, calculates GEX, or grants replay/training/trading authority.

The response-body completion clock comes from the validated observation
bundle.  Every exact recovery CAS object is durable before the writer samples
``first_observed_at`` and seals it in a create-once prepared record.  Thus a
durable prepared record is self-recoverable after a process restart, while a
pre-prepared crash leaves only harmless unclaimed CAS.  The cumulative
generation is fsynced before ``HEAD.json`` advances last.
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
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from engine.neuralweb import (
    market_memory_option_oi_observation as option_oi,
)
from engine.neuralweb import (
    market_memory_pit,
)

STORE_PROFILE = "market_memory.private.spy_option_oi_source_availability.v1"
STORE_SCHEMA = "market_memory.option_oi_store.v1"
PREPARED_SCHEMA = "market_memory.option_oi_prepared.v1"
CAPTURE_RECEIPT_SCHEMA = "market_memory.option_oi_capture_receipt.v1"
GENERATION_SCHEMA = "market_memory.option_oi_store_generation.v1"
HEAD_SCHEMA = "market_memory.option_oi_store_head.v1"
_SOURCE_OBSERVATION_SCHEMA_V1 = option_oi.SOURCE_OBSERVATION_SCHEMA
_PROBE_RECEIPT_SCHEMA_V1 = option_oi.PROBE_RECEIPT_SCHEMA

_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_PREPARED_BYTES = 128 * 1024
_MAX_RECEIPT_BYTES = 128 * 1024
_MAX_SOURCE_OBJECT_BYTES = 128 * 1024
_MAX_PROBE_RECEIPT_BYTES = 128 * 1024
_MAX_GENERATION_BYTES = 4 * 1024 * 1024
_MAX_GENERATION_CAPTURES = 4_096
_MAX_PREPARED_RECORDS = 4_096
_MAX_PREPARED_SCRATCH_FILES = 64
_MAX_HEAD_BYTES = 16 * 1024
_SOURCE_LIMITS = {
    "option_oi_response_body": option_oi.MAX_ENTITY_BYTES,
    "option_oi_source_config": 32 * 1024,
    "massive_entitlement_record": 64 * 1024,
}
_SOURCE_ROLES = tuple(_SOURCE_LIMITS)
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_STORE_ID = re.compile(r"mmoptionoistore_[a-f0-9]{64}\Z")
_PREPARED_ID = re.compile(r"mmoptionoiprepared_[a-f0-9]{64}\Z")
_CAPTURE_ID = re.compile(r"mmoptionoicapture_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmoptionoigeneration_[a-f0-9]{64}\Z")
_SOURCE_ID = re.compile(r"mmoptionoisrc_[a-f0-9]{64}\Z")
_PROBE_ID = re.compile(r"mmoptionoiprobe_[a-f0-9]{64}\Z")
_PREPARED_SCRATCH_FILE = re.compile(
    r"\.mmoptionoiprepared_[a-f0-9]{64}\.json\.tmp\.[1-9][0-9]*\.[a-f0-9]{32}\Z"
)
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_COMPLETENESS_V1: Mapping[str, Any] = MappingProxyType(
    {
        "page_complete": True,
        "continuation_followed": False,
        "intentionally_bounded": True,
        "chain_complete": False,
        "contract_universe_complete": False,
        "atomic_chain_snapshot_verified": False,
    }
)
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
        "source_availability_only": True,
        "future_only": True,
        "first_page_only": True,
        "source_payload_contract_validated": True,
        "exact_source_bodies_integrity_bound": True,
        "provider_response_signed": False,
        "raw_cas_durable_before_prepared_clock": True,
        "prepared_self_recoverable_from_cas": True,
        "prepared_temporaries_isolated_from_scan": True,
        "page_complete": True,
        "continuation_followed": False,
        "intentionally_bounded": True,
        "chain_complete": False,
        "contract_universe_complete": False,
        "atomic_chain_snapshot_verified": False,
        "measurement_time_authenticated": False,
        "measurement_session_authenticated": False,
        "measurement_date_authenticated": False,
        "permanent_contract_identity_resolved": False,
        "contract_multiplier_assumed": False,
        "raw_entity_body_preserved_in_private_cas": True,
        "raw_entity_body_publicly_exposed": False,
        "vendor_tickers_projected": False,
        "open_interest_values_projected": False,
        "open_interest_totals_projected": False,
        "gex_projected": False,
        "replay_eligible": False,
        "feature_eligible": False,
        "context_only": True,
        "training_eligible": False,
        "promotion_eligible": False,
    }
)


class MarketMemoryOptionOiStoreError(market_memory_pit.MarketMemoryStoreError):
    """The private actual-output store is unavailable or corrupted."""


class MarketMemoryOptionOiCaptureError(MarketMemoryOptionOiStoreError):
    """A candidate actual output cannot enter the private store."""


@dataclass(frozen=True)
class StoredOptionOiObservation:
    """One capture reloaded and reprojected from its exact stored source CAS."""

    generation_id: str
    capture_receipt: dict[str, Any]
    bundle: option_oi.OptionOiObservationBundle


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
        raise MarketMemoryOptionOiStoreError(
            "actual-output value is not finite canonical JSON"
        ) from exc


def _json_type_strict_equal(value: object, expected: object) -> bool:
    """Compare JSON values without Python's bool/int equality aliasing."""

    if isinstance(expected, Mapping):
        expected = dict(expected)
    return _canonical_bytes(value) == _canonical_bytes(expected)


def _digest(body: bytes) -> str:
    return sha256(body).hexdigest()


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + _digest(_canonical_bytes(core))


def _exact_utc(value: object, *, field: str) -> str:
    if type(value) is not str or not _RFC3339_UTC.fullmatch(value):
        raise MarketMemoryOptionOiStoreError(
            f"actual-output {field} is not exact RFC3339 UTC"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryOptionOiStoreError(
            f"actual-output {field} is not a real timestamp"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        raise MarketMemoryOptionOiStoreError(f"actual-output {field} must be UTC")
    return value


def _sample_first_observed_at(*, available_at: str) -> str:
    source_clock = _exact_utc(available_at, field="source available_at")
    sampled = _utc_now()
    if not isinstance(sampled, datetime) or sampled.tzinfo is None:
        raise MarketMemoryOptionOiCaptureError(
            "option-OI store clock must be timezone-aware"
        )
    observed_at = sampled.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    source_time = datetime.fromisoformat(source_clock.replace("Z", "+00:00"))
    observed_time = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed_time < source_time:
        raise MarketMemoryOptionOiCaptureError(
            "option-OI store clock predates response-body completion"
        )
    return observed_at


def _require_digest(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise MarketMemoryOptionOiStoreError(
            f"actual-output {field} is not lowercase SHA-256"
        )
    return value


def _require_int(value: object, *, field: str, minimum: int = 1, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MarketMemoryOptionOiStoreError(
            f"actual-output {field} is outside its integer bound"
        )
    return value


def validate_option_oi_store_root(
    root: str | Path, *, repository_root: str | Path | None = None
) -> Path:
    """Require the dedicated private ``options-v1`` root and reject public roots."""

    unresolved = Path(root).expanduser()
    absolute_unresolved = Path(os.path.abspath(os.fspath(unresolved)))
    cursor = absolute_unresolved
    while True:
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise MarketMemoryOptionOiStoreError(
                "actual-output store path components cannot be inspected"
            ) from exc
        else:
            if stat.S_ISLNK(metadata.st_mode):
                raise MarketMemoryOptionOiStoreError(
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
        raise MarketMemoryOptionOiStoreError(str(exc)) from exc
    if repository_root is not None:
        repository = Path(repository_root).expanduser().resolve()
        if candidate == repository or repository in candidate.parents:
            raise MarketMemoryOptionOiStoreError(
                "actual-output store cannot use the repository or its descendants"
            )
    forbidden_base = Path("/var/lib/macro-market-memory").resolve(strict=False)
    if candidate == forbidden_base or forbidden_base in candidate.parents:
        raise MarketMemoryOptionOiStoreError(
            "option-OI storage must remain outside the canonical Market Memory tree"
        )
    canonical_base = Path("/var/lib/macro-market-memory-options").resolve(strict=False)
    if candidate == canonical_base or canonical_base in candidate.parents:
        canonical_profile = canonical_base / "options-v1"
        if candidate != canonical_profile:
            raise MarketMemoryOptionOiStoreError(
                "canonical option-OI storage permits only options-v1"
            )
    if candidate.name != "options-v1":
        raise MarketMemoryOptionOiStoreError(
            "actual-output store root must be the dedicated options-v1 directory"
        )
    if "public" in candidate.parts or any(
        part in {"trusted-v1", "w1a-v1"} for part in candidate.parts
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output store cannot use a public or trusted serving tree"
        )
    if candidate.exists():
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise MarketMemoryOptionOiStoreError(
                "actual-output store root cannot be inspected"
            ) from exc
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise MarketMemoryOptionOiStoreError(
                "actual-output store root must be a real directory"
            )
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise MarketMemoryOptionOiStoreError(
                "actual-output store root must not grant group or world access"
            )
    return candidate


def default_option_oi_store_root(repository_root: str | Path) -> Path:
    """Return the profile-owned production root (or isolated local analogue)."""

    repository = Path(repository_root).expanduser().resolve()
    override = os.environ.get("MARKET_MEMORY_OPTION_OI_STORE_DIR", "").strip()
    if override:
        candidate = Path(override).expanduser()
    elif repository == Path("/opt/macro"):
        candidate = Path("/var/lib/macro-market-memory-options/options-v1")
    else:
        candidate = (
            Path.home()
            / ".local"
            / "state"
            / "macro-market-memory"
            / _digest(os.fsencode(repository))[:16]
            / "options-v1"
        )
    return validate_option_oi_store_root(candidate, repository_root=repository)


def _safe_path(root: Path, *parts: str) -> Path:
    try:
        return market_memory_pit._safe_store_path(root, *parts)
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryOptionOiStoreError(str(exc)) from exc


def _manifest_path(root: Path) -> Path:
    return _safe_path(root, "store_manifest.json")


def _head_path(root: Path) -> Path:
    return _safe_path(root, "HEAD.json")


def _prepared_path(root: Path, prepared_id: str) -> Path:
    if type(prepared_id) is not str or not _PREPARED_ID.fullmatch(prepared_id):
        raise MarketMemoryOptionOiStoreError("prepared_id is malformed")
    digest = prepared_id.removeprefix("mmoptionoiprepared_")
    return _safe_path(root, "prepared", digest[:2], f"{prepared_id}.json")


def _prepared_scratch_root(root: Path) -> Path:
    return _safe_path(root, "scratch", "prepared")


def _source_body_path(root: Path, digest: str) -> Path:
    _require_digest(digest, field="source body digest")
    return _safe_path(root, "source_bodies", digest[:2], f"{digest}.bin")


def _source_object_path(root: Path, source_observation_id: str) -> Path:
    if type(source_observation_id) is not str or not _SOURCE_ID.fullmatch(
        source_observation_id
    ):
        raise MarketMemoryOptionOiStoreError("source_observation_id is malformed")
    digest = source_observation_id.removeprefix("mmoptionoisrc_")
    return _safe_path(
        root,
        "source_observations",
        digest[:2],
        f"{source_observation_id}.json",
    )


def _probe_receipt_path(root: Path, probe_receipt_id: str) -> Path:
    if type(probe_receipt_id) is not str or not _PROBE_ID.fullmatch(probe_receipt_id):
        raise MarketMemoryOptionOiStoreError("probe_receipt_id is malformed")
    digest = probe_receipt_id.removeprefix("mmoptionoiprobe_")
    return _safe_path(
        root,
        "probe_receipts",
        digest[:2],
        f"{probe_receipt_id}.json",
    )


def _capture_path(root: Path, capture_id: str) -> Path:
    if type(capture_id) is not str or not _CAPTURE_ID.fullmatch(capture_id):
        raise MarketMemoryOptionOiStoreError("capture_id is malformed")
    digest = capture_id.removeprefix("mmoptionoicapture_")
    return _safe_path(root, "capture_receipts", digest[:2], f"{capture_id}.json")


def _generation_path(root: Path, generation_id: str) -> Path:
    if type(generation_id) is not str or not _GENERATION_ID.fullmatch(generation_id):
        raise MarketMemoryOptionOiStoreError("generation_id is malformed")
    digest = generation_id.removeprefix("mmoptionoigeneration_")
    return _safe_path(root, "generations", digest[:2], f"{generation_id}.json")


def _object_key(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:  # pragma: no cover - paths are built above
        raise MarketMemoryOptionOiStoreError(
            "actual-output object key escaped its store"
        ) from exc


def _mkdir(path: Path) -> None:
    try:
        market_memory_pit._mkdir_durable(path)
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryOptionOiStoreError(str(exc)) from exc


def _write_json_create_once(
    root: Path, path: Path, body: bytes, *, label: str, limit: int
) -> bool:
    if type(body) is not bytes or not body or len(body) > limit:
        raise MarketMemoryOptionOiCaptureError(
            f"{label} is empty or exceeds its byte bound"
        )
    try:
        written = market_memory_pit._write_create_once(root, path, body, label=label)
    except market_memory_pit.MarketMemoryCaptureError as exc:
        raise MarketMemoryOptionOiCaptureError(str(exc)) from exc
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryOptionOiStoreError(str(exc)) from exc
    return written


def _read_json(path: Path, *, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        return market_memory_pit._read_canonical_object(path, limit=limit, label=label)
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise MarketMemoryOptionOiStoreError(str(exc)) from exc


def _clean_prepared_scratch(root: Path) -> None:
    """Remove only bounded, exact-name prepared temporaries from private scratch."""

    scratch = _prepared_scratch_root(root)
    scratch_parent = scratch.parent
    if scratch_parent.exists() or scratch_parent.is_symlink():
        try:
            parent_metadata = scratch_parent.lstat()
        except OSError as exc:
            raise MarketMemoryOptionOiStoreError(
                "option-OI scratch parent cannot be inspected"
            ) from exc
        if (
            stat.S_ISLNK(parent_metadata.st_mode)
            or not stat.S_ISDIR(parent_metadata.st_mode)
            or stat.S_IMODE(parent_metadata.st_mode) & 0o077
        ):
            raise MarketMemoryOptionOiStoreError("option-OI scratch parent is unsafe")
    if not scratch.exists() and not scratch.is_symlink():
        return
    try:
        metadata = scratch.lstat()
    except OSError as exc:
        raise MarketMemoryOptionOiStoreError(
            "option-OI prepared scratch cannot be inspected"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise MarketMemoryOptionOiStoreError("option-OI prepared scratch is unsafe")
    children: list[Path] = []
    try:
        for path in scratch.iterdir():
            if len(children) >= _MAX_PREPARED_SCRATCH_FILES:
                raise MarketMemoryOptionOiStoreError(
                    "option-OI prepared scratch exceeds its bound"
                )
            children.append(path)
    except MarketMemoryOptionOiStoreError:
        raise
    except OSError as exc:
        raise MarketMemoryOptionOiStoreError(
            "option-OI prepared scratch cannot be enumerated"
        ) from exc
    children.sort(key=lambda path: path.name)
    for path in children:
        try:
            child_metadata = path.lstat()
        except OSError as exc:
            raise MarketMemoryOptionOiStoreError(
                "option-OI prepared scratch entry cannot be inspected"
            ) from exc
        if (
            _PREPARED_SCRATCH_FILE.fullmatch(path.name) is None
            or stat.S_ISLNK(child_metadata.st_mode)
            or not stat.S_ISREG(child_metadata.st_mode)
            or stat.S_IMODE(child_metadata.st_mode) & 0o077
        ):
            raise MarketMemoryOptionOiStoreError(
                "option-OI prepared scratch entry is noncanonical"
            )
        try:
            path.unlink()
        except OSError as exc:
            raise MarketMemoryOptionOiStoreError(
                "option-OI prepared scratch entry cannot be removed"
            ) from exc
    try:
        market_memory_pit._directory_fsync(scratch)
    except OSError as exc:
        raise MarketMemoryOptionOiStoreError(
            "option-OI prepared scratch cleanup cannot be fsynced"
        ) from exc


def _write_prepared_create_once(root: Path, path: Path, body: bytes) -> bool:
    """Link one prepared record from isolated scratch, never from its scan tree."""

    if type(body) is not bytes or not body or len(body) > _MAX_PREPARED_BYTES:
        raise MarketMemoryOptionOiCaptureError(
            "actual-output prepared record is empty or exceeds its byte bound"
        )
    try:
        path.parent.relative_to(root)
    except ValueError as exc:
        raise MarketMemoryOptionOiStoreError(
            "prepared write escaped the option-OI root"
        ) from exc
    _mkdir(path.parent)
    _clean_prepared_scratch(root)
    scratch = _prepared_scratch_root(root)
    _mkdir(scratch)
    if path.exists() or path.is_symlink():
        _payload, existing = _read_json(
            path,
            limit=_MAX_PREPARED_BYTES,
            label="existing actual-output prepared record",
        )
        if existing != body:
            raise MarketMemoryOptionOiCaptureError(
                "immutable actual-output prepared record collision"
            )
        return False

    temporary = scratch / f".{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    if _PREPARED_SCRATCH_FILE.fullmatch(temporary.name) is None:
        raise MarketMemoryOptionOiStoreError(
            "prepared scratch filename is not canonical"
        )
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
            _payload, existing = _read_json(
                path,
                limit=_MAX_PREPARED_BYTES,
                label="raced actual-output prepared record",
            )
            if existing != body:
                raise MarketMemoryOptionOiCaptureError(
                    "immutable actual-output prepared record collision"
                ) from None
            return False
    except (MarketMemoryOptionOiStoreError, MarketMemoryOptionOiCaptureError):
        raise
    except OSError as exc:
        raise MarketMemoryOptionOiStoreError(
            "cannot publish immutable actual-output prepared record"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
            market_memory_pit._directory_fsync(scratch)
        except OSError as exc:
            raise MarketMemoryOptionOiStoreError(
                "prepared scratch cleanup cannot be completed"
            ) from exc


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
        raise MarketMemoryOptionOiStoreError(
            f"{label} cannot be opened safely"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MarketMemoryOptionOiStoreError(f"{label} is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > limit:
            raise MarketMemoryOptionOiStoreError(f"{label} exceeds its safe size bound")
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
        raise MarketMemoryOptionOiStoreError(f"{label} cannot be read") from exc
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
        raise MarketMemoryOptionOiStoreError(
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
        raise MarketMemoryOptionOiCaptureError(
            f"{label} is empty, oversized, or does not match its digest"
        )
    try:
        path.parent.relative_to(root)
    except ValueError as exc:
        raise MarketMemoryOptionOiStoreError(
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
            raise MarketMemoryOptionOiCaptureError(f"immutable {label} collision")
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
                raise MarketMemoryOptionOiCaptureError(
                    f"immutable {label} collision"
                ) from None
            return False
    except (MarketMemoryOptionOiStoreError, MarketMemoryOptionOiCaptureError):
        raise
    except OSError as exc:
        raise MarketMemoryOptionOiStoreError(
            f"cannot publish immutable {label}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _replace_head(root: Path, head: Mapping[str, Any]) -> None:
    body = _canonical_bytes(head)
    if len(body) > _MAX_HEAD_BYTES:
        raise MarketMemoryOptionOiStoreError(
            "actual-output HEAD exceeds its safe size bound"
        )
    path = _head_path(root)
    if path.is_symlink():
        raise MarketMemoryOptionOiStoreError("actual-output HEAD cannot be a symlink")
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
        raise MarketMemoryOptionOiStoreError(
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
        "probe_receipt_schema": _PROBE_RECEIPT_SCHEMA_V1,
        "generation_schema": GENERATION_SCHEMA,
        "head_schema": HEAD_SCHEMA,
        "mode": "private_future_only_source_availability",
        "evidence_policy": dict(_EVIDENCE_POLICY_V1),
        "authority": dict(_AUTHORITY_V1),
    }
    manifest["store_id"] = _content_id("mmoptionoistore_", manifest, field="store_id")
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
        "probe_receipt_schema",
        "generation_schema",
        "head_schema",
        "mode",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryOptionOiStoreError(
            "actual-output store manifest fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    expected = {
        "schema": STORE_SCHEMA,
        "profile": STORE_PROFILE,
        "prepared_schema": PREPARED_SCHEMA,
        "capture_receipt_schema": CAPTURE_RECEIPT_SCHEMA,
        "source_observation_schema": _SOURCE_OBSERVATION_SCHEMA_V1,
        "probe_receipt_schema": _PROBE_RECEIPT_SCHEMA_V1,
        "generation_schema": GENERATION_SCHEMA,
        "head_schema": HEAD_SCHEMA,
        "mode": "private_future_only_source_availability",
        "evidence_policy": dict(_EVIDENCE_POLICY_V1),
        "authority": dict(_AUTHORITY_V1),
    }
    for field, wanted in expected.items():
        if not _json_type_strict_equal(clean.get(field), wanted):
            raise MarketMemoryOptionOiStoreError(f"actual-output store {field} drift")
    if type(clean.get("nonce")) is not str or not re.fullmatch(
        r"[a-f0-9]{32}", clean["nonce"]
    ):
        raise MarketMemoryOptionOiStoreError("actual-output store nonce is malformed")
    store_id = clean.get("store_id")
    if type(store_id) is not str or not _STORE_ID.fullmatch(store_id):
        raise MarketMemoryOptionOiStoreError("actual-output store_id is malformed")
    if _content_id("mmoptionoistore_", clean, field="store_id") != store_id:
        raise MarketMemoryOptionOiStoreError(
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
                row["first_observed_at"],
                row["available_at"],
                row["capture_id"],
            ),
        ),
    }
    generation["generation_id"] = _content_id(
        "mmoptionoigeneration_", generation, field="generation_id"
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
        raise MarketMemoryOptionOiStoreError(
            "actual-output generation fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != GENERATION_SCHEMA or clean.get("store_id") != store_id:
        raise MarketMemoryOptionOiStoreError(
            "actual-output generation schema or store mismatch"
        )
    generation_id = clean.get("generation_id")
    if type(generation_id) is not str or not _GENERATION_ID.fullmatch(generation_id):
        raise MarketMemoryOptionOiStoreError("actual-output generation_id is malformed")
    previous = clean.get("previous_generation_id")
    if previous is not None and (
        type(previous) is not str or not _GENERATION_ID.fullmatch(previous)
    ):
        raise MarketMemoryOptionOiStoreError(
            "previous actual-output generation_id is malformed"
        )
    captures = clean.get("captures")
    if not isinstance(captures, list) or len(captures) > _MAX_GENERATION_CAPTURES:
        raise MarketMemoryOptionOiStoreError(
            "actual-output generation exceeds its capture bound"
        )
    entry_fields = {
        "capture_id",
        "source_observation_id",
        "probe_receipt_id",
        "available_at",
        "first_observed_at",
        "receipt_sha256",
    }
    sort_keys: list[tuple[str, str, str]] = []
    capture_ids: list[str] = []
    source_ids: list[str] = []
    probe_ids: list[str] = []
    for entry in captures:
        if not isinstance(entry, Mapping) or set(entry) != entry_fields:
            raise MarketMemoryOptionOiStoreError(
                "actual-output generation entry is not canonical"
            )
        if type(entry.get("capture_id")) is not str or not _CAPTURE_ID.fullmatch(
            entry["capture_id"]
        ):
            raise MarketMemoryOptionOiStoreError(
                "actual-output generation capture_id is malformed"
            )
        if type(
            entry.get("source_observation_id")
        ) is not str or not _SOURCE_ID.fullmatch(entry["source_observation_id"]):
            raise MarketMemoryOptionOiStoreError(
                "actual-output generation source ID is malformed"
            )
        if type(entry.get("probe_receipt_id")) is not str or not _PROBE_ID.fullmatch(
            entry["probe_receipt_id"]
        ):
            raise MarketMemoryOptionOiStoreError(
                "actual-output generation probe ID is malformed"
            )
        _exact_utc(entry.get("available_at"), field="available_at")
        _exact_utc(entry.get("first_observed_at"), field="first_observed_at")
        if datetime.fromisoformat(
            entry["first_observed_at"].replace("Z", "+00:00")
        ) < datetime.fromisoformat(entry["available_at"].replace("Z", "+00:00")):
            raise MarketMemoryOptionOiStoreError(
                "actual-output generation observation predates availability"
            )
        _require_digest(entry.get("receipt_sha256"), field="receipt digest")
        sort_keys.append(
            (
                entry["first_observed_at"],
                entry["available_at"],
                entry["capture_id"],
            )
        )
        capture_ids.append(entry["capture_id"])
        source_ids.append(entry["source_observation_id"])
        probe_ids.append(entry["probe_receipt_id"])
    if sort_keys != sorted(sort_keys) or len(capture_ids) != len(set(capture_ids)):
        raise MarketMemoryOptionOiStoreError(
            "actual-output generation capture index is not canonical"
        )
    if len(source_ids) != len(set(source_ids)) or len(probe_ids) != len(set(probe_ids)):
        raise MarketMemoryOptionOiStoreError(
            "actual-output generation observation index is ambiguous"
        )
    if (
        _content_id("mmoptionoigeneration_", clean, field="generation_id")
        != generation_id
    ):
        raise MarketMemoryOptionOiStoreError(
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
        raise MarketMemoryOptionOiStoreError(
            "actual-output HEAD fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != HEAD_SCHEMA or clean.get("store_id") != store_id:
        raise MarketMemoryOptionOiStoreError(
            "actual-output HEAD schema or store mismatch"
        )
    if type(clean.get("generation_id")) is not str or not _GENERATION_ID.fullmatch(
        clean["generation_id"]
    ):
        raise MarketMemoryOptionOiStoreError(
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
        "probe_receipts",
        "capture_receipts",
    )
    if not (manifest_path.exists() or manifest_path.is_symlink()):
        for name in ("generations", *immutable_roots):
            path = _safe_path(root, name)
            if path.exists() or path.is_symlink():
                raise MarketMemoryOptionOiStoreError(
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
                raise MarketMemoryOptionOiStoreError(
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
        raise MarketMemoryOptionOiStoreError(
            "actual-output HEAD generation digest mismatch"
        )
    generation = _validate_generation(generation_raw, store_id=manifest["store_id"])
    if generation["generation_id"] != head["generation_id"]:
        raise MarketMemoryOptionOiStoreError(
            "actual-output HEAD generation identity mismatch"
        )
    return _StoreState(manifest, head, generation)


def _source_refs(
    root: Path, bundle: option_oi.OptionOiObservationBundle
) -> dict[str, dict[str, Any]]:
    response = bundle.probe_receipt["response"]["entity_body"]
    response_path = _source_body_path(root, response["sha256"])
    refs: dict[str, dict[str, Any]] = {
        "option_oi_response_body": {
            "source_kind": "remote_response_entity",
            "url": option_oi.SOURCE_URL,
            "sha256": response["sha256"],
            "bytes": response["bytes"],
            "object_key": _object_key(response_path, root=root),
        }
    }
    artifacts = bundle.source_observation["git_sources"]
    for role in ("option_oi_source_config", "massive_entitlement_record"):
        artifact = artifacts[role]
        path = _source_body_path(root, artifact["sha256"])
        refs[role] = {
            "source_kind": "git_blob",
            "repo_path": artifact["repo_path"],
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
            "git_blob_oid": artifact["git_blob_oid"],
            "object_key": _object_key(path, root=root),
        }
    return refs


def _bundle_source_bodies(
    bundle: option_oi.OptionOiObservationBundle,
) -> dict[str, bytes]:
    return {
        "option_oi_response_body": bundle.pinned_inputs.fetched_response.body,
        "option_oi_source_config": (
            bundle.pinned_inputs.pinned_sources.source_config_body
        ),
        "massive_entitlement_record": (
            bundle.pinned_inputs.pinned_sources.license_record_body
        ),
    }


def _persist_bundle_cas(
    root: Path,
    bundle: option_oi.OptionOiObservationBundle,
) -> None:
    """Durably publish every exact recovery object before a clock is claimed."""

    bodies = _bundle_source_bodies(bundle)
    refs = _source_refs(root, bundle)
    for role in _SOURCE_ROLES:
        ref = refs[role]
        _write_raw_create_once(
            root,
            _source_body_path(root, ref["sha256"]),
            bodies[role],
            digest=ref["sha256"],
            label=f"{role} source body",
            limit=_SOURCE_LIMITS[role],
        )
    source_id = bundle.source_observation["source_observation_id"]
    _write_json_create_once(
        root,
        _source_object_path(root, source_id),
        bundle.source_observation_bytes,
        label="option_oi source observation",
        limit=_MAX_SOURCE_OBJECT_BYTES,
    )
    probe_id = bundle.probe_receipt["probe_receipt_id"]
    _write_json_create_once(
        root,
        _probe_receipt_path(root, probe_id),
        bundle.probe_receipt_bytes,
        label="option-OI probe receipt",
        limit=_MAX_PROBE_RECEIPT_BYTES,
    )


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


def _prepared_id(bundle: option_oi.OptionOiObservationBundle) -> str:
    core = {
        "profile": STORE_PROFILE,
        "source_observation_id": bundle.source_observation["source_observation_id"],
        "probe_receipt_id": bundle.probe_receipt["probe_receipt_id"],
        "available_at": bundle.source_observation["available_at"],
    }
    return "mmoptionoiprepared_" + _digest(_canonical_bytes(core))


def _new_prepared(
    root: Path,
    bundle: option_oi.OptionOiObservationBundle,
    *,
    first_observed_at: str,
) -> dict[str, Any]:
    prepared_id = _prepared_id(bundle)
    source_id = bundle.source_observation["source_observation_id"]
    probe_id = bundle.probe_receipt["probe_receipt_id"]
    available_at = _exact_utc(
        bundle.source_observation["available_at"], field="available_at"
    )
    observed_at = _exact_utc(first_observed_at, field="first_observed_at")
    if datetime.fromisoformat(
        observed_at.replace("Z", "+00:00")
    ) < datetime.fromisoformat(available_at.replace("Z", "+00:00")):
        raise MarketMemoryOptionOiCaptureError(
            "first_observed_at predates source availability"
        )
    return {
        "schema": PREPARED_SCHEMA,
        "prepared_id": prepared_id,
        "profile": STORE_PROFILE,
        "source_commit": bundle.pinned_inputs.pinned_sources.pinned_commit,
        "source_observation_id": source_id,
        "probe_receipt_id": probe_id,
        "source_bodies": _source_refs(root, bundle),
        "source_observation": _object_ref(
            root,
            object_id=source_id,
            body=bundle.source_observation_bytes,
            path=_source_object_path(root, source_id),
            schema=_SOURCE_OBSERVATION_SCHEMA_V1,
            id_field="source_observation_id",
        ),
        "probe_receipt": _object_ref(
            root,
            object_id=probe_id,
            body=bundle.probe_receipt_bytes,
            path=_probe_receipt_path(root, probe_id),
            schema=_PROBE_RECEIPT_SCHEMA_V1,
            id_field="probe_receipt_id",
        ),
        "available_at": available_at,
        "first_observed_at": observed_at,
        "evidence_policy": dict(_EVIDENCE_POLICY_V1),
        "authority": dict(_AUTHORITY_V1),
    }


def _validate_source_refs(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != set(_SOURCE_ROLES):
        raise MarketMemoryOptionOiStoreError(
            "actual-output source body roles are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    expected_paths = {
        "option_oi_source_config": "config/market_memory_option_oi_source.v1.json",
        "massive_entitlement_record": "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
    }
    for role in _SOURCE_ROLES:
        ref = clean[role]
        if not isinstance(ref, Mapping):
            raise MarketMemoryOptionOiStoreError(
                f"actual-output {role} reference fields are not canonical"
            )
        digest = _require_digest(ref.get("sha256"), field=f"{role} digest")
        _require_int(
            ref.get("bytes"), field=f"{role} bytes", maximum=_SOURCE_LIMITS[role]
        )
        if ref.get("object_key") != f"source_bodies/{digest[:2]}/{digest}.bin":
            raise MarketMemoryOptionOiStoreError(
                f"actual-output {role} object key is not canonical"
            )
        if role == "option_oi_response_body":
            if (
                set(ref)
                != {
                    "source_kind",
                    "url",
                    "sha256",
                    "bytes",
                    "object_key",
                }
                or ref.get("source_kind") != "remote_response_entity"
                or ref.get("url") != option_oi.SOURCE_URL
            ):
                raise MarketMemoryOptionOiStoreError(
                    "actual-output response body source reference drift"
                )
            continue
        if (
            set(ref)
            != {
                "source_kind",
                "repo_path",
                "sha256",
                "bytes",
                "git_blob_oid",
                "object_key",
            }
            or ref.get("source_kind") != "git_blob"
        ):
            raise MarketMemoryOptionOiStoreError(
                f"actual-output {role} Git reference fields are not canonical"
            )
        if ref.get("repo_path") != expected_paths[role]:
            raise MarketMemoryOptionOiStoreError(
                f"actual-output {role} repository path drift"
            )
        oid = ref.get("git_blob_oid")
        if type(oid) is not str or not _COMMIT.fullmatch(oid):
            raise MarketMemoryOptionOiStoreError(
                f"actual-output {role} Git blob OID is malformed"
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
        raise MarketMemoryOptionOiStoreError(
            f"actual-output {id_field} reference fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    object_id = clean.get(id_field)
    if type(object_id) is not str or not id_pattern.fullmatch(object_id):
        raise MarketMemoryOptionOiStoreError(
            f"actual-output {id_field} reference is malformed"
        )
    if clean.get("schema") != schema:
        raise MarketMemoryOptionOiStoreError(f"actual-output {id_field} schema drift")
    _require_digest(clean.get("sha256"), field=f"{id_field} digest")
    _require_int(clean.get("bytes"), field=f"{id_field} bytes", maximum=maximum)
    identity_digest = object_id.rsplit("_", 1)[-1]
    if clean.get("object_key") != (
        f"{directory}/{identity_digest[:2]}/{object_id}.json"
    ):
        raise MarketMemoryOptionOiStoreError(
            f"actual-output {id_field} object key is not canonical"
        )
    return clean


def _validate_prepared(
    value: Mapping[str, Any],
    *,
    expected_bundle: option_oi.OptionOiObservationBundle | None = None,
) -> dict[str, Any]:
    fields = {
        "schema",
        "prepared_id",
        "profile",
        "source_commit",
        "source_observation_id",
        "probe_receipt_id",
        "source_bodies",
        "source_observation",
        "probe_receipt",
        "available_at",
        "first_observed_at",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared record fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != PREPARED_SCHEMA or clean.get("profile") != STORE_PROFILE:
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared schema or profile drift"
        )
    if type(clean.get("source_commit")) is not str or not _COMMIT.fullmatch(
        clean["source_commit"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared source commit is malformed"
        )
    if type(clean.get("source_observation_id")) is not str or not _SOURCE_ID.fullmatch(
        clean["source_observation_id"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared source ID is malformed"
        )
    if type(clean.get("probe_receipt_id")) is not str or not _PROBE_ID.fullmatch(
        clean["probe_receipt_id"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared probe ID is malformed"
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
    probe_ref = _validate_object_ref(
        clean.get("probe_receipt"),
        id_field="probe_receipt_id",
        id_pattern=_PROBE_ID,
        schema=_PROBE_RECEIPT_SCHEMA_V1,
        directory="probe_receipts",
        maximum=_MAX_PROBE_RECEIPT_BYTES,
    )
    if (
        source_ref["source_observation_id"] != clean["source_observation_id"]
        or probe_ref["probe_receipt_id"] != clean["probe_receipt_id"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared object identities disagree"
        )
    available = _exact_utc(clean.get("available_at"), field="prepared available_at")
    observed = _exact_utc(
        clean.get("first_observed_at"), field="prepared first_observed_at"
    )
    if datetime.fromisoformat(observed.replace("Z", "+00:00")) < datetime.fromisoformat(
        available.replace("Z", "+00:00")
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared observation predates availability"
        )
    if not _json_type_strict_equal(clean.get("evidence_policy"), _EVIDENCE_POLICY_V1):
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared evidence policy drift"
        )
    if not _json_type_strict_equal(clean.get("authority"), _AUTHORITY_V1):
        raise MarketMemoryOptionOiStoreError("actual-output prepared authority drift")
    core = {
        "profile": STORE_PROFILE,
        "source_observation_id": clean["source_observation_id"],
        "probe_receipt_id": clean["probe_receipt_id"],
        "available_at": available,
    }
    expected_prepared_id = "mmoptionoiprepared_" + _digest(_canonical_bytes(core))
    if clean.get("prepared_id") != expected_prepared_id:
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared identity does not bind its core"
        )
    if expected_bundle is not None:
        expected = _new_prepared(
            Path("/unused/options-v1"),
            expected_bundle,
            first_observed_at=observed,
        )
        # The first source commit is provenance, not semantic identity.  A
        # code-only commit with the same two Git blobs remains idempotent.
        expected["source_commit"] = clean["source_commit"]
        if clean != expected:
            raise MarketMemoryOptionOiCaptureError(
                "existing prepared record differs from the validated bundle"
            )
    clean["source_bodies"] = sources
    clean["source_observation"] = source_ref
    clean["probe_receipt"] = probe_ref
    return clean


def _load_or_create_prepared(
    root: Path,
    bundle: option_oi.OptionOiObservationBundle,
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
        raise MarketMemoryOptionOiStoreError(
            "option-OI prepared record disappeared under the writer lock"
        )
    # Detached validation bound response-body completion and the
    # complete recovery CAS is already durable.  This record is therefore the
    # first claimed clock and can always be resumed without a refetch.
    prepared = _new_prepared(
        root,
        bundle,
        first_observed_at=attempt_observed_at,
    )
    body = _canonical_bytes(prepared)
    _write_prepared_create_once(root, path, body)
    return _validate_prepared(prepared, expected_bundle=bundle)


def _load_bundle_from_prepared(
    root: Path,
    prepared: Mapping[str, Any],
) -> option_oi.OptionOiObservationBundle:
    """Reconstruct one prepared observation solely from its exact private CAS."""

    clean = _validate_prepared(prepared)
    bodies: dict[str, bytes] = {}
    for role in _SOURCE_ROLES:
        ref = clean["source_bodies"][role]
        path = _source_body_path(root, ref["sha256"])
        if _object_key(path, root=root) != ref["object_key"]:
            raise MarketMemoryOptionOiStoreError(
                f"prepared option-OI {role} path differs from its receipt"
            )
        bodies[role] = _read_raw(
            path,
            digest=ref["sha256"],
            expected_bytes=ref["bytes"],
            limit=_SOURCE_LIMITS[role],
            label=f"prepared stored {role}",
        )

    source_ref = clean["source_observation"]
    source_path = _source_object_path(root, source_ref["source_observation_id"])
    if _object_key(source_path, root=root) != source_ref["object_key"]:
        raise MarketMemoryOptionOiStoreError(
            "prepared source-observation path differs from its receipt"
        )
    source_raw, source_body = _read_json(
        source_path,
        limit=_MAX_SOURCE_OBJECT_BYTES,
        label="prepared option-OI source observation",
    )
    if (
        len(source_body) != source_ref["bytes"]
        or _digest(source_body) != source_ref["sha256"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "prepared source observation differs from its receipt"
        )

    probe_ref = clean["probe_receipt"]
    probe_path = _probe_receipt_path(root, probe_ref["probe_receipt_id"])
    if _object_key(probe_path, root=root) != probe_ref["object_key"]:
        raise MarketMemoryOptionOiStoreError(
            "prepared probe-receipt path differs from its receipt"
        )
    probe_raw, probe_body = _read_json(
        probe_path,
        limit=_MAX_PROBE_RECEIPT_BYTES,
        label="prepared option-OI probe receipt",
    )
    if (
        len(probe_body) != probe_ref["bytes"]
        or _digest(probe_body) != probe_ref["sha256"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "prepared probe receipt differs from its receipt"
        )

    try:
        selected_headers = probe_raw["response"]["selected_headers"]
        if not isinstance(selected_headers, Mapping):
            raise TypeError("selected headers are not an object")
        candidate = option_oi.OptionOiObservationBundle(
            pinned_inputs=option_oi.PinnedOptionOiInputs(
                fetched_response=option_oi.FetchedOptionOiResponse(
                    status=200,
                    url=option_oi.SOURCE_URL,
                    selected_headers=tuple(
                        (name, selected_headers[name])
                        for name in ("content-type", "content-length")
                        if name in selected_headers
                    ),
                    body=bodies["option_oi_response_body"],
                    response_body_completed_at=clean["available_at"],
                ),
                pinned_sources=option_oi.PinnedOptionOiSources(
                    pinned_commit=clean["source_commit"],
                    source_config_body=bodies["option_oi_source_config"],
                    license_record_body=bodies["massive_entitlement_record"],
                    git_blob_oids=tuple(
                        (role, clean["source_bodies"][role]["git_blob_oid"])
                        for role in (
                            "option_oi_source_config",
                            "massive_entitlement_record",
                        )
                    ),
                ),
            ),
            probe_receipt=probe_raw,
            probe_receipt_bytes=probe_body,
            source_observation=source_raw,
            source_observation_bytes=source_body,
        )
    except (KeyError, TypeError) as exc:
        raise MarketMemoryOptionOiStoreError(
            "prepared option-OI CAS cannot reconstruct its frozen bundle"
        ) from exc
    try:
        checked = option_oi.validate_option_oi_observation_bundle(candidate)
    except option_oi.MarketMemoryOptionOiObservationError as exc:
        raise MarketMemoryOptionOiStoreError(
            "prepared option-OI CAS fails detached reprojection"
        ) from exc
    _validate_prepared(clean, expected_bundle=checked)
    return checked


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
        "source_commit": prepared["source_commit"],
        "source_bodies": copy.deepcopy(prepared["source_bodies"]),
        "source_observation": copy.deepcopy(prepared["source_observation"]),
        "probe_receipt": copy.deepcopy(prepared["probe_receipt"]),
        "clocks": {
            "response_body_completed_at": prepared["available_at"],
            "available_at": prepared["available_at"],
            "first_observed_at": prepared["first_observed_at"],
        },
        "completeness": dict(_COMPLETENESS_V1),
        "mode": "private_future_only_source_availability",
        "source_availability_capture": True,
        "evidence_policy": dict(_EVIDENCE_POLICY_V1),
        "authority": dict(_AUTHORITY_V1),
    }
    receipt["capture_id"] = _content_id(
        "mmoptionoicapture_", receipt, field="capture_id"
    )
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
        "source_commit",
        "source_bodies",
        "source_observation",
        "probe_receipt",
        "clocks",
        "completeness",
        "mode",
        "source_availability_capture",
        "evidence_policy",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketMemoryOptionOiStoreError(
            "actual-output capture receipt fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if (
        clean.get("schema") != CAPTURE_RECEIPT_SCHEMA
        or clean.get("profile") != STORE_PROFILE
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output capture schema or profile drift"
        )
    receipt_store = clean.get("store_id")
    if type(receipt_store) is not str or not _STORE_ID.fullmatch(receipt_store):
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt store_id is malformed"
        )
    if store_id is not None and receipt_store != store_id:
        raise MarketMemoryOptionOiStoreError(
            "actual-output capture belongs to another store"
        )
    if type(clean.get("prepared_id")) is not str or not _PREPARED_ID.fullmatch(
        clean["prepared_id"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt prepared_id is malformed"
        )
    prepared_digest = clean["prepared_id"].removeprefix("mmoptionoiprepared_")
    if clean.get("prepared_object_key") != (
        f"prepared/{prepared_digest[:2]}/{clean['prepared_id']}.json"
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt prepared key is not canonical"
        )
    if type(clean.get("source_commit")) is not str or not _COMMIT.fullmatch(
        clean["source_commit"]
    ):
        raise MarketMemoryOptionOiStoreError(
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
    probe_ref = _validate_object_ref(
        clean.get("probe_receipt"),
        id_field="probe_receipt_id",
        id_pattern=_PROBE_ID,
        schema=_PROBE_RECEIPT_SCHEMA_V1,
        directory="probe_receipts",
        maximum=_MAX_PROBE_RECEIPT_BYTES,
    )
    clocks = clean.get("clocks")
    if not isinstance(clocks, Mapping) or set(clocks) != {
        "response_body_completed_at",
        "available_at",
        "first_observed_at",
    }:
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt clocks are not canonical"
        )
    completed = _exact_utc(
        clocks.get("response_body_completed_at"),
        field="receipt response_body_completed_at",
    )
    available = _exact_utc(clocks.get("available_at"), field="receipt available_at")
    observed = _exact_utc(
        clocks.get("first_observed_at"), field="receipt first_observed_at"
    )
    if completed != available:
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt availability clocks disagree"
        )
    if datetime.fromisoformat(observed.replace("Z", "+00:00")) < datetime.fromisoformat(
        available.replace("Z", "+00:00")
    ):
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt observation predates availability"
        )
    if not _json_type_strict_equal(clean.get("completeness"), _COMPLETENESS_V1):
        raise MarketMemoryOptionOiStoreError("actual-output receipt completeness drift")
    if clean.get("mode") != "private_future_only_source_availability":
        raise MarketMemoryOptionOiStoreError("actual-output receipt mode drift")
    if clean.get("source_availability_capture") is not True:
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt must assert its source-availability capture"
        )
    if not _json_type_strict_equal(clean.get("evidence_policy"), _EVIDENCE_POLICY_V1):
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt evidence policy drift"
        )
    if not _json_type_strict_equal(clean.get("authority"), _AUTHORITY_V1):
        raise MarketMemoryOptionOiStoreError("actual-output receipt authority drift")
    capture_id = clean.get("capture_id")
    if type(capture_id) is not str or not _CAPTURE_ID.fullmatch(capture_id):
        raise MarketMemoryOptionOiStoreError("actual-output capture_id is malformed")
    if _content_id("mmoptionoicapture_", clean, field="capture_id") != capture_id:
        raise MarketMemoryOptionOiStoreError(
            "actual-output capture_id does not bind its receipt"
        )
    clean["source_bodies"] = sources
    clean["source_observation"] = source_ref
    clean["probe_receipt"] = probe_ref
    clean["clocks"] = dict(clocks)
    clean["completeness"] = dict(_COMPLETENESS_V1)
    return clean


def _generation_entry(receipt: Mapping[str, Any], *, body: bytes) -> dict[str, Any]:
    return {
        "capture_id": receipt["capture_id"],
        "source_observation_id": receipt["source_observation"]["source_observation_id"],
        "probe_receipt_id": receipt["probe_receipt"]["probe_receipt_id"],
        "available_at": receipt["clocks"]["available_at"],
        "first_observed_at": receipt["clocks"]["first_observed_at"],
        "receipt_sha256": _digest(body),
    }


def _publish_prepared_capture(
    root: Path,
    *,
    state: _StoreState,
    prepared: Mapping[str, Any],
    bundle: option_oi.OptionOiObservationBundle,
) -> tuple[_StoreState, str]:
    """Publish one fully recoverable prepared capture and advance HEAD last."""

    clean_prepared = _validate_prepared(prepared, expected_bundle=bundle)
    durable_raw, _ = _read_json(
        _prepared_path(root, clean_prepared["prepared_id"]),
        limit=_MAX_PREPARED_BYTES,
        label="durable option-OI prepared record",
    )
    durable_prepared = _validate_prepared(durable_raw, expected_bundle=bundle)
    if durable_prepared != clean_prepared:
        raise MarketMemoryOptionOiStoreError(
            "durable option-OI prepared record changed before publication"
        )

    source_id = bundle.source_observation["source_observation_id"]
    probe_id = bundle.probe_receipt["probe_receipt_id"]
    matching = [
        dict(entry)
        for entry in state.generation["captures"]
        if entry["source_observation_id"] == source_id
        or entry["probe_receipt_id"] == probe_id
    ]
    if matching:
        raise MarketMemoryOptionOiStoreError(
            "option-OI prepared publication collides with an active observation"
        )

    # Normal and restart-resume publication share this exact CAS verification.
    # It is idempotent and never samples a clock.
    _persist_bundle_cas(root, bundle)
    receipt = _build_receipt(
        root,
        store_id=state.manifest["store_id"],
        prepared=durable_prepared,
    )
    receipt = _validate_receipt(receipt, store_id=state.manifest["store_id"])
    receipt_body = _canonical_bytes(receipt)
    if len(receipt_body) > _MAX_RECEIPT_BYTES:
        raise MarketMemoryOptionOiCaptureError(
            "actual-output capture receipt exceeds its byte bound"
        )
    if len(state.generation["captures"]) >= _MAX_GENERATION_CAPTURES:
        raise MarketMemoryOptionOiCaptureError(
            "actual-output generation reached its pilot capture bound"
        )
    generation = _new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=state.generation["generation_id"],
        captures=[
            *[dict(item) for item in state.generation["captures"]],
            _generation_entry(receipt, body=receipt_body),
        ],
    )
    generation_body = _canonical_bytes(generation)
    if len(generation_body) > _MAX_GENERATION_BYTES:
        raise MarketMemoryOptionOiCaptureError(
            "actual-output generation exceeds its byte bound"
        )

    _write_json_create_once(
        root,
        _capture_path(root, receipt["capture_id"]),
        receipt_body,
        label="actual-output capture receipt",
        limit=_MAX_RECEIPT_BYTES,
    )
    _write_json_create_once(
        root,
        _generation_path(root, generation["generation_id"]),
        generation_body,
        label="actual-output generation",
        limit=_MAX_GENERATION_BYTES,
    )
    head = _new_head(generation, body=generation_body)
    _replace_head(root, head)
    return _StoreState(state.manifest, head, generation), receipt["capture_id"]


def _scan_prepared_records(root: Path) -> list[dict[str, Any]]:
    """Strictly enumerate the bounded canonical prepared-record tree."""

    prepared_root = _safe_path(root, "prepared")
    if not prepared_root.exists() and not prepared_root.is_symlink():
        return []
    try:
        root_metadata = prepared_root.lstat()
        prefixes = sorted(prepared_root.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise MarketMemoryOptionOiStoreError(
            "option-OI prepared tree cannot be inspected"
        ) from exc
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_IMODE(root_metadata.st_mode) & 0o077
        or len(prefixes) > 256
    ):
        raise MarketMemoryOptionOiStoreError(
            "option-OI prepared tree is unsafe or noncanonical"
        )

    records: list[dict[str, Any]] = []
    for prefix in prefixes:
        try:
            metadata = prefix.lstat()
            children = sorted(prefix.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            raise MarketMemoryOptionOiStoreError(
                "option-OI prepared prefix cannot be inspected"
            ) from exc
        if (
            re.fullmatch(r"[a-f0-9]{2}", prefix.name) is None
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise MarketMemoryOptionOiStoreError(
                "option-OI prepared prefix is unsafe or noncanonical"
            )
        for path in children:
            if len(records) >= _MAX_PREPARED_RECORDS:
                raise MarketMemoryOptionOiStoreError(
                    "option-OI prepared scan exceeds its bounded pilot capacity"
                )
            try:
                file_metadata = path.lstat()
            except OSError as exc:
                raise MarketMemoryOptionOiStoreError(
                    "option-OI prepared record cannot be inspected"
                ) from exc
            prepared_id = path.name.removesuffix(".json")
            if (
                not path.name.endswith(".json")
                or not _PREPARED_ID.fullmatch(prepared_id)
                or stat.S_ISLNK(file_metadata.st_mode)
                or not stat.S_ISREG(file_metadata.st_mode)
                or stat.S_IMODE(file_metadata.st_mode) & 0o077
                or _prepared_path(root, prepared_id) != path
            ):
                raise MarketMemoryOptionOiStoreError(
                    "option-OI prepared record is unsafe or noncanonical"
                )
            raw, _ = _read_json(
                path,
                limit=_MAX_PREPARED_BYTES,
                label="scanned option-OI prepared record",
            )
            clean = _validate_prepared(raw)
            if clean["prepared_id"] != prepared_id:
                raise MarketMemoryOptionOiStoreError(
                    "option-OI prepared filename disagrees with its identity"
                )
            records.append(clean)
    return sorted(
        records,
        key=lambda item: (
            item["first_observed_at"],
            item["available_at"],
            item["prepared_id"],
        ),
    )


def _active_prepared_ids(
    root: Path,
    *,
    state: _StoreState,
    prepared_by_id: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    active: set[str] = set()
    for entry in state.generation["captures"]:
        receipt_raw, receipt_body = _read_json(
            _capture_path(root, entry["capture_id"]),
            limit=_MAX_RECEIPT_BYTES,
            label="active option-OI capture receipt",
        )
        receipt = _validate_receipt(
            receipt_raw,
            store_id=state.manifest["store_id"],
        )
        if _generation_entry(receipt, body=receipt_body) != entry:
            raise MarketMemoryOptionOiStoreError(
                "active option-OI receipt differs from its generation entry"
            )
        prepared_id = receipt["prepared_id"]
        prepared = prepared_by_id.get(prepared_id)
        if prepared is None:
            raise MarketMemoryOptionOiStoreError(
                "active option-OI capture has no canonical prepared record"
            )
        if (
            _build_receipt(
                root,
                store_id=state.manifest["store_id"],
                prepared=prepared,
            )
            != receipt
        ):
            raise MarketMemoryOptionOiStoreError(
                "active option-OI receipt differs from its prepared record"
            )
        if prepared_id in active:
            raise MarketMemoryOptionOiStoreError(
                "active option-OI prepared identity is ambiguous"
            )
        active.add(prepared_id)
    return active


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
        raise MarketMemoryOptionOiStoreError(
            "pinned actual-output generation differs from its object key"
        )
    return clean, body


def _load_capture(
    root: Path,
    *,
    manifest: Mapping[str, Any],
    generation: Mapping[str, Any],
    capture_id: str,
) -> StoredOptionOiObservation:
    matches = [
        dict(entry)
        for entry in generation["captures"]
        if entry["capture_id"] == capture_id
    ]
    if len(matches) != 1:
        raise MarketMemoryOptionOiStoreError(
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
        raise MarketMemoryOptionOiStoreError(
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
        raise MarketMemoryOptionOiStoreError(
            "actual-output prepared and capture identities are aliased"
        )
    expected_from_prepared = _build_receipt(
        root,
        store_id=manifest["store_id"],
        prepared=prepared,
    )
    if expected_from_prepared != receipt:
        raise MarketMemoryOptionOiStoreError(
            "actual-output receipt differs from its prepared record"
        )

    bodies: dict[str, bytes] = {}
    for role in _SOURCE_ROLES:
        ref = receipt["source_bodies"][role]
        path = _source_body_path(root, ref["sha256"])
        if _object_key(path, root=root) != ref["object_key"]:
            raise MarketMemoryOptionOiStoreError(
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
        label="stored option_oi source observation",
    )
    if (
        len(source_body) != source_ref["bytes"]
        or _digest(source_body) != source_ref["sha256"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "stored source observation differs from its receipt"
        )
    probe_ref = receipt["probe_receipt"]
    probe_raw, probe_body = _read_json(
        _probe_receipt_path(root, probe_ref["probe_receipt_id"]),
        limit=_MAX_PROBE_RECEIPT_BYTES,
        label="stored option-OI probe receipt",
    )
    if (
        len(probe_body) != probe_ref["bytes"]
        or _digest(probe_body) != probe_ref["sha256"]
    ):
        raise MarketMemoryOptionOiStoreError(
            "stored probe receipt differs from its capture receipt"
        )
    selected_headers = probe_raw["response"]["selected_headers"]
    pinned_inputs = option_oi.PinnedOptionOiInputs(
        fetched_response=option_oi.FetchedOptionOiResponse(
            status=200,
            url=option_oi.SOURCE_URL,
            selected_headers=tuple(
                (name, selected_headers[name])
                for name in ("content-type", "content-length")
                if name in selected_headers
            ),
            body=bodies["option_oi_response_body"],
            response_body_completed_at=receipt["clocks"]["response_body_completed_at"],
        ),
        pinned_sources=option_oi.PinnedOptionOiSources(
            pinned_commit=receipt["source_commit"],
            source_config_body=bodies["option_oi_source_config"],
            license_record_body=bodies["massive_entitlement_record"],
            git_blob_oids=tuple(
                (role, receipt["source_bodies"][role]["git_blob_oid"])
                for role in (
                    "option_oi_source_config",
                    "massive_entitlement_record",
                )
            ),
        ),
    )
    candidate = option_oi.OptionOiObservationBundle(
        pinned_inputs=pinned_inputs,
        probe_receipt=probe_raw,
        probe_receipt_bytes=probe_body,
        source_observation=source_raw,
        source_observation_bytes=source_body,
    )
    try:
        checked = option_oi.validate_option_oi_observation_bundle(candidate)
    except option_oi.MarketMemoryOptionOiObservationError as exc:
        raise MarketMemoryOptionOiStoreError(
            "stored option-OI bundle fails detached reprojection"
        ) from exc
    _validate_prepared(prepared, expected_bundle=checked)
    return StoredOptionOiObservation(
        generation_id=generation["generation_id"],
        capture_receipt=receipt,
        bundle=checked,
    )


def initialize_option_oi_store(root: str | Path) -> dict[str, Any]:
    """Create or validate the complete empty private option_oi generation."""

    store_root = validate_option_oi_store_root(root)
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


def load_option_oi_generation(
    root: str | Path, *, generation_id: str | None = None
) -> dict[str, Any]:
    """Load the active or an explicitly pinned immutable generation."""

    store_root = validate_option_oi_store_root(root)
    state = _load_state(store_root)
    generation, _ = _load_generation(
        store_root,
        manifest=state.manifest,
        generation_id=generation_id,
    )
    return copy.deepcopy(generation)


def load_option_oi_capture(
    root: str | Path,
    *,
    capture_id: str,
    generation_id: str | None = None,
) -> StoredOptionOiObservation:
    """Reload one capture only if named by the selected complete generation."""

    store_root = validate_option_oi_store_root(root)
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


def resume_pending_option_oi_captures(
    root: str | Path,
) -> tuple[StoredOptionOiObservation, ...]:
    """Publish every recoverable prepared observation without network or clocks."""

    store_root = validate_option_oi_store_root(root)
    _mkdir(store_root)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(store_root, flags)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        state = _initialize_or_load(store_root)
        _clean_prepared_scratch(store_root)
        prepared_records = _scan_prepared_records(store_root)
        prepared_by_id = {
            prepared["prepared_id"]: prepared for prepared in prepared_records
        }
        if len(prepared_by_id) != len(prepared_records):
            raise MarketMemoryOptionOiStoreError(
                "option-OI prepared scan contains duplicate identities"
            )
        active_prepared = _active_prepared_ids(
            store_root,
            state=state,
            prepared_by_id=prepared_by_id,
        )
        pending = [
            prepared
            for prepared in prepared_records
            if prepared["prepared_id"] not in active_prepared
        ]
        if len(state.generation["captures"]) + len(pending) > _MAX_GENERATION_CAPTURES:
            raise MarketMemoryOptionOiCaptureError(
                "pending option-OI captures exceed the pilot generation bound"
            )

        source_ids = {
            entry["source_observation_id"] for entry in state.generation["captures"]
        }
        probe_ids = {
            entry["probe_receipt_id"] for entry in state.generation["captures"]
        }
        recoverable: list[
            tuple[dict[str, Any], option_oi.OptionOiObservationBundle]
        ] = []
        # Validate every pending record and every CAS dependency before any
        # receipt, generation, or HEAD write.  A single partial/tampered record
        # therefore fails the entire preflight instead of hiding behind order.
        for prepared in pending:
            source_id = prepared["source_observation_id"]
            probe_id = prepared["probe_receipt_id"]
            if source_id in source_ids or probe_id in probe_ids:
                raise MarketMemoryOptionOiStoreError(
                    "pending option-OI prepared identities are ambiguous"
                )
            bundle = _load_bundle_from_prepared(store_root, prepared)
            source_ids.add(source_id)
            probe_ids.add(probe_id)
            recoverable.append((prepared, bundle))

        capture_ids: list[str] = []
        for prepared, bundle in recoverable:
            state, capture_id = _publish_prepared_capture(
                store_root,
                state=state,
                prepared=prepared,
                bundle=bundle,
            )
            capture_ids.append(capture_id)
        return tuple(
            _load_capture(
                store_root,
                manifest=state.manifest,
                generation=state.generation,
                capture_id=capture_id,
            )
            for capture_id in capture_ids
        )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def capture_option_oi_observation(
    root: str | Path,
    *,
    bundle: option_oi.OptionOiObservationBundle,
) -> StoredOptionOiObservation:
    """Validate and append one exact current option-OI availability revision."""

    # No filesystem mutation or wall-clock sample may precede this detached
    # raw-byte reprojection boundary.
    try:
        checked = option_oi.validate_option_oi_observation_bundle(bundle)
    except option_oi.MarketMemoryOptionOiObservationError as exc:
        raise MarketMemoryOptionOiCaptureError(
            "option_oi bundle failed detached validation before store entry"
        ) from exc
    if (
        checked.source_observation.get("schema") != _SOURCE_OBSERVATION_SCHEMA_V1
        or checked.probe_receipt.get("schema") != _PROBE_RECEIPT_SCHEMA_V1
    ):
        raise MarketMemoryOptionOiCaptureError(
            "option_oi bundle is not the frozen actual-output store v1 contract"
        )
    store_root = validate_option_oi_store_root(root)
    _mkdir(store_root)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(store_root, flags)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        state = _initialize_or_load(store_root)
        source_id = checked.source_observation["source_observation_id"]
        probe_id = checked.probe_receipt["probe_receipt_id"]
        matching = [
            dict(entry)
            for entry in state.generation["captures"]
            if entry["source_observation_id"] == source_id
            or entry["probe_receipt_id"] == probe_id
        ]
        if matching:
            if len(matching) != 1 or (
                matching[0]["source_observation_id"] != source_id
                or matching[0]["probe_receipt_id"] != probe_id
            ):
                raise MarketMemoryOptionOiStoreError(
                    "actual-output generation contains an ambiguous identity match"
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
                or stored.bundle.probe_receipt_bytes != checked.probe_receipt_bytes
                or _bundle_source_bodies(stored.bundle)
                != _bundle_source_bodies(checked)
            ):
                raise MarketMemoryOptionOiStoreError(
                    "idempotent option_oi identity differs from stored exact bytes"
                )
            return stored

        # Unclaimed recovery CAS is durable before a store clock is sampled.
        # A crash in this phase may leave harmless orphan CAS, but never a
        # prepared record whose exact bundle cannot be reconstructed.
        _persist_bundle_cas(store_root, checked)
        prepared_path = _prepared_path(store_root, _prepared_id(checked))
        if prepared_path.exists() or prepared_path.is_symlink():
            # A durable prepared record owns the first store-observation clock.
            # Resume it without sampling a replacement clock.
            attempt_observed_at = None
        else:
            attempt_observed_at = _sample_first_observed_at(
                available_at=checked.source_observation["available_at"]
            )
        prepared = _load_or_create_prepared(
            store_root,
            checked,
            attempt_observed_at=attempt_observed_at,
        )
        state, capture_id = _publish_prepared_capture(
            store_root,
            state=state,
            prepared=prepared,
            bundle=checked,
        )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return load_option_oi_capture(
        store_root,
        capture_id=capture_id,
        generation_id=state.generation["generation_id"],
    )


__all__ = [
    "CAPTURE_RECEIPT_SCHEMA",
    "GENERATION_SCHEMA",
    "HEAD_SCHEMA",
    "PREPARED_SCHEMA",
    "STORE_PROFILE",
    "STORE_SCHEMA",
    "MarketMemoryOptionOiCaptureError",
    "MarketMemoryOptionOiStoreError",
    "StoredOptionOiObservation",
    "capture_option_oi_observation",
    "default_option_oi_store_root",
    "initialize_option_oi_store",
    "load_option_oi_capture",
    "load_option_oi_generation",
    "resume_pending_option_oi_captures",
    "validate_option_oi_store_root",
]
