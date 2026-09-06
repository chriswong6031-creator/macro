from __future__ import annotations

import json
import os
import plistlib
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "ops" / "launchd" / "run_research_feed.sh"
PLIST = ROOT / "ops" / "launchd" / "com.mastermindx.research-feed.plist"
CANONICAL_DB = "/Volumes/STORAGE/MastermindX/marketdesk/db/marketdesk.sqlite"
CANONICAL_REPO = "mastermindx-market-intelligence/macro"
LEGACY_REPO = "chriswong6031-creator/macro"
LEGACY_DB_SUFFIX = "mastermind-research/marketdesk_paper_extractor/db/marketdesk.sqlite"


def _write_db(path: Path, timestamps: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE papers (vaulted_at TEXT)")
        conn.executemany(
            "INSERT INTO papers(vaulted_at) VALUES (?)",
            [(timestamp,) for timestamp in timestamps],
        )


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_feed(
    tmp_path: Path,
    *,
    timestamps: list[str],
    watermark: str | None,
    active_runs: list[dict[str, object]] | None = None,
    list_rc: int = 0,
    dispatch_rc: int = 0,
    lock_exists: bool = False,
    legacy_timestamps: list[str] | None = None,
    db_override: str = "external",
    valid_schema: bool = True,
    producer_running: bool = True,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Path]]:
    external_db = tmp_path / "external" / "marketdesk.sqlite"
    legacy_db = tmp_path / "home" / LEGACY_DB_SUFFIX
    legacy_data_db = tmp_path / "home" / "mastermind-research/marketdesk_paper_extractor/data/marketdesk.sqlite"
    missing_db = tmp_path / "missing" / "marketdesk.sqlite"
    watermark_path = tmp_path / "state" / "feed.watermark"
    legacy_watermark = tmp_path / "home" / "mastermind-research" / ".feed_vault_watermark"
    lock_dir = tmp_path / "state" / "feed.lock"
    legacy_lock = tmp_path / "home" / "mastermind-research" / ".feed.lock"
    log_path = tmp_path / "logs" / "feed.log"
    legacy_log = tmp_path / "home" / "mastermind-research" / "feed.log"
    capture = tmp_path / "gh.commands"
    gh = tmp_path / "bin" / "gh"
    launchctl = tmp_path / "bin" / "launchctl"
    gh.parent.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)
    watermark_path.parent.mkdir(parents=True)
    legacy_watermark.parent.mkdir(parents=True, exist_ok=True)

    if db_override != "missing":
        if valid_schema:
            _write_db(external_db, timestamps)
        else:
            external_db.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(external_db) as conn:
                conn.execute("CREATE TABLE wrong_table (value TEXT)")
    if legacy_timestamps is not None or db_override == "legacy":
        _write_db(legacy_db, legacy_timestamps if legacy_timestamps is not None else timestamps)
    if db_override == "legacy_data":
        _write_db(legacy_data_db, timestamps)
    if watermark is not None:
        watermark_path.write_text(watermark + "\n", encoding="utf-8")
        legacy_watermark.write_text(watermark + "\n", encoding="utf-8")
    if lock_exists:
        lock_dir.mkdir()
        legacy_lock.mkdir()

    _write_executable(
        gh,
        """#!/bin/bash
set -eu
printf '%s
' "$*" >> "$GH_CAPTURE"
if [ "${1:-} ${2:-}" = "run list" ]; then
  if [ "${GH_LIST_RC:-0}" != "0" ]; then
    echo "fixture run-list failure" >&2
    exit "$GH_LIST_RC"
  fi
  printf '%s
' "${GH_ACTIVE_JSON:-[]}"
  exit 0
fi
if [ "${1:-} ${2:-}" = "workflow run" ]; then
  if [ "${GH_DISPATCH_RC:-0}" != "0" ]; then
    echo "fixture dispatch failure" >&2
    exit "$GH_DISPATCH_RC"
  fi
  echo "https://github.example/actions/runs/42"
  exit 0
fi
echo "unexpected gh command: $*" >&2
exit 97
""",
    )
    _write_executable(
        launchctl,
        """#!/bin/bash
set -eu
if [ "${1:-}" != "list" ]; then
  echo "unexpected launchctl command: $*" >&2
  exit 98
fi
if [ "${FEED_PRODUCER_RUNNING:-1}" = "1" ]; then
  printf '123	0	%s
' "${RESEARCH_FEED_PRODUCER_LABEL:-com.mastermindx.research-trickle}"
fi
""",
    )

    override_paths = {
        "external": external_db,
        "legacy": legacy_db,
        "legacy_data": legacy_data_db,
        "missing": missing_db,
    }
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "PATH": f"{gh.parent}:{env.get('PATH', '')}",
            "RESEARCH_FEED_WATERMARK_PATH": str(watermark_path),
            "RESEARCH_FEED_LOCK_DIR": str(lock_dir),
            "RESEARCH_FEED_LOG_PATH": str(log_path),
            "RESEARCH_FEED_GH_BIN": str(gh),
            "RESEARCH_FEED_LAUNCHCTL_BIN": str(launchctl),
            "RESEARCH_FEED_PYTHON_BIN": sys.executable,
            "RESEARCH_FEED_REPO": CANONICAL_REPO,
            "RESEARCH_FEED_WORKFLOW": "research-ingest.yml",
            "RESEARCH_FEED_BRANCH": "main",
            "RESEARCH_FEED_PRODUCER_LABEL": "com.mastermindx.research-trickle",
            "GH_CAPTURE": str(capture),
            "GH_ACTIVE_JSON": json.dumps(active_runs or []),
            "GH_LIST_RC": str(list_rc),
            "GH_DISPATCH_RC": str(dispatch_rc),
            "FEED_PRODUCER_RUNNING": "1" if producer_running else "0",
        }
    )
    if db_override != "unset":
        env["RESEARCH_FEED_DB_PATH"] = str(override_paths[db_override])
    result = subprocess.run(
        ["/bin/bash", str(RUNNER)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, {
        "db": external_db,
        "legacy_db": legacy_db,
        "legacy_data_db": legacy_data_db,
        "watermark": watermark_path,
        "legacy_watermark": legacy_watermark,
        "lock": lock_dir,
        "legacy_lock": legacy_lock,
        "log": log_path,
        "legacy_log": legacy_log,
        "capture": capture,
    }


def _commands(paths: dict[str, Path]) -> list[str]:
    capture = paths["capture"]
    return capture.read_text(encoding="utf-8").splitlines() if capture.exists() else []


def test_tracked_runner_and_plist_are_parseable_and_pin_the_existing_service() -> None:
    assert RUNNER.is_file()
    assert PLIST.is_file()
    parsed = subprocess.run(
        ["/bin/bash", "-n", str(RUNNER)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert parsed.returncode == 0, parsed.stderr

    with PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    assert payload["Label"] == "com.mastermindx.research-feed"
    assert payload["ProgramArguments"] == [
        "/bin/bash",
        "/Users/chriswong/mastermind-research/feed.sh",
    ]
    assert payload["StartInterval"] == 900
    assert payload["RunAtLoad"] is True
    assert payload["ProcessType"] == "Background"
    assert payload["StandardOutPath"] == "/Users/chriswong/mastermind-research/feed.out.log"
    assert payload["StandardErrorPath"] == "/Users/chriswong/mastermind-research/feed.err.log"
    assert payload["EnvironmentVariables"]["PATH"] == "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    assert "WorkingDirectory" not in payload
    assert "KeepAlive" not in payload


def test_runner_defaults_to_the_producers_canonical_storage_db() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert CANONICAL_DB in source
    assert CANONICAL_REPO in source
    assert LEGACY_REPO not in source
    assert 'DB="$APP/db/marketdesk.sqlite"' not in source
    assert "RESEARCH_FEED_DB_PATH" in source
    assert "legacy internal database is forbidden" in source


def test_external_db_wins_when_a_stale_legacy_db_is_present(tmp_path: Path) -> None:
    previous = "2026-08-15T02:55:31.468766+00:00"
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[latest],
        legacy_timestamps=[previous],
        watermark=previous,
    )
    assert result.returncode == 0, result.stderr
    assert sum(command.startswith("workflow run") for command in _commands(paths)) == 1
    assert paths["watermark"].read_text(encoding="utf-8").strip() == latest


@pytest.mark.parametrize("db_override", ["legacy", "legacy_data"])
def test_legacy_internal_database_override_is_rejected(tmp_path: Path, db_override: str) -> None:
    previous = "2026-08-15T02:55:31.468766+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=["2026-09-06T14:00:00+00:00"],
        legacy_timestamps=[previous],
        watermark=previous,
        db_override=db_override,
    )
    assert result.returncode != 0
    assert _commands(paths) == []
    assert "legacy internal database is forbidden" in paths["log"].read_text(encoding="utf-8")


def test_missing_external_database_fails_closed_without_github(tmp_path: Path) -> None:
    previous = "2026-09-06T13:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[],
        watermark=previous,
        db_override="missing",
    )
    assert result.returncode != 0
    assert _commands(paths) == []
    assert paths["watermark"].read_text(encoding="utf-8").strip() == previous
    assert "canonical database unavailable" in paths["log"].read_text(encoding="utf-8")


def test_database_without_required_schema_fails_closed(tmp_path: Path) -> None:
    result, paths = _run_feed(
        tmp_path,
        timestamps=[],
        watermark="2026-09-06T13:00:00+00:00",
        valid_schema=False,
    )
    assert result.returncode != 0
    assert _commands(paths) == []
    assert "database query failed" in paths["log"].read_text(encoding="utf-8")


def test_missing_watermark_adopts_current_state_without_dispatch(tmp_path: Path) -> None:
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=["2026-09-06T13:00:00+00:00", latest],
        watermark=None,
    )
    assert result.returncode == 0, result.stderr
    assert paths["watermark"].read_text(encoding="utf-8").strip() == latest
    assert not any(command.startswith("workflow run") for command in _commands(paths))
    assert "initialized watermark" in paths["log"].read_text(encoding="utf-8")


