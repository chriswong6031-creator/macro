"""Fail-closed local publication for the BioCatalyst ClinicalTrials.gov lane.

The collector is intentionally allowed to write only an attempt-private root and
an attempt-public staging root.  This module validates the collector's
allowlisted read projection, creates one complete public generation, and moves
the small current pointer last.  A failure never rewrites the last good pointer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any, Callable, Mapping, Sequence

from engine.sector_intelligence import (
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
    validate_trial_history_read_model,
    validate_trial_projection_against_source,
)

from .storage import MirrorReceipt, StorageError, mirror_bytes_verified
from .trials import build_trial_snapshot, validate_trial_snapshot
from .prospective import (
    ProspectiveError,
    SourceEvidence as ProspectiveSourceEvidence,
    validate_public_model as validate_prospective_public_model,
    validate_publication_evidence as validate_prospective_publication_evidence,
)


_RUN_ID_RE = re.compile(r"^ctgov_run_[A-Za-z0-9_]+$")
_NCT_ID_RE = re.compile(r"^NCT[0-9]{8}$")
_SOURCE_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2})?$"
)

_COLLECTOR_MANIFEST_KEYS = frozenset(
    {
        "manifest_version",
        "hash_scope",
        "run_id",
        "query_sha256",
        "source_dataset_timestamp_raw",
        "entries",
        "manifest_sha256",
    }
)
_COLLECTOR_ENTRY_KEYS = frozenset(
    {
        "nct_id",
        "source_snapshot_id",
        "source_record_ref",
        "public_state_sha256",
    }
)
_PUBLIC_STATE_KEYS = frozenset(
    {
        "contract_id",
        "schema_version",
        "nct_id",
        "source_snapshot_id",
        "source_record_ref",
        "canonical_content_sha256",
        "source_uri",
        "source_dataset_timestamp_raw",
        "source_last_update_posted_at",
        "source_published_at",
        "retrieved_at",
        "coverage_class",
        "license_class",
        "source_attribution",
        "modification_disclosure",
    }
)
_PUBLIC_GENERATION_MANIFEST_KEYS = frozenset(
    {
        "contract_id",
        "schema_version",
        "generation_id",
        "run_id",
        "source_dataset_timestamp_raw",
        "watermark_after",
        "published_at",
        "coverage_class",
        "hash_scope",
        "source_manifest_sha256",
        "query_sha256",
        "configured_nct_ids",
        "published_source_record_refs",
        "configured_nct_count",
        "observed_nct_count",
        "last_attempt_at",
        "last_success_at",
        "artifacts",
        "manifest_sha256",
    }
)
_POINTER_KEYS = frozenset(
    {
        "contract_id",
        "schema_version",
        "generation_id",
        "manifest_sha256",
        "watermark_after",
        "published_at",
    }
)
_ARTIFACT_KEYS = frozenset(("name", "sha256", "byte_count"))
_PUBLIC_GENERATION_SCHEMAS = frozenset(("1.0.0", "1.1.0", "1.2.0", "1.3.0"))
_TRIAL_SNAPSHOT_DIRECTORY = "trial_snapshots"
_TRIAL_HISTORY_DIRECTORY = "history"
_TRIAL_PROSPECTIVE_DIRECTORY = "prospective"
_HEALTH_KEYS = frozenset(
    {
        "schema_version",
        "state",
        "enabled",
        "generation_id",
        "configured_nct_count",
        "observed_nct_count",
        "last_attempt_at",
        "last_success_at",
        "source_dataset_timestamp_raw",
        "freshness_budget_seconds",
        "coverage_class",
        "last_error_code",
    }
)
_SAFE_HEALTH_STATES = frozenset(
    ("fresh", "stale", "partial", "quarantined", "disabled", "unavailable")
)

# The worker accepts only the exact CT.gov v2 wire shape.  The broader B0
# contract intentionally permits legacy fixtures without this trio, but a live
# B1 run must never turn a partial/mutated wire manifest into publishable facts.
_CTGOV_V2_API_ROOT = "https://clinicaltrials.gov/api/v2"
_CTGOV_V2_REQUEST_PATH = "/studies"

# These are the complete bounded codes the B1 collector can emit today.  They
# are deliberately enumerated here so a source-integrity incident retains its
# meaning through the outer worker health surface instead of collapsing to a
# generic collection failure.
_COLLECTOR_INCIDENT_CODES = frozenset(
    (
        "ARCHIVE_READBACK_MISMATCH",
        "COLLECTION_FAILED",
        "CONTRACT_VALIDATION_FAILED",
        "COUNT_MISMATCH",
        "DIVERGENT_DUPLICATE",
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
        "RECEIPT_ID_MISMATCH",
        "REPLAY_DIVERGENCE",
        "RUN_NOT_REPLAYABLE",
        "SOURCE_CHANGED_MID_RUN",
        "UNSAFE_OBJECT_KEY",
        "UNSUPPORTED_CONTENT_ENCODING",
    )
)

# This is a poisoning guard, not an elapsed-freshness calculation.  CT.gov's
# dataTimestamp can be offset-less, so the offset-less branch compares only
# civil UTC-shaped wall time; it never silently assigns an upstream timezone.
_MAX_SOURCE_FUTURE_SKEW_SECONDS = 36 * 60 * 60


class PublicationError(RuntimeError):
    """A bounded failure code suitable for the public operational-health DTO."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CommittedGeneration:
    generation_id: str
    manifest_sha256: str
    watermark_after: str
    published_at: str
    source_dataset_timestamp_raw: str
    configured_nct_count: int
    observed_nct_count: int
    last_attempt_at: str
    last_success_at: str
    schema_version: str


@dataclass(frozen=True)
class PreparedGeneration:
    generation_id: str
    stage_path: Path
    manifest_sha256: str
    watermark_after: str
    published_at: str
    source_dataset_timestamp_raw: str


@dataclass(frozen=True)
class CommittedTrialProjection:
    """Pointer-bound product projection returned without exposing disk paths."""

    generation: CommittedGeneration
    trials: tuple[dict[str, Any], ...]
    history_models_by_nct: Mapping[str, dict[str, Any]]
    prospective_models_by_nct: Mapping[str, dict[str, Any]]


@dataclass(frozen=True)
class HistoryPublicationEvidence:
    """Private, replay-validated B2 evidence supplied for one public model.

    This is an intentionally typed publication seam.  A complete current
    history model must carry the exact source snapshots and semantic change
    facts which generated it.  A carry-forward has no new evidence because its
    only admissible input is an exact byte copy of the current pointer-bound
    artifact; see ``carried_forward``.
    """

    snapshots: tuple[Mapping[str, Any], ...] = ()
    facts: tuple[Mapping[str, Any], ...] = ()
    carried_forward: bool = False


