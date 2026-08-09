"""Privileged deployment runtime for the B1S2b fixed-cohort collection path.

This module owns the *membership plane* of the dedicated
``macro-biocatalyst-fixed-cohort`` service identity: the immutable
digest-qualified manifest store, the single ``active.json`` pointer, the one
bounded no-follow loader that everything else must go through, and the
rotation/rollback lifecycle that binds every membership change to an immutable
``BC-O1a`` receipt.

It exists because the operator ruling recorded in
``research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md`` cleared the ClinicalTrials.gov
Record History *rights* gate while noting that no installed worker or timer
existed.  That ruling is explicit that it opens **no outcome-family clock**: a
clock over a source with no proven collection path would record "accruing since
2026-08-07" while accruing nothing.  This module builds the collection path so a
clock can later be opened through an activation receipt -- it does not open one,
enable a source, start a unit, publish a route, or touch R2.

Design commitments, each of which has a hostile test:

* Membership is only ever a validated ``ctgov_fixed_cohort.v1`` document read
  from a root-owned, digest-qualified, read-only file.  No environment variable,
  CLI argument, or caller-supplied NCT list can create, enlarge, reorder, or
  replace it.
* ``active.json`` is a real regular file holding canonical JSON plus exactly one
  LF -- never a symlink, FIFO, device, hardlink, or directory -- and its bytes
  must be byte-identical to an installed immutable manifest.
* Membership never changes in place.  A rotation installs new immutable bytes,
  re-reads them through the runtime loader, records the receipt, and only then
  atomically replaces the pointer.  Rollback uses the same validated path.
* Every failure is a distinct, bounded code.  Cleanup failures never replace the
  error that is already propagating.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

from engine.biocatalyst.fixed_cohort import (
    FIXED_COHORT_MAX_NCT_IDS,
    validate_fixed_cohort,
)
from engine.biocatalyst.operational_store import (
    OperationalStore,
    OperationalStoreError,
    OperationalStoreUnavailableError,
)
from engine.sector_intelligence.contracts import (
    ContractError,
    ContractRegistry,
    ContractValidationError,
    ValidationIssue,
    canonical_json_bytes,
    canonical_json_sha256,
)


# ---------------------------------------------------------------------------
# Frozen runtime contract (W1-A).  These paths are the deployment interface and
# are asserted by the deployment tests; they are never derived from user input.
# ---------------------------------------------------------------------------

RUNTIME_IDENTITY = "macro-biocatalyst-fixed-cohort"
RUNTIME_ENV_FILE = "/etc/macro-biocatalyst-fixed-cohort.env"
RUNTIME_CONFIG_ROOT = "/etc/macro-biocatalyst-fixed-cohort"
RUNTIME_MANIFEST_DIRNAME = "manifests"
RUNTIME_ACTIVE_POINTER_NAME = "active.json"
RUNTIME_STATE_ROOT = "/var/lib/macro-biocatalyst-fixed-cohort"
RUNTIME_RUN_ROOT = "/var/lib/macro-biocatalyst-fixed-cohort/runs"
RUNTIME_RECEIPT_ROOT = "/var/lib/macro-biocatalyst-fixed-cohort/receipts"
RUNTIME_OPERATIONAL_ROOT = "/var/lib/macro-biocatalyst-fixed-cohort/operational"

# The B0a lane this runtime must never overlap or borrow authority from.
B0A_MASKED_PATHS: tuple[str, ...] = (
    "/var/lib/macro-biocatalyst",
    "/etc/macro-biocatalyst.env",
    "/etc/macro-biocatalyst-control.env",
)

ROTATION_RECEIPT_CONTRACT_ID = "biocatalyst_manifest_rotation_receipt.v1"
ROTATION_RECEIPT_RULING_REF = "research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md"
ROTATION_RECEIPT_DIRNAME = "rotations"

# BC-O1a's record-kind enum has no membership-rotation kind, and its per-kind
# payload schemas are closed.  Rather than misrepresent a rotation as a source
# run to force it through, the FULL binding (old/new ids, both file digests, the
# named actor, and the known time) lives in an immutable content-addressed
# ``biocatalyst_manifest_rotation_receipt.v1`` file under the private receipt
# root, and BC-O1a carries the ordered ledger entry that points at it by content
# address.  ``review_decision`` is the kind that fits: a rotation is a human
# decision about membership with an immutable rationale artifact.  Adding a
# first-class ``membership_rotation_receipt`` kind to BC-O1a is the correct
# follow-up and belongs to the lane that owns operational_store.py.
ROTATION_RECORD_KIND = "review_decision"
ROTATION_DECIDED_BY_KIND = "analyst"
RUN_RECORD_KIND = "source_run_receipt"
RUN_RECEIPT_SOURCE_ID = "clinicaltrials_gov_v2"
# BC-O1a's run_state enum is {complete, incomplete, failed, skipped}; the
# transport's bounded-failure state is "quarantined".
RUN_STATE_BY_TRANSPORT_STATE = {"complete": "complete", "quarantined": "failed"}

ROTATION_KINDS = ("rotation", "rollback")

MANIFEST_MAX_BYTES = 16 * 1024
ACTIVE_POINTER_MAX_BYTES = 16 * 1024
RUN_EVIDENCE_MAX_BYTES = 64 * 1024

# Root-owned by default.  Tests inject their own uid/gid so no test ever needs
# real root or a filesystem-root write.
DEFAULT_TRUSTED_UIDS = frozenset({0})
DEFAULT_TRUSTED_GIDS = frozenset({0})

_PROHIBITED_USES: tuple[str, ...] = (
    "dynamic_cohort_expansion",
    "live_ingestion",
    "identity_mapping",
    "scoring",
    "prediction",
    "prophet_authority",
    "neural_web_authority",
    "ranking",
    "sizing",
    "alerts",
)

_COHORT_ID_RE = re.compile(r"^ctgov_fixed_cohort_[a-f0-9]{24}$", re.ASCII)
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$", re.ASCII)
_MANIFEST_NAME_RE = re.compile(
    r"^(?P<cohort_id>ctgov_fixed_cohort_[a-f0-9]{24})\.(?P<digest>[a-f0-9]{64})\.json$",
    re.ASCII,
)
_ACTOR_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$", re.ASCII)
_KNOWN_TIME_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$", re.ASCII
)
_NCT_IN_TEXT_RE = re.compile(r"NCT[0-9]{8}", re.ASCII)

# Environment names that would move membership out of the immutable manifest and
# into the process environment.  Matching is on ``_``-delimited SEGMENTS, not raw
# substrings: a substring rule refuses ``AWS_LAMBDA_FUNCTION_NAME`` because
# "FUNCTION" contains "NCT", and a fence that fires on unrelated names gets
# disabled by the first operator it inconveniences.
MEMBERSHIP_ENV_SEGMENTS: frozenset[str] = frozenset(
    {"ALLOWLIST", "MEMBER", "MEMBERS", "MEMBERSHIP", "NCT", "NCTID", "NCTIDS", "NCTS"}
)
# Multi-segment phrases that are unambiguous membership carriers.  The lane's own
# gate (``BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED``) deliberately matches none
# of these.
MEMBERSHIP_ENV_PHRASES: tuple[str, ...] = (
    "COHORT_ID",
    "COHORT_IDS",
    "COHORT_LIST",
    "COHORT_MEMBER",
    "COHORT_NCT",
    "MANIFEST_JSON",
    "NCT_ID",
    "NCT_IDS",
    "QUERY_ID",
    "STUDY_ID",
    "STUDY_IDS",
)


class FixedCohortRuntimeError(RuntimeError):
    """One bounded deployment-runtime failure with a fixed error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Canonical manifest bytes