def test_no_new_rows_does_not_query_or_dispatch_github(tmp_path: Path) -> None:
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(tmp_path, timestamps=[latest], watermark=latest)
    assert result.returncode == 0, result.stderr
    assert _commands(paths) == []
    assert paths["watermark"].read_text(encoding="utf-8").strip() == latest
    assert "nothing new" in paths["log"].read_text(encoding="utf-8")


def test_new_row_dispatches_once_and_advances_watermark_only_after_success(tmp_path: Path) -> None:
    previous = "2026-09-06T13:00:00+00:00"
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[previous, latest],
        watermark=previous,
    )
    assert result.returncode == 0, result.stderr
    commands = _commands(paths)
    assert sum(command.startswith("run list") for command in commands) == 1
    assert sum(command.startswith("workflow run") for command in commands) == 1
    dispatch = next(command for command in commands if command.startswith("workflow run"))
    assert "research-ingest.yml" in dispatch
    assert f"--repo {CANONICAL_REPO}" in dispatch
    assert "--ref main" in dispatch
    assert paths["watermark"].read_text(encoding="utf-8").strip() == latest
    assert "ingest triggered" in paths["log"].read_text(encoding="utf-8")


def test_dispatch_failure_is_red_and_preserves_watermark(tmp_path: Path) -> None:
    previous = "2026-09-06T13:00:00+00:00"
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[previous, latest],
        watermark=previous,
        dispatch_rc=23,
    )
    assert result.returncode != 0
    assert paths["watermark"].read_text(encoding="utf-8").strip() == previous
    assert sum(command.startswith("workflow run") for command in _commands(paths)) == 1
    assert "dispatch failed" in paths["log"].read_text(encoding="utf-8")