@dataclass(frozen=True)
class ProspectivePublicationEvidence:
    """Private evidence seam for one bounded prospective public model."""

    epoch: Mapping[str, Any]
    current: ProspectiveSourceEvidence
    current_observation: Mapping[str, Any]
    exact_diff: Mapping[str, Any] | None
    generated_at: str
    prior: ProspectiveSourceEvidence | None = None
    prior_observation: Mapping[str, Any] | None = None
    prior_model: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class PrivateMirrorManifest:
    path: Path
    payload: bytes
    object_key: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("now_fn must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(
    path: Path,
    payload: bytes,
    *,
    after_replace: Callable[[Path], None] | None = None,
) -> None:
    """Durably replace one file without exposing a partial JSON document."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if after_replace is not None:
            after_replace(path)
        _fsync_directory(path.parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _load_json_object(path: Path, *, code: str) -> dict[str, Any]:
    def reject_constant(_: str) -> None:
        raise ValueError("non-finite JSON number")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError("duplicate JSON object key")
            payload[key] = value
        return payload

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise PublicationError(code) from exc
    if not isinstance(payload, dict):
        raise PublicationError(code)
    return payload


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(payload) + b"\n"


def _without(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    copy = dict(payload)
    copy.pop(key, None)
    return copy


def _safe_relative(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or "\\" in name:
        raise PublicationError("PUBLIC_ARTIFACT_PATH_INVALID")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PublicationError("PUBLIC_ARTIFACT_PATH_INVALID")
    if path.as_posix() != name:
        raise PublicationError("PUBLIC_ARTIFACT_PATH_INVALID")
    return path


def _safe_child(root: Path, relative: str) -> Path:
    child = root.joinpath(*_safe_relative(relative).parts)
    try:
        resolved_root = root.resolve(strict=True)
        resolved = child.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise PublicationError("PUBLIC_ARTIFACT_PATH_INVALID") from exc
    if child.is_symlink() or not child.is_file():
        raise PublicationError("PUBLIC_ARTIFACT_PATH_INVALID")
    return child


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _validate_source_timestamp(value: object) -> str:
    if not isinstance(value, str) or not _SOURCE_TIMESTAMP_RE.fullmatch(value):
        raise PublicationError("SOURCE_TIMESTAMP_INVALID")
    _parse_source_timestamp(value)
    return value


def _parse_source_timestamp(value: str) -> datetime:
    """Parse only for ordering; callers retain and publish the exact raw literal."""

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PublicationError("SOURCE_TIMESTAMP_INVALID") from exc


def _bounded_string(value: object, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PublicationError("COLLECTOR_PROJECTION_INVALID")
    return value


def _validate_utc_datetime(value: object) -> str:
    rendered = _bounded_string(value, maximum=64)
    if not rendered.endswith("Z"):
        raise PublicationError("COLLECTOR_PROJECTION_INVALID")
    try:
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError("COLLECTOR_PROJECTION_INVALID") from exc
    if parsed.tzinfo is None:
        raise PublicationError("COLLECTOR_PROJECTION_INVALID")
    return rendered


def _validate_optional_source_date(value: object) -> str | None:
    if value is None:
        return None
    rendered = _bounded_string(value, maximum=10)
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", rendered):
        raise PublicationError("COLLECTOR_PROJECTION_INVALID")
    try:
        date.fromisoformat(rendered)
    except ValueError as exc:
        raise PublicationError("COLLECTOR_PROJECTION_INVALID") from exc
    return rendered


def _validate_ctgov_v2_wire_binding(run: Mapping[str, Any]) -> None:
    """Require the complete, immutable CT.gov v2 request description.

    The registry intentionally remains able to parse legacy B0 fixture
    manifests where these fields are absent.  A B1 publication has a stronger
    boundary: the canonical query hash must bind the exact API root, path, and
    deterministic base parameters which produced its receipts.
    """

    manifest = run.get("query_manifest")
    if not isinstance(manifest, Mapping):
        raise PublicationError("CTGOV_WIRE_BINDING_INVALID")
    configured = manifest.get("configured_nct_ids")
    page_size = manifest.get("page_size")
    if (
        not isinstance(configured, list)
        or not configured
        or any(not isinstance(nct_id, str) or not _NCT_ID_RE.fullmatch(nct_id) for nct_id in configured)
        or not isinstance(page_size, int)
        or isinstance(page_size, bool)
    ):
        raise PublicationError("CTGOV_WIRE_BINDING_INVALID")
    expected_params = {
        "query.id": ",".join(configured),
        "format": "json",
        "pageSize": str(page_size),
        "countTotal": "true",
    }
    if (
        manifest.get("api_root") != _CTGOV_V2_API_ROOT
        or manifest.get("request_path") != _CTGOV_V2_REQUEST_PATH
        or not isinstance(manifest.get("base_query_params"), Mapping)
        or dict(manifest["base_query_params"]) != expected_params
    ):
        raise PublicationError("CTGOV_WIRE_BINDING_INVALID")


def _validate_run(run: Mapping[str, Any], *, expected_watermark: str | None) -> dict[str, Any]:
    """Require a complete source-contract run before any mirror or promotion."""

    try:
        validate_contract(dict(run))
    except Exception as exc:
        raise PublicationError("RUN_CONTRACT_INVALID") from exc
    run_id = run.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise PublicationError("RUN_ID_INVALID")
    if run.get("run_state") != "complete" or run.get("completeness_state") != "reconciled":
        raise PublicationError("RUN_NOT_COMPLETE")
    error_codes = run.get("error_codes")
    if not isinstance(error_codes, list):
        raise PublicationError("RUN_CONTRACT_INVALID")
    if error_codes:
        # A reconciled complete run carries no incident.  Preserve a known
        # collector code rather than flattening it into COLLECTION_FAILED.
        if len(error_codes) == 1 and error_codes[0] in _COLLECTOR_INCIDENT_CODES:
            raise PublicationError(error_codes[0])
        raise PublicationError("COLLECTOR_INCIDENT_PRESENT")
    watermark_before = run.get("watermark_before")
    watermark_after = run.get("watermark_after")
    if watermark_before != expected_watermark:
        raise PublicationError("WATERMARK_BINDING_MISMATCH")
    if not isinstance(watermark_after, str) or not watermark_after:
        raise PublicationError("WATERMARK_INVALID")
    _validate_source_timestamp(run.get("source_dataset_timestamp_before_raw"))
    _validate_source_timestamp(run.get("source_dataset_timestamp_after_raw"))
    if run["source_dataset_timestamp_before_raw"] != run["source_dataset_timestamp_after_raw"]:
        raise PublicationError("SOURCE_TIMESTAMP_INCONSISTENT")
    _validate_ctgov_v2_wire_binding(run)
    return dict(run)


def validate_candidate_run(
    run: Mapping[str, Any], *, expected_watermark: str | None
) -> dict[str, Any]:
    """Public worker seam for validating an injected collector result."""

    return _validate_run(run, expected_watermark=expected_watermark)


def _require_within(path: Path, root: Path, *, code: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
        resolved_root = Path(root).resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise PublicationError(code) from exc
    return resolved


def _require_real_directory(
    path: Path,
    *,
    code: str,
    create: bool = False,
) -> Path:
    """Require one real directory without following its final component.

    These roots are mutation boundaries.  ``Path.is_dir`` alone is unsafe here
    because it follows a pre-planted symlink and would let a later ``replace``
    escape the BioCatalyst state or public tree.
    """

    candidate = Path(path)
    if candidate.is_symlink():
        raise PublicationError(code)
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        if not create:
            raise PublicationError(code) from None
        try:
            candidate.mkdir(mode=0o700)
            metadata = candidate.lstat()
        except (FileExistsError, OSError) as exc:
            raise PublicationError(code) from exc
    except OSError as exc:
        raise PublicationError(code) from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise PublicationError(code)
    return candidate


def _regular_tree_inventory(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return deterministic directory/file inventories or reject unsafe nodes."""

    root = _require_real_directory(root, code="PRIVATE_STAGE_INVALID")
    directories: list[str] = []
    files: list[str] = []
    try:
        tree = list(root.rglob("*"))
    except OSError as exc:
        raise PublicationError("PRIVATE_ARTIFACT_UNREADABLE") from exc
    for path in tree:
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise PublicationError("PRIVATE_ARTIFACT_UNREADABLE") from exc
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(metadata.st_mode):
            raise PublicationError("PRIVATE_STAGE_INVALID")
        if stat.S_ISDIR(metadata.st_mode):
            directories.append(relative)
        elif stat.S_ISREG(metadata.st_mode):
            files.append(relative)
        else:
            raise PublicationError("PRIVATE_STAGE_INVALID")
    return tuple(sorted(directories)), tuple(sorted(files))


def _validate_public_state(
    state: Mapping[str, Any],
    *,
    entry: Mapping[str, Any],
    nct_id: str,
    source_timestamp_raw: str,
    published_refs: frozenset[str],
    source_snapshot: Mapping[str, Any] | None = None,
) -> None:
    if set(state) != _PUBLIC_STATE_KEYS:
        raise PublicationError("COLLECTOR_PROJECTION_UNSAFE")
    canonical_hash = state.get("canonical_content_sha256")
    if not _valid_digest(canonical_hash):
        raise PublicationError("COLLECTOR_PROJECTION_INVALID")
    expected_ref = f"src:ctgov:{nct_id}:sha256:{canonical_hash}"
    snapshot_id = state.get("source_snapshot_id")
    if (
        state.get("contract_id") != "biocatalyst_trial_source_state.v1"
        or state.get("schema_version") != "1.0.0"
        or state.get("nct_id") != nct_id
        or state.get("source_record_ref") != expected_ref
        or state.get("source_record_ref") not in published_refs
        or state.get("source_snapshot_id") != entry["source_snapshot_id"]
        or state.get("source_record_ref") != entry["source_record_ref"]
        or state.get("source_dataset_timestamp_raw") != source_timestamp_raw
        or state.get("source_uri") != f"https://clinicaltrials.gov/study/{nct_id}"
        or state.get("coverage_class") != "current_only"
        or state.get("license_class") != "us_government_source_facts"
        or state.get("source_attribution") != "ClinicalTrials.gov"
        or state.get("modification_disclosure")
        != "BioCatalyst parsed and normalized this source-state reference."
        or not isinstance(snapshot_id, str)
        or not snapshot_id.startswith(f"ctgov_snapshot_{nct_id}_")
        or not snapshot_id.endswith(f"_{canonical_hash}")
        or len(snapshot_id) > 512
    ):
        raise PublicationError("COLLECTOR_PROJECTION_INVALID")
    _validate_optional_source_date(state.get("source_last_update_posted_at"))
    _validate_optional_source_date(state.get("source_published_at"))
    _validate_utc_datetime(state.get("retrieved_at"))
    if source_snapshot is not None:
        for state_field, snapshot_field in (
            ("nct_id", "nct_id"),
            ("source_snapshot_id", "source_snapshot_id"),
            ("source_record_ref", "source_record_ref"),
            ("canonical_content_sha256", "canonical_content_sha256"),
            ("source_uri", "source_uri"),
            ("source_dataset_timestamp_raw", "source_dataset_timestamp_raw"),
            ("source_last_update_posted_at", "source_last_update_posted_at"),
            ("source_published_at", "source_published_at"),
            ("retrieved_at", "retrieved_at"),
            ("coverage_class", "coverage_class"),
            ("license_class", "license_class"),
        ):
            if state.get(state_field) != source_snapshot.get(snapshot_field):
                raise PublicationError("PUBLIC_SNAPSHOT_BINDING_MISMATCH")


def _validate_trial_snapshot_binding(
    snapshot: Mapping[str, Any],
    *,
    source_state: Mapping[str, Any],
    nct_id: str,
) -> dict[str, Any]:
    """Validate the normalized product DTO and bind it to the proven source state."""

    try:
        normalized = validate_trial_snapshot(snapshot)
    except Exception as exc:  # the product parser exposes no storage details
        raise PublicationError("TRIAL_PROJECTION_INVALID") from exc
    attribution = normalized.get("source_attribution")
    if not isinstance(attribution, Mapping):
        raise PublicationError("TRIAL_PROJECTION_INVALID")
    if (
        normalized.get("nct_id") != nct_id
        or normalized.get("source_version_ordinal") != 1
        or normalized.get("source_snapshot_ref") != source_state.get("source_snapshot_id")
        or normalized.get("source_record_ref") != source_state.get("source_record_ref")
        or normalized.get("canonical_content_sha256")
        != source_state.get("canonical_content_sha256")
        or normalized.get("coverage_class") != source_state.get("coverage_class")
        or normalized.get("source_published_at") != source_state.get("source_published_at")
        or normalized.get("retrieved_at") != source_state.get("retrieved_at")
        or normalized.get("first_seen_at") != source_state.get("retrieved_at")
        or normalized.get("knowledge_cutoff") != source_state.get("retrieved_at")
        or normalized.get("transaction_from") is None
        or attribution.get("source_uri") != source_state.get("source_uri")
        or attribution.get("source_processed_at_raw")
        != source_state.get("source_dataset_timestamp_raw")
        or attribution.get("source_last_update_posted_at")
        != source_state.get("source_last_update_posted_at")
    ):
        raise PublicationError("TRIAL_PROJECTION_BINDING_MISMATCH")
    return normalized


