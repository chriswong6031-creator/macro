"""Capture-only attestation for the frozen MastermindX selector registration.

The frozen sparse-selector registration is globally inactive and requires a new
governed implementation before it can emit a candidate.  This module therefore
does one thing: during an exact five-minute capture slot, attest that the
dedicated operational checkout still contains that exact registration and the
private NBBO cohort prerequisite.  It does not inspect campaign data, infer a
candidate or event, enroll a contract, or grant authority.

Static registration bytes never cover a slot by themselves.  A successful
source object exists only after this process verifies one externally reviewed,
exact release and tree, every repository byte that can affect this receipt, and
the causal current-slot clocks while holding the shared install lock.

This is not a signature or an independent proof that the host occurrence
happened.  Durable occurrence requires the future launcher to append the exact
canonical bytes to the private evidence store and bind its own host receipt.

Future integration hard dependencies are machine-readable below.  In
particular, an installer must hold ``_exclusive_install_lock`` across its whole
adjacent checkout swap, while the launcher must supply a literal reviewed
``CaptureReleasePolicy`` rather than deriving one from the installed checkout.
"""

from __future__ import annotations

import copy
import errno
import fcntl
import json
import os
import re
import stat
import subprocess
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha1, sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo

import engine as _engine_package
import lib as _lib_package
from engine import session_digest as _session_digest
from lib import nyse_calendar as _nyse_calendar

SOURCE_SCHEMA = "options.mastermindx_selector_capture_attestation/v1"
AUTHENTICATION_BASIS = (
    "reviewed_exact_release_tree_owner_bound_timed_lock_triple_snapshot/v2"
)
MODE = "capture_only_registration_inactive"
COMPARISON_SYSTEM = "mastermindx"
DISPOSITION = "registered_selector_inactive"
CAPTURE_CADENCE_SECONDS = 300

OPS_CHECKOUT_ROOT = Path("/Users/chriswong/options-nbbo-ops-wt")
MODULE_RELATIVE_PATH = Path("engine/options_mastermindx_capture.py")
MODULE_PATH = Path(__file__).resolve()
ENGINE_INIT_RELATIVE_PATH = Path("engine/__init__.py")
ENGINE_INIT_PATH = Path(_engine_package.__file__).resolve()
SCHEMA_RELATIVE_PATH = Path(
    "contracts/options/options.mastermindx_selector_capture_attestation.v1.schema.json"
)
SCHEMA_PATH = Path(__file__).resolve().parents[1] / SCHEMA_RELATIVE_PATH
SESSION_DIGEST_RELATIVE_PATH = Path("engine/session_digest.py")
SESSION_DIGEST_PATH = Path(_session_digest.__file__).resolve()
NYSE_CALENDAR_RELATIVE_PATH = Path("lib/nyse_calendar.py")
NYSE_CALENDAR_PATH = Path(_nyse_calendar.__file__).resolve()
LIB_INIT_RELATIVE_PATH = Path("lib/__init__.py")
LIB_INIT_PATH = Path(_lib_package.__file__).resolve()
SELECTOR_RECEIPT_RELATIVE_PATH = Path(
    "research/options_estate/sparse_selector_preregistration_receipt_v1.json"
)
INSTALL_LOCK_PATH = Path(
    "/Users/chriswong/.mastermind_private/options_nbbo_cohort_v1/.install.lock"
)
GIT_BINARY = Path("/usr/bin/git")
MAX_ATTESTED_FILE_BYTES = 2 * 1024 * 1024
INSTALL_LOCK_TIMEOUT_SECONDS = 2.0
INSTALL_LOCK_POLL_SECONDS = 0.01
MAX_IGNORED_CACHE_ENTRIES = 256
MAX_IGNORED_CACHE_FILE_BYTES = 2 * 1024 * 1024
MAX_IGNORED_CACHE_TOTAL_BYTES = 16 * 1024 * 1024
SAFE_IGNORED_ROOT_CACHE = Path(".pytest_cache")
MAX_TRACKED_TREE_FILES = 100_000
MAX_TRACKED_TREE_BYTES = 8 * 1024 * 1024 * 1024
MAX_TRACKED_FILE_BYTES = 512 * 1024 * 1024
SAFE_IGNORED_PYTEST_CACHE_FILES = frozenset(
    {
        Path(".pytest_cache/.gitignore"),
        Path(".pytest_cache/CACHEDIR.TAG"),
        Path(".pytest_cache/README.md"),
        Path(".pytest_cache/v/cache/lastfailed"),
        Path(".pytest_cache/v/cache/nodeids"),
        Path(".pytest_cache/v/cache/stepwise"),
    }
)

SELECTOR_MERGE_SHA = "6ba8e7f368a1674b7114d5bd867aa721bd0472f8"
NBBO_COHORT_MERGE_SHA = "9056d844667ed1a293b29c6deec99521e5f58f7a"
SELECTOR_EFFECTIVE_FREEZE_AT = "2026-08-12T13:30:00Z"
SELECTOR_RECEIPT_SCHEMA = "options.sparse_selector_activation_receipt/v1"
SELECTOR_RECEIPT_ID = (
    "ossr_9309cd0e7a70c28c0f0fd36ba74330bcc4dd4abcaf87c7f41436162b30d1e838"
)
SELECTOR_RECEIPT_SHA256 = (
    "49d0fa742383e86d8907fec60e47d733788d8879e394d85c8e6a6ac0d3f1a878"
)
SELECTOR_RECEIPT_BYTES = 16_050
SELECTOR_RULE_SHA256 = (
    "a98d3b92e1ebe069c141d5f79ee9260eeb2b8eeee4f90f574ef0069c062ad20b"
)
SELECTOR_RULE_ID = "sparse_exact_option_truth_gate/v1"
ACTIVATION_MANIFEST_ID = (
    "ossm_da48d6a53a3cbdd2f7baf1f53b6f454cc4503608cb12c49a8e02e263766d9695"
)

ET = ZoneInfo("America/New_York")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

FALSE_AUTHORITY: Mapping[str, bool] = MappingProxyType(
    {
        "may_originate_signal": False,
        "may_score": False,
        "may_rank": False,
        "may_select": False,
        "may_issue": False,
        "may_size": False,
        "may_trade": False,
        "may_publish_pick": False,
        "may_train_prophet": False,
        "may_feed_neural_web": False,
        "may_claim_completion": False,
    }
)

CLAIM_BOUNDARY: Mapping[str, bool] = MappingProxyType(
    {
        "candidate_source_observed": False,
        "current_candidate_absence_observed": False,
        "candidate_event_inference": False,
        "event_enrollment": False,
        "public_output": False,
        "prospective_selector_evidence": False,
        "satisfies_sparse_gate": False,
        "static_registration_is_slot_coverage": False,
        "trade_or_return_claim": False,
        "training_eligible": False,
    }
)

OBSERVATION: Mapping[str, Any] = MappingProxyType(
    {
        "basis": "registration_inactive_candidate_source_not_examined",
        "candidate_source_examined": False,
        "candidate_count_known": False,
        "candidate_count": None,
        "candidate_events_inferred": False,
        "event_producer_armed": False,
        "emitted_enrollment_event_count": 0,
        "emitted_enrollment_event_ids": (),
    }
)

