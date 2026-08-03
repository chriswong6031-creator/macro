"""Operator-armed B1 BioCatalyst ClinicalTrials.gov evidence worker.

This is intentionally a narrow source-fact lane.  It never reads shared R2
credentials, never gives the collector the real public root, and advances a
single public pointer only after source artifacts have been retained and read
back from the dedicated BioCatalyst object store.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from typing import Any, Callable, Iterator, Mapping, Protocol
import uuid

import yaml

from engine.biocatalyst.activation import (
    ActivationError,
    activation_target_binding_sha256,
    validate_activation_gate,
    validate_activation_heartbeat,
)
from engine.biocatalyst.publication import (
    CommittedGeneration,
    HistoryPublicationEvidence,
    ProspectivePublicationEvidence,
    PublicationError,
    PublicGenerationPublisher,
    archive_failed_attempt,
    archive_private_stage,
    assert_source_timestamp_monotonic,
    assert_source_timestamp_not_future,
    build_private_mirror_manifest,
    failure_health,
    mirror_private_receipt,
    success_health,
    validate_candidate_run,
    write_private_incident,
)
from engine.biocatalyst.prospective import (
    ProspectiveError,
    SourceEvidence as ProspectiveSourceEvidence,
    build_coverage_epoch,
    build_exact_diff as build_prospective_exact_diff,
    build_observation as build_prospective_observation,
    build_public_model as build_prospective_public_model,
    build_public_event as build_prospective_public_event,
    validate_public_model as validate_prospective_public_model,
)
from engine.biocatalyst.history import (
    build_history_exact_diff,
    build_history_read_model,
    build_unavailable_history_read_model,
    derive_history_change_facts,
)
from engine.biocatalyst.storage import (
    BinaryObjectStore,
    DedicatedR2Config,
    DedicatedR2Store,
    StorageError,
    mirror_tree_verified,
)
from engine.sector_intelligence import (
    build_ctgov_publication_context,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_ctgov_publication_bundle,
    validate_contract,
    validate_ctgov_history_receipt_against_raw_response,
    validate_ctgov_history_run_against_receipts,
    validate_trial_history_diff_against_snapshots,
    validate_trial_registry_change_fact_against_diff,
    validate_trial_history_snapshot_against_evidence,
    validate_trial_observation_against_source_evidence,
)


EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_MISCONFIGURED = 2

_NCT_RE = re.compile(r"^NCT[0-9]{8}$")
_SOURCE_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})?$"
)
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_HISTORY_RUN_ID_RE = re.compile(r"^ctgov_history_run_NCT[0-9]{8}_[A-Za-z0-9_-]+$")
_HISTORY_SNAPSHOT_ID_RE = re.compile(r"^ctgov_history_snapshot_[A-Za-z0-9_-]+$")
_SERVICE_STATE_ROOT = Path("/var/lib/macro-biocatalyst/state")
_SERVICE_PUBLIC_ROOT = Path("/var/lib/macro-biocatalyst/public")
_SERVICE_ACTIVATION_GATE_PATH = Path(
    "/var/lib/macro-biocatalyst/activation/gate.json"
)
_SERVICE_ACTIVATION_HEARTBEAT_PATH = Path(
    "/var/lib/macro-biocatalyst/activation/heartbeat.json"
)
_SOURCE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "biocatalyst_sources.yml"
_ACTIVATION_ID_RE = re.compile(r"^r2_activation_[a-f0-9]{24}$")
_R2_ACCOUNT_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_R2_JURISDICTIONS = frozenset({"default", "eu", "fedramp"})
_ACTIVATION_ARTIFACT_MAX_BYTES = 64 * 1024
_SAFE_ERROR_CODES = frozenset(
    {
        "ARCHIVE_READBACK_MISMATCH",
        "BIOCATALYST_CANARY_NCTS_INVALID",
        "BIOCATALYST_ENABLED_INVALID",
        "BIOCATALYST_HISTORY_ENABLED_INVALID",
        "BIOCATALYST_HISTORY_SOURCE_NOT_APPROVED",
        "BIOCATALYST_R2_BUCKET_INVALID",
        "BIOCATALYST_R2_CLIENT_UNAVAILABLE",
        "BIOCATALYST_R2_CONFIG_MISSING",
        "BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED",
        "BIOCATALYST_R2_CONDITIONAL_CREATE_UNAVAILABLE",
        "BIOCATALYST_R2_ENDPOINT_INVALID",
        "BIOCATALYST_R2_READBACK_FAILED",
        "BIOCATALYST_R2_READBACK_MISMATCH",
        "BIOCATALYST_R2_READ_FAILED",
        "BIOCATALYST_R2_RETENTION_CONFIRMED_INVALID",
        "BIOCATALYST_R2_RETENTION_NOT_CONFIRMED",
        "BIOCATALYST_R2_ACTIVATION_GATE_INVALID",
        "BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID",
        "BIOCATALYST_R2_ACTIVATION_HEARTBEAT_STALE",
        "BIOCATALYST_R2_ACTIVATION_RECEIPT_COLLISION",
        "BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID",
        "BIOCATALYST_R2_ACTIVATION_TIME_INVALID",
        "BIOCATALYST_R2_CONTROL_CONFIG_INVALID",
        "BIOCATALYST_R2_CONTROL_PLANE_UNAVAILABLE",
        "BIOCATALYST_R2_CONTROL_RESPONSE_INVALID",
        "BIOCATALYST_R2_DATA_PLANE_INVALID",
        "BIOCATALYST_R2_LIFECYCLE_DELETE_PRESENT",
        "BIOCATALYST_R2_RETENTION_LOCK_MISSING",
        "BIOCATALYST_R2_RETENTION_LOCK_SCOPE_INVALID",
        "BIOCATALYST_R2_WORKER_TOKEN_INVALID",
        "BIOCATALYST_R2_WORKER_TOKEN_SCOPE_INVALID",
        "BIOCATALYST_RUNTIME_PATH_INVALID",
        "BIOCATALYST_USER_AGENT_INVALID",
        "BIOCATALYST_PROSPECTIVE_DOWNGRADE_FORBIDDEN",
        "BIOCATALYST_PROSPECTIVE_ENABLED_INVALID",
        "COLLECTION_FAILED",
        "COLLECTOR_INCIDENT_PRESENT",
        "COLLECTOR_BINDING_MISMATCH",
        "COLLECTOR_COUNTS_MISMATCH",
        "COLLECTOR_GENERATION_MISSING",
        "COLLECTOR_GENERATION_OUTSIDE_STAGE",
        "COLLECTOR_GENERATION_UNSAFE",
        "COLLECTOR_MANIFEST_HASH_MISMATCH",
        "COLLECTOR_MANIFEST_INVALID",
        "COLLECTOR_PROJECTION_HASH_MISMATCH",
        "COLLECTOR_PROJECTION_INVALID",
        "COLLECTOR_PROJECTION_UNSAFE",
        "CONTRACT_VALIDATION_FAILED",
        "COUNT_MISMATCH",
        "CTGOV_WIRE_BINDING_INVALID",
        "DIVERGENT_DUPLICATE",
        "GENERATION_HEALTH_BINDING_MISMATCH",
        "HEALTH_PAYLOAD_INVALID",
        "HTTP_REQUEST_FAILED",
        "IMMUTABLE_OBJECT_COLLISION",
        "INVALID_PAGE_TOKEN",
        "INVALID_SOURCE_JSON",
        "INVALID_SOURCE_SHAPE",
        "INVALID_SOURCE_VERSION",
        "INVALID_STUDY_IDENTITY",
        "PAGE_CAP_EXHAUSTED",
        "PAGINATION_CYCLE",
        "POINTER_STATE_UNCERTAIN",
        "POINTER_WRITE_FAILED",
        "PRIVATE_ARCHIVE_COLLISION",
        "PRIVATE_ARTIFACTS_MISSING",
        "PRIVATE_ARTIFACT_UNREADABLE",
        "PRIVATE_STAGE_INVALID",
        "PUBLIC_GENERATION_ARTIFACT_MISMATCH",
        "PUBLIC_GENERATION_COLLISION",
        "PUBLIC_GENERATION_HASH_MISMATCH",
        "PUBLIC_GENERATION_INVALID",
        "PUBLIC_POINTER_INVALID",
        "PUBLIC_SNAPSHOT_BINDING_MISMATCH",
        "PUBLIC_STAGE_COLLISION",
        "PUBLIC_STAGE_MISSING",
        "PROSPECTIVE_BASELINE_INVALID",
        "PROSPECTIVE_DIFF_INVALID",
        "PROSPECTIVE_DIFF_STATE_INVALID",
        "PROSPECTIVE_EPOCH_INVALID",
        "PROSPECTIVE_EVENT_COLLISION",
        "PROSPECTIVE_IDENTITY_INVALID",
        "PROSPECTIVE_INTERVAL_INVALID",
        "PROSPECTIVE_MODEL_BINDING_INVALID",
        "PROSPECTIVE_MODEL_HASH_MISMATCH",
        "PROSPECTIVE_MODEL_INVALID",
        "PROSPECTIVE_MODEL_LIMIT_EXCEEDED",
        "PROSPECTIVE_OBSERVATION_INVALID",
        "PROSPECTIVE_PRIOR_EVIDENCE_MISSING",
        "PROSPECTIVE_PRIOR_MIRROR_INVALID",
        "PROSPECTIVE_PRIVATE_ARCHIVE_INVALID",
        "PROSPECTIVE_PUBLICATION_EVIDENCE_INVALID",
        "PROSPECTIVE_SCOPE_INVALID",
        "PROSPECTIVE_SOURCE_EVIDENCE_INVALID",
        "PROSPECTIVE_TIME_INVALID",
        "PROSPECTIVE_VALUE_INVALID",
        "RUN_CONTRACT_INVALID",
        "RUN_ID_INVALID",
        "RUN_NOT_COMPLETE",
        "RUN_NOT_REPLAYABLE",
        "RAW_EVIDENCE_INVALID",
        "RECEIPT_ID_MISMATCH",
        "REPLAY_DIVERGENCE",
        "SOURCE_CHANGED_MID_RUN",
        "SOURCE_TIMESTAMP_FUTURE",
        "SOURCE_TIMESTAMP_INCOMPARABLE",
        "SOURCE_TIMESTAMP_INCONSISTENT",
        "SOURCE_TIMESTAMP_INVALID",
        "SOURCE_TIMESTAMP_REGRESSION",
        "TRIAL_PROJECTION_BINDING_MISMATCH",
        "TRIAL_PROJECTION_INVALID",
        "TRIAL_PROSPECTIVE_EVIDENCE_BINDING_MISMATCH",
        "TRIAL_PROSPECTIVE_EVIDENCE_INVALID",
        "TRIAL_PROSPECTIVE_PROJECTION_BINDING_MISMATCH",
        "TRIAL_PROSPECTIVE_PROJECTION_INVALID",
        "UNEXPECTED_HTTP_STATUS",
        "UNSAFE_OBJECT_KEY",
        "UNSAFE_PRIVATE_ARTIFACT",
        "UNSUPPORTED_CODE_VERSION",
        "UNSUPPORTED_CONTENT_ENCODING",
        "WATERMARK_BINDING_MISMATCH",
        "WATERMARK_INVALID",
        "WORKER_CANARY_BINDING_MISMATCH",
        "WORKER_MODE_BINDING_MISMATCH",
    }
)
_TRANSIENT_AVAILABILITY_CODES = frozenset(
    {
        "BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED",
        "BIOCATALYST_R2_READBACK_FAILED",
        "BIOCATALYST_R2_READ_FAILED",
        "HTTP_REQUEST_FAILED",
        "POINTER_WRITE_FAILED",
        "UNEXPECTED_HTTP_STATUS",
    }
)
# Partial is deliberately a tiny, explicit availability class.  Every other
# known error is an integrity, provenance, immutability, configuration, or
# trust-boundary failure and therefore requires quarantine by default.
_QUARANTINE_CODES = _SAFE_ERROR_CODES - _TRANSIENT_AVAILABILITY_CODES


class WorkerConfigError(RuntimeError):
    """Bounded configuration failure with no value/secret in its message."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _validated_root_pair(state_root: Path, public_root: Path) -> tuple[Path, Path]:
    """Validate a disjoint local state/public pair without creating either path."""

    raw_state_root = Path(state_root)
    raw_public_root = Path(public_root)
    if (
        not raw_state_root.is_absolute()
        or not raw_public_root.is_absolute()
        or raw_state_root.is_symlink()
        or raw_public_root.is_symlink()
    ):
        raise WorkerConfigError("BIOCATALYST_RUNTIME_PATH_INVALID")
    state = raw_state_root.resolve()
    public = raw_public_root.resolve()
    if state == public:
        raise WorkerConfigError("BIOCATALYST_RUNTIME_PATH_INVALID")
    try:
        state.relative_to(public)
        raise WorkerConfigError("BIOCATALYST_RUNTIME_PATH_INVALID")
    except ValueError:
        pass
    try:
        public.relative_to(state)
        raise WorkerConfigError("BIOCATALYST_RUNTIME_PATH_INVALID")
    except ValueError:
        pass
    return state, public


