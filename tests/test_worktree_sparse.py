"""Stale-lock self-heal + loud failure for scripts/worktree_sparse.py — MO-B PLAT-6.

WHY THIS EXISTS
---------------
Census 2026-09-06 (agentos/discoveries/DSC-SPARSE-MINT-FAILS-SILENTLY-ON-
STALE-LOCKS.md): 97 of 267 `.claude/worktrees/` session trees were FULL
(~6.5 GiB) instead of sparse (~0.4 GiB). `refuse_if_locked` refuses whenever
`index.lock`/`info/sparse-checkout.lock` exists, with no notion of staleness
— but under fleet lock contention those locks are frequently left behind by a
killed sibling process (measured ages 600-3,500 minutes, no live holder), and
the refusal was swallowed upstream: the harness reported the worktree as
created and the session proceeded on a full tree.

This suite pins three additive behaviors, all fail-closed by default:

  (1) A lock older than `STALE_LOCK_MIN_AGE_S` (600s) with NO live process
      holding the worktree/git-dir (per an injectable `gather_live_processes`
      probe) is removed automatically, with a line-starting `::warning`
      naming the lock, its age, and the tree — see `lock_is_stale` (a pure
      predicate over an injected process list, so no real process spawning is
      needed here) and `_clear_stale_locks`.
  (2) A lock that is either young OR still held by a live process (or whose
      liveness could not be confirmed at all — `gather_live_processes`
      returning `None`) still refuses with a line-starting `::error` and a
      non-zero exit, exactly as before — this suite proves the new staleness
      path never weakens that refusal.
  (3) A post-condition check after `apply_profile` succeeds: `git
      sparse-checkout list` must match the requested include set, and every
      excluded directory must be an empty husk on disk — never a partially
      materialized tree. A mismatch fails loud (non-zero, `::error`) instead
      of reporting the success message.
  (4) `status --json` returns a machine-readable
      `{sparse, missing_dirs, stale_locks_removed, full_bytes_estimate}` shape
      for fleet census scripts.

Run: python3 -m pytest tests/test_worktree_sparse.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from scripts import worktree_sparse as WS

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "worktree_create_sparse.py"

_BIG_CONTENT = b'{"ticker": "ABC", "series": [1, 2, 3, 4, 5]}\n' * 40


def _load_hook():
    spec = importlib.util.spec_from_file_location("worktree_create_sparse_pt6", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(("git", "-C", str(repo)) + args,
                           capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _real_git_dir(repo: Path) -> Path:
    return Path(_git(repo, "rev-parse", "--path-format=absolute", "--git-dir"))


def _backdate(path: Path, age_s: float) -> None:
    """Set ``path``'s mtime (and atime) to ``age_s`` seconds in the past."""
    ts = time.time() - age_s
    os.utime(path, (ts, ts))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed repo, sparsed to include only `scripts/` — `big/` starts
    tracked, excluded, and (because cone sparse-checkout physically removes
    what it excludes) empty on disk, the same shape as a session worktree
    under policy R8."""
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


# ── (1) a confirmed-stale lock is removed, loudly, and the op proceeds ──────

def test_stale_lock_is_removed_with_warning_and_operation_proceeds(repo, monkeypatch, capsys):
    gitdir = _real_git_dir(repo)
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")
    _backdate(lock, WS.STALE_LOCK_MIN_AGE_S + 60)
    monkeypatch.setattr(WS, "gather_live_processes", lambda *a, **k: [])

    rc = WS.apply_profile(repo, exclude_dirs=["big"])
    blob = "".join(capsys.readouterr())

    assert rc == 0, f"a confirmed-stale lock must not block the operation:\n{blob}"
    assert not lock.exists(), "a confirmed-stale lock must be removed"
    warning_lines = [ln for ln in blob.splitlines() if "::warning" in ln]
    assert warning_lines, f"no ::warning emitted for the removed stale lock:\n{blob}"
    assert any(ln.startswith("::warning") for ln in warning_lines), (
        f"annotation did not open the line, so GitHub will drop it: {warning_lines}")
    assert str(lock) in blob, f"warning did not name the lock path:\n{blob}"


def test_stale_lock_removal_also_applies_to_the_sparse_checkout_lock(repo, monkeypatch, capsys):
    gitdir = _real_git_dir(repo)
    lock = gitdir / "info" / "sparse-checkout.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"")
    _backdate(lock, WS.STALE_LOCK_MIN_AGE_S + 120)
    monkeypatch.setattr(WS, "gather_live_processes", lambda *a, **k: [])

    rc = WS.apply_profile(repo, exclude_dirs=["big"])
    blob = "".join(capsys.readouterr())

    assert rc == 0, f"a confirmed-stale sparse-checkout.lock must not block the op:\n{blob}"
    assert not lock.exists()
    assert "::warning" in blob and str(lock) in blob


# ── (2) a young lock, a live-held lock, and an unconfirmed probe all refuse ─

def test_old_lock_with_live_process_still_refuses(repo, monkeypatch, capsys):
    gitdir = _real_git_dir(repo)
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")
    _backdate(lock, WS.STALE_LOCK_MIN_AGE_S + 60)
    monkeypatch.setattr(
        WS, "gather_live_processes",
        lambda *a, **k: [{"pid": 999, "cwd": str(repo), "open_files": []}],
    )

    rc = WS.apply_profile(repo, exclude_dirs=["big"])
    blob = "".join(capsys.readouterr())

    assert rc != 0, "a lock with a live process must still refuse even when old"
    assert lock.exists(), "a live-held lock must never be auto-deleted"
    error_lines = [ln for ln in blob.splitlines() if "::error" in ln]
    assert error_lines and any(ln.startswith("::error") for ln in error_lines), (
        f"no line-starting ::error for a still-locked refusal:\n{blob}")


def test_old_lock_with_unconfirmed_probe_fails_closed(repo, monkeypatch, capsys):
    """`gather_live_processes` returning None (probe untrustworthy — lsof
    missing, /proc unreadable, unsupported platform) must NEVER be read as
    'nothing is alive'. The lock stays and the operation still refuses."""
    gitdir = _real_git_dir(repo)
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")
    _backdate(lock, WS.STALE_LOCK_MIN_AGE_S + 60)
    monkeypatch.setattr(WS, "gather_live_processes", lambda *a, **k: None)

    rc = WS.apply_profile(repo, exclude_dirs=["big"])
    blob = "".join(capsys.readouterr())

    assert rc != 0, f"an unconfirmed liveness probe must fail closed:\n{blob}"
    assert lock.exists()
    assert "::error" in blob


def test_young_lock_refuses_even_with_no_live_process(repo, monkeypatch, capsys):
    """A lock created moments ago (age < STALE_LOCK_MIN_AGE_S) must refuse
    regardless of process state — age is a hard floor, not just a hint."""
    gitdir = _real_git_dir(repo)
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")  # fresh; no backdating

    probe_called = []

    def spy_probe(*a, **k):
        probe_called.append(True)
        return []

    monkeypatch.setattr(WS, "gather_live_processes", spy_probe)

    rc = WS.apply_profile(repo, exclude_dirs=["big"])
    blob = "".join(capsys.readouterr())

    assert rc != 0
    assert lock.exists(), "a lock younger than the threshold must never be auto-deleted"
    assert not probe_called, (
        "the live-process probe should not even run for a lock too young to "
        "qualify — it is a real subprocess call and the age check is free")
    assert "::error" in blob


# ── `gather_live_processes` — the real per-platform probe (round-2 verify) ──
# (round 1/2 review: "attack the liveness probe — a process whose cwd is a
# SUBDIRECTORY of the worktree; a process with the gitdir open but cwd
# elsewhere; lsof timing out". The subdirectory-cwd case already worked (lsof
# `+D` recurses), but two real gaps existed: (a) on Darwin, if only ONE of the
# two required lsof calls failed/timed out, the probe still returned a
# confirmed (partial) result instead of None, silently dropping exactly the
# half that might have found the holder; (b) on Linux, the git-dir
# "open file, cwd elsewhere" case was never checked at all — only cwd was.)

def test_gather_live_processes_darwin_partial_probe_failure_is_unconfirmed(
    monkeypatch, tmp_path,
):
    """If the cwd-scoped lsof call succeeds but the git-dir-scoped one
    fails/times out (or vice versa), the whole probe must come back
    unconfirmed (None) — a probe that only half-answered is not proof nothing
    holds the lock."""
    monkeypatch.setattr(WS.platform, "system", lambda: "Darwin")

    def cwd_ok_gitdir_fails(args):
        if "-d" in args:  # the cwd-scoped probe
            return "p123\nfcwd\n/somewhere\n"
        return None  # the git-dir open-file probe "timed out"

    monkeypatch.setattr(WS, "_run_lsof", cwd_ok_gitdir_fails)
    assert WS.gather_live_processes(tmp_path / "wt", tmp_path / "gitdir") is None

    def gitdir_ok_cwd_fails(args):
        if "-d" in args:
            return None  # the cwd-scoped probe "timed out"
        return "p456\nfcwd\n/other\n"

    monkeypatch.setattr(WS, "_run_lsof", gitdir_ok_cwd_fails)
    assert WS.gather_live_processes(tmp_path / "wt", tmp_path / "gitdir") is None


def test_gather_live_processes_linux_detects_gitdir_open_file_when_cwd_elsewhere(
    monkeypatch, tmp_path,
):
    """A process with the lock file open via an fd, but whose cwd is
    elsewhere, must still be detected on Linux — the same coverage the
    macOS `lsof -F pn +D <git_dir>` call already provides."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    gitdir = tmp_path / "gitdir"
    gitdir.mkdir()
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    lockfile = gitdir / "index.lock"
    lockfile.write_bytes(b"")

    proc_root = tmp_path / "proc"
    pid_dir = proc_root / "4242"
    pid_dir.mkdir(parents=True)
    os.symlink(other_cwd, pid_dir / "cwd")
    fd_dir = pid_dir / "fd"
    fd_dir.mkdir()
    os.symlink(lockfile, fd_dir / "9")

    monkeypatch.setattr(WS.platform, "system", lambda: "Linux")

    procs = WS.gather_live_processes(worktree, gitdir, proc_root=proc_root)

    assert procs is not None
    assert any(p["pid"] == 4242 for p in procs), f"missed gitdir-open-file holder: {procs}"


