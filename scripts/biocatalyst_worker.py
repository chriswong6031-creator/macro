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
from datetime import datetime, timezone
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

from engine.biocatalyst.publication import (
    CommittedGeneration,
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
_SERVICE_STATE_ROOT = Path("/var/lib/macro-biocatalyst/state")
_SERVICE_PUBLIC_ROOT = Path("/var/lib/macro-biocatalyst/public")
_SAFE_ERROR_CODES = frozenset(
    {
        "ARCHIVE_READBACK_MISMATCH",
        "BIOCATALYST_R2_BUCKET_INVALID",
        "BIOCATALYST_R2_CLIENT_UNAVAILABLE",
        "BIOCATALYST_R2_CONFIG_MISSING",
        "BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED",
        "BIOCATALYST_R2_CONDITIONAL_CREATE_UNAVAILABLE",
        "BIOCATALYST_R2_ENDPOINT_INVALID",
        "BIOCATALYST_R2_READBACK_FAILED",
        "BIOCATALYST_R2_READBACK_MISMATCH",
        "BIOCATALYST_R2_READ_FAILED",
        "BIOCATALYST_RUNTIME_PATH_INVALID",
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
        object.__setattr__(self, "state_root", state_root)
        object.__setattr__(self, "public_root", public_root)


@dataclass(frozen=True)
class EnvironmentPlan:
    state: str
    config: WorkerConfig | None
    state_root: Path | None
    public_root: Path | None
    configured_nct_count: int
    error_code: str | None = None


@dataclass(frozen=True)
class WorkerResult:
    exit_code: int
    status: str
    error_code: str | None = None
    generation_id: str | None = None


class CollectorResult(Protocol):
    run_id: str
    run_path: Path
    generation_path: Path


class Collector(Protocol):
    def collect(self, *, watermark_before: str | None = None) -> CollectorResult: ...


CollectorFactory = Callable[..., Collector]
StoreFactory = Callable[[DedicatedR2Config], BinaryObjectStore]


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


def load_environment(environ: Mapping[str, str] | None = None) -> EnvironmentPlan:
    """Parse the env contract without ever falling back to another R2 plane."""

    values = os.environ if environ is None else environ
    state_root, public_root = _service_runtime_paths(values)
    raw_ncts = values.get("BIOCATALYST_CANARY_NCTS", "")
    configured_nct_count = len({item.strip() for item in raw_ncts.split(",") if item.strip()})
    enabled = values.get("BIOCATALYST_ENABLED", "").strip()
    if enabled in {"", "0"}:
        return EnvironmentPlan(
            state="disabled",
            config=None,
            state_root=state_root,
            public_root=public_root,
            configured_nct_count=configured_nct_count,
        )
    if enabled != "1":
        return EnvironmentPlan(
            state="invalid",
            config=None,
            state_root=state_root,
            public_root=public_root,
            configured_nct_count=configured_nct_count,
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
        )
    except (StorageError, WorkerConfigError) as exc:
        return EnvironmentPlan(
            state="invalid",
            config=None,
            state_root=state_root,
            public_root=public_root,
            configured_nct_count=configured_nct_count,
            error_code=exc.code,
        )
    return EnvironmentPlan(
        state="enabled",
        config=config,
        state_root=state_root,
        public_root=public_root,
        configured_nct_count=len(config.nct_ids),
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
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise PublicationError("RUN_CONTRACT_INVALID") from exc
    if not isinstance(payload, dict):
        raise PublicationError("RUN_CONTRACT_INVALID")
    try:
        canonical_json_bytes(payload)
    except Exception as exc:
        raise PublicationError("RUN_CONTRACT_INVALID") from exc
    return payload


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
) -> dict[str, dict[str, Any]]:
    """Independently prove B1 run -> exact probes/pages -> canonical snapshots.

    The worker treats every collector write as hostile until this boundary has
    reloaded it from disk.  It intentionally derives every live path from the
    run clock, deterministic run ID, page ordinal, and content hash rather than
    trusting a path supplied by the collector.
    """

    try:
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
        if actual_files != expected_files or actual_directories != expected_directories:
            raise PublicationError("RAW_EVIDENCE_INVALID")
        return snapshots_by_nct
    except PublicationError as exc:
        if exc.code == "RAW_EVIDENCE_INVALID":
            raise
        raise PublicationError("RAW_EVIDENCE_INVALID") from exc
    except Exception as exc:
        raise PublicationError("RAW_EVIDENCE_INVALID") from exc


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
    store_factory: StoreFactory = _default_store_factory,
    now_fn: Callable[[], datetime] = _utc_now,
    publisher_factory: Callable[[Path], PublicGenerationPublisher] = PublicGenerationPublisher,
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
        candidate_run_id: str | None = None
        attempt_id = _attempt_id(now_fn())
        try:
            prior = publisher.read_committed()
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

            validated_snapshots_by_nct = _validate_private_raw_evidence(
                private_stage,
                run,
                run_path=run_path,
                config=config,
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
                validated_snapshots_by_nct=validated_snapshots_by_nct,
            )

            # Construct the dedicated client only after every local source,
            # snapshot, and collector-projection check has passed.  This keeps
            # failed source collection entirely outside the R2 plane.
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
    store_factory: StoreFactory = _default_store_factory,
    now_fn: Callable[[], datetime] = _utc_now,
) -> WorkerResult:
    """Entry point with safe disabled/misconfigured semantics and no network work."""

    plan = load_environment(environ)
    if plan.state == "enabled":
        assert plan.config is not None
        return run_once(
            plan.config,
            collector_factory=collector_factory,
            store_factory=store_factory,
            now_fn=now_fn,
        )

    if plan.public_root is not None:
        publisher = PublicGenerationPublisher(plan.public_root)
        prior = _actual_committed_or(publisher, None)
        _try_write_health(
            publisher,
            state="disabled",
            enabled=False,
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
