"""Fail-closed tests for the Control Room GitHub-source publisher."""
from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import time
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import publish_control_room_active_builds as publisher
from scripts import build_project_active_build_map as project_map


def _payload(*, collected_at: datetime | None = None) -> dict:
    stamp = collected_at or datetime.now(timezone.utc)
    source = {
        "schema": "project_active_builds.source.v1",
        "collected_at": stamp.isoformat(),
        "merged_days": 14,
        "repositories": [
            {
                "repo": spec.repository,
                "base_branch": spec.base_branch,
                "base_sha": (str(index + 1) * 40),
                "open_prs": [],
                "recently_merged": [],
            }
            for index, spec in enumerate(project_map.REPOSITORIES)
        ],
    }
    return project_map.compile_snapshot(source)


def _encoded(payload: dict | None = None) -> bytes:
    return (json.dumps(payload or _payload(), sort_keys=True) + "\n").encode()


def _safe_directory(path: Path) -> None:
    path.mkdir(mode=0o750)
    path.chmod(0o750)


def test_builder_command_is_the_existing_canonical_json_stdout_seam(tmp_path):
    assert publisher.builder_command(tmp_path, "/usr/bin/python3") == [
        "/usr/bin/python3",
        str(tmp_path / "scripts" / "build_project_active_build_map.py"),
        "--json-stdout",
    ]


def test_cross_repo_source_contract_uses_caddy_group_and_zero_future_tolerance():
    assert publisher.SERVICE_GROUP == "caddy"
    assert publisher.SOURCE_FUTURE_TOLERANCE_SECONDS == 0
    assert publisher.COLLECTION_MIN_INTERVAL_SECONDS == 9 * 60


def test_collection_due_uses_validated_source_clock_not_file_mtime(tmp_path):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    target = source_dir / "project-active-builds.json"
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    target.write_bytes(_encoded(_payload(collected_at=now - timedelta(minutes=8))))
    target.chmod(0o640)
    old_mtime = (now - timedelta(days=30)).timestamp()
    os.utime(target, (old_mtime, old_mtime))

    assert not publisher.collection_due(
        target,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        now=now,
    )

    target.write_bytes(_encoded(_payload(collected_at=now - timedelta(minutes=9))))
    target.chmod(0o640)
    future_mtime = (now + timedelta(days=30)).timestamp()
    os.utime(target, (future_mtime, future_mtime))
    assert publisher.collection_due(
        target,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        now=now,
    )


def test_collection_due_is_fail_closed_on_unsafe_target_but_recollects_bad_bytes(
    tmp_path,
):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    target = source_dir / "project-active-builds.json"
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)

    target.write_bytes(b"malformed")
    target.chmod(0o640)
    assert publisher.collection_due(
        target,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        now=now,
    )

    target.unlink()
    target.symlink_to(source_dir / "elsewhere")
    with pytest.raises(publisher.PublishError, match="TARGET_UNSAFE"):
        publisher.collection_due(
            target,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
            now=now,
        )


def test_safe_directory_fstat_failure_is_sanitized_and_descriptor_is_closed(
    tmp_path, monkeypatch
):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    real_close = publisher.os.close
    closed: list[int] = []

    def record_close(descriptor):
        closed.append(descriptor)
        return real_close(descriptor)

    monkeypatch.setattr(
        publisher.os,
        "fstat",
        lambda _descriptor: (_ for _ in ()).throw(OSError("private fstat detail")),
    )
    monkeypatch.setattr(publisher.os, "close", record_close)

    try:
        with pytest.raises(publisher.PublishError, match="DIRECTORY_UNSAFE") as error:
            publisher._open_safe_directory(
                source_dir,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )
    finally:
        monkeypatch.undo()
    assert "private" not in str(error.value)
    assert len(closed) == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b'{"schema":"project_active_builds.v1","schema":"wrong"}',
        b'{"schema":"project_active_builds.v1","value":NaN}',
        b'{"schema":"wrong","collected_at":"2026-08-28T00:00:00+00:00"}',
        b'{"schema":"project_active_builds.v1","collected_at":"not-a-clock"}',
        b'{"schema":"project_active_builds.v1","collected_at":"2026-08-28T00:00:00"}',
        _encoded(_payload(collected_at=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc))).replace(
            b"T12:00:00+00:00", b" 12:00:00+00:00"
        ),
        _encoded(_payload(collected_at=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc))).replace(
            b"+00:00", b"+0000"
        ),
    ],
)
def test_document_parser_rejects_empty_duplicate_nonfinite_schema_and_bad_clock(raw):
    with pytest.raises(publisher.PublishError):
        publisher.validate_document(raw, now=datetime(2026, 8, 28, tzinfo=timezone.utc))


