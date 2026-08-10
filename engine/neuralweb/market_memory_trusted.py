"""Trusted go-forward Market Memory context publication and exact federation.

W1A intentionally stores only explicit missingness.  This module leaves that
store and policy untouched and adds a separate, create-once store for one
bounded observed feature: the current SPY canary's ``macro.regime_state``.

The publisher writes exact raw/source evidence under the API-inaccessible
state tree first, then a label-free typed feature object, packet, duplicate
query/context receipts, cumulative generation, and finally ``HEAD.json`` in
the read-only serving tree.  Readers trust only the generation named by HEAD.
They never choose a nearest timestamp, recompute a packet, or fall back around
corruption.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from engine.neuralweb import market_memory, market_memory_pit

TRUSTED_CAPTURE_RECEIPT_SCHEMA = "market_memory.trusted_capture_receipt.v1"
TRUSTED_STORE_SCHEMA = "market_memory.trusted_store.v1"
TRUSTED_STORE_PROFILE = "market_memory.trusted.macro_regime_canary.v1"
_GENERATION_SCHEMA = "market_memory.store_generation.v1"
_HEAD_SCHEMA = "market_memory.store_head.v1"
_ALLOWED_OBSERVED_FEATURE_IDS = ("macro.regime_state",)
_MAX_CAPTURE_LAG = timedelta(minutes=15)
_MAX_CLOCK_SKEW = timedelta(seconds=5)
_MAX_RECEIPT_BYTES = 96 * 1024
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_FEATURE_BYTES = 128 * 1024
_MAX_PRIVATE_SOURCE_BYTES = 2 * 1024 * 1024
_MAX_GENERATION_BYTES = 2 * 1024 * 1024
_MAX_GENERATION_CAPTURES = 4_096
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"mmstore_[a-f0-9]{64}\Z")
_CAPTURE_ID = re.compile(r"mmcapture_[a-f0-9]{64}\Z")
_CONTEXT_ID = re.compile(r"mmctx_[a-f0-9]{64}\Z")
_QUERY_ID = re.compile(r"mmquery_[a-f0-9]{64}\Z")
_SNAPSHOT_ID = re.compile(r"mmsnap_[a-f0-9]{64}\Z")
_GIT_COMMIT = re.compile(r"[a-f0-9]{40,64}\Z")
_EVIDENCE_POLICY = {
    "contract_validated": True,
    "source_artifact_bytes_authenticated": True,
    "component_source_receipts_authenticated": False,
    "identity_artifacts_authenticated": True,
    "actual_output_only": True,
    "allowed_observed_feature_ids": list(_ALLOWED_OBSERVED_FEATURE_IDS),
    "all_other_features": "explicit_missing",
    "training_eligible": False,
    "promotion_eligible": False,
    "role": "context_only",
}
_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "store_id",
        "nonce",
        "profile",
        "packet_schema",
        "capture_receipt_schema",
        "generation_schema",
        "mode",
        "allowed_observed_feature_ids",
        "evidence_policy",
        "authority",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "store_id",
        "capture_id",
        "query_id",
        "context_id",
        "packet_sha256",
        "packet_bytes",
        "object_key",
        "feature_snapshot",
        "source_evidence",
        "subject",
        "clocks",
        "mode",
        "captured_at",
        "deployed_commit",
        "feature_registry_version",
        "source_registry_version",
        "source_receipt_ids",
        "source_artifact_sha256s",
        "observed_feature_ids",
        "missing_feature_ids",
        "domain_coverage_sha256",
        "evidence_policy",
        "authority",
    }
)
_FEATURE_SNAPSHOT_FIELDS = frozenset(
    {
        "snapshot_id",
        "schema",
        "content_sha256",
        "content_bytes",
        "object_key",
        "as_of",
    }
)
_SOURCE_EVIDENCE_FIELDS = frozenset(
    {
        "raw_source_sha256",
        "raw_source_bytes",
        "raw_source_built_at",
        "raw_source_observed_at",
        "identity_config_sha256",
        "membership_artifact_sha256",
        "membership_artifact_bytes",
        "calendar_artifact_sha256",
        "calendar_artifact_bytes",
    }
)


class MarketMemoryTrustedError(market_memory_pit.MarketMemoryPITError):
    """Base error for the trusted publisher boundary."""


class MarketMemoryTrustedCaptureError(
    MarketMemoryTrustedError, market_memory_pit.MarketMemoryCaptureError
):
    """A candidate cannot enter the bounded trusted store."""


@dataclass(frozen=True)
class _TrustedStoreState:
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
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted Market Memory value is not canonical finite JSON"
        ) from exc


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + sha256(_canonical_bytes(core)).hexdigest()


def _parse_utc(value: object, *, field: str) -> tuple[datetime, str]:
    try:
        return market_memory_pit._parse_exact_utc(value, field=field)
    except market_memory_pit.MarketMemoryQueryError as exc:
        raise market_memory_pit.MarketMemoryStoreError(
            f"trusted receipt {field} is malformed"
        ) from exc


def _require_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise market_memory_pit.MarketMemoryStoreError(
            f"trusted receipt {field} is not lowercase SHA-256"
        )
    return value


def _require_exact_int(
    value: object, *, field: str, minimum: int = 0, maximum: int
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise market_memory_pit.MarketMemoryStoreError(
            f"trusted receipt {field} is outside its integer bound"
        )
    return value


def validate_trusted_store_root(
    root: str | Path, *, repository_root: str | Path | None = None
) -> Path:
    return market_memory_pit.validate_store_root(root, repository_root=repository_root)


def _validate_disjoint_roots(public_root: Path, private_root: Path) -> None:
    if public_root == private_root:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted public and private roots must be disjoint"
        )
    if public_root in private_root.parents or private_root in public_root.parents:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted public and private roots cannot contain one another"
        )


def _manifest_path(root: Path) -> Path:
    return market_memory_pit._safe_store_path(root, "store_manifest.json")


def _head_path(root: Path) -> Path:
    return market_memory_pit._safe_store_path(root, "HEAD.json")


def _feature_path(root: Path, digest: str) -> Path:
    _require_digest(digest, field="feature content digest")
    return market_memory_pit._safe_store_path(
        root, "feature_objects", digest[:2], f"{digest}.json"
    )


def _private_object_path(root: Path, category: str, digest: str) -> Path:
    if category not in {"raw", "membership", "calendar"}:
        raise market_memory_pit.MarketMemoryStoreError(
            "private evidence category is not registered"
        )
    _require_digest(digest, field=f"{category} object digest")
    return market_memory_pit._safe_store_path(
        root, f"{category}_objects", digest[:2], f"{digest}.json"
    )


def _private_receipt_path(root: Path, capture_id: str) -> Path:
    if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
        raise market_memory_pit.MarketMemoryStoreError(
            "private capture_id is malformed"
        )
    digest = capture_id.removeprefix("mmcapture_")
    return market_memory_pit._safe_store_path(
        root, "capture_receipts", digest[:2], f"{capture_id}.json"
    )


def _write_exact_bytes_create_once(
    root: Path, path: Path, body: bytes, *, label: str, limit: int
) -> bool:
    if not isinstance(body, bytes) or not body or len(body) > limit:
        raise MarketMemoryTrustedCaptureError(
            f"{label} is empty or exceeds its byte bound"
        )
    try:
        path.parent.relative_to(root)
    except ValueError as exc:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted immutable write escaped its root"
        ) from exc
    market_memory_pit._mkdir_durable(path.parent)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise market_memory_pit.MarketMemoryStoreError(
                f"existing {label} is not a regular file"
            )
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise market_memory_pit.MarketMemoryStoreError(
                f"cannot read existing {label}"
            ) from exc
        if len(existing) > limit or existing != body:
            raise MarketMemoryTrustedCaptureError(f"immutable {label} collision")
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
            if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
                raise MarketMemoryTrustedCaptureError(
                    f"immutable {label} collision"
                ) from None
            return False
    except (MarketMemoryTrustedCaptureError, market_memory_pit.MarketMemoryStoreError):
        raise
    except OSError as exc:
        raise market_memory_pit.MarketMemoryStoreError(
            f"cannot publish immutable {label}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _new_manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": TRUSTED_STORE_SCHEMA,
        "store_id": "",
        "nonce": uuid4().hex,
        "profile": TRUSTED_STORE_PROFILE,
        "packet_schema": market_memory.AS_KNOWN_AT_SCHEMA,
        "capture_receipt_schema": TRUSTED_CAPTURE_RECEIPT_SCHEMA,
        "generation_schema": _GENERATION_SCHEMA,
        "mode": "operational_pit",
        "allowed_observed_feature_ids": list(_ALLOWED_OBSERVED_FEATURE_IDS),
        "evidence_policy": copy.deepcopy(_EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    manifest["store_id"] = _content_id("mmstore_", manifest, field="store_id")
    return manifest


def _validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_FIELDS:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted store manifest fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != TRUSTED_STORE_SCHEMA:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted store manifest schema mismatch"
        )
    store_id = clean.get("store_id")
    if not isinstance(store_id, str) or not _STORE_ID.fullmatch(store_id):
        raise market_memory_pit.MarketMemoryStoreError("trusted store_id is malformed")
    if not isinstance(clean.get("nonce"), str) or not re.fullmatch(
        r"[a-f0-9]{32}", clean["nonce"]
    ):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted store nonce is malformed"
        )
    expected = {
        "profile": TRUSTED_STORE_PROFILE,
        "packet_schema": market_memory.AS_KNOWN_AT_SCHEMA,
        "capture_receipt_schema": TRUSTED_CAPTURE_RECEIPT_SCHEMA,
        "generation_schema": _GENERATION_SCHEMA,
        "mode": "operational_pit",
        "allowed_observed_feature_ids": list(_ALLOWED_OBSERVED_FEATURE_IDS),
        "evidence_policy": _EVIDENCE_POLICY,
        "authority": dict(market_memory.AUTHORITY),
    }
    for field, wanted in expected.items():
        if clean.get(field) != wanted:
            raise market_memory_pit.MarketMemoryStoreError(
                f"trusted store {field} drift"
            )
    if _content_id("mmstore_", clean, field="store_id") != store_id:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted store_id does not bind its manifest"
        )
    return clean


def _empty_state(root: Path, manifest: Mapping[str, Any]) -> _TrustedStoreState:
    generation = market_memory_pit._new_generation(
        store_id=str(manifest["store_id"]),
        previous_generation_id=None,
        captures=[],
    )
    generation_body = _canonical_bytes(generation)
    market_memory_pit._write_create_once(
        root,
        market_memory_pit._generation_path(root, generation["generation_id"]),
        generation_body,
        label="trusted empty generation",
    )
    head = market_memory_pit._new_head(generation, generation_body=generation_body)
    market_memory_pit._replace_head(root, head)
    return _TrustedStoreState(dict(manifest), head, generation)


def _initialize_or_load(root: Path) -> _TrustedStoreState:
    manifest_path = _manifest_path(root)
    head_path = _head_path(root)
    if head_path.exists() or head_path.is_symlink():
        return _load_state(root)
    if not (manifest_path.exists() or manifest_path.is_symlink()):
        for name in (
            "generations",
            "objects",
            "contexts",
            "queries",
            "feature_objects",
        ):
            path = market_memory_pit._safe_store_path(root, name)
            if path.exists() or path.is_symlink():
                raise market_memory_pit.MarketMemoryStoreError(
                    "trusted store initialization is partial"
                )
        manifest = _new_manifest()
        market_memory_pit._write_create_once(
            root,
            manifest_path,
            _canonical_bytes(manifest),
            label="trusted store manifest",
        )
        return _empty_state(root, manifest)
    for name in ("objects", "contexts", "queries", "feature_objects"):
        path = market_memory_pit._safe_store_path(root, name)
        if path.exists() or path.is_symlink():
            raise market_memory_pit.MarketMemoryStoreError(
                "trusted store has captures without an active HEAD"
            )
    manifest, _body = market_memory_pit._read_canonical_object(
        manifest_path,
        limit=_MAX_MANIFEST_BYTES,
        label="trusted store manifest",
    )
    clean = _validate_manifest(manifest)
    # Reuse or create the deterministic empty generation after an interrupted
    # initialization, then publish HEAD last.
    return _empty_state(root, clean)


def _load_state(root: Path) -> _TrustedStoreState:
    manifest, _manifest_body = market_memory_pit._read_canonical_object(
        _manifest_path(root),
        limit=_MAX_MANIFEST_BYTES,
        label="trusted store manifest",
    )
    clean_manifest = _validate_manifest(manifest)
    head, _head_body = market_memory_pit._read_canonical_object(
        _head_path(root),
        limit=market_memory_pit._MAX_HEAD_BYTES,
        label="trusted store HEAD",
    )
    clean_head = market_memory_pit._validate_head(
        head, store_id=clean_manifest["store_id"]
    )
    if clean_head.get("schema") != _HEAD_SCHEMA:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted store HEAD schema mismatch"
        )
    generation, generation_body = market_memory_pit._read_canonical_object(
        market_memory_pit._generation_path(root, clean_head["generation_id"]),
        limit=_MAX_GENERATION_BYTES,
        label="trusted store generation",
    )
    if sha256(generation_body).hexdigest() != clean_head["generation_sha256"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted store HEAD generation digest mismatch"
        )
    clean_generation = market_memory_pit._validate_generation(
        generation, store_id=clean_manifest["store_id"]
    )
    if clean_generation["generation_id"] != clean_head["generation_id"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted store HEAD generation identity mismatch"
        )
    return _TrustedStoreState(clean_manifest, clean_head, clean_generation)


def _snapshot_core(snapshot: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    expected = {
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
    if not isinstance(snapshot, Mapping) or set(snapshot) != expected:
        raise MarketMemoryTrustedCaptureError(
            "macro regime snapshot fields are not canonical"
        )
    core = {
        "schema": snapshot["schema"],
        "as_of": snapshot["as_of"],
        "transform_version": snapshot["transform_version"],
        "source_artifact": copy.deepcopy(snapshot["source_artifact"]),
        "state": copy.deepcopy(snapshot["state"]),
    }
    body = _canonical_bytes(core)
    digest = sha256(body).hexdigest()
    if snapshot.get("content_sha256") != digest:
        raise MarketMemoryTrustedCaptureError(
            "macro regime snapshot digest does not bind its projection"
        )
    if snapshot.get("snapshot_id") != f"mmsnap_{digest}":
        raise MarketMemoryTrustedCaptureError(
            "macro regime snapshot_id does not bind its projection"
        )
    if snapshot.get("content_bytes") != len(body):
        raise MarketMemoryTrustedCaptureError(
            "macro regime snapshot byte count mismatch"
        )
    if len(body) > _MAX_FEATURE_BYTES:
        raise MarketMemoryTrustedCaptureError(
            "macro regime snapshot exceeds its byte bound"
        )
    return core, body


def _missing_features(observed_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature_id, spec in market_memory.CANONICAL_FEATURE_REGISTRY.items():
        if feature_id in _ALLOWED_OBSERVED_FEATURE_IDS:
            continue
        rows.append(
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
                "missing_reason": "no_point_in_time_vintage",
                "quality": {
                    "status": "missing",
                    "flags": ["not_captured"],
                    "staleness_seconds": None,
                    "imputed": False,
                },
            }
        )
    return rows


def _regime_source_receipt(
    snapshot: Mapping[str, Any], *, as_known_at: str
) -> dict[str, Any]:
    source = snapshot["source_artifact"]
    built_dt, built_at = _parse_utc(source.get("built_at"), field="source built_at")
    observed_dt, observed_at = _parse_utc(
        snapshot.get("observed_at"), field="snapshot observed_at"
    )
    cutoff_dt, _cutoff = _parse_utc(as_known_at, field="as_known_at")
    if built_dt > observed_dt or observed_dt > cutoff_dt:
        raise MarketMemoryTrustedCaptureError(
            "macro regime source clocks are not operationally ordered"
        )
    raw_digest = _require_digest(
        source.get("raw_sha256"), field="raw regime source digest"
    )
    staleness = (observed_dt - built_dt).total_seconds()
    receipt: dict[str, Any] = {
        "receipt_id": "",
        "source_id": "market_regime_store",
        "source_role": "macro_regime",
        "source_schema": "market_memory.source.macro_regime.v1",
        "artifact_sha256": raw_digest,
        "event_time": built_at,
        "measurement_end": built_at,
        # The committed artifact has no trustworthy publication receipt.  Its
        # first safe availability is this process's post-stable-read clock.
        "available_at": observed_at,
        "observed_at": observed_at,
        "vintage_id": "mmv_"
        + sha256(f"market_regime_store:{built_at}".encode()).hexdigest(),
        "revision_id": "mmr_" + raw_digest,
        "pit_basis": "live_captured",
        "availability_class": "revision",
        "availability_rule": "registered_adapter_receipt.v1",
        "market_session": "XNYS_REGULAR",
        "valid_from": None,
        "valid_through": None,
        "identity_binding": None,
        "quality": {
            "status": "ok",
            "flags": [],
            "staleness_seconds": staleness,
            "imputed": False,
        },
        "age_at_cutoff_seconds": (cutoff_dt - built_dt).total_seconds(),
    }
    receipt["receipt_id"] = market_memory._source_receipt_id(receipt)
    return receipt


def build_trusted_packet(
    snapshot: Mapping[str, Any], identity_evidence: Any
) -> market_memory.AsKnownAtContext:
    """Build the only trusted v1 packet admitted by this store profile."""

    from engine.neuralweb import market_memory_identity, market_memory_projection

    clean_snapshot = market_memory_projection.validate_macro_regime_snapshot(snapshot)
    clean_identity = market_memory_identity.validate_canary_identity_evidence(
        identity_evidence
    )
    _snapshot_core(clean_snapshot)
    event_dt, event_time = _parse_utc(
        clean_identity.observed_at, field="identity observed_at"
    )
    snapshot_observed_dt, _snapshot_observed = _parse_utc(
        clean_snapshot["observed_at"], field="snapshot observed_at"
    )
    if snapshot_observed_dt > event_dt:
        raise MarketMemoryTrustedCaptureError(
            "identity observation precedes the macro regime stable read"
        )
    regime_source = _regime_source_receipt(clean_snapshot, as_known_at=event_time)
    source_receipts = [*map(dict, clean_identity.source_receipts), regime_source]
    snapshot_as_of_dt, _snapshot_as_of = _parse_utc(
        clean_snapshot["as_of"], field="snapshot as_of"
    )
    feature_quality = {
        "status": "ok",
        "flags": [],
        "staleness_seconds": (snapshot_observed_dt - snapshot_as_of_dt).total_seconds(),
        "imputed": False,
    }
    feature_receipts = [
        {
            "feature_id": "macro.regime_state",
            "feature_role": "decision_time_context",
            "domain": "macro",
            "status": "observed",
            "value": {
                "snapshot_id": clean_snapshot["snapshot_id"],
                "schema": clean_snapshot["schema"],
                "content_sha256": clean_snapshot["content_sha256"],
                "as_of": clean_snapshot["as_of"],
            },
            "unit": "snapshot_ref",
            "observed_at": clean_snapshot["observed_at"],
            "pit_basis": "live_captured",
            "transform_version": "market_memory.macro_regime_transform.v1",
            "source_receipt_ids": [regime_source["receipt_id"]],
            "missing_reason": None,
            "quality": feature_quality,
        },
        *_missing_features(event_time),
    ]
    try:
        packet = market_memory.build_as_known_at_context(
            subject=clean_identity.subject,
            event_time=event_time,
            as_known_at=event_time,
            mode="operational_pit",
            source_receipts=source_receipts,
            identity_receipt=clean_identity.identity_receipt,
            feature_receipts=feature_receipts,
        )
    except market_memory.TemporalContractError as exc:
        raise MarketMemoryTrustedCaptureError(
            "trusted packet candidate violates the frozen temporal contract"
        ) from exc
    return _validate_trusted_packet(packet)


def _validate_trusted_packet(
    packet: Mapping[str, Any],
) -> market_memory.AsKnownAtContext:
    try:
        clean = market_memory.validate_as_known_at_context(packet)
    except market_memory.TemporalContractError as exc:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet violates the frozen temporal contract"
        ) from exc
    if clean["mode"] != "operational_pit":
        raise market_memory_pit.MarketMemoryStoreError("trusted packet mode drift")
    observed = sorted(
        row["feature_id"]
        for row in clean["feature_receipts"]
        if row["status"] == "observed"
    )
    if observed != list(_ALLOWED_OBSERVED_FEATURE_IDS):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet observed-feature policy drift"
        )
    missing = {
        row["feature_id"]
        for row in clean["feature_receipts"]
        if row["status"] == "missing"
    }
    expected_missing = set(market_memory.CANONICAL_FEATURE_REGISTRY) - set(
        _ALLOWED_OBSERVED_FEATURE_IDS
    )
    if missing != expected_missing:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet missingness closure drift"
        )
    sources_by_id = {row["source_id"]: row for row in clean["source_receipts"]}
    if set(sources_by_id) != {
        "security_master_membership",
        "market_calendar",
        "market_regime_store",
    }:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet source closure drift"
        )
    macro = next(
        row
        for row in clean["feature_receipts"]
        if row["feature_id"] == "macro.regime_state"
    )
    regime_receipt_id = sources_by_id["market_regime_store"]["receipt_id"]
    if macro["source_receipt_ids"] != [regime_receipt_id]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted macro feature source binding drift"
        )
    if clean["identity_receipt"]["membership_status"] != "market_scope":
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted canary membership authority drift"
        )
    if clean["authority"] != dict(market_memory.AUTHORITY):
        raise market_memory_pit.MarketMemoryStoreError("trusted packet authority drift")
    return clean


def _build_receipt(
    *,
    store_id: str,
    packet: Mapping[str, Any],
    packet_sha256: str,
    packet_bytes: int,
    snapshot: Mapping[str, Any],
    identity_evidence: Any,
    captured_at: str,
    deployed_commit: str,
) -> dict[str, Any]:
    query = {
        "subject": copy.deepcopy(packet["subject"]),
        "event_time": packet["clocks"]["event_time"],
        "as_known_at": packet["clocks"]["as_known_at"],
        "mode": packet["mode"],
    }
    query_id = market_memory_pit._query_id(query)
    source_by_id = {row["source_id"]: row for row in packet["source_receipts"]}
    feature_digest = str(snapshot["content_sha256"])
    membership_body = bytes(identity_evidence.membership_artifact_bytes)
    calendar_body = bytes(identity_evidence.calendar_artifact_bytes)
    receipt: dict[str, Any] = {
        "schema": TRUSTED_CAPTURE_RECEIPT_SCHEMA,
        "profile": TRUSTED_STORE_PROFILE,
        "store_id": store_id,
        "capture_id": "",
        "query_id": query_id,
        "context_id": packet["context_id"],
        "packet_sha256": packet_sha256,
        "packet_bytes": packet_bytes,
        "object_key": f"objects/{packet_sha256[:2]}/{packet_sha256}.json",
        "feature_snapshot": {
            "snapshot_id": snapshot["snapshot_id"],
            "schema": snapshot["schema"],
            "content_sha256": feature_digest,
            "content_bytes": snapshot["content_bytes"],
            "object_key": (
                f"feature_objects/{feature_digest[:2]}/{feature_digest}.json"
            ),
            "as_of": snapshot["as_of"],
        },
        "source_evidence": {
            "raw_source_sha256": snapshot["source_artifact"]["raw_sha256"],
            "raw_source_bytes": snapshot["source_artifact"]["raw_bytes"],
            "raw_source_built_at": snapshot["source_artifact"]["built_at"],
            "raw_source_observed_at": snapshot["observed_at"],
            "identity_config_sha256": identity_evidence.config_sha256,
            "membership_artifact_sha256": sha256(membership_body).hexdigest(),
            "membership_artifact_bytes": len(membership_body),
            "calendar_artifact_sha256": sha256(calendar_body).hexdigest(),
            "calendar_artifact_bytes": len(calendar_body),
        },
        "subject": copy.deepcopy(packet["subject"]),
        "clocks": copy.deepcopy(packet["clocks"]),
        "mode": packet["mode"],
        "captured_at": captured_at,
        "deployed_commit": deployed_commit,
        "feature_registry_version": packet["feature_registry_version"],
        "source_registry_version": packet["source_registry_version"],
        "source_receipt_ids": sorted(
            row["receipt_id"] for row in packet["source_receipts"]
        ),
        "source_artifact_sha256s": sorted(
            row["artifact_sha256"] for row in packet["source_receipts"]
        ),
        "observed_feature_ids": list(_ALLOWED_OBSERVED_FEATURE_IDS),
        "missing_feature_ids": sorted(
            row["feature_id"]
            for row in packet["feature_receipts"]
            if row["status"] == "missing"
        ),
        "domain_coverage_sha256": sha256(
            _canonical_bytes(packet["domain_coverage"])
        ).hexdigest(),
        "evidence_policy": copy.deepcopy(_EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    if (
        source_by_id["market_regime_store"]["artifact_sha256"]
        != receipt["source_evidence"]["raw_source_sha256"]
    ):
        raise MarketMemoryTrustedCaptureError(
            "trusted regime receipt does not bind the raw source"
        )
    receipt["capture_id"] = market_memory_pit._capture_id(receipt)
    return _validate_receipt(receipt)


def _validate_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RECEIPT_FIELDS:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture receipt fields are not canonical"
        )
    clean = copy.deepcopy(dict(value))
    if clean.get("schema") != TRUSTED_CAPTURE_RECEIPT_SCHEMA:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture receipt schema mismatch"
        )
    if clean.get("profile") != TRUSTED_STORE_PROFILE:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture profile mismatch"
        )
    store_id = clean.get("store_id")
    capture_id = clean.get("capture_id")
    query_id = clean.get("query_id")
    context_id = clean.get("context_id")
    if not isinstance(store_id, str) or not _STORE_ID.fullmatch(store_id):
        raise market_memory_pit.MarketMemoryStoreError("trusted store_id is malformed")
    if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture_id is malformed"
        )
    if not isinstance(query_id, str) or not _QUERY_ID.fullmatch(query_id):
        raise market_memory_pit.MarketMemoryStoreError("trusted query_id is malformed")
    if not isinstance(context_id, str) or not _CONTEXT_ID.fullmatch(context_id):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted context_id is malformed"
        )
    packet_digest = _require_digest(clean.get("packet_sha256"), field="packet_sha256")
    packet_bytes = _require_exact_int(
        clean.get("packet_bytes"),
        field="packet_bytes",
        minimum=1,
        maximum=market_memory_pit._MAX_PACKET_BYTES,
    )
    del packet_bytes
    if clean.get("object_key") != (f"objects/{packet_digest[:2]}/{packet_digest}.json"):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet object key mismatch"
        )
    snapshot = clean.get("feature_snapshot")
    if not isinstance(snapshot, Mapping) or set(snapshot) != _FEATURE_SNAPSHOT_FIELDS:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted feature snapshot receipt is not canonical"
        )
    snapshot_id = snapshot.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID.fullmatch(snapshot_id):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted snapshot_id is malformed"
        )
    if snapshot.get("schema") != "market_memory.macro_regime_snapshot.v1":
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted feature snapshot schema mismatch"
        )
    feature_digest = _require_digest(
        snapshot.get("content_sha256"), field="feature content_sha256"
    )
    if snapshot_id != f"mmsnap_{feature_digest}":
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted snapshot_id does not bind its content"
        )
    _require_exact_int(
        snapshot.get("content_bytes"),
        field="feature content_bytes",
        minimum=1,
        maximum=_MAX_FEATURE_BYTES,
    )
    if snapshot.get("object_key") != (
        f"feature_objects/{feature_digest[:2]}/{feature_digest}.json"
    ):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted feature object key mismatch"
        )
    _parse_utc(snapshot.get("as_of"), field="feature as_of")
    evidence = clean.get("source_evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != _SOURCE_EVIDENCE_FIELDS:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted source evidence receipt is not canonical"
        )
    for field in (
        "raw_source_sha256",
        "identity_config_sha256",
        "membership_artifact_sha256",
        "calendar_artifact_sha256",
    ):
        _require_digest(evidence.get(field), field=field)
    _require_exact_int(
        evidence.get("raw_source_bytes"),
        field="raw_source_bytes",
        minimum=1,
        maximum=_MAX_PRIVATE_SOURCE_BYTES,
    )
    for field in ("membership_artifact_bytes", "calendar_artifact_bytes"):
        _require_exact_int(
            evidence.get(field), field=field, minimum=1, maximum=64 * 1024
        )
    built_dt, _built = _parse_utc(
        evidence.get("raw_source_built_at"), field="raw source built_at"
    )
    observed_dt, _observed = _parse_utc(
        evidence.get("raw_source_observed_at"), field="raw source observed_at"
    )
    if built_dt > observed_dt:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted raw source was observed before it was built"
        )
    if not isinstance(clean.get("subject"), Mapping) or not isinstance(
        clean.get("clocks"), Mapping
    ):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture query is malformed"
        )
    clocks = clean["clocks"]
    if set(clocks) != {"event_time", "as_known_at", "knowledge_cutoff"}:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture clocks are not canonical"
        )
    if clocks["as_known_at"] != clocks["knowledge_cutoff"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture cutoff clocks disagree"
        )
    try:
        query, _event_dt, cutoff_dt = market_memory_pit._normalize_query(
            subject=clean["subject"],
            event_time=clocks["event_time"],
            as_known_at=clocks["as_known_at"],
            mode=str(clean.get("mode") or ""),
            reject_future_cutoff=False,
        )
    except market_memory_pit.MarketMemoryQueryError as exc:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture query is malformed"
        ) from exc
    if market_memory_pit._query_id(query) != query_id:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted query_id does not bind its query"
        )
    captured_dt, _captured = _parse_utc(clean.get("captured_at"), field="captured_at")
    if captured_dt + _MAX_CLOCK_SKEW < cutoff_dt:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture precedes its cutoff"
        )
    if captured_dt - cutoff_dt > _MAX_CAPTURE_LAG:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture is not contemporaneous"
        )
    deployed_commit = clean.get("deployed_commit")
    if not isinstance(deployed_commit, str) or not _GIT_COMMIT.fullmatch(
        deployed_commit
    ):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted deployed_commit is malformed"
        )
    for field in (
        "source_receipt_ids",
        "source_artifact_sha256s",
        "observed_feature_ids",
        "missing_feature_ids",
    ):
        values = clean.get(field)
        if (
            not isinstance(values, list)
            or values != sorted(set(values))
            or not all(isinstance(row, str) for row in values)
        ):
            raise market_memory_pit.MarketMemoryStoreError(
                f"trusted capture {field} is not canonical"
            )
    if clean["observed_feature_ids"] != list(_ALLOWED_OBSERVED_FEATURE_IDS):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture observed-feature policy drift"
        )
    expected_missing = sorted(
        set(market_memory.CANONICAL_FEATURE_REGISTRY)
        - set(_ALLOWED_OBSERVED_FEATURE_IDS)
    )
    if clean["missing_feature_ids"] != expected_missing:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture missingness policy drift"
        )
    _require_digest(clean.get("domain_coverage_sha256"), field="domain coverage digest")
    if clean.get("evidence_policy") != _EVIDENCE_POLICY:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture evidence policy drift"
        )
    if clean.get("authority") != dict(market_memory.AUTHORITY):
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture authority drift"
        )
    if market_memory_pit._capture_id(clean) != capture_id:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture_id does not bind its receipt"
        )
    return clean


def _validate_receipt_against_packet(
    receipt: Mapping[str, Any], packet: Mapping[str, Any]
) -> None:
    if receipt["context_id"] != packet["context_id"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet context differs from its receipt"
        )
    if receipt["subject"] != packet["subject"] or receipt["clocks"] != packet["clocks"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet query differs from its receipt"
        )
    if receipt["feature_registry_version"] != packet["feature_registry_version"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet feature registry differs from its receipt"
        )
    if receipt["source_registry_version"] != packet["source_registry_version"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet source registry differs from its receipt"
        )
    source_ids = sorted(row["receipt_id"] for row in packet["source_receipts"])
    source_digests = sorted(row["artifact_sha256"] for row in packet["source_receipts"])
    missing_ids = sorted(
        row["feature_id"]
        for row in packet["feature_receipts"]
        if row["status"] == "missing"
    )
    if source_ids != receipt["source_receipt_ids"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet source receipts differ from its capture"
        )
    if source_digests != receipt["source_artifact_sha256s"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet source artifacts differ from its capture"
        )
    if missing_ids != receipt["missing_feature_ids"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet missingness differs from its capture"
        )
    coverage_digest = sha256(_canonical_bytes(packet["domain_coverage"])).hexdigest()
    if coverage_digest != receipt["domain_coverage_sha256"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet domain coverage differs from its capture"
        )
    macro = next(
        row
        for row in packet["feature_receipts"]
        if row["feature_id"] == "macro.regime_state"
    )
    if macro["value"] != {
        "snapshot_id": receipt["feature_snapshot"]["snapshot_id"],
        "schema": receipt["feature_snapshot"]["schema"],
        "content_sha256": receipt["feature_snapshot"]["content_sha256"],
        "as_of": receipt["feature_snapshot"]["as_of"],
    }:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet feature reference differs from its capture"
        )


def _load_stored(
    root: Path, receipt: Mapping[str, Any], *, store_id: str
) -> market_memory_pit.StoredMarketMemoryContext:
    clean_receipt = _validate_receipt(receipt)
    if clean_receipt["store_id"] != store_id:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted capture belongs to another store"
        )
    packet, packet_body = market_memory_pit._read_canonical_object(
        market_memory_pit._object_path(root, clean_receipt["packet_sha256"]),
        limit=market_memory_pit._MAX_PACKET_BYTES,
        label="trusted packet object",
    )
    if sha256(packet_body).hexdigest() != clean_receipt["packet_sha256"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet object digest mismatch"
        )
    if len(packet_body) != clean_receipt["packet_bytes"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted packet object byte count mismatch"
        )
    clean_packet = _validate_trusted_packet(packet)
    _validate_receipt_against_packet(clean_receipt, clean_packet)
    feature_digest = clean_receipt["feature_snapshot"]["content_sha256"]
    _feature, feature_body = market_memory_pit._read_canonical_object(
        _feature_path(root, feature_digest),
        limit=_MAX_FEATURE_BYTES,
        label="trusted feature object",
    )
    if sha256(feature_body).hexdigest() != feature_digest:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted feature object digest mismatch"
        )
    if len(feature_body) != clean_receipt["feature_snapshot"]["content_bytes"]:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted feature object byte count mismatch"
        )
    return market_memory_pit.StoredMarketMemoryContext(clean_packet, clean_receipt)


def _existing_evidence_capture(
    root: Path,
    generation: Mapping[str, Any],
    *,
    raw_source_sha256: str,
    identity_config_sha256: str,
    feature_content_sha256: str,
) -> dict[str, Any] | None:
    """Return one already-published capture for identical trusted inputs."""

    matches: list[dict[str, Any]] = []
    for entry in generation["captures"]:
        receipt, _body = market_memory_pit._read_canonical_object(
            market_memory_pit._context_path(root, entry["context_id"]),
            limit=_MAX_RECEIPT_BYTES,
            label="trusted idempotency receipt",
        )
        clean = _validate_receipt(receipt)
        if market_memory_pit._capture_entry(clean) != dict(entry):
            raise market_memory_pit.MarketMemoryStoreError(
                "trusted idempotency receipt differs from generation"
            )
        evidence = clean["source_evidence"]
        if (
            evidence["raw_source_sha256"] == raw_source_sha256
            and evidence["identity_config_sha256"] == identity_config_sha256
            and clean["feature_snapshot"]["content_sha256"] == feature_content_sha256
        ):
            matches.append(clean)
    if len(matches) > 1:
        raise market_memory_pit.MarketMemoryStoreError(
            "trusted generation contains duplicate identical evidence captures"
        )
    return matches[0] if matches else None


class TrustedFileAsKnownAtReader(market_memory.AsKnownAtReader):
    """Exact reader over the separate authenticated-feature store."""

    def __init__(self, root: str | Path, *, mode: str = "operational_pit") -> None:
        self.root = validate_trusted_store_root(root)
        if mode != "operational_pit":
            raise market_memory_pit.MarketMemoryQueryError(
                "trusted reader supports operational_pit only"
            )
        self.mode = mode

    def read_stored_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> market_memory_pit.StoredMarketMemoryContext:
        query, _event_dt, _cutoff_dt = market_memory_pit._normalize_query(
            subject=subject,
            event_time=event_time,
            as_known_at=as_known_at,
            mode=self.mode,
            reject_future_cutoff=True,
        )
        query_id = market_memory_pit._query_id(query)
        state = _load_state(self.root)
        entry = market_memory_pit._generation_entry(
            state.generation, field="query_id", value=query_id
        )
        if entry is None:
            raise market_memory_pit.MarketMemoryContextNotFound(
                "exact query is absent from the trusted active generation"
            )
        receipt, receipt_body = market_memory_pit._read_canonical_object(
            market_memory_pit._query_path(self.root, query_id),
            limit=_MAX_RECEIPT_BYTES,
            label="trusted query receipt",
        )
        clean_receipt = _validate_receipt(receipt)
        if market_memory_pit._capture_entry(clean_receipt) != entry:
            raise market_memory_pit.MarketMemoryStoreError(
                "trusted query receipt differs from generation"
            )
        context_receipt, context_body = market_memory_pit._read_canonical_object(
            market_memory_pit._context_path(self.root, clean_receipt["context_id"]),
            limit=_MAX_RECEIPT_BYTES,
            label="trusted context receipt",
        )
        if context_body != receipt_body or context_receipt != receipt:
            raise market_memory_pit.MarketMemoryStoreError(
                "trusted query and context receipts disagree"
            )
        return _load_stored(
            self.root, clean_receipt, store_id=state.manifest["store_id"]
        )

    def read_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> market_memory.AsKnownAtContext:
        return self.read_stored_as_known_at(
            subject=subject, event_time=event_time, as_known_at=as_known_at
        ).packet

    def read_stored_context_id(
        self, context_id: str
    ) -> market_memory_pit.StoredMarketMemoryContext:
        market_memory_pit._context_path(self.root, context_id)
        state = _load_state(self.root)
        entry = market_memory_pit._generation_entry(
            state.generation, field="context_id", value=context_id
        )
        if entry is None:
            raise market_memory_pit.MarketMemoryContextNotFound(
                "context is absent from the trusted active generation"
            )
        receipt, context_body = market_memory_pit._read_canonical_object(
            market_memory_pit._context_path(self.root, context_id),
            limit=_MAX_RECEIPT_BYTES,
            label="trusted context receipt",
        )
        clean_receipt = _validate_receipt(receipt)
        if market_memory_pit._capture_entry(clean_receipt) != entry:
            raise market_memory_pit.MarketMemoryStoreError(
                "trusted context receipt differs from generation"
            )
        query_receipt, query_body = market_memory_pit._read_canonical_object(
            market_memory_pit._query_path(self.root, clean_receipt["query_id"]),
            limit=_MAX_RECEIPT_BYTES,
            label="trusted query receipt",
        )
        if query_body != context_body or query_receipt != receipt:
            raise market_memory_pit.MarketMemoryStoreError(
                "trusted context is not published by its query receipt"
            )
        return _load_stored(
            self.root, clean_receipt, store_id=state.manifest["store_id"]
        )


class CompositeAsKnownAtReader(market_memory.AsKnownAtReader):
    """Exact federation over trusted observed packets and W1A missingness."""

    def __init__(
        self,
        w1a_root: str | Path,
        trusted_root: str | Path,
        *,
        mode: str = "operational_pit",
    ) -> None:
        self.w1a = market_memory_pit.FileAsKnownAtReader(w1a_root, mode=mode)
        self.trusted = TrustedFileAsKnownAtReader(trusted_root, mode=mode)
        self.mode = mode

    @staticmethod
    def _resolve(
        trusted: market_memory_pit.StoredMarketMemoryContext | None,
        w1a: market_memory_pit.StoredMarketMemoryContext | None,
    ) -> market_memory_pit.StoredMarketMemoryContext:
        if trusted is None and w1a is None:
            raise market_memory_pit.MarketMemoryContextNotFound(
                "exact context is absent from both complete generations"
            )
        if trusted is not None and w1a is not None:
            if _canonical_bytes(trusted.packet) != _canonical_bytes(w1a.packet):
                raise market_memory_pit.MarketMemoryStoreError(
                    "exact query is ambiguously published by both stores"
                )
            return trusted
        return trusted if trusted is not None else w1a  # type: ignore[return-value]

    def read_stored_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> market_memory_pit.StoredMarketMemoryContext:
        found: list[market_memory_pit.StoredMarketMemoryContext | None] = []
        for reader in (self.trusted, self.w1a):
            try:
                found.append(
                    reader.read_stored_as_known_at(
                        subject=subject,
                        event_time=event_time,
                        as_known_at=as_known_at,
                    )
                )
            except market_memory_pit.MarketMemoryContextNotFound:
                found.append(None)
        return self._resolve(found[0], found[1])

    def read_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> market_memory.AsKnownAtContext:
        return self.read_stored_as_known_at(
            subject=subject, event_time=event_time, as_known_at=as_known_at
        ).packet

    def read_stored_context_id(
        self, context_id: str
    ) -> market_memory_pit.StoredMarketMemoryContext:
        found: list[market_memory_pit.StoredMarketMemoryContext | None] = []
        for reader in (self.trusted, self.w1a):
            try:
                found.append(reader.read_stored_context_id(context_id))
            except market_memory_pit.MarketMemoryContextNotFound:
                found.append(None)
        return self._resolve(found[0], found[1])


def initialize_trusted_store(public_root: str | Path) -> dict[str, Any]:
    """Create or validate the complete empty trusted generation.

    Deployment calls this before projection so the API can distinguish a
    proven exact miss from an unavailable store even when the current source
    correctly fails a strict intake check.  It publishes no context or feature.
    """

    public = validate_trusted_store_root(public_root)
    market_memory_pit._mkdir_durable(public)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(public, flags)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        state = _initialize_or_load(public)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return {
        "schema": state.manifest["schema"],
        "store_id": state.manifest["store_id"],
        "generation_id": state.generation["generation_id"],
        "capture_count": len(state.generation["captures"]),
    }


def capture_trusted_regime_context(
    public_root: str | Path,
    private_root: str | Path,
    *,
    snapshot: Mapping[str, Any],
    identity_evidence: Any,
    raw_source_body: bytes,
    deployed_commit: str,
) -> market_memory_pit.StoredMarketMemoryContext:
    """Publish one current SPY regime packet through the sole trusted writer."""

    from engine.neuralweb import market_memory_identity, market_memory_projection

    clean_snapshot = market_memory_projection.validate_macro_regime_snapshot(snapshot)
    clean_identity = market_memory_identity.validate_canary_identity_evidence(
        identity_evidence
    )
    _feature_core, feature_body = _snapshot_core(clean_snapshot)
    if not isinstance(raw_source_body, bytes):
        raise MarketMemoryTrustedCaptureError("raw regime source must be exact bytes")
    raw_digest = sha256(raw_source_body).hexdigest()
    if (
        raw_digest != clean_snapshot["source_artifact"]["raw_sha256"]
        or len(raw_source_body) != clean_snapshot["source_artifact"]["raw_bytes"]
    ):
        raise MarketMemoryTrustedCaptureError(
            "raw regime source differs from the projected stable read"
        )
    if not isinstance(deployed_commit, str) or not _GIT_COMMIT.fullmatch(
        deployed_commit
    ):
        raise MarketMemoryTrustedCaptureError("deployed commit is malformed")
    packet = build_trusted_packet(clean_snapshot, clean_identity)
    packet_digest, packet_body = market_memory_pit._packet_sha256(packet)
    captured_dt = _utc_now().astimezone(timezone.utc)
    cutoff_dt, _cutoff = _parse_utc(
        packet["clocks"]["as_known_at"], field="packet as_known_at"
    )
    if captured_dt + _MAX_CLOCK_SKEW < cutoff_dt or (
        captured_dt - cutoff_dt > _MAX_CAPTURE_LAG
    ):
        raise MarketMemoryTrustedCaptureError(
            "trusted packet capture is not contemporaneous"
        )
    captured_at = captured_dt.isoformat().replace("+00:00", "Z")
    public = validate_trusted_store_root(public_root)
    private = validate_trusted_store_root(private_root)
    _validate_disjoint_roots(public, private)
    market_memory_pit._mkdir_durable(public)
    market_memory_pit._mkdir_durable(private)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    lock_descriptor = os.open(public, flags)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        state = _initialize_or_load(public)
        existing_evidence = _existing_evidence_capture(
            public,
            state.generation,
            raw_source_sha256=raw_digest,
            identity_config_sha256=clean_identity.config_sha256,
            feature_content_sha256=clean_snapshot["content_sha256"],
        )
        if existing_evidence is not None:
            return TrustedFileAsKnownAtReader(public).read_stored_context_id(
                existing_evidence["context_id"]
            )
        receipt = _build_receipt(
            store_id=state.manifest["store_id"],
            packet=packet,
            packet_sha256=packet_digest,
            packet_bytes=len(packet_body),
            snapshot=clean_snapshot,
            identity_evidence=clean_identity,
            captured_at=captured_at,
            deployed_commit=deployed_commit,
        )
        receipt_body = _canonical_bytes(receipt)
        if len(receipt_body) > _MAX_RECEIPT_BYTES:
            raise MarketMemoryTrustedCaptureError(
                "trusted capture receipt exceeds its byte bound"
            )
        active = market_memory_pit._generation_entry(
            state.generation, field="query_id", value=receipt["query_id"]
        )
        if active is not None:
            if (
                active["packet_sha256"] != packet_digest
                or active["context_id"] != packet["context_id"]
            ):
                raise MarketMemoryTrustedCaptureError(
                    "trusted query already has a different immutable capture"
                )
            return TrustedFileAsKnownAtReader(public).read_stored_as_known_at(
                subject=packet["subject"],
                event_time=packet["clocks"]["event_time"],
                as_known_at=packet["clocks"]["as_known_at"],
            )
        context_path = market_memory_pit._context_path(public, packet["context_id"])
        query_path = market_memory_pit._query_path(public, receipt["query_id"])
        if query_path.exists() and not context_path.exists():
            raise market_memory_pit.MarketMemoryStoreError(
                "trusted query receipt exists without its context receipt"
            )
        if context_path.exists() or context_path.is_symlink():
            existing, existing_body = market_memory_pit._read_canonical_object(
                context_path,
                limit=_MAX_RECEIPT_BYTES,
                label="orphan trusted context receipt",
            )
            clean_existing = _validate_receipt(existing)
            if (
                clean_existing["store_id"] != state.manifest["store_id"]
                or clean_existing["query_id"] != receipt["query_id"]
                or clean_existing["context_id"] != packet["context_id"]
                or clean_existing["packet_sha256"] != packet_digest
                or clean_existing["feature_snapshot"]["content_sha256"]
                != clean_snapshot["content_sha256"]
                or clean_existing["source_evidence"]["raw_source_sha256"] != raw_digest
                or clean_existing["source_evidence"]["identity_config_sha256"]
                != clean_identity.config_sha256
            ):
                raise MarketMemoryTrustedCaptureError(
                    "immutable trusted context receipt collision"
                )
            # A context receipt is written only after the private evidence,
            # feature object, and packet. Validate all public bytes plus the
            # private receipt before retaining the original system capture
            # clock and completing a crash-interrupted generation publish.
            _load_stored(
                public,
                clean_existing,
                store_id=state.manifest["store_id"],
            )
            private_receipt, private_receipt_body = (
                market_memory_pit._read_canonical_object(
                    _private_receipt_path(private, clean_existing["capture_id"]),
                    limit=_MAX_RECEIPT_BYTES,
                    label="orphan private trusted capture receipt",
                )
            )
            if (
                private_receipt != clean_existing
                or private_receipt_body != existing_body
            ):
                raise market_memory_pit.MarketMemoryStoreError(
                    "private and public trusted capture receipts disagree"
                )
            if query_path.exists() or query_path.is_symlink():
                existing_query, existing_query_body = (
                    market_memory_pit._read_canonical_object(
                        query_path,
                        limit=_MAX_RECEIPT_BYTES,
                        label="orphan trusted query receipt",
                    )
                )
                if (
                    existing_query != clean_existing
                    or existing_query_body != existing_body
                ):
                    raise market_memory_pit.MarketMemoryStoreError(
                        "orphan trusted query and context receipts disagree"
                    )
            receipt = clean_existing
            receipt_body = existing_body
        if len(state.generation["captures"]) >= _MAX_GENERATION_CAPTURES:
            raise MarketMemoryTrustedCaptureError(
                "trusted store generation reached its pilot bound"
            )
        preview = market_memory_pit._new_generation(
            store_id=state.manifest["store_id"],
            previous_generation_id=state.generation["generation_id"],
            captures=[
                *[dict(row) for row in state.generation["captures"]],
                market_memory_pit._capture_entry(receipt),
            ],
        )
        if len(_canonical_bytes(preview)) > _MAX_GENERATION_BYTES:
            raise MarketMemoryTrustedCaptureError(
                "trusted store generation exceeds its byte bound"
            )

        membership_body = bytes(clean_identity.membership_artifact_bytes)
        calendar_body = bytes(clean_identity.calendar_artifact_bytes)
        membership_digest = sha256(membership_body).hexdigest()
        calendar_digest = sha256(calendar_body).hexdigest()
        # Private exact evidence is durable before the public packet can become
        # reachable.  These raw bytes are never mounted into the API namespace.
        _write_exact_bytes_create_once(
            private,
            _private_object_path(private, "raw", raw_digest),
            raw_source_body,
            label="raw regime object",
            limit=_MAX_PRIVATE_SOURCE_BYTES,
        )
        _write_exact_bytes_create_once(
            private,
            _private_object_path(private, "membership", membership_digest),
            membership_body,
            label="membership evidence object",
            limit=64 * 1024,
        )
        _write_exact_bytes_create_once(
            private,
            _private_object_path(private, "calendar", calendar_digest),
            calendar_body,
            label="calendar evidence object",
            limit=64 * 1024,
        )
        market_memory_pit._write_create_once(
            private,
            _private_receipt_path(private, receipt["capture_id"]),
            receipt_body,
            label="private trusted capture receipt",
        )
        market_memory_pit._write_create_once(
            public,
            _feature_path(public, clean_snapshot["content_sha256"]),
            feature_body,
            label="trusted feature object",
        )
        market_memory_pit._write_create_once(
            public,
            market_memory_pit._object_path(public, packet_digest),
            packet_body,
            label="trusted packet object",
        )
        market_memory_pit._write_create_once(
            public,
            context_path,
            receipt_body,
            label="trusted context receipt",
        )
        market_memory_pit._write_create_once(
            public,
            query_path,
            receipt_body,
            label="trusted query receipt",
        )
        generation = market_memory_pit._new_generation(
            store_id=state.manifest["store_id"],
            previous_generation_id=state.generation["generation_id"],
            captures=[
                *[dict(row) for row in state.generation["captures"]],
                market_memory_pit._capture_entry(receipt),
            ],
        )
        generation_body = _canonical_bytes(generation)
        market_memory_pit._write_create_once(
            public,
            market_memory_pit._generation_path(public, generation["generation_id"]),
            generation_body,
            label="trusted store generation",
        )
        head = market_memory_pit._new_head(generation, generation_body=generation_body)
        market_memory_pit._replace_head(public, head)
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)
    return TrustedFileAsKnownAtReader(public).read_stored_as_known_at(
        subject=packet["subject"],
        event_time=packet["clocks"]["event_time"],
        as_known_at=packet["clocks"]["as_known_at"],
    )


def default_trusted_store_root(repository_root: str | Path) -> Path:
    repository = Path(repository_root).expanduser().resolve()
    override = os.environ.get("MARKET_MEMORY_TRUSTED_STORE_DIR", "").strip()
    candidate = (
        Path(override).expanduser().resolve()
        if override
        else (
            Path("/var/lib/macro-market-memory/public/trusted-v1")
            if repository == Path("/opt/macro")
            else repository / "data" / "neuralweb" / "market_memory" / "trusted-v1"
        )
    )
    return validate_trusted_store_root(candidate, repository_root=repository)


def default_private_evidence_root(repository_root: str | Path) -> Path:
    repository = Path(repository_root).expanduser().resolve()
    override = os.environ.get("MARKET_MEMORY_CONTEXT_PROJECTION_DIR", "").strip()
    candidate = (
        Path(override).expanduser().resolve()
        if override
        else Path("/var/lib/macro-market-memory/state/context-projection")
    )
    return validate_trusted_store_root(candidate, repository_root=repository)
