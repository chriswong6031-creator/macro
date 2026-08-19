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

# Captured once, before any test monkeypatches `WS.subprocess.Popen` — `WS.subprocess`
# and this module's `subprocess` are the SAME singleton module object, so a helper
# that re-reads `subprocess.Popen` fresh on every call would, in a test that installs
# two fakes in sequence, capture the FIRST fake instead of the true original and
# silently chain onto it. Every fake-Popen helper below must delegate to this fixed
# reference, never to a freshly-read `subprocess.Popen`.
_REAL_POPEN = subprocess.Popen


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


class _KilledProc:
    """Stands in for a real `Popen` whose child fully ignores SIGTERM, so
    `_run_git_timed`'s escalation ladder runs to the SIGKILL step — the
    still-possible-in-principle last resort the repair path backstops.
    `communicate()` raises `TimeoutExpired` on the first two calls (matching
    the initial wait and the post-`terminate()` grace wait both expiring),
    then succeeds on the third (the reap after `kill()`)."""

    def __init__(self):
        self.returncode = None
        self._calls = 0

    def communicate(self, timeout=None):
        self._calls += 1
        if self._calls <= 2:
            raise subprocess.TimeoutExpired(cmd="git", timeout=timeout or 0)
        self.returncode = -9  # killed
        return "", ""

    def terminate(self):
        pass  # simulates a child that ignores SIGTERM

    def kill(self):
        pass  # returncode lands on the subsequent communicate() reap


def _install_kill_mid_write(monkeypatch, repo: Path, target_rel: str, target_bytes: bytes):
    """Patch `subprocess.Popen` inside the module so that ONLY the
    `sparse-checkout add -- big` invocation is intercepted: it simulates a
    process fully SIGKILL-escalated mid-materialization by (1) writing a
    TRUNCATED (0-byte) copy of one real tracked file straight to disk —
    exactly what a killed `git` leaves, since the file is created via
    open+truncate before its content write lands — (2) leaving a stale
    `index.lock` in the real git-dir, matching what git itself leaves when
    the rename-into-place never happens, and (3) returning a `_KilledProc`
    whose `communicate()` raises `TimeoutExpired` twice, driving
    `_run_git_timed`'s ladder through `terminate()` and into `kill()` —
    matching what a fully wedged child (one that ignores SIGTERM) still
    forces today. Every other `Popen`/`subprocess.run` call (repair's `git
    show`, `git ls-tree`, fixture setup) passes through to the real
    implementation untouched.
    """
    gitdir = _real_git_dir(repo)

    def fake_popen(cmd, *args, **kwargs):
        if (isinstance(cmd, (list, tuple))
                and len(cmd) >= 6
                and cmd[0] == "git" and cmd[3] == "sparse-checkout"
                and cmd[4] == "add"):
            abs_path = repo / target_rel
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(b"")  # truncated mid-write, like the real incident
            gitdir.mkdir(parents=True, exist_ok=True)
            (gitdir / "index.lock").write_bytes(b"")  # stale lock left behind
            return _KilledProc()
        return _REAL_POPEN(cmd, *args, **kwargs)

    monkeypatch.setattr(WS.subprocess, "Popen", fake_popen)


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


# ── 4. `full` (disable_profile) is the LARGER version of the same hazard ────
#
# `add` materializes one directory; `disable` materializes every omitted tree
# in one pass (measured ~3.31 of the repo's 3.8 GiB) — so if a 60s timeout can
# SIGKILL an `add`, it fires far more readily on `disable`, and the corruption
# signature (a truncated tracked file + a stale index.lock) is identical.
# Follow-up requested by the commissioning session after review of the initial
# PR, which had scoped the fix to `add` alone.

def _install_kill_mid_write_disable(monkeypatch, repo: Path, target_rel: str):
    """Same shape as `_install_kill_mid_write`, but intercepts
    `sparse-checkout disable` instead of `sparse-checkout add -- <names>`."""
    gitdir = _real_git_dir(repo)

    def fake_popen(cmd, *args, **kwargs):
        if (isinstance(cmd, (list, tuple))
                and len(cmd) >= 5
                and cmd[0] == "git" and cmd[3] == "sparse-checkout"
                and cmd[4] == "disable"):
            abs_path = repo / target_rel
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(b"")  # truncated mid-write, like the real incident
            gitdir.mkdir(parents=True, exist_ok=True)
            (gitdir / "index.lock").write_bytes(b"")  # stale lock left behind
            return _KilledProc()
        return _REAL_POPEN(cmd, *args, **kwargs)

    monkeypatch.setattr(WS.subprocess, "Popen", fake_popen)


