#!/usr/bin/env python3
"""Run one bounded, paper-only sparse-selector canary transition.

The operational surface is intentionally smaller than the selector engine.  It
has no configurable paths, no W1A input, no proposal authority, and no loop.  A
launch may claim one five-minute bucket and grant at most one new transition.
The durable bucket claim is written before the call, so a pre-WAL crash can
lose a slot.  A transition whose WAL authority was already sealed is the sole
exception: recovery re-enters ``advance`` with that exact original claim and
adopts the frozen transition without replanning another one.

This file imports only the standard library at module load.  The sealed runtime
and clean, receipted checkout are authenticated before repository paths and
site-packages are added for the delayed selector imports.  That ordering is
load-bearing for ``python -I -S`` operation.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo


EXPECTED_HOST_MODEL = "Mac13,1"
EXPECTED_MACHINE = "arm64"
THETA_HOST = "127.0.0.1"
THETA_PORT = 25503
THETA_TIMEOUT_SECONDS = 2.0

EXPECTED_REPO_ROOT = Path("/Users/chriswong/options-sparse-selector-ops-wt")
CANONICAL_ORIGIN_URL = "git@github.com:mastermindx-market-intelligence/macro.git"
CANONICAL_ORIGIN_REF = "refs/remotes/origin/main"
GIT = Path("/usr/bin/git")
SSH = Path("/usr/bin/ssh")
DEPLOY_KEY = Path("/Users/chriswong/.ssh/macro_dashboard_deploy")
GIT_SSH_COMMAND = (
    f"{SSH} -i {DEPLOY_KEY} -o IdentitiesOnly=yes -o BatchMode=yes"
)

SELECTOR_ROOT = Path(
    "/Users/chriswong/.mastermind_private/options_sparse_selector_v1"
)
OPS_ROOT = Path(
    "/Users/chriswong/.mastermind_private/options_sparse_selector_ops_v1"
)
MARK_ROOT = Path(
    "/Users/chriswong/.mastermind_private/prophet_option_mark_observations_v1"
)
LIFECYCLE_ROOT = Path(
    "/Users/chriswong/.mastermind_private/prophet_option_shadow_lifecycle_v1"
)
W1A_RECEIPT_ROOT: None = None
PROPOSALS_ARMED = False

RUNTIME_ROOT = Path(
    "/Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v1"
)
RUNTIME_MANIFEST = RUNTIME_ROOT / "runtime_closure.json"
RUNTIME_MARKER = RUNTIME_ROOT / ".options_sparse_selector_persistent_runtime_root"
RUNTIME_MARKER_BODY = b"options.sparse_selector.persistent_runtime_root/v1\n"
RUNTIME_MARKER_SHA256 = (
    "3a340239f359c167e295cb14f4182b33765d6017d12b3b11e131e29939b993fc"
)
RUNTIME_PYTHON = RUNTIME_ROOT / "runtime/bin/python3.12"
RUNTIME_SITE_PACKAGES = RUNTIME_ROOT / "runtime/lib/python3.12/site-packages"
RECEIPTED_IMPORT_PATHS = (
    "engine/options_sparse_selector.py",
    "engine/private_auth_dict.py",
    "scripts/run_options_sparse_selector.py",
    "ops/launchd/run_options_sparse_selector_verified.py",
)
VERIFIED_CARRIER_PATH = EXPECTED_REPO_ROOT / RECEIPTED_IMPORT_PATHS[-1]
EXPECTED_RUNTIME_SOURCE = Path("/Users/chriswong/miniconda3/envs/plane")
EXPECTED_RUNTIME_IMPORTS = (
    "attr",
    "attrs",
    "dateutil",
    "idna",
    "jsonschema",
    "jsonschema_specifications",
    "numpy",
    "pandas",
    "pyarrow",
    "pytz",
    "referencing",
    "rpds",
    "six",
    "typing_extensions",
)
MAX_RUNTIME_FILES = 100_000
MAX_RUNTIME_TREE_BYTES = 8 * 1024 * 1024 * 1024

PLIST_RELATIVE_PATH = "ops/launchd/com.mastermind.optionssparseselector.plist"
REPO_PLIST = EXPECTED_REPO_ROOT / PLIST_RELATIVE_PATH
INSTALLED_PLIST = Path(
    "/Users/chriswong/Library/LaunchAgents/com.mastermind.optionssparseselector.plist"
)

CAMPAIGNS_PATH = "data/options_signal_campaign/campaigns.jsonl"
EPISODES_PATH = "data/options_signal_episode/episodes.jsonl"
CHECKPOINT_PATH = "data/options_signal_campaign/checkpoint.json"
SOURCE_PATHS = (CAMPAIGNS_PATH, EPISODES_PATH, CHECKPOINT_PATH)
MAX_SOURCE_BYTES = {
    CAMPAIGNS_PATH: 64 * 1024 * 1024,
    EPISODES_PATH: 64 * 1024 * 1024,
    CHECKPOINT_PATH: 4 * 1024 * 1024,
}

ACTIVATION_EXPIRES_AT = "2026-08-21T20:00:00Z"
MAX_HEAD_GENERATIONS = 128
HALT_AFTER_FIRST_SETTLED_MANIFEST = True
MIN_FREE_DISK_BYTES = 10 * 1024 * 1024 * 1024
WATCHDOG_SECONDS = 235
SLOT_SECONDS = 300
RTH_CONTRACT = "nyse_session_window_recurring_schedule/v1"

LOCK_NAME = "run.lock"
STATUS_NAME = "status.json"
HALT_NAME = "halt.json"
SLOT_CLAIM_NAME = "slot_claim.json"
TRANSITION_RECEIPT_DIRECTORY = "transitions"
STATUS_SCHEMA = "options.sparse_selector_operational_status/v1"
TRANSITION_SCHEMA = "options.sparse_selector_operational_transition/v1"
HALT_SCHEMA = "options.sparse_selector_operational_halt/v1"
SLOT_CLAIM_SCHEMA = "options.sparse_selector_operational_slot_claim/v1"
MODE = "paper_only_abstention_denominator_canary"
FALSE_AUTHORITY = {
    "may_issue": False,
    "may_publish_pick": False,
    "may_propose": False,
    "may_select": False,
    "may_trade": False,
}
ET = ZoneInfo("America/New_York")
_SHA1_RE = re.compile(r"[a-f0-9]{40}")


class RunnerError(RuntimeError):
    """The canary cannot prove a required operational invariant."""


class RunnerBusy(RunnerError):
    """Another fixed-path runner owns the outer singleton lock."""


@dataclass(frozen=True)
class RepositoryState:
    head_commit: str
    origin_main_commit: str
    origin_main_committed_at: str


@dataclass(frozen=True)
class SourceMaterial:
    commit: str
    observed_at: str
    bodies: Mapping[str, bytes]
    blob_oids: Mapping[str, str]


@dataclass(frozen=True)
class RuntimeBindings:
    core: ModuleType
    session_window_et: Callable[[str], tuple[datetime, datetime]]
    is_session: Callable[[Any], bool]


@dataclass(frozen=True)
class SessionGate:
    allowed: bool
    reason: str
    session_date: str | None


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunnerError("operational receipt is not canonical JSON") from exc


def _utc(value: datetime, *, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RunnerError(f"{label} is not timezone-aware")
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    clean = _utc(value, label="operational clock")
    return clean.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RunnerError(f"{label} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RunnerError(f"{label} is not canonical UTC") from exc
    precision = "microseconds" if "." in value else "seconds"
    normalized = parsed.astimezone(timezone.utc).isoformat(
        timespec=precision
    ).replace("+00:00", "Z")
    if normalized != value:
        raise RunnerError(f"{label} is not canonical UTC")
    return parsed


def _slot_id(value: datetime) -> str:
    epoch_seconds = int(_utc(value, label="slot clock").timestamp())
    bucket = epoch_seconds - (epoch_seconds % SLOT_SECONDS)
    return datetime.fromtimestamp(bucket, timezone.utc).strftime("%Y%m%dT%H%MZ")


def _safe_now(clock: Callable[[], datetime]) -> datetime:
    return _utc(clock(), label="real operational clock")


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _attest_directory(
    path: Path,
    *,
    label: str,
    mode: int,
    owner_uid: int | None = None,
) -> os.stat_result:
    if not path.is_absolute():
        raise RunnerError(f"{label} path is not absolute")
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise RunnerError(f"{label} is unavailable") from exc
    expected_uid = os.getuid() if owner_uid is None else owner_uid
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_uid != expected_uid
    ):
        raise RunnerError(f"{label} metadata is unsafe")
    return metadata


def _read_regular(
    path: Path,
    *,
    label: str,
    maximum: int,
    modes: frozenset[int] = frozenset({0o400, 0o600}),
) -> bytes:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise RunnerError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) not in modes
        or not 0 <= before.st_size <= maximum
    ):
        raise RunnerError(f"{label} metadata is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RunnerError(f"{label} cannot be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            raise RunnerError(f"{label} changed before read")
        body = bytearray()
        while len(body) <= maximum:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise RunnerError(f"{label} changed during read") from exc
    if (
        len(body) > maximum
        or _identity(opened) != _identity(after)
        or _identity(after) != _identity(current)
    ):
        raise RunnerError(f"{label} changed during read")
    return bytes(body)


def _host_model() -> str:
    try:
        completed = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.model"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RunnerError("host model cannot be attested") from exc
    return completed.stdout.decode("ascii", errors="strict").strip()


def _theta_probe() -> None:
    try:
        connection = socket.create_connection(
            (THETA_HOST, THETA_PORT), timeout=THETA_TIMEOUT_SECONDS
        )
    except OSError as exc:
        raise RunnerError("local Theta is unavailable") from exc
    connection.close()


def _attest_host() -> dict[str, Any]:
    model = _host_model()
    machine = platform.machine()
    if model != EXPECTED_HOST_MODEL or machine != EXPECTED_MACHINE:
        raise RunnerError("wrong target host")
    _theta_probe()
    return {
        "model": model,
        "machine": machine,
        "theta": {
            "host": THETA_HOST,
            "port": THETA_PORT,
            "reachable": True,
        },
    }


def _git_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment["LC_ALL"] = "C"
    environment["PATH"] = "/usr/bin:/bin"
    return environment


def _git(
    arguments: Sequence[str],
    *,
    check: bool = True,
    timeout: int = 60,
) -> subprocess.CompletedProcess[bytes]:
    command = [
        str(GIT),
        "-C",
        str(EXPECTED_REPO_ROOT),
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "protocol.file.allow=never",
        "-c",
        f"core.sshCommand={GIT_SSH_COMMAND}",
        *arguments,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RunnerError("authenticated Git command failed") from exc
    if check and result.returncode != 0:
        raise RunnerError("authenticated Git command was refused")
    return result


def _one_line(body: bytes, *, label: str) -> str:
    try:
        value = body.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RunnerError(f"{label} is not UTF-8") from exc
    if not value or "\n" in value or "\r" in value:
        raise RunnerError(f"{label} is malformed")
    return value


def _attest_repository() -> RepositoryState:
    _attest_directory(EXPECTED_REPO_ROOT, label="selector checkout", mode=0o755)
    _read_regular(
        DEPLOY_KEY,
        label="selector Git deploy key",
        maximum=64 * 1024,
        modes=frozenset({0o400, 0o600}),
    )
    top = _one_line(
        _git(["rev-parse", "--show-toplevel"]).stdout,
        label="selector checkout root",
    )
    if top != str(EXPECTED_REPO_ROOT):
        raise RunnerError("selector checkout root drifted")
    origin_url = _one_line(
        _git(["remote", "get-url", "origin"]).stdout,
        label="selector origin URL",
    )
    if origin_url != CANONICAL_ORIGIN_URL:
        raise RunnerError("selector origin is not canonical")
    dirty = _git(
        ["status", "--porcelain=v1", "--untracked-files=all"], timeout=30
    ).stdout
    if dirty:
        raise RunnerError("selector checkout is dirty")
    _git(
        [
            "fetch",
            "--quiet",
            "--no-tags",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        ],
        timeout=120,
    )
    # Reprove cleanliness after the only mutating Git operation.
    if _git(["status", "--porcelain=v1", "--untracked-files=all"]).stdout:
        raise RunnerError("selector checkout changed during fetch")
    head = _one_line(
        _git(["rev-parse", "--verify", "HEAD^{commit}"]).stdout,
        label="selector checkout HEAD",
    )
    origin = _one_line(
        _git(["rev-parse", "--verify", f"{CANONICAL_ORIGIN_REF}^{{commit}}"]).stdout,
        label="canonical origin/main",
    )
    if _SHA1_RE.fullmatch(head) is None or _SHA1_RE.fullmatch(origin) is None:
        raise RunnerError("selector Git commit identity is malformed")
    ancestry = _git(["merge-base", "--is-ancestor", head, origin], check=False)
    if ancestry.returncode != 0:
        raise RunnerError("selector checkout HEAD is not an origin/main ancestor")
    committed = _one_line(
        _git(["show", "-s", "--format=%cI", origin]).stdout,
        label="origin/main commit clock",
    )
    try:
        parsed = datetime.fromisoformat(committed)
    except ValueError as exc:
        raise RunnerError("origin/main commit clock is malformed") from exc
    if parsed.tzinfo is None:
        raise RunnerError("origin/main commit clock is not aware")
    return RepositoryState(
        head_commit=head,
        origin_main_commit=origin,
        origin_main_committed_at=_utc_text(parsed),
    )


def _git_blob_oid(body: bytes) -> str:
    digest = hashlib.sha1()  # noqa: S324 - this is the repository's Git OID
    digest.update(f"blob {len(body)}\0".encode("ascii"))
    digest.update(body)
    return digest.hexdigest()


def _read_source_blobs(commit: str) -> tuple[dict[str, bytes], dict[str, str]]:
    if _SHA1_RE.fullmatch(commit) is None:
        raise RunnerError("source commit identity is malformed")
    bodies: dict[str, bytes] = {}
    oids: dict[str, str] = {}
    for path in SOURCE_PATHS:
        tree = _git(["ls-tree", "-z", "--full-tree", commit, "--", path]).stdout
        expected_suffix = b"\t" + path.encode("utf-8") + b"\0"
        if tree.count(b"\0") != 1 or not tree.endswith(expected_suffix):
            raise RunnerError(f"source tree entry for {path} is not exact")
        header = tree[: -len(expected_suffix)]
        try:
            mode, kind, oid = header.decode("ascii").split(" ")
        except (UnicodeDecodeError, ValueError) as exc:
            raise RunnerError(f"source tree entry for {path} is malformed") from exc
        if mode != "100644" or kind != "blob" or _SHA1_RE.fullmatch(oid) is None:
            raise RunnerError(f"source tree entry for {path} is unsafe")
        body = _git(["cat-file", "blob", oid], timeout=60).stdout
        if len(body) > MAX_SOURCE_BYTES[path] or _git_blob_oid(body) != oid:
            raise RunnerError(f"source blob for {path} differs from its tree OID")
        bodies[path] = body
        oids[path] = oid
    # The ref may advance during reads, but the selected immutable commit must
    # still exist and the freshly fetched ref must not roll back.
    if _git(["cat-file", "-e", f"{commit}^{{commit}}"], check=False).returncode != 0:
        raise RunnerError("selected source commit disappeared after read")
    return bodies, oids


def _runtime_relative(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RunnerError(f"{label} path is malformed")
    parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise RunnerError(f"{label} path escapes the sealed runtime")
    return value


def _load_verified_carrier() -> ModuleType:
    name = "_options_sparse_selector_verified_carrier"
    spec = importlib.util.spec_from_file_location(name, VERIFIED_CARRIER_PATH)
    if spec is None or spec.loader is None:
        raise RunnerError("receipted runtime verifier cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(name, None)
        raise RunnerError("receipted runtime verifier import failed") from exc
    return module


def _attest_runtime_carrier(repository: RepositoryState) -> dict[str, Any]:
    _attest_directory(RUNTIME_ROOT, label="selector persistent runtime", mode=0o700)
    marker = _read_regular(
        RUNTIME_MARKER,
        label="selector persistent runtime marker",
        maximum=256,
        modes=frozenset({0o600}),
    )
    if (
        marker != RUNTIME_MARKER_BODY
        or hashlib.sha256(marker).hexdigest() != RUNTIME_MARKER_SHA256
    ):
        raise RunnerError("selector persistent runtime marker drifted")
    raw = _read_regular(
        RUNTIME_MANIFEST,
        label="selector runtime manifest",
        maximum=16 * 1024 * 1024,
        modes=frozenset({0o400, 0o600}),
    )
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerError("selector runtime manifest is malformed") from exc
    if not isinstance(manifest, dict) or _canonical_json(manifest) != raw:
        raise RunnerError("selector runtime manifest is not canonical")
    installation = manifest.get("installation")
    expected_installation = {
        "kind": "persistent",
        "target_root": str(RUNTIME_ROOT),
        "repo_root": str(EXPECTED_REPO_ROOT),
        "expected_release_sha": repository.head_commit,
        "release_sha": repository.head_commit,
        "marker": RUNTIME_MARKER.name,
        "marker_sha256": RUNTIME_MARKER_SHA256,
        "origin_url": CANONICAL_ORIGIN_URL,
        "deploy_key": str(DEPLOY_KEY),
        "deploy_key_sha256": hashlib.sha256(
            _read_regular(
                DEPLOY_KEY,
                label="selector Git deploy key",
                maximum=64 * 1024,
                modes=frozenset({0o400, 0o600}),
            )
        ).hexdigest(),
    }
    imports = manifest.get("repo_import_source_sha256")
    expected_keys = {
        "schema",
        "authority",
        "training",
        "profile",
        "source_runtime",
        "runtime",
        "timezone_database",
        "repo_import_source_sha256",
        "files",
        "imports",
        "native_signature",
        "native_dyld_loaded",
        "native_files",
        "installation",
    }
    expected_profile = {
        "model": EXPECTED_HOST_MODEL,
        "machine": EXPECTED_MACHINE,
        "theta": f"{THETA_HOST}:{THETA_PORT}",
        "python": str(EXPECTED_RUNTIME_SOURCE / "bin/python3.12"),
    }
    if (
        set(manifest) != expected_keys
        or manifest.get("schema") != "options.sparse_selector_runtime_carrier/v2"
        or manifest.get("authority") is not False
        or manifest.get("training") is not False
        or manifest.get("profile") != expected_profile
        or manifest.get("source_runtime") != str(EXPECTED_RUNTIME_SOURCE)
        or manifest.get("runtime") != "runtime"
        or manifest.get("timezone_database") != "share/zoneinfo"
        or manifest.get("imports") != list(EXPECTED_RUNTIME_IMPORTS)
        or manifest.get("native_signature") != "adhoc"
        or installation != expected_installation
        or not isinstance(imports, dict)
        or set(imports) != set(RECEIPTED_IMPORT_PATHS)
    ):
        raise RunnerError("selector runtime installation receipt drifted")
    for relative in RECEIPTED_IMPORT_PATHS:
        path = EXPECTED_REPO_ROOT / relative
        body = _read_regular(
            path,
            label="receipted selector import",
            maximum=16 * 1024 * 1024,
            modes=frozenset({0o400, 0o444, 0o600, 0o644}),
        )
        if imports.get(relative) != hashlib.sha256(body).hexdigest():
            raise RunnerError("receipted selector import bytes drifted")
    files = manifest.get("files")
    if (
        not isinstance(files, list)
        or not 0 < len(files) <= MAX_RUNTIME_FILES
    ):
        raise RunnerError("selector runtime file census is malformed")
    paths: list[str] = []
    total_bytes = 0
    by_path: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "sha256",
            "bytes",
            "mode",
        }:
            raise RunnerError("selector runtime file receipt is malformed")
        relative = _runtime_relative(item.get("path"), label="runtime file")
        size = item.get("bytes")
        mode = item.get("mode")
        digest = item.get("sha256")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
            or type(size) is not int
            or not 0 <= size <= 512 * 1024 * 1024
            or mode not in {0o444, 0o555}
        ):
            raise RunnerError("selector runtime file receipt fields drifted")
        paths.append(relative)
        total_bytes += size
        by_path[relative] = item
    if (
        paths != sorted(paths)
        or len(paths) != len(set(paths))
        or total_bytes > MAX_RUNTIME_TREE_BYTES
        or by_path.get("bin/python3.12", {}).get("mode") != 0o555
        or "share/zoneinfo/America/New_York" not in by_path
    ):
        raise RunnerError("selector runtime file census identity drifted")
    native_files = manifest.get("native_files")
    native_loaded = manifest.get("native_dyld_loaded")
    if (
        not isinstance(native_files, list)
        or not native_files
        or len(native_files) != len(set(native_files))
        or any(
            _runtime_relative(item, label="runtime native") not in by_path
            or by_path[item]["mode"] != 0o555
            for item in native_files
        )
        or type(native_loaded) is not int
        or native_loaded != len(native_files) - 1
    ):
        raise RunnerError("selector runtime native census drifted")
    carrier = _load_verified_carrier()
    carrier_paths = tuple(
        path.as_posix() for path in carrier.REPO_IMPORT_SOURCE_PATHS
    )
    if (
        carrier.MANIFEST_SCHEMA != "options.sparse_selector_runtime_carrier/v2"
        or tuple(carrier.RUNTIME_REQUIRED_IMPORTS) != EXPECTED_RUNTIME_IMPORTS
        or carrier_paths != RECEIPTED_IMPORT_PATHS
        or carrier.MAX_FILES != MAX_RUNTIME_FILES
        or carrier.MAX_TREE_BYTES != MAX_RUNTIME_TREE_BYTES
    ):
        raise RunnerError("receipted runtime verifier contract drifted")
    try:
        carrier._attest_sealed_tree(RUNTIME_ROOT / "runtime", files)
    except Exception as exc:
        raise RunnerError("sealed runtime differs from its full manifest") from exc
    if _read_regular(
        RUNTIME_MANIFEST,
        label="reproved selector runtime manifest",
        maximum=16 * 1024 * 1024,
        modes=frozenset({0o400, 0o600}),
    ) != raw:
        raise RunnerError("selector runtime manifest changed during attestation")
    try:
        executable = Path(sys.executable).resolve(strict=True)
    except OSError as exc:
        raise RunnerError("running selector Python is unavailable") from exc
    if executable != RUNTIME_PYTHON:
        raise RunnerError("runner is not executing from the sealed runtime")
    _attest_directory(
        RUNTIME_SITE_PACKAGES,
        label="selector sealed site-packages",
        mode=0o555,
    )
    return {
        "manifest_path": str(RUNTIME_MANIFEST),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "manifest_bytes": len(raw),
        "file_count": len(files),
        "file_bytes": total_bytes,
        "native_file_count": len(native_files),
        "release_sha": repository.head_commit,
    }


def _load_runtime() -> RuntimeBindings:
    # ``-I -S`` intentionally starts without the checkout or sealed packages.
    # Add only the two authenticated roots after carrier attestation.
    for path in (str(RUNTIME_SITE_PACKAGES), str(EXPECTED_REPO_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    from engine import options_sparse_selector as core
    from engine.session_digest import session_window_et
    from lib.nyse_calendar import is_session

    if (
        getattr(core, "SELECTOR_RUNTIME_ARMED", None) is not True
        or getattr(core, "SELECTOR_PROPOSALS_ARMED", None) is not False
        or PROPOSALS_ARMED is not False
        or W1A_RECEIPT_ROOT is not None
    ):
        raise RunnerError("selector code-only activation rails drifted")
    return RuntimeBindings(
        core=core,
        session_window_et=session_window_et,
        is_session=is_session,
    )


def _private_directory_receipt(path: Path, metadata: os.stat_result) -> dict[str, Any]:
    return {
        "path": str(path),
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "uid": metadata.st_uid,
        "mode": stat.S_IMODE(metadata.st_mode),
    }


def _attest_evidence_roots() -> dict[str, Any]:
    mark = _attest_directory(MARK_ROOT, label="selector mark root", mode=0o700)
    lifecycle = _attest_directory(
        LIFECYCLE_ROOT, label="selector lifecycle root", mode=0o700
    )
    return {
        "w1a": None,
        "mark": _private_directory_receipt(MARK_ROOT, mark),
        "lifecycle": _private_directory_receipt(LIFECYCLE_ROOT, lifecycle),
    }


def _attest_disk() -> int:
    parent = SELECTOR_ROOT.parent
    _attest_directory(parent, label="selector private parent", mode=0o700)
    try:
        free = shutil.disk_usage(parent).free
    except OSError as exc:
        raise RunnerError("selector private disk cannot be measured") from exc
    if free < MIN_FREE_DISK_BYTES:
        raise RunnerError("selector private disk reserve is below 10 GiB")
    return free


def _attest_installed_plist() -> dict[str, Any]:
    modes = frozenset({0o400, 0o444, 0o600, 0o644})
    repo_body = _read_regular(
        REPO_PLIST,
        label="selector release launchd plist",
        maximum=1024 * 1024,
        modes=modes,
    )
    installed_body = _read_regular(
        INSTALLED_PLIST,
        label="selector installed launchd plist",
        maximum=1024 * 1024,
        modes=modes,
    )
    if installed_body != repo_body:
        raise RunnerError("installed selector launchd plist differs from its release")
    try:
        payload = plistlib.loads(repo_body)
    except Exception as exc:
        raise RunnerError("selector launchd plist is malformed") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("Label") != "com.mastermind.optionssparseselector"
        or payload.get("StartInterval") != 300
        or payload.get("KeepAlive") is not False
        or "RunAtLoad" in payload
        or "EnvironmentVariables" in payload
    ):
        raise RunnerError("selector launchd plist contract drifted")
    return {
        "repo_path": str(REPO_PLIST),
        "installed_path": str(INSTALLED_PLIST),
        "sha256": hashlib.sha256(repo_body).hexdigest(),
        "bytes": len(repo_body),
        "exact_release_match": True,
    }


def _session_gate(now: datetime, runtime: RuntimeBindings) -> SessionGate:
    scheduled = _utc(now, label="scheduled selector clock")
    ending = scheduled + timedelta(seconds=WATCHDOG_SECONDS)
    local = scheduled.astimezone(ET)
    ending_local = ending.astimezone(ET)
    session_date = local.date()
    if not runtime.is_session(session_date):
        return SessionGate(False, "NON_NYSE_SESSION", session_date.isoformat())
    opened, closed = runtime.session_window_et(session_date.isoformat())
    if not (opened <= local < closed):
        return SessionGate(False, "OUTSIDE_NYSE_RTH", session_date.isoformat())
    if ending_local.date() != session_date or not (opened <= ending_local < closed):
        return SessionGate(False, "WATCHDOG_CROSSES_NYSE_RTH_CLOSE", session_date.isoformat())
    return SessionGate(True, "IN_NYSE_RTH", session_date.isoformat())


def _ensure_ops_root() -> None:
    parent = OPS_ROOT.parent
    _attest_directory(parent, label="selector ops parent", mode=0o700)
    try:
        os.mkdir(OPS_ROOT, 0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise RunnerError("selector ops root cannot be created") from exc
    _attest_directory(OPS_ROOT, label="selector ops root", mode=0o700)


@contextmanager
def _ops_lock() -> Iterator[None]:
    _ensure_ops_root()
    path = OPS_ROOT / LOCK_NAME
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RunnerError("selector ops lock cannot be opened") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise RunnerError("selector ops lock metadata is unsafe")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RunnerBusy("selector runner is already active") from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)


def _deadline_handler(_signum: int, _frame: object) -> None:
    raise RunnerError("selector runner exceeded its 235-second watchdog")


@contextmanager
def _deadline() -> Iterator[None]:
    if not hasattr(signal, "SIGALRM"):
        raise RunnerError("selector watchdog is unavailable")
    previous = signal.signal(signal.SIGALRM, _deadline_handler)
    signal.alarm(WATCHDOG_SECONDS)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_receipt(name: str, value: Mapping[str, Any]) -> None:
    if name not in {STATUS_NAME, HALT_NAME, SLOT_CLAIM_NAME}:
        raise RunnerError("operational receipt target is not registered")
    body = _canonical_json(value)
    target = OPS_ROOT / name
    temporary = OPS_ROOT / f".{name}.{os.getpid()}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(temporary, flags, 0o600)
        try:
            offset = 0
            while offset < len(body):
                offset += os.write(descriptor, body[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
        _fsync_directory(OPS_ROOT)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RunnerError("operational receipt cannot be published atomically") from exc


def _read_canonical_receipt(name: str, *, schema: str) -> dict[str, Any] | None:
    path = OPS_ROOT / name
    if not path.exists():
        return None
    raw = _read_regular(path, label=f"selector {name}", maximum=1024 * 1024)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"selector {name} is malformed") from exc
    if (
        not isinstance(value, dict)
        or _canonical_json(value) != raw
        or value.get("schema") != schema
        or value.get("authority") != FALSE_AUTHORITY
        or value.get("mode") != MODE
    ):
        raise RunnerError(f"selector {name} drifted")
    return value


def _read_slot_claim() -> dict[str, Any] | None:
    value = _read_canonical_receipt(SLOT_CLAIM_NAME, schema=SLOT_CLAIM_SCHEMA)
    if value is None:
        return None
    if set(value) != {
        "schema",
        "mode",
        "slot_id",
        "scheduled_at",
        "claimed_at",
        "source_commit",
        "parent_head_id",
        "parent_generation",
        "authority",
    }:
        raise RunnerError("selector slot claim shape drifted")
    scheduled = _parse_utc(value.get("scheduled_at"), label="slot scheduled clock")
    claimed = _parse_utc(value.get("claimed_at"), label="slot claim clock")
    if (
        value.get("slot_id") != _slot_id(scheduled)
        or claimed != scheduled
        or _SHA1_RE.fullmatch(str(value.get("source_commit"))) is None
        or (
            value.get("parent_head_id") is not None
            and re.fullmatch(r"ossh_[a-f0-9]{64}", value["parent_head_id"])
            is None
        )
        or type(value.get("parent_generation")) is not int
        or value["parent_generation"] < 0
        or (value["parent_head_id"] is None) != (value["parent_generation"] == 0)
    ):
        raise RunnerError("selector slot claim semantics drifted")
    return value


def _claim_slot(
    *,
    scheduled_at: datetime,
    source_commit: str,
    parent_head: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    requested = _slot_id(scheduled_at)
    previous = _read_slot_claim()
    if previous is not None and requested <= previous["slot_id"]:
        return previous, False
    claim = {
        "schema": SLOT_CLAIM_SCHEMA,
        "mode": MODE,
        "slot_id": requested,
        "scheduled_at": _utc_text(scheduled_at),
        "claimed_at": _utc_text(scheduled_at),
        "source_commit": source_commit,
        "parent_head_id": None if parent_head is None else parent_head["head_id"],
        "parent_generation": 0 if parent_head is None else parent_head["generation"],
        "authority": dict(FALSE_AUTHORITY),
    }
    _atomic_receipt(SLOT_CLAIM_NAME, claim)
    return claim, True


def _evidence_inputs(core: ModuleType) -> Any:
    if W1A_RECEIPT_ROOT is not None or PROPOSALS_ARMED is not False:
        raise RunnerError("canary proposal boundary is not structurally closed")
    value = core.EvidenceInputs(
        w1a_receipt_root=None,
        mark_root=MARK_ROOT,
        lifecycle_root=LIFECYCLE_ROOT,
    )
    if getattr(value, "w1a_receipt_root", object()) is not None:
        raise RunnerError("selector EvidenceInputs admitted W1A")
    return value


def _selector_snapshot(core: ModuleType, evidence_inputs: Any) -> dict[str, Any]:
    public = core.status(SELECTOR_ROOT, evidence_inputs=evidence_inputs)
    if public.get("runtime_armed") is not True or public.get("proposals_armed") is not False:
        raise RunnerError("selector runtime status escaped code-only rails")
    head = public.get("head")
    recovery_intent = public.get("recovery_intent") is True
    recovery_head = public.get("intent_next_head") if recovery_intent else None
    decisions: list[dict[str, Any]] = []
    if public.get("initialized"):
        if head is None and not recovery_intent:
            raise RunnerError("initialized selector status lacks a HEAD")
        if head is not None and not isinstance(head, dict):
            raise RunnerError("initialized selector status has a malformed HEAD")
        if recovery_intent and (
            not isinstance(recovery_head, dict)
            or public.get("intent_next_head_id") != recovery_head.get("head_id")
        ):
            raise RunnerError("selector recovery status lacks its exact target HEAD")
        # core.status authenticates/reconstructs a durable intent.  The
        # explicit recovery allowance then authenticates the complete live
        # parent graph without pretending the WAL is absent, so proposal poison
        # is checked both before adoption and after advance.
        if head is not None:
            authenticate_kwargs = {"evidence_inputs": evidence_inputs}
            if recovery_intent:
                authenticate_kwargs["_allow_durable_intent"] = True
            authenticated, decisions, _body = core.authenticate_store(
                SELECTOR_ROOT, **authenticate_kwargs
            )
            if authenticated != head:
                raise RunnerError("selector public and authenticated HEAD differ")
    elif head is not None:
        raise RunnerError("uninitialized selector status carries a HEAD")
    if head is not None:
        proposal_count = head.get("proposal_session_count")
        if proposal_count != 0:
            raise RunnerError("selector HEAD contains proposal state")
    if recovery_head is not None and recovery_head.get("proposal_session_count") != 0:
        raise RunnerError("selector recovery target contains proposal state")
    if any(decision.get("action") == "propose" for decision in decisions):
        raise RunnerError("selector store contains a propose action")
    if any(decision.get("action") != "abstain" for decision in decisions):
        raise RunnerError("selector store contains an unregistered action")
    return {
        "public": public,
        "head": head,
        "recovery_head": recovery_head,
        "decisions": decisions,
    }


def _effective_head(snapshot: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = snapshot.get("recovery_head") or snapshot.get("head")
    return value if isinstance(value, Mapping) else None


def _head_receipt(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    head = _effective_head(snapshot)
    if head is None:
        return None
    return {
        "head_id": head["head_id"],
        "previous_head_id": head["previous_head_id"],
        "generation": head["generation"],
        "advanced_at": head["advanced_at"],
        "cycle_count": head["cycle_count"],
        "source_phase": head["source_phase"],
        "source_commit": head["source_commit"],
        "source_observed_at": head["source_observed_at"],
        "source_campaign_prefix": dict(head["source_campaign_prefix"]),
        "source_episode_prefix": dict(head["source_episode_prefix"]),
        "source_checkpoint": dict(head["source_checkpoint"]),
        "candidate_count": head["candidate_count"],
        "decision_count": head["decision_count"],
        "pending_manifest": head["pending_manifest"],
        "proposal_session_count": head["proposal_session_count"],
    }


def _status_source_receipt(
    *,
    snapshot: Mapping[str, Any],
    source: SourceMaterial | None,
    source_mode: str | None,
) -> dict[str, Any] | None:
    head = _effective_head(snapshot)
    if head is not None:
        prefixes = {
            "campaigns": dict(head["source_campaign_prefix"]),
            "episodes": dict(head["source_episode_prefix"]),
            "checkpoint": dict(head["source_checkpoint"]),
        }
        blob_oids = {
            CAMPAIGNS_PATH: prefixes["campaigns"]["git_blob_oid"],
            EPISODES_PATH: prefixes["episodes"]["git_blob_oid"],
            CHECKPOINT_PATH: prefixes["checkpoint"]["git_blob_oid"],
        }
        if source is not None and (
            source.commit != head["source_commit"]
            or dict(source.blob_oids) != blob_oids
        ):
            raise RunnerError("status source differs from authenticated selector HEAD")
        return {
            "mode": "AUTHENTICATED_RECOVERY_TARGET"
            if snapshot.get("recovery_head") is not None
            else "AUTHENTICATED_HEAD",
            "selection_mode": source_mode,
            "commit": head["source_commit"],
            "observed_at": head["source_observed_at"],
            "blob_oids": blob_oids,
            "prefixes": prefixes,
        }
    if source is None:
        return None
    return {
        "mode": source_mode,
        "selection_mode": source_mode,
        "commit": source.commit,
        "observed_at": source.observed_at,
        "blob_oids": dict(source.blob_oids),
        "prefixes": None,
    }


def _active_epoch(snapshot: Mapping[str, Any]) -> bool:
    head = snapshot.get("recovery_head") or snapshot.get("head")
    if head is None:
        return False
    return bool(
        snapshot["public"].get("recovery_intent")
        or head.get("source_phase") != "DRAINED"
        or head.get("pending_manifest") is not None
        or head.get("decision_count") != head.get("candidate_count")
    )


def _select_source(
    *,
    repository: RepositoryState,
    snapshot: Mapping[str, Any],
    clock: Callable[[], datetime],
) -> tuple[SourceMaterial | None, str]:
    head = snapshot.get("recovery_head") or snapshot.get("head")
    if _active_epoch(snapshot):
        commit = head["source_commit"]
        ancestry = _git(
            ["merge-base", "--is-ancestor", commit, repository.origin_main_commit],
            check=False,
        )
        if ancestry.returncode != 0:
            raise RunnerError("active selector source commit left origin/main ancestry")
        bodies, oids = _read_source_blobs(commit)
        expected = {
            CAMPAIGNS_PATH: head["source_campaign_prefix"]["git_blob_oid"],
            EPISODES_PATH: head["source_episode_prefix"]["git_blob_oid"],
            CHECKPOINT_PATH: head["source_checkpoint"]["git_blob_oid"],
        }
        if oids != expected:
            raise RunnerError("active selector source epoch differs from its HEAD")
        return (
            SourceMaterial(
                commit=commit,
                observed_at=head["source_observed_at"],
                bodies=bodies,
                blob_oids=oids,
            ),
            "PINNED_ACTIVE_EPOCH",
        )
    bodies, oids = _read_source_blobs(repository.origin_main_commit)
    # Reprove the remote ref after reading all three immutable objects.  A move
    # requires a later launch; mixing the old/new ref in one observation is forbidden.
    live_ref = _one_line(
        _git(["rev-parse", "--verify", f"{CANONICAL_ORIGIN_REF}^{{commit}}"]).stdout,
        label="reproved origin/main",
    )
    if live_ref != repository.origin_main_commit:
        raise RunnerError("origin/main advanced during source observation")
    if head is not None:
        previous_oids = {
            CAMPAIGNS_PATH: head["source_campaign_prefix"]["git_blob_oid"],
            EPISODES_PATH: head["source_episode_prefix"]["git_blob_oid"],
            CHECKPOINT_PATH: head["source_checkpoint"]["git_blob_oid"],
        }
        if oids == previous_oids:
            return None, "DRAINED_SOURCE_UNCHANGED"
    observed_at = _utc_text(_safe_now(clock))
    return (
        SourceMaterial(
            commit=repository.origin_main_commit,
            observed_at=observed_at,
            bodies=bodies,
            blob_oids=oids,
        ),
        "FRESH_SOURCE_EPOCH",
    )


def _source_snapshot(core: ModuleType, source: SourceMaterial) -> Any:
    return core.SourceSnapshot(
        commit=source.commit,
        campaigns_raw=source.bodies[CAMPAIGNS_PATH],
        episodes_raw=source.bodies[EPISODES_PATH],
        observed_at=source.observed_at,
        campaigns_blob_oid=source.blob_oids[CAMPAIGNS_PATH],
        episodes_blob_oid=source.blob_oids[EPISODES_PATH],
        checkpoint_raw=source.bodies[CHECKPOINT_PATH],
        checkpoint_blob_oid=source.blob_oids[CHECKPOINT_PATH],
    )


def _status_receipt(
    *,
    recorded_at: datetime,
    outcome: str,
    reason: str,
    repository: RepositoryState,
    snapshot: Mapping[str, Any],
    source: SourceMaterial | None,
    source_mode: str | None,
    session: SessionGate | None,
    slot_claim: Mapping[str, Any] | None,
    halted: bool,
    operational_proof: Mapping[str, Any] | None = None,
    immutable_transition_receipt: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": STATUS_SCHEMA,
        "mode": MODE,
        "recorded_at": _utc_text(recorded_at),
        "outcome": outcome,
        "reason": reason,
        "activation_expires_at": ACTIVATION_EXPIRES_AT,
        "proposal_capability": False,
        "w1a_receipt_root": None,
        "halted": halted,
        "repository": {
            "head_commit": repository.head_commit,
            "origin_main_commit": repository.origin_main_commit,
            "origin_main_committed_at": repository.origin_main_committed_at,
        },
        "source": _status_source_receipt(
            snapshot=snapshot,
            source=source,
            source_mode=source_mode,
        ),
        "session": None
        if session is None
        else {
            "contract": RTH_CONTRACT,
            "allowed": session.allowed,
            "reason": session.reason,
            "session_date": session.session_date,
        },
        "slot_claim": None if slot_claim is None else dict(slot_claim),
        "selector": _head_receipt(snapshot),
        "operational_proof": None
        if operational_proof is None
        else dict(operational_proof),
        "immutable_transition_receipt": immutable_transition_receipt,
        "authority": dict(FALSE_AUTHORITY),
    }


def _publish_status(**kwargs: Any) -> dict[str, Any]:
    receipt = _status_receipt(**kwargs)
    _atomic_receipt(STATUS_NAME, receipt)
    return receipt


def _transition_proof(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    required = {"host", "runtime", "evidence_roots", "launchd"}
    if not required <= set(value):
        raise RunnerError("immutable transition operational proof is incomplete")
    return {key: value[key] for key in sorted(required)}


def _transition_value(
    *,
    snapshot: Mapping[str, Any],
    slot_claim: Mapping[str, Any],
    operational_proof: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema": TRANSITION_SCHEMA,
        "mode": MODE,
        "resulting_head": _head_receipt(snapshot),
        "source": _status_source_receipt(
            snapshot=snapshot,
            source=None,
            source_mode="AUTHENTICATED_HEAD",
        ),
        "slot_claim": dict(slot_claim),
        "operational_proof": _transition_proof(operational_proof),
        "authority": dict(FALSE_AUTHORITY),
    }


def _validate_transition_claim(
    *,
    head: Mapping[str, Any],
    slot_claim: Mapping[str, Any],
    runtime: RuntimeBindings,
) -> None:
    required = {
        "schema",
        "mode",
        "slot_id",
        "scheduled_at",
        "claimed_at",
        "source_commit",
        "parent_head_id",
        "parent_generation",
        "authority",
    }
    if set(slot_claim) != required:
        raise RunnerError("transition slot claim shape drifted")
    scheduled = _parse_utc(
        slot_claim.get("scheduled_at"), label="transition scheduled clock"
    )
    claimed = _parse_utc(
        slot_claim.get("claimed_at"), label="transition claim clock"
    )
    advanced = _parse_utc(head.get("advanced_at"), label="transition HEAD clock")
    if (
        slot_claim.get("schema") != SLOT_CLAIM_SCHEMA
        or slot_claim.get("mode") != MODE
        or slot_claim.get("authority") != FALSE_AUTHORITY
        or slot_claim.get("slot_id") != _slot_id(scheduled)
        or claimed != scheduled
        or slot_claim.get("source_commit") != head.get("source_commit")
        or slot_claim.get("parent_head_id") != head.get("previous_head_id")
        or slot_claim.get("parent_generation") != head.get("generation") - 1
        or not _session_gate(scheduled, runtime).allowed
        or advanced < scheduled
        or advanced >= scheduled + timedelta(seconds=SLOT_SECONDS)
    ):
        raise RunnerError("transition slot claim does not bind its resulting HEAD")


def _repair_linked_transition_temp(
    *, target: Path, head_id: str, directory: Path
) -> None:
    try:
        metadata = os.lstat(target)
    except OSError as exc:
        raise RunnerError("immutable transition target is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink not in {1, 2}
    ):
        raise RunnerError("immutable transition target metadata is unsafe")
    if metadata.st_nlink == 1:
        return
    pattern = re.compile(rf"\.transition\.{re.escape(head_id)}\.\d+\.tmp")
    matches: list[Path] = []
    try:
        entries = list(OPS_ROOT.iterdir())
    except OSError as exc:
        raise RunnerError("selector ops root cannot repair transition link") from exc
    for entry in entries:
        if pattern.fullmatch(entry.name) is None:
            continue
        linked = os.lstat(entry)
        if (
            not stat.S_ISREG(linked.st_mode)
            or stat.S_ISLNK(linked.st_mode)
            or (linked.st_dev, linked.st_ino) != (metadata.st_dev, metadata.st_ino)
            or linked.st_uid != os.getuid()
            or stat.S_IMODE(linked.st_mode) != 0o600
        ):
            raise RunnerError("stranded transition temp does not bind its target")
        matches.append(entry)
    if len(matches) != 1:
        raise RunnerError("immutable transition hard-link repair is ambiguous")
    try:
        matches[0].unlink()
        _fsync_directory(OPS_ROOT)
        _fsync_directory(directory)
        repaired = os.lstat(target)
    except OSError as exc:
        raise RunnerError("immutable transition hard-link repair failed") from exc
    if (
        repaired.st_nlink != 1
        or (repaired.st_dev, repaired.st_ino) != (metadata.st_dev, metadata.st_ino)
    ):
        raise RunnerError("immutable transition hard-link repair was not exact")


def _write_transition_receipt(
    *,
    snapshot: Mapping[str, Any],
    slot_claim: Mapping[str, Any],
    operational_proof: Mapping[str, Any] | None,
) -> str:
    if not isinstance(snapshot, Mapping):
        raise RunnerError("immutable transition lacks a selector snapshot")
    head = _effective_head(snapshot)
    if head is None or not isinstance(head.get("head_id"), str):
        raise RunnerError("immutable transition lacks a resulting HEAD")
    head_id = head["head_id"]
    if re.fullmatch(r"ossh_[a-f0-9]{64}", head_id) is None:
        raise RunnerError("immutable transition HEAD identity is malformed")
    directory = OPS_ROOT / TRANSITION_RECEIPT_DIRECTORY
    try:
        os.mkdir(directory, 0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise RunnerError("immutable transition directory cannot be created") from exc
    _attest_directory(
        directory, label="selector transition receipt directory", mode=0o700
    )
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        raise RunnerError("immutable transition directory cannot be enumerated") from exc
    names = [path.name for path in entries]
    if (
        len(names) > MAX_HEAD_GENERATIONS
        or any(re.fullmatch(r"ossh_[a-f0-9]{64}\.json", name) is None for name in names)
    ):
        raise RunnerError("immutable transition receipt census drifted")
    target = directory / f"{head_id}.json"
    relative = f"{TRANSITION_RECEIPT_DIRECTORY}/{head_id}.json"
    transition = _transition_value(
        snapshot=snapshot,
        slot_claim=slot_claim,
        operational_proof=operational_proof,
    )
    body = _canonical_json(transition)
    if target.exists():
        _repair_linked_transition_temp(
            target=target, head_id=head_id, directory=directory
        )
        if _read_regular(
            target,
            label="immutable selector transition receipt",
            maximum=1024 * 1024,
        ) != body:
            raise RunnerError("immutable transition receipt conflicts with its HEAD")
        _fsync_directory(directory)
    else:
        if len(names) >= MAX_HEAD_GENERATIONS:
            raise RunnerError("immutable transition receipt cap is exhausted")
        temporary = OPS_ROOT / f".transition.{head_id}.{os.getpid()}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(temporary, flags, 0o600)
            try:
                offset = 0
                while offset < len(body):
                    offset += os.write(descriptor, body[offset:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError:
                if _read_regular(
                    target,
                    label="raced immutable selector transition",
                    maximum=1024 * 1024,
                ) != body:
                    raise RunnerError(
                        "immutable transition receipt conflicts with its HEAD"
                    )
            _fsync_directory(directory)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise RunnerError("immutable transition receipt cannot be published") from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return relative


def _publish_transition_status(**kwargs: Any) -> dict[str, Any]:
    snapshot = kwargs.get("snapshot")
    slot_claim = kwargs.get("slot_claim")
    if not isinstance(snapshot, Mapping) or not isinstance(slot_claim, Mapping):
        raise RunnerError("immutable transition lacks its snapshot or slot claim")
    relative = _write_transition_receipt(
        snapshot=snapshot,
        slot_claim=slot_claim,
        operational_proof=kwargs.get("operational_proof"),
    )
    kwargs["immutable_transition_receipt"] = relative
    receipt = _status_receipt(**kwargs)
    _atomic_receipt(STATUS_NAME, receipt)
    return receipt


def _reconcile_current_transition(
    *,
    snapshot: Mapping[str, Any],
    slot_claim: Mapping[str, Any] | None,
    operational_proof: Mapping[str, Any],
    runtime: RuntimeBindings,
) -> str | None:
    if snapshot["public"].get("recovery_intent"):
        return None
    head = _effective_head(snapshot)
    if head is None:
        return None
    target = (
        OPS_ROOT
        / TRANSITION_RECEIPT_DIRECTORY
        / f"{head['head_id']}.json"
    )
    relative = f"{TRANSITION_RECEIPT_DIRECTORY}/{head['head_id']}.json"
    if target.exists():
        _repair_linked_transition_temp(
            target=target,
            head_id=head["head_id"],
            directory=target.parent,
        )
        raw = _read_regular(
            target,
            label="existing immutable selector transition",
            maximum=1024 * 1024,
        )
        try:
            existing = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RunnerError("existing immutable transition is malformed") from exc
        embedded_claim = existing.get("slot_claim") if isinstance(existing, dict) else None
        if (
            not isinstance(embedded_claim, Mapping)
            or _canonical_json(existing) != raw
            or existing
            != _transition_value(
                snapshot=snapshot,
                slot_claim=embedded_claim,
                operational_proof=operational_proof,
            )
        ):
            raise RunnerError("existing immutable transition conflicts with its HEAD")
        _validate_transition_claim(
            head=head,
            slot_claim=embedded_claim,
            runtime=runtime,
        )
        return relative
    if slot_claim is None or slot_claim.get("source_commit") != head["source_commit"]:
        raise RunnerError("authenticated HEAD lacks its exact transition slot claim")
    if (
        slot_claim.get("parent_head_id") != head.get("previous_head_id")
        or slot_claim.get("parent_generation") != head["generation"] - 1
    ):
        raise RunnerError("transition slot claim does not bind the HEAD parent")
    _validate_transition_claim(
        head=head,
        slot_claim=slot_claim,
        runtime=runtime,
    )
    prior_status = _read_canonical_receipt(STATUS_NAME, schema=STATUS_SCHEMA)
    prior_selector = None if prior_status is None else prior_status.get("selector")
    previous_head_id = head.get("previous_head_id")
    if prior_selector is not None and prior_selector.get("head_id") not in {
        previous_head_id,
        head["head_id"],
    }:
        raise RunnerError("current HEAD does not extend the previous operational status")
    return _write_transition_receipt(
        snapshot=snapshot,
        slot_claim=slot_claim,
        operational_proof=operational_proof,
    )


def _publish_halt(
    *,
    halted_at: datetime,
    reason: str,
    snapshot: Mapping[str, Any],
    slot_claim: Mapping[str, Any] | None,
) -> dict[str, Any]:
    existing = _read_canonical_receipt(HALT_NAME, schema=HALT_SCHEMA)
    if existing is not None:
        return existing
    receipt = {
        "schema": HALT_SCHEMA,
        "mode": MODE,
        "halted_at": _utc_text(halted_at),
        "reason": reason,
        "selector": _head_receipt(snapshot),
        "slot_claim": None if slot_claim is None else dict(slot_claim),
        "authority": dict(FALSE_AUTHORITY),
    }
    _atomic_receipt(HALT_NAME, receipt)
    return receipt


def _static_preflight() -> tuple[
    RepositoryState, RuntimeBindings, dict[str, Any]
]:
    if W1A_RECEIPT_ROOT is not None or PROPOSALS_ARMED is not False:
        raise RunnerError("canary compile-time proposal rails drifted")
    host = _attest_host()
    repository = _attest_repository()
    evidence = _attest_evidence_roots()
    free_bytes = _attest_disk()
    runtime_receipt = _attest_runtime_carrier(repository)
    launchd = _attest_installed_plist()
    runtime = _load_runtime()
    return repository, runtime, {
        "host": host,
        "runtime": runtime_receipt,
        "evidence_roots": evidence,
        "launchd": launchd,
        "private_disk_free_bytes": free_bytes,
    }


def run_once(
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
) -> dict[str, Any]:
    with _ops_lock(), _deadline():
        repository, runtime, operational_proof = _static_preflight()
        preflight_clock = _safe_now(clock)
        gate = _session_gate(preflight_clock, runtime)
        evidence = _evidence_inputs(runtime.core)
        snapshot = _selector_snapshot(runtime.core, evidence)
        prior_claim = _read_slot_claim()
        prior_halt = _read_canonical_receipt(HALT_NAME, schema=HALT_SCHEMA)
        current_transition = _reconcile_current_transition(
            snapshot=snapshot,
            slot_claim=prior_claim,
            operational_proof=operational_proof,
            runtime=runtime,
        )
        now = _safe_now(clock)
        if snapshot["public"].get("recovery_intent"):
            recovery_head = _effective_head(snapshot)
            if recovery_head is None or prior_claim is None:
                raise RunnerError("selector recovery lacks its original slot claim")
            if prior_claim["source_commit"] != recovery_head["source_commit"]:
                raise RunnerError("selector recovery slot source differs from its target")
            if (
                prior_claim["parent_head_id"]
                != recovery_head.get("previous_head_id")
                or prior_claim["parent_generation"]
                != recovery_head["generation"] - 1
            ):
                raise RunnerError("selector recovery slot does not bind its target parent")
            original_scheduled = _parse_utc(
                prior_claim["scheduled_at"], label="recovery scheduled clock"
            )
            recovery_gate = _session_gate(original_scheduled, runtime)
            if not recovery_gate.allowed:
                raise RunnerError("selector recovery claim was not sealed inside NYSE RTH")
            source, source_mode = _select_source(
                repository=repository,
                snapshot=snapshot,
                clock=clock,
            )
            if source is None or source.commit != prior_claim["source_commit"]:
                raise RunnerError("selector recovery source is unavailable or drifted")
            runtime.core.advance(
                private_root=SELECTOR_ROOT,
                source=_source_snapshot(runtime.core, source),
                evidence_inputs=evidence,
                scheduled_at=prior_claim["scheduled_at"],
                clock=clock,
            )
            after = _selector_snapshot(runtime.core, evidence)
            if after["public"].get("recovery_intent") or after["head"] is None:
                raise RunnerError("selector recovery did not publish its exact HEAD")
            after_head = after["head"]
            halted = False
            reason = "sealed_intent_recovered"
            if prior_halt is not None:
                halted = True
                reason = str(prior_halt["reason"])
            elif (
                HALT_AFTER_FIRST_SETTLED_MANIFEST
                and after_head["decision_count"] > 0
            ):
                halted = True
                reason = "first_settled_manifest"
            elif after_head["generation"] >= MAX_HEAD_GENERATIONS:
                halted = True
                reason = "generation_cap_reached"
            elif now >= _parse_utc(
                ACTIVATION_EXPIRES_AT, label="activation expiry"
            ):
                halted = True
                reason = "activation_expired"
            if halted and prior_halt is None:
                _publish_halt(
                    halted_at=_safe_now(clock),
                    reason=reason,
                    snapshot=after,
                    slot_claim=prior_claim,
                )
            return _publish_transition_status(
                recorded_at=_safe_now(clock),
                outcome="HALTED" if halted else "RECOVERED",
                reason=reason,
                repository=repository,
                snapshot=after,
                source=source,
                source_mode=source_mode,
                session=recovery_gate,
                slot_claim=prior_claim,
                halted=halted,
                operational_proof=operational_proof,
            )
        if prior_halt is not None:
            return _publish_status(
                recorded_at=now,
                outcome="HALTED",
                reason=str(prior_halt["reason"]),
                repository=repository,
                snapshot=snapshot,
                source=None,
                source_mode=None,
                session=gate,
                slot_claim=prior_claim,
                halted=True,
                operational_proof=operational_proof,
                immutable_transition_receipt=current_transition,
            )
        expires = _parse_utc(ACTIVATION_EXPIRES_AT, label="activation expiry")
        if now >= expires:
            _publish_halt(
                halted_at=now,
                reason="activation_expired",
                snapshot=snapshot,
                slot_claim=prior_claim,
            )
            return _publish_status(
                recorded_at=now,
                outcome="HALTED",
                reason="activation_expired",
                repository=repository,
                snapshot=snapshot,
                source=None,
                source_mode=None,
                session=gate,
                slot_claim=prior_claim,
                halted=True,
                operational_proof=operational_proof,
                immutable_transition_receipt=current_transition,
            )
        head = snapshot["head"]
        if head is not None and head["decision_count"] > 0:
            _publish_halt(
                halted_at=now,
                reason="first_settled_manifest",
                snapshot=snapshot,
                slot_claim=prior_claim,
            )
            return _publish_status(
                recorded_at=now,
                outcome="HALTED",
                reason="first_settled_manifest",
                repository=repository,
                snapshot=snapshot,
                source=None,
                source_mode=None,
                session=gate,
                slot_claim=prior_claim,
                halted=True,
                operational_proof=operational_proof,
                immutable_transition_receipt=current_transition,
            )
        if head is not None and head["generation"] >= MAX_HEAD_GENERATIONS:
            _publish_halt(
                halted_at=now,
                reason="generation_cap_reached",
                snapshot=snapshot,
                slot_claim=prior_claim,
            )
            return _publish_status(
                recorded_at=now,
                outcome="HALTED",
                reason="generation_cap_reached",
                repository=repository,
                snapshot=snapshot,
                source=None,
                source_mode=None,
                session=gate,
                slot_claim=prior_claim,
                halted=True,
                operational_proof=operational_proof,
                immutable_transition_receipt=current_transition,
            )
        # Re-evaluate at the actual pre-claim clock; a slow preflight may cross
        # a session boundary even though its first sample was inside RTH.
        scheduled_at = _safe_now(clock)
        gate = _session_gate(scheduled_at, runtime)
        if not gate.allowed:
            return _publish_status(
                recorded_at=scheduled_at,
                outcome="SKIPPED",
                reason=gate.reason,
                repository=repository,
                snapshot=snapshot,
                source=None,
                source_mode=None,
                session=gate,
                slot_claim=prior_claim,
                halted=False,
                operational_proof=operational_proof,
                immutable_transition_receipt=current_transition,
            )
        source, source_mode = _select_source(
            repository=repository,
            snapshot=snapshot,
            clock=clock,
        )
        if source is None:
            return _publish_status(
                recorded_at=_safe_now(clock),
                outcome="SKIPPED",
                reason=source_mode,
                repository=repository,
                snapshot=snapshot,
                source=None,
                source_mode=source_mode,
                session=gate,
                slot_claim=prior_claim,
                halted=False,
                operational_proof=operational_proof,
                immutable_transition_receipt=current_transition,
            )
        # Claim only after every source byte and the final ref have been proved.
        # scheduled_at is sampled fresh here, not the deterministic bucket floor.
        scheduled_at = _safe_now(clock)
        gate = _session_gate(scheduled_at, runtime)
        if not gate.allowed:
            return _publish_status(
                recorded_at=scheduled_at,
                outcome="SKIPPED",
                reason=gate.reason,
                repository=repository,
                snapshot=snapshot,
                source=source,
                source_mode=source_mode,
                session=gate,
                slot_claim=prior_claim,
                halted=False,
                operational_proof=operational_proof,
                immutable_transition_receipt=current_transition,
            )
        claim, claimed = _claim_slot(
            scheduled_at=scheduled_at,
            source_commit=source.commit,
            parent_head=_effective_head(snapshot),
        )
        if not claimed:
            return _publish_status(
                recorded_at=scheduled_at,
                outcome="SKIPPED",
                reason="SLOT_ALREADY_CLAIMED",
                repository=repository,
                snapshot=snapshot,
                source=source,
                source_mode=source_mode,
                session=gate,
                slot_claim=claim,
                halted=False,
                operational_proof=operational_proof,
                immutable_transition_receipt=current_transition,
            )
        runtime.core.advance(
            private_root=SELECTOR_ROOT,
            source=_source_snapshot(runtime.core, source),
            evidence_inputs=evidence,
            scheduled_at=_utc_text(scheduled_at),
            clock=clock,
        )
        after = _selector_snapshot(runtime.core, evidence)
        if after["public"].get("recovery_intent"):
            raise RunnerError("selector advance left a durable recovery intent")
        after_head = after["head"]
        if after_head is None:
            raise RunnerError("selector advance did not publish a HEAD")
        if after_head["generation"] > MAX_HEAD_GENERATIONS:
            raise RunnerError("selector advance crossed its generation cap")
        halted = False
        reason = "one_transition_committed"
        if HALT_AFTER_FIRST_SETTLED_MANIFEST and after_head["decision_count"] > 0:
            halted = True
            reason = "first_settled_manifest"
        elif after_head["generation"] >= MAX_HEAD_GENERATIONS:
            halted = True
            reason = "generation_cap_reached"
        if halted:
            _publish_halt(
                halted_at=_safe_now(clock),
                reason=reason,
                snapshot=after,
                slot_claim=claim,
            )
        return _publish_transition_status(
            recorded_at=_safe_now(clock),
            outcome="HALTED" if halted else "ADVANCED",
            reason=reason,
            repository=repository,
            snapshot=after,
            source=source,
            source_mode=source_mode,
            session=gate,
            slot_claim=claim,
            halted=halted,
            operational_proof=operational_proof,
        )


def report_status(
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
) -> dict[str, Any]:
    with _ops_lock(), _deadline():
        repository, runtime, operational_proof = _static_preflight()
        evidence = _evidence_inputs(runtime.core)
        snapshot = _selector_snapshot(runtime.core, evidence)
        claim = _read_slot_claim()
        halt = _read_canonical_receipt(HALT_NAME, schema=HALT_SCHEMA)
        current_transition = _reconcile_current_transition(
            snapshot=snapshot,
            slot_claim=claim,
            operational_proof=operational_proof,
            runtime=runtime,
        )
        now = _safe_now(clock)
        return _publish_status(
            recorded_at=now,
            outcome="HALTED" if halt is not None else "STATUS",
            reason="not_halted" if halt is None else str(halt["reason"]),
            repository=repository,
            snapshot=snapshot,
            source=None,
            source_mode=None,
            session=_session_gate(now, runtime),
            slot_claim=claim,
            halted=halt is not None,
            operational_proof=operational_proof,
            immutable_transition_receipt=current_transition,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--run-once", action="store_true")
    operation.add_argument("--status", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        receipt = run_once() if arguments.run_once else report_status()
    except RunnerBusy as exc:
        print(str(exc), file=sys.stderr)
        return 75
    except Exception as exc:  # fail closed for delayed engine validation errors
        print(f"sparse selector operational refusal: {exc}", file=sys.stderr)
        return 2
    print(_canonical_json(receipt).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