OCCURRENCE_TRUST: Mapping[str, Any] = MappingProxyType(
    {
        "basis": "same_process_host_clock_only",
        "host_clock_cryptographically_attested": False,
        "platform_and_tzdata_attested": False,
        "standalone_replay_proves_host_occurrence": False,
        "outer_private_append_receipt_required": True,
    }
)

AUTHORITY_SOURCE_PATHS: Mapping[str, Path] = MappingProxyType(
    {
        "capture_module": MODULE_RELATIVE_PATH,
        "engine_package_init": ENGINE_INIT_RELATIVE_PATH,
        "schema_contract": SCHEMA_RELATIVE_PATH,
        "session_window_source": SESSION_DIGEST_RELATIVE_PATH,
        "nyse_calendar_source": NYSE_CALENDAR_RELATIVE_PATH,
        "lib_package_init": LIB_INIT_RELATIVE_PATH,
    }
)

# These values are part of the integration contract, not aspirational prose.
# Tests require the future launcher/installer to retain every item.
FUTURE_LAUNCHER_HARD_REQUIREMENTS = (
    "literal_external_policy_not_runtime_derived",
    "public_builder_current_slot_only_no_clock_or_schedule_input",
    "same_effective_user_as_owned_checkout_and_lock",
    "outer_private_append_receipt_for_durable_host_occurrence",
    "external_owned_0700_pythonpycacheprefix_outside_checkout",
    "python_started_without_in_checkout_bytecode_cache",
)
FUTURE_INSTALLER_HARD_REQUIREMENTS = (
    "exclusive_same_lock_before_and_through_adjacent_swap",
    "bounded_lock_wait_fail_closed",
    "exact_detached_clean_release_and_tree_from_external_policy",
    "no_in_place_checkout_mutation",
    "rollback_checkout_preserved",
    "launcher_policy_and_checkout_cut_over_as_one_governed_release",
    "purge_in_checkout_python_bytecode_caches_before_cutover",
)


class MastermindXCaptureError(ValueError):
    """The operational checkout or capture attestation is invalid."""


@dataclass(frozen=True)
class CaptureReleasePolicy:
    """Reviewed release identity supplied by the later armed integration.

    Keeping this policy outside this module avoids a self-referential digest:
    the integration can pin the exact merge plus the already-reviewed module
    and schema bytes after this isolated slice lands.
    """

    producer_release_sha: str
    producer_tree_sha: str
    module_sha256: str
    module_bytes: int
    engine_init_sha256: str
    engine_init_bytes: int
    schema_sha256: str
    schema_bytes: int
    session_digest_sha256: str
    session_digest_bytes: int
    nyse_calendar_sha256: str
    nyse_calendar_bytes: int
    lib_init_sha256: str
    lib_init_bytes: int
    selector_receipt_sha256: str
    selector_receipt_bytes: int


def canonical_json_bytes(payload: object) -> bytes:
    """Return strict canonical UTF-8 JSON with one trailing newline."""

    try:
        return (
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise MastermindXCaptureError(
            f"payload is not strict canonical JSON: {exc}"
        ) from exc


def _validated_release_policy(
    policy: CaptureReleasePolicy,
) -> CaptureReleasePolicy:
    if not isinstance(policy, CaptureReleasePolicy):
        raise MastermindXCaptureError("capture release policy is not reviewed")
    for label, digest in (
        ("release", policy.producer_release_sha),
        ("tree", policy.producer_tree_sha),
    ):
        if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
            raise MastermindXCaptureError(f"producer {label} SHA is malformed")
    for label, digest in (
        ("module", policy.module_sha256),
        ("engine package init", policy.engine_init_sha256),
        ("schema", policy.schema_sha256),
        ("session digest", policy.session_digest_sha256),
        ("NYSE calendar", policy.nyse_calendar_sha256),
        ("lib package init", policy.lib_init_sha256),
        ("selector receipt", policy.selector_receipt_sha256),
    ):
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise MastermindXCaptureError(f"producer {label} digest is malformed")
    for label, size in (
        ("module", policy.module_bytes),
        ("engine package init", policy.engine_init_bytes),
        ("schema", policy.schema_bytes),
        ("session digest", policy.session_digest_bytes),
        ("NYSE calendar", policy.nyse_calendar_bytes),
        ("lib package init", policy.lib_init_bytes),
        ("selector receipt", policy.selector_receipt_bytes),
    ):
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 <= size <= MAX_ATTESTED_FILE_BYTES
        ):
            raise MastermindXCaptureError(f"producer {label} byte count is malformed")
    if (
        policy.selector_receipt_sha256 != SELECTOR_RECEIPT_SHA256
        or policy.selector_receipt_bytes != SELECTOR_RECEIPT_BYTES
    ):
        raise MastermindXCaptureError(
            "external policy does not pin the frozen selector receipt"
        )
    return policy


def _policy_authority_receipts(
    policy: CaptureReleasePolicy,
) -> dict[str, dict[str, Any]]:
    policy = _validated_release_policy(policy)
    values = {
        "capture_module": (policy.module_sha256, policy.module_bytes),
        "engine_package_init": (
            policy.engine_init_sha256,
            policy.engine_init_bytes,
        ),
        "schema_contract": (policy.schema_sha256, policy.schema_bytes),
        "session_window_source": (
            policy.session_digest_sha256,
            policy.session_digest_bytes,
        ),
        "nyse_calendar_source": (
            policy.nyse_calendar_sha256,
            policy.nyse_calendar_bytes,
        ),
        "lib_package_init": (
            policy.lib_init_sha256,
            policy.lib_init_bytes,
        ),
    }
    return {
        name: {
            "path": AUTHORITY_SOURCE_PATHS[name].as_posix(),
            "object_sha256": digest,
            "object_bytes": size,
        }
        for name, (digest, size) in values.items()
    }


