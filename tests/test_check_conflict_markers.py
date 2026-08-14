"""Conflict-marker ratchet must consume ci-plan's file list on a shallow clone.

Measured 2026-08-13 after #5564: packs checkout fetch-depth:1, so
``origin/main...HEAD`` is a bad revision (#5519 pack-7, #5499 pack-8):

    check_conflict_markers: ERROR — cannot classify files changed from
    origin/main: fatal: bad revision 'origin/main...HEAD'

That list arrives as a FILE since 2026-08-14 (run 31775693780): carried inline
it measured 350,264 bytes, past execve's 131,072-byte MAX_ARG_STRLEN, and every
pack died at launch before this guard — or any other — could run.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_conflict_markers as MARKERS

_OPEN = "<" * 7 + " ours\n"
_CLOSE = ">" * 7 + " theirs\n"


@pytest.fixture(autouse=True)
def _isolate_planner_transports(monkeypatch: pytest.MonkeyPatch) -> None:
    """This suite runs INSIDE a pack, which exports the live PR's diff.

    Both transport names must go. Measured cost of missing one (#5560, the
    inline form): tests that monkeypatched the wrong layer asserted against the
    hosted runner's own diff and redded pack-1 on every unrelated PR. The file
    handle is the same trap with a newer name, and it OUT-RANKS the inline
    value — so a suite that isolates only ``CI_CHANGED_FILES_JSON`` is
    isolating the transport that no longer wins.
    """
    for name in ("CI_CHANGED_FILES_FILE", "CI_CHANGED_FILES_JSON"):
        monkeypatch.delenv(name, raising=False)


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


def test_git_classify_failure_emits_line_starting_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sweeper live-inherited-red matches this string; it must start the line."""
    monkeypatch.delenv("CI_CHANGED_FILES_JSON", raising=False)
    monkeypatch.chdir(tmp_path)
    assert MARKERS.main(["--changed-from", "origin/main"]) == 2
    lines = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("::")
    ]
    assert lines, "classify failure must emit a GitHub workflow command"
    assert lines[0].startswith("::error title=legacy-job-conflict-markers::")
    assert "cannot classify files changed from origin/" in lines[0]


def _handle(tmp_path: Path, body: str) -> str:
    path = tmp_path / "changed-files.json"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_planner_file_scans_listed_files_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file transport carries the same ratchet the env string carried."""
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "clean.html.j2").write_text("<div>ok</div>\n")
    (tmp_path / "templates" / "bad.html.j2").write_text(_OPEN + "x\n" + _CLOSE)
    monkeypatch.setenv(
        "CI_CHANGED_FILES_FILE",
        _handle(
            tmp_path,
            '["templates/clean.html.j2","templates/bad.html.j2","docs/note.md"]',
        ),
    )
    monkeypatch.chdir(tmp_path)
    assert MARKERS.main(["--changed-from", "origin/main"]) == 1


def test_planner_file_outranks_a_stale_inline_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FILE FIRST. A leftover env string must not decide what gets scanned.

    Both names can be present at once — a pack exports the handle while an
    older step's inline value lingers — and the two can disagree. The artifact
    the pack downloaded is the authority; deferring to the string would scan a
    diff nobody published.
    """
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "bad.html.j2").write_text(_OPEN + "x\n" + _CLOSE)
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", '["templates/bad.html.j2"]')
    monkeypatch.setenv("CI_CHANGED_FILES_FILE", _handle(tmp_path, "null"))
    monkeypatch.chdir(tmp_path)
    assert MARKERS.main(["--changed-from", "origin/main"]) == 0


def test_malformed_planner_file_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unreadable, empty and corrupt all fail closed — never a silent git fallback."""
    monkeypatch.delenv("CI_CHANGED_FILES_JSON", raising=False)
    monkeypatch.chdir(tmp_path)
    for body in ("{nope", "", "[1]"):
        monkeypatch.setenv("CI_CHANGED_FILES_FILE", _handle(tmp_path, body))
        assert MARKERS.main(["--changed-from", "origin/main"]) == 2, body
    monkeypatch.setenv("CI_CHANGED_FILES_FILE", str(tmp_path / "never-written.json"))
    assert MARKERS.main(["--changed-from", "origin/main"]) == 2


def test_planner_file_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert MARKERS.planner_changed_paths_from_file(
        _handle(tmp_path, '["a.py",""]')
    ) == ["a.py"]
    assert MARKERS.planner_changed_paths_from_file(_handle(tmp_path, "null")) == []
    with pytest.raises(RuntimeError, match="unreadable"):
        MARKERS.planner_changed_paths_from_file(str(tmp_path / "absent.json"))
    with pytest.raises(RuntimeError, match="empty"):
        MARKERS.planner_changed_paths_from_file(_handle(tmp_path, "  \n"))
    # Unset handle: the inline decoder answers, unchanged.
    monkeypatch.delenv("CI_CHANGED_FILES_FILE", raising=False)
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", '["b.md"]')
    assert MARKERS.planner_paths_from_environment() == ["b.md"]
    monkeypatch.delenv("CI_CHANGED_FILES_JSON")
    assert MARKERS.planner_paths_from_environment() is None


def test_planner_paths_helpers() -> None:
    assert MARKERS.planner_changed_paths(None) is None
    assert MARKERS.planner_changed_paths("") is None
    assert MARKERS.planner_changed_paths("null") == []
    assert MARKERS.planner_changed_paths('["a.py",""]') == ["a.py"]
    with pytest.raises(RuntimeError, match="malformed"):
        MARKERS.planner_changed_paths("{nope")
    with pytest.raises(RuntimeError, match="array of strings"):
        MARKERS.planner_changed_paths("[1]")