def _validate_trial_history_model_binding(
    model: Mapping[str, Any],
    *,
    nct_id: str,
) -> dict[str, Any]:
    """Validate one public-safe B2 history artifact before it can be served.

    History collection and source replay happen in the B2 history lane.  This
    request-time reader has a deliberately narrower responsibility: it checks
    contract/self-hash integrity and binds the artifact to the current NCT.
    Evidence authenticity is established at promotion by
    ``_validate_history_publication_evidence`` under the single-writer public
    root boundary. Hashes do not authenticate against that authorized writer
    (or host root) maliciously rewriting an entire internally consistent tree.
    """

    try:
        normalized = json.loads(canonical_json_bytes(model))
        if not isinstance(normalized, dict):
            raise ValueError("history model must be a JSON object")
        validate_contract("trial_history_read_model.v1", normalized)
    except Exception as exc:
        raise PublicationError("TRIAL_HISTORY_PROJECTION_INVALID") from exc
    if normalized.get("nct_id") != nct_id:
        raise PublicationError("TRIAL_HISTORY_PROJECTION_BINDING_MISMATCH")
    if not _valid_digest(normalized.get("model_payload_sha256")):
        raise PublicationError("TRIAL_HISTORY_PROJECTION_INVALID")
    if (
        canonical_json_sha256(_without(normalized, "model_payload_sha256"))
        != normalized["model_payload_sha256"]
    ):
        raise PublicationError("TRIAL_HISTORY_PROJECTION_HASH_MISMATCH")
    return normalized


def _validate_history_publication_evidence(
    model: Mapping[str, Any],
    *,
    nct_id: str,
    evidence: HistoryPublicationEvidence,
    prior_model_bytes: bytes | None,
) -> None:
    """Require independent B2 replay evidence before public promotion.

    The public schema and its self-hash prove only that a model is internally
    coherent.  They do not prove the model was derived from a particular
    historical registry chain.  Fresh available models are therefore replayed
    against the exact snapshots/facts preserved in the private B2 lane.  A
    carried-forward available model is the sole no-new-evidence exception and
    is accepted only as an exact public-artifact byte copy of the prior pointer.
    """

    if not isinstance(evidence, HistoryPublicationEvidence):
        raise PublicationError("TRIAL_HISTORY_EVIDENCE_INVALID")
    snapshots = evidence.snapshots
    facts = evidence.facts
    if (
        not isinstance(snapshots, tuple)
        or not isinstance(facts, tuple)
        or any(not isinstance(snapshot, Mapping) for snapshot in snapshots)
        or any(not isinstance(fact, Mapping) for fact in facts)
    ):
        raise PublicationError("TRIAL_HISTORY_EVIDENCE_INVALID")
    if any(snapshot.get("nct_id") != nct_id for snapshot in snapshots) or any(
        fact.get("nct_id") != nct_id for fact in facts
    ):
        raise PublicationError("TRIAL_HISTORY_EVIDENCE_BINDING_MISMATCH")

    available = model.get("available")
    if available is False:
        if evidence.carried_forward or snapshots or facts:
            raise PublicationError("TRIAL_HISTORY_EVIDENCE_BINDING_MISMATCH")
        try:
            validate_trial_history_read_model(model, (), ())
        except Exception as exc:
            raise PublicationError("TRIAL_HISTORY_EVIDENCE_INVALID") from exc
        return
    if available is not True:
        raise PublicationError("TRIAL_HISTORY_EVIDENCE_INVALID")

    if evidence.carried_forward:
        if snapshots or facts or prior_model_bytes is None:
            raise PublicationError("TRIAL_HISTORY_EVIDENCE_BINDING_MISMATCH")
        if _json_bytes(model) != prior_model_bytes:
            raise PublicationError("TRIAL_HISTORY_CARRY_FORWARD_MISMATCH")
        return
    if not snapshots:
        raise PublicationError("TRIAL_HISTORY_EVIDENCE_BINDING_MISMATCH")
    try:
        validate_trial_history_read_model(model, snapshots, facts)
    except Exception as exc:
        raise PublicationError("TRIAL_HISTORY_EVIDENCE_INVALID") from exc


def _validate_projection_payload(
    source_generation: Path,
    *,
    run_id: str,
    query_sha256: str,
    source_timestamp_raw: str,
    configured_nct_ids: Sequence[str],
    published_source_record_refs: Sequence[str],
    expected_published_count: int | None,
    manifest_filename: str = "publication_manifest.json",
    trial_directory: str = "",
    allowed_extra_files: Sequence[str] = (),
    allowed_extra_directories: Sequence[str] = (),
    validated_snapshots_by_nct: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], tuple[tuple[str, dict[str, Any]], ...]]:
    """Validate every file, DTO field, and cross-reference in a stage generation."""

    if not _RUN_ID_RE.fullmatch(run_id) or not _valid_digest(query_sha256):
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    source_timestamp_raw = _validate_source_timestamp(source_timestamp_raw)
    if not isinstance(configured_nct_ids, Sequence) or isinstance(configured_nct_ids, (str, bytes)):
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    if not isinstance(published_source_record_refs, Sequence) or isinstance(published_source_record_refs, (str, bytes)):
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    configured = tuple(configured_nct_ids)
    if (
        not configured
        or tuple(sorted(configured)) != configured
        or len(set(configured)) != len(configured)
        or any(not isinstance(value, str) or not _NCT_ID_RE.fullmatch(value) for value in configured)
    ):
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    published_refs = tuple(published_source_record_refs)
    if len(set(published_refs)) != len(published_refs) or any(
        not isinstance(value, str) or not re.fullmatch(r"src:ctgov:NCT[0-9]{8}:sha256:[0-9a-f]{64}", value)
        for value in published_refs
    ):
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    published_ref_set = frozenset(published_refs)
    if validated_snapshots_by_nct is not None:
        if (
            set(validated_snapshots_by_nct) != set(configured)
            or any(not isinstance(snapshot, Mapping) for snapshot in validated_snapshots_by_nct.values())
        ):
            raise PublicationError("PUBLIC_SNAPSHOT_BINDING_MISMATCH")

    source_generation = Path(source_generation)
    if not source_generation.is_dir() or source_generation.is_symlink():
        raise PublicationError("COLLECTOR_GENERATION_MISSING")
    entries = list(source_generation.iterdir())
    allowed_directories = ({trial_directory} if trial_directory else set()) | set(
        allowed_extra_directories
    )
    if any(
        item.is_symlink()
        or (item.is_dir() and item.name not in allowed_directories)
        or (not item.is_dir() and not item.is_file())
        for item in entries
    ):
        raise PublicationError("COLLECTOR_GENERATION_UNSAFE")

    if manifest_filename not in {"publication_manifest.json", "source_manifest.json"}:
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    if trial_directory not in {"", "trials"}:
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    if trial_directory:
        trial_root = source_generation / trial_directory
        if not trial_root.is_dir() or trial_root.is_symlink() or any(
            item.is_symlink() or item.is_dir() or not item.is_file()
            for item in trial_root.rglob("*")
        ):
            raise PublicationError("COLLECTOR_GENERATION_UNSAFE")
    source_manifest_path = source_generation / manifest_filename
    source_manifest = _load_json_object(source_manifest_path, code="COLLECTOR_MANIFEST_INVALID")
    if set(source_manifest) != _COLLECTOR_MANIFEST_KEYS:
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    if (
        source_manifest.get("manifest_version") != "biocatalyst_publication.v1"
        or source_manifest.get("hash_scope") != "canonical_manifest_excluding_manifest_sha256"
        or source_manifest.get("run_id") != run_id
        or source_manifest.get("query_sha256") != query_sha256
        or source_manifest.get("source_dataset_timestamp_raw") != source_timestamp_raw
    ):
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    if not _valid_digest(source_manifest.get("manifest_sha256")):
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    if canonical_json_sha256(_without(source_manifest, "manifest_sha256")) != source_manifest["manifest_sha256"]:
        raise PublicationError("COLLECTOR_MANIFEST_HASH_MISMATCH")

    raw_entries = source_manifest.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    normalized: list[tuple[str, dict[str, Any]]] = []
    seen_ncts: set[str] = set()
    seen_refs: set[str] = set()
    for entry in raw_entries:
        if not isinstance(entry, dict) or set(entry) != _COLLECTOR_ENTRY_KEYS:
            raise PublicationError("COLLECTOR_MANIFEST_INVALID")
        nct_id = entry.get("nct_id")
        if not isinstance(nct_id, str) or not _NCT_ID_RE.fullmatch(nct_id) or nct_id in seen_ncts:
            raise PublicationError("COLLECTOR_MANIFEST_INVALID")
        if not all(_bounded_string(entry.get(key), maximum=512) for key in ("source_snapshot_id", "source_record_ref")):
            raise PublicationError("COLLECTOR_MANIFEST_INVALID")
        if not _valid_digest(entry.get("public_state_sha256")):
            raise PublicationError("COLLECTOR_MANIFEST_INVALID")
        state = _load_json_object(
            source_generation / trial_directory / f"{nct_id}.json",
            code="COLLECTOR_PROJECTION_INVALID",
        )
        _validate_public_state(
            state,
            entry=entry,
            nct_id=nct_id,
            source_timestamp_raw=source_timestamp_raw,
            published_refs=published_ref_set,
            source_snapshot=(
                validated_snapshots_by_nct.get(nct_id)
                if validated_snapshots_by_nct is not None
                else None
            ),
        )
        if canonical_json_sha256(state) != entry["public_state_sha256"]:
            raise PublicationError("COLLECTOR_PROJECTION_HASH_MISMATCH")
        seen_ncts.add(nct_id)
        seen_refs.add(str(entry["source_record_ref"]))
        normalized.append((nct_id, state))

    if tuple(item[0] for item in normalized) != tuple(sorted(seen_ncts)):
        raise PublicationError("COLLECTOR_MANIFEST_INVALID")
    if seen_ncts != set(configured) or seen_refs != published_ref_set:
        raise PublicationError("COLLECTOR_BINDING_MISMATCH")
    if expected_published_count is not None and expected_published_count != len(normalized):
        raise PublicationError("COLLECTOR_COUNTS_MISMATCH")
    expected_files = {
        manifest_filename,
        *(f"{trial_directory + '/' if trial_directory else ''}{nct_id}.json" for nct_id in seen_ncts),
        *allowed_extra_files,
    }
    actual_files = {
        path.relative_to(source_generation).as_posix()
        for path in source_generation.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise PublicationError("COLLECTOR_GENERATION_UNSAFE")
    return source_manifest, tuple(normalized)


def _validate_collector_projection(
    source_generation: Path,
    *,
    run: Mapping[str, Any],
    validated_snapshots_by_nct: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], tuple[tuple[str, dict[str, Any]], ...]]:
    query_manifest = run.get("query_manifest")
    counts = run.get("counts")
    if not isinstance(query_manifest, dict) or not isinstance(counts, dict):
        raise PublicationError("RUN_CONTRACT_INVALID")
    return _validate_projection_payload(
        source_generation,
        run_id=run["run_id"],
        query_sha256=query_manifest.get("query_sha256"),
        source_timestamp_raw=run["source_dataset_timestamp_before_raw"],
        configured_nct_ids=query_manifest.get("configured_nct_ids", ()),
        published_source_record_refs=run.get("published_source_record_refs", ()),
        expected_published_count=counts.get("studies_published"),
        validated_snapshots_by_nct=validated_snapshots_by_nct,
    )