def test_document_parser_rejects_stale_and_future_collection_clocks():
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(publisher.PublishError, match="SOURCE_STALE"):
        publisher.validate_document(
            _encoded(_payload(collected_at=now - timedelta(minutes=6))), now=now
        )
    with pytest.raises(publisher.PublishError, match="SOURCE_FUTURE"):
        publisher.validate_document(
            _encoded(_payload(collected_at=now + timedelta(minutes=2))), now=now
        )


@pytest.mark.parametrize("suffix", ["Z", "+00:00"])
def test_document_parser_accepts_only_canonical_utc_forms_and_normalizes_to_z(suffix):
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    raw = _encoded(_payload(collected_at=now)).replace(b"+00:00", suffix.encode())
    normalized = json.loads(publisher.validate_document(raw, now=now))
    assert normalized["collected_at"] == "2026-08-28T12:00:00Z"


def test_bounded_process_accepts_small_stdout_and_never_forwards_stderr():
    result = publisher.run_bounded(
        [sys.executable, "-c", "import sys; print('ok'); print('secret', file=sys.stderr)"],
        cwd=Path.cwd(),
        timeout_seconds=2,
        stdout_limit=64,
        stderr_limit=64,
    )
    assert result.stdout == b"ok\n"
    assert result.returncode == 0
    assert not hasattr(result, "stderr")


@pytest.mark.parametrize(
    "program, error",
    [
        ("import sys; sys.stdout.write('x' * 1000000)", "COLLECT_STDOUT_LIMIT"),
        ("import sys; sys.stderr.write('x' * 1000000)", "COLLECT_STDERR_LIMIT"),
        ("import time; time.sleep(5)", "COLLECT_TIMEOUT"),
        ("raise SystemExit(7)", "COLLECT_EXIT"),
    ],
)
def test_bounded_process_caps_output_kills_and_reaps(program, error):
    with pytest.raises(publisher.PublishError, match=error):
        publisher.run_bounded(
            [sys.executable, "-c", program],
            cwd=Path.cwd(),
            timeout_seconds=0.2,
            stdout_limit=128,
            stderr_limit=128,
        )


def test_bounded_process_kills_descendant_group_after_parent_already_exited(tmp_path):
    child_pid_path = tmp_path / "child.pid"
    program = (
        "import pathlib,subprocess,sys; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "raise SystemExit(0)"
    )

    with pytest.raises(publisher.PublishError, match="COLLECT_TIMEOUT"):
        publisher.run_bounded(
            [sys.executable, "-c", program],
            cwd=Path.cwd(),
            timeout_seconds=0.3,
            stdout_limit=128,
            stderr_limit=128,
        )

    child_pid = int(child_pid_path.read_text())
    deadline = time.monotonic() + 2
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            os.kill(child_pid, signal.SIGKILL)
            pytest.fail("bounded collector leaked a descendant process group")
        time.sleep(0.02)


def test_bounded_process_kills_pipe_detached_descendant_after_successful_parent(tmp_path):
    child_pid_path = tmp_path / "detached-child.pid"
    program = (
        "import pathlib,subprocess,sys; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "raise SystemExit(0)"
    )

    result = publisher.run_bounded(
        [sys.executable, "-c", program],
        cwd=Path.cwd(),
        timeout_seconds=2,
        stdout_limit=128,
        stderr_limit=128,
    )
    assert result.returncode == 0

    child_pid = int(child_pid_path.read_text())
    deadline = time.monotonic() + 2
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            os.kill(child_pid, signal.SIGKILL)
            pytest.fail("successful collector leaked a pipe-detached descendant")
        time.sleep(0.02)


