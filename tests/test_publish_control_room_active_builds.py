"""Fail-closed tests for the Control Room GitHub-source publisher."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
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


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b'{"schema":"project_active_builds.v1","schema":"wrong"}',
        b'{"schema":"project_active_builds.v1","value":NaN}',
        b'{"schema":"wrong","collected_at":"2026-08-28T00:00:00+00:00"}',
        b'{"schema":"project_active_builds.v1","collected_at":"not-a-clock"}',
        b'{"schema":"project_active_builds.v1","collected_at":"2026-08-28T00:00:00"}',
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


def test_update_lane_invokes_publisher_each_tick_and_failure_is_nonfatal():
    script = (Path(__file__).parents[1] / "app" / "deploy" / "update.sh").read_text()
    command = (
        'if ! /usr/bin/python3 "$APP_DIR/scripts/publish_control_room_active_builds.py"; then'
    )
    assert command in script
    block = script.split("# BEGIN CONTROL_ROOM_ACTIVE_BUILDS_PUBLISH\n", 1)[1].split(
        "# END CONTROL_ROOM_ACTIVE_BUILDS_PUBLISH", 1
    )[0]
    assert "exit " not in block
    assert "project active-build source publication deferred" in block
    assert script.index(command) < script.index("ADMIN_UNIT_UPDATED=0")
