#!/usr/bin/env python3
"""Run canonical Macro Git commands with one explicit machine identity.

This is the write-capable sibling of ``scripts.prophet_canonical_git``.  The
two M1 publisher lanes that commit host-built artifacts need to keep working
after the canonical Macro repository becomes private, but they must never fall
back to a user SSH agent, credential helper, global Git rewrite, or anonymous
HTTPS URL.

The caller supplies normal Git arguments.  This wrapper validates an
owner-only key beneath the process owner's ``~/.ssh`` directory, requires the
entire repository-local configuration to match the canonical sparse-clone
schema, admits only the literal canonical SSH repository, constructs a minimal
environment, and then replaces itself with ``/usr/bin/git``.  Git's exit
status is therefore preserved exactly.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import subprocess
import sys


CANONICAL_REPOSITORY_SSH = (
    "git@github.com:mastermindx-market-intelligence/macro.git"
)
MACHINE_GIT_KEY_ENV = "MACRO_PUBLISH_GIT_SSH_KEY"
MAX_KEY_BYTES = 64 * 1024

_GIT = "/usr/bin/git"
_SSH = "/usr/bin/ssh"
_ALLOWED_COMMAND_CONFIG = frozenset(
    {
        "user.name=dashboard-bot",
        "user.email=actions@users.noreply.github.com",
    }
)
_ALLOWED_COMMANDS = frozenset(
    {
        "add",
        "clone",
        "commit",
        "diff",
        "fetch",
        "ls-remote",
        "push",
        "reset",
        "rev-parse",
        "sparse-checkout",
    }
)
_CANONICAL_FETCH = [
    "--no-tags",
    "--no-recurse-submodules",
    "--depth",
    "1",
    CANONICAL_REPOSITORY_SSH,
    "+refs/heads/main:refs/remotes/origin/main",
]
_CANONICAL_PUSH = [
    "--recurse-submodules=no",
    CANONICAL_REPOSITORY_SSH,
    "HEAD:refs/heads/main",
]
_SCP_REMOTE = re.compile(r"^[^/@:\s]+@[^:\s]+:.+$")

# This is the complete configuration produced on the publisher host by the
# allowlisted ``clone --depth 1 --filter=blob:none --sparse`` command.  The
# wrapper intentionally has no "safe-looking unknown key" escape hatch: Git
# configuration can execute programs through fsmonitor, external diff/textconv,
# and clean/smudge/process filters, and new execution-bearing families may be
# added in later Git releases.  A regenerated clone is disposable, so failing
# closed on any drift is safer than trying to maintain a blacklist.
_CANONICAL_LOCAL_CONFIG = {
    "core.repositoryformatversion": "1",
    "core.filemode": "true",
    "core.bare": "false",
    "core.logallrefupdates": "true",
    "core.ignorecase": "true",
    "core.precomposeunicode": "true",
    "remote.origin.url": CANONICAL_REPOSITORY_SSH,
    "remote.origin.fetch": "+refs/heads/main:refs/remotes/origin/main",
    "remote.origin.promisor": "true",
    "remote.origin.partialclonefilter": "blob:none",
    "branch.main.remote": "origin",
    "branch.main.merge": "refs/heads/main",
    "extensions.worktreeconfig": "true",
}
_CANONICAL_WORKTREE_CONFIG = {
    "core.sparsecheckout": "true",
    "core.sparsecheckoutcone": "true",
}


class MachineGitError(RuntimeError):
    """The explicit machine-Git contract was not satisfied."""


def _process_home() -> Path:
    try:
        return Path(pwd.getpwuid(os.geteuid()).pw_dir)
    except (KeyError, OSError) as exc:
        raise MachineGitError("machine Git process home is unavailable") from exc


def _require_owner_only_directory(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise MachineGitError("machine Git private key directory is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise MachineGitError("machine Git private key directory must be real")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise MachineGitError("machine Git private key directory must be owner-only")


def _deploy_key() -> Path:
    raw = os.environ.get(MACHINE_GIT_KEY_ENV)
    if not raw:
        raise MachineGitError(f"{MACHINE_GIT_KEY_ENV} is required")
    if raw != raw.strip() or any(char in raw for char in ("\x00", "\n", "\r")):
        raise MachineGitError(f"{MACHINE_GIT_KEY_ENV} is malformed")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise MachineGitError(f"{MACHINE_GIT_KEY_ENV} must be an absolute path")
    try:
        info = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise MachineGitError("machine Git key is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise MachineGitError("machine Git key must be a regular non-symlink file")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise MachineGitError("machine Git key must be process-owned and owner-only")
    if info.st_nlink != 1:
        raise MachineGitError("machine Git key must not have filesystem aliases")
    if info.st_size <= 0 or info.st_size > MAX_KEY_BYTES:
        raise MachineGitError("machine Git key size is unsafe")

    private_root = _process_home() / ".ssh"
    try:
        root = private_root.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise MachineGitError(
            "machine Git key must live in the dedicated private key root"
        ) from exc
    if candidate != resolved or not relative.parts:
        raise MachineGitError("machine Git key path must not traverse links")
    _require_owner_only_directory(root)
    cursor = root
    for component in relative.parts[:-1]:
        cursor /= component
        _require_owner_only_directory(cursor)
    return resolved


def _git_environment(key_path: Path) -> dict[str, str]:
    quoted_key = shlex.quote(str(key_path))
    ssh_command = (
        f"{_SSH} -F /dev/null -i {quoted_key} "
        "-o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none "
        "-o StrictHostKeyChecking=yes"
    )
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(_process_home()),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "GIT_SSH_COMMAND": ssh_command,
        "GIT_SSH_VARIANT": "ssh",
        # Disable hooks without inheriting any caller-supplied GIT_CONFIG_COUNT.
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null",
    }


def _repository_path(arguments: list[str]) -> Path | None:
    """Return the last explicit ``git -C <path>`` repository, if present."""
    repo: Path | None = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-C":
            if index + 1 >= len(arguments):
                raise MachineGitError("machine Git -C is missing its path")
            repo = Path(arguments[index + 1]).resolve()
            index += 2
            continue
        if argument.startswith("-C") and len(argument) > 2:
            repo = Path(argument[2:]).resolve()
        index += 1
    return repo


def _run_config(
    repository: Path,
    environment: dict[str, str],
    scope: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [_GIT, "-C", str(repository), "config", scope, "--no-includes", *arguments],
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MachineGitError("machine Git could not inspect local configuration") from exc


def _configuration_entries(
    repository: Path,
    environment: dict[str, str],
    scope: str,
) -> dict[str, str]:
    result = _run_config(repository, environment, scope, "--null", "--list")
    if result.returncode != 0:
        raise MachineGitError("machine Git local configuration is unreadable")

    entries: dict[str, str] = {}
    records = result.stdout.split("\0")
    if records and records[-1] == "":
        records.pop()
    for record in records:
        if "\n" not in record:
            raise MachineGitError("machine Git local configuration is malformed")
        raw_key, value = record.split("\n", 1)
        key = raw_key.lower()
        if not key or key in entries or raw_key != raw_key.strip():
            raise MachineGitError("machine Git local configuration is malformed")
        entries[key] = value
    return entries


def _refuse_unsafe_local_configuration(
    repository: Path,
    environment: dict[str, str],
) -> None:
    git_directory = repository / ".git"
    try:
        git_directory_info = git_directory.lstat()
    except OSError as exc:
        raise MachineGitError("machine Git requires a standalone repository") from exc
    if stat.S_ISLNK(git_directory_info.st_mode) or not stat.S_ISDIR(
        git_directory_info.st_mode
    ):
        raise MachineGitError("machine Git requires a standalone repository")

    local_entries = _configuration_entries(repository, environment, "--local")
    worktree_entries = _configuration_entries(repository, environment, "--worktree")
    if (
        local_entries != _CANONICAL_LOCAL_CONFIG
        or worktree_entries != _CANONICAL_WORKTREE_CONFIG
    ):
        raise MachineGitError(
            "machine Git repository configuration is outside the canonical sparse-clone schema"
        )


def _validate_repository_arguments(arguments: list[str]) -> None:
    if not arguments:
        raise MachineGitError("machine Git requires a command")
    index = 0
    command_index: int | None = None
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-C":
            if index + 1 >= len(arguments):
                raise MachineGitError("machine Git -C is missing its path")
            index += 2
            continue
        if argument.startswith("-C") and len(argument) > 2:
            index += 1
            continue
        if argument == "-c":
            if index + 1 >= len(arguments):
                raise MachineGitError("machine Git -c is missing its value")
            if arguments[index + 1] not in _ALLOWED_COMMAND_CONFIG:
                raise MachineGitError("machine Git refuses command-line configuration")
            index += 2
            continue
        if argument.startswith("-c") and len(argument) > 2:
            if argument[2:] not in _ALLOWED_COMMAND_CONFIG:
                raise MachineGitError("machine Git refuses command-line configuration")
            index += 1
            continue
        if argument.startswith("--config-env"):
            raise MachineGitError("machine Git refuses environment-backed configuration")
        if argument.startswith("-"):
            raise MachineGitError("machine Git refuses an unsupported global option")
        command_index = index
        break

    if command_index is None:
        raise MachineGitError("machine Git requires a command")
    command = arguments[command_index]
    operands = arguments[command_index + 1 :]
    if command not in _ALLOWED_COMMANDS:
        raise MachineGitError("machine Git command is not allowlisted")

    for argument in operands:
        lowered = argument.lower()
        if argument == "origin":
            raise MachineGitError("machine Git network calls require the literal repository")
        if (
            "://" in argument
            or "github.com:" in lowered
            or "github.com/" in lowered
            or _SCP_REMOTE.match(argument)
        ):
            if argument != CANONICAL_REPOSITORY_SSH:
                raise MachineGitError("machine Git refuses a non-canonical repository URL")

    if command == "clone":
        if len(operands) != 6 or operands[:5] != [
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            CANONICAL_REPOSITORY_SSH,
        ]:
            raise MachineGitError("machine Git clone contract is not canonical")
        if not Path(operands[5]).is_absolute():
            raise MachineGitError("machine Git clone destination must be absolute")
    elif command == "fetch" and operands != _CANONICAL_FETCH:
        raise MachineGitError("machine Git fetch contract is not canonical")
    elif command == "push" and operands not in (
        _CANONICAL_PUSH,
        ["--dry-run", *_CANONICAL_PUSH],
    ):
        raise MachineGitError("machine Git push contract is not canonical")
    elif command == "ls-remote" and operands != [
        CANONICAL_REPOSITORY_SSH,
        "refs/heads/main",
    ]:
        raise MachineGitError("machine Git ls-remote contract is not canonical")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        _validate_repository_arguments(arguments)
        key = _deploy_key()
        environment = _git_environment(key)
        repository = _repository_path(arguments)
        if repository is not None:
            _refuse_unsafe_local_configuration(repository, environment)
        os.execve(_GIT, [_GIT, *arguments], environment)
    except MachineGitError as exc:
        print(f"macro-machine-git: ERROR: {exc}", file=sys.stderr, flush=True)
        return 78
    except OSError:
        print("macro-machine-git: ERROR: Git could not execute", file=sys.stderr, flush=True)
        return 78
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
