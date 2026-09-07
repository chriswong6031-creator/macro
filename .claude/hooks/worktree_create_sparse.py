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

WHERE IT PLANTS (2026-08-20)
----------------------------
Under the checkout the SESSION was launched in, not under the main working tree.
The hook used to derive its destination from ``--git-common-dir``, whose answer
is identical from every checkout of a clone — so every Claude worktree landed in
``Macro Dashboard/.claude/worktrees/`` no matter which folder the operator
opened, including the operator-designated local root the workspace law points
every session at. Placement now follows ``--show-toplevel``, climbed out of any
session-worktree root so spawns never nest, with ``MACRO_LOCAL_ROOT`` as the
explicit override. Only the BYTES move: the clone is one clone, so every
worktree stays registered in ``Macro Dashboard/.git/worktrees/`` and that folder
remains undeletable (see CLAUDE.md § Shared workspace).

``scripts/worktree_gc.py`` expands its repo-relative roots under every host
checkout for the same reason — a tree the sweeper cannot see is a tree it can
never reclaim.

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
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOOK = "WorktreeCreate"
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
PR_NAME = re.compile(r"^pr-([0-9]+)$")

# ── where the new worktree is PLANTED ────────────────────────────────────────
# The bytes of a session worktree and the git metadata registering it live in
# different places, and conflating the two is what planted every Claude worktree
# in the forbidden directory. `--git-common-dir` answers with the MAIN working
# tree's `.git` from EVERY checkout of a clone, so `common.parent` is a constant:
# on this host it can only ever name `Macro Dashboard`, no matter which folder
# the operator opened. That is the right answer to "which git do I talk to" and
# the wrong answer to "where do the files go" — and because it is a constant, no
# session could ever escape it by launching somewhere else.
#
# Placement instead follows the checkout the SESSION was launched in, climbed out
# of any session-worktree root so a spawn plants a sibling rather than nesting.
# Keep this list in step with `ship_loop_guard.AGENT_WORKTREE_ROOTS`,
# `config/worktree_gc.json` roots and `.gitignore` —
# `tests/test_agent_worktree_roots.py` pins all four together.
SESSION_WORKTREE_ROOTS = (
    ".claude/worktrees/",
    ".claire/worktrees/",
    ".codex/worktrees/",
    ".codex-worktrees/",
    ".cursor/worktrees/",
    ".grok/worktrees/",
    ".warp/worktrees/",
)


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


def climb_out_of_session_root(path: Path) -> Path:
    """The directory that OWNS the session-worktree root ``path`` sits under.

    Returns ``path`` unchanged when it is not inside one. A session spawned from
    inside a session worktree must plant its sibling beside it, never within it:
    a nested `.claude/worktrees/a/.claude/worktrees/b` is invisible to the GC's
    depth-1 orphan scan and drags `b` along when `a` is swept.
    """
    parts = Path(path).parts
    for root in SESSION_WORKTREE_ROOTS:
        marker = tuple(root.strip("/").split("/"))
        span = len(marker)
        for index in range(len(parts) - span + 1):
            if parts[index:index + span] == marker:
                return Path(*parts[:index])
    return Path(path)