def test_failed_full_repairs_a_truncated_tracked_file(repo, monkeypatch, capsys):
    """`python3 scripts/worktree_sparse.py full` (disable_profile) killed
    mid-checkout must not leave `big/data.json` truncated, same guarantee as
    `add`. Fails against origin/main: `disable_profile` there has no `timeout`
    parameter and no repair path at all."""
    _install_kill_mid_write_disable(monkeypatch, repo, "big/data.json")

    rc = WS.disable_profile(root=repo, timeout=0.01)
    blob = "".join(capsys.readouterr())

    assert rc != 0, "a failed `git sparse-checkout disable` must exit non-zero"
    assert "::error" in blob and any(
        ln.startswith("::error") for ln in blob.splitlines()
    ), f"failed `full` produced no line-starting ::error annotation:\n{blob}"

    restored = (repo / "big" / "data.json").read_bytes()
    assert restored == _BIG_CONTENT, (
        "a tracked file left truncated by a killed `sparse-checkout disable` "
        f"was NOT repaired back to its committed content (got {len(restored)} "
        f"bytes, want {len(_BIG_CONTENT)}):\n{blob}"
    )


def test_preexisting_lock_refuses_full_before_any_write(repo, monkeypatch, capsys):
    """A stale lock must stop `full` before it ever calls `sparse-checkout
    disable`, exactly like it stops `add`. Fails against origin/main:
    `disable_profile` there has no preflight lock check, so it always
    attempts the disable regardless of a lock sitting in the git-dir."""
    gitdir = _real_git_dir(repo)
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")

    call_log = []
    real_run = subprocess.run

    def spy_run(cmd, *a, **kw):
        if (isinstance(cmd, (list, tuple)) and len(cmd) >= 5
                and cmd[0] == "git" and cmd[3] == "sparse-checkout" and cmd[4] == "disable"):
            call_log.append(cmd)
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(WS.subprocess, "run", spy_run)

    rc = WS.disable_profile(root=repo)
    blob = "".join(capsys.readouterr())

    assert rc != 0, "a pre-existing lock must refuse `full`, not proceed"
    assert not call_log, (
        "`git sparse-checkout disable` was invoked despite a pre-existing lock — "
        "the refusal must happen BEFORE any write is attempted")
    assert not (repo / "big").exists(), "nothing should have been materialized"
    assert "::error" in blob and str(lock) in blob, (
        f"refusal did not name the lock path in an ::error annotation:\n{blob}")
    assert lock.exists(), "a lock this run did not create must never be auto-deleted"


def test_successful_full_still_works(repo, capsys):
    rc = WS.disable_profile(root=repo)
    blob = "".join(capsys.readouterr())

    assert rc == 0, f"a normal, uninterrupted full checkout must still succeed:\n{blob}"
    assert (repo / "big" / "data.json").read_bytes() == _BIG_CONTENT
    assert WS.missing_dirs(repo) == []
    assert "::error" not in blob


# ── 5. `sparse`/`auto` (apply_profile): preflight refusal only ──────────────
#
# Narrowing the cone is mostly a delete, not a from-scratch write, so it does
# not carry the same truncation risk — but `auto` runs on every session-
# worktree creation across four agent runtimes, and a lock left behind here is
# inherited by the very next git command any of them runs. The cheap up-front
# refusal is applied; the heavier byte-for-byte repair deliberately is not
# (see the docstring on `apply_profile` for the reasoning, and the PR body for
# the decision record).