@pytest.mark.parametrize("status", ["waiting", "requested", "pending"])
def test_all_nonterminal_github_run_states_are_deduplicated(tmp_path: Path, status: str) -> None:
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[latest],
        watermark="2026-09-06T13:00:00+00:00",
        active_runs=[
            {
                "databaseId": 88,
                "status": status,
                "createdAt": "2026-09-06T14:00:05Z",
                "url": "https://github.example/actions/runs/88",
            }
        ],
    )
    assert result.returncode == 0, result.stderr
    commands = _commands(paths)
    assert sum(command.startswith("run list") for command in commands) == 1
    assert not any(command.startswith("workflow run") for command in commands)
    assert paths["watermark"].read_text(encoding="utf-8").strip() == latest


def test_active_run_newer_than_latest_row_dedupes_and_advances_watermark(tmp_path: Path) -> None:
    previous = "2026-09-06T13:00:00+00:00"
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[previous, latest],
        watermark=previous,
        active_runs=[
            {
                "databaseId": 99,
                "status": "in_progress",
                "createdAt": "2026-09-06T14:01:00Z",
                "url": "https://github.example/actions/runs/99",
            }
        ],
    )
    assert result.returncode == 0, result.stderr
    assert not any(command.startswith("workflow run") for command in _commands(paths))
    assert paths["watermark"].read_text(encoding="utf-8").strip() == latest
    assert "already covers latest vault row" in paths["log"].read_text(encoding="utf-8")


