"""Bounded live projection of the current raw US macro-regime artifact.

W1B.1 deliberately projects one already-built artifact and nothing else.  The
projector stable-reads ``data/regime/latest.json``, preserves the exact source
byte identity, and emits a small allowlisted macro snapshot.  It does not read
historical outcomes, recurse into the large regime payload, persist a packet,
or grant rank/gate/size/trade/Prophet authority.

``freshness.built_at`` is a measurement/build clock, not proof that Market
Memory possessed the artifact at that time.  ``observed_at`` is therefore
owned by this process and stamped only after the stable read completes.  A
trusted source-receipt adapter must use that observation as the earliest live
availability clock; it must never backdate availability to ``built_at``.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from engine.neuralweb import market_memory

SNAPSHOT_SCHEMA = "market_memory.macro_regime_snapshot.v1"
TRANSFORM_VERSION = "market_memory.macro_regime_transform.v1"
SOURCE_ID = "data.regime.latest"
SOURCE_SCHEMA_VERSION = 1
PIT_BASIS = "live_captured"

_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_SNAPSHOT_ID = re.compile(r"mmsnap_[a-f0-9]{64}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_QUADS = frozenset({"Q1", "Q2", "Q3", "Q4"})
_LIQUIDITY = frozenset({"expanding", "neutral", "contracting", "unknown"})
_CYCLES = frozenset({"early", "mid", "late", "unknown"})
_TRANSITIONS = frozenset({"STABLE", "WEAKENING", "TRANSITIONING", "NEW_REGIME"})
_TRANSITION_FLAGS: tuple[str, ...] = (
    "flag_breadth_price",
    "flag_credit_equity",
    "flag_ratio_inflection",
    "flag_inflation_basket",
    "flag_confidence_decay",
    "flag_gex",
    "flag_rotation_persistence",
)
_STATE_FIELDS = frozenset(
    {
        "quad",
        "raw_quad",
        "pending_quad",
        "pending_days",
        "pending_need",
        "growth_score",
        "inflation_score",
        "growth_confidence",
        "inflation_confidence",
        "confidence",
        "liquidity_overlay",
        "cycle_tag",
        "transition_state",
        "transition_state_raw",
        "transition_ratcheted",
        "transition_dwell_remaining",
        "transition_flags",
    }
)
_SNAPSHOT_FIELDS = frozenset(
    {
        "schema",
        "snapshot_id",
        "content_sha256",
        "content_bytes",
        "as_of",
        "observed_at",
        "pit_basis",
        "transform_version",
        "source_artifact",
        "state",
        "quality",
        "authority",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "source_schema_version",
        "source_asof",
        "built_at",
        "raw_sha256",
        "raw_bytes",
    }
)
_QUALITY = {
    "status": "complete",
    "actual_output_capture": True,
    "current_snapshot_only": True,
    "component_source_receipts_authenticated": False,
    "feature_projection_eligible": True,
    "imputed": False,
    "training_eligible": False,
    "promotion_eligible": False,
}


class MarketMemoryProjectionError(ValueError):
    """The current regime artifact or projected snapshot is not admissible."""


@dataclass(frozen=True)
class _StableRead:
    body: bytes
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @property
    def identity(self) -> tuple[int, int, int, int, int]:
        return (
            self.device,
            self.inode,
            self.size,
            self.mtime_ns,
            self.ctime_ns,
        )


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
        raise MarketMemoryProjectionError(
            "macro regime projection is not canonical finite JSON"
        ) from exc


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _strict_json_object(body: bytes) -> dict[str, Any]:
    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON token {value}")

    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=reject_nonfinite,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise MarketMemoryProjectionError(
            "macro regime source is not strict JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise MarketMemoryProjectionError("macro regime source must be a JSON object")
    return payload


def _stable_read_source(path: str | Path) -> _StableRead:
    source = Path(os.path.abspath(Path(path).expanduser()))
    if source.is_symlink():
        raise MarketMemoryProjectionError("macro regime source is a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise MarketMemoryProjectionError(
            "macro regime source cannot be opened safely"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise MarketMemoryProjectionError(
                "macro regime source is not a regular file"
            )
        if before.st_size <= 0 or before.st_size > _MAX_SOURCE_BYTES:
            raise MarketMemoryProjectionError(
                "macro regime source exceeds its safe size bound"
            )
        chunks: list[bytes] = []
        remaining = _MAX_SOURCE_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
        after = os.fstat(descriptor)
        path_after = os.stat(source, follow_symlinks=False)
    except MarketMemoryProjectionError:
        raise
    except OSError as exc:
        raise MarketMemoryProjectionError(
            "macro regime source cannot be read safely"
        ) from exc
    finally:
        os.close(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    path_identity = (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_size,
        path_after.st_mtime_ns,
        path_after.st_ctime_ns,
    )
    if (
        before_identity != after_identity
        or after_identity != path_identity
        or len(body) != before.st_size
        or len(body) > _MAX_SOURCE_BYTES
    ):
        raise MarketMemoryProjectionError(
            "macro regime source changed during stable read"
        )
    return _StableRead(body, *before_identity)


def _observation_clock() -> tuple[datetime, str]:
    value = _utc_now()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MarketMemoryProjectionError("projector observation clock must be UTC")
    if value.utcoffset() != timedelta(0):
        raise MarketMemoryProjectionError("projector observation clock must be UTC")
    value = value.astimezone(timezone.utc)
    stamp = value.isoformat().replace("+00:00", "Z")
    if not _RFC3339_UTC.fullmatch(stamp):
        raise MarketMemoryProjectionError(
            "projector observation clock is not canonical UTC"
        )
    return value, stamp


def _date_value(value: object, *, field: str) -> date:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise MarketMemoryProjectionError(f"{field} must be an exact date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise MarketMemoryProjectionError(f"{field} must be an exact date") from exc


def _utc_value(value: object, *, field: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not _RFC3339_UTC.fullmatch(value):
        raise MarketMemoryProjectionError(
            f"{field} must be an exact RFC3339 UTC timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryProjectionError(f"{field} is not a valid timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise MarketMemoryProjectionError(f"{field} must be UTC")
    parsed = parsed.astimezone(timezone.utc)
    return parsed, parsed.isoformat().replace("+00:00", "Z")


def _integer(
    value: object, *, field: str, minimum: int = 0, maximum: int = 3_650
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise MarketMemoryProjectionError(f"{field} is outside its integer bound")
    return value


def _number(value: object, *, field: str, minimum: float, maximum: float) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < minimum
        or float(value) > maximum
    ):
        raise MarketMemoryProjectionError(f"{field} is outside its finite bound")
    return float(value)


def _enum(value: object, allowed: frozenset[str], *, field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise MarketMemoryProjectionError(f"{field} is outside its frozen vocabulary")
    return value


def _optional_quad(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _enum(value, _QUADS, field=field)


def _project_state(raw: Mapping[str, Any]) -> dict[str, Any]:
    if raw.get("schema_version") != SOURCE_SCHEMA_VERSION or isinstance(
        raw.get("schema_version"), bool
    ):
        raise MarketMemoryProjectionError("macro regime source schema mismatch")
    pending_days = _integer(raw.get("pending_days"), field="pending_days")
    pending_need = _integer(raw.get("pending_need"), field="pending_need", minimum=1)
    pending_quad = _optional_quad(raw.get("pending_quad"), field="pending_quad")
    quad = _enum(raw.get("quad"), _QUADS, field="quad")
    if pending_quad is None and pending_days != 0:
        raise MarketMemoryProjectionError(
            "pending_days must be zero without a pending_quad"
        )
    if pending_quad is not None and (
        pending_quad == quad or pending_days <= 0 or pending_days >= pending_need
    ):
        raise MarketMemoryProjectionError(
            "pending regime hysteresis state is internally inconsistent"
        )
    flags = raw.get("transition_flags")
    if not isinstance(flags, Mapping) or set(flags) != set(_TRANSITION_FLAGS):
        raise MarketMemoryProjectionError(
            "transition_flags do not match the frozen raw-regime allowlist"
        )
    clean_flags: dict[str, bool] = {}
    for key in _TRANSITION_FLAGS:
        value = flags.get(key)
        if not isinstance(value, bool):
            raise MarketMemoryProjectionError(f"transition_flags.{key} must be boolean")
        clean_flags[key] = value
    ratcheted = raw.get("transition_ratcheted")
    if not isinstance(ratcheted, bool):
        raise MarketMemoryProjectionError("transition_ratcheted must be boolean")
    state = {
        "quad": quad,
        "raw_quad": _optional_quad(raw.get("raw_quad"), field="raw_quad"),
        "pending_quad": pending_quad,
        "pending_days": pending_days,
        "pending_need": pending_need,
        "growth_score": _number(
            raw.get("growth_score"), field="growth_score", minimum=-1.0, maximum=1.0
        ),
        "inflation_score": _number(
            raw.get("inflation_score"),
            field="inflation_score",
            minimum=-1.0,
            maximum=1.0,
        ),
        "growth_confidence": _number(
            raw.get("growth_confidence"),
            field="growth_confidence",
            minimum=0.0,
            maximum=1.0,
        ),
        "inflation_confidence": _number(
            raw.get("inflation_confidence"),
            field="inflation_confidence",
            minimum=0.0,
            maximum=1.0,
        ),
        "confidence": _number(
            raw.get("confidence"), field="confidence", minimum=0.0, maximum=1.0
        ),
        "liquidity_overlay": _enum(
            raw.get("liquidity_overlay"), _LIQUIDITY, field="liquidity_overlay"
        ),
        "cycle_tag": _enum(raw.get("cycle_tag"), _CYCLES, field="cycle_tag"),
        "transition_state": _enum(
            raw.get("transition_state"), _TRANSITIONS, field="transition_state"
        ),
        "transition_state_raw": _enum(
            raw.get("transition_state_raw"),
            _TRANSITIONS,
            field="transition_state_raw",
        ),
        "transition_ratcheted": ratcheted,
        "transition_dwell_remaining": _integer(
            raw.get("transition_dwell_remaining"),
            field="transition_dwell_remaining",
        ),
        "transition_flags": clean_flags,
    }
    if set(state) != _STATE_FIELDS:
        raise MarketMemoryProjectionError("macro regime state allowlist drift")
    return state


def _projection_core(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": value["schema"],
        "as_of": value["as_of"],
        "transform_version": value["transform_version"],
        "source_artifact": copy.deepcopy(value["source_artifact"]),
        "state": copy.deepcopy(value["state"]),
    }


def build_macro_regime_snapshot(path: str | Path) -> dict[str, Any]:
    """Stable-read and project one current macro regime snapshot.

    The function is pure with respect to the filesystem: it reads ``path`` and
    returns a detached value.  It creates no store, packet, receipt, or label.
    """

    stable = _stable_read_source(path)
    raw = _strict_json_object(stable.body)
    # This process-owned clock is intentionally called only after the exact
    # bytes have survived the complete stable read and strict JSON parse.
    observed_dt, observed_at = _observation_clock()

    source_asof = _date_value(raw.get("asof"), field="asof")
    if raw.get("date") != source_asof.isoformat():
        raise MarketMemoryProjectionError("regime date does not match asof")
    freshness = raw.get("freshness")
    if not isinstance(freshness, Mapping):
        raise MarketMemoryProjectionError("freshness must be an object")
    if freshness.get("asof") != source_asof.isoformat():
        raise MarketMemoryProjectionError("freshness.asof does not match asof")
    built_dt, built_at = _utc_value(
        freshness.get("built_at"), field="freshness.built_at"
    )
    if source_asof > built_dt.date():
        raise MarketMemoryProjectionError("asof follows freshness.built_at")
    if built_dt > observed_dt or source_asof > observed_dt.date():
        raise MarketMemoryProjectionError(
            "regime build/asof clock is in the projector's future"
        )

    source_artifact = {
        "source_id": SOURCE_ID,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "source_asof": source_asof.isoformat(),
        # This is measurement/build evidence only.  It is deliberately not
        # named or used as a Market Memory availability clock.
        "built_at": built_at,
        "raw_sha256": sha256(stable.body).hexdigest(),
        "raw_bytes": len(stable.body),
    }
    snapshot: dict[str, Any] = {
        "schema": SNAPSHOT_SCHEMA,
        "snapshot_id": "",
        "content_sha256": "",
        "content_bytes": 0,
        # Use the exact build clock instead of inventing a session-close time
        # for the date-only source ``asof`` field.
        "as_of": built_at,
        "observed_at": observed_at,
        "pit_basis": PIT_BASIS,
        "transform_version": TRANSFORM_VERSION,
        "source_artifact": source_artifact,
        "state": _project_state(raw),
        "quality": copy.deepcopy(_QUALITY),
        "authority": dict(market_memory.AUTHORITY),
    }
    content = _canonical_bytes(_projection_core(snapshot))
    digest = sha256(content).hexdigest()
    snapshot["snapshot_id"] = f"mmsnap_{digest}"
    snapshot["content_sha256"] = digest
    snapshot["content_bytes"] = len(content)
    return validate_macro_regime_snapshot(snapshot)


def validate_macro_regime_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a snapshot at a consumer boundary and detach its content."""

    if not isinstance(value, Mapping) or set(value) != _SNAPSHOT_FIELDS:
        raise MarketMemoryProjectionError(
            "macro regime snapshot fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != SNAPSHOT_SCHEMA:
        raise MarketMemoryProjectionError("macro regime snapshot schema mismatch")
    if clean.get("transform_version") != TRANSFORM_VERSION:
        raise MarketMemoryProjectionError("macro regime transform version mismatch")
    if clean.get("pit_basis") != PIT_BASIS:
        raise MarketMemoryProjectionError("macro regime snapshot basis drift")
    as_of_dt, as_of = _utc_value(clean.get("as_of"), field="as_of")
    observed_dt, observed_at = _utc_value(clean.get("observed_at"), field="observed_at")
    if observed_dt < as_of_dt:
        raise MarketMemoryProjectionError("snapshot observed_at precedes as_of")
    clean["as_of"] = as_of
    clean["observed_at"] = observed_at

    source = clean.get("source_artifact")
    if not isinstance(source, Mapping) or set(source) != _SOURCE_FIELDS:
        raise MarketMemoryProjectionError(
            "macro regime source artifact fields are not canonical"
        )
    if (
        source.get("source_id") != SOURCE_ID
        or source.get("source_schema_version") != SOURCE_SCHEMA_VERSION
        or isinstance(source.get("source_schema_version"), bool)
    ):
        raise MarketMemoryProjectionError("macro regime source identity drift")
    source_asof = _date_value(source.get("source_asof"), field="source_asof")
    built_dt, built_at = _utc_value(source.get("built_at"), field="built_at")
    if built_dt != as_of_dt or source_asof > built_dt.date():
        raise MarketMemoryProjectionError(
            "macro regime source build/asof clocks do not bind the snapshot"
        )
    raw_hash = source.get("raw_sha256")
    raw_bytes = source.get("raw_bytes")
    if not isinstance(raw_hash, str) or not _SHA256.fullmatch(raw_hash):
        raise MarketMemoryProjectionError("raw source SHA-256 is malformed")
    if (
        not isinstance(raw_bytes, int)
        or isinstance(raw_bytes, bool)
        or raw_bytes <= 0
        or raw_bytes > _MAX_SOURCE_BYTES
    ):
        raise MarketMemoryProjectionError("raw source byte count is invalid")
    clean["source_artifact"] = {
        "source_id": SOURCE_ID,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "source_asof": source_asof.isoformat(),
        "built_at": built_at,
        "raw_sha256": raw_hash,
        "raw_bytes": raw_bytes,
    }

    state = clean.get("state")
    if not isinstance(state, Mapping) or set(state) != _STATE_FIELDS:
        raise MarketMemoryProjectionError("macro regime state fields are not canonical")
    # Reuse the raw-state validator: all required projection fields share the
    # same names and it rejects unknown nested transition flags.
    state_source = {**state, "schema_version": SOURCE_SCHEMA_VERSION}
    clean["state"] = _project_state(state_source)
    if clean.get("quality") != _QUALITY:
        raise MarketMemoryProjectionError("macro regime snapshot quality drift")
    clean["quality"] = copy.deepcopy(_QUALITY)
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise MarketMemoryProjectionError("macro regime snapshot authority drift")
    clean["authority"] = dict(market_memory.AUTHORITY)

    content = _canonical_bytes(_projection_core(clean))
    digest = sha256(content).hexdigest()
    content_hash = clean.get("content_sha256")
    content_bytes = clean.get("content_bytes")
    if content_hash != digest:
        raise MarketMemoryProjectionError(
            "macro regime content_sha256 does not bind projected bytes"
        )
    if (
        not isinstance(content_bytes, int)
        or isinstance(content_bytes, bool)
        or content_bytes != len(content)
    ):
        raise MarketMemoryProjectionError(
            "macro regime content_bytes does not bind projected bytes"
        )
    snapshot_id = clean.get("snapshot_id")
    if (
        not isinstance(snapshot_id, str)
        or not _SNAPSHOT_ID.fullmatch(snapshot_id)
        or snapshot_id != f"mmsnap_{digest}"
    ):
        raise MarketMemoryProjectionError(
            "macro regime snapshot_id does not bind projected bytes"
        )
    return clean


def macro_regime_snapshot_reference(value: Mapping[str, Any]) -> dict[str, str]:
    """Return the exact typed reference accepted by ``macro.regime_state``."""

    clean = validate_macro_regime_snapshot(value)
    return {
        "snapshot_id": clean["snapshot_id"],
        "schema": clean["schema"],
        "content_sha256": clean["content_sha256"],
        "as_of": clean["as_of"],
    }


def read_verified_macro_regime_bytes(
    path: str | Path, snapshot: Mapping[str, Any]
) -> bytes:
    """Repeat the stable read and return bytes bound to ``snapshot``.

    A trusted publisher calls this immediately before private persistence.  The
    second stable read closes a projection-to-persistence replacement race, and
    the semantic comparison prevents a caller from pairing self-consistent
    snapshot metadata with unrelated raw bytes.  Raw bytes never enter the
    public snapshot value.
    """

    clean = validate_macro_regime_snapshot(snapshot)
    stable = _stable_read_source(path)
    source = clean["source_artifact"]
    if (
        len(stable.body) != source["raw_bytes"]
        or sha256(stable.body).hexdigest() != source["raw_sha256"]
    ):
        raise MarketMemoryProjectionError(
            "macro regime source bytes no longer match projected evidence"
        )
    raw = _strict_json_object(stable.body)
    source_asof = _date_value(raw.get("asof"), field="asof")
    freshness = raw.get("freshness")
    if not isinstance(freshness, Mapping):
        raise MarketMemoryProjectionError("freshness must be an object")
    _built_dt, built_at = _utc_value(
        freshness.get("built_at"), field="freshness.built_at"
    )
    if (
        raw.get("date") != source_asof.isoformat()
        or freshness.get("asof") != source_asof.isoformat()
        or source_asof.isoformat() != source["source_asof"]
        or built_at != source["built_at"]
        or _project_state(raw) != clean["state"]
    ):
        raise MarketMemoryProjectionError(
            "macro regime source semantics no longer match projected evidence"
        )
    return stable.body


__all__ = [
    "PIT_BASIS",
    "SNAPSHOT_SCHEMA",
    "SOURCE_ID",
    "SOURCE_SCHEMA_VERSION",
    "TRANSFORM_VERSION",
    "MarketMemoryProjectionError",
    "build_macro_regime_snapshot",
    "macro_regime_snapshot_reference",
    "read_verified_macro_regime_bytes",
    "validate_macro_regime_snapshot",
]
