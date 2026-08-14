"""Conflict-marker ratchet must consume ci-plan's file list on a shallow clone.

Measured 2026-08-13 after #5564: packs checkout fetch-depth:1, so
``origin/main...HEAD`` is a bad revision (#5519 pack-7, #5499 pack-8):

    check_conflict_markers: ERROR — cannot classify files changed from
    origin/main: fatal: bad revision 'origin/main...HEAD'
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_conflict_markers as MARKERS

_OPEN = "<" * 7 + " ours\n"
_CLOSE = ">" * 7 + " theirs\n"


def test_planner_json_scans_listed_files_without_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "clean.html.j2").write_text("<div>ok</div>\n")
    (tmp_path / "templates" / "bad.html.j2").write_text(_OPEN + "x\n" + _CLOSE)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("out of scope\n")
    monkeypatch.setenv(
        "CI_CHANGED_FILES_JSON",
        '["templates/clean.html.j2","templates/bad.html.j2","docs/note.md"]',
    )
    monkeypatch.chdir(tmp_path)
    assert MARKERS.main(["--changed-from", "origin/main"]) == 1


def test_planner_json_null_is_verified_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "bad.html.j2").write_text(_OPEN + "x\n" + _CLOSE)
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", "null")
    monkeypatch.chdir(tmp_path)
    assert MARKERS.main(["--changed-from", "origin/main"]) == 0


def test_malformed_planner_json_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", "{nope")
    monkeypatch.chdir(tmp_path)
    assert MARKERS.main(["--changed-from", "origin/main"]) == 2


def test_unset_env_still_uses_git_changed_from(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI_CHANGED_FILES_JSON", raising=False)
    monkeypatch.chdir(tmp_path)
    rc = MARKERS.main(["--changed-from", "origin/main"])
    assert rc == 2


def test_planner_paths_helpers() -> None:
    assert MARKERS.planner_changed_paths(None) is None
    assert MARKERS.planner_changed_paths("") is None
    assert MARKERS.planner_changed_paths("null") == []
    assert MARKERS.planner_changed_paths('["a.py",""]') == ["a.py"]
    with pytest.raises(RuntimeError, match="malformed"):
        MARKERS.planner_changed_paths("{nope")
    with pytest.raises(RuntimeError, match="array of strings"):
        MARKERS.planner_changed_paths("[1]")