# ---------------------------------------------------------------------------


def manifest_content_bytes(document: Mapping[str, Any]) -> bytes:
    """Return the exact on-disk bytes for one manifest: canonical JSON + one LF."""

    try:
        return canonical_json_bytes(document) + b"\n"
    except ContractError as exc:
        raise FixedCohortRuntimeError(
            "MANIFEST_NOT_CANONICAL", "manifest must be finite canonical JSON"
        ) from exc


def manifest_content_sha256(document: Mapping[str, Any]) -> str:
    """Digest the *file bytes*, not the contract's internal payload digest.

    ``cohort_payload_sha256`` hashes the document minus itself; this hashes the
    exact bytes a reader will find on disk, which is what the digest-qualified
    filename and the ``active.json`` binding commit to.
    """

    return hashlib.sha256(manifest_content_bytes(document)).hexdigest()


def manifest_filename(document: Mapping[str, Any]) -> str:
    """Return ``{cohort_id}.{content_sha256}.json`` for one validated manifest."""

    cohort_id = document.get("cohort_id")
    if not isinstance(cohort_id, str) or not _COHORT_ID_RE.fullmatch(cohort_id):
        raise FixedCohortRuntimeError(
            "MANIFEST_COHORT_ID_INVALID", "manifest cohort_id is not a canonical cohort id"
        )
    return f"{cohort_id}.{manifest_content_sha256(document)}.json"


def manifest_path_for(config_root: Path | str, document: Mapping[str, Any]) -> Path:
    return Path(config_root) / RUNTIME_MANIFEST_DIRNAME / manifest_filename(document)


def active_pointer_path_for(config_root: Path | str) -> Path:
    return Path(config_root) / RUNTIME_ACTIVE_POINTER_NAME


# ---------------------------------------------------------------------------
# The one bounded no-follow loader
# ---------------------------------------------------------------------------


def _require_safe_absolute_path(path: Path, *, code: str) -> Path:
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise FixedCohortRuntimeError(
            code, "path must be absolute and free of relative components"
        )
    return path


def _is_symlink_at(name: str, dir_fd: int) -> bool:
    """Report whether ``name`` is a symlink, without following it.

    ``O_NOFOLLOW`` reports the refusal differently per platform -- Linux raises
    ELOOP, macOS raises ENOTDIR when ``O_DIRECTORY`` is also set -- so the errno
    alone cannot name the cause.  One descriptor-relative ``lstat`` can.
    """

    try:
        return stat.S_ISLNK(os.lstat(name, dir_fd=dir_fd).st_mode)
    except OSError:
        return False


