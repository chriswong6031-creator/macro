#!/usr/bin/env python3
"""Publish the existing project active-build map for the Control Room.

This is a deliberately small trust-boundary adapter.  It runs only inside the
already-trusted ``macro-update`` lane, invokes the canonical GitHub collector,
validates its complete typed document, and atomically installs one read-only
artifact for Mastermind.  It owns no timer, credentials, cache, routing, or
execution authority of its own.

Failures are fail-closed and leave the last-good artifact untouched.  Messages
contain stable reason codes only; child stderr is never forwarded.
"""
from __future__ import annotations

import grp
import json
import os
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_project_active_build_map as project_map


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRECTORY = Path("/var/lib/mastermind-control-room-sources")
OUTPUT_PATH = SOURCE_DIRECTORY / "project-active-builds.json"
SERVICE_GROUP = "mastermind-control-room"
DIRECTORY_MODE = 0o750
FILE_MODE = 0o640
COLLECT_TIMEOUT_SECONDS = 90.0
STDOUT_LIMIT_BYTES = 4 * 1024 * 1024
STDERR_LIMIT_BYTES = 16 * 1024
SOURCE_MAX_AGE_SECONDS = 300
SOURCE_FUTURE_TOLERANCE_SECONDS = 60


class PublishError(RuntimeError):
    """A sanitized, stable fail-closed publication reason."""


@dataclass(frozen=True)
class BoundedResult:
    stdout: bytes
    returncode: int


def builder_command(repo_root: Path, python_executable: str) -> list[str]:
    """Return the one approved producer command with no caller-controlled args."""
    return [
        python_executable,
        str(repo_root / "scripts" / "build_project_active_build_map.py"),
        "--json-stdout",
    ]


