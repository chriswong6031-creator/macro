"""Fail-closed reader for canonical private Prophet source blobs.

The two long-lived Prophet option processes need current ``main`` bytes even when
their executable checkout is deliberately pinned.  This module is the single
machine-authenticated Git seam for those reads.  It never consults an ambient
remote URL, SSH agent, user Git configuration, working-tree file, or public HTTP
fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import subprocess


_REPO = Path(__file__).resolve().parent.parent

CANONICAL_REPOSITORY_SSH = (
    "git@github.com:mastermindx-market-intelligence/macro.git"
)
CANONICAL_SOURCE_REF = "refs/heads/main"
CANONICAL_LOCAL_REF = "refs/prophet-b1/canonical-main"
CANONICAL_GIT_KEY_ENV = "PROPHET_CANONICAL_GIT_SSH_KEY"
ALLOWED_SOURCE_PATHS = frozenset(
    {
        "data/prophet/ledger.jsonl",
        "site/prophet/index.json",
    }
)
MAX_BLOB_BYTES = 32 * 1024 * 1024
MAX_KEY_BYTES = 64 * 1024

_GIT = "/usr/bin/git"
_SSH = "/usr/bin/ssh"
_OBJECT_ID_RE = re.compile(r"^[a-f0-9]{40}(?:[a-f0-9]{24})?$")


class CanonicalGitError(RuntimeError):
    """A canonical source could not be authenticated or read safely."""


@dataclass(frozen=True, slots=True)
class CanonicalGitBlob:
    """Exact bytes and immutable Git identity for one accepted source blob."""

    source_repository: str
    source_ref: str
    source_commit: str
    source_path: str
    blob_oid: str
    body: bytes

    @property
    def byte_count(self) -> int:
        return len(self.body)

    @property
    def digest(self) -> str:
        return sha256(self.body).hexdigest()


def _fail(message: str) -> CanonicalGitError:
    # Deliberately never attach subprocess stderr: SSH diagnostics can disclose
    # host, account, key path, agent, or local Git configuration details.
    return CanonicalGitError(message)


def _process_home() -> Path:
    try:
        return Path(pwd.getpwuid(os.geteuid()).pw_dir)
    except (KeyError, OSError) as exc:
        raise _fail("canonical Git process home is unavailable") from exc


def _require_private_key_directory(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise _fail("canonical Git private key directory is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise _fail("canonical Git private key directory must be a real directory")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise _fail("canonical Git private key directory must be owner-only")


def _deploy_key() -> Path:
    raw = os.environ.get(CANONICAL_GIT_KEY_ENV)
    if not raw:
        raise _fail(f"{CANONICAL_GIT_KEY_ENV} is required")
    if raw != raw.strip() or any(character in raw for character in ("\x00", "\n", "\r")):
        raise _fail(f"{CANONICAL_GIT_KEY_ENV} is malformed")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise _fail(f"{CANONICAL_GIT_KEY_ENV} must be an absolute path")
    try:
        info = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _fail("canonical Git machine key is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise _fail("canonical Git machine key must be a regular non-symlink file")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise _fail("canonical Git machine key must be process-owned and owner-only")
    if info.st_nlink != 1:
        raise _fail("canonical Git machine key must not have filesystem aliases")
    if info.st_size <= 0 or info.st_size > MAX_KEY_BYTES:
        raise _fail("canonical Git machine key size is unsafe")

    private_key_root = _process_home() / ".ssh"
    try:
        private_key_root_resolved = private_key_root.resolve(strict=True)
        relative_key = resolved.relative_to(private_key_root_resolved)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _fail(
            "canonical Git machine key must live in the dedicated private key root"
        ) from exc
    if candidate != resolved or not relative_key.parts:
        raise _fail("canonical Git machine key path must not traverse links")
    _require_private_key_directory(private_key_root_resolved)
    cursor = private_key_root_resolved
    for component in relative_key.parts[:-1]:
        cursor /= component
        _require_private_key_directory(cursor)
    return resolved


def _git_environment(key_path: Path) -> dict[str, str]:
    home = str(_process_home())
    quoted_key = shlex.quote(str(key_path))
    ssh_command = (
        f"{_SSH} -F /dev/null -i {quoted_key} "
        "-o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none "
        "-o StrictHostKeyChecking=accept-new"
    )
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": home,
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "GIT_SSH_COMMAND": ssh_command,
        "GIT_SSH_VARIANT": "ssh",
        # A missing object must fail rather than make a second, ambient-promisor
        # network request through a checkout-configured remote.
        "GIT_NO_LAZY_FETCH": "1",
    }


def _run_git(
    arguments: list[str],
    *,
    environment: dict[str, str],
    timeout: int,
    accepted_returncodes: frozenset[int] = frozenset({0}),
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            [_GIT, *arguments],
            cwd=_REPO,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _fail("canonical Git command could not execute") from exc
    if result.returncode not in accepted_returncodes:
        raise _fail("canonical Git command refused")
    return result


def _refuse_local_url_rewrites(environment: dict[str, str]) -> None:
    # Linked worktrees can carry a separate config.worktree when
    # extensions.worktreeConfig is enabled.  Fetch consults both scopes, so a
    # local-only preflight would leave a literal-URL rewrite bypass.
    for scope in ("--local", "--worktree"):
        result = _run_git(
            [
                "config",
                scope,
                "--includes",
                "--name-only",
                "--get-regexp",
                r"^url\.",
            ],
            environment=environment,
            timeout=10,
            accepted_returncodes=frozenset({0, 1}),
        )
        names = result.stdout.decode("utf-8", errors="replace").splitlines()
        if any(name.lower().endswith("insteadof") for name in names):
            raise _fail("canonical Git refuses repository URL rewrites")


def read_canonical_blob(source_path: str) -> CanonicalGitBlob:
    """Fetch current canonical ``main`` and return one exact allowlisted blob.

    The literal SSH repository and literal refspec are not caller-configurable.
    The accepted commit is resolved once after fetch, and every subsequent object
    query is anchored to that immutable commit rather than the moving local ref.
    """
    if source_path not in ALLOWED_SOURCE_PATHS:
        raise _fail("canonical Git source path is not allowlisted")

    key_path = _deploy_key()
    environment = _git_environment(key_path)
    _refuse_local_url_rewrites(environment)
    _run_git(
        [
            "-c",
            "core.hooksPath=/dev/null",
            "fetch",
            "--no-tags",
            "--no-recurse-submodules",
            "--force",
            CANONICAL_REPOSITORY_SSH,
            f"+{CANONICAL_SOURCE_REF}:{CANONICAL_LOCAL_REF}",
        ],
        environment=environment,
        timeout=120,
    )

    commit_result = _run_git(
        ["rev-parse", "--verify", f"{CANONICAL_LOCAL_REF}^{{commit}}"],
        environment=environment,
        timeout=15,
    )
    try:
        source_commit = commit_result.stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise _fail("canonical Git returned a malformed commit identity") from exc
    if not _OBJECT_ID_RE.fullmatch(source_commit):
        raise _fail("canonical Git returned a malformed commit identity")

    object_spec = f"{source_commit}:{source_path}"
    type_result = _run_git(
        ["cat-file", "-t", object_spec],
        environment=environment,
        timeout=15,
    )
    if type_result.stdout.strip() != b"blob":
        raise _fail("canonical Git source object is not a blob")

    oid_result = _run_git(
        ["rev-parse", "--verify", object_spec],
        environment=environment,
        timeout=15,
    )
    try:
        blob_oid = oid_result.stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise _fail("canonical Git returned a malformed blob identity") from exc
    if not _OBJECT_ID_RE.fullmatch(blob_oid):
        raise _fail("canonical Git returned a malformed blob identity")

    size_result = _run_git(
        ["cat-file", "-s", object_spec],
        environment=environment,
        timeout=15,
    )
    try:
        declared_size = int(size_result.stdout.decode("ascii", errors="strict").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise _fail("canonical Git returned a malformed blob size") from exc
    if declared_size <= 0 or declared_size > MAX_BLOB_BYTES:
        raise _fail("canonical Git blob size is unsafe")

    body = _run_git(
        ["show", object_spec],
        environment=environment,
        timeout=60,
    ).stdout
    if len(body) != declared_size:
        raise _fail("canonical Git blob byte count changed during read")

    return CanonicalGitBlob(
        source_repository=CANONICAL_REPOSITORY_SSH,
        source_ref=CANONICAL_SOURCE_REF,
        source_commit=source_commit,
        source_path=source_path,
        blob_oid=blob_oid,
        body=body,
    )