def _open_directory_chain(directory: Path) -> int:
    """Open ``directory`` component by component, refusing every symlink."""

    _require_safe_absolute_path(directory, code="MANIFEST_PATH_UNSAFE")
    if any(not hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")):
        raise FixedCohortRuntimeError(
            "MANIFEST_PLATFORM_UNSUPPORTED",
            "descriptor-relative no-follow support is required",
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current = -1
    try:
        current = os.open(os.path.sep, flags)
        for component in directory.parts[1:]:
            try:
                nxt = os.open(component, flags, dir_fd=current)
            except OSError as exc:
                code = (
                    "MANIFEST_SYMLINK_REFUSED"
                    if exc.errno == errno.ELOOP or _is_symlink_at(component, current)
                    else "MANIFEST_PARENT_UNAVAILABLE"
                )
                raise FixedCohortRuntimeError(
                    code, f"manifest parent directory is unavailable or unsafe: {exc}"
                ) from exc
            try:
                if not stat.S_ISDIR(os.fstat(nxt).st_mode):
                    raise FixedCohortRuntimeError(
                        "MANIFEST_PARENT_UNAVAILABLE",
                        "every manifest parent component must be a real directory",
                    )
            except BaseException:
                os.close(nxt)
                raise
            os.close(current)
            current = nxt
        return current
    except BaseException:
        if current >= 0:
            os.close(current)
        raise


def _check_ownership_and_mode(
    info: os.stat_result,
    *,
    trusted_uids: Iterable[int],
    trusted_gids: Iterable[int],
    what: str,
) -> None:
    if info.st_uid not in set(trusted_uids):
        raise FixedCohortRuntimeError(
            "MANIFEST_OWNER_UNSAFE", f"{what} is not owned by a trusted uid"
        )
    if info.st_gid not in set(trusted_gids):
        raise FixedCohortRuntimeError(
            "MANIFEST_OWNER_UNSAFE", f"{what} is not owned by a trusted gid"
        )
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o022:
        raise FixedCohortRuntimeError(
            "MANIFEST_MODE_UNSAFE", f"{what} must not be group or world writable"
        )
    if mode & 0o7000:
        raise FixedCohortRuntimeError(
            "MANIFEST_MODE_UNSAFE", f"{what} must not carry setuid, setgid, or sticky bits"
        )


def _stat_signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def read_trusted_file(
    path: Path | str,
    *,
    trusted_uids: Iterable[int] = DEFAULT_TRUSTED_UIDS,
    trusted_gids: Iterable[int] = DEFAULT_TRUSTED_GIDS,
    max_bytes: int = MANIFEST_MAX_BYTES,
) -> bytes:
    """Read one small, root-owned, single-link regular file with no symlink step.

    ``O_NOFOLLOW`` defeats a symlinked final component, ``O_NONBLOCK`` keeps a
    FIFO from hanging the runtime, ``S_ISREG`` refuses FIFOs and device nodes,
    ``st_nlink == 1`` refuses a hardlinked alias, and the before/after stat
    signature refuses a path swapped underneath the descriptor.
    """

    target = _require_safe_absolute_path(Path(path), code="MANIFEST_PATH_UNSAFE")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise FixedCohortRuntimeError(
            "MANIFEST_LIMIT_INVALID", "max_bytes must be a positive integer"
        )
    parent_fd = _open_directory_chain(target.parent)
    descriptor = -1
    try:
        _check_ownership_and_mode(
            os.fstat(parent_fd),
            trusted_uids=trusted_uids,
            trusted_gids=trusted_gids,
            what="the manifest directory",
        )
        try:
            descriptor = os.open(
                target.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            code = (
                "MANIFEST_SYMLINK_REFUSED"
                if exc.errno == errno.ELOOP or _is_symlink_at(target.name, parent_fd)
                else "MANIFEST_UNREADABLE"
            )
            raise FixedCohortRuntimeError(
                code, f"manifest cannot be safely opened: {exc}"
            ) from exc
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise FixedCohortRuntimeError(
                "MANIFEST_NOT_REGULAR_FILE",
                "manifest must be a regular file, never a FIFO, device, or directory",
            )
        if before.st_nlink != 1:
            raise FixedCohortRuntimeError(
                "MANIFEST_HARDLINKED", "manifest must be a single-link regular file"
            )
        _check_ownership_and_mode(
            before,
            trusted_uids=trusted_uids,
            trusted_gids=trusted_gids,
            what="the manifest file",
        )
        if before.st_size < 1 or before.st_size > max_bytes:
            raise FixedCohortRuntimeError(
                "MANIFEST_SIZE_OUT_OF_BOUNDS",
                f"manifest must be 1-{max_bytes} bytes",
            )
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                raise FixedCohortRuntimeError(
                    "MANIFEST_CHANGED_DURING_READ", "manifest shrank while being read"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if _stat_signature(before) != _stat_signature(os.fstat(descriptor)):
            raise FixedCohortRuntimeError(
                "MANIFEST_CHANGED_DURING_READ", "manifest changed while being read"
            )
        return b"".join(chunks)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key {key!r}")
        payload[key] = value
    return payload


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-standard JSON constant {token!r}")


def parse_manifest_bytes(raw: bytes) -> dict[str, Any]:
    """Parse manifest bytes, refusing anything that is not canonical JSON + LF."""

    if not isinstance(raw, bytes):
        raise FixedCohortRuntimeError(
            "MANIFEST_NONCANONICAL_BYTES", "manifest bytes must be raw bytes"
        )
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise FixedCohortRuntimeError(
            "MANIFEST_NONCANONICAL_BYTES", f"manifest is not bounded JSON: {exc}"
        ) from exc
    if type(parsed) is not dict:
        raise FixedCohortRuntimeError(
            "MANIFEST_NONCANONICAL_BYTES", "manifest must encode a JSON object"
        )
    if raw != manifest_content_bytes(parsed):
        # Re-ordered keys, extra whitespace, a missing terminal LF, or a second
        # LF all change the file digest, so none of them may be tolerated.
        raise FixedCohortRuntimeError(
            "MANIFEST_NONCANONICAL_BYTES",
            "manifest bytes must be canonical JSON followed by exactly one LF",
        )
    return parsed


@dataclass(frozen=True)
class LoadedManifest:
    """One detached, contract-valid manifest and the exact bytes it came from."""

    path: Path
    cohort_id: str
    content_sha256: str
    raw_bytes: bytes
    document: dict[str, Any]

    @property
    def nct_ids(self) -> tuple[str, ...]:
        return tuple(self.document["nct_ids"])


def validate_manifest_document(
    document: Mapping[str, Any], *, repo_root: Path | str | None = None
) -> None:
    """Fail closed unless the manifest is a valid ``ctgov_fixed_cohort.v1``.

    That contract already binds the source registry reference, the exact
    registry bytes digest, the cohort identity digest, and the self digest, so
    a hand-edited membership list cannot survive this call.
    """

    try:
        validate_fixed_cohort(document, repo_root=repo_root)
    except (ContractValidationError, ContractError) as exc:
        raise FixedCohortRuntimeError(
            "MANIFEST_CONTRACT_INVALID", f"manifest failed its contract: {exc}"
        ) from exc
    nct_ids = document.get("nct_ids")
    if not isinstance(nct_ids, list) or not 1 <= len(nct_ids) <= FIXED_COHORT_MAX_NCT_IDS:
        raise FixedCohortRuntimeError(
            "MANIFEST_CONTRACT_INVALID", "manifest membership is outside the reviewed bounds"
        )


def load_manifest_file(
    path: Path | str,
    *,
    trusted_uids: Iterable[int] = DEFAULT_TRUSTED_UIDS,
    trusted_gids: Iterable[int] = DEFAULT_TRUSTED_GIDS,
    repo_root: Path | str | None = None,
    require_digest_qualified_name: bool = True,
) -> LoadedManifest:
    """Load one immutable manifest through every deployment check, in order."""

    target = Path(path)
    raw = read_trusted_file(
        target,
        trusted_uids=trusted_uids,
        trusted_gids=trusted_gids,
        max_bytes=MANIFEST_MAX_BYTES,
    )
    document = parse_manifest_bytes(raw)
    validate_manifest_document(document, repo_root=repo_root)
    digest = hashlib.sha256(raw).hexdigest()
    cohort_id = document["cohort_id"]
    if require_digest_qualified_name:
        match = _MANIFEST_NAME_RE.fullmatch(target.name)
        if match is None:
            raise FixedCohortRuntimeError(
                "MANIFEST_NAME_NOT_DIGEST_QUALIFIED",
                "immutable manifests must be named {cohort_id}.{content_sha256}.json",
            )
        if match.group("cohort_id") != cohort_id or match.group("digest") != digest:
            raise FixedCohortRuntimeError(
                "MANIFEST_DIGEST_MISMATCH",
                "manifest filename does not bind its own cohort id and content digest",
            )
    return LoadedManifest(
        path=target,
        cohort_id=cohort_id,
        content_sha256=digest,
        raw_bytes=raw,
        document=document,
    )


def load_active_manifest(
    config_root: Path | str,
    *,
    trusted_uids: Iterable[int] = DEFAULT_TRUSTED_UIDS,
    trusted_gids: Iterable[int] = DEFAULT_TRUSTED_GIDS,
    repo_root: Path | str | None = None,
) -> LoadedManifest:
    """Load ``active.json`` once and prove it names an installed immutable manifest.

    The pointer is a *copy* of validated bytes, never a symlink, so the loader
    additionally re-reads the digest-qualified immutable manifest and requires
    byte equality.  A pointer edited in place therefore fails closed even if the
    edit happens to remain contract-valid.
    """

    root = Path(config_root)
    pointer = active_pointer_path_for(root)
    raw = read_trusted_file(
        pointer,
        trusted_uids=trusted_uids,
        trusted_gids=trusted_gids,
        max_bytes=ACTIVE_POINTER_MAX_BYTES,
    )
    document = parse_manifest_bytes(raw)
    validate_manifest_document(document, repo_root=repo_root)
    digest = hashlib.sha256(raw).hexdigest()
    # The backing read is the enforcement, not a formality: the path is derived
    # from the pointer's own digest, and ``load_manifest_file`` requires that
    # file to self-bind the same digest.  A pointer edited in place therefore
    # names a manifest that was never installed, and fails closed.
    immutable = root / RUNTIME_MANIFEST_DIRNAME / f"{document['cohort_id']}.{digest}.json"
    load_manifest_file(
        immutable,
        trusted_uids=trusted_uids,
        trusted_gids=trusted_gids,
        repo_root=repo_root,
    )
    return LoadedManifest(
        path=pointer,
        cohort_id=document["cohort_id"],
        content_sha256=digest,
        raw_bytes=raw,
        document=document,
    )


# ---------------------------------------------------------------------------
# Durable writes
# ---------------------------------------------------------------------------


def atomic_write_bytes(path: Path | str, payload: bytes, *, mode: int = 0o444) -> None:
    """Create or replace one file without ever exposing partial bytes.

    A crash or an ``ENOSPC`` between the temp write, the fsync, and the rename
    leaves the destination either absent or holding its previous complete bytes.
    The temp file is always unlinked, and that cleanup never replaces the error
    that is already propagating.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        code = "RUNTIME_DISK_FULL" if exc.errno == errno.ENOSPC else "RUNTIME_WRITE_FAILED"
        raise FixedCohortRuntimeError(code, f"durable write failed: {exc}") from exc
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        except OSError:
            # Cleanup is strictly less informative than whatever is propagating.
            pass


def install_manifest(
    document: Mapping[str, Any],
    *,
    config_root: Path | str,
    trusted_uids: Iterable[int] = DEFAULT_TRUSTED_UIDS,
    trusted_gids: Iterable[int] = DEFAULT_TRUSTED_GIDS,
    repo_root: Path | str | None = None,
) -> Path:
    """Install one immutable, read-only, digest-qualified manifest.

    Re-installing byte-identical bytes is a no-op.  Different bytes at the same
    digest-qualified path is impossible by construction, and different bytes at
    an existing path is a hard conflict rather than an overwrite.
    """

    validate_manifest_document(document, repo_root=repo_root)
    payload = manifest_content_bytes(document)
    destination = manifest_path_for(config_root, document)
    if destination.exists():
        existing = read_trusted_file(
            destination,
            trusted_uids=trusted_uids,
            trusted_gids=trusted_gids,
            max_bytes=MANIFEST_MAX_BYTES,
        )
        if existing != payload:
            raise FixedCohortRuntimeError(
                "MANIFEST_IMMUTABLE_COLLISION",
                "a different manifest already occupies this digest-qualified path",
            )
        return destination
    atomic_write_bytes(destination, payload, mode=0o444)
    return destination


# ---------------------------------------------------------------------------
# Rotation receipt
# ---------------------------------------------------------------------------


def _rotation_identity_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in document.items()
        if key != "receipt_payload_sha256"
    }


def manifest_rotation_receipt_semantic_issues(
    document: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Return deterministic semantic failures for one rotation receipt."""

    if not isinstance(document, Mapping):
        return [_issue("$", "manifest_rotation.document", "receipt must be a JSON object")]
    issues: list[ValidationIssue] = []
    kind = document.get("rotation_kind")
    previous_id = document.get("previous_cohort_id")
    previous_digest = document.get("previous_manifest_sha256")
    if (previous_id is None) != (previous_digest is None):
        issues.append(
            _issue(
                "$.previous_cohort_id",
                "manifest_rotation.previous_pair",
                "previous cohort id and previous manifest digest must both be present or both be null",
            )
        )
    if kind == "rollback" and previous_id is None:
        issues.append(
            _issue(
                "$.rotation_kind",
                "manifest_rotation.rollback_requires_previous",
                "a rollback must name the membership it is rolling back from",
            )
        )
    if (
        document.get("next_cohort_id") == previous_id
        and document.get("next_manifest_sha256") == previous_digest
    ):
        issues.append(
            _issue(
                "$.next_manifest_sha256",
                "manifest_rotation.no_op",
                "a rotation receipt must record an actual membership change",
            )
        )
    manifest_path = document.get("manifest_path")
    next_id = document.get("next_cohort_id")
    next_digest = document.get("next_manifest_sha256")
    if (
        isinstance(manifest_path, str)
        and isinstance(next_id, str)
        and isinstance(next_digest, str)
        and not manifest_path.endswith(f"/{next_id}.{next_digest}.json")
    ):
        issues.append(
            _issue(
                "$.manifest_path",
                "manifest_rotation.path_binding",
                "manifest_path must be the digest-qualified path of the incoming manifest",
            )
        )
    try:
        expected = canonical_json_sha256(_rotation_identity_payload(document))
    except ContractError:
        return sorted(
            set(
                issues
                + [
                    _issue(
                        "$",
                        "manifest_rotation.canonical_payload",
                        "receipt must be finite canonical JSON",
                    )
                ]
            )
        )
    if document.get("receipt_payload_sha256") != expected:
        issues.append(
            _issue(
                "$.receipt_payload_sha256",
                "manifest_rotation.hash",
                "receipt_payload_sha256 must hash the canonical payload excluding only itself",
            )
        )
    return sorted(set(issues))


def validate_manifest_rotation_receipt(
    document: Any, *, repo_root: Path | str | None = None
) -> None:
    """Fail closed unless schema and rotation semantics both hold."""

    registry = ContractRegistry(repo_root)
    schema_issues = list(registry.issues(ROTATION_RECEIPT_CONTRACT_ID, document))
    semantic_issues = (
        manifest_rotation_receipt_semantic_issues(document)
        if isinstance(document, Mapping)
        else [_issue("$", "manifest_rotation.document", "receipt must be a JSON object")]
    )
    issues = tuple(sorted(set(schema_issues + semantic_issues)))
    if issues:
        raise ContractValidationError(ROTATION_RECEIPT_CONTRACT_ID, issues)


def build_manifest_rotation_receipt(
    *,
    rotation_kind: str,
    previous: LoadedManifest | None,
    incoming: LoadedManifest,
    config_root: Path | str,
    actor: str,
    known_time: str,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build and validate one rotation receipt without persisting it."""

    if rotation_kind not in ROTATION_KINDS:
        raise FixedCohortRuntimeError(
            "ROTATION_KIND_INVALID", f"rotation_kind must be one of {list(ROTATION_KINDS)}"
        )
    if not isinstance(actor, str) or not _ACTOR_RE.fullmatch(actor):
        raise FixedCohortRuntimeError(
            "ROTATION_ACTOR_INVALID", "a rotation must name a bounded human actor"
        )
    if not isinstance(known_time, str) or not _KNOWN_TIME_RE.fullmatch(known_time):
        raise FixedCohortRuntimeError(
            "ROTATION_KNOWN_TIME_INVALID", "known_time must be a microsecond UTC Z stamp"
        )
    root = Path(config_root)
    document: dict[str, Any] = {
        "contract_id": ROTATION_RECEIPT_CONTRACT_ID,
        "schema_version": "1.0.0",
        "rotation_kind": rotation_kind,
        "previous_cohort_id": previous.cohort_id if previous is not None else None,
        "previous_manifest_sha256": (
            previous.content_sha256 if previous is not None else None
        ),
        "next_cohort_id": incoming.cohort_id,
        "next_manifest_sha256": incoming.content_sha256,
        "actor": actor,
        "known_time": known_time,
        "config_root": str(root),
        "active_pointer_path": str(active_pointer_path_for(root)),
        "manifest_path": str(incoming.path),
        "membership_authority": "fixed_cohort_only",
        "authority": "facts_and_context_only",
        "ruling_ref": ROTATION_RECEIPT_RULING_REF,
        "prohibited_uses": list(_PROHIBITED_USES),
        "hash_scope": "canonical_payload_excluding_receipt_payload_sha256",
    }
    document["receipt_payload_sha256"] = canonical_json_sha256(
        _rotation_identity_payload(document)
    )
    validate_manifest_rotation_receipt(document, repo_root=repo_root)
    return document


def rotation_receipt_id(receipt: Mapping[str, Any]) -> str:
    """Content-address one rotation receipt.

    An A->B->A->B sequence produces four distinct ids because ``known_time`` is
    part of the hashed payload, while replaying the identical rotation is a true
    no-op rather than a conflict.
    """

    digest = receipt.get("receipt_payload_sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise FixedCohortRuntimeError(
            "ROTATION_RECEIPT_INVALID", "rotation receipt carries no payload digest"
        )
    return f"fixed_cohort_rotation.{digest[:32]}"


def rotation_idempotency_key(receipt: Mapping[str, Any]) -> str:
    """Derive the BC-O1a idempotency key for one rotation receipt."""

    return rotation_receipt_id(receipt)


def rotation_receipt_path(receipt_root: Path | str, receipt: Mapping[str, Any]) -> Path:
    """Return the immutable, date-partitioned path for one rotation receipt."""

    known_time = receipt.get("known_time")
    if not isinstance(known_time, str) or not _KNOWN_TIME_RE.fullmatch(known_time):
        raise FixedCohortRuntimeError(
            "ROTATION_KNOWN_TIME_INVALID", "known_time must be a microsecond UTC Z stamp"
        )
    return (
        Path(receipt_root)
        / ROTATION_RECEIPT_DIRNAME
        / known_time[0:4]
        / known_time[5:7]
        / f"{rotation_receipt_id(receipt)}.json"
    )


def rotation_ledger_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Project one rotation receipt onto the BC-O1a ``review_decision`` shape.

    The ledger entry is an ordered, append-only index; ``rationale_ref`` is the
    content address of the immutable receipt that carries the full binding, so
    nothing is lost, only relocated to the artifact BC-O1a can actually hold.
    """

    return {
        "decision_id": rotation_receipt_id(receipt),
        "queue_item_id": f"fixed_cohort_membership.{receipt['next_cohort_id']}",
        "decision_state": "accepted",
        "decided_by_kind": ROTATION_DECIDED_BY_KIND,
        "rationale_ref": f"internal:{rotation_receipt_id(receipt)}",
    }


# ---------------------------------------------------------------------------
# Operational store availability and the rotation lifecycle
# ---------------------------------------------------------------------------


def require_operational_store_available(store: OperationalStore) -> None:
    """Fail closed before any collection when BC-O1a cannot accept a receipt.

    A run that could collect but could not record would leave source traffic
    with no evidence, which is precisely the fabrication this program refuses.
    """

    try:
        store.read(RUN_RECORD_KIND, limit=1)
    except (OperationalStoreUnavailableError, OperationalStoreError) as exc:
        raise FixedCohortRuntimeError(
            "OPERATIONAL_STORE_UNAVAILABLE",
            f"BC-O1a receipt store is unavailable: {getattr(exc, 'code', exc)}",
        ) from exc
    except OSError as exc:
        raise FixedCohortRuntimeError(
            "OPERATIONAL_STORE_UNAVAILABLE", f"BC-O1a receipt store is unavailable: {exc}"
        ) from exc
    if not os.access(store.state_root, os.W_OK | os.X_OK):
        raise FixedCohortRuntimeError(
            "OPERATIONAL_STORE_UNAVAILABLE", "BC-O1a receipt store is not writable"
        )


class _RotationLock:
    """One exclusive, self-cleaning rotation lock.

    Two concurrent rotations would race the pointer; the loser is refused with a
    distinct code rather than allowed to interleave.  A run that loads the
    pointer while a rotation is in flight is unaffected: it detaches complete
    bytes, and the swap is atomic.
    """

    def __init__(self, config_root: Path | str) -> None:
        self._path = Path(config_root) / ".rotation.lock"
        self._descriptor = -1

    def __enter__(self) -> "_RotationLock":
        try:
            self._descriptor = os.open(
                self._path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
            )
        except FileExistsError as exc:
            raise FixedCohortRuntimeError(
                "ROTATION_IN_PROGRESS", "another rotation holds the membership lock"
            ) from exc
        except OSError as exc:
            raise FixedCohortRuntimeError(
                "ROTATION_LOCK_UNAVAILABLE", f"rotation lock cannot be taken: {exc}"
            ) from exc
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._descriptor >= 0:
            try:
                os.close(self._descriptor)
            except OSError:
                pass
        try:
            os.unlink(self._path)
        except OSError:
            # Releasing the lock must never replace the primary error.
            pass


def rotate_active_manifest(
    *,
    config_root: Path | str,
    receipt_root: Path | str,
    document: Mapping[str, Any],
    actor: str,
    known_time: str,
    store: OperationalStore,
    rotation_kind: str = "rotation",
    trusted_uids: Iterable[int] = DEFAULT_TRUSTED_UIDS,
    trusted_gids: Iterable[int] = DEFAULT_TRUSTED_GIDS,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Rotate (or roll back) the active membership through the validated path.

    Order is load-bearing and matches the frozen W1-A lifecycle:

    1. install the new immutable versioned manifest (a rollback must already
       have one, and never installs new bytes);
    2. validate and byte-read it back *under the runtime loader*;
    3. record the rotation receipt binding old/new ids, digests, actor, and
       known time -- as an immutable content-addressed file under the receipt
       root, plus the BC-O1a ledger entry that points at it.  If either refuses,
       nothing has moved;
    4. atomically replace ``active.json`` with the exact validated bytes and
       read it back through the same loader;
    5. leave the prior immutable manifest and its receipt intact.

    Membership is never edited in place, on either direction of travel.
    """

    root = Path(config_root)
    receipts = Path(receipt_root)
    if rotation_kind not in ROTATION_KINDS:
        raise FixedCohortRuntimeError(
            "ROTATION_KIND_INVALID", f"rotation_kind must be one of {list(ROTATION_KINDS)}"
        )
    if receipts.is_symlink() or not receipts.is_dir():
        raise FixedCohortRuntimeError(
            "RECEIPT_ROOT_UNAVAILABLE", f"receipt root must be a real directory: {receipts}"
        )
    require_operational_store_available(store)
    with _RotationLock(root):
        pointer = active_pointer_path_for(root)
        previous: LoadedManifest | None = None
        if pointer.exists() or pointer.is_symlink():
            previous = load_active_manifest(
                root,
                trusted_uids=trusted_uids,
                trusted_gids=trusted_gids,
                repo_root=repo_root,
            )

        # 1 + 2: install (or require) the immutable manifest, then re-read it
        # through the loader every runtime read will use.
        target = manifest_path_for(root, document)
        if rotation_kind == "rollback":
            if not target.exists():
                raise FixedCohortRuntimeError(
                    "ROLLBACK_TARGET_NOT_INSTALLED",
                    "a rollback may only select an already-installed immutable manifest",
                )
        else:
            install_manifest(
                document,
                config_root=root,
                trusted_uids=trusted_uids,
                trusted_gids=trusted_gids,
                repo_root=repo_root,
            )
        incoming = load_manifest_file(
            target,
            trusted_uids=trusted_uids,
            trusted_gids=trusted_gids,
            repo_root=repo_root,
        )

        # 3: the receipt precedes the pointer move, so no membership can change
        # without a durable, attributed record of who changed it and when.
        try:
            receipt = build_manifest_rotation_receipt(
                rotation_kind=rotation_kind,
                previous=previous,
                incoming=incoming,
                config_root=root,
                actor=actor,
                known_time=known_time,
                repo_root=repo_root,
            )
        except (ContractValidationError, ContractError) as exc:
            raise FixedCohortRuntimeError(
                "ROTATION_RECEIPT_INVALID", f"rotation receipt failed its contract: {exc}"
            ) from exc
        receipt_path = rotation_receipt_path(receipts, receipt)
        receipt_bytes = canonical_json_bytes(receipt) + b"\n"
        if receipt_path.exists():
            existing = read_trusted_file(
                receipt_path,
                trusted_uids=trusted_uids,
                trusted_gids=trusted_gids,
                max_bytes=MANIFEST_MAX_BYTES,
            )
            if existing != receipt_bytes:
                raise FixedCohortRuntimeError(
                    "ROTATION_RECEIPT_COLLISION",
                    "a different rotation receipt already occupies this content address",
                )
        else:
            atomic_write_bytes(receipt_path, receipt_bytes, mode=0o400)
            if receipt_path.read_bytes() != receipt_bytes:
                raise FixedCohortRuntimeError(
                    "ROTATION_RECEIPT_READBACK_FAILED",
                    "the rotation receipt did not read back as written",
                )
        try:
            store.append(
                ROTATION_RECORD_KIND,
                rotation_ledger_payload(receipt),
                idempotency_key=rotation_idempotency_key(receipt),
                # The rotation's own known time, not the process wall clock, so
                # a replayed rotation is a no-op rather than a key conflict.
                recorded_at=known_time,
            )
        except (OperationalStoreError, OSError) as exc:
            raise FixedCohortRuntimeError(
                "ROTATION_RECEIPT_REFUSED",
                f"BC-O1a refused the rotation ledger entry: {getattr(exc, 'code', exc)}",
            ) from exc

        # 4: atomic replace with the exact validated bytes, then prove it.
        atomic_write_bytes(pointer, incoming.raw_bytes, mode=0o444)
        readback = load_active_manifest(
            root,
            trusted_uids=trusted_uids,
            trusted_gids=trusted_gids,
            repo_root=repo_root,
        )
        if (
            readback.raw_bytes != incoming.raw_bytes
            or readback.content_sha256 != incoming.content_sha256
        ):
            raise FixedCohortRuntimeError(
                "ACTIVE_POINTER_READBACK_FAILED",
                "active.json did not read back as the exact validated manifest bytes",
            )
        return receipt


def active_pointer_matches_receipt(
    config_root: Path | str,
    receipt: Mapping[str, Any],
    *,
    trusted_uids: Iterable[int] = DEFAULT_TRUSTED_UIDS,
    trusted_gids: Iterable[int] = DEFAULT_TRUSTED_GIDS,
    repo_root: Path | str | None = None,
) -> bool:
    """Report whether the live pointer actually reflects a recorded rotation.

    A receipt is written before the swap, so an interrupted rotation leaves a
    receipt whose ``next_manifest_sha256`` the pointer does not carry.  That
    mismatch is detectable rather than silent, which is why this helper exists.
    """

    loaded = load_active_manifest(
        config_root,
        trusted_uids=trusted_uids,
        trusted_gids=trusted_gids,
        repo_root=repo_root,
    )
    return (
        loaded.cohort_id == receipt.get("next_cohort_id")
        and loaded.content_sha256 == receipt.get("next_manifest_sha256")
    )


# ---------------------------------------------------------------------------
# Environment fence
# ---------------------------------------------------------------------------


def membership_environment_offences(environ: Mapping[str, str]) -> tuple[str, ...]:
    """Return the environment names that try to carry cohort membership."""

    if not isinstance(environ, Mapping):
        raise FixedCohortRuntimeError(
            "ENVIRONMENT_INVALID", "environment must be a mapping of names to values"
        )
    offences: list[str] = []
    for name, value in environ.items():
        if not isinstance(name, str):
            offences.append(repr(name))
            continue
        upper = name.upper()
        if any(phrase in upper for phrase in MEMBERSHIP_ENV_PHRASES):
            offences.append(name)
            continue
        if MEMBERSHIP_ENV_SEGMENTS & set(upper.split("_")):
            offences.append(name)
            continue
        if isinstance(value, str) and _NCT_IN_TEXT_RE.search(value):
            offences.append(name)
    return tuple(sorted(set(offences)))


def assert_environment_carries_no_membership(environ: Mapping[str, str]) -> None:
    """Fail closed when the environment attempts to alter cohort membership.

    ``config/biocatalyst_sources.yml`` plus the validated manifest are the sole
    membership authority.  An environment that merely *mentions* an NCT id is
    refused rather than ignored, because a silently ignored override is
    indistinguishable to an operator from one that worked.
    """

    offences = membership_environment_offences(environ)
    if offences:
        raise FixedCohortRuntimeError(
            "ENVIRONMENT_MEMBERSHIP_ATTEMPT",
            "membership may never come from the environment: " + ", ".join(offences),
        )


__all__ = [
    "B0A_MASKED_PATHS",
    "DEFAULT_TRUSTED_GIDS",
    "DEFAULT_TRUSTED_UIDS",
    "FixedCohortRuntimeError",
    "LoadedManifest",
    "MEMBERSHIP_ENV_PHRASES",
    "MEMBERSHIP_ENV_SEGMENTS",
    "ROTATION_DECIDED_BY_KIND",
    "ROTATION_KINDS",
    "ROTATION_RECEIPT_CONTRACT_ID",
    "ROTATION_RECEIPT_DIRNAME",
    "ROTATION_RECEIPT_RULING_REF",
    "ROTATION_RECORD_KIND",
    "RUN_RECEIPT_SOURCE_ID",
    "RUN_STATE_BY_TRANSPORT_STATE",
    "RUNTIME_ACTIVE_POINTER_NAME",
    "RUNTIME_CONFIG_ROOT",
    "RUNTIME_ENV_FILE",
    "RUNTIME_IDENTITY",
    "RUNTIME_MANIFEST_DIRNAME",
    "RUNTIME_OPERATIONAL_ROOT",
    "RUNTIME_RECEIPT_ROOT",
    "RUNTIME_RUN_ROOT",
    "RUNTIME_STATE_ROOT",
    "RUN_RECORD_KIND",
    "active_pointer_matches_receipt",
    "active_pointer_path_for",
    "assert_environment_carries_no_membership",
    "atomic_write_bytes",
    "build_manifest_rotation_receipt",
    "install_manifest",
    "load_active_manifest",
    "load_manifest_file",
    "manifest_content_bytes",
    "manifest_content_sha256",
    "manifest_filename",
    "manifest_path_for",
    "manifest_rotation_receipt_semantic_issues",
    "membership_environment_offences",
    "parse_manifest_bytes",
    "read_trusted_file",
    "require_operational_store_available",
    "rotate_active_manifest",
    "rotation_idempotency_key",
    "rotation_ledger_payload",
    "rotation_receipt_id",
    "rotation_receipt_path",
    "utc_now",
    "validate_manifest_document",
    "validate_manifest_rotation_receipt",
]
