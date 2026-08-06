"""tests/test_worktree_gc.py — hermetic tests for the fleet worktree sweeper.

COVERAGE
  Classification (fail-closed lattice):
   1. clean + old + HEAD ancestor of origin/main → SAFE_MERGED (ancestor proof)
   2. squash-merge: merged-PR proof requires exact headRefOid match → SAFE_MERGED;
      a head that moved past the merged oid stays UNPUSHED
   3. dirty worktree → DIRTY (kept)
   4. unpushed unique commits → UNPUSHED (kept)
   5. fresh activity → RECENT (kept) — age gate reads STRONG signals only
      (reflog entry epochs, session transcript mtimes); neither observer
      stamps on index/HEAD/dir mtimes nor a repo-global reflog-expire sweep
      of logs/HEAD file mtimes may fake recency (both regression-pinned)
   6. `git worktree lock` → LOCKED (kept)
   7. live process cwd inside → LIVE_PROC (kept)
   8. open PR → OPEN_PR (kept) even when clean + old + pushed
   9. pushed + PR states UNAVAILABLE (None) → UNPUSHED (fail-closed);
      pushed + known-empty PR map → SAFE_REMOTE
  10. orphan directory (no registration) → ORPHAN, never deleted by default
  11. process scan unavailable → ERROR verdicts and apply refuses even armed

  Arming / apply:
  12. --apply with armed:false → exit 2, nothing deleted (report still renders)
  13. --apply armed → deletes only SAFE_*, prunes registration, deletes the
      local branch on the merged proof; DIRTY / UNPUSHED / LOCKED survive
  14. max_delete_per_run caps deletions

All git activity runs against throwaway repos under tmp_path with a local
bare "origin" — no network, no gh (PR states injected via --pr-states-file),
no real ledger writes (LEDGER_DIR monkeypatched).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from scripts import worktree_gc as wgc


# ── scaffolding ──────────────────────────────────────────────────────────────

def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert p.returncode == 0, f"git {' '.join(args)} failed: {p.stderr}"
    return p.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> dict:
    """Primary checkout with a local bare origin and a .claude/worktrees root."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    primary = tmp_path / "primary"
    primary.mkdir()
    _git(primary, "init", "-b", "main")
    _git(primary, "config", "user.email", "t@t")
    _git(primary, "config", "user.name", "t")
    (primary / "README.md").write_text("hello\n")
    _git(primary, "add", "-A")
    _git(primary, "commit", "-m", "init")
    _git(primary, "remote", "add", "origin", str(origin))
    _git(primary, "push", "-u", "origin", "main")
    (primary / ".claude" / "worktrees").mkdir(parents=True)
    return {"primary": primary, "origin": origin, "root": primary / ".claude" / "worktrees"}


def _add_worktree(repo: dict, name: str, branch: str | None = None) -> Path:
    wt = repo["root"] / name
    args = ["worktree", "add"]
    if branch:
        args += ["-b", branch]
    args += [str(wt), "main"]
    _git(repo["primary"], *args)
    return wt


def _commit_in(wt: Path, fname: str = "extra.txt") -> str:
    (wt / fname).write_text("x\n")
    _git(wt, "add", "-A")
    _git(wt, "config", "user.email", "t@t")
    _git(wt, "config", "user.name", "t")
    _git(wt, "commit", "-m", f"add {fname}")
    return _git(wt, "rev-parse", "HEAD")


def _age(repo: dict, wt: Path, days: float = 30.0) -> None:
    """Backdate every activity source the age probe reads.

    The reflog is aged by rewriting each entry's EMBEDDED epoch — the probe
    reads entry content, not the file mtime (repo-global `reflog expire`
    sweeps make the mtime meaningless; see _reflog_last_epoch).
    """
    old = time.time() - days * 86400
    gitdir = Path(_git(wt, "rev-parse", "--absolute-git-dir"))
    for p in [wt, wt / ".git", gitdir / "HEAD", gitdir / "index"]:
        if p.exists():
            os.utime(p, (old, old))
    reflog = gitdir / "logs" / "HEAD"
    if reflog.exists():
        out = []
        for line in reflog.read_text().splitlines():
            head, sep, msg = line.partition("\t")
            toks = head.split()
            if len(toks) >= 2:
                toks[-2] = str(int(old))
            out.append(" ".join(toks) + sep + msg)
        reflog.write_text("\n".join(out) + "\n")
        os.utime(reflog, (old, old))