def test_preexisting_lock_refuses_apply_profile_before_any_write(repo, monkeypatch, capsys):
    """Fails against origin/main: `apply_profile` there has no lock check at
    all, so it always proceeds into `sparse-checkout init`/`set` regardless of
    a lock already sitting in the git-dir."""
    gitdir = _real_git_dir(repo)
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")

    call_log = []
    real_run = subprocess.run

    def spy_run(cmd, *a, **kw):
        if (isinstance(cmd, (list, tuple)) and len(cmd) >= 5
                and cmd[0] == "git" and cmd[3] == "sparse-checkout"
                and cmd[4] in ("init", "set")):
            call_log.append(cmd)
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(WS.subprocess, "run", spy_run)

    rc = WS.apply_profile(repo, exclude_dirs=["big"])
    blob = "".join(capsys.readouterr())

    assert rc != 0, "a pre-existing lock must refuse apply_profile, not proceed"
    assert not call_log, (
        "`sparse-checkout init`/`set` was invoked despite a pre-existing lock — "
        "the refusal must happen BEFORE any write is attempted")
    assert "::error" in blob and str(lock) in blob, (
        f"refusal did not name the lock path in an ::error annotation:\n{blob}")
    assert lock.exists(), "a lock this run did not create must never be auto-deleted"


# ── 6. adversarial review of #5907: repair must not clobber pre-existing ────
#      local work, and an unreadable size read must not be reported as clean.
#
# `verify_and_repair` originally treated ANY size mismatch against HEAD as
# corruption and rewrote the file from HEAD — which is equally the signature
# of an ordinary uncommitted edit. Reproduced two ways in the review: `add
# data site` where `site/` is already in the cone and holds an uncommitted
# edit, and a single-directory `add site` where a stale
# `info/sparse-checkout.lock` (the SAME kill that orphans `index.lock`) makes
# the run exit 128 and fall into the repair path anyway. `_committed_sizes`
# also returned `{}` (a real all-clear) on BOTH a failed git call and an
# unparseable size field (`BAD`, what `git ls-tree -l` prints for a size under
# `GIT_NO_LAZY_FETCH=1` against an unreachable promisor on this repo's
# blobless clone) — so a genuinely truncated file could be reported as
# "nothing found" instead of "could not check".

def test_verify_and_repair_protects_a_dirty_file_but_still_repairs_a_truncated_sibling(repo):
    """A size mismatch is ALSO what an ordinary local edit looks like. The
    repair must not clobber a path git already reports dirty, but must still
    repair a genuinely truncated sibling in the SAME directory and pass —
    pinning that the protection narrows the repair rather than disabling it."""
    ok, reason = WS._run_sparse_checkout_add(repo, ["big"])
    assert ok, f"fixture setup: materializing big/ failed: {reason}"

    edited = b"a locally edited, uncommitted, different-length blob\n"
    (repo / "big" / "other.txt").write_bytes(edited)  # uncommitted edit, BEFORE the kill

    # `protected` is captured at this point in the real flow — BEFORE the
    # sparse-checkout command that might corrupt something runs. Only the
    # pre-existing edit is dirty here; data.json is still intact.
    protected = WS.dirty_paths(repo, ["big"])
    assert protected == {"big/other.txt"}, (
        "fixture precondition: only the pre-existing edit should be dirty "
        f"before the simulated kill: {protected}")

    (repo / "big" / "data.json").write_bytes(b"")  # simulates the kill-truncation, AFTER capture

    repaired, skipped, unreadable = WS.verify_and_repair(repo, ["big"], protected)

    assert unreadable == []
    assert "big/data.json" in repaired, (
        "the genuinely truncated sibling must still be repaired in the same pass")
    assert "big/other.txt" in skipped, (
        "the dirty file must be reported skipped, not silently ignored")
    assert "big/other.txt" not in repaired, (
        "a protected path must never land in the repaired list")
    assert (repo / "big" / "other.txt").read_bytes() == edited, (
        "an uncommitted local edit was reverted by the repair — the exact "
        "clobber this fix exists to prevent")
    assert (repo / "big" / "data.json").read_bytes() == _BIG_CONTENT, (
        "the truncated sibling was not actually restored")


def test_committed_sizes_none_vs_empty_dict_are_distinguishable(repo, monkeypatch):
    """`{}` must mean a real all-clear (no tracked files found); `None` must
    mean the read could not be trusted. Collapsing the two — the original bug
    — lets a genuinely truncated file get reported as "nothing to repair"."""
    # A successful read that finds nothing is a real all-clear: {}.
    assert WS._committed_sizes(repo, "does-not-exist-anywhere") == {}

    # The underlying git call failing outright must propagate as None.
    monkeypatch.setattr(WS, "_git", lambda *a, **k: None)
    assert WS._committed_sizes(repo, "big") is None