def _terminate_and_reap(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.wait()


def run_bounded(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
) -> BoundedResult:
    """Run one child with incremental pipe caps, timeout, kill, and reap."""
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise PublishError("COLLECT_START") from exc

    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, ("stdout", stdout_limit))
    selector.register(process.stderr, selectors.EVENT_READ, ("stderr", stderr_limit))
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout_seconds
    reason: str | None = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = "COLLECT_TIMEOUT"
                break
            events = selector.select(min(remaining, 0.1))
            if not events:
                continue
            for key, _mask in events:
                stream_name, limit = key.data
                try:
                    chunk = os.read(key.fd, min(65536, limit - len(buffers[stream_name]) + 1))
                except OSError:
                    reason = "COLLECT_PIPE"
                    break
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffers[stream_name].extend(chunk)
                if len(buffers[stream_name]) > limit:
                    reason = (
                        "COLLECT_STDOUT_LIMIT"
                        if stream_name == "stdout"
                        else "COLLECT_STDERR_LIMIT"
                    )
                    break
            if reason is not None:
                break

        if reason is not None:
            _terminate_and_reap(process)
            raise PublishError(reason)

        returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        if returncode != 0:
            raise PublishError("COLLECT_EXIT")
        return BoundedResult(stdout=bytes(buffers["stdout"]), returncode=returncode)
    except subprocess.TimeoutExpired as exc:
        _terminate_and_reap(process)
        raise PublishError("COLLECT_TIMEOUT") from exc
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
        if process.poll() is None:
            _terminate_and_reap(process)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublishError("DOCUMENT_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> Any:
    raise PublishError("DOCUMENT_NONFINITE_NUMBER")


def validate_document(raw: bytes, *, now: datetime | None = None) -> bytes:
    """Validate and return canonical JSON bytes for the exact source contract."""
    if not raw or len(raw) > STDOUT_LIMIT_BYTES:
        raise PublishError("DOCUMENT_SIZE")
    try:
        text = raw.decode("utf-8", errors="strict")
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except PublishError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PublishError("DOCUMENT_JSON") from exc
    if not isinstance(document, dict):
        raise PublishError("DOCUMENT_SHAPE")
    if document.get("schema") != project_map.SCHEMA:
        raise PublishError("DOCUMENT_SCHEMA")

    try:
        canonical = project_map.compile_snapshot(document)
    except (KeyError, TypeError, ValueError) as exc:
        raise PublishError("DOCUMENT_CONTRACT") from exc
    if canonical != document:
        raise PublishError("DOCUMENT_NONCANONICAL")

    stamp_text = document.get("collected_at")
    if not isinstance(stamp_text, str):
        raise PublishError("SOURCE_CLOCK")
    try:
        stamp = datetime.fromisoformat(stamp_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublishError("SOURCE_CLOCK") from exc
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise PublishError("SOURCE_CLOCK")

    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() != timedelta(0):
        raise PublishError("LOCAL_CLOCK")
    age = (observed - stamp).total_seconds()
    if age < -SOURCE_FUTURE_TOLERANCE_SECONDS:
        raise PublishError("SOURCE_FUTURE")
    if age > SOURCE_MAX_AGE_SECONDS:
        raise PublishError("SOURCE_STALE")
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _open_safe_directory(path: Path, *, expected_uid: int, expected_gid: int) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PublishError("DIRECTORY_UNSAFE") from exc
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != DIRECTORY_MODE
        or metadata.st_uid != expected_uid
        or metadata.st_gid != expected_gid
    ):
        os.close(descriptor)
        raise PublishError("DIRECTORY_UNSAFE")
    return descriptor


def _validate_target(
    directory_fd: int,
    name: str,
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PublishError("TARGET_UNSAFE") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != FILE_MODE
        or metadata.st_nlink != 1
        or metadata.st_uid != expected_uid
        or metadata.st_gid != expected_gid
    ):
        raise PublishError("TARGET_UNSAFE")


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def publish_document(
    target: Path,
    content: bytes,
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
    """Atomically publish after directory and existing-target safety checks."""
    directory_fd = _open_safe_directory(
        target.parent, expected_uid=expected_uid, expected_gid=expected_gid
    )
    temporary_name = f".{target.name}.tmp-{secrets.token_hex(12)}"
    temporary_created = False
    try:
        _validate_target(
            directory_fd,
            target.name,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            temporary_fd = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
            temporary_created = True
        except OSError as exc:
            raise PublishError("TEMPORARY_CREATE_FAILED") from exc
        try:
            _write_all(temporary_fd, content)
            os.fchown(temporary_fd, expected_uid, expected_gid)
            os.fchmod(temporary_fd, FILE_MODE)
            os.fsync(temporary_fd)
        except OSError as exc:
            raise PublishError("TEMPORARY_WRITE_FAILED") from exc
        finally:
            os.close(temporary_fd)

        # Recheck immediately before rename so a swapped/hard-linked destination
        # cannot be silently replaced after the initial admission check.
        _validate_target(
            directory_fd,
            target.name,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        try:
            os.replace(
                temporary_name,
                target.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            temporary_created = False
            os.fsync(directory_fd)
        except OSError as exc:
            raise PublishError("ATOMIC_REPLACE_FAILED") from exc
        _validate_target(
            directory_fd,
            target.name,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def collect_document(repo_root: Path = REPO_ROOT) -> bytes:
    command = builder_command(repo_root, sys.executable)
    result = run_bounded(
        command,
        cwd=repo_root,
        timeout_seconds=COLLECT_TIMEOUT_SECONDS,
        stdout_limit=STDOUT_LIMIT_BYTES,
        stderr_limit=STDERR_LIMIT_BYTES,
    )
    return validate_document(result.stdout)


def main() -> int:
    if os.geteuid() != 0:
        print("control-room-source: PUBLISHER_NOT_ROOT", file=sys.stderr)
        return 2
    try:
        service_gid = grp.getgrnam(SERVICE_GROUP).gr_gid
    except KeyError:
        print("control-room-source: SERVICE_GROUP_UNAVAILABLE", file=sys.stderr)
        return 2
    try:
        content = collect_document()
        publish_document(
            OUTPUT_PATH,
            content,
            expected_uid=0,
            expected_gid=service_gid,
        )
    except PublishError as exc:
        print(f"control-room-source: {exc}", file=sys.stderr)
        return 1
    print("control-room-source: PUBLISHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