def _tree_equal(left: Path, right: Path) -> bool:
    try:
        left_directories, left_files = _regular_tree_inventory(left)
        right_directories, right_files = _regular_tree_inventory(right)
    except PublicationError:
        return False
    if left_directories != right_directories or left_files != right_files:
        return False
    try:
        return all((left / rel).read_bytes() == (right / rel).read_bytes() for rel in left_files)
    except OSError:
        return False


def archive_private_stage(
    private_stage: Path,
    *,
    state_root: Path,
    run_id: str,
) -> Path:
    """Move one verified private staging tree into a stable local evidence archive."""

    raw_state_root = _require_real_directory(
        Path(state_root), code="PRIVATE_STAGE_INVALID"
    )
    staging_root = _require_real_directory(
        raw_state_root / "staging", code="PRIVATE_STAGE_INVALID"
    )
    private_stage = _require_within(
        private_stage, staging_root, code="PRIVATE_STAGE_INVALID"
    )
    _regular_tree_inventory(private_stage)
    committed_root = _require_real_directory(
        raw_state_root / "committed",
        code="PRIVATE_STAGE_INVALID",
        create=True,
    )
    if not _RUN_ID_RE.fullmatch(run_id):
        raise PublicationError("RUN_ID_INVALID")
    destination_root = committed_root / run_id
    destination = destination_root / "private"
    if destination_root.is_symlink():
        raise PublicationError("PRIVATE_STAGE_INVALID")
    try:
        destination_root.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        raise PublicationError("PRIVATE_STAGE_INVALID") from exc
    _require_real_directory(destination_root, code="PRIVATE_STAGE_INVALID")
    if destination.is_symlink():
        raise PublicationError("PRIVATE_ARCHIVE_COLLISION")
    if destination.exists():
        if not _tree_equal(private_stage, destination):
            raise PublicationError("PRIVATE_ARCHIVE_COLLISION")
        shutil.rmtree(private_stage)
    else:
        os.replace(private_stage, destination)
        _fsync_directory(destination_root)
    return destination_root


def build_private_mirror_manifest(
    archive_root: Path,
    *,
    run_id: str,
    receipts: Sequence[MirrorReceipt],
    verified_at: str,
) -> PrivateMirrorManifest:
    """Persist a deterministic non-secret receipt for one immutable run.

    Retrying a crashed worker can legitimately revisit the same run ID.  Its
    mirror receipt therefore uses the run's immutable completion timestamp,
    never a fresh wall-clock value that would collide with an already-retained
    R2 object.
    """

    if not _RUN_ID_RE.fullmatch(run_id):
        raise PublicationError("RUN_ID_INVALID")
    _validate_utc_datetime(verified_at)
    rendered = [
        {
            "object_key": receipt.object_key,
            "sha256": receipt.sha256,
            "byte_count": receipt.byte_count,
        }
        for receipt in sorted(receipts, key=lambda item: item.object_key)
    ]
    payload: dict[str, Any] = {
        "contract_id": "biocatalyst_private_mirror_receipt.v1",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "verified_at": verified_at,
        "objects": rendered,
    }
    payload["manifest_sha256"] = canonical_json_sha256(payload)
    path = Path(archive_root) / "mirror_receipt.json"
    bytes_payload = _json_bytes(payload)
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise PublicationError("PRIVATE_ARTIFACT_UNREADABLE") from exc
        if existing != bytes_payload:
            raise PublicationError("PRIVATE_ARCHIVE_COLLISION")
    else:
        atomic_write(path, bytes_payload)
    return PrivateMirrorManifest(
        path=path,
        payload=bytes_payload,
        object_key=f"biocatalyst/mirror_receipts/{run_id}.json",
    )


def archive_failed_attempt(attempt_root: Path, *, state_root: Path, attempt_id: str) -> Path | None:
    """Keep failed raw evidence locally without touching the last-good public state."""

    try:
        raw_state_root = _require_real_directory(
            Path(state_root), code="PRIVATE_STAGE_INVALID"
        )
        staging_root = _require_real_directory(
            raw_state_root / "staging", code="PRIVATE_STAGE_INVALID"
        )
        dead_letter_root = _require_real_directory(
            raw_state_root / "dead-letter",
            code="PRIVATE_STAGE_INVALID",
            create=True,
        )
        attempt_root = _require_within(
            attempt_root, staging_root, code="PRIVATE_STAGE_INVALID"
        )
        _regular_tree_inventory(attempt_root)
    except PublicationError:
        return None
    if not attempt_root.exists():
        return None
    if not re.fullmatch(r"attempt_[A-Za-z0-9_]+", attempt_id):
        return None
    destination = dead_letter_root / attempt_id
    if destination.is_symlink():
        return None
    if destination.exists():
        try:
            _regular_tree_inventory(destination)
        except PublicationError:
            return None
        return destination
    try:
        os.replace(attempt_root, destination)
        _fsync_directory(destination.parent)
    except OSError:
        return None
    return destination


def write_private_incident(
    incident_root: Path,
    *,
    run_id: str,
    attempt_id: str,
    failure_code: str,
    r2_mirror_state: str,
    dead_letter_ref: str | None,
    prior: CommittedGeneration | None,
    observed: CommittedGeneration | None,
    now: datetime,
) -> Path:
    """Write one bounded immutable worker-incident record beside retained facts.

    The record intentionally contains identifiers, hashes, and coarse state
    only.  It never serializes a filesystem path, object-store endpoint, or
    credential, so failure health can remain an equally bounded public DTO.
    """

    if not _RUN_ID_RE.fullmatch(run_id) or not re.fullmatch(r"attempt_[A-Za-z0-9_]+", attempt_id):
        raise PublicationError("PRIVATE_STAGE_INVALID")
    if not re.fullmatch(r"[A-Z0-9_]{1,96}", failure_code):
        raise PublicationError("PRIVATE_STAGE_INVALID")
    if r2_mirror_state not in {"not_started", "objects_verified", "mirror_receipt_verified"}:
        raise PublicationError("PRIVATE_STAGE_INVALID")
    if dead_letter_ref is not None and not re.fullmatch(r"dead-letter/attempt_[A-Za-z0-9_]+", dead_letter_ref):
        raise PublicationError("PRIVATE_STAGE_INVALID")
    root = Path(incident_root)
    if root.is_symlink() or not root.is_dir():
        raise PublicationError("PRIVATE_STAGE_INVALID")
    payload: dict[str, Any] = {
        "contract_id": "biocatalyst_worker_incident.v1",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "attempt_id": attempt_id,
        "failure_code": failure_code,
        "recorded_at": _iso(now),
        "private_archive_state": "retained",
        "r2_mirror_state": r2_mirror_state,
        "dead_letter_ref": dead_letter_ref,
        "prior_generation_id": prior.generation_id if prior else None,
        "prior_manifest_sha256": prior.manifest_sha256 if prior else None,
        "observed_generation_id": observed.generation_id if observed else None,
        "observed_manifest_sha256": observed.manifest_sha256 if observed else None,
    }
    path = root / "incidents" / f"{attempt_id}.json"
    bytes_payload = _json_bytes(payload)
    if path.exists():
        if path.is_symlink():
            raise PublicationError("PRIVATE_STAGE_INVALID")
        try:
            if path.read_bytes() != bytes_payload:
                raise PublicationError("PRIVATE_ARCHIVE_COLLISION")
        except OSError as exc:
            raise PublicationError("PRIVATE_ARTIFACT_UNREADABLE") from exc
        return path
    atomic_write(path, bytes_payload)
    return path


