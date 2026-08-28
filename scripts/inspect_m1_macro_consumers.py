#!/usr/bin/env python3
"""Bounded, read-only inspection of an explicitly supplied M1 Macro scope."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import selectors
import signal
import socket
import stat
import subprocess
import sys
import time
from typing import Callable, Mapping
from urllib.parse import urlsplit


SCHEMA = "macro.m1_consumer_census.v1"
_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_OUTPUT_BYTES = 256 * 1024
_READ_CHUNK_BYTES = 16 * 1024
_COMMAND_TIMEOUT_SECONDS = 5.0
_SAFE_PATH_ENV_NAMES = frozenset({"PYTHONPATH"})
_INTERPRETER_NAMES = frozenset({"bash", "sh", "python", "python3", "env"})
_CANONICAL_OWNER = "mastermindx-market-intelligence"
_OLD_OWNER = "chriswong6031-creator"
_REPO_NAME = "macro"

GIT_SAFETY_PREFIX = (
    "--no-optional-locks",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "submodule.recurse=false",
    "-c",
    "status.submoduleSummary=false",
)
GIT_ALLOWED_SUFFIXES = frozenset(
    {
        ("rev-parse", "--show-toplevel"),
        ("rev-parse", "HEAD"),
        ("symbolic-ref", "-q", "--short", "HEAD"),
        (
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=all",
        ),
        ("remote", "-v"),
        ("config", "--no-includes", "--local", "--get", "core.sshCommand"),
        ("config", "--no-includes", "--worktree", "--get", "core.sshCommand"),
        (
            "config",
            "--no-includes",
            "--local",
            "--name-only",
            "--get-regexp",
            r"^url\.",
        ),
        (
            "config",
            "--no-includes",
            "--worktree",
            "--name-only",
            "--get-regexp",
            r"^url\.",
        ),
        (
            "config",
            "--no-includes",
            "--local",
            "--name-only",
            "--get-regexp",
            r"^credential\.helper$",
        ),
        (
            "config",
            "--no-includes",
            "--worktree",
            "--name-only",
            "--get-regexp",
            r"^credential\.helper$",
        ),
    }
)


class InspectionError(RuntimeError):
    """A bounded, sanitized inspection failure."""


def _close_pipe(pipe: object) -> None:
    try:
        pipe.close()  # type: ignore[attr-defined]
    except OSError:
        pass


def _terminate_bounded_child(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1.0)
    if process.stdout is not None:
        _close_pipe(process.stdout)
    if process.stderr is not None:
        _close_pipe(process.stderr)


def _run_bounded_readonly(
    argv: tuple[str, ...],
    *,
    cwd: Path | None,
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run an already-approved command with a streaming time/output ceiling."""
    process = subprocess.Popen(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        close_fds=True,
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        _terminate_bounded_child(process)
        raise InspectionError("COMMAND_OUTPUT_INVALID")

    selected = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    selected.register(process.stdout, selectors.EVENT_READ, "stdout")
    selected.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + _COMMAND_TIMEOUT_SECONDS
    total = 0

    try:
        while selected.get_map():
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                _terminate_bounded_child(process)
                raise InspectionError("COMMAND_TIMEOUT")
            events = selected.select(remaining_time)
            if not events:
                _terminate_bounded_child(process)
                raise InspectionError("COMMAND_TIMEOUT")
            for key, _ in events:
                pipe = key.fileobj
                chunk = os.read(pipe.fileno(), _READ_CHUNK_BYTES)  # type: ignore[union-attr]
                if not chunk:
                    selected.unregister(pipe)
                    _close_pipe(pipe)
                    continue
                if total + len(chunk) > _MAX_OUTPUT_BYTES:
                    _terminate_bounded_child(process)
                    raise InspectionError("OUTPUT_LIMIT")
                buffers[str(key.data)].extend(chunk)
                total += len(chunk)
    finally:
        selected.close()

    try:
        returncode = process.wait(timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        _terminate_bounded_child(process)
        raise InspectionError("COMMAND_TIMEOUT") from None

    try:
        stdout = buffers["stdout"].decode("utf-8", errors="strict")
        stderr = buffers["stderr"].decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise InspectionError("COMMAND_OUTPUT_INVALID") from None
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def _git_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _run_git(path: Path, *suffix: str) -> subprocess.CompletedProcess[str]:
    approved = tuple(suffix)
    if approved not in GIT_ALLOWED_SUFFIXES:
        raise InspectionError("READ_ONLY_COMMAND_REFUSED")
    argv = ("/usr/bin/git", *GIT_SAFETY_PREFIX, *approved)
    return _run_bounded_readonly(argv, cwd=path, env=_git_environment())


@dataclass(frozen=True, slots=True)
class GitIdentityEvidence:
    canonical_repo: bool
    wrong_owner: bool
    anonymous_transport: bool
    explicit_machine_identity: bool
    ambient_fallback_possible: bool
    write_capability_observed: bool


@dataclass(frozen=True, slots=True)
class CheckoutEvidence:
    path: str
    head: str | None
    detached: bool | None
    dirty_tracked_count: int | None
    dirty_untracked_count: int | None
    remote_states: tuple[str, ...]
    fetch_head_mtime: str | None
    git_identity: GitIdentityEvidence
    inspection_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ServiceEvidence:
    service_id: str
    plist_path: str
    loaded: bool | None
    enabled: bool | None
    disabled_observed_state: str | None
    active: bool | None
    entrypoint: str | None
    working_directory: str | None
    environment_names: tuple[str, ...]
    checkout: CheckoutEvidence | None
    last_execution: str | None
    last_execution_source: str | None
    recent_evidence_metadata: tuple[str, ...]
    hazards: tuple[str, ...]
    inspection_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CensusReport:
    schema: str
    observed_at: str
    hostname: str
    supplied_scope_sha256: str
    services: tuple[ServiceEvidence, ...]
    complete_for_supplied_scope: bool
    scope_coverage_errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScopeService:
    service_id: str
    domain: str
    plist_path: Path
    recent_evidence_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ScopeManifest:
    schema: str
    hostname: str
    services: tuple[ScopeService, ...]
    scheduler_surfaces_checked: tuple[str, ...]
    recent_job_sources_checked: tuple[str, ...]
    exact_sha256: str


def parse_launchctl_disabled(output: str, label: str) -> tuple[bool, str | None]:
    """Return exact persistent-disable evidence for one validated label."""
    if (
        _LABEL_RE.fullmatch(label) is None
        or len(output.encode("utf-8")) > _MAX_OUTPUT_BYTES
    ):
        raise InspectionError("LAUNCHCTL_DISABLED_STATE_INVALID")

    matches: list[str] = []
    exact_quoted_label = f'"{label}"'
    near_label = re.compile(rf'"{re.escape(label)}[^"\r\n]+"')
    for line in output.splitlines():
        match = re.fullmatch(r'\s*"([^"\r\n]+)"\s*=>\s*(\S+)\s*', line)
        if match is not None and match.group(1) == label:
            matches.append(match.group(2))
            continue
        if exact_quoted_label in line or near_label.search(line) is not None:
            raise InspectionError("LAUNCHCTL_DISABLED_STATE_INVALID")

    if not matches:
        return (False, None)
    if len(matches) != 1 or matches[0] not in {"true", "disabled"}:
        raise InspectionError("LAUNCHCTL_DISABLED_STATE_INVALID")
    return (True, matches[0])


def parse_plist(path: Path) -> dict[str, object]:
    """Parse the narrow launchd definition shape without exposing values."""
    try:
        doc = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError, TypeError):
        raise InspectionError("PLIST_INVALID") from None
    if not isinstance(doc, dict):
        raise InspectionError("PLIST_INVALID")

    label = doc.get("Label")
    argv = doc.get("ProgramArguments")
    cwd = doc.get("WorkingDirectory")
    env = doc.get("EnvironmentVariables", {})
    if not isinstance(label, str) or not label or _LABEL_RE.fullmatch(label) is None:
        raise InspectionError("PLIST_INVALID")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(item, str) for item in argv
    ):
        raise InspectionError("PLIST_INVALID")
    if cwd is not None and (
        not isinstance(cwd, str) or not Path(cwd).is_absolute()
    ):
        raise InspectionError("PLIST_INVALID")
    if not isinstance(env, dict) or not all(isinstance(name, str) for name in env):
        raise InspectionError("PLIST_INVALID")
    for key in ("StandardOutPath", "StandardErrorPath"):
        value = doc.get(key)
        if value is not None and not isinstance(value, str):
            raise InspectionError("PLIST_INVALID")
    return doc