def _write_config(tmp_path: Path, **overrides) -> Path:
    cfg = {"armed": False, "min_age_days": 7, "include_open_pr": False,
           "include_orphans": False, "delete_local_branches": True,
           "max_delete_per_run": 200, "pr_limit": 50,
           "roots": [".claude/worktrees"]}
    cfg.update(overrides)
    p = tmp_path / "gc_config.json"
    p.write_text(json.dumps(cfg))
    return p


def _pr_file(tmp_path: Path, states: dict) -> Path:
    p = tmp_path / "pr_states.json"
    p.write_text(json.dumps(states))
    return p


def _run_main(repo: dict, tmp_path: Path, monkeypatch, *, cfg: Path | None = None,
              pr_states: dict | None = None, apply: bool = False,
              procs: dict | None = None, extra: list[str] | None = None) -> tuple[int, dict]:
    """Invoke wgc.main() hermetically; returns (exit_code, json payload)."""
    monkeypatch.setattr(wgc, "LEDGER_DIR", tmp_path / "ledger")
    monkeypatch.setattr(wgc, "session_activity_mtime", lambda path: None)
    if procs is None:
        monkeypatch.setattr(wgc, "proc_cwd_map", lambda roots: {})
    else:
        monkeypatch.setattr(wgc, "proc_cwd_map", lambda roots: procs)
    out = tmp_path / "out.json"
    argv = ["--repo-root", str(repo["primary"]),
            "--config", str(cfg or _write_config(tmp_path)),
            "--no-gh", "--no-sizes", "--json-out", str(out)]
    if pr_states is not None:
        argv += ["--pr-states-file", str(_pr_file(tmp_path, pr_states))]
        argv.remove("--no-gh")
    if apply:
        argv.append("--apply")
    if extra:
        argv += extra
    rc = wgc.main(argv)
    return rc, json.loads(out.read_text())


def _verdict(payload: dict, name: str) -> dict:
    for w in payload["worktrees"]:
        if w["name"] == name:
            return w
    raise AssertionError(f"worktree {name} not in payload")


# ── classification ───────────────────────────────────────────────────────────

def test_ancestor_of_main_clean_old_is_safe_merged(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "done", branch="claude/done")
    _age(repo, wt)
    rc, payload = _run_main(repo, tmp_path, monkeypatch)
    assert rc == 0
    w = _verdict(payload, "done")
    assert w["verdict"] == "SAFE_MERGED"
    assert "ancestor" in w["proof"]


def test_squash_merge_needs_exact_oid_match(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "squashed", branch="claude/squashed")
    head = _commit_in(wt)
    _age(repo, wt)
    # PR merged at exactly this head → safe even though ancestry can't see it.
    rc, payload = _run_main(repo, tmp_path, monkeypatch, pr_states={
        "claude/squashed": {"state": "MERGED", "number": 42, "headRefOid": head}})
    assert _verdict(payload, "squashed")["verdict"] == "SAFE_MERGED"
    # Same PR but the local head moved past the merged oid → fail closed.
    head2 = _commit_in(wt, "after_merge.txt")
    assert head2 != head
    _age(repo, wt)
    rc, payload = _run_main(repo, tmp_path, monkeypatch, pr_states={
        "claude/squashed": {"state": "MERGED", "number": 42, "headRefOid": head}})
    assert _verdict(payload, "squashed")["verdict"] == "UNPUSHED"


def test_dirty_is_kept(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "dirty", branch="claude/dirty")
    (wt / "scratch.txt").write_text("uncommitted\n")
    _age(repo, wt)
    _, payload = _run_main(repo, tmp_path, monkeypatch)
    assert _verdict(payload, "dirty")["verdict"] == "DIRTY"


def test_unpushed_commits_are_kept(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "unpushed", branch="claude/unpushed")
    _commit_in(wt)
    _age(repo, wt)
    _, payload = _run_main(repo, tmp_path, monkeypatch)
    assert _verdict(payload, "unpushed")["verdict"] == "UNPUSHED"


