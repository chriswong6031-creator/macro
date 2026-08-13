#!/usr/bin/env python3
"""WorktreeCreate hook — mint session worktrees off fresh origin/main, sparse.

CONTRACT (set by the harness, preserved byte-for-byte from the zsh prototype
this replaces): stdin carries a JSON object with `name` (the requested worktree
name) and `cwd` (a path inside the repo the session was launched from); STDOUT
must carry the created worktree path and NOTHING else; progress goes to stderr;
exit 0 = created.

WHAT IT DOES
------------
1. `git fetch --prune origin main`, so every session starts on fresh origin/main
   (house law: branch off fresh origin/main, never a squash-merged branch).
2. `git worktree add --no-checkout -b worktree-<name>`.
3. Applies the sparse profile from `config/sparse_worktree.json` — every tracked
   top-level directory EXCEPT the heavy generated ones (`data/`, `site/`,
   `mockups/`, `verify_shots/`).
4. `git read-tree -mu HEAD` to populate exactly the selected paths (a
   `--no-checkout` worktree starts with an empty index).

A name of the form `pr-<N>` bases the worktree on that pull request's head
instead of origin/main.

WHY (research/WORKTREE_GC_POLICY.md §0 R8)
------------------------------------------
A full checkout is ~3.8 GiB and 87 % of that is generated artifacts. At ~40
session worktrees/day the 0-3 d active window is a ~330 GiB standing working set
the GC sweeper cannot touch — it only reclaims FINISHED trees. On 2026-08-13 the
Studio sat at 1.7 Ti / 1.8 Ti (~100 GiB free) after two receipted runner ENOSPC
crashes. Arming the GC (#5502) drains the finished pool; this hook shrinks the
active one. Measured: ~0.35-0.57 GiB per tree instead of 3.8 GiB.

Nothing is hidden by this: the omitted paths stay tracked, `git status` stays
clean (skip-worktree), and a session that needs them runs
`python3 scripts/worktree_sparse.py full`. Guards and tests that REQUIRE a heavy
tree detect the omission and refuse or skip with that command in the message —
see scripts/worktree_sparse.py, which is the single detector they all share.

IDEMPOTENT ON PURPOSE
---------------------
The zsh prototype was wired through `.claude/settings.local.json`, which is
globally gitignored — so the behaviour worked but was neither versioned,
reviewable, nor shipped to any other clone. While both wirings may coexist on a
host mid-migration, whichever hook runs second must not fail the spawn: an
existing destination that is already a registered worktree of this repo is
reported as success.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOOK = "WorktreeCreate"
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
PR_NAME = re.compile(r"^pr-([0-9]+)$")


def log(msg: str) -> None:
    print(f"{HOOK}: {msg}", file=sys.stderr, flush=True)


def fail(msg: str) -> int:
    log(msg)
    return 1


def git(root: Path, *args: str, check: bool = True) -> str:
    """Run git in ``root``; raise RuntimeError on failure when check is True."""
    proc = subprocess.run(
        ("git", "-c", "maintenance.auto=false", "-c", "gc.auto=0", "-C", str(root)) + args,
        capture_output=True, text=True, check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def ref_exists(repo_root: Path, ref: str) -> bool:
    """True when ``ref`` resolves in this repository."""
    return subprocess.run(
        ("git", "-C", str(repo_root), "show-ref", "--verify", "--quiet", ref),
        capture_output=True, check=False,
    ).returncode == 0


def is_registered_worktree(repo_root: Path, dest: Path) -> bool:
    """True when ``dest`` is already a worktree of this repository."""
    try:
        listed = git(repo_root, "worktree", "list", "--porcelain")
    except RuntimeError:
        return False
    target = str(dest.resolve())
    return any(
        ln.startswith("worktree ") and Path(ln[len("worktree "):]).resolve().as_posix() == target
        for ln in listed.splitlines()
    )


# Fallback profile, used only when config/sparse_worktree.json cannot be read —
# e.g. a checkout predating it. R8's two named directories are the floor.
# tests/test_sparse_worktree_profile.py pins this against the config file.
FALLBACK_EXCLUDE_DIRS = ("data", "site")


def load_profile(repo_root: Path) -> dict:
    """Profile from config/sparse_worktree.json — the same file the CLI reads.

    Parsed directly rather than imported through scripts/worktree_sparse.py: this
    hook gates every session spawn on the host, so it must not depend on the
    repo's import surface being intact. Reading JSON needs nothing but stdlib.
    """
    try:
        raw = json.loads((repo_root / "config" / "sparse_worktree.json").read_text("utf-8"))
        excludes = raw.get("exclude_dirs")
        if not isinstance(excludes, list) or not all(isinstance(d, str) for d in excludes):
            raise ValueError(f"exclude_dirs is not a list of strings: {excludes!r}")
        return {"enabled": bool(raw.get("enabled", True)), "exclude_dirs": excludes}
    except Exception as exc:  # noqa: BLE001 — a bad config must never block a spawn
        log(f"profile config unreadable ({exc}); falling back to "
            f"{'/'.join(FALLBACK_EXCLUDE_DIRS)} exclusion")
        return {"enabled": True, "exclude_dirs": list(FALLBACK_EXCLUDE_DIRS)}


def apply_sparse(dest: Path, repo_root: Path, base: str, exclude: set[str]) -> None:
    """Select every tracked top-level dir except ``exclude``, then populate."""
    tracked = [ln for ln in git(repo_root, "ls-tree", "-d", "--name-only", base).splitlines() if ln]
    include = [d for d in tracked if d not in exclude]
    if not include:
        raise RuntimeError("no sparse-checkout directories were selected")
    git(dest, "sparse-checkout", "init", "--cone")
    git(dest, "sparse-checkout", "set", "--cone", "--", *include)
    omitted = sorted(set(tracked) & exclude)
    log(f"sparse profile: omitting {', '.join(omitted) if omitted else '(nothing)'}")


def main() -> int:
    if shutil.which("git") is None:
        return fail("git is unavailable")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        return fail(f"hook input is not valid JSON: {exc}")

    name = payload.get("name")
    cwd = payload.get("cwd")
    if not isinstance(name, str) or not name:
        return fail("hook input does not contain a valid name")
    if not isinstance(cwd, str) or not Path(cwd).is_dir():
        return fail(f"hook input does not contain an existing cwd: {cwd!r}")
    if not SAFE_NAME.match(name):
        return fail(f"unsafe worktree name: {name}")

    try:
        common = Path(git(Path(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"))
    except RuntimeError:
        return fail("cwd is not inside a git worktree")
    repo_root = common.parent
    worktree_root = repo_root / ".claude" / "worktrees"
    dest = worktree_root / name
    branch = f"worktree-{name}"

    if dest.exists():
        # A sibling wiring (the legacy zsh hook) may have created it already.
        if is_registered_worktree(repo_root, dest):
            log(f"destination already a registered worktree; reusing {dest}")
            print(dest)
            return 0
        return fail(f"destination already exists and is not a worktree: {dest}")
    if ref_exists(repo_root, f"refs/heads/{branch}"):
        return fail(f"local branch already exists: {branch}")

    worktree_root.mkdir(parents=True, exist_ok=True)

    try:
        log("refreshing origin/main")
        git(repo_root, "fetch", "--prune", "origin", "main")
        base = "refs/remotes/origin/main"
        pr = PR_NAME.match(name)
        if pr:
            base = f"refs/claude-worktree-pr/{pr.group(1)}"
            log(f"fetching pull request #{pr.group(1)}")
            git(repo_root, "fetch", "origin", f"+refs/pull/{pr.group(1)}/head:{base}")
    except RuntimeError as exc:
        return fail(str(exc))

    created = False
    try:
        profile = load_profile(repo_root)
        sparse = bool(profile.get("enabled", True))
        log(f"creating {'sparse' if sparse else 'full'} worktree at {dest}")
        git(repo_root, "worktree", "add", "--no-checkout", "-b", branch, str(dest), base)
        created = True
        if sparse:
            apply_sparse(dest, repo_root, base, set(profile.get("exclude_dirs") or ()))
        # `--no-checkout` leaves an empty index; populate only the selected paths.
        git(dest, "read-tree", "-mu", "HEAD")
    except RuntimeError as exc:
        if created:
            subprocess.run(("git", "-C", str(repo_root), "worktree", "remove", "--force",
                            "--", str(dest)), capture_output=True, check=False)
        return fail(str(exc))

    print(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