def test_active_run_older_than_latest_row_defers_without_moving_watermark(tmp_path: Path) -> None:
    previous = "2026-09-06T13:00:00+00:00"
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[previous, latest],
        watermark=previous,
        active_runs=[
            {
                "databaseId": 98,
                "status": "queued",
                "createdAt": "2026-09-06T13:59:00Z",
                "url": "https://github.example/actions/runs/98",
            }
        ],
    )
    assert result.returncode == 0, result.stderr
    assert not any(command.startswith("workflow run") for command in _commands(paths))
    assert paths["watermark"].read_text(encoding="utf-8").strip() == previous
    assert "predates latest vault row" in paths["log"].read_text(encoding="utf-8")


def test_active_run_query_failure_fails_closed_without_dispatch(tmp_path: Path) -> None:
    previous = "2026-09-06T13:00:00+00:00"
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[previous, latest],
        watermark=previous,
        list_rc=19,
    )
    assert result.returncode != 0
    assert not any(command.startswith("workflow run") for command in _commands(paths))
    assert paths["watermark"].read_text(encoding="utf-8").strip() == previous
    assert "could not reconcile active ingestion runs" in paths["log"].read_text(encoding="utf-8")


def test_existing_lock_suppresses_a_second_feed_process(tmp_path: Path) -> None:
    previous = "2026-09-06T13:00:00+00:00"
    latest = "2026-09-06T14:00:00+00:00"
    result, paths = _run_feed(
        tmp_path,
        timestamps=[previous, latest],
        watermark=previous,
        lock_exists=True,
    )
    assert result.returncode == 0, result.stderr
    assert _commands(paths) == []
    assert paths["watermark"].read_text(encoding="utf-8").strip() == previous


def test_invalid_watermark_fails_closed_without_querying_github(tmp_path: Path) -> None:
    result, paths = _run_feed(
        tmp_path,
        timestamps=["2026-09-06T14:00:00+00:00"],
        watermark="not-a-timestamp'; DROP TABLE papers; --",
    )
    assert result.returncode != 0
    assert _commands(paths) == []
    assert "invalid watermark" in paths["log"].read_text(encoding="utf-8")