def test_recent_activity_is_kept(repo, tmp_path, monkeypatch):
    _add_worktree(repo, "fresh", branch="claude/fresh")
    _, payload = _run_main(repo, tmp_path, monkeypatch)
    assert _verdict(payload, "fresh")["verdict"] == "RECENT"


def test_observer_stamps_do_not_fake_recency(repo, tmp_path, monkeypatch):
    """Fleet dashboards running plain `git status` rewrite gitdir/index, and
    Finder/.DS_Store bumps the worktree dir mtime — observation, not activity.
    Measured on the Studio: 137/143 dead trees were pinned "fresh" purely by
    such file mtimes while reflog entries and transcripts sat weeks old.
    Only STRONG signals may gate."""
    wt = _add_worktree(repo, "observed", branch="claude/observed")
    _age(repo, wt)
    gitdir = Path(_git(wt, "rev-parse", "--absolute-git-dir"))
    now = time.time()
    for p in [wt, wt / ".git", gitdir / "HEAD", gitdir / "index"]:
        if p.exists():
            os.utime(p, (now, now))
    _, payload = _run_main(repo, tmp_path, monkeypatch)
    w = _verdict(payload, "observed")
    assert w["verdict"] == "SAFE_MERGED", f"observer stamps misread as {w['verdict']}"
    assert w["age_days"] > 7


def test_reflog_file_mtime_sweep_does_not_fake_recency(repo, tmp_path, monkeypatch):
    """Repo-global `reflog expire` rewrites every worktree's logs/HEAD in one
    sweep (measured stamping all 186 Studio trees at 2026-08-04 15:38:24).
    A fresh reflog FILE mtime over old entry epochs must not read as activity."""
    wt = _add_worktree(repo, "expired", branch="claude/expired")
    _age(repo, wt)
    gitdir = Path(_git(wt, "rev-parse", "--absolute-git-dir"))
    now = time.time()
    os.utime(gitdir / "logs" / "HEAD", (now, now))  # the maintenance sweep
    _, payload = _run_main(repo, tmp_path, monkeypatch)
    w = _verdict(payload, "expired")
    assert w["verdict"] == "SAFE_MERGED", f"stale tree misread as {w['verdict']}"
    assert w["age_days"] > 7


def test_locked_is_kept(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "pinned", branch="claude/pinned")
    _git(repo["primary"], "worktree", "lock", "--reason", "session parked", str(wt))
    _age(repo, wt)
    _, payload = _run_main(repo, tmp_path, monkeypatch)
    w = _verdict(payload, "pinned")
    assert w["verdict"] == "LOCKED"
    assert "session parked" in " ".join(w["reasons"])


def test_live_process_is_kept(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "busy", branch="claude/busy")
    _age(repo, wt)
    procs = {str(wt.resolve()): ["123:zsh"]}
    _, payload = _run_main(repo, tmp_path, monkeypatch, procs=procs)
    w = _verdict(payload, "busy")
    assert w["verdict"] == "LIVE_PROC"
    assert w["procs"] == ["123:zsh"]


def test_open_pr_is_kept_even_when_pushed_and_old(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "inflight", branch="claude/inflight")
    _commit_in(wt)
    _git(wt, "push", "-u", "origin", "claude/inflight")
    _age(repo, wt)
    _, payload = _run_main(repo, tmp_path, monkeypatch, pr_states={
        "claude/inflight": {"state": "OPEN", "number": 7, "headRefOid": ""}})
    w = _verdict(payload, "inflight")
    assert w["verdict"] == "OPEN_PR"
    assert "PR #7" in " ".join(w["reasons"])


def test_pushed_fail_closed_without_pr_states_safe_remote_with(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "pushed", branch="claude/pushed")
    _commit_in(wt)
    _git(wt, "push", "-u", "origin", "claude/pushed")
    _age(repo, wt)
    # PR states unavailable (--no-gh, no file) → cannot rule out an open PR.
    _, payload = _run_main(repo, tmp_path, monkeypatch)
    assert _verdict(payload, "pushed")["verdict"] == "UNPUSHED"
    # Known-complete (empty) PR map → provably no open PR → SAFE_REMOTE.
    _, payload = _run_main(repo, tmp_path, monkeypatch, pr_states={})
    w = _verdict(payload, "pushed")
    assert w["verdict"] == "SAFE_REMOTE"
    assert "origin/claude/pushed" in w["proof"]


