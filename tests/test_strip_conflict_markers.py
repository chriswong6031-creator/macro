"""Lane gate: a conflicted stash/rebase apply must be stripped, never committed.

2026-08-01 incident: `git pull --rebase --autostash` in a push-retry loop left a
conflicted autostash apply in the working tree, and the next broad
`git add site/ templates/` staged the marker lines verbatim — d29e4dd44d shipped
them across 1,704 committed pages, served live until c1bfee482a healed them.
scripts/ci/strip_conflict_markers.sh now runs before every broad add: any file
dirty vs HEAD carrying both a column-0 conflict opener and closer is restored
from HEAD. These tests replay the incident with a real git repo, asserting on
restored BYTES (not exit codes), per the mirrored-guard-vacuity lesson.

Marker strings are built by repetition so no literal marker line ever appears
in this file (check_conflict_markers scans raw lines).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "ci" / "strip_conflict_markers.sh"

OPENER = "<" * 7 + " Updated upstream"
SEP = "=" * 7
CLOSER = ">" * 7 + " Stashed changes"

CLEAN_PAGE = "<html><body>committed render</body></html>\n"
FRESH_EDIT = "<html><body>this run's legit render</body></html>\n"
WRECKED = f"before\n{OPENER}\nstale side\n{SEP}\nfresh side\n{CLOSER}\nafter\n"


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )
    return out.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "lane"
    (r / "site").mkdir(parents=True)
    (r / "templates").mkdir()
    (r / "data").mkdir()
    _git(r.parent, "init", "-q", str(r))
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "site" / "wrecked.html").write_text(CLEAN_PAGE)
    (r / "site" / "legit.html").write_text(CLEAN_PAGE)
    (r / "data" / "ledger.jsonl").write_text('{"day": 1}\n')
    (r / "site" / "underline.md").write_text("Heading\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return r


def _run(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return out.stdout


def test_wrecked_file_restored_legit_edit_untouched(repo: Path) -> None:
    (repo / "site" / "wrecked.html").write_text(WRECKED)
    (repo / "site" / "legit.html").write_text(FRESH_EDIT)
    out = _run(repo)
    assert (repo / "site" / "wrecked.html").read_text() == CLEAN_PAGE
    assert (repo / "site" / "legit.html").read_text() == FRESH_EDIT
    # annotation must START its line or GitHub silently drops it
    assert any(
        line.startswith("::warning") for line in out.splitlines()
    ), out


def test_staged_wreckage_is_unstaged_too(repo: Path) -> None:
    (repo / "site" / "wrecked.html").write_text(WRECKED)
    _git(repo, "add", "site/wrecked.html")
    _run(repo)
    assert (repo / "site" / "wrecked.html").read_text() == CLEAN_PAGE
    staged = _git(repo, "diff", "--cached", "--name-only")
    assert "site/wrecked.html" not in staged


def test_bare_separator_line_is_not_wreckage(repo: Path) -> None:
    # a setext-style underline is a legitimate line: only opener+closer together
    # mark a file as wreckage
    (repo / "site" / "underline.md").write_text(f"Heading\n{SEP}\nbody\n")
    out = _run(repo)
    assert (repo / "site" / "underline.md").read_text() == f"Heading\n{SEP}\nbody\n"
    assert "::warning" not in out


def test_opener_without_closer_is_left_alone(repo: Path) -> None:
    # half a marker pair (e.g. page content that quotes git output) is not
    # restorable wreckage; check_conflict_markers still guards the commit path
    half = f"before\n{OPENER}\nafter\n"
    (repo / "site" / "wrecked.html").write_text(half)
    _run(repo)
    assert (repo / "site" / "wrecked.html").read_text() == half


def test_new_wrecked_file_is_unstaged_not_committed(repo: Path) -> None:
    (repo / "site" / "brandnew.html").write_text(WRECKED)
    _git(repo, "add", "site/brandnew.html")
    out = _run(repo)
    staged = _git(repo, "diff", "--cached", "--name-only")
    assert "site/brandnew.html" not in staged
    assert any(line.startswith("::warning") for line in out.splitlines()), out


def test_clean_tree_is_silent(repo: Path) -> None:
    out = _run(repo)
    assert "::warning" not in out
    assert "stripped" not in out


def test_sweep_scope_respects_args(repo: Path) -> None:
    (repo / "data" / "ledger.jsonl").write_text(WRECKED)
    _run(repo, "site/")
    # data/ outside the requested sweep — left untouched
    assert (repo / "data" / "ledger.jsonl").read_text() == WRECKED
    _run(repo)
    assert (repo / "data" / "ledger.jsonl").read_text() == '{"day": 1}\n'