def release_policy_sha256(policy: CaptureReleasePolicy) -> str:
    """Identity for the caller-frozen exact release and authority-byte set."""

    policy = _validated_release_policy(policy)
    payload = {
        "producer_release_sha": policy.producer_release_sha,
        "producer_tree_sha": policy.producer_tree_sha,
        "authority_sources": _policy_authority_receipts(policy),
        "selector_registration": {
            "path": SELECTOR_RECEIPT_RELATIVE_PATH.as_posix(),
            "object_sha256": policy.selector_receipt_sha256,
            "object_bytes": policy.selector_receipt_bytes,
        },
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


def producer_rule_sha256(policy: CaptureReleasePolicy) -> str:
    """Return the reviewed rule digest including its external release policy."""

    policy = _validated_release_policy(policy)
    rule = {
        "rule_id": "mastermindx_sparse_selector_capture_attestation/v2",
        "comparison_system": COMPARISON_SYSTEM,
        "disposition": DISPOSITION,
        "source_schema": SOURCE_SCHEMA,
        "authentication_basis": AUTHENTICATION_BASIS,
        "capture_cadence_seconds": CAPTURE_CADENCE_SECONDS,
        "slot_completion_boundary": "scheduled_at_plus_300_seconds_exclusive",
        "operational_checkout": {
            "path": str(OPS_CHECKOUT_ROOT),
            "mode": "0700",
            "owner": "effective_user",
            "detached_head": True,
            "tracked_worktree_bytes_match_head": True,
            "ordinary_untracked_absent": True,
            "ignored_files_policy": "bounded_owned_nonexecutable_pytest_cache_only",
            "exact_release_sha": policy.producer_release_sha,
            "exact_tree_sha": policy.producer_tree_sha,
            "authority_sources": _policy_authority_receipts(policy),
            "selector_receipt_matches_head_blob": True,
            "required_ancestor_shas": [
                SELECTOR_MERGE_SHA,
                NBBO_COHORT_MERGE_SHA,
            ],
        },
        "selector_registration": {
            "path": SELECTOR_RECEIPT_RELATIVE_PATH.as_posix(),
            "object_sha256": SELECTOR_RECEIPT_SHA256,
            "object_bytes": SELECTOR_RECEIPT_BYTES,
            "receipt_id": SELECTOR_RECEIPT_ID,
            "selector_rule_sha256": SELECTOR_RULE_SHA256,
            "selector_effective_freeze_at": SELECTOR_EFFECTIVE_FREEZE_AT,
            "registration_state": "globally_inactive",
            "historical_activation_action": "abstain",
            "historical_activation_reason_codes": [
                "NO_PROSPECTIVE_CANDIDATES"
            ],
            "current_slot_reason_code": "REGISTERED_SELECTOR_INACTIVE",
            "future_rows_policy": "new_governed_implementation_required",
        },
        "candidate_source_policy": "never_read_or_infer",
        "event_policy": "never_emit_or_enroll",
        "coverage_policy": "same_process_receipt_not_host_occurrence_proof",
        "occurrence_trust": dict(OCCURRENCE_TRUST),
        "future_launcher_hard_requirements": list(
            FUTURE_LAUNCHER_HARD_REQUIREMENTS
        ),
        "future_installer_hard_requirements": list(
            FUTURE_INSTALLER_HARD_REQUIREMENTS
        ),
        "authority": dict(FALSE_AUTHORITY),
    }
    return sha256(canonical_json_bytes(rule)).hexdigest()


def strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    """Parse one strict JSON object, rejecting duplicates and non-finite values."""

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in values:
            if key in out:
                raise MastermindXCaptureError(f"{label} has duplicate key {key!r}")
            out[key] = value
        return out

    def constant(value: str) -> None:
        raise MastermindXCaptureError(
            f"{label} contains non-finite number {value}"
        )

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MastermindXCaptureError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise MastermindXCaptureError(f"{label} root must be an object")
    return value


def _utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise MastermindXCaptureError(f"{label} must be a UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise MastermindXCaptureError(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise MastermindXCaptureError(f"{label} must be UTC")
    return parsed


def _aware_utc(value: Any, *, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise MastermindXCaptureError(
            f"{label} must be a timezone-aware datetime"
        )
    return value.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    return (
        _aware_utc(value, label="runtime clock")
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _session_window(session: date) -> tuple[datetime, datetime]:
    if not _nyse_calendar.is_session(session):
        raise MastermindXCaptureError(f"{session.isoformat()} is not an NYSE session")
    opened, closed = _session_digest.session_window_et(session)
    return opened.astimezone(timezone.utc), closed.astimezone(timezone.utc)


def _runtime_now() -> datetime:
    """Return the non-overridable production clock used by the public builder."""

    return datetime.now(timezone.utc)


def _scheduled_slot(attempted: datetime) -> datetime:
    attempted = _aware_utc(attempted, label="attempted_at")
    session = attempted.astimezone(ET).date()
    opened, closed = _session_window(session)
    if not opened <= attempted < closed:
        raise MastermindXCaptureError("capture attempted outside NYSE RTH")
    elapsed = int((attempted - opened).total_seconds())
    return opened + timedelta(
        seconds=(elapsed // CAPTURE_CADENCE_SECONDS) * CAPTURE_CADENCE_SECONDS
    )


def _validate_slot(
    *,
    scheduled: datetime,
    attempted: datetime,
    capture_event: datetime,
    completed: datetime,
) -> None:
    freeze = _utc(SELECTOR_EFFECTIVE_FREEZE_AT, label="selector effective freeze")
    if scheduled < freeze:
        raise MastermindXCaptureError("capture scheduled before selector freeze")
    session = scheduled.astimezone(ET).date()
    opened, closed = _session_window(session)
    if not opened <= scheduled < closed:
        raise MastermindXCaptureError("capture scheduled outside NYSE RTH")
    elapsed = (scheduled - opened).total_seconds()
    if elapsed != int(elapsed) or int(elapsed) % CAPTURE_CADENCE_SECONDS:
        raise MastermindXCaptureError("capture is not on the frozen 300s grid")
    if scheduled.microsecond:
        raise MastermindXCaptureError("capture grid clock has fractional seconds")
    if not scheduled <= attempted <= capture_event <= completed:
        raise MastermindXCaptureError("capture clocks are not causal")
    if completed >= scheduled + timedelta(seconds=CAPTURE_CADENCE_SECONDS):
        raise MastermindXCaptureError("capture did not complete inside its slot")


def _validate_terminal_slot(
    *, scheduled: datetime, completed: datetime, terminal: datetime
) -> None:
    """Require the fully validated receipt to return inside its capture slot."""

    if not completed <= terminal < scheduled + timedelta(
        seconds=CAPTURE_CADENCE_SECONDS
    ):
        raise MastermindXCaptureError(
            "capture terminal clock left its scheduled slot"
        )


def _git(
    root: Path,
    *arguments: str,
    allowed_returncodes: tuple[int, ...] = (0,),
    timeout_seconds: int = 15,
) -> tuple[int, bytes]:
    if not GIT_BINARY.is_absolute() or not GIT_BINARY.exists():
        raise MastermindXCaptureError("absolute Git binary is unavailable")
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }
    try:
        result = subprocess.run(
            [str(GIT_BINARY), "-C", str(root), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MastermindXCaptureError(f"Git verification failed: {exc}") from exc
    if result.returncode not in allowed_returncodes:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise MastermindXCaptureError(
            f"Git verification failed rc={result.returncode}: {message[:300]}"
        )
    return result.returncode, result.stdout


def _validate_owned_regular_metadata(
    metadata: os.stat_result, *, label: str
) -> None:
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MastermindXCaptureError(f"{label} must be a regular non-symlink file")
    if metadata.st_uid != os.geteuid():
        raise MastermindXCaptureError(f"{label} is not owned by the effective user")
    if metadata.st_nlink != 1:
        raise MastermindXCaptureError(f"{label} must have exactly one hard link")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise MastermindXCaptureError(f"{label} is group/world writable")


def _metadata_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_regular_bytes(
    path: Path,
    *,
    label: str,
    require_single_link: bool,
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MastermindXCaptureError(f"{label} is unavailable: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise MastermindXCaptureError(
                f"{label} must be a regular non-symlink file"
            )
        if before.st_uid != os.geteuid():
            raise MastermindXCaptureError(f"{label} is not owned by the effective user")
        if require_single_link and before.st_nlink != 1:
            raise MastermindXCaptureError(f"{label} must have exactly one hard link")
        if stat.S_IMODE(before.st_mode) & 0o022:
            raise MastermindXCaptureError(f"{label} is group/world writable")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ATTESTED_FILE_BYTES:
                raise MastermindXCaptureError(f"{label} exceeds the file byte cap")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _metadata_identity(before) != _metadata_identity(after):
        raise MastermindXCaptureError(f"{label} changed while it was read")
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise MastermindXCaptureError(f"{label} vanished after it was read") from exc
    if _metadata_identity(current) != _metadata_identity(after):
        raise MastermindXCaptureError(f"{label} path changed while it was read")
    if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
        raise MastermindXCaptureError(f"{label} must remain a regular file")
    if current.st_uid != os.geteuid():
        raise MastermindXCaptureError(f"{label} owner changed while it was read")
    if require_single_link and current.st_nlink != 1:
        raise MastermindXCaptureError(f"{label} hard-link count changed")
    if stat.S_IMODE(current.st_mode) & 0o022:
        raise MastermindXCaptureError(f"{label} became group/world writable")
    body = b"".join(chunks)
    if len(body) != after.st_size:
        raise MastermindXCaptureError(f"{label} read was incomplete")
    return body, after


def _read_owned_regular(path: Path, *, label: str) -> tuple[bytes, os.stat_result]:
    return _read_regular_bytes(path, label=label, require_single_link=True)


def _acquire_flock_with_timeout(
    descriptor: int,
    operation: int,
    *,
    timeout_seconds: float | None = None,
) -> None:
    if timeout_seconds is None:
        timeout_seconds = INSTALL_LOCK_TIMEOUT_SECONDS
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds < 0
    ):
        raise MastermindXCaptureError("capture install-lock timeout is invalid")
    deadline = time.monotonic() + float(timeout_seconds)
    while True:
        try:
            fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                raise MastermindXCaptureError(
                    f"capture install lock failed: {exc}"
                ) from exc
            if time.monotonic() >= deadline:
                raise MastermindXCaptureError(
                    "capture install lock timed out"
                ) from exc
            time.sleep(INSTALL_LOCK_POLL_SECONDS)


def _require_lock_path_identity(
    descriptor_metadata: os.stat_result, *, stage: str
) -> None:
    try:
        current = os.lstat(INSTALL_LOCK_PATH)
    except OSError as exc:
        raise MastermindXCaptureError(
            f"capture install lock vanished {stage}: {exc}"
        ) from exc
    if _metadata_identity(current) != _metadata_identity(descriptor_metadata):
        raise MastermindXCaptureError(
            f"capture install lock path changed {stage}"
        )
    _validate_owned_regular_metadata(current, label="capture install lock")
    if stat.S_IMODE(current.st_mode) != 0o600:
        raise MastermindXCaptureError("capture install lock mode must remain 0600")


@contextmanager
def _install_lock(operation: int) -> Any:
    """Hold the install/attest lock shared across one coherent observation.

    The later install slice must take this same file exclusively before an
    adjacent checkout swap.  Double-snapshot verification below still fails
    closed if an older installer does not yet honor the lock.
    """

    parent = INSTALL_LOCK_PATH.parent
    try:
        parent_metadata = os.lstat(parent)
    except OSError as exc:
        raise MastermindXCaptureError(
            f"capture install-lock directory is unavailable: {exc}"
        ) from exc
    if (
        stat.S_ISLNK(parent_metadata.st_mode)
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        raise MastermindXCaptureError(
            "capture install-lock directory must be owned non-symlink mode 0700"
        )
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(INSTALL_LOCK_PATH, flags, 0o600)
    except OSError as exc:
        raise MastermindXCaptureError(f"capture install lock failed: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        _validate_owned_regular_metadata(metadata, label="capture install lock")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise MastermindXCaptureError("capture install lock mode must be 0600")
        _require_lock_path_identity(metadata, stage="after open")
        _acquire_flock_with_timeout(descriptor, operation)
        _require_lock_path_identity(metadata, stage="after acquisition")
        try:
            yield
        finally:
            _require_lock_path_identity(metadata, stage="before release")
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@contextmanager
def _shared_install_lock() -> Any:
    """Attestor lock: held across every checkout read and final recheck."""

    with _install_lock(fcntl.LOCK_SH):
        yield


@contextmanager
def _exclusive_install_lock() -> Any:
    """Required future-installer lock for the complete adjacent swap.

    The installer must enter this context before validating its stage, retain it
    through label stop/move/manifest update/label start, and release only after
    verifying the exact active release.  Any installer that does not use this
    exact lock protocol is incompatible with this attestor.
    """

    with _install_lock(fcntl.LOCK_EX):
        yield


def _verify_root(root: Path) -> os.stat_result:
    if os.geteuid() == 0:
        raise MastermindXCaptureError("capture must not run as root")
    if not root.is_absolute() or root != OPS_CHECKOUT_ROOT:
        raise MastermindXCaptureError("capture checkout path is not the frozen root")
    try:
        resolved = root.resolve(strict=True)
        metadata = os.lstat(root)
    except OSError as exc:
        raise MastermindXCaptureError(
            f"capture checkout is unavailable: {exc}"
        ) from exc
    if resolved != root or stat.S_ISLNK(metadata.st_mode):
        raise MastermindXCaptureError("capture checkout path traverses a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise MastermindXCaptureError("capture checkout root is not a directory")
    if metadata.st_uid != os.geteuid():
        raise MastermindXCaptureError(
            "capture checkout is not owned by the effective user"
        )
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise MastermindXCaptureError("capture checkout root mode must be 0700")
    return metadata


def _single_line(value: bytes, *, label: str) -> str:
    try:
        text = value.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise MastermindXCaptureError(f"{label} is not UTF-8") from exc
    if not text or "\n" in text or "\r" in text:
        raise MastermindXCaptureError(f"{label} is not one non-empty line")
    return text


def _nul_paths(value: bytes, *, label: str) -> list[Path]:
    paths: list[Path] = []
    for raw in value.split(b"\0"):
        if not raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MastermindXCaptureError(f"{label} path is not UTF-8") from exc
        path = Path(text)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise MastermindXCaptureError(f"{label} path is unsafe")
        paths.append(path)
    return paths


def _verify_index_exact(root: Path, *, head: str) -> None:
    """Reject index flags and require exact HEAD mode/object/stage tuples."""

    _, stage = _git(root, "ls-files", "--stage", "-z")
    entries = [entry for entry in stage.split(b"\0") if entry]
    index_entries: list[tuple[bytes, bytes, bytes, bytes]] = []
    for entry in entries:
        try:
            prefix, raw_path = entry.split(b"\t", 1)
            mode, object_id, stage_number = prefix.split(b" ")
            path_text = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise MastermindXCaptureError("Git index entry is malformed") from exc
        if stage_number != b"0":
            raise MastermindXCaptureError("Git index contains an unmerged entry")
        path = Path(path_text)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise MastermindXCaptureError("Git index path is unsafe")
        index_entries.append((mode, object_id, stage_number, raw_path))

    _, flags = _git(root, "ls-files", "-v", "-z")
    for entry in (entry for entry in flags.split(b"\0") if entry):
        if len(entry) < 3 or entry[1:2] != b" ":
            raise MastermindXCaptureError("Git index flag entry is malformed")
        marker = entry[:1]
        if marker in (b"h", b"S", b"s"):
            raise MastermindXCaptureError(
                "Git index contains assume-unchanged or skip-worktree flags"
            )

    _, tree_raw = _git(root, "ls-tree", "-r", "-z", head)
    tree_entries: list[tuple[bytes, bytes, bytes, bytes]] = []
    for entry in (entry for entry in tree_raw.split(b"\0") if entry):
        try:
            prefix, raw_path = entry.split(b"\t", 1)
            mode, object_type, object_id = prefix.split(b" ")
        except ValueError as exc:
            raise MastermindXCaptureError("Git HEAD tree entry is malformed") from exc
        if object_type != b"blob":
            raise MastermindXCaptureError("Git HEAD contains a non-blob tracked entry")
        tree_entries.append((mode, object_id, b"0", raw_path))
    if index_entries != tree_entries:
        raise MastermindXCaptureError(
            "Git index mode/object/stage tuples do not equal installed HEAD"
        )


def _verify_all_tracked_worktree_bytes(
    root: Path, *, head: str
) -> tuple[str, int, int]:
    """Compare raw regular-file bytes and modes to every exact HEAD blob.

    This reads worktree file descriptors directly with ``O_NOFOLLOW`` and
    computes Git's raw ``blob <size>\\0<body>`` identity itself.  No installed
    index metadata, attributes, clean filter, autocrlf rule, or smudge/clean
    driver participates.  One bounded ``ls-tree`` call inventories HEAD; there
    is never one Git subprocess per file.
    """

    _, tree_raw = _git(root, "ls-tree", "-r", "-l", "-z", head)
    entries: list[tuple[Path, bytes, bytes, int]] = []
    tracked_directories: set[Path] = set()
    total_bytes = 0
    for entry in (item for item in tree_raw.split(b"\0") if item):
        try:
            prefix, raw_path = entry.split(b"\t", 1)
            mode, object_type, object_id, raw_size = prefix.split()
            path_text = raw_path.decode("utf-8")
            object_bytes = int(raw_size)
        except (UnicodeDecodeError, ValueError) as exc:
            raise MastermindXCaptureError("Git HEAD tree entry is malformed") from exc
        relative_path = Path(path_text)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or not relative_path.parts
        ):
            raise MastermindXCaptureError("Git HEAD tree path is unsafe")
        if (
            object_type != b"blob"
            or mode not in (b"100644", b"100755")
            or not _SHA_RE.fullmatch(object_id.decode("ascii", errors="ignore"))
            or not 0 <= object_bytes <= MAX_TRACKED_FILE_BYTES
        ):
            raise MastermindXCaptureError("Git HEAD tracked blob is unsupported")
        total_bytes += object_bytes
        if (
            len(entries) >= MAX_TRACKED_TREE_FILES
            or total_bytes > MAX_TRACKED_TREE_BYTES
        ):
            raise MastermindXCaptureError("Git HEAD tracked tree exceeds its bound")
        entries.append((relative_path, mode, object_id, object_bytes))
        parent = relative_path.parent
        while parent != Path("."):
            tracked_directories.add(parent)
            parent = parent.parent

    scan = sha256()
    directory_identities: dict[Path, tuple[int, ...]] = {}
    for relative_directory in sorted(
        tracked_directories, key=lambda item: item.as_posix()
    ):
        try:
            metadata = os.lstat(root / relative_directory)
        except OSError as exc:
            raise MastermindXCaptureError(
                f"tracked directory {relative_directory.as_posix()} is unavailable: {exc}"
            ) from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o755
        ):
            raise MastermindXCaptureError(
                f"tracked directory {relative_directory.as_posix()} is unsafe"
            )
        directory_identities[relative_directory] = _metadata_identity(metadata)

    for relative_path, mode, object_id, object_bytes in entries:
        path = root / relative_path
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise MastermindXCaptureError(
                f"tracked path {relative_path.as_posix()} is unavailable: {exc}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            expected_mode = 0o755 if mode == b"100755" else 0o644
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != expected_mode
                or before.st_size != object_bytes
            ):
                raise MastermindXCaptureError(
                    f"tracked path {relative_path.as_posix()} metadata differs from HEAD"
                )
            digest = sha1(f"blob {object_bytes}\0".encode("ascii"))
            read_bytes = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                read_bytes += len(chunk)
                digest.update(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (
            read_bytes != object_bytes
            or _metadata_identity(before) != _metadata_identity(after)
        ):
            raise MastermindXCaptureError(
                f"tracked path {relative_path.as_posix()} changed while read"
            )
        try:
            current = os.lstat(path)
        except OSError as exc:
            raise MastermindXCaptureError(
                f"tracked path {relative_path.as_posix()} vanished after read"
            ) from exc
        if _metadata_identity(current) != _metadata_identity(after):
            raise MastermindXCaptureError(
                f"tracked path {relative_path.as_posix()} changed while read"
            )
        if digest.hexdigest().encode("ascii") != object_id:
            raise MastermindXCaptureError(
                f"tracked path {relative_path.as_posix()} raw bytes differ from HEAD"
            )
        scan.update(
            canonical_json_bytes(
                [
                    relative_path.as_posix(),
                    mode.decode("ascii"),
                    object_id.decode("ascii"),
                    object_bytes,
                    list(_metadata_identity(after)),
                ]
            )
        )
    for relative_directory in sorted(
        tracked_directories, key=lambda item: item.as_posix()
    ):
        try:
            current = os.lstat(root / relative_directory)
        except OSError as exc:
            raise MastermindXCaptureError(
                f"tracked directory {relative_directory.as_posix()} vanished: {exc}"
            ) from exc
        identity = _metadata_identity(current)
        if identity != directory_identities[relative_directory]:
            raise MastermindXCaptureError(
                f"tracked directory {relative_directory.as_posix()} changed while read"
            )
        scan.update(
            canonical_json_bytes(
                [relative_directory.as_posix(), list(identity)]
            )
        )
    return scan.hexdigest(), len(entries), total_bytes


def _safe_ignored_cache_path(relative_path: Path) -> bool:
    return relative_path in SAFE_IGNORED_PYTEST_CACHE_FILES


def _verify_ignored_caches(root: Path) -> None:
    """Allow only a bounded inert root pytest cache; reject every other ignore."""

    _, raw = _git(root, "ls-files", "-o", "-i", "--exclude-standard", "-z")
    paths = _nul_paths(raw, label="ignored")
    if len(paths) > MAX_IGNORED_CACHE_ENTRIES:
        raise MastermindXCaptureError("ignored cache entry cap exceeded")
    total_bytes = 0
    checked_directories: set[Path] = set()
    for relative_path in paths:
        if not _safe_ignored_cache_path(relative_path):
            raise MastermindXCaptureError(
                f"unsafe ignored path {relative_path.as_posix()}"
            )
        for parent in relative_path.parents:
            if parent == Path("."):
                break
            if parent in checked_directories:
                continue
            metadata = os.lstat(root / parent)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) not in (0o700, 0o755)
            ):
                raise MastermindXCaptureError(
                    f"ignored cache directory {parent.as_posix()} is unsafe"
                )
            checked_directories.add(parent)
        metadata = os.lstat(root / relative_path)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) not in (0o600, 0o644)
            or metadata.st_size > MAX_IGNORED_CACHE_FILE_BYTES
        ):
            raise MastermindXCaptureError(
                f"ignored cache file {relative_path.as_posix()} is unsafe"
            )
        total_bytes += metadata.st_size
        if total_bytes > MAX_IGNORED_CACHE_TOTAL_BYTES:
            raise MastermindXCaptureError("ignored cache byte cap exceeded")


def _require_ancestor(root: Path, ancestor: str, head: str, *, label: str) -> None:
    if not _SHA_RE.fullmatch(ancestor):
        raise MastermindXCaptureError(f"{label} SHA is malformed")
    code, _ = _git(
        root,
        "merge-base",
        "--is-ancestor",
        ancestor,
        head,
        allowed_returncodes=(0, 1),
    )
    if code != 0:
        raise MastermindXCaptureError(f"installed checkout lacks {label} ancestor")


def _tracked_file_receipt(
    root: Path,
    *,
    head: str,
    relative_path: Path,
    runtime_path: Path | None = None,
    label: str,
) -> tuple[dict[str, Any], bytes, tuple[int, ...]]:
    path = root / relative_path
    if runtime_path is not None and runtime_path != path:
        raise MastermindXCaptureError(
            f"{label} did not execute from installed checkout"
        )
    body, metadata = _read_owned_regular(path, label=label)
    _, blob = _git(root, "show", f"{head}:{relative_path.as_posix()}")
    if blob != body:
        raise MastermindXCaptureError(f"{label} does not match installed HEAD blob")
    return _file_receipt(relative_path, body), body, _metadata_identity(metadata)


def _file_receipt(relative_path: Path, body: bytes) -> dict[str, Any]:
    return {
        "path": relative_path.as_posix(),
        "object_sha256": sha256(body).hexdigest(),
        "object_bytes": len(body),
    }


def _validate_selector_receipt(body: bytes) -> None:
    if len(body) != SELECTOR_RECEIPT_BYTES:
        raise MastermindXCaptureError("selector registration byte count drifted")
    if sha256(body).hexdigest() != SELECTOR_RECEIPT_SHA256:
        raise MastermindXCaptureError("selector registration digest drifted")
    receipt = strict_json_object(body, label="selector registration")
    registration = receipt.get("registration")
    selector_rule = receipt.get("selector_rule")
    activation = receipt.get("activation_disposition")
    manifest = receipt.get("activation_manifest")
    claim_boundary = receipt.get("claim_boundary")
    authority = receipt.get("authority")
    expected_activation = {
        "action": "abstain",
        "future_rows_policy": "new_governed_implementation_required",
        "reason_codes": ["NO_PROSPECTIVE_CANDIDATES"],
        "selector_active": False,
    }
    if (
        receipt.get("schema") != SELECTOR_RECEIPT_SCHEMA
        or receipt.get("receipt_id") != SELECTOR_RECEIPT_ID
        or not isinstance(registration, Mapping)
        or registration.get("repository") != "mastermindx-market-intelligence/macro"
        or registration.get("selector_rule_sha256") != SELECTOR_RULE_SHA256
        or not isinstance(registration.get("selector_effective_freeze"), Mapping)
        or registration["selector_effective_freeze"].get("effective_freeze_at")
        != SELECTOR_EFFECTIVE_FREEZE_AT
        or not isinstance(selector_rule, Mapping)
        or selector_rule.get("rule_id") != SELECTOR_RULE_ID
        or activation != expected_activation
        or not isinstance(manifest, Mapping)
        or manifest.get("manifest_id") != ACTIVATION_MANIFEST_ID
        or manifest.get("scope") != "activation_snapshot_not_covered_session"
        or not isinstance(claim_boundary, Mapping)
        or claim_boundary.get("covered_session_evidence") is not False
        or not all(value is False for value in claim_boundary.values())
        or not isinstance(authority, Mapping)
        or not all(value is False for value in authority.values())
    ):
        raise MastermindXCaptureError("selector registration semantics drifted")


def _checkout_attestation(
    root: Path, policy: CaptureReleasePolicy
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    policy = _validated_release_policy(policy)
    root_metadata = _verify_root(root)
    _, top_raw = _git(root, "rev-parse", "--show-toplevel")
    top = Path(_single_line(top_raw, label="Git top level")).resolve(strict=True)
    if top != root:
        raise MastermindXCaptureError("Git top level is not the frozen checkout root")
    _, head_raw = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    head = _single_line(head_raw, label="installed HEAD")
    if not _SHA_RE.fullmatch(head):
        raise MastermindXCaptureError("installed HEAD SHA is malformed")
    if head != policy.producer_release_sha:
        raise MastermindXCaptureError(
            "installed checkout is not the exact reviewed producer release"
        )
    _, tree_raw = _git(root, "rev-parse", "--verify", "HEAD^{tree}")
    tree = _single_line(tree_raw, label="installed tree")
    if tree != policy.producer_tree_sha:
        raise MastermindXCaptureError(
            "installed checkout tree is not the exact reviewed producer tree"
        )
    symbolic_code, _ = _git(
        root,
        "symbolic-ref",
        "-q",
        "HEAD",
        allowed_returncodes=(0, 1),
    )
    if symbolic_code == 0:
        raise MastermindXCaptureError("installed checkout HEAD is not detached")
    _verify_index_exact(root, head=head)
    _, ordinary_untracked = _git(
        root,
        "ls-files",
        "-o",
        "--exclude-standard",
        "-z",
    )
    if ordinary_untracked:
        raise MastermindXCaptureError("installed checkout has ordinary untracked files")
    _verify_ignored_caches(root)
    tracked_tree_snapshot = _verify_all_tracked_worktree_bytes(root, head=head)
    if _metadata_identity(root_metadata) != _metadata_identity(_verify_root(root)):
        raise MastermindXCaptureError("capture checkout root changed during tree read")
    _require_ancestor(root, SELECTOR_MERGE_SHA, head, label="selector merge")
    _require_ancestor(root, NBBO_COHORT_MERGE_SHA, head, label="NBBO cohort merge")
    authority_receipts: dict[str, dict[str, Any]] = {}
    snapshot_metadata: dict[str, Any] = {
        "checkout_root": _metadata_identity(root_metadata),
        "tracked_worktree": tracked_tree_snapshot,
    }
    authority_runtime_paths = {
        "capture_module": MODULE_PATH,
        "engine_package_init": ENGINE_INIT_PATH,
        "schema_contract": SCHEMA_PATH,
        "session_window_source": SESSION_DIGEST_PATH,
        "nyse_calendar_source": NYSE_CALENDAR_PATH,
        "lib_package_init": LIB_INIT_PATH,
    }
    expected_authority = _policy_authority_receipts(policy)
    for name, relative_path in AUTHORITY_SOURCE_PATHS.items():
        receipt, _body, metadata_identity = _tracked_file_receipt(
            root,
            head=head,
            relative_path=relative_path,
            runtime_path=authority_runtime_paths[name],
            label=f"MastermindX {name.replace('_', ' ')}",
        )
        if receipt != expected_authority[name]:
            raise MastermindXCaptureError(
                f"capture {name.replace('_', ' ')} release binding drifted"
            )
        authority_receipts[name] = receipt
        snapshot_metadata[name] = metadata_identity

    selector_receipt, selector_body, selector_metadata_identity = _tracked_file_receipt(
        root,
        head=head,
        relative_path=SELECTOR_RECEIPT_RELATIVE_PATH,
        label="selector registration",
    )
    _validate_selector_receipt(selector_body)
    snapshot_metadata["selector_registration"] = selector_metadata_identity
    if selector_receipt != {
        "path": SELECTOR_RECEIPT_RELATIVE_PATH.as_posix(),
        "object_sha256": policy.selector_receipt_sha256,
        "object_bytes": policy.selector_receipt_bytes,
    }:
        raise MastermindXCaptureError("selector registration receipt drifted")

    checkout = {
        "path": str(root),
        "head_sha": head,
        "tree_sha": tree,
        "producer_release_sha": policy.producer_release_sha,
        "release_policy_sha256": release_policy_sha256(policy),
        "selector_merge_sha": SELECTOR_MERGE_SHA,
        "nbbo_cohort_merge_sha": NBBO_COHORT_MERGE_SHA,
        "owner_uid": root_metadata.st_uid,
        "root_device": root_metadata.st_dev,
        "root_inode": root_metadata.st_ino,
        "root_mode": "0700",
        "detached_head": True,
        "tracked_worktree_matches_head": True,
        "ordinary_untracked_absent": True,
        "ignored_cache_policy": "bounded_owned_nonexecutable_pytest_cache_only",
        "authority_sources": authority_receipts,
    }
    selector = {
        **selector_receipt,
        "receipt_id": SELECTOR_RECEIPT_ID,
        "selector_rule_sha256": SELECTOR_RULE_SHA256,
        "activation_manifest_id": ACTIVATION_MANIFEST_ID,
        "selector_effective_freeze_at": SELECTOR_EFFECTIVE_FREEZE_AT,
        "registration_state": "globally_inactive",
        "historical_activation_action": "abstain",
        "historical_activation_reason_codes": ["NO_PROSPECTIVE_CANDIDATES"],
        "current_slot_reason_code": "REGISTERED_SELECTOR_INACTIVE",
        "candidate_source_examined": False,
        "current_candidate_count_known": False,
        "future_rows_policy": "new_governed_implementation_required",
        "registered_receipt_is_covered_session_evidence": False,
    }
    return checkout, selector, snapshot_metadata


_ATTESTATION_FIELDS = {
    "schema",
    "attestation_id",
    "mode",
    "authentication_basis",
    "comparison_system",
    "scheduled_at",
    "attempted_at",
    "completed_at",
    "capture_event_at",
    "disposition",
    "emitted_enrollment_event_count",
    "emitted_enrollment_event_ids",
    "producer_rule_sha256",
    "release_policy_sha256",
    "checkout",
    "selector_registration",
    "observation",
    "claim_boundary",
    "occurrence_trust",
    "authority",
}


def _attestation_id(payload: Mapping[str, Any]) -> str:
    identity = copy.deepcopy(dict(payload))
    identity.pop("attestation_id", None)
    return "mxcap_" + sha256(canonical_json_bytes(identity)).hexdigest()


def validate_attestation(
    raw: Any, *, release_policy: CaptureReleasePolicy
) -> dict[str, Any]:
    """Validate semantics against the integration's reviewed release policy.

    This source-specific validator is mandatory in both build and replay paths.
    Durable host occurrence is authenticated by the outer private evidence
    store; this object is deliberately not a signature or standalone occurrence
    proof.
    """

    release_policy = _validated_release_policy(release_policy)
    expected_rule_sha256 = producer_rule_sha256(release_policy)
    if not isinstance(raw, Mapping):
        raise MastermindXCaptureError("capture attestation must be an object")
    payload = copy.deepcopy(dict(raw))
    if set(payload) != _ATTESTATION_FIELDS:
        raise MastermindXCaptureError("capture attestation fields are not exact")
    if (
        payload.get("schema") != SOURCE_SCHEMA
        or payload.get("mode") != MODE
        or payload.get("authentication_basis") != AUTHENTICATION_BASIS
        or payload.get("comparison_system") != COMPARISON_SYSTEM
        or payload.get("disposition") != DISPOSITION
        or payload.get("emitted_enrollment_event_count") != 0
        or payload.get("emitted_enrollment_event_ids") != []
        or payload.get("producer_rule_sha256") != expected_rule_sha256
        or payload.get("release_policy_sha256")
        != release_policy_sha256(release_policy)
        or payload.get("observation") != _json_observation()
        or payload.get("claim_boundary") != dict(CLAIM_BOUNDARY)
        or payload.get("occurrence_trust") != dict(OCCURRENCE_TRUST)
        or payload.get("authority") != dict(FALSE_AUTHORITY)
    ):
        raise MastermindXCaptureError("capture attestation governance drifted")

    scheduled = _utc(payload.get("scheduled_at"), label="scheduled_at")
    attempted = _utc(payload.get("attempted_at"), label="attempted_at")
    capture_event = _utc(payload.get("capture_event_at"), label="capture_event_at")
    completed = _utc(payload.get("completed_at"), label="completed_at")
    for text, parsed, label in (
        (payload["scheduled_at"], scheduled, "scheduled_at"),
        (payload["attempted_at"], attempted, "attempted_at"),
        (payload["capture_event_at"], capture_event, "capture_event_at"),
        (payload["completed_at"], completed, "completed_at"),
    ):
        if text != utc_text(parsed):
            raise MastermindXCaptureError(f"{label} is not canonical")
    _validate_slot(
        scheduled=scheduled,
        attempted=attempted,
        capture_event=capture_event,
        completed=completed,
    )

    checkout = payload.get("checkout")
    expected_checkout_fields = {
        "path",
        "head_sha",
        "tree_sha",
        "producer_release_sha",
        "release_policy_sha256",
        "selector_merge_sha",
        "nbbo_cohort_merge_sha",
        "owner_uid",
        "root_device",
        "root_inode",
        "root_mode",
        "detached_head",
        "tracked_worktree_matches_head",
        "ordinary_untracked_absent",
        "ignored_cache_policy",
        "authority_sources",
    }
    if (
        not isinstance(checkout, Mapping)
        or set(checkout) != expected_checkout_fields
        or checkout.get("path") != str(OPS_CHECKOUT_ROOT)
        or not isinstance(checkout.get("owner_uid"), int)
        or isinstance(checkout.get("owner_uid"), bool)
        or checkout.get("owner_uid", -1) < 1
        or checkout.get("root_mode") != "0700"
        or checkout.get("detached_head") is not True
        or checkout.get("tracked_worktree_matches_head") is not True
        or checkout.get("ordinary_untracked_absent") is not True
        or checkout.get("ignored_cache_policy")
        != "bounded_owned_nonexecutable_pytest_cache_only"
        or checkout.get("selector_merge_sha") != SELECTOR_MERGE_SHA
        or checkout.get("nbbo_cohort_merge_sha") != NBBO_COHORT_MERGE_SHA
        or checkout.get("producer_release_sha")
        != release_policy.producer_release_sha
        or checkout.get("head_sha") != release_policy.producer_release_sha
        or checkout.get("tree_sha") != release_policy.producer_tree_sha
        or checkout.get("release_policy_sha256")
        != release_policy_sha256(release_policy)
        or any(
            not isinstance(checkout.get(field), int)
            or isinstance(checkout.get(field), bool)
            or checkout.get(field, -1) < 1
            for field in ("root_device", "root_inode")
        )
    ):
        raise MastermindXCaptureError("capture checkout receipt is malformed")
    if checkout.get("authority_sources") != _policy_authority_receipts(
        release_policy
    ):
        raise MastermindXCaptureError(
            "capture authority-source receipts are malformed"
        )

    selector = payload.get("selector_registration")
    expected_selector = {
        "path": SELECTOR_RECEIPT_RELATIVE_PATH.as_posix(),
        "object_sha256": SELECTOR_RECEIPT_SHA256,
        "object_bytes": SELECTOR_RECEIPT_BYTES,
        "receipt_id": SELECTOR_RECEIPT_ID,
        "selector_rule_sha256": SELECTOR_RULE_SHA256,
        "activation_manifest_id": ACTIVATION_MANIFEST_ID,
        "selector_effective_freeze_at": SELECTOR_EFFECTIVE_FREEZE_AT,
        "registration_state": "globally_inactive",
        "historical_activation_action": "abstain",
        "historical_activation_reason_codes": ["NO_PROSPECTIVE_CANDIDATES"],
        "current_slot_reason_code": "REGISTERED_SELECTOR_INACTIVE",
        "candidate_source_examined": False,
        "current_candidate_count_known": False,
        "future_rows_policy": "new_governed_implementation_required",
        "registered_receipt_is_covered_session_evidence": False,
    }
    if selector != expected_selector:
        raise MastermindXCaptureError("selector registration binding drifted")
    if payload.get("attestation_id") != _attestation_id(payload):
        raise MastermindXCaptureError("capture attestation content identity drifted")
    canonical_json_bytes(payload)
    _validate_source_schema(payload, release_policy=release_policy)
    return copy.deepcopy(payload)


def _json_observation() -> dict[str, Any]:
    observation = copy.deepcopy(dict(OBSERVATION))
    observation["emitted_enrollment_event_ids"] = list(
        observation["emitted_enrollment_event_ids"]
    )
    return observation


def _validate_source_schema(
    payload: Mapping[str, Any], *, release_policy: CaptureReleasePolicy
) -> None:
    """Run the exact installed schema contract; absence/failure is fatal."""

    try:
        from jsonschema import Draft202012Validator, FormatChecker

        release_policy = _validated_release_policy(release_policy)
        schema_body, _metadata = _read_owned_regular(
            SCHEMA_PATH, label="capture source schema"
        )
        if _file_receipt(SCHEMA_RELATIVE_PATH, schema_body) != {
            "path": SCHEMA_RELATIVE_PATH.as_posix(),
            "object_sha256": release_policy.schema_sha256,
            "object_bytes": release_policy.schema_bytes,
        }:
            raise MastermindXCaptureError(
                "capture source schema release binding drifted"
            )
        schema = strict_json_object(schema_body, label="capture schema")
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(copy.deepcopy(dict(payload))),
            key=lambda error: "/".join(str(part) for part in error.path),
        )
    except MastermindXCaptureError:
        raise
    except Exception as exc:
        raise MastermindXCaptureError(
            f"capture source schema validation failed: {exc}"
        ) from exc
    if errors:
        summary = "; ".join(
            f"{'/'.join(str(part) for part in error.path) or '<root>'}: "
            f"{error.message}"
            for error in errors[:8]
        )
        raise MastermindXCaptureError(
            f"capture source schema validation failed: {summary}"
        )


def _snapshot_identity(
    snapshot: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> str:
    return sha256(canonical_json_bytes(snapshot)).hexdigest()


def build_mastermindx_capture_attestation(
    *,
    release_policy: CaptureReleasePolicy,
) -> dict[str, Any]:
    """Attest the installed frozen selector during the current capture slot.

    The public API accepts neither a slot nor a clock.  Tests patch the private
    ``_runtime_now`` boundary; a production caller cannot request historical or
    future success.
    """

    release_policy = _validated_release_policy(release_policy)
    attempted = _aware_utc(_runtime_now(), label="attempted_at")
    scheduled = _scheduled_slot(attempted)
    with _shared_install_lock():
        before = _checkout_attestation(OPS_CHECKOUT_ROOT, release_policy)
        capture_event = _aware_utc(_runtime_now(), label="capture_event_at")
        after = _checkout_attestation(OPS_CHECKOUT_ROOT, release_policy)
        if _snapshot_identity(before) != _snapshot_identity(after):
            raise MastermindXCaptureError(
                "installed checkout changed across capture event"
            )
        checkout, selector, _metadata = after
        completed = _aware_utc(_runtime_now(), label="completed_at")
        final = _checkout_attestation(OPS_CHECKOUT_ROOT, release_policy)
        if _snapshot_identity(after) != _snapshot_identity(final):
            raise MastermindXCaptureError(
                "installed checkout changed before final snapshot"
            )
        _validate_slot(
            scheduled=scheduled,
            attempted=attempted,
            capture_event=capture_event,
            completed=completed,
        )
        payload: dict[str, Any] = {
            "schema": SOURCE_SCHEMA,
            "attestation_id": None,
            "mode": MODE,
            "authentication_basis": AUTHENTICATION_BASIS,
            "comparison_system": COMPARISON_SYSTEM,
            "scheduled_at": utc_text(scheduled),
            "attempted_at": utc_text(attempted),
            "completed_at": utc_text(completed),
            "capture_event_at": utc_text(capture_event),
            "disposition": DISPOSITION,
            "emitted_enrollment_event_count": 0,
            "emitted_enrollment_event_ids": [],
            "producer_rule_sha256": producer_rule_sha256(release_policy),
            "release_policy_sha256": release_policy_sha256(release_policy),
            "checkout": checkout,
            "selector_registration": selector,
            "observation": _json_observation(),
            "claim_boundary": dict(CLAIM_BOUNDARY),
            "occurrence_trust": dict(OCCURRENCE_TRUST),
            "authority": dict(FALSE_AUTHORITY),
        }
        payload["attestation_id"] = _attestation_id(payload)
        result = validate_attestation(payload, release_policy=release_policy)
        validated_final = _checkout_attestation(OPS_CHECKOUT_ROOT, release_policy)
        if _snapshot_identity(final) != _snapshot_identity(validated_final):
            raise MastermindXCaptureError(
                "installed checkout changed during final validation"
            )
        terminal = _aware_utc(_runtime_now(), label="terminal_at")
        _validate_terminal_slot(
            scheduled=scheduled,
            completed=completed,
            terminal=terminal,
        )
        return result


__all__ = [
    "AUTHENTICATION_BASIS",
    "CaptureReleasePolicy",
    "COMPARISON_SYSTEM",
    "DISPOSITION",
    "MastermindXCaptureError",
    "SOURCE_SCHEMA",
    "build_mastermindx_capture_attestation",
    "canonical_json_bytes",
    "release_policy_sha256",
    "producer_rule_sha256",
    "strict_json_object",
    "validate_attestation",
]