class PublicGenerationPublisher:
    """Validate and atomically promote public generations and their single pointer."""

    def __init__(
        self,
        public_root: Path,
        *,
        now_fn=_utc_now,
        pointer_after_replace_hook: Callable[[Path], None] | None = None,
    ) -> None:
        raw_public_root = Path(public_root)
        if raw_public_root.is_symlink():
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        self.public_root = raw_public_root.resolve()
        self.now_fn = now_fn
        self._pointer_after_replace_hook = pointer_after_replace_hook

    @property
    def pointer_path(self) -> Path:
        return self.public_root / "current.json"

    @property
    def health_path(self) -> Path:
        return self.public_root / "health.json"

    def _generations_root(self, *, create: bool = False) -> Path:
        return _require_real_directory(
            self.public_root / "generations",
            code="PUBLIC_GENERATION_INVALID",
            create=create,
        )

    def _generation_dir(self, generation_id: str) -> Path:
        if not _RUN_ID_RE.fullmatch(generation_id):
            raise PublicationError("PUBLIC_POINTER_INVALID")
        return self._generations_root() / generation_id

    def _load_generation_manifest(self, generation_id: str) -> dict[str, Any]:
        generation = self._generation_dir(generation_id)
        if not generation.is_dir() or generation.is_symlink():
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        tree = list(generation.rglob("*"))
        if any(item.is_symlink() or (not item.is_dir() and not item.is_file()) for item in tree):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        manifest = _load_json_object(generation / "manifest.json", code="PUBLIC_GENERATION_INVALID")
        if set(manifest) != _PUBLIC_GENERATION_MANIFEST_KEYS:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if manifest.get("generation_id") != generation_id or manifest.get("run_id") != generation_id:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        generation_schema = manifest.get("schema_version")
        if (
            manifest.get("contract_id") != "biocatalyst_public_generation.v1"
            or generation_schema not in _PUBLIC_GENERATION_SCHEMAS
        ):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        directories = {
            item.relative_to(generation).as_posix()
            for item in tree
            if item.is_dir()
        }
        expected_directories = {"trials"}
        if generation_schema in {"1.1.0", "1.2.0", "1.3.0"}:
            expected_directories.add(_TRIAL_SNAPSHOT_DIRECTORY)
        if generation_schema in {"1.2.0", "1.3.0"}:
            expected_directories.add(_TRIAL_HISTORY_DIRECTORY)
        if generation_schema == "1.3.0":
            expected_directories.add(_TRIAL_PROSPECTIVE_DIRECTORY)
        if directories != expected_directories:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if (
            manifest.get("coverage_class") != "current_only"
            or manifest.get("hash_scope") != "canonical_manifest_excluding_manifest_sha256"
        ):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if not _valid_digest(manifest.get("manifest_sha256")) or not _valid_digest(manifest.get("source_manifest_sha256")):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if canonical_json_sha256(_without(manifest, "manifest_sha256")) != manifest["manifest_sha256"]:
            raise PublicationError("PUBLIC_GENERATION_HASH_MISMATCH")
        _validate_source_timestamp(manifest.get("source_dataset_timestamp_raw"))
        if not isinstance(manifest.get("watermark_after"), str) or not manifest["watermark_after"]:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if not isinstance(manifest.get("published_at"), str) or not manifest["published_at"]:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        _validate_utc_datetime(manifest["watermark_after"])
        _validate_utc_datetime(manifest["published_at"])
        for key in ("configured_nct_count", "observed_nct_count"):
            if (
                not isinstance(manifest.get(key), int)
                or isinstance(manifest[key], bool)
                or manifest[key] < 0
            ):
                raise PublicationError("PUBLIC_GENERATION_INVALID")
        _validate_utc_datetime(manifest.get("last_attempt_at"))
        _validate_utc_datetime(manifest.get("last_success_at"))
        if (
            manifest["last_attempt_at"] != manifest["published_at"]
            or manifest["last_success_at"] != manifest["published_at"]
        ):
            raise PublicationError("GENERATION_HEALTH_BINDING_MISMATCH")
        query_sha256 = manifest.get("query_sha256")
        configured_nct_ids = manifest.get("configured_nct_ids")
        published_refs = manifest.get("published_source_record_refs")
        if not _valid_digest(query_sha256):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        seen: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict) or set(artifact) != _ARTIFACT_KEYS:
                raise PublicationError("PUBLIC_GENERATION_INVALID")
            name = artifact.get("name")
            if not isinstance(name, str) or name in seen or not _valid_digest(artifact.get("sha256")):
                raise PublicationError("PUBLIC_GENERATION_INVALID")
            if not isinstance(artifact.get("byte_count"), int) or artifact["byte_count"] < 1:
                raise PublicationError("PUBLIC_GENERATION_INVALID")
            source_state_artifact = bool(re.fullmatch(r"trials/NCT[0-9]{8}\.json", str(name)))
            trial_snapshot_artifact = generation_schema in {"1.1.0", "1.2.0", "1.3.0"} and bool(
                re.fullmatch(r"trial_snapshots/NCT[0-9]{8}\.json", str(name))
            )
            trial_history_artifact = generation_schema in {"1.2.0", "1.3.0"} and bool(
                re.fullmatch(r"history/NCT[0-9]{8}\.json", str(name))
            )
            trial_prospective_artifact = generation_schema == "1.3.0" and bool(
                re.fullmatch(r"prospective/NCT[0-9]{8}\.json", str(name))
            )
            if (
                name not in {"source_manifest.json", "health.json"}
                and not source_state_artifact
                and not trial_snapshot_artifact
                and not trial_history_artifact
                and not trial_prospective_artifact
            ):
                raise PublicationError("PUBLIC_GENERATION_INVALID")
            path = _safe_child(generation, name)
            payload = path.read_bytes()
            if len(payload) != artifact["byte_count"] or sha256(payload).hexdigest() != artifact["sha256"]:
                raise PublicationError("PUBLIC_GENERATION_ARTIFACT_MISMATCH")
            seen.add(name)
        required = {"source_manifest.json", "health.json"}
        if not required.issubset(seen) or not any(name.startswith("trials/NCT") for name in seen):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if generation_schema in {"1.1.0", "1.2.0", "1.3.0"} and not any(
            name.startswith(f"{_TRIAL_SNAPSHOT_DIRECTORY}/NCT") for name in seen
        ):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if generation_schema in {"1.2.0", "1.3.0"} and not any(
            name.startswith(f"{_TRIAL_HISTORY_DIRECTORY}/NCT") for name in seen
        ):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if generation_schema == "1.3.0" and not any(
            name.startswith(f"{_TRIAL_PROSPECTIVE_DIRECTORY}/NCT") for name in seen
        ):
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        all_files = {
            item.relative_to(generation).as_posix()
            for item in tree
            if item.is_file()
        }
        if all_files != {"manifest.json", *seen}:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        trial_snapshot_names = tuple(
            sorted(
                name
                for name in seen
                if name.startswith(f"{_TRIAL_SNAPSHOT_DIRECTORY}/")
            )
        )
        trial_history_names = tuple(
            sorted(
                name
                for name in seen
                if name.startswith(f"{_TRIAL_HISTORY_DIRECTORY}/")
            )
        )
        trial_prospective_names = tuple(
            sorted(
                name
                for name in seen
                if name.startswith(f"{_TRIAL_PROSPECTIVE_DIRECTORY}/")
            )
        )
        source_manifest, states = _validate_projection_payload(
            generation,
            run_id=generation_id,
            query_sha256=query_sha256,
            source_timestamp_raw=manifest["source_dataset_timestamp_raw"],
            configured_nct_ids=configured_nct_ids,
            published_source_record_refs=published_refs,
            expected_published_count=len(
                [name for name in seen if name.startswith("trials/NCT")]
            ),
            manifest_filename="source_manifest.json",
            trial_directory="trials",
            allowed_extra_files=(
                "manifest.json",
                "health.json",
                *trial_snapshot_names,
                *trial_history_names,
                *trial_prospective_names,
            ),
            allowed_extra_directories=(
                (
                    _TRIAL_SNAPSHOT_DIRECTORY,
                    _TRIAL_HISTORY_DIRECTORY,
                    _TRIAL_PROSPECTIVE_DIRECTORY,
                )
                if generation_schema == "1.3.0"
                else ((_TRIAL_SNAPSHOT_DIRECTORY, _TRIAL_HISTORY_DIRECTORY)
                if generation_schema == "1.2.0"
                else ((_TRIAL_SNAPSHOT_DIRECTORY,) if generation_schema == "1.1.0" else ())
                )
            ),
        )
        if source_manifest["manifest_sha256"] != manifest["source_manifest_sha256"]:
            raise PublicationError("PUBLIC_GENERATION_ARTIFACT_MISMATCH")
        if {f"trials/{nct_id}.json" for nct_id, _ in states} != {
            name for name in seen if name.startswith("trials/")
        }:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if generation_schema == "1.0.0" and trial_snapshot_names:
            raise PublicationError("PUBLIC_GENERATION_INVALID")
        if generation_schema in {"1.1.0", "1.2.0", "1.3.0"}:
            states_by_nct = dict(states)
            expected_trial_names = {
                f"{_TRIAL_SNAPSHOT_DIRECTORY}/{nct_id}.json"
                for nct_id in states_by_nct
            }
            if set(trial_snapshot_names) != expected_trial_names:
                raise PublicationError("TRIAL_PROJECTION_INVALID")
            for nct_id in sorted(states_by_nct):
                product = _load_json_object(
                    generation / _TRIAL_SNAPSHOT_DIRECTORY / f"{nct_id}.json",
                    code="TRIAL_PROJECTION_INVALID",
                )
                _validate_trial_snapshot_binding(
                    product,
                    source_state=states_by_nct[nct_id],
                    nct_id=nct_id,
                )
            if generation_schema in {"1.2.0", "1.3.0"}:
                expected_history_names = {
                    f"{_TRIAL_HISTORY_DIRECTORY}/{nct_id}.json"
                    for nct_id in states_by_nct
                }
                if set(trial_history_names) != expected_history_names:
                    raise PublicationError("TRIAL_HISTORY_PROJECTION_INVALID")
                for nct_id in sorted(states_by_nct):
                    history_model = _load_json_object(
                        generation / _TRIAL_HISTORY_DIRECTORY / f"{nct_id}.json",
                        code="TRIAL_HISTORY_PROJECTION_INVALID",
                    )
                    _validate_trial_history_model_binding(history_model, nct_id=nct_id)
            if generation_schema == "1.3.0":
                expected_prospective_names = {
                    f"{_TRIAL_PROSPECTIVE_DIRECTORY}/{nct_id}.json"
                    for nct_id in states_by_nct
                }
                if set(trial_prospective_names) != expected_prospective_names:
                    raise PublicationError("TRIAL_PROSPECTIVE_PROJECTION_INVALID")
                for nct_id in sorted(states_by_nct):
                    prospective_model = _load_json_object(
                        generation / _TRIAL_PROSPECTIVE_DIRECTORY / f"{nct_id}.json",
                        code="TRIAL_PROSPECTIVE_PROJECTION_INVALID",
                    )
                    try:
                        validate_prospective_public_model(prospective_model)
                    except ProspectiveError as exc:
                        raise PublicationError("TRIAL_PROSPECTIVE_PROJECTION_INVALID") from exc
                    if prospective_model.get("nct_id") != nct_id:
                        raise PublicationError("TRIAL_PROSPECTIVE_PROJECTION_INVALID")
        if (
            manifest["configured_nct_count"] != len(manifest["configured_nct_ids"])
            or manifest["observed_nct_count"] != len(states)
        ):
            raise PublicationError("GENERATION_HEALTH_BINDING_MISMATCH")
        health = _load_json_object(generation / "health.json", code="HEALTH_PAYLOAD_INVALID")
        self._validate_generation_health_binding(
            health,
            generation_id=generation_id,
            configured_nct_count=len(manifest["configured_nct_ids"]),
            observed_nct_count=len(states),
            source_dataset_timestamp_raw=manifest["source_dataset_timestamp_raw"],
            last_attempt_at=manifest["last_attempt_at"],
            last_success_at=manifest["last_success_at"],
        )
        return manifest

    def read_committed(self) -> CommittedGeneration | None:
        """Read a fully validated committed state, never a loose watermark file."""

        if self.pointer_path.is_symlink():
            raise PublicationError("PUBLIC_POINTER_INVALID")
        if not self.pointer_path.exists():
            return None
        try:
            pointer_metadata = self.pointer_path.lstat()
        except OSError as exc:
            raise PublicationError("PUBLIC_POINTER_INVALID") from exc
        if not stat.S_ISREG(pointer_metadata.st_mode):
            raise PublicationError("PUBLIC_POINTER_INVALID")
        pointer = _load_json_object(self.pointer_path, code="PUBLIC_POINTER_INVALID")
        if set(pointer) != _POINTER_KEYS:
            raise PublicationError("PUBLIC_POINTER_INVALID")
        if pointer.get("contract_id") != "biocatalyst_current_pointer.v1" or pointer.get("schema_version") != "1.0.0":
            raise PublicationError("PUBLIC_POINTER_INVALID")
        generation_id = pointer.get("generation_id")
        if not isinstance(generation_id, str) or not _RUN_ID_RE.fullmatch(generation_id):
            raise PublicationError("PUBLIC_POINTER_INVALID")
        if not _valid_digest(pointer.get("manifest_sha256")):
            raise PublicationError("PUBLIC_POINTER_INVALID")
        _validate_utc_datetime(pointer.get("watermark_after"))
        _validate_utc_datetime(pointer.get("published_at"))
        manifest = self._load_generation_manifest(generation_id)
        if (
            pointer.get("manifest_sha256") != manifest["manifest_sha256"]
            or pointer.get("watermark_after") != manifest["watermark_after"]
            or pointer.get("published_at") != manifest["published_at"]
        ):
            raise PublicationError("PUBLIC_POINTER_INVALID")
        return CommittedGeneration(
            generation_id=generation_id,
            manifest_sha256=manifest["manifest_sha256"],
            watermark_after=manifest["watermark_after"],
            published_at=manifest["published_at"],
            source_dataset_timestamp_raw=manifest["source_dataset_timestamp_raw"],
            configured_nct_count=manifest["configured_nct_count"],
            observed_nct_count=manifest["observed_nct_count"],
            last_attempt_at=manifest["last_attempt_at"],
            last_success_at=manifest["last_success_at"],
            schema_version=manifest["schema_version"],
        )

    def read_trial_projection(self) -> CommittedTrialProjection | None:
        """Return only current pointer-bound normalized trial facts.

        Legacy B1 generations remain valid evidence generations, but they do not
        silently masquerade as a product projection.  Callers receive a bounded
        unavailable code until the worker publishes the first v1.1 generation.
        """

        committed = self.read_committed()
        if committed is None:
            return None
        manifest = self._load_generation_manifest(committed.generation_id)
        generation_schema = manifest.get("schema_version")
        if generation_schema not in {"1.1.0", "1.2.0", "1.3.0"}:
            raise PublicationError("TRIAL_PROJECTION_UNAVAILABLE")
        generation = self._generation_dir(committed.generation_id)
        trials: list[dict[str, Any]] = []
        history_models_by_nct: dict[str, dict[str, Any]] = {}
        prospective_models_by_nct: dict[str, dict[str, Any]] = {}
        for nct_id in manifest["configured_nct_ids"]:
            source_state = _load_json_object(
                generation / "trials" / f"{nct_id}.json",
                code="COLLECTOR_PROJECTION_INVALID",
            )
            product = _load_json_object(
                generation / _TRIAL_SNAPSHOT_DIRECTORY / f"{nct_id}.json",
                code="TRIAL_PROJECTION_INVALID",
            )
            trials.append(
                _validate_trial_snapshot_binding(
                    product,
                    source_state=source_state,
                    nct_id=nct_id,
                )
            )
            if generation_schema in {"1.2.0", "1.3.0"}:
                history_model = _load_json_object(
                    generation / _TRIAL_HISTORY_DIRECTORY / f"{nct_id}.json",
                    code="TRIAL_HISTORY_PROJECTION_INVALID",
                )
                history_models_by_nct[nct_id] = _validate_trial_history_model_binding(
                    history_model,
                    nct_id=nct_id,
                )
            else:
                # B1b remains readable after B2 ships.  It has no public
                # history artifact, so state that absence explicitly instead
                # of pretending the current registry cut is a history feed.
                history_models_by_nct[nct_id] = {
                    "available": False,
                    "unavailable_reason": "not_collected",
                }
            if generation_schema == "1.3.0":
                prospective_model = _load_json_object(
                    generation / _TRIAL_PROSPECTIVE_DIRECTORY / f"{nct_id}.json",
                    code="TRIAL_PROSPECTIVE_PROJECTION_INVALID",
                )
                try:
                    validate_prospective_public_model(prospective_model)
                except ProspectiveError as exc:
                    raise PublicationError("TRIAL_PROSPECTIVE_PROJECTION_INVALID") from exc
                if prospective_model.get("nct_id") != nct_id:
                    raise PublicationError("TRIAL_PROSPECTIVE_PROJECTION_INVALID")
                prospective_models_by_nct[nct_id] = prospective_model
            else:
                prospective_models_by_nct[nct_id] = {
                    "available": False,
                    "unavailable_reason": "baseline_not_established",
                }
        if len(trials) != committed.observed_nct_count:
            raise PublicationError("TRIAL_PROJECTION_BINDING_MISMATCH")
        if len(history_models_by_nct) != len(trials):
            raise PublicationError("TRIAL_HISTORY_PROJECTION_BINDING_MISMATCH")
        if len(prospective_models_by_nct) != len(trials):
            raise PublicationError("TRIAL_PROSPECTIVE_PROJECTION_BINDING_MISMATCH")
        return CommittedTrialProjection(
            generation=committed,
            trials=tuple(trials),
            history_models_by_nct=history_models_by_nct,
            prospective_models_by_nct=prospective_models_by_nct,
        )

    def _prior_history_model_bytes(self, nct_id: str) -> bytes | None:
        """Return one already validated B2 artifact for exact carry-forward.

        This never reaches into worker state.  A B1.1 generation has no history
        artifact and is deliberately not eligible as a last-good history model.
        """

        committed = self.read_committed()
        if committed is None:
            return None
        manifest = self._load_generation_manifest(committed.generation_id)
        if manifest.get("schema_version") not in {"1.2.0", "1.3.0"}:
            return None
        if nct_id not in manifest.get("configured_nct_ids", ()):
            return None
        path = _safe_child(
            self._generation_dir(committed.generation_id),
            f"{_TRIAL_HISTORY_DIRECTORY}/{nct_id}.json",
        )
        payload = path.read_bytes()
        model = _load_json_object(path, code="TRIAL_HISTORY_PROJECTION_INVALID")
        _validate_trial_history_model_binding(model, nct_id=nct_id)
        # Published B2 artifacts are canonical bytes by construction.  Recheck
        # that invariant before accepting a byte-identical carry-forward.
        if payload != _json_bytes(model):
            raise PublicationError("TRIAL_HISTORY_PROJECTION_INVALID")
        return payload

    def prepare_generation(
        self,
        *,
        collector_generation: Path,
        collector_public_root: Path,
        final_stage: Path,
        run: Mapping[str, Any],
        expected_watermark: str | None,
        health: Mapping[str, Any],
        validated_snapshots_by_nct: Mapping[str, Mapping[str, Any]],
        source_receipts: Sequence[Mapping[str, Any]],
        raw_page_bodies_by_receipt: Mapping[str, bytes],
        history_models_by_nct: Mapping[str, Mapping[str, Any]] | None = None,
        history_evidence_by_nct: Mapping[str, HistoryPublicationEvidence] | None = None,
        prospective_models_by_nct: Mapping[str, Mapping[str, Any]] | None = None,
        prospective_evidence_by_nct: Mapping[str, ProspectivePublicationEvidence] | None = None,
    ) -> PreparedGeneration:
        """Make a complete sanitized generation outside the actual public root."""

        run = _validate_run(run, expected_watermark=expected_watermark)
        collector_generation = _require_within(
            collector_generation,
            collector_public_root,
            code="COLLECTOR_GENERATION_OUTSIDE_STAGE",
        )
        source_manifest, states = _validate_collector_projection(
            collector_generation,
            run=run,
            validated_snapshots_by_nct=validated_snapshots_by_nct,
        )
        states_by_nct = dict(states)
        if history_models_by_nct is None:
            if history_evidence_by_nct is not None:
                raise PublicationError("TRIAL_HISTORY_EVIDENCE_BINDING_MISMATCH")
            normalized_history_models: dict[str, dict[str, Any]] | None = None
        else:
            if set(history_models_by_nct) != set(states_by_nct):
                raise PublicationError("TRIAL_HISTORY_PROJECTION_BINDING_MISMATCH")
            if history_evidence_by_nct is None or set(history_evidence_by_nct) != set(
                states_by_nct
            ):
                raise PublicationError("TRIAL_HISTORY_EVIDENCE_BINDING_MISMATCH")
            evidence_by_nct = history_evidence_by_nct
            normalized_history_models = {
                nct_id: _validate_trial_history_model_binding(
                    history_models_by_nct[nct_id],
                    nct_id=nct_id,
                )
                for nct_id in sorted(states_by_nct)
            }
            for nct_id, model in normalized_history_models.items():
                evidence = evidence_by_nct.get(nct_id)
                if not isinstance(evidence, HistoryPublicationEvidence):
                    raise PublicationError("TRIAL_HISTORY_EVIDENCE_INVALID")
                _validate_history_publication_evidence(
                    model,
                    nct_id=nct_id,
                    evidence=evidence,
                    prior_model_bytes=(
                        self._prior_history_model_bytes(nct_id)
                        if evidence.carried_forward
                        else None
                    ),
                )
        if prospective_models_by_nct is None:
            if prospective_evidence_by_nct is not None:
                raise PublicationError("TRIAL_PROSPECTIVE_EVIDENCE_BINDING_MISMATCH")
            normalized_prospective_models: dict[str, dict[str, Any]] | None = None
        else:
            if normalized_history_models is None:
                raise PublicationError("TRIAL_PROSPECTIVE_PROJECTION_BINDING_MISMATCH")
            if set(prospective_models_by_nct) != set(states_by_nct):
                raise PublicationError("TRIAL_PROSPECTIVE_PROJECTION_BINDING_MISMATCH")
            if prospective_evidence_by_nct is None or set(prospective_evidence_by_nct) != set(
                states_by_nct
            ):
                raise PublicationError("TRIAL_PROSPECTIVE_EVIDENCE_BINDING_MISMATCH")
            normalized_prospective_models = {
                nct_id: dict(prospective_models_by_nct[nct_id])
                for nct_id in sorted(states_by_nct)
            }
            for nct_id, model in normalized_prospective_models.items():
                evidence = prospective_evidence_by_nct.get(nct_id)
                if not isinstance(evidence, ProspectivePublicationEvidence):
                    raise PublicationError("TRIAL_PROSPECTIVE_EVIDENCE_INVALID")
                try:
                    validate_prospective_publication_evidence(
                        model,
                        epoch=evidence.epoch,
                        current=evidence.current,
                        current_observation=evidence.current_observation,
                        exact_diff=evidence.exact_diff,
                        generated_at=evidence.generated_at,
                        prior=evidence.prior,
                        prior_observation=evidence.prior_observation,
                        prior_model=evidence.prior_model,
                    )
                except ProspectiveError as exc:
                    raise PublicationError("TRIAL_PROSPECTIVE_EVIDENCE_INVALID") from exc
        self._validate_generation_health_binding(
            health,
            generation_id=run["run_id"],
            configured_nct_count=len(run["query_manifest"]["configured_nct_ids"]),
            observed_nct_count=len(states),
            source_dataset_timestamp_raw=run["source_dataset_timestamp_before_raw"],
            last_attempt_at=run["finished_at"],
            last_success_at=run["finished_at"],
        )
        final_stage = Path(final_stage)
        if final_stage.exists():
            raise PublicationError("PUBLIC_STAGE_COLLISION")
        final_stage.mkdir(parents=True)
        try:
            atomic_write(final_stage / "source_manifest.json", _json_bytes(source_manifest))
            for nct_id, state in states:
                atomic_write(final_stage / "trials" / f"{nct_id}.json", _json_bytes(state))
            for nct_id, _state in states:
                try:
                    product = build_trial_snapshot(
                        validated_snapshots_by_nct[nct_id],
                        source_version_ordinal=1,
                    )
                except Exception as exc:
                    raise PublicationError("TRIAL_PROJECTION_INVALID") from exc
                _validate_trial_snapshot_binding(
                    product,
                    source_state=states_by_nct[nct_id],
                    nct_id=nct_id,
                )
                try:
                    validate_trial_projection_against_source(
                        product,
                        validated_snapshots_by_nct[nct_id],
                        run=run,
                        receipts=source_receipts,
                        raw_page_bodies_by_receipt=raw_page_bodies_by_receipt,
                    )
                except Exception as exc:
                    raise PublicationError("TRIAL_PROJECTION_INVALID") from exc
                atomic_write(
                    final_stage / _TRIAL_SNAPSHOT_DIRECTORY / f"{nct_id}.json",
                    _json_bytes(product),
                )
            if normalized_history_models is not None:
                for nct_id in sorted(normalized_history_models):
                    atomic_write(
                        final_stage / _TRIAL_HISTORY_DIRECTORY / f"{nct_id}.json",
                        _json_bytes(normalized_history_models[nct_id]),
                    )
            if normalized_prospective_models is not None:
                for nct_id in sorted(normalized_prospective_models):
                    atomic_write(
                        final_stage / _TRIAL_PROSPECTIVE_DIRECTORY / f"{nct_id}.json",
                        _json_bytes(normalized_prospective_models[nct_id]),
                    )
            atomic_write(final_stage / "health.json", _json_bytes(dict(health)))
            artifact_paths = sorted(
                path for path in final_stage.rglob("*") if path.is_file()
            )
            artifacts = [
                {
                    "name": path.relative_to(final_stage).as_posix(),
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                    "byte_count": len(path.read_bytes()),
                }
                for path in artifact_paths
            ]
            payload: dict[str, Any] = {
                "contract_id": "biocatalyst_public_generation.v1",
                "schema_version": (
                    "1.3.0"
                    if normalized_prospective_models is not None
                    else ("1.2.0" if normalized_history_models is not None else "1.1.0")
                ),
                "generation_id": run["run_id"],
                "run_id": run["run_id"],
                "source_dataset_timestamp_raw": run["source_dataset_timestamp_before_raw"],
                "watermark_after": run["watermark_after"],
                "published_at": run["finished_at"],
                "coverage_class": "current_only",
                "hash_scope": "canonical_manifest_excluding_manifest_sha256",
                "source_manifest_sha256": source_manifest["manifest_sha256"],
                "query_sha256": run["query_manifest"]["query_sha256"],
                "configured_nct_ids": list(run["query_manifest"]["configured_nct_ids"]),
                "published_source_record_refs": list(run["published_source_record_refs"]),
                "configured_nct_count": health["configured_nct_count"],
                "observed_nct_count": health["observed_nct_count"],
                "last_attempt_at": health["last_attempt_at"],
                "last_success_at": health["last_success_at"],
                "artifacts": artifacts,
            }
            payload["manifest_sha256"] = canonical_json_sha256(payload)
            atomic_write(final_stage / "manifest.json", _json_bytes(payload))
            _fsync_directory(final_stage)
            return PreparedGeneration(
                generation_id=run["run_id"],
                stage_path=final_stage,
                manifest_sha256=payload["manifest_sha256"],
                watermark_after=run["watermark_after"],
                published_at=run["finished_at"],
                source_dataset_timestamp_raw=run["source_dataset_timestamp_before_raw"],
            )
        except Exception:
            if final_stage.exists():
                shutil.rmtree(final_stage)
            raise

    def install_generation(self, prepared: PreparedGeneration) -> Path:
        """Atomically install the generation directory but deliberately not its pointer."""

        stage = Path(prepared.stage_path)
        if not stage.exists() or stage.is_symlink():
            raise PublicationError("PUBLIC_STAGE_MISSING")
        try:
            _regular_tree_inventory(stage)
        except PublicationError as exc:
            raise PublicationError("PUBLIC_STAGE_MISSING") from exc
        if not _RUN_ID_RE.fullmatch(prepared.generation_id):
            raise PublicationError("PUBLIC_POINTER_INVALID")
        generations_root = self._generations_root(create=True)
        target = generations_root / prepared.generation_id
        if target.is_symlink():
            raise PublicationError("PUBLIC_GENERATION_COLLISION")
        if target.exists():
            manifest = self._load_generation_manifest(prepared.generation_id)
            if manifest["manifest_sha256"] != prepared.manifest_sha256:
                raise PublicationError("PUBLIC_GENERATION_COLLISION")
            shutil.rmtree(stage)
            return target
        os.replace(stage, target)
        _fsync_directory(target.parent)
        manifest = self._load_generation_manifest(prepared.generation_id)
        if manifest["manifest_sha256"] != prepared.manifest_sha256:
            raise PublicationError("PUBLIC_GENERATION_ARTIFACT_MISMATCH")
        return target

    def write_pointer(self, prepared: PreparedGeneration) -> None:
        """Advance the one last-good pointer only after all earlier stages succeed."""

        # Verify the installed target again immediately before its pointer can move.
        manifest = self._load_generation_manifest(prepared.generation_id)
        if manifest["manifest_sha256"] != prepared.manifest_sha256:
            raise PublicationError("PUBLIC_GENERATION_ARTIFACT_MISMATCH")
        pointer = {
            "contract_id": "biocatalyst_current_pointer.v1",
            "schema_version": "1.0.0",
            "generation_id": prepared.generation_id,
            "manifest_sha256": prepared.manifest_sha256,
            "watermark_after": prepared.watermark_after,
            "published_at": prepared.published_at,
        }
        replacement = _json_bytes(pointer)
        if self.pointer_path.is_symlink():
            raise PublicationError("POINTER_STATE_UNCERTAIN")
        try:
            previous = self.pointer_path.read_bytes() if self.pointer_path.exists() else None
        except OSError as exc:
            raise PublicationError("POINTER_STATE_UNCERTAIN") from exc
        try:
            atomic_write(
                self.pointer_path,
                replacement,
                after_replace=self._pointer_after_replace_hook,
            )
        except Exception as exc:
            self._rollback_pointer(previous, replacement)
            raise PublicationError("POINTER_WRITE_FAILED") from exc
        try:
            actual = self.pointer_path.read_bytes()
        except OSError as exc:
            raise PublicationError("POINTER_STATE_UNCERTAIN") from exc
        if actual != replacement:
            self._rollback_pointer(previous, replacement)
            raise PublicationError("POINTER_STATE_UNCERTAIN")

    def _rollback_pointer(self, previous: bytes | None, replacement: bytes) -> None:
        """Restore the old pointer after a post-replace durability fault.

        An error after ``os.replace`` is not evidence that the old pointer won.
        We inspect the file and either prove it is old, roll the known new bytes
        back, or surface uncertainty rather than silently moving the watermark.
        """

        if self.pointer_path.is_symlink():
            raise PublicationError("POINTER_STATE_UNCERTAIN")
        try:
            actual = self.pointer_path.read_bytes() if self.pointer_path.exists() else None
        except OSError as exc:
            raise PublicationError("POINTER_STATE_UNCERTAIN") from exc
        if actual == previous:
            return
        if actual != replacement:
            raise PublicationError("POINTER_STATE_UNCERTAIN")
        try:
            if previous is None:
                self.pointer_path.unlink()
                _fsync_directory(self.pointer_path.parent)
            else:
                atomic_write(self.pointer_path, previous)
        except Exception as exc:
            raise PublicationError("POINTER_STATE_UNCERTAIN") from exc
        try:
            restored = self.pointer_path.read_bytes() if self.pointer_path.exists() else None
        except OSError as exc:
            raise PublicationError("POINTER_STATE_UNCERTAIN") from exc
        if restored != previous:
            raise PublicationError("POINTER_STATE_UNCERTAIN")

    def write_health(self, payload: Mapping[str, Any]) -> None:
        self._validate_health(payload)
        if self.health_path.is_symlink():
            raise PublicationError("HEALTH_PAYLOAD_INVALID")
        atomic_write(self.health_path, _json_bytes(dict(payload)))

    def read_operational_health(
        self,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Read bound health and derive staleness from the transaction clock.

        The mutable file records the latest completed attempt; it is not a
        perpetual freshness assertion.  Every reader must use this seam so an
        idle/disabled timer cannot leave a historical success labeled fresh.
        The derived downgrade is observational and never rewrites disk.
        """

        if self.health_path.is_symlink() or not self.health_path.exists():
            raise PublicationError("HEALTH_PAYLOAD_INVALID")
        try:
            health_metadata = self.health_path.lstat()
        except OSError as exc:
            raise PublicationError("HEALTH_PAYLOAD_INVALID") from exc
        if not stat.S_ISREG(health_metadata.st_mode):
            raise PublicationError("HEALTH_PAYLOAD_INVALID")
        health = _load_json_object(self.health_path, code="HEALTH_PAYLOAD_INVALID")
        self._validate_health(health)

        committed = self.read_committed()
        generation_id = health.get("generation_id")
        if generation_id is not None:
            if committed is None or (
                generation_id != committed.generation_id
                or health.get("configured_nct_count") != committed.configured_nct_count
                or health.get("observed_nct_count") != committed.observed_nct_count
                or health.get("source_dataset_timestamp_raw")
                != committed.source_dataset_timestamp_raw
                or health.get("last_success_at") != committed.last_success_at
            ):
                raise PublicationError("HEALTH_PAYLOAD_INVALID")
        elif health.get("state") == "fresh" or committed is not None:
            # A fresh DTO needs a committed generation, and a mutable health
            # file may not silently forget a pointer that still exists.
            raise PublicationError("HEALTH_PAYLOAD_INVALID")

        if health.get("state") == "fresh":
            assert committed is not None
            self._validate_generation_health_binding(
                health,
                generation_id=committed.generation_id,
                configured_nct_count=committed.configured_nct_count,
                observed_nct_count=committed.observed_nct_count,
                source_dataset_timestamp_raw=committed.source_dataset_timestamp_raw,
                last_attempt_at=committed.last_attempt_at,
                last_success_at=committed.last_success_at,
            )
            observed_now = self.now_fn() if now is None else now
            if observed_now.tzinfo is None:
                raise PublicationError("HEALTH_PAYLOAD_INVALID")
            last_success = datetime.fromisoformat(
                committed.last_success_at.replace("Z", "+00:00")
            )
            age_seconds = (
                observed_now.astimezone(timezone.utc)
                - last_success.astimezone(timezone.utc)
            ).total_seconds()
            if age_seconds > health["freshness_budget_seconds"]:
                health = dict(health)
                health["state"] = "stale"
                health["last_error_code"] = "FRESHNESS_BUDGET_EXCEEDED"
        return dict(health)

    @staticmethod
    def _validate_generation_health_binding(
        payload: Mapping[str, Any],
        *,
        generation_id: str,
        configured_nct_count: int,
        observed_nct_count: int,
        source_dataset_timestamp_raw: str,
        last_attempt_at: str,
        last_success_at: str,
    ) -> None:
        """Tie a generation-local health DTO to its immutable source bundle."""

        PublicGenerationPublisher._validate_health(payload)
        if (
            payload.get("state") != "fresh"
            or payload.get("enabled") is not True
            or payload.get("generation_id") != generation_id
            or payload.get("configured_nct_count") != configured_nct_count
            or payload.get("observed_nct_count") != observed_nct_count
            or payload.get("source_dataset_timestamp_raw") != source_dataset_timestamp_raw
            or payload.get("last_attempt_at") != last_attempt_at
            or payload.get("last_success_at") != last_success_at
            or payload.get("freshness_budget_seconds") != 7200
            or payload.get("coverage_class") != "current_only"
            or payload.get("last_error_code") is not None
        ):
            raise PublicationError("GENERATION_HEALTH_BINDING_MISMATCH")

    @staticmethod
    def _validate_health(payload: Mapping[str, Any]) -> None:
        if set(payload) != _HEALTH_KEYS:
            raise PublicationError("HEALTH_PAYLOAD_INVALID")
        if payload.get("schema_version") != "biocatalyst_operational_health.v1":
            raise PublicationError("HEALTH_PAYLOAD_INVALID")
        if payload.get("state") not in _SAFE_HEALTH_STATES or not isinstance(payload.get("enabled"), bool):
            raise PublicationError("HEALTH_PAYLOAD_INVALID")
        if payload.get("generation_id") is not None and (
            not isinstance(payload["generation_id"], str)
            or not _RUN_ID_RE.fullmatch(payload["generation_id"])
        ):
            raise PublicationError("HEALTH_PAYLOAD_INVALID")
        for key in ("configured_nct_count", "observed_nct_count", "freshness_budget_seconds"):
            if not isinstance(payload.get(key), int) or isinstance(payload[key], bool) or payload[key] < 0 or payload[key] > 10_000_000:
                raise PublicationError("HEALTH_PAYLOAD_INVALID")
        _validate_utc_datetime(payload.get("last_attempt_at"))
        if payload.get("last_success_at") is not None:
            _validate_utc_datetime(payload["last_success_at"])
        if payload.get("source_dataset_timestamp_raw") is not None:
            _validate_source_timestamp(payload["source_dataset_timestamp_raw"])
        if payload.get("last_error_code") is not None and (
            not isinstance(payload["last_error_code"], str)
            or not re.fullmatch(r"[A-Z0-9_]{1,96}", payload["last_error_code"])
        ):
            raise PublicationError("HEALTH_PAYLOAD_INVALID")
        if payload.get("coverage_class") != "current_only":
            raise PublicationError("HEALTH_PAYLOAD_INVALID")


def success_health(
    *,
    run: Mapping[str, Any],
    generation_id: str,
) -> dict[str, Any]:
    counts = run["counts"]
    return {
        "schema_version": "biocatalyst_operational_health.v1",
        "state": "fresh",
        "enabled": True,
        "generation_id": generation_id,
        "configured_nct_count": int(counts["configured"]),
        "observed_nct_count": int(counts["studies_published"]),
        "last_attempt_at": run["finished_at"],
        "last_success_at": run["finished_at"],
        "source_dataset_timestamp_raw": run["source_dataset_timestamp_before_raw"],
        "freshness_budget_seconds": 7200,
        "coverage_class": "current_only",
        "last_error_code": None,
    }


def failure_health(
    *,
    state: str,
    enabled: bool,
    configured_nct_count: int,
    error_code: str | None,
    prior: CommittedGeneration | None,
    now: datetime,
) -> dict[str, Any]:
    if state not in _SAFE_HEALTH_STATES:
        raise ValueError("unsafe health state")
    return {
        "schema_version": "biocatalyst_operational_health.v1",
        "state": state,
        "enabled": enabled,
        "generation_id": prior.generation_id if prior else None,
        # If a pointer survives an incident, health must describe that exact
        # retained generation rather than the candidate's changed canary set.
        "configured_nct_count": (
            prior.configured_nct_count if prior else max(0, configured_nct_count)
        ),
        "observed_nct_count": prior.observed_nct_count if prior else 0,
        "last_attempt_at": _iso(now),
        "last_success_at": prior.last_success_at if prior else None,
        "source_dataset_timestamp_raw": prior.source_dataset_timestamp_raw if prior else None,
        "freshness_budget_seconds": 7200,
        "coverage_class": "current_only",
        "last_error_code": error_code,
    }


def assert_source_timestamp_monotonic(
    candidate_raw: str,
    prior: CommittedGeneration | None,
) -> None:
    """Reject a cross-run raw ``dataTimestamp`` regression without altering it.

    The upstream field may omit a UTC offset, so we do not synthesize one or do
    timezone arithmetic.  ClinicalTrials.gov's fixed-width literal format gives
    us the conservative equality/lexical comparison needed to catch a rollback.
    """

    candidate_raw = _validate_source_timestamp(candidate_raw)
    if prior is None:
        return
    prior_raw = _validate_source_timestamp(prior.source_dataset_timestamp_raw)
    candidate_time = _parse_source_timestamp(candidate_raw)
    prior_time = _parse_source_timestamp(prior_raw)
    if (candidate_time.tzinfo is None) != (prior_time.tzinfo is None):
        raise PublicationError("SOURCE_TIMESTAMP_INCOMPARABLE")
    if candidate_time.tzinfo is not None:
        candidate_time = candidate_time.astimezone(timezone.utc)
        prior_time = prior_time.astimezone(timezone.utc)
    if candidate_time < prior_time:
        raise PublicationError("SOURCE_TIMESTAMP_REGRESSION")


def assert_source_timestamp_not_future(
    candidate_raw: str,
    *,
    now: datetime,
    maximum_skew_seconds: int = _MAX_SOURCE_FUTURE_SKEW_SECONDS,
) -> None:
    """Reject a source-version value that could poison future watermark checks.

    This is intentionally separate from source freshness.  We never calculate
    age/SLO from CT.gov's raw dataTimestamp.  For an explicit-offset value we
    compare instants in UTC.  For an offset-less value we compare only its
    literal civil time against the local worker's current UTC-shaped civil
    time, leaving the upstream raw value unmodified and unlabelled.
    """

    candidate_raw = _validate_source_timestamp(candidate_raw)
    if (
        not isinstance(maximum_skew_seconds, int)
        or isinstance(maximum_skew_seconds, bool)
        or maximum_skew_seconds < 0
        or now.tzinfo is None
    ):
        raise PublicationError("SOURCE_TIMESTAMP_FUTURE")
    candidate = _parse_source_timestamp(candidate_raw)
    utc_now = now.astimezone(timezone.utc)
    if candidate.tzinfo is None:
        candidate_wall = candidate.replace(tzinfo=None)
        allowed_wall = utc_now.replace(tzinfo=None) + timedelta(seconds=maximum_skew_seconds)
        if candidate_wall > allowed_wall:
            raise PublicationError("SOURCE_TIMESTAMP_FUTURE")
        return
    if candidate.astimezone(timezone.utc) > utc_now + timedelta(seconds=maximum_skew_seconds):
        raise PublicationError("SOURCE_TIMESTAMP_FUTURE")


def mirror_private_receipt(
    store: Any,
    receipt: PrivateMirrorManifest,
) -> MirrorReceipt:
    """Read back the local mirror receipt too; it is part of a retained run."""

    try:
        return mirror_bytes_verified(
            store,
            object_key=receipt.object_key,
            payload=receipt.payload,
            content_type="application/json",
        )
    except StorageError as exc:
        raise PublicationError(exc.code) from exc


__all__ = [
    "CommittedGeneration",
    "PreparedGeneration",
    "PrivateMirrorManifest",
    "ProspectivePublicationEvidence",
    "PublicationError",
    "PublicGenerationPublisher",
    "archive_failed_attempt",
    "archive_private_stage",
    "assert_source_timestamp_monotonic",
    "assert_source_timestamp_not_future",
    "atomic_write",
    "build_private_mirror_manifest",
    "failure_health",
    "mirror_private_receipt",
    "success_health",
    "validate_candidate_run",
    "write_private_incident",
]
