"""Offline, fail-closed verification of BioCatalyst launch-SLO evidence.

This is deliberately a *reader*.  It has no network client, object-store
writer, scheduler, source activation, product projection, or authority hook.
The caller supplies an already-approved local evidence root.  Every object is
resolved by the digest declared in the immutable launch manifest; directory
components and artifact-provided paths are never trusted as routing input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from .contracts import (
    ContractError,
    ContractRegistry,
    ValidationIssue,
    canonical_json_bytes,
)


LAUNCH_SLO_EVIDENCE_ARTIFACT_CONTRACT_ID = "biocatalyst_launch_slo_evidence_artifact.v1"
LAUNCH_SLO_RECOVERY_OBJECT_CONTRACT_ID = "biocatalyst_launch_slo_recovery_object.v1"
_ARTIFACT_CONTRACT_ID = LAUNCH_SLO_EVIDENCE_ARTIFACT_CONTRACT_ID
_EVIDENCE_ROOT_SENTINEL = ".biocatalyst_launch_slo_offline_store.v1"
_EVIDENCE_ROOT_SENTINEL_BYTES = b"biocatalyst_launch_slo_offline_store.v1\n"
_MAX_MANIFEST_BYTES = 1 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_JSON_DEPTH = 48
_MAX_JSON_NODES = 2_000_000
_MAX_STRING_LENGTH = 256 * 1024
_MAX_NUMBER_TOKEN_LENGTH = 64
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_UTC_SECOND_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_STAGES = (
    "fetch",
    "parse",
    "contract_validation",
    "completeness_reconciliation",
    "publication",
    "watermark_or_pointer",
)
_CRITICAL_FAILURES = frozenset(
    ("integrity_failure", "rights_failure", "privacy_failure", "cross_tenant_failure")
)


class LaunchSloEvidenceError(ContractError):
    """A trusted local evidence store is absent, malformed, or contradictory."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(sorted(set(issues)))
        super().__init__("; ".join(str(issue) for issue in self.issues))


@dataclass(frozen=True)
class LaunchSloSourceOutcome:
    """One recomputed source outcome; never a runtime activation decision."""

    source_id: str
    expected_opportunities: int
    denominator: int
    successful_opportunities: int
    misses: int
    upstream_unavailable_observations: int
    maximum_consecutive_misses_observed: int
    freshness_p95_seconds: Decimal | None
    minimum_completeness_ratio_observed: Decimal | None
    minimum_vs_prior_scope_ratio_observed: Decimal | None
    stage_successes: tuple[tuple[str, int], ...]
    critical_failure_types: tuple[str, ...]
    passed: bool


@dataclass(frozen=True)
class LaunchSloEvidenceVerification:
    """The deterministic result produced from exact local evidence bytes."""

    manifest_id: str
    manifest_content_sha256: str
    predecessor_manifest_id: str
    predecessor_manifest_content_sha256: str
    generation_id: str
    sources: tuple[LaunchSloSourceOutcome, ...]
    aggregate_passed: bool


@dataclass(frozen=True)
class _ScheduledOpportunity:
    """One immutable cadence slot and its inclusive execution window."""

    opportunity_at: str
    opened_at: datetime
    closed_at: datetime


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _trusted_utc_now() -> datetime:
    """Return the verifier's process clock in UTC.

    This intentionally has no public injection parameter. Tests may monkeypatch
    this internal seam, while production callers cannot supply their own clock.
    """

    return datetime.now(timezone.utc)


def _frozen_trusted_utc_now() -> datetime:
    now = _trusted_utc_now()
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() != timedelta(0)
    ):
        raise LaunchSloEvidenceError(
            (
                _issue(
                    "$.trusted_clock",
                    "launch_slo.evidence.trusted_clock",
                    "internal trusted clock must return a timezone-aware UTC instant",
                ),
            )
        )
    return now.astimezone(timezone.utc)


def _canonical_z_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not _UTC_SECOND_RE.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _bounded_parse_int(token: str) -> int:
    if len(token.lstrip("-")) > _MAX_NUMBER_TOKEN_LENGTH:
        raise ValueError("integer token exceeds verifier limit")
    return int(token)


def _bounded_parse_float(token: str) -> float:
    if len(token) > _MAX_NUMBER_TOKEN_LENGTH:
        raise ValueError("number token exceeds verifier limit")
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-standard JSON constant {token!r}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _check_json_tree(value: Any, *, depth: int = 0, seen: list[int] | None = None) -> None:
    if seen is None:
        seen = [0]
    seen[0] += 1
    if seen[0] > _MAX_JSON_NODES:
        raise ValueError("JSON document exceeds node limit")
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("JSON document exceeds nesting-depth limit")
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise ValueError("JSON string exceeds verifier limit")
        return
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return
    if isinstance(value, list):
        for item in value:
            _check_json_tree(item, depth=depth + 1, seen=seen)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            if len(key) > _MAX_STRING_LENGTH:
                raise ValueError("JSON object key exceeds verifier limit")
            _check_json_tree(item, depth=depth + 1, seen=seen)
        return
    raise ValueError(f"unsupported JSON value {type(value).__name__}")


def _parse_canonical_json(raw: bytes, *, path: str) -> Mapping[str, Any]:
    try:
        text = raw.decode("utf-8")
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_int=_bounded_parse_int,
            parse_float=_bounded_parse_float,
            parse_constant=_reject_json_constant,
        )
        _check_json_tree(parsed)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise LaunchSloEvidenceError(
            (_issue(path, "launch_slo.evidence.json", f"invalid bounded JSON: {exc}"),)
        ) from exc
    if not isinstance(parsed, Mapping):
        raise LaunchSloEvidenceError(
            (_issue(path, "launch_slo.evidence.shape", "evidence bytes must encode a JSON object"),)
        )
    try:
        canonical = canonical_json_bytes(parsed)
    except ContractError as exc:
        raise LaunchSloEvidenceError(
            (_issue(path, "launch_slo.evidence.canonical", "evidence must be finite canonical JSON"),)
        ) from exc
    if raw != canonical:
        raise LaunchSloEvidenceError(
            (_issue(path, "launch_slo.evidence.noncanonical", "evidence bytes must be canonical JSON"),)
        )
    return parsed


