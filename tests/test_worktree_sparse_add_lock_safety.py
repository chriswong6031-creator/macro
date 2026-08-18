"""`git sparse-checkout add` must never leave a TRACKED file truncated —
scripts/worktree_sparse.py.

Observed directly 2026-08-18 in a session worktree with `site/` omitted:
`python3 scripts/worktree_sparse.py add site` failed partway (one soft line,
`git sparse-checkout add` failed`) and left a TRACKED file
(`site/flow/CORZ.json`) at 0 bytes on disk against 5,040 bytes committed at
HEAD, plus a stale ~49-minute-old `.git/worktrees/<name>/index.lock`. `git
checkout -- <file>` refused while that lock was present; a byte-level
`git show HEAD:<path> > <path>` restore worked.

ROOT CAUSE, reproduced here deterministically: `git sparse-checkout add`
materializes a heavy tree file-by-file. If the underlying `git` process is
killed mid-loop (this repo's own `_git()` wrapper races a 60s subprocess
timeout against exactly this call, and `subprocess.run` SIGKILLs the child on
expiry), a file it had just started writing is left truncated (created via
open+truncate, killed before the content write landed), and the `index.lock`
git creates for the whole operation is never renamed into place because the
operation never completed — so it survives as a stale lock. This is
independently reproducible against the real macro-dashboard repo (a throwaway
worktree, sparsified, `git sparse-checkout add -- site` raced against a short
subprocess timeout) and is modelled hermetically below via a small synthetic
git repo plus a `subprocess.run` interception that mimics exactly this
kill-mid-write shape, so the test is fast and has no dependency on real
timing races or on this repo's own heavy trees.

Two fixes are pinned:
  * (A)/(B) `add_dirs` — on a failed `sparse-checkout add`, print a bare
    `::error` annotation (never through a logger — see
    tests/test_gh_annotation_line_start.py) and verify+repair: any on-disk
    tracked file under the targeted dirs whose size no longer matches HEAD is
    restored byte-for-byte via `git show HEAD:<path>` (never `git checkout --`,
    which refuses while the stale lock is present).
  * (C) `refuse_if_locked` — a pre-existing `index.lock` in this checkout's
    git-dir (worktree or primary) refuses UP FRONT, before any write is
    attempted, rather than proceeding into the same corruption. The lock is
    never deleted automatically.

Run: python3 -m pytest tests/test_worktree_sparse_add_lock_safety.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from scripts import worktree_sparse as WS


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(("git", "-C", str(repo)) + args,
                           capture_output=True, text=True, check=True)
    return proc.stdout.strip()


# The exact bytes the fixture commits for the file this test corrupts. Real
# content (not empty), so a 0-byte truncation is unambiguous.
_BIG_CONTENT = b'{"ticker": "ABC", "series": [1, 2, 3, 4, 5]}\n' * 40


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed repo carrying a heavy-ish tracked dir, sparsed to omit it —
    the same shape a session worktree gets under policy R8."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    (r / "scripts").mkdir()
    (r / "scripts" / "keep.txt").write_text("keep\n", encoding="utf-8")
    big = r / "big"
    big.mkdir()
    (big / "data.json").write_bytes(_BIG_CONTENT)
    (big / "other.txt").write_text("unrelated tracked file\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    _git(r, "sparse-checkout", "init", "--cone")
    _git(r, "sparse-checkout", "set", "--cone", "--", "scripts")
    assert WS.missing_dirs(r) == ["big"], "fixture precondition: big/ starts omitted"
    return r


def _real_git_dir(repo: Path) -> Path:
    out = subprocess.run(
        ("git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-dir"),
        capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip())


def _install_kill_mid_write(monkeypatch, repo: Path, target_rel: str, target_bytes: bytes):
    """Patch `subprocess.run` inside the module so that ONLY the
    `sparse-checkout add -- big` invocation is intercepted: it simulates a
    process SIGKILLed mid-materialization by (1) writing a TRUNCATED (0-byte)
    copy of one real tracked file straight to disk — exactly what a killed
    `git` leaves, since the file is created via open+truncate before its
    content write lands — (2) leaving a stale `index.lock` in the real
    git-dir, matching what git itself leaves when the rename-into-place never
    happens, and (3) raising TimeoutExpired, matching what `subprocess.run`
    raises to the caller after it kills the child on a real timeout. Every
    other subprocess.run call (repair's `git show`, `git ls-tree`, fixture
    setup) passes through to the real implementation untouched.
    """
    real_run = subprocess.run
    gitdir = _real_git_dir(repo)

    def fake_run(cmd, *args, **kwargs):
        if (isinstance(cmd, (list, tuple))
                and len(cmd) >= 6
                and cmd[0] == "git" and cmd[3] == "sparse-checkout"
                and cmd[4] == "add"):
            abs_path = repo / target_rel
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(b"")  # truncated mid-write, like the real incident
            gitdir.mkdir(parents=True, exist_ok=True)
            (gitdir / "index.lock").write_bytes(b"")  # stale lock left behind
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0.01))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(WS.subprocess, "run", fake_run)


# ── 1. the bug: a killed `add` must not leave a truncated tracked file ──────

def test_failed_add_repairs_a_truncated_tracked_file(repo, monkeypatch, capsys):
    _install_kill_mid_write(monkeypatch, repo, "big/data.json", _BIG_CONTENT)

    rc = WS.add_dirs(["big"], root=repo, timeout=0.01)
    blob = "".join(capsys.readouterr())

    assert rc != 0, "a failed `git sparse-checkout add` must exit non-zero"

    restored = (repo / "big" / "data.json").read_bytes()
    assert restored == _BIG_CONTENT, (
        "a tracked file left truncated by a killed `sparse-checkout add` was "
        f"NOT repaired back to its committed content (got {len(restored)} bytes, "
        f"want {len(_BIG_CONTENT)}):\n{blob}"
    )


def test_failed_add_emits_a_github_annotation_at_line_start(repo, monkeypatch, capsys):
    _install_kill_mid_write(monkeypatch, repo, "big/data.json", _BIG_CONTENT)

    WS.add_dirs(["big"], root=repo, timeout=0.01)
    out = capsys.readouterr()
    lines = (out.out + out.err).splitlines()
    errors = [ln for ln in lines if "::error" in ln]

    assert errors, "a failed `sparse-checkout add` produced no ::error annotation"
    assert any(ln.startswith("::error") for ln in errors), (
        f"annotation did not open the line, so GitHub will drop it: {errors}")


def test_repair_does_not_touch_a_file_that_never_materialized(repo, monkeypatch):
    """A tracked path under `big/` that the killed process never reached (never
    written to disk at all) is not corruption — it stays absent, not created."""
    _install_kill_mid_write(monkeypatch, repo, "big/data.json", _BIG_CONTENT)

    WS.add_dirs(["big"], root=repo, timeout=0.01)

    assert not (repo / "big" / "other.txt").exists(), (
        "repair must not materialize a tracked path the failed add never wrote")


# ── 2. the other half: refuse up front on a pre-existing stale lock ─────────

def test_preexisting_lock_refuses_before_any_write(repo, monkeypatch, capsys):
    gitdir = _real_git_dir(repo)
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")

    call_log = []
    real_run = subprocess.run

    def spy_run(cmd, *a, **kw):
        if (isinstance(cmd, (list, tuple)) and len(cmd) >= 5
                and cmd[0] == "git" and cmd[3] == "sparse-checkout" and cmd[4] == "add"):
            call_log.append(cmd)
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(WS.subprocess, "run", spy_run)

    rc = WS.add_dirs(["big"], root=repo)
    blob = "".join(capsys.readouterr())

    assert rc != 0, "a pre-existing lock must refuse, not proceed"
    assert not call_log, (
        "`git sparse-checkout add` was invoked despite a pre-existing lock — "
        "the refusal must happen BEFORE any write is attempted")
    assert not (repo / "big").exists(), "nothing should have been materialized"
    assert "::error" in blob and str(lock) in blob, (
        f"refusal did not name the lock path in an ::error annotation:\n{blob}")
    assert lock.exists(), "a lock this run did not create must never be auto-deleted"


def test_index_lock_path_resolves_the_worktree_gitdir(repo):
    gitdir = _real_git_dir(repo)
    assert WS.index_lock_path(repo) == gitdir / "index.lock"


# ── 3. the clean path is unaffected ──────────────────────────────────────────

def test_successful_add_still_works_and_reports_nothing_wrong(repo, capsys):
    rc = WS.add_dirs(["big"], root=repo)
    blob = "".join(capsys.readouterr())

    assert rc == 0, f"a normal, uninterrupted add must still succeed:\n{blob}"
    assert (repo / "big" / "data.json").read_bytes() == _BIG_CONTENT
    assert "::error" not in blob