def test_committed_sizes_returns_none_on_unparseable_size_field(repo, monkeypatch):
    """`git ls-tree -l` prints `BAD` in the size column under
    `GIT_NO_LAZY_FETCH=1` against an unreachable promisor (this repo's own
    blobless-clone shape). That must return None, not silently skip the row —
    a corrupt/unavailable size read is not the same as a legitimate
    submodule's `-`."""
    fake_ls_tree = "100644 blob abc123def0000000000000000000000000000000       BAD\tbig/data.json"
    monkeypatch.setattr(WS, "_git", lambda *a, **k: fake_ls_tree)
    assert WS._committed_sizes(repo, "big") is None


def test_committed_sizes_still_skips_a_legitimate_submodule_marker(repo, monkeypatch):
    """A `-` size field (submodule; no blob size) stays a legitimate skip, not
    an unreadable result — only an unparseable non-`-` field is."""
    fake_ls_tree = "160000 commit abc123def0000000000000000000000000000000       -\tbig/submod"
    monkeypatch.setattr(WS, "_git", lambda *a, **k: fake_ls_tree)
    assert WS._committed_sizes(repo, "big") == {}


def test_failed_add_reports_unverified_when_committed_sizes_unreadable(repo, monkeypatch, capsys):
    """When the committed-size read itself fails, the caller must say so
    loudly (`worktree-sparse-unverified`) and must NOT print the old
    unconditional "no truncated tracked file found to repair" clean bill of
    health — that message on an unreadable directory is exactly the silent
    green the module's own docstring forbids."""
    _install_kill_mid_write(monkeypatch, repo, "big/data.json", _BIG_CONTENT)
    monkeypatch.setattr(WS, "_committed_sizes", lambda *a, **k: None)

    rc = WS.add_dirs(["big"], root=repo, timeout=0.01)
    blob = "".join(capsys.readouterr())

    assert rc != 0
    assert "worktree-sparse-unverified" in blob, (
        f"no unreadable-sizes annotation emitted:\n{blob}")
    assert "no truncated tracked file found to repair" not in blob, (
        f"printed a clean bill of health while sizes were unreadable:\n{blob}")


def test_dirty_paths_parses_a_rename_record(repo):
    """`git status --porcelain -z` writes a rename as TWO NUL-separated
    fields (destination path in the `XY path` record, then the origin path as
    an extra field) — the extra field must be consumed as the origin, not
    mistaken for an unrelated next record."""
    _git(repo, "mv", "scripts/keep.txt", "scripts/kept.txt")

    result = WS.dirty_paths(repo, ["scripts"])

    assert result is not None
    assert "scripts/kept.txt" in result, f"destination path missing: {result}"
    assert "scripts/keep.txt" in result, (
        f"origin path was not consumed as the rename's extra field: {result}")


def test_dirty_paths_returns_none_when_git_status_fails(repo, monkeypatch):
    def fake_run(cmd, *a, **kw):
        class _R:
            returncode = 1
            stdout = ""
        return _R()
    monkeypatch.setattr(WS.subprocess, "run", fake_run)
    assert WS.dirty_paths(repo, ["big"]) is None


def test_preexisting_sparse_checkout_lock_alone_refuses_before_any_write(repo, monkeypatch, capsys):
    """`git sparse-checkout` acquires `info/sparse-checkout.lock` BEFORE
    `index.lock`, so the same kill can orphan the sparse-checkout lock with no
    index.lock ever created. The preflight must catch this lock on its own,
    not only the `index.lock` case already covered above."""
    gitdir = _real_git_dir(repo)
    lock = gitdir / "info" / "sparse-checkout.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"")
    index_lock = gitdir / "index.lock"
    assert not index_lock.exists(), "fixture precondition: index.lock absent"

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

    assert rc != 0, "a pre-existing sparse-checkout.lock must refuse, not proceed"
    assert not call_log, (
        "`git sparse-checkout add` was invoked despite a pre-existing "
        "sparse-checkout.lock — the refusal must happen BEFORE any write")
    assert not (repo / "big").exists(), "nothing should have been materialized"
    assert "::error" in blob and str(lock) in blob, (
        f"refusal did not name the sparse-checkout.lock path:\n{blob}")
    assert lock.exists(), "a lock this run did not create must never be auto-deleted"