def _ensure_real_directory(path: Path) -> None:
    """Create one direct anchor or reject a symlink/non-directory in its place."""

    candidate = Path(path)
    if candidate.is_symlink():
        raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID")
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        try:
            candidate.mkdir(mode=0o700)
            metadata = candidate.lstat()
        except (FileExistsError, OSError) as exc:
            raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID") from exc
    except OSError as exc:
        raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID")


def _prepare_runtime_layout(config: "WorkerConfig") -> None:
    """Fail closed on hostile fixed anchors before collector or R2 activity."""

    for root in (config.state_root, config.public_root):
        if root.is_symlink():
            raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID")
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID") from exc
        _ensure_real_directory(root)
    for anchor in (
        config.state_root / "staging",
        config.state_root / "committed",
        config.state_root / "dead-letter",
        config.public_root / "generations",
    ):
        _ensure_real_directory(anchor)

    lock_path = config.state_root / "biocatalyst_worker.lock"
    if lock_path.is_symlink():
        raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID")
    try:
        metadata = lock_path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID")


@dataclass(frozen=True)
class WorkerConfig:
    state_root: Path
    public_root: Path
    nct_ids: tuple[str, ...]
    user_agent: str
    r2: DedicatedR2Config
    history_enabled: bool = False
    prospective_enabled: bool = False
    r2_retention_confirmed: bool = False
    activation_id: str | None = None
    activation_gate_path: Path | None = None
    activation_heartbeat_path: Path | None = None
    r2_account_id: str | None = None
    r2_jurisdiction: str = "default"
    activation_owner_uid: int = 0
    activation_group_gid: int | None = None

    def __post_init__(self) -> None:
        state_root, public_root = _validated_root_pair(self.state_root, self.public_root)
        if (
            not self.nct_ids
            or tuple(sorted(self.nct_ids)) != self.nct_ids
            or len(set(self.nct_ids)) != len(self.nct_ids)
            or any(not _NCT_RE.fullmatch(nct_id) for nct_id in self.nct_ids)
        ):
            raise WorkerConfigError("BIOCATALYST_CANARY_NCTS_INVALID")
        if len(self.user_agent.strip()) < 12 or len(self.user_agent) > 512 or "@" not in self.user_agent:
            raise WorkerConfigError("BIOCATALYST_USER_AGENT_INVALID")
        if not isinstance(self.history_enabled, bool):
            raise WorkerConfigError("BIOCATALYST_HISTORY_ENABLED_INVALID")
        if not isinstance(self.prospective_enabled, bool):
            raise WorkerConfigError("BIOCATALYST_PROSPECTIVE_ENABLED_INVALID")
        if not isinstance(self.r2_retention_confirmed, bool):
            raise WorkerConfigError("BIOCATALYST_R2_RETENTION_CONFIRMED_INVALID")
        if (
            not isinstance(self.activation_owner_uid, int)
            or isinstance(self.activation_owner_uid, bool)
            or self.activation_owner_uid < 0
        ):
            raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
        if (
            self.activation_group_gid is not None
            and (
                not isinstance(self.activation_group_gid, int)
                or isinstance(self.activation_group_gid, bool)
                or self.activation_group_gid < 0
            )
        ):
            raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
        if self.prospective_enabled:
            gate_path = self.activation_gate_path
            heartbeat_path = self.activation_heartbeat_path
            if (
                not isinstance(self.activation_id, str)
                or not _ACTIVATION_ID_RE.fullmatch(self.activation_id)
                or not isinstance(gate_path, Path)
                or not isinstance(heartbeat_path, Path)
                or not gate_path.is_absolute()
                or not heartbeat_path.is_absolute()
                or gate_path == heartbeat_path
                or not isinstance(self.r2_account_id, str)
                or not _R2_ACCOUNT_ID_RE.fullmatch(self.r2_account_id)
                or self.r2_jurisdiction not in _R2_JURISDICTIONS
            ):
                raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
            if gate_path.parent != heartbeat_path.parent:
                raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
            for artifact_path in (gate_path, heartbeat_path):
                try:
                    artifact_path.relative_to(state_root)
                except ValueError:
                    pass
                else:
                    raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
                try:
                    artifact_path.relative_to(public_root)
                except ValueError:
                    pass
                else:
                    raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
        object.__setattr__(self, "state_root", state_root)
        object.__setattr__(self, "public_root", public_root)


@dataclass(frozen=True)
class EnvironmentPlan:
    state: str
    config: WorkerConfig | None
    state_root: Path | None
    public_root: Path | None
    configured_nct_count: int
    requested_enabled: bool = False
    error_code: str | None = None


@dataclass(frozen=True)
class WorkerResult:
    exit_code: int
    status: str
    error_code: str | None = None
    generation_id: str | None = None


@dataclass(frozen=True)
class ValidatedPrivateEvidence:
    """In-memory evidence bundle proven against the exact private run tree."""

    snapshots_by_nct: dict[str, dict[str, Any]]
    receipts: tuple[dict[str, Any], ...]
    raw_page_bodies_by_receipt: dict[str, bytes]


@dataclass(frozen=True)
class PriorProspectiveState:
    """Pointer-bound prior public state joined to replayed private evidence."""

    epoch: dict[str, Any]
    source_by_nct: Mapping[str, ProspectiveSourceEvidence]
    observations_by_nct: Mapping[str, dict[str, Any]]
    public_models_by_nct: Mapping[str, dict[str, Any]]


class CollectorResult(Protocol):
    run_id: str
    run_path: Path
    generation_path: Path


class Collector(Protocol):
    def collect(self, *, watermark_before: str | None = None) -> CollectorResult: ...


CollectorFactory = Callable[..., Collector]


class HistoryCollector(Protocol):
    def collect_nct(self, nct_id: str) -> Any: ...


HistoryCollectorFactory = Callable[..., HistoryCollector]
StoreFactory = Callable[[DedicatedR2Config], BinaryObjectStore]
ActivationVerifier = Callable[["WorkerConfig", datetime], None]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _service_runtime_paths(values: Mapping[str, str]) -> tuple[Path | None, Path | None]:
    """Accept only the systemd-owned pair before any environment health write.

    The worker itself supports injected temporary roots for hermetic tests, but
    an EnvironmentFile is root-owned production input.  Letting an arbitrary
    absolute value such as ``/etc`` reach ``write_health`` would turn a typo
    into a root filesystem write, so this boundary is deliberately exact.
    """

    raw_state = values.get("BIOCATALYST_STATE_ROOT")
    raw_public = values.get("BIOCATALYST_PUBLIC_ROOT")
    if not raw_state or not raw_public:
        return None, None
    state_path = Path(raw_state)
    public_path = Path(raw_public)
    if (
        state_path != _SERVICE_STATE_ROOT
        or public_path != _SERVICE_PUBLIC_ROOT
        or state_path.is_symlink()
        or public_path.is_symlink()
    ):
        return None, None
    try:
        state, public = _validated_root_pair(state_path, public_path)
    except WorkerConfigError:
        return None, None
    return state, public


def _parse_nct_ids(raw: str | None) -> tuple[str, ...]:
    values = tuple(sorted({item.strip() for item in (raw or "").split(",") if item.strip()}))
    if not values or any(not _NCT_RE.fullmatch(value) for value in values):
        raise WorkerConfigError("BIOCATALYST_CANARY_NCTS_INVALID")
    return values


def _parse_history_enabled(raw: str | None) -> bool:
    value = (raw or "").strip()
    if value in {"", "0"}:
        return False
    if value == "1":
        return True
    raise WorkerConfigError("BIOCATALYST_HISTORY_ENABLED_INVALID")


def _parse_prospective_enabled(raw: str | None) -> bool:
    value = (raw or "").strip()
    if value in {"", "0"}:
        return False
    if value == "1":
        return True
    raise WorkerConfigError("BIOCATALYST_PROSPECTIVE_ENABLED_INVALID")


def _parse_r2_retention_confirmed(raw: str | None) -> bool:
    value = (raw or "").strip()
    if value in {"", "0"}:
        return False
    if value == "1":
        return True
    raise WorkerConfigError("BIOCATALYST_R2_RETENTION_CONFIRMED_INVALID")


def _service_activation_paths(
    values: Mapping[str, str],
) -> tuple[Path | None, Path | None]:
    raw_gate = values.get("BIOCATALYST_R2_ACTIVATION_GATE_PATH", "").strip()
    raw_heartbeat = values.get(
        "BIOCATALYST_R2_ACTIVATION_HEARTBEAT_PATH", ""
    ).strip()
    if not raw_gate and not raw_heartbeat:
        return None, None
    gate_path = Path(raw_gate)
    heartbeat_path = Path(raw_heartbeat)
    if (
        gate_path != _SERVICE_ACTIVATION_GATE_PATH
        or heartbeat_path != _SERVICE_ACTIVATION_HEARTBEAT_PATH
        or gate_path.is_symlink()
        or heartbeat_path.is_symlink()
    ):
        raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    return gate_path, heartbeat_path