def _checkout_candidates(doc: dict[str, object]) -> tuple[Path, ...]:
    candidates: set[Path] = set()
    cwd = doc.get("WorkingDirectory")
    if isinstance(cwd, str) and Path(cwd).is_absolute():
        candidates.add(Path(cwd))

    argv = doc.get("ProgramArguments", [])
    if isinstance(argv, list):
        for arg in argv:
            if isinstance(arg, str) and Path(arg).is_absolute():
                candidates.add(Path(arg).parent)

    env = doc.get("EnvironmentVariables", {})
    if isinstance(env, dict):
        for name in _SAFE_PATH_ENV_NAMES:
            value = env.get(name)
            if isinstance(value, str):
                for part in value.split(":"):
                    if part and Path(part).is_absolute():
                        candidates.add(Path(part))
    return tuple(sorted(candidates, key=str))


def _entrypoint(argv: list[str]) -> str | None:
    absolute = [item for item in argv if Path(item).is_absolute()]
    if not absolute:
        return None
    if Path(absolute[0]).name in _INTERPRETER_NAMES and len(absolute) > 1:
        return absolute[1]
    return absolute[0]


def service_definition(
    path: Path,
) -> tuple[
    str,
    str | None,
    str | None,
    tuple[str, ...],
    tuple[Path, ...],
    tuple[Path, ...],
]:
    """Return only bounded launchd definition evidence and path candidates."""
    doc = parse_plist(path)
    label = doc["Label"]
    argv = doc["ProgramArguments"]
    assert isinstance(label, str)
    assert isinstance(argv, list)
    typed_argv = [item for item in argv if isinstance(item, str)]

    cwd_value = doc.get("WorkingDirectory")
    cwd = cwd_value if isinstance(cwd_value, str) else None
    env = doc.get("EnvironmentVariables", {})
    env_names = tuple(sorted(env)) if isinstance(env, dict) else ()

    recent_paths: set[Path] = set()
    for key in ("StandardOutPath", "StandardErrorPath"):
        value = doc.get(key)
        if isinstance(value, str) and Path(value).is_absolute():
            recent_paths.add(Path(value))

    return (
        label,
        _entrypoint(typed_argv),
        cwd,
        env_names,
        _checkout_candidates(doc),
        tuple(sorted(recent_paths, key=str)),
    )