# ── 7. `_run_git_timed` escalates SIGTERM before SIGKILL on expiry ──────────
#
# `subprocess.run(..., timeout=...)` sends SIGKILL straight away on expiry.
# Git installs cleanup handlers (removing `index.lock`, finishing or
# discarding an in-flight write) that run on SIGTERM and CANNOT run on
# SIGKILL — so the fix sends SIGTERM first via `Popen.terminate()` and only
# escalates to `Popen.kill()` if the child ignores SIGTERM for the whole
# `TERM_GRACE_S` grace window. These tests point `_run_git_timed` at a
# controllable child (never a real git call) so the ladder can be exercised
# deterministically and fast: an ordinary `sleep` that honors SIGTERM must
# produce the clean-SIGTERM reason, while a `trap '' TERM; sleep` child that
# IGNORES SIGTERM must be force-killed and must say so.

# A single PROCESS (no shell fork) that installs SIG_IGN for SIGTERM, then
# sleeps. Deliberately not `sh -c 'trap "" TERM; sleep 5'`: that spawns a
# shell that forks `sleep` as a SEPARATE grandchild holding the same stdout/
# stderr pipe fds — SIGKILLing the shell doesn't close those fds, so the
# final reaping `communicate()` blocks for the full 5s waiting on the
# orphaned grandchild's pipes instead of returning as soon as the killed
# process dies. A single Python process has no such grandchild, so kill()
# reaps promptly.
_IGNORE_SIGTERM_CHILD = [
    sys.executable, "-c",
    "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(5)",
]


def _install_fake_child(monkeypatch, argv: list[str], captured: list | None = None):
    """Replace whatever argv `_run_git_timed` built with `argv`, so the
    timeout/escalation ladder races a real, controllable child process
    instead of real git. `captured`, if given, collects every `Popen`
    instance created so a caller can inspect `.returncode` afterward."""
    def fake_popen(cmd, *a, **kw):
        proc = _REAL_POPEN(list(argv), *a, **kw)
        if captured is not None:
            captured.append(proc)
        return proc

    monkeypatch.setattr(WS.subprocess, "Popen", fake_popen)


def test_run_git_timed_terminates_cleanly_when_child_honors_sigterm(repo, monkeypatch):
    """An ordinary `sleep`, which does not trap signals, dies immediately on
    SIGTERM — the ladder must stop there and never reach `kill()`. Fails
    against the pre-fix `subprocess.run`-based implementation, which has no
    escalation ladder at all and just reports a bare 'timed out ... killed'."""
    monkeypatch.setattr(WS, "TERM_GRACE_S", 3.0)
    _install_fake_child(monkeypatch, ["sleep", "5"])

    ok, reason = WS._run_git_timed(repo, ("status",), timeout=0.2)

    assert ok is False
    assert "terminated cleanly with SIGTERM" in reason, reason
    assert "SIGKILL" not in reason, (
        f"a SIGTERM-honoring child must never be escalated to SIGKILL: {reason}")


def test_run_git_timed_escalates_to_sigkill_when_child_ignores_sigterm(repo, monkeypatch):
    """A child that explicitly traps and ignores SIGTERM must still die —
    the ladder escalates to `kill()` (SIGKILL) after `TERM_GRACE_S`, and the
    reason must warn that a SIGKILLed checkout can leave a truncated file."""
    monkeypatch.setattr(WS, "TERM_GRACE_S", 0.3)
    _install_fake_child(monkeypatch, _IGNORE_SIGTERM_CHILD)

    ok, reason = WS._run_git_timed(repo, ("status",), timeout=0.2)

    assert ok is False
    assert "ignored SIGTERM for" in reason, reason
    assert "killed with SIGKILL" in reason, reason
    assert "truncated" in reason, (
        f"escalation reason must warn a SIGKILLed checkout can leave a "
        f"truncated file: {reason}")