def _parse_activation_id(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if not _ACTIVATION_ID_RE.fullmatch(value):
        raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    return value


def _parse_r2_account_id(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    if not value:
        return None
    if not _R2_ACCOUNT_ID_RE.fullmatch(value):
        raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    return value


def _parse_r2_jurisdiction(raw: str | None) -> str:
    value = (raw or "default").strip().lower()
    if value not in _R2_JURISDICTIONS:
        raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    return value


def _history_source_production_allowed(
    registry_path: Path | None = None,
) -> bool:
    """Fail closed unless the versioned source registry explicitly approves B2.

    The environment switch is an operator control, not a rights override.  A
    reviewed repository change must advance the source registry before a
    production service can instantiate the undocumented Record History adapter.
    """

    registry_path = _SOURCE_REGISTRY_PATH if registry_path is None else registry_path
    try:
        payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        source = payload["sources"]["clinicaltrials_gov_record_history"]
    except (OSError, UnicodeError, yaml.YAMLError, KeyError, TypeError):
        return False
    return bool(
        isinstance(source, Mapping)
        and source.get("source_id") == "clinicaltrials_gov_record_history"
        and source.get("production_ingest_allowed") is True
        and source.get("source_shape_canary_required") is True
    )


def load_environment(environ: Mapping[str, str] | None = None) -> EnvironmentPlan:
    """Parse the env contract without ever falling back to another R2 plane."""

    values = os.environ if environ is None else environ
    state_root, public_root = _service_runtime_paths(values)
    raw_ncts = values.get("BIOCATALYST_CANARY_NCTS", "")
    configured_nct_count = len({item.strip() for item in raw_ncts.split(",") if item.strip()})
    enabled = values.get("BIOCATALYST_ENABLED", "").strip()
    requested_enabled = enabled == "1"
    try:
        history_enabled = _parse_history_enabled(values.get("BIOCATALYST_HISTORY_ENABLED"))
        prospective_enabled = _parse_prospective_enabled(
            values.get("BIOCATALYST_PROSPECTIVE_ENABLED")
        )
        r2_retention_confirmed = _parse_r2_retention_confirmed(
            values.get("BIOCATALYST_R2_RETENTION_CONFIRMED")
        )
        activation_gate_path, activation_heartbeat_path = _service_activation_paths(
            values
        )
        activation_id = _parse_activation_id(
            values.get("BIOCATALYST_R2_ACTIVATION_ID")
        )
        r2_account_id = _parse_r2_account_id(values.get("BIOCATALYST_R2_ACCOUNT_ID"))
        r2_jurisdiction = _parse_r2_jurisdiction(
            values.get("BIOCATALYST_R2_JURISDICTION")
        )
        if prospective_enabled and (
            activation_gate_path is None
            or activation_heartbeat_path is None
            or activation_id is None
            or r2_account_id is None
        ):
            raise WorkerConfigError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
        if history_enabled and not _history_source_production_allowed():
            raise WorkerConfigError("BIOCATALYST_HISTORY_SOURCE_NOT_APPROVED")
    except WorkerConfigError as exc:
        return EnvironmentPlan(
            state="invalid",
            config=None,
            state_root=state_root,
            public_root=public_root,
            configured_nct_count=configured_nct_count,
            requested_enabled=requested_enabled,
            error_code=exc.code,
        )
    if enabled in {"", "0"}:
        return EnvironmentPlan(
            state="disabled",
            config=None,
            state_root=state_root,
            public_root=public_root,
            configured_nct_count=configured_nct_count,
            requested_enabled=False,
        )
    if enabled != "1":
        return EnvironmentPlan(
            state="invalid",
            config=None,
            state_root=state_root,
            public_root=public_root,
            configured_nct_count=configured_nct_count,
            requested_enabled=False,
            error_code="BIOCATALYST_ENABLED_INVALID",
        )
    try:
        if state_root is None or public_root is None:
            raise WorkerConfigError("BIOCATALYST_RUNTIME_PATH_INVALID")
        config = WorkerConfig(
            state_root=state_root,
            public_root=public_root,
            nct_ids=_parse_nct_ids(raw_ncts),
            user_agent=values.get("BIOCATALYST_USER_AGENT", "").strip(),
            r2=DedicatedR2Config.from_environment(values),
            history_enabled=history_enabled,
            prospective_enabled=prospective_enabled,
            r2_retention_confirmed=r2_retention_confirmed,
            activation_id=activation_id,
            activation_gate_path=activation_gate_path,
            activation_heartbeat_path=activation_heartbeat_path,
            r2_account_id=r2_account_id,
            r2_jurisdiction=r2_jurisdiction,
            activation_owner_uid=0,
            activation_group_gid=os.getgid(),
        )
    except (StorageError, WorkerConfigError) as exc:
        return EnvironmentPlan(
            state="invalid",
            config=None,
            state_root=state_root,
            public_root=public_root,
            configured_nct_count=configured_nct_count,
            requested_enabled=True,
            error_code=exc.code,
        )
    return EnvironmentPlan(
        state="enabled",
        config=config,
        state_root=state_root,
        public_root=public_root,
        configured_nct_count=len(config.nct_ids),
        requested_enabled=True,
    )


def _strict_json_object(path: Path) -> dict[str, Any]:
    def reject_constant(_: str) -> None:
        raise ValueError("non-finite JSON")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def lossless_float(value: str) -> float:
        try:
            exact = Decimal(value)
            parsed = float(value)
            round_tripped = Decimal(repr(parsed))
        except (InvalidOperation, OverflowError, ValueError) as exc:
            raise ValueError("invalid JSON number") from exc
        if not math.isfinite(parsed) or round_tripped != exact:
            raise ValueError("lossy or non-finite JSON number")
        return parsed

    try:
        payload = json.loads(
            path.read_bytes().decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
            parse_float=lossless_float,
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as exc:
        raise PublicationError("RUN_CONTRACT_INVALID") from exc
    if not isinstance(payload, dict):
        raise PublicationError("RUN_CONTRACT_INVALID")
    try:
        canonical_json_bytes(payload)
    except Exception as exc:
        raise PublicationError("RUN_CONTRACT_INVALID") from exc
    return payload


def _read_activation_artifact(
    path: Path,
    *,
    config: WorkerConfig,
    code: str,
) -> dict[str, Any]:
    """Read one root-controlled activation artifact without following links.

    The fixed activation directory is deliberately not writable by the worker.
    Exact ownership and modes turn the local documents into a privilege split,
    while the contract hashes bind them to the independently verified R2
    control plane.
    """

    candidate = Path(path)
    parent = candidate.parent
    file_fd: int | None = None
    try:
        if (
            not candidate.is_absolute()
            or candidate.name not in {"gate.json", "heartbeat.json"}
            or parent.is_symlink()
            or parent.resolve(strict=True) != parent
        ):
            raise ActivationError(code)
        parent_metadata = parent.lstat()
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or parent_metadata.st_uid != config.activation_owner_uid
            or (
                config.activation_group_gid is not None
                and parent_metadata.st_gid != config.activation_group_gid
            )
            or stat.S_IMODE(parent_metadata.st_mode) != 0o750
        ):
            raise ActivationError(code)

        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_fd = os.open(os.fspath(candidate), flags)
        metadata_before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(metadata_before.st_mode)
            or metadata_before.st_uid != config.activation_owner_uid
            or (
                config.activation_group_gid is not None
                and metadata_before.st_gid != config.activation_group_gid
            )
            or stat.S_IMODE(metadata_before.st_mode) != 0o440
            or metadata_before.st_nlink != 1
            or metadata_before.st_size <= 0
            or metadata_before.st_size > _ACTIVATION_ARTIFACT_MAX_BYTES
        ):
            raise ActivationError(code)
        raw = os.read(file_fd, _ACTIVATION_ARTIFACT_MAX_BYTES + 1)
        metadata_after = os.fstat(file_fd)
        if (
            len(raw) != metadata_before.st_size
            or metadata_after.st_dev != metadata_before.st_dev
            or metadata_after.st_size != metadata_before.st_size
            or metadata_after.st_mtime_ns != metadata_before.st_mtime_ns
            or metadata_after.st_ctime_ns != metadata_before.st_ctime_ns
            or metadata_after.st_ino != metadata_before.st_ino
            or metadata_after.st_mode != metadata_before.st_mode
            or metadata_after.st_uid != metadata_before.st_uid
            or metadata_after.st_gid != metadata_before.st_gid
            or metadata_after.st_nlink != metadata_before.st_nlink
        ):
            raise ActivationError(code)

        def reject_constant(_: str) -> None:
            raise ValueError("non-finite JSON")

        def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate JSON key")
                value[key] = item
            return value

        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
        if not isinstance(payload, dict):
            raise ActivationError(code)
        return payload
    except ActivationError:
        raise
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ActivationError(code) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)


def _default_activation_verifier(config: WorkerConfig, now: datetime) -> None:
    """Validate a root-sealed gate and its latest read-only heartbeat locally."""

    if (
        config.activation_gate_path is None
        or config.activation_heartbeat_path is None
        or config.activation_id is None
        or config.r2_account_id is None
    ):
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    gate = _read_activation_artifact(
        config.activation_gate_path,
        config=config,
        code="BIOCATALYST_R2_ACTIVATION_GATE_INVALID",
    )
    heartbeat = _read_activation_artifact(
        config.activation_heartbeat_path,
        config=config,
        code="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID",
    )
    validate_activation_gate(gate, now=now)
    validate_activation_heartbeat(heartbeat, gate, now=now)
    expected_binding = activation_target_binding_sha256(
        account_id=config.r2_account_id,
        bucket=config.r2.bucket,
        endpoint=config.r2.endpoint,
        jurisdiction=config.r2_jurisdiction,
        worker_token_id=config.r2.access_key_id,
    )
    if (
        gate.get("activation_id") != config.activation_id
        or heartbeat.get("activation_id") != config.activation_id
        or gate.get("target_binding_sha256") != expected_binding
        or heartbeat.get("target_binding_sha256") != expected_binding
    ):
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")


def _path_within(path: Path, root: Path, *, code: str) -> Path:
    try:
        root = Path(root).resolve(strict=True)
        candidate = Path(path).resolve(strict=True)
        candidate.relative_to(root)
    except (OSError, ValueError) as exc:
        raise PublicationError(code) from exc
    if Path(path).is_symlink() or not candidate.is_file():
        raise PublicationError(code)
    return candidate


def _private_object_path(private_stage: Path, object_key: object) -> Path:
    """Resolve one receipt-declared private key without traversal or symlinks."""

    if not isinstance(object_key, str) or not object_key or "\\" in object_key:
        raise PublicationError("RAW_EVIDENCE_INVALID")
    key = PurePosixPath(object_key)
    if (
        key.is_absolute()
        or not key.parts
        or any(part in {"", ".", ".."} for part in key.parts)
        or key.as_posix() != object_key
        or not object_key.startswith("biocatalyst/")
    ):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    return _path_within(
        private_stage.joinpath(*key.parts),
        private_stage,
        code="RAW_EVIDENCE_INVALID",
    )