def _remote_owner_repo(url: str) -> tuple[str | None, str | None, bool]:
    """Return owner, repository, and HTTPS transport without retaining secrets."""
    https_transport = False
    lowered = url.casefold()
    scp_prefix = "git@github.com:"
    ssh_prefix = "ssh://git@github.com/"
    if lowered.startswith(scp_prefix):
        location = url[len(scp_prefix):]
    elif lowered.startswith(ssh_prefix):
        location = url[len(ssh_prefix):]
    else:
        try:
            parsed = urlsplit(url)
        except ValueError:
            return (None, None, False)
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or parsed.hostname is None
            or parsed.hostname.casefold() != "github.com"
        ):
            return (None, None, False)
        https_transport = True
        location = parsed.path.lstrip("/")

    parts = location.rstrip("/").split("/")
    if len(parts) != 2:
        return (None, None, https_transport)
    owner, repo = parts
    if repo.casefold().endswith(".git"):
        repo = repo[:-4]
    return (owner.casefold(), repo.casefold(), https_transport)


def classify_remote(url: str) -> tuple[bool, bool, bool]:
    """Classify one raw URL into non-secret repository identity facts."""
    owner, repo, https_transport = _remote_owner_repo(url)
    is_macro = repo == _REPO_NAME
    return (
        bool(is_macro and owner == _CANONICAL_OWNER),
        bool(is_macro and owner == _OLD_OWNER),
        bool(is_macro and https_transport),
    )