def test_orphan_dir_reported_not_deleted(repo, tmp_path, monkeypatch):
    orphan = repo["root"] / "husk"
    orphan.mkdir()
    (orphan / "junk.bin").write_text("x")
    old = time.time() - 30 * 86400
    os.utime(orphan, (old, old))
    cfg = _write_config(tmp_path, armed=True)
    rc, payload = _run_main(repo, tmp_path, monkeypatch, cfg=cfg, apply=True)
    assert _verdict(payload, "husk")["verdict"] == "ORPHAN"
    assert orphan.exists(), "orphan must survive apply while include_orphans=false"


def test_proc_scan_failure_fails_closed(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "done", branch="claude/done")
    _age(repo, wt)
    monkeypatch.setattr(wgc, "LEDGER_DIR", tmp_path / "ledger")
    monkeypatch.setattr(wgc, "session_activity_mtime", lambda path: None)
    monkeypatch.setattr(wgc, "proc_cwd_map", lambda roots: None)
    out = tmp_path / "out.json"
    rc = wgc.main(["--repo-root", str(repo["primary"]),
                   "--config", str(_write_config(tmp_path, armed=True)),
                   "--no-gh", "--no-sizes", "--apply", "--json-out", str(out)])
    payload = json.loads(out.read_text())
    assert rc == 2
    assert _verdict(payload, "done")["verdict"] == "ERROR"
    assert wt.exists()


# ── arming / apply ───────────────────────────────────────────────────────────

def test_apply_disarmed_refuses(repo, tmp_path, monkeypatch):
    wt = _add_worktree(repo, "done", branch="claude/done")
    _age(repo, wt)
    rc, payload = _run_main(repo, tmp_path, monkeypatch, apply=True)
    assert rc == 2
    assert wt.exists()
    assert payload["apply"] is None
    assert _verdict(payload, "done")["verdict"] == "SAFE_MERGED"  # report still classified


def test_apply_armed_deletes_only_safe(repo, tmp_path, monkeypatch):
    safe = _add_worktree(repo, "safe", branch="claude/safe")
    _age(repo, safe)
    dirty = _add_worktree(repo, "dirty", branch="claude/dirty")
    (dirty / "scratch.txt").write_text("keep me\n")
    _age(repo, dirty)
    unpushed = _add_worktree(repo, "unpushed", branch="claude/unpushed")
    _commit_in(unpushed)
    _age(repo, unpushed)

    cfg = _write_config(tmp_path, armed=True)
    rc, payload = _run_main(repo, tmp_path, monkeypatch, cfg=cfg, apply=True, pr_states={})
    assert rc == 0
    assert not safe.exists()
    assert dirty.exists() and unpushed.exists()
    assert str(safe) in payload["apply"]["deleted"]
    # registration pruned, merged-proof branch deleted
    listed = _git(repo["primary"], "worktree", "list", "--porcelain")
    assert "safe" not in listed
    branches = _git(repo["primary"], "branch", "--list", "claude/safe")
    assert branches == ""
    assert (tmp_path / "ledger" / "ledger.jsonl").exists()


def test_max_delete_cap(repo, tmp_path, monkeypatch):
    for i in range(3):
        _age(repo, _add_worktree(repo, f"safe{i}", branch=f"claude/safe{i}"))
    cfg = _write_config(tmp_path, armed=True, max_delete_per_run=2)
    rc, payload = _run_main(repo, tmp_path, monkeypatch, cfg=cfg, apply=True, pr_states={})
    assert rc == 0
    assert len(payload["apply"]["deleted"]) == 2
    assert payload["apply"]["skipped_cap"] == 1
    survivors = [w for w in ("safe0", "safe1", "safe2") if (repo["root"] / w).exists()]
    assert len(survivors) == 1