class _OfflineEvidenceStore:
    """Read a pinned evidence tree using descriptor-relative traversal only."""

    def __init__(self, root: Path | str) -> None:
        supplied = Path(root)
        if not supplied.is_absolute():
            raise LaunchSloEvidenceError(
                (_issue("$.evidence_root", "launch_slo.evidence.root", "evidence_root must be an absolute approved path"),)
            )
        if any(part in {"", ".", ".."} for part in supplied.parts[1:]):
            raise LaunchSloEvidenceError(
                (_issue("$.evidence_root", "launch_slo.evidence.root", "evidence_root may not contain relative path components"),)
            )
        if (
            not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_NONBLOCK")
        ):
            raise LaunchSloEvidenceError(
                (_issue("$.evidence_root", "launch_slo.evidence.platform", "offline verification requires openat, O_DIRECTORY, O_NOFOLLOW, and O_NONBLOCK support"),)
            )
        self.root = supplied
        self._root_fd = -1
        try:
            self._root_fd = self._open_absolute_directory(supplied)
            sentinel = self._read_relative(
                Path(_EVIDENCE_ROOT_SENTINEL),
                expected_size=len(_EVIDENCE_ROOT_SENTINEL_BYTES),
                max_size=len(_EVIDENCE_ROOT_SENTINEL_BYTES),
                label="$.evidence_root",
            )
            if sentinel != _EVIDENCE_ROOT_SENTINEL_BYTES:
                raise LaunchSloEvidenceError(
                    (_issue("$.evidence_root", "launch_slo.evidence.root_sentinel", "evidence root sentinel is missing or invalid"),)
                )
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _open_absolute_directory(path: Path) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current_fd = -1
        try:
            current_fd = os.open(os.path.sep, flags)
            for component in path.parts[1:]:
                try:
                    next_fd = os.open(component, flags, dir_fd=current_fd)
                except OSError as exc:
                    code = (
                        "launch_slo.evidence.symlink"
                        if exc.errno == errno.ELOOP
                        else "launch_slo.evidence.root"
                    )
                    raise LaunchSloEvidenceError(
                        (_issue("$.evidence_root", code, f"approved evidence root is unavailable or unsafe: {exc}"),)
                    ) from exc
                try:
                    opened = os.fstat(next_fd)
                except BaseException:
                    os.close(next_fd)
                    raise
                if not stat.S_ISDIR(opened.st_mode):
                    os.close(next_fd)
                    raise LaunchSloEvidenceError(
                        (_issue("$.evidence_root", "launch_slo.evidence.root", "every evidence-root component must be a real directory"),)
                    )
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except BaseException:
            if current_fd >= 0:
                os.close(current_fd)
            raise

    def close(self) -> None:
        descriptor = self._root_fd
        self._root_fd = -1
        if descriptor >= 0:
            os.close(descriptor)

    def __enter__(self) -> "_OfflineEvidenceStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _read_relative(
        self,
        relative: Path,
        *,
        expected_size: int | None,
        max_size: int,
        label: str,
    ) -> bytes:
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise LaunchSloEvidenceError(
                (_issue(label, "launch_slo.evidence.path", "evidence path escapes the approved root"),)
            )
        if self._root_fd < 0:
            raise LaunchSloEvidenceError(
                (_issue(label, "launch_slo.evidence.closed", "evidence store descriptor is closed"),)
            )
        parent_fd = -1
        descriptor = -1
        try:
            parent_fd = os.dup(self._root_fd)
            for component in relative.parts[:-1]:
                try:
                    next_fd = os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=parent_fd,
                    )
                except OSError as exc:
                    code = (
                        "launch_slo.evidence.symlink"
                        if exc.errno == errno.ELOOP
                        else "launch_slo.evidence.missing"
                    )
                    raise LaunchSloEvidenceError(
                        (_issue(label, code, f"required evidence parent is unavailable or unsafe: {exc}"),)
                    ) from exc
                try:
                    opened_parent = os.fstat(next_fd)
                except BaseException:
                    os.close(next_fd)
                    raise
                if not stat.S_ISDIR(opened_parent.st_mode):
                    os.close(next_fd)
                    raise LaunchSloEvidenceError(
                        (_issue(label, "launch_slo.evidence.path", "evidence parent must be a real directory"),)
                    )
                os.close(parent_fd)
                parent_fd = next_fd
            try:
                descriptor = os.open(
                    relative.parts[-1],
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    code = "launch_slo.evidence.symlink"
                elif exc.errno in {errno.ENOENT, errno.ENOTDIR}:
                    code = "launch_slo.evidence.missing"
                else:
                    code = "launch_slo.evidence.open"
                raise LaunchSloEvidenceError(
                    (_issue(label, code, f"cannot safely open evidence: {exc}"),)
                ) from exc
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise LaunchSloEvidenceError(
                    (_issue(label, "launch_slo.evidence.file", "evidence must be a single-link regular file"),)
                )
            if before.st_size < 1 or before.st_size > max_size:
                raise LaunchSloEvidenceError(
                    (_issue(label, "launch_slo.evidence.size", f"evidence size must be between 1 and {max_size} bytes"),)
                )
            if expected_size is not None and before.st_size != expected_size:
                raise LaunchSloEvidenceError(
                    (_issue(label, "launch_slo.evidence.byte_count", "evidence size does not match the manifest-bound byte count"),)
                )
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise LaunchSloEvidenceError(
                        (_issue(label, "launch_slo.evidence.read", "evidence changed during bounded read"),)
                    )
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            signature_before = (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            signature_after = (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if signature_before != signature_after:
                raise LaunchSloEvidenceError(
                    (_issue(label, "launch_slo.evidence.toctou", "evidence changed while being read"),)
                )
            return b"".join(chunks)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if parent_fd >= 0:
                os.close(parent_fd)

    def predecessor_manifest(self, content_sha256: str) -> Mapping[str, Any]:
        raw = self._read_relative(
            Path("manifests") / f"{content_sha256}.json",
            expected_size=None,
            max_size=_MAX_MANIFEST_BYTES,
            label="$.soak.predecessor_manifest",
        )
        return _parse_canonical_json(raw, path="$.soak.predecessor_manifest")

    def artifact(self, artifact: Mapping[str, Any], *, label: str) -> Mapping[str, Any]:
        digest = artifact.get("content_sha256")
        byte_count = artifact.get("byte_count")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise LaunchSloEvidenceError(
                (_issue(f"{label}.content_sha256", "launch_slo.evidence.digest", "artifact digest must be a lowercase SHA-256"),)
            )
        if isinstance(byte_count, bool) or not isinstance(byte_count, int):
            raise LaunchSloEvidenceError(
                (_issue(f"{label}.byte_count", "launch_slo.evidence.byte_count", "artifact byte_count must be an integer"),)
            )
        if byte_count > _MAX_ARTIFACT_BYTES:
            raise LaunchSloEvidenceError(
                (_issue(f"{label}.byte_count", "launch_slo.evidence.size", f"offline verifier refuses artifacts larger than {_MAX_ARTIFACT_BYTES} bytes"),)
            )
        _assert_approved_object_ref(artifact, label=label)
        raw = self._read_relative(
            Path("artifacts") / f"{digest}.json",
            expected_size=byte_count,
            max_size=_MAX_ARTIFACT_BYTES,
            label=label,
        )
        actual = hashlib.sha256(raw).hexdigest()
        if actual != digest:
            raise LaunchSloEvidenceError(
                (_issue(f"{label}.content_sha256", "launch_slo.evidence.hash", "artifact bytes do not match the manifest-bound SHA-256"),)
            )
        return _parse_canonical_json(raw, path=label)

    def recovery_object(
        self,
        reference: Mapping[str, Any],
        *,
        role: str,
        label: str,
        registry: ContractRegistry,
    ) -> Mapping[str, Any]:
        digest = _strict_digest_reference(reference, path=label, expected_role=role).get(
            "content_sha256"
        )
        assert isinstance(digest, str)  # Checked by _strict_digest_reference.
        raw = self._read_relative(
            Path(role) / f"{digest}.json",
            expected_size=None,
            max_size=_MAX_ARTIFACT_BYTES,
            label=label,
        )
        if hashlib.sha256(raw).hexdigest() != digest:
            raise LaunchSloEvidenceError(
                (_issue(f"{label}.content_sha256", "launch_slo.evidence.hash", "recovery evidence bytes do not match their resolved SHA-256"),)
            )
        document = _parse_canonical_json(raw, path=label)
        issues = registry.issues(LAUNCH_SLO_RECOVERY_OBJECT_CONTRACT_ID, document)
        if issues:
            raise LaunchSloEvidenceError(issues)
        if document.get("role") != ("input" if role == "recovery_input" else "readback"):
            raise LaunchSloEvidenceError(
                (_issue(f"{label}.role", "launch_slo.evidence.recovery_role", "recovery object role must match its fixed digest-addressed store prefix"),)
            )
        return document


def _assert_approved_object_ref(artifact: Mapping[str, Any], *, label: str) -> None:
    object_ref = artifact.get("object_ref")
    digest = artifact.get("content_sha256")
    kind = artifact.get("kind")
    if not all(isinstance(value, str) for value in (object_ref, digest, kind)):
        raise LaunchSloEvidenceError(
            (_issue(label, "launch_slo.evidence.object_ref", "artifact object_ref, kind, and digest must be strings"),)
        )
    parsed = urlsplit(object_ref)
    expected_path = f"/{kind}/{digest}.json"
    if (
        parsed.scheme != "r2"
        or parsed.netloc != "biocatalyst-soak"
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise LaunchSloEvidenceError(
            (_issue(f"{label}.object_ref", "launch_slo.evidence.object_ref", "artifact object_ref must be the approved digest-addressed r2 path"),)
        )


def _assert_artifact_document_binding(
    document: Mapping[str, Any],
    artifact_ref: Mapping[str, Any],
    *,
    label: str,
    registry: ContractRegistry,
    trusted_now: datetime,
) -> None:
    issues = registry.issues(_ARTIFACT_CONTRACT_ID, document)
    binding_fields = (
        "kind",
        "scheduled_manifest_id",
        "scheduled_manifest_content_sha256",
        "source_id",
        "window_start",
        "window_end",
        "captured_at",
    )
    for field in binding_fields:
        if document.get(field) != artifact_ref.get(field):
            issues += (
                _issue(
                    f"{label}.{field}",
                    "launch_slo.evidence.binding",
                    f"typed artifact field {field!r} must exactly match its manifest artifact reference",
                ),
            )
    if document.get("contract_id") != _ARTIFACT_CONTRACT_ID:
        issues += (
            _issue(f"{label}.contract_id", "launch_slo.evidence.contract", "artifact is not a registered launch-SLO evidence artifact"),
        )
    if issues:
        raise LaunchSloEvidenceError(issues)
    captured = _canonical_z_datetime(document.get("captured_at"))
    window_end = _canonical_z_datetime(document.get("window_end"))
    if captured is None or window_end is None or captured < window_end:
        raise LaunchSloEvidenceError(
            (_issue(f"{label}.captured_at", "launch_slo.evidence.capture_time", "completed-pass evidence must be canonically captured at or after the frozen soak end"),)
        )
    if captured > trusted_now:
        raise LaunchSloEvidenceError(
            (_issue(f"{label}.captured_at", "launch_slo.evidence.future_time", "artifact capture cannot be later than the verifier's trusted UTC clock"),)
        )


def _artifacts_by_kind(
    manifest: Mapping[str, Any],
    store: _OfflineEvidenceStore,
    registry: ContractRegistry,
    trusted_now: datetime,
) -> dict[str, list[tuple[str, Mapping[str, Any], Mapping[str, Any]]]]:
    soak = manifest.get("soak")
    if not isinstance(soak, Mapping):
        raise LaunchSloEvidenceError(
            (_issue("$.soak", "launch_slo.evidence.manifest", "completed manifest has no soak object"),)
        )
    slots: tuple[tuple[str, object], ...] = (
        ("$.soak.telemetry_generation_ref", soak.get("telemetry_generation_ref")),
        ("$.soak.ci_validation_receipt_ref", soak.get("ci_validation_receipt_ref")),
    )
    lists: tuple[tuple[str, object], ...] = (
        ("$.soak.raw_telemetry_refs", soak.get("raw_telemetry_refs")),
        ("$.soak.correction_replay_evidence_refs", soak.get("correction_replay_evidence_refs")),
        ("$.soak.rollback_restore_evidence_refs", soak.get("rollback_restore_evidence_refs")),
    )
    resolved: dict[str, list[tuple[str, Mapping[str, Any], Mapping[str, Any]]]] = {}
    digests: set[str] = set()
    for label, candidate in slots:
        if not isinstance(candidate, Mapping):
            raise LaunchSloEvidenceError(
                (_issue(label, "launch_slo.evidence.manifest", "completed evidence role is absent"),)
            )
        entries = ((label, candidate),)
        for entry_label, artifact_ref in entries:
            digest = artifact_ref.get("content_sha256")
            if isinstance(digest, str) and digest in digests:
                raise LaunchSloEvidenceError(
                    (_issue(f"{entry_label}.content_sha256", "launch_slo.evidence.role_reuse", "artifact digest may serve only one evidence role"),)
                )
            if isinstance(digest, str):
                digests.add(digest)
            document = store.artifact(artifact_ref, label=entry_label)
            _assert_artifact_document_binding(
                document,
                artifact_ref,
                label=entry_label,
                registry=registry,
                trusted_now=trusted_now,
            )
            kind = artifact_ref.get("kind")
            if isinstance(kind, str):
                resolved.setdefault(kind, []).append((entry_label, artifact_ref, document))
    for label, candidates in lists:
        if not isinstance(candidates, list):
            raise LaunchSloEvidenceError(
                (_issue(label, "launch_slo.evidence.manifest", "evidence role must be an ordered list"),)
            )
        for index, artifact_ref in enumerate(candidates):
            entry_label = f"{label}[{index}]"
            if not isinstance(artifact_ref, Mapping):
                raise LaunchSloEvidenceError(
                    (_issue(entry_label, "launch_slo.evidence.manifest", "evidence reference must be an object"),)
                )
            digest = artifact_ref.get("content_sha256")
            if isinstance(digest, str) and digest in digests:
                raise LaunchSloEvidenceError(
                    (_issue(f"{entry_label}.content_sha256", "launch_slo.evidence.role_reuse", "artifact digest may serve only one evidence role"),)
                )
            if isinstance(digest, str):
                digests.add(digest)
            document = store.artifact(artifact_ref, label=entry_label)
            _assert_artifact_document_binding(
                document,
                artifact_ref,
                label=entry_label,
                registry=registry,
                trusted_now=trusted_now,
            )
            kind = artifact_ref.get("kind")
            if isinstance(kind, str):
                resolved.setdefault(kind, []).append((entry_label, artifact_ref, document))
    return resolved


def _single_aggregate_artifact(
    entries: Mapping[str, list[tuple[str, Mapping[str, Any], Mapping[str, Any]]]],
    *,
    kind: str,
) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    candidates = entries.get(kind, [])
    if len(candidates) != 1 or candidates[0][1].get("source_id") is not None:
        raise LaunchSloEvidenceError(
            (_issue(f"$.soak.{kind}", "launch_slo.evidence.role_coverage", f"exactly one aggregate {kind} artifact is required"),)
        )
    return candidates[0]


def _per_source_artifacts(
    entries: Mapping[str, list[tuple[str, Mapping[str, Any], Mapping[str, Any]]]],
    *,
    kind: str,
    source_ids: set[str],
) -> dict[str, tuple[str, Mapping[str, Any], Mapping[str, Any]]]:
    candidates = entries.get(kind, [])
    by_source: dict[str, tuple[str, Mapping[str, Any], Mapping[str, Any]]] = {}
    for candidate in candidates:
        source_id = candidate[1].get("source_id")
        if not isinstance(source_id, str) or source_id in by_source:
            raise LaunchSloEvidenceError(
                (_issue(f"$.soak.{kind}", "launch_slo.evidence.role_coverage", f"{kind} must have one distinct artifact for each source"),)
            )
        by_source[source_id] = candidate
    if set(by_source) != source_ids:
        raise LaunchSloEvidenceError(
            (_issue(f"$.soak.{kind}", "launch_slo.evidence.role_coverage", f"{kind} source set must exactly equal launch-critical sources"),)
        )
    return by_source


def _expected_schedule(
    policy: Mapping[str, Any], start: datetime, end: datetime
) -> tuple[_ScheduledOpportunity, ...]:
    opportunity = policy.get("opportunity_rule")
    if not isinstance(opportunity, Mapping):
        raise LaunchSloEvidenceError(
            (_issue("$.sources", "launch_slo.evidence.schedule", "source policy has no opportunity rule"),)
        )
    cadence = opportunity.get("cadence_seconds")
    open_offset = opportunity.get("window_open_offset_seconds")
    close_offset = opportunity.get("window_close_offset_seconds")
    if isinstance(cadence, bool) or not isinstance(cadence, int) or cadence < 1:
        raise LaunchSloEvidenceError(
            (_issue("$.sources", "launch_slo.evidence.schedule", "source cadence must be a positive integer"),)
        )
    if (
        isinstance(open_offset, bool)
        or isinstance(close_offset, bool)
        or not isinstance(open_offset, int)
        or not isinstance(close_offset, int)
        or not 0 <= open_offset < close_offset <= cadence
    ):
        raise LaunchSloEvidenceError(
            (_issue("$.sources", "launch_slo.evidence.schedule", "frozen opportunity offsets must satisfy 0 <= open < close <= cadence"),)
        )
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if (start - epoch).total_seconds() % cadence or (end - start).total_seconds() % cadence:
        raise LaunchSloEvidenceError(
            (_issue("$.soak", "launch_slo.evidence.schedule", "soak bounds must exactly align to the frozen UTC cadence"),)
        )
    count = int((end - start).total_seconds() // cadence)
    schedule: list[_ScheduledOpportunity] = []
    for index in range(count):
        slot = start + timedelta(seconds=cadence * index)
        opened = slot + timedelta(seconds=open_offset)
        closed = slot + timedelta(seconds=close_offset)
        schedule.append(
            _ScheduledOpportunity(
                opportunity_at=opened.strftime("%Y-%m-%dT%H:%M:%SZ"),
                opened_at=opened,
                closed_at=closed,
            )
        )
    return tuple(schedule)


def _nearest_rank_p95(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    index = math.ceil(Decimal("0.95") * len(values)) - 1
    return sorted(values)[index]


def _maximum_consecutive_misses(outcomes: Sequence[str]) -> int:
    maximum = current = 0
    for outcome in outcomes:
        if outcome == "miss":
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def _strict_digest_reference(
    reference: object,
    *,
    path: str,
    expected_role: str,
) -> Mapping[str, Any]:
    if not isinstance(reference, Mapping):
        raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.reference", "evidence reference must be an object"),))
    object_ref = reference.get("object_ref")
    digest = reference.get("content_sha256")
    if not isinstance(object_ref, str) or not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.reference", "evidence reference must contain a safe object reference and SHA-256"),))
    parsed = urlsplit(object_ref)
    expected_path = f"/{expected_role}/{digest}.json"
    if (
        parsed.scheme != "r2"
        or parsed.netloc != "biocatalyst-soak"
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_path
    ):
        raise LaunchSloEvidenceError((_issue(f"{path}.object_ref", "launch_slo.evidence.reference", "evidence reference must use its fixed approved digest-addressed R2 role path"),))
    return reference


def _derived_recovery_pass(
    document: Mapping[str, Any],
    *,
    kind: str,
    label: str,
    store: _OfflineEvidenceStore,
    registry: ContractRegistry,
    trusted_now: datetime,
) -> bool:
    expected_procedure = f"biocatalyst_{kind}_procedure.v1"
    if document.get("procedure_version") != expected_procedure:
        raise LaunchSloEvidenceError((_issue(f"{label}.procedure_version", "launch_slo.evidence.recovery_procedure", "recovery procedure version must match the evidence role"),))
    drill_id = document.get("drill_id")
    if not isinstance(drill_id, str) or re.fullmatch(
        rf"biocatalyst_{re.escape(kind)}_[a-f0-9]{{24}}", drill_id
    ) is None:
        raise LaunchSloEvidenceError(
            (_issue(f"{label}.drill_id", "launch_slo.evidence.recovery_drill_id", "recovery drill ID prefix must match its correction or rollback evidence kind"),)
        )
    window_end = _canonical_z_datetime(document.get("window_end"))
    started = _canonical_z_datetime(document.get("started_at"))
    completed = _canonical_z_datetime(document.get("completed_at"))
    captured = _canonical_z_datetime(document.get("captured_at"))
    input_ref = _strict_digest_reference(
        document.get("input_evidence"),
        path=f"{label}.input_evidence",
        expected_role="recovery_input",
    )
    target_ref = _strict_digest_reference(
        document.get("target_evidence"),
        path=f"{label}.target_evidence",
        expected_role="recovery_readback",
    )
    input_object = store.recovery_object(
        input_ref,
        role="recovery_input",
        label=f"{label}.input_evidence",
        registry=registry,
    )
    readback_object = store.recovery_object(
        target_ref,
        role="recovery_readback",
        label=f"{label}.target_evidence",
        registry=registry,
    )
    input_captured = _canonical_z_datetime(input_object.get("captured_at"))
    readback_captured = _canonical_z_datetime(readback_object.get("captured_at"))
    chronology = (
        window_end,
        input_captured,
        started,
        completed,
        readback_captured,
        captured,
        trusted_now,
    )
    if any(moment is None for moment in chronology) or any(
        earlier > later
        for earlier, later in zip(chronology, chronology[1:])
        if earlier is not None and later is not None
    ):
        raise LaunchSloEvidenceError(
            (_issue(label, "launch_slo.evidence.recovery_time", "recovery chronology must be soak end <= input capture <= start <= completion <= readback capture <= artifact capture <= trusted UTC now"),)
        )
    expected_binding = {
        "source_id": document.get("source_id"),
        "generation_id": document.get("generation_id"),
        "operation_kind": kind,
        "operation_id": document.get("drill_id"),
    }
    for field, expected in expected_binding.items():
        if input_object.get(field) != expected or readback_object.get(field) != expected:
            raise LaunchSloEvidenceError((_issue(label, "launch_slo.evidence.recovery_binding", f"resolved recovery {field} must exactly bind the enclosing recovery artifact"),))
    expected_digest = document.get("expected_result_sha256")
    observed_digest = document.get("observed_result_sha256")
    checks = document.get("verification_checks")
    if not isinstance(checks, Mapping) or not all(
        checks.get(key) is True
        for key in ("input_bound", "target_bound", "operation_applied", "readback_verified")
    ):
        derived = False
    else:
        derived = bool(
            expected_digest == observed_digest
            and isinstance(expected_digest, str)
            and _SHA256_RE.fullmatch(expected_digest)
            and input_object.get("expected_result_sha256") == expected_digest
            and readback_object.get("input_content_sha256") == input_ref.get("content_sha256")
            and readback_object.get("observed_result_sha256") == observed_digest
            and readback_object.get("readback_verified") is True
        )
    claimed = document.get("result")
    if claimed != ("passed" if derived else "failed"):
        raise LaunchSloEvidenceError((_issue(f"{label}.result", "launch_slo.evidence.recovery_result", "recovery result must equal its typed digest/check recomputation"),))
    return derived


def _derived_ci_pass(
    document: Mapping[str, Any], *, label: str, trusted_now: datetime
) -> bool:
    window_end = _canonical_z_datetime(document.get("window_end"))
    started = _canonical_z_datetime(document.get("started_at"))
    completed = _canonical_z_datetime(document.get("completed_at"))
    captured = _canonical_z_datetime(document.get("captured_at"))
    if (
        window_end is None
        or started is None
        or completed is None
        or captured is None
        or started < window_end
        or completed < started
        or captured < completed
        or captured > trusted_now
    ):
        raise LaunchSloEvidenceError((_issue(label, "launch_slo.evidence.ci_time", "CI chronology must be soak end <= start <= completion <= artifact capture <= trusted UTC now"),))
    outcomes = document.get("check_outcomes")
    required = ("contract_validation", "evidence_integrity", "source_recomputation")
    derived = isinstance(outcomes, Mapping) and all(outcomes.get(key) is True for key in required)
    claimed = document.get("result")
    if claimed != ("passed" if derived else "failed"):
        raise LaunchSloEvidenceError((_issue(f"{label}.result", "launch_slo.evidence.ci_result", "CI result must equal its typed check-outcome recomputation"),))
    return bool(derived)


def _recompute_source(
    *,
    source_id: str,
    policy: Mapping[str, Any],
    artifact: Mapping[str, Any],
    expected_schedule: tuple[_ScheduledOpportunity, ...],
) -> LaunchSloSourceOutcome:
    observations = artifact.get("observations")
    if not isinstance(observations, list):
        raise LaunchSloEvidenceError(
            (_issue(f"$.artifact[{source_id}].observations", "launch_slo.evidence.observations", "raw telemetry must contain observations"),)
        )
    by_time: dict[str, Mapping[str, Any]] = {}
    for index, observation in enumerate(observations):
        path = f"$.artifact[{source_id}].observations[{index}]"
        if not isinstance(observation, Mapping):
            raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.observation", "observation must be an object"),))
        moment = observation.get("opportunity_at")
        if not isinstance(moment, str) or _canonical_z_datetime(moment) is None or moment in by_time:
            raise LaunchSloEvidenceError((_issue(f"{path}.opportunity_at", "launch_slo.evidence.observation_time", "each canonical opportunity timestamp must appear exactly once"),))
        by_time[moment] = observation
    expected_set = {window.opportunity_at for window in expected_schedule}
    observed_set = set(by_time)
    if observed_set != expected_set or len(observations) != len(expected_schedule):
        raise LaunchSloEvidenceError(
            (_issue(f"$.artifact[{source_id}].observations", "launch_slo.evidence.opportunity_coverage", "raw telemetry must cover every and only frozen scheduled opportunity exactly once"),)
        )

    stage_successes = {stage: 0 for stage in _STAGES}
    successful = misses = upstream = 0
    critical: set[str] = set()
    freshnesses: list[Decimal] = []
    completenesses: list[Decimal] = []
    prior_scopes: list[Decimal] = []
    outcomes: list[str] = []
    for window in expected_schedule:
        moment = window.opportunity_at
        observation = by_time[moment]
        path = f"$.artifact[{source_id}].observations[{moment}]"
        attempted = _canonical_z_datetime(observation.get("attempted_at"))
        completed = _canonical_z_datetime(observation.get("completed_at"))
        if (
            attempted is None
            or completed is None
            or attempted < window.opened_at
            or completed < attempted
            or completed > window.closed_at
        ):
            raise LaunchSloEvidenceError(
                (_issue(path, "launch_slo.evidence.opportunity_window", "every observation must satisfy frozen window open <= attempted_at <= completed_at <= window close"),)
            )
        outcome = observation.get("outcome")
        stages = observation.get("stage_results")
        failure_types = observation.get("critical_failure_types")
        if outcome not in {"success", "miss"} or not isinstance(stages, Mapping) or not isinstance(failure_types, list):
            raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.observation", "observation fields are malformed"),))
        stage_values = [stages.get(stage) for stage in _STAGES]
        if not all(isinstance(value, bool) for value in stage_values):
            raise LaunchSloEvidenceError((_issue(f"{path}.stage_results", "launch_slo.evidence.stage", "every required stage must be boolean"),))
        all_stages = all(stage_values)
        seen_false = False
        for value in stage_values:
            if value is False:
                seen_false = True
            elif seen_false:
                raise LaunchSloEvidenceError((_issue(f"{path}.stage_results", "launch_slo.evidence.stage_order", "stage outcomes must form a monotone true-prefix; no later stage may pass after an earlier failure"),))
        freshness = _decimal(observation.get("freshness_seconds"))
        completeness = _decimal(observation.get("completeness_ratio"))
        prior_scope = _decimal(observation.get("prior_scope_ratio"))
        upstream_unavailable = observation.get("upstream_unavailable")
        if not isinstance(upstream_unavailable, bool) or any(item not in _CRITICAL_FAILURES for item in failure_types):
            raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.observation", "observation has an invalid outage or critical-failure value"),))
        critical.update(str(item) for item in failure_types)
        if upstream_unavailable and any(stage_values):
            raise LaunchSloEvidenceError((_issue(f"{path}.upstream_unavailable", "launch_slo.evidence.upstream_stage", "upstream-unavailable observations must fail before fetch"),))
        if outcome == "success":
            if not all_stages or upstream_unavailable or None in (freshness, completeness, prior_scope):
                raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.success_reconciliation", "successful opportunities require every stage, measurements, and no upstream outage"),))
            successful += 1
        else:
            if all_stages:
                raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.miss_reconciliation", "a miss must have at least one failed stage"),))
            if upstream_unavailable and any(value is not None for value in (observation.get("freshness_seconds"), observation.get("completeness_ratio"), observation.get("prior_scope_ratio"))):
                raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.upstream_measurement", "upstream-unavailable observations cannot carry downstream measurements"),))
            misses += 1
            upstream += int(upstream_unavailable)
        if stages.get("fetch") is True:
            if freshness is None:
                raise LaunchSloEvidenceError((_issue(f"{path}.freshness_seconds", "launch_slo.evidence.freshness", "a fetched observation requires a bounded freshness measurement"),))
            freshnesses.append(freshness)
        elif observation.get("freshness_seconds") is not None:
            raise LaunchSloEvidenceError((_issue(f"{path}.freshness_seconds", "launch_slo.evidence.freshness", "unfetched observations cannot carry freshness measurements"),))
        if stages.get("completeness_reconciliation") is True:
            if completeness is None or prior_scope is None:
                raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.completeness", "reconciled observations require completeness and prior-scope measurements"),))
            completenesses.append(completeness)
            prior_scopes.append(prior_scope)
        elif any(value is not None for value in (observation.get("completeness_ratio"), observation.get("prior_scope_ratio"))):
            raise LaunchSloEvidenceError((_issue(path, "launch_slo.evidence.completeness", "unreconciled observations cannot carry completeness/prior-scope measurements"),))
        for stage, value in zip(_STAGES, stage_values):
            if value is True:
                stage_successes[stage] += 1
        outcomes.append(str(outcome))

    budget = policy.get("error_budget")
    freshness_policy = policy.get("freshness")
    completeness_policy = policy.get("completeness")
    binding = policy.get("registry_binding")
    threshold = _decimal(budget.get("minimum_opportunity_success_ratio") if isinstance(budget, Mapping) else None)
    freshness_limit = _decimal(freshness_policy.get("maximum_seconds") if isinstance(freshness_policy, Mapping) else None)
    completeness_limit = _decimal(completeness_policy.get("minimum_ratio") if isinstance(completeness_policy, Mapping) else None)
    prior_scope_limit = _decimal(completeness_policy.get("minimum_vs_prior_scope_ratio") if isinstance(completeness_policy, Mapping) else None)
    max_misses = binding.get("maximum_consecutive_misses") if isinstance(binding, Mapping) else None
    p95 = _nearest_rank_p95(freshnesses)
    min_completeness = min(completenesses) if completenesses else None
    min_prior_scope = min(prior_scopes) if prior_scopes else None
    denominator = len(expected_schedule)
    maximum_misses = _maximum_consecutive_misses(outcomes)
    passed = bool(
        denominator
        and threshold is not None
        and Decimal(successful) / Decimal(denominator) >= threshold
        and isinstance(max_misses, int)
        and not isinstance(max_misses, bool)
        and maximum_misses <= max_misses
        and p95 is not None
        and freshness_limit is not None
        and p95 <= freshness_limit
        and min_completeness is not None
        and completeness_limit is not None
        and min_completeness >= completeness_limit
        and min_prior_scope is not None
        and prior_scope_limit is not None
        and min_prior_scope >= prior_scope_limit
        and not critical
    )
    return LaunchSloSourceOutcome(
        source_id=source_id,
        expected_opportunities=denominator,
        denominator=denominator,
        successful_opportunities=successful,
        misses=misses,
        upstream_unavailable_observations=upstream,
        maximum_consecutive_misses_observed=maximum_misses,
        freshness_p95_seconds=p95,
        minimum_completeness_ratio_observed=min_completeness,
        minimum_vs_prior_scope_ratio_observed=min_prior_scope,
        stage_successes=tuple((stage, stage_successes[stage]) for stage in _STAGES),
        critical_failure_types=tuple(sorted(critical)),
        passed=passed,
    )


def _assert_claim_matches_outcome(claim: Mapping[str, Any], outcome: LaunchSloSourceOutcome, *, index: int) -> None:
    expected: dict[str, object] = {
        "source_id": outcome.source_id,
        "expected_opportunities": outcome.expected_opportunities,
        "excluded_predeclared_maintenance": 0,
        "excluded_source_native_nonpublication": 0,
        "denominator": outcome.denominator,
        "stage_successes": dict(outcome.stage_successes),
        "successful_opportunities": outcome.successful_opportunities,
        "misses": outcome.misses,
        "upstream_unavailable_observations": outcome.upstream_unavailable_observations,
        "maximum_consecutive_misses_observed": outcome.maximum_consecutive_misses_observed,
        "freshness_p95_seconds": outcome.freshness_p95_seconds,
        "minimum_completeness_ratio_observed": outcome.minimum_completeness_ratio_observed,
        "minimum_vs_prior_scope_ratio_observed": outcome.minimum_vs_prior_scope_ratio_observed,
        "critical_failure_types": list(outcome.critical_failure_types),
        "passed": outcome.passed,
    }
    for field, value in expected.items():
        actual = claim.get(field)
        comparable = float(value) if isinstance(value, Decimal) else value
        if actual != comparable:
            raise LaunchSloEvidenceError(
                (_issue(f"$.soak.source_results[{index}].{field}", "launch_slo.evidence.recomputed_result", "claimed result must exactly equal the trusted raw-evidence recomputation"),)
            )


def _assert_predecessor(
    manifest: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    *,
    registry: ContractRegistry,
) -> None:
    issues = registry.issues("biocatalyst_launch_slo_manifest.v1", predecessor)
    if issues:
        raise LaunchSloEvidenceError(
            tuple(
                _issue("$.soak.predecessor_manifest" + issue.path[1:], "launch_slo.evidence.predecessor_contract", issue.message)
                for issue in issues
            )
        )
    predecessor_hash = manifest.get("supersedes_manifest_content_sha256")
    predecessor_id = manifest.get("supersedes_manifest_id")
    if predecessor.get("content_sha256") != predecessor_hash or predecessor.get("manifest_id") != predecessor_id:
        raise LaunchSloEvidenceError(
            (_issue("$.soak.predecessor_manifest", "launch_slo.evidence.predecessor_binding", "resolved predecessor bytes do not match the claimed immutable manifest identity"),)
        )
    if predecessor.get("state") != "soak_scheduled":
        raise LaunchSloEvidenceError(
            (_issue("$.soak.predecessor_manifest.state", "launch_slo.evidence.predecessor_state", "a release pass requires a pre-existing soak_scheduled predecessor"),)
        )
    frozen_keys = (
        "contract_id",
        "schema_version",
        "source_registry_ref",
        "source_registry_sha256",
        "sources",
        "aggregate_pass_policy",
        "unconditional_beta_failures",
        "authority",
        "hash_scope",
    )
    for key in frozen_keys:
        if manifest.get(key) != predecessor.get(key):
            raise LaunchSloEvidenceError(
                (_issue(f"$.{key}", "launch_slo.evidence.frozen_policy", "a completed claim may not change frozen predecessor policy"),)
            )
    predecessor_soak = predecessor.get("soak")
    current_soak = manifest.get("soak")
    if not isinstance(predecessor_soak, Mapping) or not isinstance(current_soak, Mapping):
        raise LaunchSloEvidenceError((_issue("$.soak", "launch_slo.evidence.predecessor", "both manifests require soak objects"),))
    for key in ("required_duration_seconds", "window_start", "window_end"):
        if current_soak.get(key) != predecessor_soak.get(key):
            raise LaunchSloEvidenceError(
                (_issue(f"$.soak.{key}", "launch_slo.evidence.frozen_window", "completed claim must retain the scheduled predecessor soak window"),)
            )


def _verify_biocatalyst_launch_slo_evidence_with_store(
    manifest: Mapping[str, Any],
    *,
    store: _OfflineEvidenceStore,
    registry: ContractRegistry,
    trusted_now: datetime,
) -> LaunchSloEvidenceVerification:
    predecessor_hash = manifest.get("supersedes_manifest_content_sha256")
    if not isinstance(predecessor_hash, str) or not _SHA256_RE.fullmatch(predecessor_hash):
        raise LaunchSloEvidenceError(
            (_issue("$.supersedes_manifest_content_sha256", "launch_slo.evidence.predecessor", "completed pass requires a safe predecessor digest"),)
        )
    predecessor = store.predecessor_manifest(predecessor_hash)
    _assert_predecessor(manifest, predecessor, registry=registry)

    sources = manifest.get("sources")
    soak = manifest.get("soak")
    if not isinstance(sources, list) or not isinstance(soak, Mapping):
        raise LaunchSloEvidenceError((_issue("$", "launch_slo.evidence.manifest", "completed manifest has no source/soak data"),))
    policies = {row.get("source_id"): row for row in sources if isinstance(row, Mapping) and isinstance(row.get("source_id"), str)}
    source_ids = set(policies)
    if len(policies) != len(sources) or not source_ids:
        raise LaunchSloEvidenceError((_issue("$.sources", "launch_slo.evidence.sources", "launch-critical source policies must be unique and complete"),))
    start = _canonical_z_datetime(soak.get("window_start"))
    end = _canonical_z_datetime(soak.get("window_end"))
    if start is None or end is None or end - start != timedelta(days=14):
        raise LaunchSloEvidenceError((_issue("$.soak", "launch_slo.evidence.window", "verification requires an exact canonical fourteen-day window"),))
    if end > trusted_now:
        raise LaunchSloEvidenceError(
            (_issue("$.soak.window_end", "launch_slo.evidence.future_time", "the frozen soak end cannot be later than the verifier's trusted UTC clock"),)
        )
    entries = _artifacts_by_kind(manifest, store, registry, trusted_now)
    _, _, generation_document = _single_aggregate_artifact(entries, kind="telemetry_generation")
    _, _, ci_document = _single_aggregate_artifact(entries, kind="ci_validation")
    raw_by_source = _per_source_artifacts(entries, kind="raw_telemetry", source_ids=source_ids)
    correction_by_source = _per_source_artifacts(entries, kind="correction_replay", source_ids=source_ids)
    rollback_by_source = _per_source_artifacts(entries, kind="rollback_restore", source_ids=source_ids)
    generation_id = generation_document.get("generation_id")
    if not isinstance(generation_id, str):
        raise LaunchSloEvidenceError((_issue("$.soak.telemetry_generation_ref", "launch_slo.evidence.generation", "telemetry generation must declare a generation ID"),))
    for kind, candidates in entries.items():
        for label, _, document in candidates:
            if document.get("generation_id") != generation_id:
                raise LaunchSloEvidenceError((_issue(label, "launch_slo.evidence.generation", "all typed evidence must bind one telemetry generation"),))
    raw_refs = generation_document.get("raw_telemetry_refs")
    expected_ref_rows = [
        {"source_id": source_id, "content_sha256": raw_by_source[source_id][1].get("content_sha256")}
        for source_id in sorted(source_ids)
    ]
    if raw_refs != expected_ref_rows:
        raise LaunchSloEvidenceError((_issue("$.soak.telemetry_generation_ref.raw_telemetry_refs", "launch_slo.evidence.generation_refs", "telemetry generation must bind exactly the lexically ordered raw telemetry evidence set"),))
    if not _derived_ci_pass(
        ci_document,
        label="$.soak.ci_validation_receipt_ref",
        trusted_now=trusted_now,
    ):
        raise LaunchSloEvidenceError((_issue("$.soak.ci_validation_receipt_ref", "launch_slo.evidence.ci", "typed CI evidence did not satisfy every required verification check"),))
    for source_id in source_ids:
        for kind, document in (("correction_replay", correction_by_source[source_id][2]), ("rollback_restore", rollback_by_source[source_id][2])):
            if not _derived_recovery_pass(
                document,
                kind=kind,
                label=f"$.soak.{kind}[{source_id}]",
                store=store,
                registry=registry,
                trusted_now=trusted_now,
            ):
                raise LaunchSloEvidenceError((_issue(f"$.soak.{kind}[{source_id}]", "launch_slo.evidence.recovery", "every source recovery drill must have passed before a release pass claim"),))

    claimed_results = soak.get("source_results")
    if not isinstance(claimed_results, list):
        raise LaunchSloEvidenceError((_issue("$.soak.source_results", "launch_slo.evidence.results", "completed claim must carry source results"),))
    claims_by_source = {row.get("source_id"): (index, row) for index, row in enumerate(claimed_results) if isinstance(row, Mapping) and isinstance(row.get("source_id"), str)}
    if len(claims_by_source) != len(claimed_results) or set(claims_by_source) != source_ids:
        raise LaunchSloEvidenceError((_issue("$.soak.source_results", "launch_slo.evidence.results", "claimed result set must exactly equal launch-critical sources"),))
    outcomes: list[LaunchSloSourceOutcome] = []
    for source_id in sorted(source_ids):
        schedule = _expected_schedule(policies[source_id], start, end)
        outcome = _recompute_source(
            source_id=source_id,
            policy=policies[source_id],
            artifact=raw_by_source[source_id][2],
            expected_schedule=schedule,
        )
        index, claim = claims_by_source[source_id]
        _assert_claim_matches_outcome(claim, outcome, index=index)
        outcomes.append(outcome)
    aggregate = bool(outcomes) and all(outcome.passed for outcome in outcomes)
    if soak.get("aggregate_passed") is not aggregate:
        raise LaunchSloEvidenceError((_issue("$.soak.aggregate_passed", "launch_slo.evidence.aggregate", "claimed aggregate result must equal the all-source recomputation"),))
    if not aggregate:
        raise LaunchSloEvidenceError((_issue("$.soak.aggregate_passed", "launch_slo.evidence.no_pass", "raw evidence does not satisfy the frozen all-source release policy"),))
    return LaunchSloEvidenceVerification(
        manifest_id=str(manifest.get("manifest_id")),
        manifest_content_sha256=str(manifest.get("content_sha256")),
        predecessor_manifest_id=str(manifest.get("supersedes_manifest_id")),
        predecessor_manifest_content_sha256=predecessor_hash,
        generation_id=generation_id,
        sources=tuple(outcomes),
        aggregate_passed=aggregate,
    )


def verify_biocatalyst_launch_slo_evidence(
    manifest: Mapping[str, Any],
    *,
    evidence_root: Path | str,
    repo_root: Path | str | None = None,
) -> LaunchSloEvidenceVerification:
    """Recompute a claimed pass from bounded local evidence or fail closed.

    This deliberately requires a completed *passed* manifest. It does not
    manufacture a result, schedule a soak, or loosen the normal generic
    contract validator. The caller must use the returned result only after
    this function has completed without an exception.
    """

    if not isinstance(manifest, Mapping) or manifest.get("state") != "soak_complete_passed":
        raise LaunchSloEvidenceError(
            (_issue("$.state", "launch_slo.evidence.claim_state", "offline pass verification accepts only an explicit soak_complete_passed claim"),)
        )
    registry = ContractRegistry(repo_root)
    # Keep the generic registry fail-closed forever: it always emits the
    # explicit unavailable-resolver issue for pass claims. This dedicated
    # entry point is the sole place that may replace that one issue, and only
    # after every other manifest/schema/semantic constraint has passed.
    base_issues = tuple(
        issue
        for issue in registry.issues("biocatalyst_launch_slo_manifest.v1", manifest)
        if issue.code != "launch_slo.trusted_evidence_verifier_unavailable"
    )
    if base_issues:
        raise LaunchSloEvidenceError(base_issues)
    trusted_now = _frozen_trusted_utc_now()
    with _OfflineEvidenceStore(evidence_root) as store:
        return _verify_biocatalyst_launch_slo_evidence_with_store(
            manifest,
            store=store,
            registry=registry,
            trusted_now=trusted_now,
        )
