"""ci_plan_changed_files: the planner's metadata diff must widen on every doubt.

The script replaced ci-plan's fetch-depth:0 history diff (2026-08-14 incident).
Its one forbidden output is a PARTIAL list: a narrowed suite on a
mis-understood diff is a silent false green, so every uncertainty — HTTP
error, malformed entry, 3000-file truncation, missing token — must emit the
literal token `null` (full suite), and only a cleanly terminated listing may
emit paths.

Run: python3 -m pytest tests/test_ci_plan_changed_files.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ci_plan_changed_files", ROOT / "scripts" / "ci_plan_changed_files.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pages: list[list[dict[str, object]] | None],
) -> tuple[int, str]:
    """Drive main() against a scripted sequence of API pages."""
    calls = iter(pages)
    monkeypatch.setattr(MOD, "_fetch_page", lambda url, token: next(calls))
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    code = MOD.main(["--repo", "o/r", "--pr", "7"])
    out = [
        line
        for line in capsys.readouterr().out.splitlines()
        if not line.startswith("::")
    ]
    assert len(out) == 1, f"stdout must be exactly one payload line, got {out}"
    return code, out[0]


def test_clean_listing_emits_sorted_paths_with_rename_both_sides(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, line = _run(
        monkeypatch,
        capsys,
        [[
            {"filename": "b.py"},
            {"filename": "a.py", "previous_filename": "z_old.py"},
        ]],
    )
    assert code == 0
    assert json.loads(line) == ["a.py", "b.py", "z_old.py"]


def test_http_failure_widens_to_null(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, line = _run(monkeypatch, capsys, [None])
    assert code == 0 and line == "null"


def test_second_page_failure_discards_the_partial_first_page(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    full_page = [{"filename": f"f{index}.py"} for index in range(MOD.PER_PAGE)]
    code, line = _run(monkeypatch, capsys, [full_page, None])
    assert code == 0 and line == "null"


def test_malformed_entry_widens_to_null(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, line = _run(monkeypatch, capsys, [[{"filename": ""}]])
    assert code == 0 and line == "null"


def test_truncation_at_the_github_file_ceiling_widens(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    full_page = [{"filename": f"f{index}.py"} for index in range(MOD.PER_PAGE)]
    code, line = _run(monkeypatch, capsys, [full_page] * MOD.MAX_PAGES)
    assert code == 0 and line == "null"


def test_missing_token_widens_and_missing_pr_number_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert MOD.main(["--repo", "o/r", "--pr", "7"]) == 0
    assert capsys.readouterr().out.strip() == "null"
    monkeypatch.delenv("CI_PR_NUMBER", raising=False)
    assert MOD.main(["--repo", "o/r"]) == 2