def test_sigterm_and_sigkill_reasons_are_distinguishable(repo, monkeypatch):
    """The whole point of escalating is that a caller can tell, from the
    returned reason alone, whether a truncating SIGKILL was even possible."""
    monkeypatch.setattr(WS, "TERM_GRACE_S", 3.0)
    _install_fake_child(monkeypatch, ["sleep", "5"])
    ok_term, reason_term = WS._run_git_timed(repo, ("status",), timeout=0.2)

    monkeypatch.setattr(WS, "TERM_GRACE_S", 0.3)
    _install_fake_child(monkeypatch, _IGNORE_SIGTERM_CHILD)
    ok_kill, reason_kill = WS._run_git_timed(repo, ("status",), timeout=0.2)

    assert ok_term is False and ok_kill is False
    assert reason_term != reason_kill
    assert "SIGKILL" not in reason_term and "SIGKILL" in reason_kill, (
        f"reasons must be distinguishable:\n  clean={reason_term!r}\n"
        f"  escalated={reason_kill!r}")


# ── 8. `_run_git_timed` non-timeout behavior is unchanged by the rewrite ────

def test_run_git_timed_success_still_returns_true_empty_reason(repo):
    ok, reason = WS._run_git_timed(repo, ("status", "--short"), timeout=5)
    assert (ok, reason) == (True, ""), (
        "a successful command must still return (True, '') exactly")


def test_run_git_timed_nonzero_exit_still_names_code_and_stderr(repo):
    ok, reason = WS._run_git_timed(repo, ("not-a-real-git-subcommand",), timeout=5)
    assert ok is False
    assert reason.startswith("exited "), (
        f"a nonzero, non-timeout exit must still be reported as 'exited <code>: ...': {reason}")
    assert reason != "exited 1", (
        f"the first 300 chars of stderr must still be carried, not dropped: {reason}")


# ── 9. no zombie process on any of the three paths ──────────────────────────

def test_run_git_timed_leaves_no_zombie_on_success_or_either_kill_path(repo, monkeypatch):
    captured: list = []

    # success path — real git call, no fault injection.
    _install_fake_child(monkeypatch, ["git", "-C", str(repo), "status", "--short"], captured)
    ok, _ = WS._run_git_timed(repo, ("status", "--short"), timeout=5)
    assert ok
    assert captured[-1].returncode is not None, (
        "a successful run left its Popen unreaped (returncode is None)")

    # clean-SIGTERM path.
    monkeypatch.setattr(WS, "TERM_GRACE_S", 3.0)
    _install_fake_child(monkeypatch, ["sleep", "5"], captured)
    ok, reason = WS._run_git_timed(repo, ("status",), timeout=0.2)
    assert not ok and "SIGKILL" not in reason
    assert captured[-1].returncode is not None, (
        "a SIGTERM-terminated child was left unreaped (returncode is None)")

    # SIGKILL-escalation path.
    monkeypatch.setattr(WS, "TERM_GRACE_S", 0.3)
    _install_fake_child(monkeypatch, _IGNORE_SIGTERM_CHILD, captured)
    ok, reason = WS._run_git_timed(repo, ("status",), timeout=0.2)
    assert not ok and "SIGKILL" in reason
    assert captured[-1].returncode is not None, (
        "a SIGKILLed child was left unreaped (returncode is None)")

    assert all(p.returncode is not None for p in captured), (
        "at least one Popen across the three paths was left as a zombie")


# ── 10. the budget is sized from the measured tail, not the median ─────────

def test_add_timeout_s_clears_the_measured_worst_case_not_the_median():
    """Measured over 12 fresh worktrees, `git sparse-checkout disable` had a
    24.89s median but an 83.49s worst observed sample (~8% exceedance
    against the old 60s cap). A cap sized from the median would still get
    SIGKILLed on exactly the tail case that matters; 300s clears the worst
    observed sample with 3.6x headroom."""
    assert WS.ADD_TIMEOUT_S >= 300, (
        f"ADD_TIMEOUT_S={WS.ADD_TIMEOUT_S} does not clear the measured worst "
        "observed sample (83.49s) with adequate headroom — a timeout budget "
        "must be sized from the tail, not the median")