def test_gather_live_processes_linux_still_detects_cwd_under_worktree(monkeypatch, tmp_path):
    """Regression guard: adding the fd/git-dir check must not break the
    existing cwd-under-worktree detection."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    sub = worktree / "sub"
    sub.mkdir()

    proc_root = tmp_path / "proc"
    pid_dir = proc_root / "777"
    pid_dir.mkdir(parents=True)
    os.symlink(sub, pid_dir / "cwd")

    monkeypatch.setattr(WS.platform, "system", lambda: "Linux")

    procs = WS.gather_live_processes(worktree, None, proc_root=proc_root)

    assert procs is not None
    assert any(p["pid"] == 777 for p in procs)


# ── `lock_is_stale` — pure predicate, no real processes ─────────────────────

def test_lock_is_stale_pure_predicate(tmp_path):
    lock = tmp_path / "index.lock"
    lock.write_bytes(b"")
    now = time.time()
    _backdate(lock, WS.STALE_LOCK_MIN_AGE_S + 1)

    assert WS.lock_is_stale(lock, now, []) is True
    assert WS.lock_is_stale(lock, now, [{"pid": 1, "cwd": None, "open_files": []}]) is False
    assert WS.lock_is_stale(lock, now, None) is False, "an unconfirmed probe is never stale"

    _backdate(lock, 5)  # too young, even with an empty (confirmed-clear) process list
    assert WS.lock_is_stale(lock, now, []) is False


def test_lock_is_stale_returns_false_on_unreadable_lock(tmp_path):
    missing = tmp_path / "does-not-exist.lock"
    assert WS.lock_is_stale(missing, time.time(), []) is False


# ── (3) post-condition check ─────────────────────────────────────────────────

def test_verify_sparse_postcondition_passes_when_matched(repo):
    assert WS.verify_sparse_postcondition(repo, ["scripts"], ["big"]) is None


def test_verify_sparse_postcondition_detects_non_husk_excluded_dir(repo):
    (repo / "big").mkdir(exist_ok=True)
    (repo / "big" / "stray.txt").write_text("oops\n", encoding="utf-8")

    problem = WS.verify_sparse_postcondition(repo, ["scripts"], ["big"])

    assert problem is not None
    assert "big" in problem


def test_verify_sparse_postcondition_detects_include_set_mismatch(repo):
    problem = WS.verify_sparse_postcondition(repo, ["scripts", "big"], [])
    assert problem is not None
    assert "mismatch" in problem.lower()


def test_postcondition_mismatch_fails_apply_profile_loudly(repo, monkeypatch, capsys):
    """Even though `git sparse-checkout set` itself succeeds, a post-apply
    verification mismatch must fail the whole call — never report the
    success message over a state that does not match what was requested."""
    monkeypatch.setattr(WS, "_cone_included", lambda root: ["scripts", "unexpected"])

    rc = WS.apply_profile(repo, exclude_dirs=["big"])
    blob = "".join(capsys.readouterr())

    assert rc != 0, f"a postcondition mismatch must fail loud:\n{blob}"
    assert "::error" in blob and "worktree-sparse-postcondition-failed" in blob
    assert any(ln.startswith("::error") for ln in blob.splitlines())
    assert "profile applied" not in blob, (
        "the success message must never print alongside a failed postcondition")


def test_add_dirs_postcondition_catches_a_falsely_successful_materialize(repo, monkeypatch, capsys):
    """`git sparse-checkout add` can exit 0 (per `_run_git_timed`) without
    actually materializing the requested directory on disk (e.g. a race).
    `add_dirs` must not report success in that case."""
    real_popen = subprocess.Popen

    class _FakeSuccessProc:
        def __init__(self):
            self.returncode = 0

        def communicate(self, timeout=None):
            return "", ""  # reports success; deliberately writes nothing to disk

    def fake_popen(cmd, *a, **k):
        if (isinstance(cmd, (list, tuple)) and len(cmd) >= 5
                and cmd[0] == "git" and cmd[3] == "sparse-checkout" and cmd[4] == "add"):
            return _FakeSuccessProc()
        return real_popen(cmd, *a, **k)

    monkeypatch.setattr(WS.subprocess, "Popen", fake_popen)

    rc = WS.add_dirs(["big"], root=repo)
    blob = "".join(capsys.readouterr())

    assert rc != 0, f"a falsely-successful add must still fail on the postcondition:\n{blob}"
    assert "::error" in blob and "worktree-sparse-add-postcondition-failed" in blob
    assert any(ln.startswith("::error") for ln in blob.splitlines())


# ── (4) status --json ────────────────────────────────────────────────────────

def test_status_json_shape(repo):
    out = WS.status_json(repo)

    assert set(out.keys()) == {
        "sparse", "missing_dirs", "stale_locks_removed", "full_bytes_estimate",
    }
    assert out["sparse"] is True
    assert out["missing_dirs"] == ["big"]
    assert out["stale_locks_removed"] == []
    assert isinstance(out["full_bytes_estimate"], int)
    assert out["full_bytes_estimate"] >= len(_BIG_CONTENT), (
        "full_bytes_estimate should at least cover big/data.json's committed size")


def test_status_json_reports_and_clears_a_stale_lock(repo, monkeypatch):
    gitdir = _real_git_dir(repo)
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")
    _backdate(lock, WS.STALE_LOCK_MIN_AGE_S + 30)
    monkeypatch.setattr(WS, "gather_live_processes", lambda *a, **k: [])

    out = WS.status_json(repo)

    assert out["stale_locks_removed"] == [str(lock)]
    assert not lock.exists()


def test_status_json_full_checkout_shape(repo):
    assert WS.disable_profile(root=repo) == 0
    out = WS.status_json(repo)
    assert out["sparse"] is False
    assert out["missing_dirs"] == []
    assert out["full_bytes_estimate"] == 0


def test_main_status_json_flag_prints_valid_json(monkeypatch, capsys):
    fake = {
        "sparse": False, "missing_dirs": [], "stale_locks_removed": [],
        "full_bytes_estimate": 0,
    }
    monkeypatch.setattr(WS, "status_json", lambda: fake)

    rc = WS.main(["status", "--json"])
    out = capsys.readouterr().out.strip()

    assert rc == 0
    assert json.loads(out) == fake


# ── the WorktreeCreate hook duplicates its own stale-lock check ─────────────
# (deliberately: it must not depend on scripts/ import surface being intact —
# see load_profile's docstring in the hook itself). This section pins the
# duplicate constant and behavior in step with the script above.

def test_hook_stale_lock_constant_matches_the_script():
    hook = _load_hook()
    assert hook.STALE_LOCK_MIN_AGE_S == WS.STALE_LOCK_MIN_AGE_S


@pytest.fixture
def hook_worktree(tmp_path: Path):
    """A registered linked worktree of a fresh synthetic repo — the shape
    ``dest`` has by the time ``apply_sparse`` runs in the real hook (created
    via ``git worktree add --no-checkout`` before sparse-checkout is ever
    applied)."""
    donor = tmp_path / "donor"
    donor.mkdir()
    _git(donor, "init", "-q")
    _git(donor, "config", "user.email", "t@example.com")
    _git(donor, "config", "user.name", "t")
    (donor / "scripts").mkdir()
    (donor / "scripts" / "keep.txt").write_text("keep\n", encoding="utf-8")
    big = donor / "big"
    big.mkdir()
    (big / "data.json").write_bytes(_BIG_CONTENT)
    _git(donor, "add", "-A")
    _git(donor, "commit", "-qm", "base")

    dest = tmp_path / "dest"
    _git(donor, "worktree", "add", "--no-checkout", "-b", "wt", str(dest))
    return dest


def test_hook_removes_a_confirmed_stale_lock_with_warning(hook_worktree, monkeypatch, capsys):
    hook = _load_hook()
    gitdir = Path(_git(hook_worktree, "rev-parse", "--path-format=absolute", "--git-dir"))
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")
    _backdate(lock, hook.STALE_LOCK_MIN_AGE_S + 60)
    monkeypatch.setattr(hook, "_live_pids_holding", lambda *a, **k: set())

    hook.apply_sparse(hook_worktree, hook_worktree, "HEAD", {"big"})
    blob = "".join(capsys.readouterr())

    assert not lock.exists(), "a confirmed-stale lock must be removed"
    warning_lines = [ln for ln in blob.splitlines() if "::warning" in ln]
    assert warning_lines and any(ln.startswith("::warning") for ln in warning_lines), (
        f"no line-starting ::warning for the removed stale lock:\n{blob}")
    assert str(lock) in blob


def test_hook_refuses_on_a_live_held_lock_even_when_old(hook_worktree, monkeypatch, capsys):
    hook = _load_hook()
    gitdir = Path(_git(hook_worktree, "rev-parse", "--path-format=absolute", "--git-dir"))
    lock = gitdir / "index.lock"
    lock.write_bytes(b"")
    _backdate(lock, hook.STALE_LOCK_MIN_AGE_S + 60)
    monkeypatch.setattr(hook, "_live_pids_holding", lambda *a, **k: {12345})

    with pytest.raises(RuntimeError, match="refusing to run"):
        hook.apply_sparse(hook_worktree, hook_worktree, "HEAD", {"big"})
    assert lock.exists(), "a live-held lock must never be auto-deleted"

    # Frozen spec item 2: "a live/young/unconfirmed lock refuses with a bare
    # `::error` line starting the line". round-1 verify (9df97a50) fixed the
    # liveness probe's fail-open gap but left this refusal going out only
    # through log()/fail(), which prints "WorktreeCreate: refusing to run
    # ..." — no ::error token at all, and any token behind that prefix would
    # not start the line either way (house law: GitHub annotations must
    # START the line). This RED-first-failed before the fix in apply_sparse.
    blob = "".join(capsys.readouterr())
    error_lines = [ln for ln in blob.splitlines() if "::error" in ln]
    assert error_lines, f"no ::error annotation emitted for a refused lock:\n{blob}"
    assert any(ln.startswith("::error") for ln in error_lines), (
        f"::error annotation does not start its line:\n{blob}")


def test_hook_live_pids_holding_fails_closed_when_cwd_probe_is_untrustworthy(monkeypatch):
    """Frozen spec item 1: an unconfirmed probe is treated as LIVE (fail
    closed). round-1 verify (9df97a50) fixed this in
    scripts.worktree_sparse.gather_live_processes but left the hook's
    duplicate `_live_pids_holding` returning a confirmed (partial) result
    whenever the OTHER lsof call succeeded — dropping exactly the half that
    might have found the holder. This directly exercises the hook's own
    `_run_lsof` failure handling (the reviewer's exact gap: the existing
    suite only ever monkeypatched `_live_pids_holding` wholesale)."""
    hook = _load_hook()

    def fake_lsof(args):
        # cwd-scoped call (`-a -d cwd ...`) times out / is untrustworthy;
        # git-dir-scoped call succeeds with an empty (trustworthy) answer.
        return None if "cwd" in args else ""

    monkeypatch.setattr(hook, "_run_lsof", fake_lsof)
    monkeypatch.setattr(hook.platform, "system", lambda: "Darwin")

    result = hook._live_pids_holding(Path("/tmp/some-worktree"), Path("/tmp/some-worktree/.git"))

    assert result is None, (
        "a partially-failed lsof probe must return None (unconfirmed), not a "
        "confirmed-empty/partial pid set")


def test_hook_live_pids_holding_fails_closed_when_gitdir_probe_is_untrustworthy(monkeypatch):
    """Same gap, the other order: cwd probe succeeds, git-dir probe fails."""
    hook = _load_hook()

    def fake_lsof(args):
        return None if "cwd" not in args else ""

    monkeypatch.setattr(hook, "_run_lsof", fake_lsof)
    monkeypatch.setattr(hook.platform, "system", lambda: "Darwin")

    result = hook._live_pids_holding(Path("/tmp/some-worktree"), Path("/tmp/some-worktree/.git"))

    assert result is None


def test_hook_fails_loud_on_a_postcondition_mismatch(hook_worktree):
    """`big/` holds a stray (untracked) file before the sparse-checkout ever
    runs — `git sparse-checkout set` never touches untracked content outside
    the index, so it survives, and the excluded dir is no longer a husk."""
    hook = _load_hook()
    (hook_worktree / "big").mkdir(exist_ok=True)
    (hook_worktree / "big" / "stray.txt").write_text("oops\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="sparse postcondition failed"):
        hook.apply_sparse(hook_worktree, hook_worktree, "HEAD", {"big"})


def test_hook_reuse_warns_but_never_blocks_on_a_full_looking_worktree(
    hook_worktree, monkeypatch, capsys,
):
    """Idempotency contract: reuse must never fail the spawn, even when the
    reused tree looks unexpectedly FULL — it only warns loudly."""
    hook = _load_hook()
    monkeypatch.setattr(
        hook, "load_profile", lambda repo_root: {"enabled": True, "exclude_dirs": ["big"]},
    )
    (hook_worktree / "big").mkdir(exist_ok=True)
    (hook_worktree / "big" / "data.json").write_bytes(_BIG_CONTENT)

    hook._warn_if_reused_worktree_looks_full(hook_worktree, hook_worktree)
    blob = "".join(capsys.readouterr())

    assert "::warning" in blob and "worktree-sparse-reuse-full" in blob
    assert any(ln.startswith("::warning") for ln in blob.splitlines())


def test_hook_reuse_warning_never_raises_even_on_internal_error(hook_worktree, monkeypatch):
    hook = _load_hook()
    monkeypatch.setattr(
        hook, "load_profile", lambda repo_root: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    hook._warn_if_reused_worktree_looks_full(hook_worktree, hook_worktree)  # must not raise