def same_repository(candidate: Path, common: Path) -> bool:
    """True when ``candidate`` is a checkout of the clone that owns ``common``."""
    try:
        other = Path(git(candidate, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    except RuntimeError:
        return False
    try:
        return other.resolve() == Path(common).resolve()
    except OSError:
        return False


def resolve_host(toplevel: Path, common: Path, primary: Path) -> Path:
    """The checkout that hosts the new session worktree.

    ``MACRO_LOCAL_ROOT`` is the operator's explicit lever (the same variable the
    Grok hook honours); otherwise the session's own checkout hosts. Climbing can
    walk out of the repository entirely — `~/.codex/worktrees/<name>/<checkout>`
    is owned by a home directory, not by a checkout — so a climb that does not
    land on a checkout of this clone falls back to the primary.
    """
    env = os.environ.get("MACRO_LOCAL_ROOT", "").strip()
    if env:
        candidate = Path(env).expanduser()
        if candidate.is_dir() and same_repository(candidate, common):
            return candidate.resolve()
        log(f"ignoring MACRO_LOCAL_ROOT={env!r}: not a checkout of this repository")
    candidate = climb_out_of_session_root(toplevel)
    if candidate == Path(toplevel):
        return Path(toplevel)
    if candidate.is_dir() and same_repository(candidate, common):
        return candidate
    return Path(primary)


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



# Kept in step with scripts.worktree_sparse.STALE_LOCK_MIN_AGE_S —
# tests/test_worktree_sparse.py pins the two constants together so they can
# never drift apart. See that module's constant for the full rationale
# (census 2026-09-06: 97/267 session worktrees found FULL instead of sparse,
# root-caused to a lock refusal that got swallowed upstream).
STALE_LOCK_MIN_AGE_S = 600


def _lock_candidates(dest: Path) -> list[Path]:
    """``index.lock`` and ``info/sparse-checkout.lock`` for ``dest``'s own
    (freshly created, `--no-checkout`) git-dir — never the shared common
    `.git`, which this hook never locks for a sparse-checkout operation."""
    try:
        git_dir = Path(git(dest, "rev-parse", "--path-format=absolute", "--git-dir"))
    except RuntimeError:
        return []
    return [git_dir / "index.lock", git_dir / "info" / "sparse-checkout.lock"]


def _run_lsof(args: list[str]) -> str | None:
    """Best-effort ``lsof`` call; None when it could not be trusted at all
    (missing binary, hung, or any other surprise). Exit 1 (no matches) is a
    trustworthy empty answer, not a failure — duplicated from
    scripts/worktree_sparse.py deliberately: this hook must not depend on the
    repo's import surface being intact (see ``load_profile`` above)."""
    try:
        out = subprocess.run(
            ["lsof", *args], capture_output=True, text=True, timeout=10, check=False,
        )
    except Exception:  # noqa: BLE001
        return None
    if out.returncode not in (0, 1):
        return None
    return out.stdout


def _parse_lsof_pn(text: str) -> list[tuple[int, list[str]]]:
    records: list[tuple[int, list[str]]] = []
    current_paths: list[str] | None = None
    for line in text.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            try:
                pid = int(value)
            except ValueError:
                current_paths = None
                continue
            current_paths = []
            records.append((pid, current_paths))
        elif tag == "n" and current_paths is not None:
            current_paths.append(value)
    return records


def _live_pids_holding(worktree_root: Path, git_dir: Path) -> set[int] | None:
    """PIDs with ``worktree_root`` as cwd or any open file under ``git_dir``.

    None when the probe itself could not be trusted — no lsof on this
    platform, or EITHER required call failed (not just both) — the caller
    must then fail closed and treat the lock as possibly live, never as proof
    nothing holds it. A probe where only one of the two checks came back is
    exactly as untrustworthy as one where neither did: silently keeping the
    half that succeeded would report a confirmed-empty result while the
    other half — the one that might have found the actual holder — was
    never really checked (mirrors scripts.worktree_sparse.gather_live_processes,
    duplicated here for the same import-independence reason as
    ``load_profile``).
    """
    if platform.system() != "Darwin":
        return None  # this host is macOS; no Linux /proc fallback needed here
    pids: set[int] = set()
    cwd_out = _run_lsof(["-a", "-d", "cwd", "-F", "pn", "+D", str(worktree_root)])
    if cwd_out is None:
        return None  # cwd probe untrustworthy — cannot confirm liveness at all
    pids.update(pid for pid, _paths in _parse_lsof_pn(cwd_out))
    file_out = _run_lsof(["-F", "pn", "+D", str(git_dir)])
    if file_out is None:
        return None  # git-dir probe untrustworthy — same fail-closed rule
    pids.update(pid for pid, _paths in _parse_lsof_pn(file_out))
    return pids


def _clear_stale_locks(dest: Path) -> tuple[list[str], list[Path]]:
    """Remove any lock in ``dest``'s git-dir that is both older than
    ``STALE_LOCK_MIN_AGE_S`` and confirmed to have no live process holding
    it, printing a bare line-starting ``::warning`` for each (to stderr —
    this hook's stdout contract carries only the created worktree path).

    Returns ``(removed_paths, still_locked)`` — ``still_locked`` is non-empty
    when a lock is young, live, or its liveness could not be confirmed at
    all; the caller refuses in that case rather than silently proceeding.
    """
    candidates = _lock_candidates(dest)
    locks = [lock for lock in candidates if lock.exists()]
    removed: list[str] = []
    still_locked: list[Path] = []
    if not locks:
        return removed, still_locked
    git_dir = candidates[0].parent if candidates else None
    now = time.time()
    for lock in locks:
        try:
            age_s = max(0.0, now - lock.stat().st_mtime)
        except OSError:
            still_locked.append(lock)
            continue
        if age_s < STALE_LOCK_MIN_AGE_S:
            still_locked.append(lock)
            continue
        pids = _live_pids_holding(dest, git_dir) if git_dir is not None else None
        if pids is None or pids:
            still_locked.append(lock)
            continue
        try:
            lock.unlink()
        except OSError:
            still_locked.append(lock)
            continue
        removed.append(str(lock))
        print(
            f"::warning title=worktree-sparse-stale-lock-removed::{lock} is "
            f"{age_s / 60:.0f}m old (>= {STALE_LOCK_MIN_AGE_S}s) with no live "
            f"process holding {dest} or its git-dir — removed as stale before "
            f"running `git sparse-checkout`",
            file=sys.stderr, flush=True,
        )
    return removed, still_locked


def _verify_sparse_postcondition(dest: Path, include: list[str], excludes: list[str]) -> str | None:
    """Same check as scripts.worktree_sparse.verify_sparse_postcondition,
    duplicated for the same import-independence reason as ``load_profile``:
    `git sparse-checkout list` must equal ``include`` exactly, and every
    excluded directory must be an empty husk on disk, never partially
    materialized content a killed operation left behind."""
    try:
        listed = [
            ln.strip() for ln in git(dest, "sparse-checkout", "list").splitlines() if ln.strip()
        ]
    except RuntimeError as exc:
        return f"`git sparse-checkout list` failed: {exc}"
    if set(listed) != set(include):
        return f"sparse-checkout list mismatch — expected {sorted(include)}, got {sorted(listed)}"
    for name in excludes:
        path = dest / name
        try:
            if not path.exists():
                continue
            entries = list(path.iterdir())
        except OSError:
            continue
        if entries:
            return (
                f"{name} is excluded but not a husk on disk "
                f"({len(entries)} entries present)"
            )
    return None


def apply_sparse(dest: Path, repo_root: Path, base: str, exclude: set[str]) -> None:
    """Select every tracked top-level dir except ``exclude``, then populate.

    Refuses up front on a lock in ``dest``'s git-dir that is not confirmed
    stale (see ``_clear_stale_locks``), and verifies afterward that the
    working tree actually ended up in the requested state (see
    ``_verify_sparse_postcondition``) — both raise ``RuntimeError``, which
    ``main`` already turns into a removed worktree plus a loud hook failure.
    """
    tracked = [ln for ln in git(repo_root, "ls-tree", "-d", "--name-only", base).splitlines() if ln]
    include = [d for d in tracked if d not in exclude]
    if not include:
        raise RuntimeError("no sparse-checkout directories were selected")
    _removed, still_locked = _clear_stale_locks(dest)
    if still_locked:
        named = ", ".join(str(p) for p in still_locked)
        reason = (
            f"{named} exists and is either held by a live process or "
            f"younger than {STALE_LOCK_MIN_AGE_S}s"
        )
        # Bare, line-starting ::error — never through log()/fail(), which
        # prefix with "WorktreeCreate: " and would hide the token behind that
        # prefix (house law: GitHub only recognizes an annotation token that
        # STARTS the line — see AGENTS.md "GitHub annotations must START the
        # line"). This is the frozen-spec-mandated refusal signal for a
        # live/young/unconfirmed lock (spec item 2); the postcondition-
        # mismatch raise below is a separate, already-loud-elsewhere path
        # (its ::error is emitted by scripts.worktree_sparse.apply_profile's
        # equivalent check) and is out of scope for this fix.
        print(
            f"::error title=worktree-sparse-lock-refused::refusing to run "
            f"`git sparse-checkout` — {reason}",
            file=sys.stderr, flush=True,
        )
        raise RuntimeError(f"refusing to run `git sparse-checkout` — {reason}")
    git(dest, "sparse-checkout", "init", "--cone")
    git(dest, "sparse-checkout", "set", "--cone", "--", *include)
    omitted = sorted(set(tracked) & exclude)
    log(f"sparse profile: omitting {', '.join(omitted) if omitted else '(nothing)'}")
    problem = _verify_sparse_postcondition(dest, include, omitted)
    if problem:
        raise RuntimeError(f"sparse postcondition failed: {problem}")


def _warn_if_reused_worktree_looks_full(dest: Path, repo_root: Path) -> None:
    """Best-effort, NON-BLOCKING: loudly flag a reused worktree that looks
    FULL when the configured profile says it should be sparse.

    A prior failed mint attempt could have left ``dest`` registered but never
    sparsified (or a lock could have blocked a repair attempt at the same
    destination). The documented idempotency contract says whichever hook
    wiring runs second must not fail the spawn on reuse, so this only warns —
    it never raises and never blocks — but a silent reuse is exactly the
    "harness reported the worktree as created" failure mode this packet
    exists to stop, so it must not stay silent either.
    """
    try:
        profile = load_profile(repo_root)
        if not profile.get("enabled", True):
            return
        exclude = set(profile.get("exclude_dirs") or ())
        if not exclude:
            return
        full = []
        for name in sorted(exclude):
            path = dest / name
            try:
                if path.is_dir() and any(path.iterdir()):
                    full.append(name)
            except OSError:
                continue
        if full:
            print(
                f"::warning title=worktree-sparse-reuse-full::{dest} was "
                f"reused but {', '.join(full)} is materialized on disk even "
                f"though the profile excludes it — this worktree may be a "
                f"FULL checkout instead of sparse; run `python3 scripts/"
                f"worktree_sparse.py status` in it to confirm and `sparse` "
                f"to re-narrow it",
                file=sys.stderr, flush=True,
            )
    except Exception:  # noqa: BLE001 — this check must never break a reuse
        pass


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
        toplevel = Path(git(Path(cwd), "rev-parse", "--path-format=absolute", "--show-toplevel"))
    except RuntimeError:
        return fail("cwd is not inside a git worktree")
    # `repo_root` is the checkout every git command below runs in AND the folder
    # the worktree is planted under. Both are satisfied by the session's own
    # host: `fetch`, `worktree add` and `worktree remove` are repo-global, so any
    # checkout of the clone serves them identically.
    repo_root = resolve_host(toplevel, common, common.parent)
    worktree_root = repo_root / ".claude" / "worktrees"
    dest = worktree_root / name
    branch = f"worktree-{name}"

    if dest.exists():
        # A sibling wiring (the legacy zsh hook) may have created it already.
        if is_registered_worktree(repo_root, dest):
            log(f"destination already a registered worktree; reusing {dest}")
            _warn_if_reused_worktree_looks_full(dest, repo_root)
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
        log(f"host checkout: {repo_root}")
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