def _remote_state(url: str) -> str:
    canonical, wrong_owner, anonymous = classify_remote(url)
    if wrong_owner:
        return "wrong_owner"
    if canonical and anonymous:
        return "canonical_https_anon"
    if canonical:
        return "canonical_ssh"
    owner, repo, _ = _remote_owner_repo(url)
    if owner is None or repo is None:
        return "unknown"
    return "other"


def _git_call(
    run_git: Callable[..., subprocess.CompletedProcess[str]],
    path: Path,
    *suffix: str,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return run_git(path, *suffix)
    except InspectionError:
        return None


def _config_present(result: subprocess.CompletedProcess[str] | None) -> bool:
    return bool(result is not None and result.returncode == 0 and result.stdout.strip())


def _explicit_identity(command: str) -> bool:
    identity_selected = re.search(r"(?:^|\s)-i(?:\s+|=)\S+", command) is not None
    identities_only = re.search(
        r"(?:^|\s)(?:-o\s*)?IdentitiesOnly\s*=\s*yes(?:\s|$)",
        command,
        flags=re.IGNORECASE,
    ) is not None
    return identity_selected and identities_only


def _iso_mtime(path: Path) -> str | None:
    try:
        value = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def inspect_checkout(
    path: Path,
    run_git: Callable[..., subprocess.CompletedProcess[str]] = _run_git,
) -> CheckoutEvidence | None:
    """Inspect one local checkout without network, mutation, or raw-value output."""
    top = _git_call(run_git, path, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return None
    top_lines = top.stdout.splitlines()
    if len(top_lines) != 1 or not Path(top_lines[0]).is_absolute():
        return None
    root = Path(top_lines[0])

    errors: list[str] = []
    head_result = _git_call(run_git, root, "rev-parse", "HEAD")
    head = None
    if head_result is not None and head_result.returncode == 0:
        candidate = head_result.stdout.strip()
        if re.fullmatch(r"[0-9a-fA-F]{40,64}", candidate):
            head = candidate.lower()
        else:
            errors.append("HEAD_INVALID")
    else:
        errors.append("HEAD_UNAVAILABLE")

    branch_result = _git_call(run_git, root, "symbolic-ref", "-q", "--short", "HEAD")
    detached = None if branch_result is None else branch_result.returncode != 0

    tracked_count: int | None = None
    untracked_count: int | None = None
    status_result = _git_call(
        run_git,
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=all",
    )
    if status_result is not None and status_result.returncode == 0:
        status_lines = [line for line in status_result.stdout.splitlines() if line]
        untracked_count = sum(line.startswith("??") for line in status_lines)
        tracked_count = len(status_lines) - untracked_count
    else:
        errors.append("STATUS_UNAVAILABLE")

    remote_result = _git_call(run_git, root, "remote", "-v")
    raw_remotes: list[str] = []
    if remote_result is not None and remote_result.returncode == 0:
        for line in remote_result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2:
                raw_remotes.append(fields[1])
    else:
        errors.append("REMOTE_UNAVAILABLE")

    ssh_commands: list[str] = []
    config_presence = False
    for scope in ("--local", "--worktree"):
        ssh_result = _git_call(
            run_git,
            root,
            "config",
            "--no-includes",
            scope,
            "--get",
            "core.sshCommand",
        )
        if ssh_result is not None and ssh_result.returncode == 0 and ssh_result.stdout.strip():
            ssh_commands.append(ssh_result.stdout.strip())
        for expression in (r"^url\.", r"^credential\.helper$"):
            present_result = _git_call(
                run_git,
                root,
                "config",
                "--no-includes",
                scope,
                "--name-only",
                "--get-regexp",
                expression,
            )
            config_presence = config_presence or _config_present(present_result)

    classifications = [classify_remote(url) for url in raw_remotes]
    explicit_identity = any(_explicit_identity(command) for command in ssh_commands)
    has_ssh_remote = any(
        url.startswith("git@github.com:") or url.startswith("ssh://")
        for url in raw_remotes
    )
    states = tuple(sorted({_remote_state(url) for url in raw_remotes})) or ("unknown",)
    identity = GitIdentityEvidence(
        canonical_repo=any(item[0] for item in classifications),
        wrong_owner=any(item[1] for item in classifications),
        anonymous_transport=any(item[2] for item in classifications),
        explicit_machine_identity=explicit_identity,
        ambient_fallback_possible=(
            config_presence
            or (has_ssh_remote and not explicit_identity)
            or bool(ssh_commands and not explicit_identity)
        ),
        write_capability_observed=False,
    )

    return CheckoutEvidence(
        path=str(root),
        head=head,
        detached=detached,
        dirty_tracked_count=tracked_count,
        dirty_untracked_count=untracked_count,
        remote_states=states,
        fetch_head_mtime=_iso_mtime(root / ".git" / "FETCH_HEAD"),
        git_identity=identity,
        inspection_errors=tuple(sorted(set(errors))),
    )


_SCOPE_KEYS = frozenset(
    {
        "schema",
        "hostname",
        "services",
        "scheduler_surfaces_checked",
        "recent_job_sources_checked",
    }
)
_SCOPE_SERVICE_KEYS = frozenset(
    {"service_id", "domain", "plist_path", "recent_evidence_paths"}
)


def _nonempty_string_list(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, str) and item.strip() for item in value):
        return None
    typed = tuple(value)
    if len(set(typed)) != len(typed):
        return None
    return typed


def _allowed_domain(domain: str, *, uid: int = os.getuid()) -> bool:
    return domain == "system" or domain == f"gui/{uid}"


def parse_scope_manifest(path: Path) -> ScopeManifest:
    """Parse and bind one strict ephemeral scope manifest."""
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > _MAX_OUTPUT_BYTES:
            raise ValueError
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise InspectionError("SCOPE_MANIFEST_INVALID") from None
    if not isinstance(payload, dict) or set(payload) != _SCOPE_KEYS:
        raise InspectionError("SCOPE_MANIFEST_INVALID")
    if payload.get("schema") != "macro.m1_consumer_scope.v1":
        raise InspectionError("SCOPE_MANIFEST_INVALID")
    if payload.get("hostname") != socket.gethostname():
        raise InspectionError("SCOPE_MANIFEST_INVALID")

    scheduler = _nonempty_string_list(payload.get("scheduler_surfaces_checked"))
    recent_sources = _nonempty_string_list(payload.get("recent_job_sources_checked"))
    rows = payload.get("services")
    if scheduler is None or recent_sources is None or not isinstance(rows, list) or not rows:
        raise InspectionError("SCOPE_MANIFEST_INVALID")

    services: list[ScopeService] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != _SCOPE_SERVICE_KEYS:
            raise InspectionError("SCOPE_MANIFEST_INVALID")
        service_id = row.get("service_id")
        domain = row.get("domain")
        plist_value = row.get("plist_path")
        evidence_values = row.get("recent_evidence_paths")
        if (
            not isinstance(service_id, str)
            or _LABEL_RE.fullmatch(service_id) is None
            or service_id in seen
            or not isinstance(domain, str)
            or not _allowed_domain(domain)
            or not isinstance(plist_value, str)
            or not Path(plist_value).is_absolute()
            or not isinstance(evidence_values, list)
            or not all(
                isinstance(item, str) and Path(item).is_absolute()
                for item in evidence_values
            )
            or len(set(evidence_values)) != len(evidence_values)
        ):
            raise InspectionError("SCOPE_MANIFEST_INVALID")
        seen.add(service_id)
        services.append(
            ScopeService(
                service_id=service_id,
                domain=domain,
                plist_path=Path(plist_value),
                recent_evidence_paths=tuple(Path(item) for item in evidence_values),
            )
        )

    return ScopeManifest(
        schema="macro.m1_consumer_scope.v1",
        hostname=socket.gethostname(),
        services=tuple(sorted(services, key=lambda item: item.service_id)),
        scheduler_surfaces_checked=tuple(sorted(set(scheduler))),
        recent_job_sources_checked=tuple(sorted(set(recent_sources))),
        exact_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _launchctl_environment() -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}


def _valid_launchctl_suffix(suffix: tuple[str, ...]) -> bool:
    if len(suffix) != 2:
        return False
    verb, target = suffix
    if verb == "print-disabled":
        return _allowed_domain(target)
    if verb != "print":
        return False
    for domain in ("system", f"gui/{os.getuid()}"):
        prefix = f"{domain}/"
        if target.startswith(prefix):
            label = target.removeprefix(prefix)
            return bool(
                label
                and len(label) <= 255
                and _LABEL_RE.fullmatch(label) is not None
            )
    return False


def _run_launchctl(*suffix: str) -> subprocess.CompletedProcess[str]:
    approved = tuple(suffix)
    if not _valid_launchctl_suffix(approved):
        raise InspectionError("READ_ONLY_COMMAND_REFUSED")
    return _run_bounded_readonly(
        ("/bin/launchctl", *approved),
        cwd=None,
        env=_launchctl_environment(),
    )


def probe_launchctl(
    label: str,
    domain: str,
    *,
    uid: int = os.getuid(),
    run_launchctl: Callable[..., subprocess.CompletedProcess[str]] = _run_launchctl,
) -> tuple[bool | None, bool | None, bool | None]:
    """Probe persistent-disable and loaded state with exact read-only argv."""
    valid_domain = domain == "system" or domain == f"gui/{uid}"
    if (
        not valid_domain
        or not label
        or len(label) > 255
        or _LABEL_RE.fullmatch(label) is None
    ):
        raise InspectionError("READ_ONLY_COMMAND_REFUSED")

    disabled_result = run_launchctl("print-disabled", domain)
    if disabled_result.returncode != 0:
        raise InspectionError("LAUNCHCTL_STATE_INVALID")
    disabled, _state = parse_launchctl_disabled(disabled_result.stdout, label)

    state_result = run_launchctl("print", f"{domain}/{label}")
    if state_result.returncode != 0:
        raise InspectionError("LAUNCHCTL_STATE_INVALID")
    states: list[str] = []
    for line in state_result.stdout.splitlines():
        match = re.fullmatch(r"\s*state\s*=\s*(running|not running)\s*", line)
        if match is not None:
            states.append(match.group(1))
        elif "state" in line:
            raise InspectionError("LAUNCHCTL_STATE_INVALID")
    if len(states) != 1:
        raise InspectionError("LAUNCHCTL_STATE_INVALID")
    active = states[0] == "running"
    return (True, active, False if disabled else None)


def _git_root(candidate: Path) -> Path | None:
    current = candidate if candidate.is_dir() else candidate.parent
    for possible in (current, *current.parents):
        if (possible / ".git").exists():
            return possible
    return None


def _file_type(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "other"


def _metadata_evidence(path: Path, kind: str) -> tuple[str, datetime] | None:
    try:
        info = path.lstat()
    except OSError:
        return None
    observed = datetime.fromtimestamp(info.st_mtime, tz=timezone.utc)
    value = (
        f"{kind}:exists=true:type={_file_type(info.st_mode)}:"
        f"size={info.st_size}:mtime={observed.isoformat()}"
    )
    return (value, observed)


def _service_error(
    row: ScopeService,
    error: str,
    *,
    loaded: bool | None = None,
    enabled: bool | None = None,
    active: bool | None = None,
) -> ServiceEvidence:
    return ServiceEvidence(
        service_id=row.service_id,
        plist_path=str(row.plist_path),
        loaded=loaded,
        enabled=enabled,
        disabled_observed_state="disabled" if enabled is False else None,
        active=active,
        entrypoint=None,
        working_directory=None,
        environment_names=(),
        checkout=None,
        last_execution=None,
        last_execution_source=None,
        recent_evidence_metadata=(),
        hazards=(),
        inspection_errors=(error,),
    )


def build_report(
    scope: ScopeManifest,
    *,
    launchctl_probe: Callable[
        [str, str], tuple[bool | None, bool | None, bool | None]
    ],
    hostname: str,
    now: datetime,
) -> CensusReport:
    """Build deterministic evidence for every row in the supplied scope."""
    coverage_errors: list[str] = []
    services: list[ServiceEvidence] = []
    if hostname != scope.hostname:
        coverage_errors.append("HOSTNAME_MISMATCH")

    for row in scope.services:
        try:
            loaded, active, enabled = launchctl_probe(row.service_id, row.domain)
        except InspectionError as exc:
            code = str(exc) if str(exc) else "LAUNCHCTL_STATE_INVALID"
            services.append(_service_error(row, code))
            coverage_errors.append(f"SERVICE_INSPECTION_INCOMPLETE:{row.service_id}")
            continue

        try:
            label, entrypoint, cwd, env_names, candidates, stream_paths = (
                service_definition(row.plist_path)
            )
        except InspectionError as exc:
            code = str(exc) if str(exc) else "PLIST_INVALID"
            services.append(
                _service_error(
                    row,
                    code,
                    loaded=loaded,
                    enabled=enabled,
                    active=active,
                )
            )
            if row.recent_evidence_paths:
                coverage_errors.append(
                    f"RECENT_EVIDENCE_UNAVAILABLE:{row.service_id}"
                )
            coverage_errors.append(f"SERVICE_INSPECTION_INCOMPLETE:{row.service_id}")
            continue

        errors: list[str] = []
        if label != row.service_id:
            errors.append("PLIST_LABEL_MISMATCH")

        roots = {root for candidate in candidates if (root := _git_root(candidate))}
        checkout: CheckoutEvidence | None = None
        if len(roots) > 1:
            errors.append("CHECKOUT_AMBIGUOUS")
        elif len(roots) == 1:
            checkout = inspect_checkout(next(iter(roots)))
            if checkout is None:
                errors.append("CHECKOUT_UNAVAILABLE")
            elif checkout.inspection_errors:
                errors.extend(checkout.inspection_errors)

        metadata: list[str] = []
        timestamps: list[tuple[datetime, str]] = []
        declared = [
            *(("launchd-stream", path) for path in stream_paths),
            *(("manifest-evidence", path) for path in row.recent_evidence_paths),
        ]
        for kind, evidence_path in declared:
            item = _metadata_evidence(evidence_path, kind)
            if item is None:
                errors.append("RECENT_EVIDENCE_UNAVAILABLE")
                coverage_errors.append(
                    f"RECENT_EVIDENCE_UNAVAILABLE:{row.service_id}"
                )
                continue
            rendered, observed = item
            metadata.append(rendered)
            timestamps.append((observed, kind))

        hazards: list[str] = []
        if checkout is not None:
            if checkout.git_identity.wrong_owner:
                hazards.append("wrong_owner")
            if checkout.git_identity.anonymous_transport:
                hazards.append("anonymous_transport")
            if checkout.git_identity.ambient_fallback_possible:
                hazards.append("ambient_fallback_possible")

        last_execution = None
        last_source = None
        if timestamps:
            newest, kind = max(timestamps, key=lambda item: item[0])
            last_execution = newest.isoformat()
            last_source = f"metadata-derived:{kind}"

        services.append(
            ServiceEvidence(
                service_id=row.service_id,
                plist_path=str(row.plist_path),
                loaded=loaded,
                enabled=enabled,
                disabled_observed_state="disabled" if enabled is False else None,
                active=active,
                entrypoint=entrypoint,
                working_directory=cwd,
                environment_names=env_names,
                checkout=checkout,
                last_execution=last_execution,
                last_execution_source=last_source,
                recent_evidence_metadata=tuple(sorted(metadata)),
                hazards=tuple(sorted(set(hazards))),
                inspection_errors=tuple(sorted(set(errors))),
            )
        )
        if errors:
            coverage_errors.append(f"SERVICE_INSPECTION_INCOMPLETE:{row.service_id}")

    ordered = tuple(sorted(services, key=lambda item: item.service_id))
    return CensusReport(
        schema=SCHEMA,
        observed_at=now.astimezone(timezone.utc).isoformat(),
        hostname=hostname,
        supplied_scope_sha256=scope.exact_sha256,
        services=ordered,
        complete_for_supplied_scope=not coverage_errors
        and all(not item.inspection_errors for item in ordered),
        scope_coverage_errors=tuple(sorted(set(coverage_errors))),
    )


def render_json(report: CensusReport) -> str:
    return json.dumps(asdict(report), sort_keys=True, indent=2)


def _table_value(value: object) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return str(value).lower()
    return re.sub(r"[\r\n|]", " ", str(value))[:512]


def render_table(report: CensusReport) -> str:
    rows = [
        "SERVICE | LOADED | DISABLED | CHECKOUT | REMOTE_STATE | "
        "LAST_EXECUTION | HAZARDS"
    ]
    for service in report.services:
        checkout_path = service.checkout.path if service.checkout is not None else None
        remote_state = (
            ",".join(service.checkout.remote_states)
            if service.checkout is not None
            else "unknown"
        )
        rows.append(
            " | ".join(
                _table_value(value)
                for value in (
                    service.service_id,
                    service.loaded,
                    service.enabled is False,
                    checkout_path,
                    remote_state,
                    service.last_execution,
                    ",".join(service.hazards),
                )
            )
        )
    return "\n".join(rows)


class _InspectionArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise InspectionError("ARGUMENTS_INVALID")


def main(argv: list[str] | None = None) -> int:
    parser = _InspectionArgumentParser(
        description=(
            "Inspect one explicit M1 Macro consumer scope without changing "
            "services, repositories, credentials, or files."
        )
    )
    parser.add_argument(
        "--scope-manifest",
        required=True,
        type=Path,
        help="absolute path to an ephemeral macro.m1_consumer_scope.v1 manifest",
    )
    parser.add_argument("--format", choices=("json", "table"), default="json")
    try:
        args = parser.parse_args(argv)
        if not args.scope_manifest.is_absolute():
            raise InspectionError("SCOPE_MANIFEST_INVALID")
        scope = parse_scope_manifest(args.scope_manifest)
        report = build_report(
            scope,
            launchctl_probe=probe_launchctl,
            hostname=socket.gethostname(),
            now=datetime.now(timezone.utc),
        )
    except InspectionError as exc:
        code = str(exc) if str(exc) else "INSPECTION_ERROR"
        if re.fullmatch(r"[A-Z0-9_]+", code) is None:
            code = "INSPECTION_ERROR"
        print(f"INSPECTION_FAILED:{code}", file=sys.stderr)
        return 65

    print(render_json(report) if args.format == "json" else render_table(report))
    return 0 if report.complete_for_supplied_scope else 65


if __name__ == "__main__":
    raise SystemExit(main())