def _canonical_run_identity(run: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return ``(year, month, run_id)`` only for the live B1 naming contract."""

    started_at = run.get("started_at")
    manifest = run.get("query_manifest")
    if not isinstance(started_at, str) or not isinstance(manifest, Mapping):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    query_hash = manifest.get("query_sha256")
    if not isinstance(query_hash, str) or not _SHA256_RE.fullmatch(query_hash):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    try:
        parsed = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError("RAW_EVIDENCE_INVALID") from exc
    if parsed.tzinfo is None:
        raise PublicationError("RAW_EVIDENCE_INVALID")
    normalized = parsed.astimezone(timezone.utc)
    stamp = normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")
    expected_run_id = "ctgov_run_" + stamp.replace("-", "").replace(":", "").replace(".", "") + f"_{query_hash[:12]}"
    if run.get("run_id") != expected_run_id:
        raise PublicationError("RAW_EVIDENCE_INVALID")
    return f"{normalized.year:04d}", f"{normalized.month:02d}", expected_run_id


def _expect_headers(headers: object, config: WorkerConfig) -> None:
    if not isinstance(headers, Mapping) or dict(headers) != {
        "accept": "application/json",
        "accept-encoding": "identity",
        "user-agent": config.user_agent,
    }:
        raise PublicationError("RAW_EVIDENCE_INVALID")


def _expect_exact_response(
    response: object,
    *,
    private_stage: Path,
    expected_raw_key: str,
) -> tuple[Path, bytes]:
    if not isinstance(response, Mapping) or type(response.get("status_code")) is not int or response.get("status_code") != 200:
        raise PublicationError("RAW_EVIDENCE_INVALID")
    digest = response.get("exact_response_sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    if response.get("raw_response_object_key") != expected_raw_key:
        raise PublicationError("RAW_EVIDENCE_INVALID")
    headers = response.get("headers")
    if not isinstance(headers, Mapping):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    encoding = headers.get("content-encoding")
    if encoding is not None and (not isinstance(encoding, str) or encoding.strip().lower() not in {"", "identity"}):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    raw_path = _private_object_path(private_stage, expected_raw_key)
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest or response.get("byte_count") != len(raw):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    content_length = headers.get("content-length")
    if content_length is not None and (
        not isinstance(content_length, str)
        or not re.fullmatch(r"[0-9]+", content_length)
        or int(content_length) != len(raw)
    ):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    return raw_path, raw


def _validate_version_evidence(
    private_stage: Path,
    run: Mapping[str, Any],
    *,
    year: str,
    month: str,
    run_id: str,
    config: WorkerConfig,
    expected_files: set[str],
) -> None:
    """Reload both exact ``/version`` probes and bind them to run/page facts."""

    evidence = run.get("version_evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != {
        "hash_scope", "version_receipt_payloads_sha256", "before", "after"
    }:
        raise PublicationError("RAW_EVIDENCE_INVALID")
    before = evidence.get("before")
    after = evidence.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise PublicationError("RAW_EVIDENCE_INVALID")
    if evidence.get("hash_scope") != "canonical_version_receipts_before_after" or evidence.get(
        "version_receipt_payloads_sha256"
    ) != canonical_json_sha256([before, after]):
        raise PublicationError("RAW_EVIDENCE_INVALID")

    for phase, receipt in (("before", before), ("after", after)):
        expected_receipt_id = f"ctgov_version_receipt_{run_id.removeprefix('ctgov_run_')}_{phase}"
        expected_receipt_key = (
            "biocatalyst/receipts/clinicaltrials/version/"
            f"{year}/{month}/{run_id}/{phase}.json"
        )
        if (
            receipt.get("receipt_id") != expected_receipt_id
            or receipt.get("run_id") != run_id
            or receipt.get("source_id") != "clinicaltrials_gov_v2"
            or receipt.get("phase") != phase
            or receipt.get("receipt_object_key") != expected_receipt_key
        ):
            raise PublicationError("RAW_EVIDENCE_INVALID")
        _expect_headers(receipt.get("request", {}).get("headers") if isinstance(receipt.get("request"), Mapping) else None, config)
        request = receipt.get("request")
        if not isinstance(request, Mapping) or request.get("method") != "GET" or request.get("path") != "/version":
            raise PublicationError("RAW_EVIDENCE_INVALID")
        receipt_path = _private_object_path(private_stage, expected_receipt_key)
        parsed_receipt = _strict_json_object(receipt_path)
        if dict(receipt) != parsed_receipt or receipt_path.read_bytes() != canonical_json_bytes(parsed_receipt) + b"\n":
            raise PublicationError("RAW_EVIDENCE_INVALID")
        response = receipt.get("response")
        digest = response.get("exact_response_sha256") if isinstance(response, Mapping) else None
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise PublicationError("RAW_EVIDENCE_INVALID")
        expected_raw_key = (
            "biocatalyst/raw/clinicaltrials/v2/version/"
            f"{year}/{month}/{run_id}/{phase}/{digest}.json"
        )
        raw_path, _ = _expect_exact_response(
            response,
            private_stage=private_stage,
            expected_raw_key=expected_raw_key,
        )
        payload = _strict_json_object(raw_path)
        timestamp = payload.get("dataTimestamp")
        api_version = payload.get("apiVersion")
        expected_timestamp = run.get(
            "source_dataset_timestamp_before_raw" if phase == "before" else "source_dataset_timestamp_after_raw"
        )
        expected_api = run.get("source_api_version" if phase == "before" else "source_api_version_after")
        if (
            not isinstance(timestamp, str)
            or not _SOURCE_TIMESTAMP_RE.fullmatch(timestamp)
            or not isinstance(api_version, str)
            or not api_version
            or receipt.get("source_dataset_timestamp_raw") != timestamp
            or receipt.get("source_api_version") != api_version
            or timestamp != expected_timestamp
            or api_version != expected_api
        ):
            raise PublicationError("RAW_EVIDENCE_INVALID")
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PublicationError("RAW_EVIDENCE_INVALID") from exc
        expected_files.add(receipt_path.relative_to(private_stage).as_posix())
        expected_files.add(raw_path.relative_to(private_stage).as_posix())

    if (
        run.get("source_dataset_timestamp_before_raw") != run.get("source_dataset_timestamp_after_raw")
        or run.get("source_api_version") != run.get("source_api_version_after")
    ):
        raise PublicationError("RAW_EVIDENCE_INVALID")


def _validate_private_raw_evidence(
    private_stage: Path,
    run: Mapping[str, Any],
    *,
    run_path: Path,
    config: WorkerConfig,
    allowed_extra_roots: tuple[str, ...] = (),
) -> ValidatedPrivateEvidence:
    """Independently prove B1 run -> exact probes/pages -> canonical snapshots.

    The worker treats every collector write as hostile until this boundary has
    reloaded it from disk.  It intentionally derives every live path from the
    run clock, deterministic run ID, page ordinal, and content hash rather than
    trusting a path supplied by the collector.
    """

    try:
        normalized_extra_roots = tuple(
            PurePosixPath(root).as_posix().rstrip("/") for root in allowed_extra_roots
        )
        if any(
            not root.startswith("biocatalyst/")
            or ".." in PurePosixPath(root).parts
            for root in normalized_extra_roots
        ):
            raise PublicationError("RAW_EVIDENCE_INVALID")
        private_stage = Path(private_stage).resolve(strict=True)
        year, month, run_id = _canonical_run_identity(run)
        expected_run_key = f"biocatalyst/runs/clinicaltrials/{year}/{month}/{run_id}.json"
        run_path = _path_within(run_path, private_stage, code="RAW_EVIDENCE_INVALID")
        expected_run_path = _private_object_path(private_stage, expected_run_key)
        if run_path != expected_run_path or run_path.read_bytes() != canonical_json_bytes(dict(run)) + b"\n":
            raise PublicationError("RAW_EVIDENCE_INVALID")
        expected_files = {run_path.relative_to(private_stage).as_posix()}
        _validate_version_evidence(
            private_stage,
            run,
            year=year,
            month=month,
            run_id=run_id,
            config=config,
            expected_files=expected_files,
        )

        receipt_ids = run.get("receipt_refs")
        if (
            not isinstance(receipt_ids, list)
            or not receipt_ids
            or any(not isinstance(receipt_id, str) for receipt_id in receipt_ids)
            or len(set(receipt_ids)) != len(receipt_ids)
        ):
            raise PublicationError("RAW_EVIDENCE_INVALID")
        receipts: list[dict[str, Any]] = []
        raw_by_receipt: dict[str, bytes] = {}
        for ordinal, receipt_id in enumerate(receipt_ids):
            expected_receipt_id = f"ctgov_receipt_{run_id.removeprefix('ctgov_run_')}_{ordinal}"
            expected_receipt_key = (
                f"biocatalyst/receipts/clinicaltrials/{year}/{month}/{run_id}/{ordinal}.json"
            )
            if receipt_id != expected_receipt_id:
                raise PublicationError("RAW_EVIDENCE_INVALID")
            receipt_path = _private_object_path(private_stage, expected_receipt_key)
            receipt = _strict_json_object(receipt_path)
            if (
                receipt.get("receipt_id") != receipt_id
                or receipt.get("run_id") != run_id
                or receipt.get("receipt_object_key") != expected_receipt_key
                or receipt_path.read_bytes() != canonical_json_bytes(receipt) + b"\n"
            ):
                raise PublicationError("RAW_EVIDENCE_INVALID")
            request = receipt.get("request")
            if not isinstance(request, Mapping) or request.get("method") != "GET" or request.get("path") != "/studies":
                raise PublicationError("RAW_EVIDENCE_INVALID")
            _expect_headers(request.get("headers"), config)
            response = receipt.get("response")
            digest = response.get("exact_response_sha256") if isinstance(response, Mapping) else None
            if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                raise PublicationError("RAW_EVIDENCE_INVALID")
            expected_raw_key = (
                "biocatalyst/raw/clinicaltrials/v2/pages/"
                f"{year}/{month}/{run_id}/{ordinal}/{digest}.json"
            )
            raw_path, raw = _expect_exact_response(
                response,
                private_stage=private_stage,
                expected_raw_key=expected_raw_key,
            )
            expected_files.add(receipt_path.relative_to(private_stage).as_posix())
            expected_files.add(raw_path.relative_to(private_stage).as_posix())
            receipts.append(receipt)
            raw_by_receipt[receipt_id] = raw
        context = build_ctgov_publication_context(run, receipts, raw_by_receipt)

        snapshot_root = private_stage / "biocatalyst" / "source_snapshots" / "clinicaltrials"
        if not snapshot_root.is_dir() or snapshot_root.is_symlink():
            raise PublicationError("RAW_EVIDENCE_INVALID")
        snapshots_by_nct: dict[str, dict[str, Any]] = {}
        snapshot_directories: set[str] = set()
        for snapshot_path in sorted(snapshot_root.rglob("*")):
            if snapshot_path.is_symlink():
                raise PublicationError("RAW_EVIDENCE_INVALID")
            private_relative = snapshot_path.relative_to(private_stage).as_posix()
            if any(
                private_relative == root or private_relative.startswith(root + "/")
                for root in normalized_extra_roots
            ):
                continue
            relative = snapshot_path.relative_to(snapshot_root)
            if snapshot_path.is_dir():
                if len(relative.parts) != 1 or not _NCT_RE.fullmatch(snapshot_path.name):
                    raise PublicationError("RAW_EVIDENCE_INVALID")
                snapshot_directories.add(snapshot_path.name)
                continue
            if (
                not snapshot_path.is_file()
                or len(relative.parts) != 2
                or not _NCT_RE.fullmatch(relative.parts[0])
                or snapshot_path.suffix != ".json"
            ):
                raise PublicationError("RAW_EVIDENCE_INVALID")
            resolved_snapshot_path = _path_within(snapshot_path, private_stage, code="RAW_EVIDENCE_INVALID")
            snapshot = _strict_json_object(resolved_snapshot_path)
            nct_id = snapshot.get("nct_id")
            snapshot_id = snapshot.get("source_snapshot_id")
            digest = snapshot.get("canonical_content_sha256")
            if (
                not isinstance(nct_id, str)
                or not _NCT_RE.fullmatch(nct_id)
                or not isinstance(snapshot_id, str)
                or not isinstance(digest, str)
                or not _SHA256_RE.fullmatch(digest)
                or nct_id in snapshots_by_nct
                or relative.parts[0] != nct_id
                or snapshot_path.name != f"{snapshot_id}.json"
                or snapshot_id != f"ctgov_snapshot_{nct_id}_{run_id.removeprefix('ctgov_run_')}_{digest}"
            ):
                raise PublicationError("RAW_EVIDENCE_INVALID")
            expected_snapshot_path = _private_object_path(
                private_stage,
                f"biocatalyst/source_snapshots/clinicaltrials/{nct_id}/{snapshot_id}.json",
            )
            if expected_snapshot_path != resolved_snapshot_path or resolved_snapshot_path.read_bytes() != canonical_json_bytes(snapshot) + b"\n":
                raise PublicationError("RAW_EVIDENCE_INVALID")
            canonical_study = snapshot.get("canonical_study")
            expected_canonical_key = f"biocatalyst/raw/clinicaltrials/v2/{nct_id}/{digest}.json"
            if not isinstance(canonical_study, Mapping) or snapshot.get("raw_object_key") != expected_canonical_key:
                raise PublicationError("RAW_EVIDENCE_INVALID")
            canonical_path = _private_object_path(private_stage, expected_canonical_key)
            if canonical_path.read_bytes() != canonical_json_bytes(canonical_study):
                raise PublicationError("RAW_EVIDENCE_INVALID")
            expected_files.add(resolved_snapshot_path.relative_to(private_stage).as_posix())
            expected_files.add(canonical_path.relative_to(private_stage).as_posix())
            snapshots_by_nct[nct_id] = snapshot

        snapshots = [snapshots_by_nct[nct_id] for nct_id in sorted(snapshots_by_nct)]
        expected_nct_ids = run.get("query_manifest", {}).get("configured_nct_ids")
        if (
            not isinstance(expected_nct_ids, list)
            or set(snapshots_by_nct) != set(expected_nct_ids)
            or snapshot_directories != set(expected_nct_ids)
        ):
            raise PublicationError("RAW_EVIDENCE_INVALID")
        context.validate_source_snapshots(snapshots)
        validate_ctgov_publication_bundle(run, receipts, raw_by_receipt, snapshots)
        actual_files: set[str] = set()
        actual_directories: set[str] = set()
        for path in private_stage.rglob("*"):
            if path.is_symlink() or (not path.is_dir() and not path.is_file()):
                raise PublicationError("RAW_EVIDENCE_INVALID")
            if path.is_file():
                actual_files.add(path.relative_to(private_stage).as_posix())
            elif path.is_dir():
                actual_directories.add(path.relative_to(private_stage).as_posix())
        expected_directories: set[str] = set()
        for relative_file in expected_files:
            for parent in PurePosixPath(relative_file).parents:
                if parent.as_posix() != ".":
                    expected_directories.add(parent.as_posix())
        def permitted_extra(relative: str) -> bool:
            return any(
                relative == root
                or relative.startswith(root + "/")
                or root.startswith(relative + "/")
                for root in normalized_extra_roots
            )

        if (
            any(path not in expected_files and not permitted_extra(path) for path in actual_files)
            or any(
                path not in expected_directories and not permitted_extra(path)
                for path in actual_directories
            )
            or not expected_files.issubset(actual_files)
            or not expected_directories.issubset(actual_directories)
        ):
            raise PublicationError("RAW_EVIDENCE_INVALID")
        return ValidatedPrivateEvidence(
            snapshots_by_nct=snapshots_by_nct,
            receipts=tuple(receipts),
            raw_page_bodies_by_receipt=raw_by_receipt,
        )
    except PublicationError as exc:
        if exc.code == "RAW_EVIDENCE_INVALID":
            raise
        raise PublicationError("RAW_EVIDENCE_INVALID") from exc
    except Exception as exc:
        raise PublicationError("RAW_EVIDENCE_INVALID") from exc


_PRIOR_PRIVATE_EXTRA_ROOTS = (
    "biocatalyst/raw/clinicaltrials/history",
    "biocatalyst/receipts/clinicaltrials/history",
    "biocatalyst/runs/clinicaltrials/history",
    "biocatalyst/source_snapshots/clinicaltrials/history",
    "biocatalyst/derived/clinicaltrials/history",
    "biocatalyst/derived/clinicaltrials/prospective",
)


def _write_private_prospective_immutable(
    private_stage: Path,
    *,
    relative: str,
    document: Mapping[str, Any],
) -> Path:
    """Write one canonical prospective artifact without overwrite semantics."""

    key = PurePosixPath(relative)
    if (
        key.is_absolute()
        or ".." in key.parts
        or key.as_posix() != relative
        or not relative.startswith("biocatalyst/derived/clinicaltrials/prospective/")
    ):
        raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID")
    root = Path(private_stage).resolve(strict=True)
    path = root.joinpath(*key.parts)
    payload = canonical_json_bytes(dict(document)) + b"\n"
    current = root
    for component in path.relative_to(root).parts[:-1]:
        current = current / component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
                metadata = current.lstat()
            except (FileExistsError, OSError) as exc:
                raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID") from exc
        except OSError as exc:
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID") from exc
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID")

    def verify_existing() -> Path:
        existing = _path_within(
            path, root, code="PROSPECTIVE_PRIVATE_ARCHIVE_INVALID"
        )
        try:
            actual = existing.read_bytes()
        except OSError as exc:
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID") from exc
        if actual != payload:
            raise PublicationError("IMMUTABLE_OBJECT_COLLISION")
        return existing

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            return verify_existing()
        except OSError as exc:
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID") from exc
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID") from exc
    except OSError as exc:
        raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID") from exc
    else:
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID")
        return verify_existing()
    return verify_existing()


def _prior_private_root(config: WorkerConfig, generation_id: str) -> tuple[Path, Path]:
    match = re.fullmatch(r"ctgov_run_([0-9]{4})([0-9]{2})[A-Za-z0-9_]+", generation_id)
    if match is None:
        raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
    private_root = config.state_root / "committed" / generation_id / "private"
    if private_root.is_symlink() or not private_root.is_dir():
        raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
    try:
        private_root = private_root.resolve(strict=True)
        private_root.relative_to(config.state_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING") from exc
    year, month = match.groups()
    run_path = private_root / "biocatalyst" / "runs" / "clinicaltrials" / year / month / f"{generation_id}.json"
    return private_root, run_path


def _verify_prior_private_mirror(
    *,
    private_root: Path,
    generation_id: str,
    store: BinaryObjectStore,
) -> None:
    """Anchor every prior local private byte to its immutable R2 receipt."""

    receipt_path = private_root.parent / "mirror_receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")
    try:
        receipt = _strict_json_object(receipt_path)
    except Exception as exc:
        raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID") from exc
    expected_keys = {
        "contract_id",
        "schema_version",
        "run_id",
        "verified_at",
        "objects",
        "manifest_sha256",
    }
    objects = receipt.get("objects")
    if (
        set(receipt) != expected_keys
        or receipt.get("contract_id") != "biocatalyst_private_mirror_receipt.v1"
        or receipt.get("schema_version") != "1.0.0"
        or receipt.get("run_id") != generation_id
        or not isinstance(objects, list)
        or not objects
        or canonical_json_sha256(
            {key: value for key, value in receipt.items() if key != "manifest_sha256"}
        )
        != receipt.get("manifest_sha256")
    ):
        raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")
    canonical_receipt = canonical_json_bytes(receipt) + b"\n"
    try:
        remote_receipt = store.get_bytes(
            f"biocatalyst/mirror_receipts/{generation_id}.json"
        )
    except Exception as exc:
        raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID") from exc
    try:
        local_receipt = receipt_path.read_bytes()
    except OSError as exc:
        raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID") from exc
    if remote_receipt != canonical_receipt or local_receipt != canonical_receipt:
        raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")

    listed_keys: list[str] = []
    for item in objects:
        if not isinstance(item, Mapping) or set(item) != {
            "object_key",
            "sha256",
            "byte_count",
        }:
            raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")
        object_key = item.get("object_key")
        digest = item.get("sha256")
        byte_count = item.get("byte_count")
        if (
            not isinstance(object_key, str)
            or not object_key.startswith("biocatalyst/")
            or PurePosixPath(object_key).as_posix() != object_key
            or ".." in PurePosixPath(object_key).parts
            or not isinstance(digest, str)
            or _SHA256_RE.fullmatch(digest) is None
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count < 1
        ):
            raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")
        path = private_root.joinpath(*PurePosixPath(object_key).parts)
        try:
            path = _path_within(
                path, private_root, code="PROSPECTIVE_PRIOR_MIRROR_INVALID"
            )
            local = path.read_bytes()
            remote = store.get_bytes(object_key)
        except Exception as exc:
            raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID") from exc
        if (
            len(local) != byte_count
            or hashlib.sha256(local).hexdigest() != digest
            or remote != local
        ):
            raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")
        listed_keys.append(object_key)
    if listed_keys != sorted(set(listed_keys)):
        raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")
    actual_keys: set[str] = set()
    for path in private_root.rglob("*"):
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")
        if path.is_file():
            actual_keys.add(path.relative_to(private_root).as_posix())
    if actual_keys != set(listed_keys):
        raise PublicationError("PROSPECTIVE_PRIOR_MIRROR_INVALID")


def _load_prior_prospective_state(
    *,
    config: WorkerConfig,
    prior: CommittedGeneration,
    publisher: PublicGenerationPublisher,
    store: BinaryObjectStore,
) -> PriorProspectiveState:
    """Replay the prior run and bind its private observation to public v1.3."""

    if prior.schema_version != "1.3.0":
        raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
    projection = publisher.read_trial_projection()
    if projection is None or projection.generation != prior:
        raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
    models = {
        key: dict(value) for key, value in projection.prospective_models_by_nct.items()
    }
    if set(models) != set(config.nct_ids):
        raise PublicationError("PROSPECTIVE_SCOPE_INVALID")
    for model in models.values():
        try:
            validate_prospective_public_model(model)
        except ProspectiveError as exc:
            raise PublicationError("PROSPECTIVE_MODEL_INVALID") from exc

    private_root, run_path = _prior_private_root(config, prior.generation_id)
    _verify_prior_private_mirror(
        private_root=private_root,
        generation_id=prior.generation_id,
        store=store,
    )
    run = _strict_json_object(run_path)
    run = validate_candidate_run(run, expected_watermark=run.get("watermark_before"))
    _validate_supported_code_version(run)
    _validate_worker_authority(run, config)
    evidence = _validate_private_raw_evidence(
        private_root,
        run,
        run_path=run_path,
        config=config,
        allowed_extra_roots=_PRIOR_PRIVATE_EXTRA_ROOTS,
    )
    epoch_ids = {model.get("coverage_epoch_id") for model in models.values()}
    if len(epoch_ids) != 1:
        raise PublicationError("PROSPECTIVE_EPOCH_INVALID")
    epoch_id = next(iter(epoch_ids))
    if not isinstance(epoch_id, str) or re.fullmatch(r"ctgov_coverage_[A-Za-z0-9_-]+", epoch_id) is None:
        raise PublicationError("PROSPECTIVE_EPOCH_INVALID")
    epoch_path = (
        private_root
        / "biocatalyst"
        / "derived"
        / "clinicaltrials"
        / "prospective"
        / "epochs"
        / epoch_id
        / f"{prior.generation_id}.json"
    )
    epoch = _strict_json_object(epoch_path)
    try:
        validate_contract("trial_coverage_epoch.v1", epoch)
    except Exception as exc:
        raise PublicationError("PROSPECTIVE_EPOCH_INVALID") from exc
    if (
        epoch.get("coverage_epoch_id") != epoch_id
        or epoch.get("scope")
        != {"kind": "explicit_nct_allowlist", "nct_ids": list(config.nct_ids)}
        or epoch.get("last_complete_run_ref") != prior.generation_id
    ):
        raise PublicationError("PROSPECTIVE_EPOCH_INVALID")

    observations: dict[str, dict[str, Any]] = {}
    sources: dict[str, ProspectiveSourceEvidence] = {}
    expected_files = {epoch_path.relative_to(private_root).as_posix()}
    base = private_root / "biocatalyst" / "derived" / "clinicaltrials" / "prospective"
    for nct_id in config.nct_ids:
        model = models[nct_id]
        model_root = base / epoch_id / nct_id / "models"
        if model_root.is_symlink() or not model_root.is_dir():
            raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
        model_paths = sorted(model_root.glob("*.json"))
        if len(model_paths) != 1 or any(path.is_symlink() or not path.is_file() for path in model_paths):
            raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
        private_model_path = model_paths[0]
        private_model = _strict_json_object(private_model_path)
        if (
            private_model_path.name != f"{model.get('model_payload_sha256')}.json"
            or private_model != model
            or private_model_path.read_bytes() != canonical_json_bytes(model) + b"\n"
        ):
            raise PublicationError("PROSPECTIVE_MODEL_BINDING_INVALID")
        expected_files.add(private_model_path.relative_to(private_root).as_posix())
        observation_root = base / epoch_id / nct_id / "observations"
        if observation_root.is_symlink() or not observation_root.is_dir():
            raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
        observation_paths = sorted(observation_root.glob("*.json"))
        if len(observation_paths) != 1 or any(path.is_symlink() or not path.is_file() for path in observation_paths):
            raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
        observation_path = observation_paths[0]
        observation = _strict_json_object(observation_path)
        if observation_path.name != f"{observation.get('observation_id')}.json":
            raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
        source = ProspectiveSourceEvidence(
            run=run,
            snapshot=evidence.snapshots_by_nct[nct_id],
            receipts=evidence.receipts,
            raw_page_bodies_by_receipt=evidence.raw_page_bodies_by_receipt,
        )
        try:
            validate_trial_observation_against_source_evidence(
                observation,
                source.snapshot,
                source.run,
                source.receipts,
                raw_page_bodies_by_receipt=source.raw_page_bodies_by_receipt,
            )
        except Exception as exc:
            raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING") from exc
        if (
            model.get("nct_id") != nct_id
            or model.get("last_observed_at") != observation.get("retrieved_at")
            or model.get("coverage_epoch_id") != epoch_id
        ):
            raise PublicationError("PROSPECTIVE_MODEL_BINDING_INVALID")
        expected_files.add(observation_path.relative_to(private_root).as_posix())
        diff_root = base / epoch_id / nct_id / "diffs"
        diff_paths = sorted(diff_root.glob("*.json")) if diff_root.is_dir() else []
        if diff_root.is_symlink() or any(path.is_symlink() or not path.is_file() for path in diff_paths):
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID")
        expected_diff_count = 1 if observation.get("source_state_changed") is True else 0
        if len(diff_paths) != expected_diff_count:
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID")
        for diff_path in diff_paths:
            diff = _strict_json_object(diff_path)
            try:
                validate_contract("trial_version_diff.v1", diff)
            except Exception as exc:
                raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID") from exc
            if (
                diff_path.name != f"{diff.get('diff_payload_sha256')}.json"
                or diff.get("after_observation_ref") != observation.get("observation_id")
                or diff.get("nct_id") != nct_id
            ):
                raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID")
            if not model.get("events") or build_prospective_public_event(diff) != model["events"][-1]:
                raise PublicationError("PROSPECTIVE_MODEL_BINDING_INVALID")
            expected_files.add(diff_path.relative_to(private_root).as_posix())
        if (
            model.get("coverage_started_at") != epoch.get("coverage_started_at")
            or model.get("generated_at") != run.get("finished_at")
            or datetime.fromisoformat(
                str(model.get("baseline_established_at")).replace("Z", "+00:00")
            )
            < datetime.fromisoformat(
                str(epoch.get("coverage_started_at")).replace("Z", "+00:00")
            )
            or (
                model.get("accrual_state") == "baseline_established"
                and (
                    epoch.get("first_complete_run_ref") != run.get("run_id")
                    or model.get("baseline_established_at")
                    != observation.get("retrieved_at")
                )
            )
        ):
            raise PublicationError("PROSPECTIVE_MODEL_BINDING_INVALID")
        observations[nct_id] = observation
        sources[nct_id] = source

    observed_upper = max(
        (item["retrieved_at"] for item in observations.values()),
        key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
    )
    if epoch.get("last_observed_at") != observed_upper:
        raise PublicationError("PROSPECTIVE_EPOCH_INVALID")
    actual_files: set[str] = set()
    for path in base.rglob("*"):
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID")
        if path.is_file():
            actual_files.add(path.relative_to(private_root).as_posix())
    if actual_files != expected_files:
        raise PublicationError("PROSPECTIVE_PRIVATE_ARCHIVE_INVALID")
    return PriorProspectiveState(
        epoch=epoch,
        source_by_nct=sources,
        observations_by_nct=observations,
        public_models_by_nct=models,
    )


def _build_prospective_generation(
    *,
    private_stage: Path,
    run: Mapping[str, Any],
    validated_evidence: ValidatedPrivateEvidence,
    config: WorkerConfig,
    prior_state: PriorProspectiveState | None,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, ProspectivePublicationEvidence],
]:
    """Build, persist, and bind one complete prospective generation."""

    retrieved_times = [
        validated_evidence.snapshots_by_nct[nct_id]["retrieved_at"]
        for nct_id in config.nct_ids
    ]
    earliest = min(retrieved_times, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
    latest = max(retrieved_times, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
    epoch = build_coverage_epoch(
        nct_ids=config.nct_ids,
        current_run_ref=run["run_id"],
        last_observed_at=latest,
        coverage_started_at=earliest if prior_state is None else None,
        transaction_from=run["finished_at"],
        prior_epoch=prior_state.epoch if prior_state is not None else None,
    )
    epoch_id = epoch["coverage_epoch_id"]
    _write_private_prospective_immutable(
        private_stage,
        relative=(
            "biocatalyst/derived/clinicaltrials/prospective/epochs/"
            f"{epoch_id}/{run['run_id']}.json"
        ),
        document=epoch,
    )
    models: dict[str, dict[str, Any]] = {}
    evidence_by_nct: dict[str, ProspectivePublicationEvidence] = {}
    for nct_id in config.nct_ids:
        current = ProspectiveSourceEvidence(
            run=run,
            snapshot=validated_evidence.snapshots_by_nct[nct_id],
            receipts=validated_evidence.receipts,
            raw_page_bodies_by_receipt=validated_evidence.raw_page_bodies_by_receipt,
        )
        prior_source = prior_state.source_by_nct[nct_id] if prior_state is not None else None
        prior_observation = (
            prior_state.observations_by_nct[nct_id] if prior_state is not None else None
        )
        prior_model = prior_state.public_models_by_nct[nct_id] if prior_state is not None else None
        observation = build_prospective_observation(
            current,
            prior=(prior_source, prior_observation) if prior_source is not None else None,
        )
        exact_diff = (
            build_prospective_exact_diff(
                prior_source,
                current,
                before_observation=prior_observation,
                after_observation=observation,
            )
            if prior_source is not None and prior_observation is not None
            else None
        )
        model = build_prospective_public_model(
            nct_id=nct_id,
            epoch=epoch,
            observation=observation,
            exact_diff=exact_diff,
            generated_at=run["finished_at"],
            prior_model=prior_model,
        )
        _write_private_prospective_immutable(
            private_stage,
            relative=(
                "biocatalyst/derived/clinicaltrials/prospective/"
                f"{epoch_id}/{nct_id}/models/{model['model_payload_sha256']}.json"
            ),
            document=model,
        )
        _write_private_prospective_immutable(
            private_stage,
            relative=(
                "biocatalyst/derived/clinicaltrials/prospective/"
                f"{epoch_id}/{nct_id}/observations/{observation['observation_id']}.json"
            ),
            document=observation,
        )
        if exact_diff is not None:
            _write_private_prospective_immutable(
                private_stage,
                relative=(
                    "biocatalyst/derived/clinicaltrials/prospective/"
                    f"{epoch_id}/{nct_id}/diffs/{exact_diff['diff_payload_sha256']}.json"
                ),
                document=exact_diff,
            )
        models[nct_id] = model
        evidence_by_nct[nct_id] = ProspectivePublicationEvidence(
            epoch=epoch,
            current=current,
            current_observation=observation,
            exact_diff=exact_diff,
            generated_at=run["finished_at"],
            prior=prior_source,
            prior_observation=prior_observation,
            prior_model=prior_model,
        )
    return models, evidence_by_nct


def _validate_worker_authority(run: Mapping[str, Any], config: WorkerConfig) -> None:
    """Require this canary worker to publish only its explicit NCT universe."""

    if run.get("mode") != "canary_poll":
        raise PublicationError("WORKER_MODE_BINDING_MISMATCH")
    manifest = run.get("query_manifest")
    configured = manifest.get("configured_nct_ids") if isinstance(manifest, Mapping) else None
    if not isinstance(configured, list) or tuple(configured) != config.nct_ids:
        raise PublicationError("WORKER_CANARY_BINDING_MISMATCH")


def _validate_supported_code_version(run: Mapping[str, Any]) -> None:
    """Refuse to publish or replay a run parsed by an unknown code surface."""

    try:
        from collectors.biocatalyst.clinicaltrials_v2 import current_b1_code_version

        expected = current_b1_code_version()
    except Exception as exc:
        raise PublicationError("UNSUPPORTED_CODE_VERSION") from exc
    if run.get("code_version") != expected:
        raise PublicationError("UNSUPPORTED_CODE_VERSION")


def _default_collector_factory(
    *,
    private_root: Path,
    public_root: Path,
    nct_ids: tuple[str, ...],
    user_agent: str,
    now_fn: Callable[[], datetime],
) -> Collector:
    # Delay network-collector imports until after disabled/misconfigured exits.
    from collectors.biocatalyst.clinicaltrials_v2 import (
        ClinicalTrialsV2Collector,
        ClinicalTrialsV2Config,
    )

    return ClinicalTrialsV2Collector(
        private_root=private_root,
        public_root=public_root,
        config=ClinicalTrialsV2Config(nct_ids=nct_ids, user_agent=user_agent),
        now_fn=now_fn,
    )


def _default_history_collector_factory(
    *,
    private_root: Path,
    nct_ids: tuple[str, ...],
    user_agent: str,
    now_fn: Callable[[], datetime],
) -> HistoryCollector:
    """Construct the optional B2 source collector without a public-root handle."""

    from collectors.biocatalyst.clinicaltrials_history import (
        ClinicalTrialsHistoryCollector,
        ClinicalTrialsHistoryConfig,
    )

    return ClinicalTrialsHistoryCollector(
        private_root=private_root,
        config=ClinicalTrialsHistoryConfig(nct_ids=nct_ids, user_agent=user_agent),
        now_fn=now_fn,
    )


def _history_source_uri(nct_id: str, resource_kind: str, source_version: int | None) -> str:
    root = f"https://clinicaltrials.gov/api/int/studies/{nct_id}"
    if resource_kind == "history_index" and source_version is None:
        return f"{root}?history=true"
    if resource_kind == "history_version" and type(source_version) is int and source_version >= 0:
        return f"{root}/history/{source_version}"
    raise PublicationError("HISTORY_EVIDENCE_INVALID")


def _history_date(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    return value


def _history_study(payload: Mapping[str, Any], nct_id: str) -> Mapping[str, Any]:
    study = payload.get("study")
    try:
        source_nct = study["protocolSection"]["identificationModule"]["nctId"]
    except (KeyError, TypeError) as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    if not isinstance(study, Mapping) or source_nct != nct_id:
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    return study


def _history_manifest_from_index(payload: Mapping[str, Any], nct_id: str) -> list[dict[str, Any]]:
    """Rebuild the only allowed version manifest from private raw index bytes."""

    _history_study(payload, nct_id)
    history = payload.get("history")
    changes = history.get("changes") if isinstance(history, Mapping) else None
    if not isinstance(changes, list) or not changes:
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    manifest: list[dict[str, Any]] = []
    for source_version, change in enumerate(changes):
        if not isinstance(change, Mapping) or type(change.get("version")) is not int:
            raise PublicationError("HISTORY_EVIDENCE_INVALID")
        if change["version"] != source_version:
            raise PublicationError("HISTORY_EVIDENCE_INVALID")
        module_labels = change.get("moduleLabels")
        if (
            not isinstance(module_labels, list)
            or len(module_labels) != len(set(module_labels))
            or any(not isinstance(label, str) or not label.strip() for label in module_labels)
            or not isinstance(change.get("status"), str)
            or not change["status"]
            or not isinstance(change.get("studyType"), str)
            or not change["studyType"]
        ):
            raise PublicationError("HISTORY_EVIDENCE_INVALID")
        qc = change.get("lastUpdateSubmitQcDate")
        if qc is not None:
            qc = _history_date(qc)
        manifest.append(
            {
                "source_version": source_version,
                "display_version": source_version + 1,
                "source_submitted_at": _history_date(change.get("date")),
                "source_last_update_submit_qc_at": qc,
                "module_labels": list(module_labels),
            }
        )
    return manifest


def _history_run_location(run: Mapping[str, Any], nct_id: str) -> tuple[str, str, str]:
    started_at = run.get("started_at")
    run_id = run.get("run_id")
    if not isinstance(started_at, str) or not isinstance(run_id, str) or not _HISTORY_RUN_ID_RE.fullmatch(run_id):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    if started.tzinfo is None or run.get("nct_id") != nct_id:
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    normalized = started.astimezone(timezone.utc)
    stamp = normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")
    expected_id = "ctgov_history_run_" + nct_id + "_" + stamp.replace("-", "").replace(":", "").replace(".", "")
    if run_id != expected_id:
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    return f"{normalized.year:04d}", f"{normalized.month:02d}", run_id


def _history_receipt_from_stage(
    private_stage: Path,
    *,
    year: str,
    month: str,
    run_id: str,
    nct_id: str,
    suffix: str,
    resource_kind: str,
    source_version: int | None,
    config: WorkerConfig,
) -> tuple[dict[str, Any], bytes]:
    """Reload one content-addressed receipt and its exact raw JSON object."""

    expected_receipt_id = f"ctgov_history_receipt_{run_id.removeprefix('ctgov_history_run_')}_{suffix}"
    receipt_path = _private_object_path(
        private_stage,
        f"biocatalyst/receipts/clinicaltrials/history/{year}/{month}/{run_id}/{expected_receipt_id}.json",
    )
    receipt = _strict_json_object(receipt_path)
    try:
        validate_contract("ctgov_history_receipt.v1", receipt)
    except Exception as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    request = receipt.get("request")
    if (
        receipt.get("receipt_id") != expected_receipt_id
        or receipt.get("run_id") != run_id
        or receipt.get("source_id") != "clinicaltrials_gov_record_history"
        or receipt.get("resource_kind") != resource_kind
        or receipt.get("nct_id") != nct_id
        or receipt.get("source_version") != source_version
        or not isinstance(request, Mapping)
        or request.get("method") != "GET"
        or request.get("source_uri") != _history_source_uri(nct_id, resource_kind, source_version)
        or request.get("credentials_stored") is not False
    ):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    _expect_headers(request.get("headers"), config)
    response = receipt.get("response")
    digest = response.get("exact_response_sha256") if isinstance(response, Mapping) else None
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    resource_key = "index" if resource_kind == "history_index" else f"version-{source_version}"
    _raw_path, raw = _expect_exact_response(
        response,
        private_stage=private_stage,
        expected_raw_key=(
            f"biocatalyst/raw/clinicaltrials/history/{nct_id}/{resource_key}/{digest}.json"
        ),
    )
    return receipt, raw


def _private_history_derived_path(
    private_stage: Path,
    *,
    nct_id: str,
    kind: str,
    digest: object,
) -> Path:
    """Return the one fixed content-addressed private derived-artifact path."""

    if kind not in {"diffs", "facts"} or not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    root = private_stage.resolve(strict=True)
    candidate = root / "biocatalyst" / "derived" / "clinicaltrials" / "history" / nct_id / kind / f"{digest}.json"
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    return candidate


def _write_private_history_derived_immutable(
    private_stage: Path,
    *,
    nct_id: str,
    kind: str,
    document: Mapping[str, Any],
    digest_field: str,
) -> Path:
    """Write one canonical derived B2 artifact exactly once, or reject divergence."""

    digest = document.get(digest_field)
    path = _private_history_derived_path(
        private_stage, nct_id=nct_id, kind=kind, digest=digest
    )
    payload = canonical_json_bytes(document) + b"\n"
    root = private_stage.resolve(strict=True)
    current = root
    for component in path.relative_to(root).parts[:-1]:
        current = current / component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
                metadata = current.lstat()
            except (FileExistsError, OSError) as exc:
                raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
        except OSError as exc:
            raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise PublicationError("HISTORY_EVIDENCE_INVALID")

    def verify_existing() -> Path:
        existing = _path_within(path, root, code="HISTORY_EVIDENCE_INVALID")
        try:
            actual = existing.read_bytes()
        except OSError as exc:
            raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
        if actual != payload:
            raise PublicationError("IMMUTABLE_OBJECT_COLLISION")
        return existing

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            return verify_existing()
        except OSError as exc:
            raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    except OSError as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    else:
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise PublicationError("HISTORY_EVIDENCE_INVALID")
        return verify_existing()
    return verify_existing()


def _complete_history_model_from_result(
    *,
    private_stage: Path,
    result: object,
    nct_id: str,
    config: WorkerConfig,
    generated_at: str,
) -> tuple[dict[str, Any], HistoryPublicationEvidence]:
    """Replay one B2 result strictly from the private stage, not object memory."""

    run_path = _path_within(getattr(result, "run_path", None), private_stage, code="HISTORY_EVIDENCE_INVALID")
    run = _strict_json_object(run_path)
    year, month, run_id = _history_run_location(run, nct_id)
    expected_run_path = _private_object_path(
        private_stage,
        f"biocatalyst/runs/clinicaltrials/history/{year}/{month}/{run_id}.json",
    )
    if run_path != expected_run_path or run_path.read_bytes() != canonical_json_bytes(run) + b"\n":
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    if getattr(result, "run_id", None) != run_id or getattr(result, "nct_id", None) != nct_id:
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    try:
        validate_contract("ctgov_history_run.v1", run)
    except Exception as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    manifest = run.get("version_manifest")
    if not isinstance(manifest, list) or not manifest:
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    index_receipt, index_raw = _history_receipt_from_stage(
        private_stage, year=year, month=month, run_id=run_id, nct_id=nct_id,
        suffix="index_pre", resource_kind="history_index", source_version=None, config=config,
    )
    try:
        index_payload = validate_ctgov_history_receipt_against_raw_response(
            index_receipt, index_raw
        )
    except Exception as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    raw_manifest = _history_manifest_from_index(index_payload, nct_id)
    if manifest != raw_manifest or run.get("history_index_receipt_ref") != index_receipt.get("receipt_id"):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    version_receipts: list[dict[str, Any]] = []
    raw_bodies_by_receipt: dict[str, bytes] = {index_receipt["receipt_id"]: index_raw}
    raw_studies: dict[int, Mapping[str, Any]] = {}
    source_versions = [entry.get("source_version") for entry in manifest if isinstance(entry, Mapping)]
    if (
        len(source_versions) != len(manifest)
        or any(type(version) is not int or version < 0 for version in source_versions)
        or source_versions != sorted(source_versions)
        or len(source_versions) != len(set(source_versions))
    ):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    # B2's current contract deliberately requires a contiguous complete chain.
    # Check that against the *listed* source IDs before any version lookup; do
    # not turn a 0,2 index into a fabricated fetch for source version 1.
    if source_versions != list(range(len(source_versions))):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    for version in source_versions:
        receipt, raw = _history_receipt_from_stage(
            private_stage, year=year, month=month, run_id=run_id, nct_id=nct_id,
            suffix=f"version_{version}", resource_kind="history_version",
            source_version=version, config=config,
        )
        try:
            payload = validate_ctgov_history_receipt_against_raw_response(receipt, raw)
        except Exception as exc:
            raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
        if type(payload.get("studyVersion")) is not int or payload.get("studyVersion") != version:
            raise PublicationError("HISTORY_EVIDENCE_INVALID")
        raw_studies[version] = _history_study(payload, nct_id)
        version_receipts.append(receipt)
        raw_bodies_by_receipt[receipt["receipt_id"]] = raw
    post_receipt, post_raw = _history_receipt_from_stage(
        private_stage, year=year, month=month, run_id=run_id, nct_id=nct_id,
        suffix="index_post", resource_kind="history_index", source_version=None, config=config,
    )
    raw_bodies_by_receipt[post_receipt["receipt_id"]] = post_raw
    if (
        run.get("history_index_post_receipt_ref") != post_receipt.get("receipt_id")
        or post_receipt.get("receipt_id") == index_receipt.get("receipt_id")
    ):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    try:
        validate_ctgov_history_run_against_receipts(
            run,
            index_receipt,
            post_receipt,
            version_receipts,
            raw_bodies_by_receipt=raw_bodies_by_receipt,
        )
    except Exception as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc

    snapshot_root = private_stage / "biocatalyst" / "source_snapshots" / "clinicaltrials" / "history" / nct_id
    if not snapshot_root.is_dir() or snapshot_root.is_symlink():
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    snapshots_by_version: dict[int, dict[str, Any]] = {}
    entries = sorted(snapshot_root.iterdir(), key=lambda item: item.name)
    if len(entries) != len(manifest):
        raise PublicationError("HISTORY_EVIDENCE_INVALID")
    for path in entries:
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise PublicationError("HISTORY_EVIDENCE_INVALID")
        snapshot_path = _path_within(path, private_stage, code="HISTORY_EVIDENCE_INVALID")
        snapshot = _strict_json_object(snapshot_path)
        source_version = snapshot.get("source_version")
        if type(source_version) is not int or source_version not in source_versions:
            raise PublicationError("HISTORY_EVIDENCE_INVALID")
        content_hash = snapshot.get("canonical_content_sha256")
        expected_snapshot_id = (
            f"ctgov_history_snapshot_{nct_id}_"
            + canonical_json_sha256(
                {
                    "nct_id": nct_id,
                    "source_version": source_version,
                    "canonical_content_sha256": content_hash,
                    "run_ref": run_id,
                }
            )[:24]
            if isinstance(content_hash, str)
            else ""
        )
        if (
            not _HISTORY_SNAPSHOT_ID_RE.fullmatch(str(snapshot.get("source_snapshot_id")))
            or snapshot.get("source_snapshot_id") != expected_snapshot_id
            or path.name != f"{expected_snapshot_id}.json"
            or source_version in snapshots_by_version
            or snapshot_path.read_bytes() != canonical_json_bytes(snapshot) + b"\n"
            or canonical_json_bytes(snapshot.get("canonical_study")) != canonical_json_bytes(raw_studies[source_version])
        ):
            raise PublicationError("HISTORY_EVIDENCE_INVALID")
        try:
            validate_trial_history_snapshot_against_evidence(
                snapshot,
                run,
                index_receipt,
                post_receipt,
                version_receipts[source_version],
                all_version_receipts=version_receipts,
                raw_bodies_by_receipt=raw_bodies_by_receipt,
            )
        except Exception as exc:
            raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
        snapshots_by_version[source_version] = snapshot
    snapshots = [snapshots_by_version[version] for version in source_versions]
    facts: list[dict[str, Any]] = []
    for before, after in zip(snapshots, snapshots[1:]):
        if before["canonical_content_sha256"] == after["canonical_content_sha256"]:
            continue
        try:
            diff = build_history_exact_diff(
                before,
                after,
                transaction_from=after["transaction_from"],
            )
            diff_path = _write_private_history_derived_immutable(
                private_stage,
                nct_id=nct_id,
                kind="diffs",
                document=diff,
                digest_field="diff_payload_sha256",
            )
            reloaded_diff = _strict_json_object(diff_path)
            if diff_path.read_bytes() != canonical_json_bytes(reloaded_diff) + b"\n":
                raise PublicationError("HISTORY_EVIDENCE_INVALID")
            validate_trial_history_diff_against_snapshots(reloaded_diff, before, after)
            for fact in derive_history_change_facts(before, after, reloaded_diff):
                fact_path = _write_private_history_derived_immutable(
                    private_stage,
                    nct_id=nct_id,
                    kind="facts",
                    document=fact,
                    digest_field="fact_payload_sha256",
                )
                reloaded_fact = _strict_json_object(fact_path)
                if fact_path.read_bytes() != canonical_json_bytes(reloaded_fact) + b"\n":
                    raise PublicationError("HISTORY_EVIDENCE_INVALID")
                validate_trial_registry_change_fact_against_diff(
                    reloaded_fact,
                    reloaded_diff,
                    before,
                    after,
                )
                facts.append(reloaded_fact)
        except Exception as exc:
            raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc
    try:
        model = build_history_read_model(snapshots, facts, generated_at=generated_at)
        return model, HistoryPublicationEvidence(
            snapshots=tuple(snapshots),
            facts=tuple(facts),
        )
    except Exception as exc:
        raise PublicationError("HISTORY_EVIDENCE_INVALID") from exc


def _prior_complete_history_models(
    publisher: PublicGenerationPublisher,
    config: WorkerConfig,
) -> dict[str, dict[str, Any]]:
    """Read only pointer-bound complete B2 models; B1.1 is not last-good history."""

    try:
        projection = publisher.read_trial_projection()
    except PublicationError:
        return {}
    if projection is None:
        return {}
    models: dict[str, dict[str, Any]] = {}
    for nct_id in config.nct_ids:
        model = projection.history_models_by_nct.get(nct_id)
        if isinstance(model, Mapping) and model.get("available") is True:
            models[nct_id] = json.loads(canonical_json_bytes(model))
    return models


def _history_unavailable_reason(exc: BaseException) -> str:
    code = getattr(exc, "code", "")
    if isinstance(code, str) and (
        code.startswith("INVALID_HISTORY")
        or code.startswith("HISTORY_")
        or code in {"RAW_EVIDENCE_INVALID", "HISTORY_EVIDENCE_INVALID"}
    ):
        return "source_shape_drift"
    return "incomplete_chain"


def _history_models_for_generation(
    *,
    private_stage: Path,
    config: WorkerConfig,
    publisher: PublicGenerationPublisher,
    history_collector_factory: HistoryCollectorFactory,
    generated_at: str,
    now_fn: Callable[[], datetime],
) -> tuple[dict[str, dict[str, Any]], dict[str, HistoryPublicationEvidence]]:
    """Build one model per current NCT without letting B2 availability gate B1."""

    # The public pointer is the only eligible history cache.  Disabling the
    # collector suppresses refreshes; it must not silently erase a complete,
    # already pointer-bound source-fact chain.
    prior_models = _prior_complete_history_models(publisher, config)
    if not config.history_enabled:
        models: dict[str, dict[str, Any]] = {}
        evidence: dict[str, HistoryPublicationEvidence] = {}
        for nct_id in config.nct_ids:
            prior_model = prior_models.get(nct_id)
            if prior_model is not None:
                models[nct_id] = prior_model
                evidence[nct_id] = HistoryPublicationEvidence(carried_forward=True)
            else:
                models[nct_id] = build_unavailable_history_read_model(
                    nct_id, unavailable_reason="disabled", generated_at=generated_at
                )
                evidence[nct_id] = HistoryPublicationEvidence()
        return models, evidence
    try:
        collector = history_collector_factory(
            private_root=private_stage,
            nct_ids=config.nct_ids,
            user_agent=config.user_agent,
            now_fn=now_fn,
        )
    except Exception as exc:
        reason = _history_unavailable_reason(exc)
        models = {}
        evidence = {}
        for nct_id in config.nct_ids:
            prior_model = prior_models.get(nct_id)
            if prior_model is not None:
                models[nct_id] = prior_model
                evidence[nct_id] = HistoryPublicationEvidence(carried_forward=True)
            else:
                models[nct_id] = build_unavailable_history_read_model(
                    nct_id, unavailable_reason=reason, generated_at=generated_at
                )
                evidence[nct_id] = HistoryPublicationEvidence()
        return models, evidence
    models: dict[str, dict[str, Any]] = {}
    evidence: dict[str, HistoryPublicationEvidence] = {}
    for nct_id in config.nct_ids:
        try:
            result = collector.collect_nct(nct_id)
            models[nct_id], evidence[nct_id] = _complete_history_model_from_result(
                private_stage=private_stage,
                result=result,
                nct_id=nct_id,
                config=config,
                generated_at=generated_at,
            )
        except Exception as exc:
            prior_model = prior_models.get(nct_id)
            if prior_model is not None:
                models[nct_id] = prior_model
                evidence[nct_id] = HistoryPublicationEvidence(carried_forward=True)
            else:
                models[nct_id] = build_unavailable_history_read_model(
                    nct_id,
                    unavailable_reason=_history_unavailable_reason(exc),
                    generated_at=generated_at,
                )
                evidence[nct_id] = HistoryPublicationEvidence()
    return models, evidence


def _default_store_factory(config: DedicatedR2Config) -> BinaryObjectStore:
    return DedicatedR2Store(config)


@contextmanager
def _nonblocking_worker_lock(state_root: Path) -> Iterator[object | None]:
    """Acquire the process-local guard; a concurrent timer tick is a safe no-op."""

    _ensure_real_directory(state_root)
    lock_path = state_root / "biocatalyst_worker.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise OSError("unsafe worker lock")
        handle = os.fdopen(descriptor, "a+")
    except OSError as exc:
        try:
            os.close(descriptor)
        except (NameError, OSError):
            pass
        raise PublicationError("BIOCATALYST_RUNTIME_PATH_INVALID") from exc
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            yield None
            return
        yield handle
    finally:
        if not handle.closed:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


def _attempt_id(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("now_fn must return timezone-aware datetimes")
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"attempt_{stamp}_{uuid.uuid4().hex[:12]}"


def _bounded_code(exc: BaseException) -> str:
    candidate = getattr(exc, "code", None)
    return candidate if candidate in _SAFE_ERROR_CODES else "COLLECTION_FAILED"


def _failure_state(code: str) -> str:
    return "quarantined" if code in _QUARANTINE_CODES else "partial"


def _try_write_health(
    publisher: PublicGenerationPublisher,
    *,
    state: str,
    enabled: bool,
    configured_nct_count: int,
    error_code: str | None,
    prior: CommittedGeneration | None,
    now: datetime,
) -> None:
    """Health is deliberately best-effort after an incident; it is never a pointer."""

    try:
        publisher.write_health(
            failure_health(
                state=state,
                enabled=enabled,
                configured_nct_count=configured_nct_count,
                error_code=error_code,
                prior=prior,
                now=now,
            )
        )
    except Exception:
        # Avoid adding a second, potentially unbounded failure string to the journal.
        return


def _actual_committed_or(
    publisher: PublicGenerationPublisher,
    fallback: CommittedGeneration | None,
) -> CommittedGeneration | None:
    """Re-read after a pointer fault so health never assumes a rollback happened."""

    try:
        return publisher.read_committed()
    except PublicationError:
        # If the pointer cannot be read after a failed mutation, reporting an
        # older cached generation would be a false operational assertion.
        return None


def run_once(
    config: WorkerConfig,
    *,
    collector_factory: CollectorFactory = _default_collector_factory,
    history_collector_factory: HistoryCollectorFactory = _default_history_collector_factory,
    store_factory: StoreFactory = _default_store_factory,
    now_fn: Callable[[], datetime] = _utc_now,
    publisher_factory: Callable[[Path], PublicGenerationPublisher] = PublicGenerationPublisher,
    activation_verifier: ActivationVerifier = _default_activation_verifier,
) -> WorkerResult:
    """Run one bounded evidence transaction through injectable collector/store seams."""

    try:
        _prepare_runtime_layout(config)
    except Exception as exc:
        code = _bounded_code(exc)
        try:
            publisher = publisher_factory(config.public_root)
        except Exception:
            return WorkerResult(EXIT_FAILED, "failed", error_code=code)
        prior = _actual_committed_or(publisher, None)
        _try_write_health(
            publisher,
            state=_failure_state(code),
            enabled=True,
            configured_nct_count=len(config.nct_ids),
            error_code=code,
            prior=prior,
            now=now_fn(),
        )
        return WorkerResult(EXIT_FAILED, "failed", error_code=code)

    publisher = publisher_factory(config.public_root)
    with _nonblocking_worker_lock(config.state_root) as lock:
        if lock is None:
            return WorkerResult(EXIT_SUCCESS, "locked")

        prior: CommittedGeneration | None = None
        attempt_root: Path | None = None
        private_archive_root: Path | None = None
        r2_mirror_state = "not_started"
        store: BinaryObjectStore | None = None
        candidate_run_id: str | None = None
        attempt_id = _attempt_id(now_fn())
        try:
            prior = publisher.read_committed()
            if (
                prior is not None
                and prior.schema_version == "1.3.0"
                and not config.prospective_enabled
            ):
                raise PublicationError("BIOCATALYST_PROSPECTIVE_DOWNGRADE_FORBIDDEN")
            if config.prospective_enabled:
                # The worker performs no Cloudflare control-plane request.  It
                # accepts only a root-sealed gate plus a fresh, root-written
                # heartbeat that bind the exact R2 account, endpoint, bucket,
                # and worker credential identity.  This check precedes even a
                # disposable attempt directory, source collector, or R2 store.
                activation_verifier(config, now_fn())
            expected_watermark = prior.watermark_after if prior else None

            attempt_root = config.state_root / "staging" / attempt_id
            private_stage = attempt_root / "private"
            collector_public_stage = attempt_root / "collector-public"
            private_stage.mkdir(parents=True)
            collector_public_stage.mkdir(parents=True)
            collector = collector_factory(
                private_root=private_stage,
                public_root=collector_public_stage,
                nct_ids=config.nct_ids,
                user_agent=config.user_agent,
                now_fn=now_fn,
            )
            result = collector.collect(watermark_before=expected_watermark)
            run_path = _path_within(result.run_path, private_stage, code="RUN_CONTRACT_INVALID")
            generation_path = _path_within(
                result.generation_path / "publication_manifest.json",
                collector_public_stage,
                code="COLLECTOR_GENERATION_OUTSIDE_STAGE",
            ).parent
            candidate_run = _strict_json_object(run_path)
            _validate_worker_authority(candidate_run, config)
            run = validate_candidate_run(candidate_run, expected_watermark=expected_watermark)
            _validate_supported_code_version(run)
            if getattr(result, "run_id", None) != run["run_id"]:
                raise PublicationError("RUN_ID_INVALID")
            candidate_run_id = run["run_id"]
            assert_source_timestamp_monotonic(
                run["source_dataset_timestamp_before_raw"],
                prior,
            )
            assert_source_timestamp_not_future(
                run["source_dataset_timestamp_before_raw"],
                now=now_fn(),
            )

            validated_evidence = _validate_private_raw_evidence(
                private_stage,
                run,
                run_path=run_path,
                config=config,
            )

            # B2 is deliberately optional.  It starts only after the B1 source
            # bundle has been independently replayed, and every B2 failure is
            # collapsed to a per-NCT complete prior model or an explicit
            # unavailable model.  It can never replace the current B1 facts.
            history_models_by_nct, history_evidence_by_nct = _history_models_for_generation(
                private_stage=private_stage,
                config=config,
                publisher=publisher,
                history_collector_factory=history_collector_factory,
                generated_at=run["finished_at"],
                now_fn=now_fn,
            )

            prospective_models_by_nct: dict[str, dict[str, Any]] | None = None
            prospective_evidence_by_nct: (
                dict[str, ProspectivePublicationEvidence] | None
            ) = None
            if config.prospective_enabled:
                # B4D accrues only across successive successful official-API
                # observations in the same explicit NCT scope.  A legacy
                # generation or a scope change deliberately starts a fresh
                # epoch; a same-scope v1.3 generation must have its exact
                # prior private source evidence present and replayable or the
                # run quarantines.
                prior_prospective_state: PriorProspectiveState | None = None
                if prior is not None and prior.schema_version == "1.3.0":
                    prior_projection = publisher.read_trial_projection()
                    if prior_projection is None:
                        raise PublicationError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
                    prior_scope = tuple(
                        sorted(
                            trial.get("nct_id")
                            for trial in prior_projection.trials
                            if isinstance(trial.get("nct_id"), str)
                        )
                    )
                    if prior_scope == config.nct_ids:
                        store = store_factory(config.r2)
                        if not isinstance(store, BinaryObjectStore):
                            raise StorageError("BIOCATALYST_R2_CLIENT_UNAVAILABLE")
                        prior_prospective_state = _load_prior_prospective_state(
                            config=config,
                            prior=prior,
                            publisher=publisher,
                            store=store,
                        )
                prospective_models_by_nct, prospective_evidence_by_nct = (
                    _build_prospective_generation(
                        private_stage=private_stage,
                        run=run,
                        validated_evidence=validated_evidence,
                        config=config,
                        prior_state=prior_prospective_state,
                    )
                )

            # Validate the collector's public projection against independently
            # validated private snapshots while it is still a disposable stage.
            # No R2 object or actual public generation exists at this point.
            health = success_health(run=run, generation_id=run["run_id"])
            prepared = publisher.prepare_generation(
                collector_generation=generation_path,
                collector_public_root=collector_public_stage,
                final_stage=attempt_root / "public-final",
                run=run,
                expected_watermark=expected_watermark,
                health=health,
                validated_snapshots_by_nct=validated_evidence.snapshots_by_nct,
                source_receipts=validated_evidence.receipts,
                raw_page_bodies_by_receipt=(
                    validated_evidence.raw_page_bodies_by_receipt
                ),
                history_models_by_nct=history_models_by_nct,
                history_evidence_by_nct=history_evidence_by_nct,
                prospective_models_by_nct=prospective_models_by_nct,
                prospective_evidence_by_nct=prospective_evidence_by_nct,
            )

            # Construct the dedicated client only after every local source,
            # snapshot, and collector-projection check has passed.  This keeps
            # failed source collection entirely outside the R2 plane.
            if store is None:
                store = store_factory(config.r2)
                if not isinstance(store, BinaryObjectStore):
                    raise StorageError("BIOCATALYST_R2_CLIENT_UNAVAILABLE")
            receipts = mirror_tree_verified(store, root=private_stage)
            r2_mirror_state = "objects_verified"
            private_archive_root = archive_private_stage(
                private_stage,
                state_root=config.state_root,
                run_id=run["run_id"],
            )
            mirror_manifest = build_private_mirror_manifest(
                private_archive_root,
                run_id=run["run_id"],
                receipts=receipts,
                verified_at=run["finished_at"],
            )
            mirror_private_receipt(store, mirror_manifest)
            r2_mirror_state = "mirror_receipt_verified"

            publisher.install_generation(prepared)
            publisher.write_pointer(prepared)
            # The generation's health is part of the pointer-bound immutable
            # bundle.  The mutable operational health is deliberately written
            # only after that commit marker advances; an I/O failure here cannot
            # turn a successful evidence commit into a failed worker outcome.
            try:
                publisher.write_health(health)
            except Exception:
                pass
            if attempt_root.exists():
                try:
                    shutil.rmtree(attempt_root)
                except OSError:
                    pass
            return WorkerResult(EXIT_SUCCESS, "success", generation_id=prepared.generation_id)
        except Exception as exc:
            code = _bounded_code(exc)
            dead_letter_path: Path | None = None
            if attempt_root is not None:
                dead_letter_path = archive_failed_attempt(
                    attempt_root,
                    state_root=config.state_root,
                    attempt_id=attempt_id,
                )
            actual_prior = _actual_committed_or(publisher, prior)
            # Once private evidence was retained, leave a bounded immutable
            # incident receipt beside it even if the later R2 mirror-receipt or
            # public-generation step fails.  This is best-effort by design: an
            # incident-write fault must not conceal the original failure code.
            incident_root = private_archive_root or dead_letter_path
            if incident_root is not None and candidate_run_id is not None:
                dead_letter_ref = (
                    f"dead-letter/{attempt_id}" if dead_letter_path is not None else None
                )
                try:
                    write_private_incident(
                        incident_root,
                        run_id=candidate_run_id,
                        attempt_id=attempt_id,
                        failure_code=code,
                        r2_mirror_state=r2_mirror_state,
                        dead_letter_ref=dead_letter_ref,
                        prior=prior,
                        observed=actual_prior,
                        now=now_fn(),
                    )
                except Exception:
                    pass
            _try_write_health(
                publisher,
                state=_failure_state(code),
                enabled=True,
                configured_nct_count=len(config.nct_ids),
                error_code=code,
                prior=actual_prior,
                now=now_fn(),
            )
            return WorkerResult(EXIT_FAILED, "failed", error_code=code)


def run_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    collector_factory: CollectorFactory = _default_collector_factory,
    history_collector_factory: HistoryCollectorFactory = _default_history_collector_factory,
    store_factory: StoreFactory = _default_store_factory,
    now_fn: Callable[[], datetime] = _utc_now,
    activation_verifier: ActivationVerifier = _default_activation_verifier,
) -> WorkerResult:
    """Entry point with safe disabled/misconfigured semantics and no network work."""

    plan = load_environment(environ)
    if plan.state == "enabled":
        assert plan.config is not None
        return run_once(
            plan.config,
            collector_factory=collector_factory,
            history_collector_factory=history_collector_factory,
            store_factory=store_factory,
            now_fn=now_fn,
            activation_verifier=activation_verifier,
        )

    if plan.public_root is not None:
        publisher = PublicGenerationPublisher(plan.public_root)
        prior = _actual_committed_or(publisher, None)
        health_state = "disabled"
        health_enabled = False
        if plan.state == "invalid" and plan.requested_enabled:
            health_state = _failure_state(plan.error_code or "COLLECTION_FAILED")
            health_enabled = True
        _try_write_health(
            publisher,
            state=health_state,
            enabled=health_enabled,
            configured_nct_count=plan.configured_nct_count,
            error_code=plan.error_code,
            prior=prior,
            now=now_fn(),
        )
    if plan.state == "disabled":
        return WorkerResult(EXIT_SUCCESS, "disabled")
    return WorkerResult(EXIT_MISCONFIGURED, "misconfigured", error_code=plan.error_code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("canary_poll",))
    args = parser.parse_args(argv)
    if args.mode != "canary_poll":  # Defensive if argparse choices changes later.
        return EXIT_MISCONFIGURED
    result = run_from_environment()
    detail = result.error_code or result.generation_id or ""
    print(f"biocatalyst-worker: {result.status}{(' ' + detail) if detail else ''}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