def test_terminate_and_reap_has_no_unbounded_wait_fallback(monkeypatch):
    class UnreapableProcess:
        pid = 987654321

        def __init__(self):
            self.wait_timeouts = []
            self.kill_calls = 0

        def poll(self):
            return None

        def kill(self):
            self.kill_calls += 1

        def wait(self, *, timeout):
            self.wait_timeouts.append(timeout)
            raise subprocess.TimeoutExpired("synthetic", timeout)

    process = UnreapableProcess()
    monkeypatch.setattr(publisher.os, "killpg", lambda *_args: None)
    with pytest.raises(publisher.PublishError, match="COLLECT_REAP_FAILED"):
        publisher._terminate_and_reap(process)
    assert process.wait_timeouts == [2, 2]
    assert process.kill_calls == 2


def test_atomic_publish_creates_exact_mode_and_preserves_valid_document(tmp_path):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    target = source_dir / "project-active-builds.json"

    publisher.publish_document(
        target,
        _encoded(),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert json.loads(target.read_text())["schema"] == "project_active_builds.v1"
    metadata = target.stat()
    assert stat.S_IMODE(metadata.st_mode) == 0o640
    assert metadata.st_nlink == 1
    assert metadata.st_uid == os.getuid()
    assert metadata.st_gid == os.getgid()
    assert not list(source_dir.glob(".project-active-builds.json.tmp-*"))


def test_publish_refuses_unsafe_directory_symlink_and_leaves_target_untouched(tmp_path):
    real_dir = tmp_path / "real"
    _safe_directory(real_dir)
    target = real_dir / "project-active-builds.json"
    target.write_bytes(b"last-good\n")
    target.chmod(0o640)
    link = tmp_path / "link"
    link.symlink_to(real_dir, target_is_directory=True)

    with pytest.raises(publisher.PublishError, match="DIRECTORY_UNSAFE"):
        publisher.publish_document(
            link / target.name,
            _encoded(),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert target.read_bytes() == b"last-good\n"


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink", "mode"])
def test_publish_refuses_unsafe_existing_target_and_preserves_last_good(tmp_path, unsafe_kind):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    target = source_dir / "project-active-builds.json"
    backing = tmp_path / "backing"
    backing.write_bytes(b"last-good\n")
    backing.chmod(0o640)
    if unsafe_kind == "symlink":
        target.symlink_to(backing)
    elif unsafe_kind == "hardlink":
        os.link(backing, target)
    else:
        target.write_bytes(b"last-good\n")
        target.chmod(0o644)

    with pytest.raises(publisher.PublishError, match="TARGET_UNSAFE"):
        publisher.publish_document(
            target,
            _encoded(),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert backing.read_bytes() == b"last-good\n"
    if unsafe_kind == "mode":
        assert target.read_bytes() == b"last-good\n"


def test_pre_replace_failure_preserves_last_good_and_removes_temporary(tmp_path, monkeypatch):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    target = source_dir / "project-active-builds.json"
    target.write_bytes(b"last-good\n")
    target.chmod(0o640)

    def fail_replace(*_args, **_kwargs):
        raise OSError("synthetic")

    monkeypatch.setattr(publisher.os, "replace", fail_replace)
    with pytest.raises(publisher.PublishError, match="ATOMIC_REPLACE_FAILED"):
        publisher.publish_document(
            target,
            _encoded(),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )

    assert target.read_bytes() == b"last-good\n"
    assert not list(source_dir.glob(".project-active-builds.json.tmp-*"))


def test_post_replace_directory_fsync_failure_is_typed_effect_unknown(tmp_path, monkeypatch):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    target = source_dir / "project-active-builds.json"
    target.write_bytes(b"last-good\n")
    target.chmod(0o640)
    real_fsync = publisher.os.fsync

    def fail_directory_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("synthetic durability failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(publisher.os, "fsync", fail_directory_fsync)
    with pytest.raises(publisher.PublishError, match="PUBLISH_EFFECT_UNKNOWN"):
        publisher.publish_document(
            target,
            _encoded(),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert target.read_bytes() != b"last-good\n"


def test_post_replace_validation_failure_is_typed_effect_unknown(tmp_path, monkeypatch):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    target = source_dir / "project-active-builds.json"
    target.write_bytes(b"last-good\n")
    target.chmod(0o640)
    real_validate = publisher._validate_target
    calls = 0

    def fail_only_post_commit(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise publisher.PublishError("TARGET_UNSAFE")
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(publisher, "_validate_target", fail_only_post_commit)
    with pytest.raises(publisher.PublishError, match="PUBLISH_EFFECT_UNKNOWN"):
        publisher.publish_document(
            target,
            _encoded(),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert target.read_bytes() != b"last-good\n"


def test_cleanup_failure_is_sanitized_and_does_not_mask_precommit_effect_state(
    tmp_path, monkeypatch
):
    source_dir = tmp_path / "sources"
    _safe_directory(source_dir)
    target = source_dir / "project-active-builds.json"
    target.write_bytes(b"last-good\n")
    target.chmod(0o640)

    monkeypatch.setattr(
        publisher.os,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace secret")),
    )
    real_unlink = publisher.os.unlink

    def fail_temporary_unlink(path, *args, **kwargs):
        if str(path).startswith(".project-active-builds.json.tmp-"):
            raise OSError("cleanup secret")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(publisher.os, "unlink", fail_temporary_unlink)
    with pytest.raises(publisher.PublishError, match="TEMPORARY_CLEANUP_FAILED") as error:
        publisher.publish_document(
            target,
            _encoded(),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert "secret" not in str(error.value)
    assert target.read_bytes() == b"last-good\n"


@pytest.mark.parametrize(
    "reason, expected_status",
    [("PUBLISH_EFFECT_UNKNOWN", 3), ("TEMPORARY_CLEANUP_FAILED", 1)],
)
def test_main_emits_only_stable_reason_and_distinct_effect_status(
    monkeypatch, capsys, reason, expected_status
):
    monkeypatch.setattr(publisher.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        publisher.grp, "getgrnam", lambda _name: SimpleNamespace(gr_gid=os.getgid())
    )
    monkeypatch.setattr(publisher, "collection_due", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(publisher, "collect_document", _encoded)

    def fail_publish(*_args, **_kwargs):
        raise publisher.PublishError(reason) from OSError("underlying secret")

    monkeypatch.setattr(publisher, "publish_document", fail_publish)
    assert publisher.main() == expected_status
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"control-room-source: {reason}\n"
    assert "secret" not in captured.err


def test_main_skips_github_collection_when_artifact_is_not_due(monkeypatch, capsys):
    monkeypatch.setattr(publisher.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        publisher.grp, "getgrnam", lambda _name: SimpleNamespace(gr_gid=os.getgid())
    )
    monkeypatch.setattr(publisher, "collection_due", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        publisher,
        "collect_document",
        lambda *_args, **_kwargs: pytest.fail("GitHub collection must be skipped"),
    )
    monkeypatch.setattr(
        publisher,
        "publish_document",
        lambda *_args, **_kwargs: pytest.fail("publication must be skipped"),
    )

    assert publisher.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "control-room-source: FRESH_NOOP\n"
    assert captured.err == ""


def test_update_lane_invokes_publisher_each_tick_and_failure_is_nonfatal():
    script = (Path(__file__).parents[1] / "app" / "deploy" / "update.sh").read_text()
    command = 'if /usr/bin/python3 "$APP_DIR/scripts/publish_control_room_active_builds.py"; then'
    assert command in script
    block = script.split("# BEGIN CONTROL_ROOM_ACTIVE_BUILDS_PUBLISH\n", 1)[1].split(
        "# END CONTROL_ROOM_ACTIVE_BUILDS_PUBLISH", 1
    )[0]
    assert "exit " not in block
    assert "project active-build source publication deferred" in block
    assert "project active-build source publication effect unknown" in block
    assert script.index(command) < script.index("ADMIN_UNIT_UPDATED=0")
