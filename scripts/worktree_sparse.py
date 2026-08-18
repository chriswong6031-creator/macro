#!/usr/bin/env python3
"""Sparse session-worktree profile — detector + one-command opt-in (policy R8).

WHY THIS EXISTS
---------------
`research/WORKTREE_GC_POLICY.md` §0 R8: a full checkout of this repo is ~3.8 GiB,
of which `data/` 2.3 + `site/` 0.73 + `mockups/` 0.23 + `verify_shots/` 0.05 =
**87 %** is generated artifacts that a typical session never reads. At the
measured fleet cadence (~40 session worktrees/day) the 0-3 d ACTIVE window is a
~330 GiB standing working set that the GC sweeper structurally cannot reduce —
it only reclaims trees that are already finished.

On 2026-08-13 the Studio hit 1.7 Ti / 1.8 Ti (~100 GiB free) and self-hosted
runners ENOSPC-crashed twice. Arming the GC (#5502) drains the finished pool;
only a thinner per-tree footprint shrinks the active window. This module is that
second half: new session worktrees check out every directory EXCEPT the heavy
generated ones, and this CLI is the one command that opts back in.

THE HONESTY RULE (why this is a detector and not just a setup script)
--------------------------------------------------------------------
A sparse tree must never make a guard or a test read GREEN for the wrong reason.
Two measured ways it silently can:

  * `scripts/check_template_site_sync.py` enumerates its own pair list by
    walking `site/`. With `site/` absent, `find_pairs` yields nothing and the
    paired plain-copy asset law reports "sync OK (0 pairs checked)" and exits 0
    — a vacuous pass on the exact guard that protects the render lanes.
    `render.yml` carries a long comment about the same failure mode reaching the
    lane itself ("would render, guard and COMMIT whatever subset of the tree it
    found — a truncated publish, not a red X").
  * tests that read the committed `site/`/`data/` trees fail with a confusing
    FileNotFoundError that reads like a real regression.

So every caller that needs a heavy tree asks `missing_dirs()` FIRST and refuses
or skips with `remedy_line()` in the message. Nothing is silently greened.

DETECTION IS NOT A DIRECTORY CHECK
----------------------------------
`(root / "data").is_dir()` lies in both directions, measured on this tree:

  * `site/` is absent entirely -> is_dir() False (correct, by luck)
  * `data/` survives as a 0-byte HUSK after `git reset --hard` -> is_dir() True
    while holding none of the 2.3 GiB it tracks.

The husk is why `git reset --hard` cannot be trusted to restore the profile
either. The authoritative signal is git's own sparse state: cone-mode
`git sparse-checkout list` is the include set, and anything HEAD tracks that is
not in it is omitted. The emptiness heuristic is only the non-cone fallback.

Usage:
    python3 scripts/worktree_sparse.py status        # what is / is not materialized
    python3 scripts/worktree_sparse.py auto          # new linked worktree: apply profile
    python3 scripts/worktree_sparse.py full          # opt IN to a full checkout
    python3 scripts/worktree_sparse.py sparse        # re-apply the configured profile
    python3 scripts/worktree_sparse.py add site      # materialize ONE excluded dir
    python3 scripts/worktree_sparse.py clean         # report stray writes into an
    python3 scripts/worktree_sparse.py clean --force # omitted tree, and delete them
Exit codes: 0 = success · 1 = failure (not a git worktree, git error, bad dir).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sparse_worktree.json"

# `git sparse-checkout add` (and `disable`, which is the same hazard at LARGER
# scale — it materializes every omitted tree at once, ~3.31 of the repo's
# 3.8 GiB, where `add` materializes one) checks out a heavy tree file-by-file;
# a process that dies mid-loop (our own wrapper timing out and SIGKILLing it,
# an OOM kill, a session getting torn down) leaves whatever file it was
# writing truncated on disk AND a stale `index.lock` that git created but
# never got to rename into place (measured 2026-08-18: a 0-byte tracked JSON
# file plus a ~49-minute-old `.git/worktrees/<name>/index.lock`; reproduced
# deterministically here by racing a short subprocess timeout against a real
# `sparse-checkout add` — see tests/test_worktree_sparse_add_lock_safety.py).
# The originating report's own hypothesis ("the stale lock caused it") was
# WRONG BUT USEFUL: it correctly named the worktree state to look at while
# misattributing cause. The lock is a CO-SYMPTOM, not the trigger — the real
# mechanism is timeout -> SIGKILL -> a file already `open()`ed (which
# truncates) never receives its content write, and the same kill orphans the
# lock because the rename-into-place that would have cleared it never runs.
# ADD_TIMEOUT_S is the same 60s budget `_git()` uses elsewhere, shared by both
# operations and exposed as a parameter so a test can shrink it instead of
# waiting on real timing. Left at 60s deliberately — the repair path below
# covers the corruption regardless of what makes the checkout exceed it.
ADD_TIMEOUT_S = 60

# Fallback when config/sparse_worktree.json is unreadable. Kept in step with that
# file by tests/test_sparse_worktree_profile.py so the two can never drift.
DEFAULT_EXCLUDE_DIRS = ("data", "site", "mockups", "verify_shots")

FULL_CHECKOUT_CMD = "python3 scripts/worktree_sparse.py full"


def remedy_line(dirs: list[str] | tuple[str, ...] | None = None) -> str:
    """The one-line remedy every refusal/skip message must carry."""
    what = ", ".join(sorted(dirs)) if dirs else "heavy generated trees"
    return (
        f"sparse worktree — {what} not checked out; "
        f"opt into a full checkout with: {FULL_CHECKOUT_CMD}"
    )


def load_profile(config_path: Path | None = None) -> dict:
    """Return {'enabled': bool, 'exclude_dirs': [...]}, falling back to defaults."""
    path = config_path or CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a missing/broken config must not break the hook
        return {"enabled": True, "exclude_dirs": list(DEFAULT_EXCLUDE_DIRS)}
    excludes = raw.get("exclude_dirs")
    if not isinstance(excludes, list) or not all(isinstance(d, str) for d in excludes):
        excludes = list(DEFAULT_EXCLUDE_DIRS)
    return {"enabled": bool(raw.get("enabled", True)), "exclude_dirs": excludes}


def _git(root: Path, *args: str) -> str | None:
    """Run a git command in ``root``; None when git is unavailable or it fails."""
    try:
        out = subprocess.run(
            ("git", "-C", str(root)) + args,
            capture_output=True, text=True, timeout=60, check=False,
        )
    except Exception:  # noqa: BLE001 — git missing, or a hung filesystem
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _git_bytes(root: Path, *args: str, timeout: float = 60) -> bytes | None:
    """Like ``_git`` but returns raw bytes — a byte-exact restore must never go
    through text decoding, which can silently mangle a binary blob."""
    try:
        out = subprocess.run(
            ("git", "-C", str(root)) + args,
            capture_output=True, timeout=timeout, check=False,
        )
    except Exception:  # noqa: BLE001
        return None
    return out.stdout if out.returncode == 0 else None


def index_lock_path(root: Path = ROOT) -> Path | None:
    """The ``index.lock`` this checkout's git-dir would use — worktree-aware.

    ``git rev-parse --git-dir`` already resolves to ``.git/worktrees/<name>``
    for a linked worktree and to ``.git`` for the primary checkout, so a single
    lookup covers both cases the frozen spec names. None when git itself is
    unreadable (matches ``_git``'s failure contract).
    """
    git_dir = _git(root, "rev-parse", "--path-format=absolute", "--git-dir")
    if not git_dir:
        return None
    return Path(git_dir) / "index.lock"


def _lock_age_desc(lock: Path) -> str:
    try:
        age_s = max(0.0, time.time() - lock.stat().st_mtime)
    except OSError:
        return "unknown age"
    if age_s < 60:
        return f"{age_s:.0f}s old"
    return f"{age_s / 60:.0f}m old"


def refuse_if_locked(root: Path = ROOT) -> bool:
    """Print a loud, actionable refusal and return True when a stale/live
    ``index.lock`` already sits in this checkout's git-dir.

    Never deletes the lock: another process may legitimately hold it. This is
    the up-front half of the fix — it stops a NEW ``add`` from running into a
    lock a previous failed attempt (or a genuinely concurrent git process)
    left behind, instead of proceeding into the same partial-write corruption.
    """
    lock = index_lock_path(root)
    if lock is None or not lock.exists():
        return False
    age = _lock_age_desc(lock)
    print(
        f"::error title=worktree-sparse-locked::{lock} exists ({age}) — refusing "
        f"to run `git sparse-checkout add`. Check for a live git process using "
        f"this worktree (e.g. `ps aux | grep '[g]it.*{root.name}'`); if none is "
        f"running, a previous `worktree_sparse.py add` was likely killed (a slow "
        f"or timed-out materialization) and left this lock stale. Only remove it "
        f"once you've confirmed nothing else holds it: rm '{lock}'",
        flush=True,
    )
    return True


def _committed_sizes(root: Path, name: str) -> dict[str, int]:
    """``{relative_path: committed byte size}`` for every file HEAD tracks under
    ``name`` — read straight from the tree object, independent of whatever
    inconsistent state a killed checkout left the index/sparse patterns in."""
    out = _git(root, "ls-tree", "-r", "-l", "HEAD", "--", name)
    sizes: dict[str, int] = {}
    if not out:
        return sizes
    for line in out.splitlines():
        try:
            meta, path = line.split("\t", 1)
        except ValueError:
            continue
        fields = meta.split()
        if len(fields) < 4 or fields[3] == "-":  # "-" = submodule; no blob size
            continue
        try:
            sizes[path] = int(fields[3])
        except ValueError:
            continue
    return sizes


def verify_and_repair(root: Path, names: list[str]) -> list[str]:
    """Restore, byte-for-byte from HEAD, any on-disk tracked file under ``names``
    whose size no longer matches what HEAD committed — the exact signature a
    process killed mid-``sparse-checkout add`` leaves (materialized via
    open+truncate, killed before the content write landed).

    Deliberately never uses ``git checkout --`` — the stale ``index.lock`` this
    same failure typically leaves behind makes that refuse (measured: `fatal:
    Unable to create '.../index.lock': File exists`). ``git show HEAD:<path>``
    reads straight from the object database and writing it out bypasses the
    index entirely, so it works even while that lock is still sitting there.

    Returns the list of relative paths actually rewritten, for the caller to
    report.
    """
    repaired: list[str] = []
    for name in names:
        committed = _committed_sizes(root, name)
        for rel_path, expected_size in committed.items():
            abs_path = root / rel_path
            try:
                if not abs_path.is_file():
                    continue  # never materialized at all — not corruption
                if abs_path.stat().st_size == expected_size:
                    continue  # matches HEAD — nothing to repair
            except OSError:
                continue
            content = _git_bytes(root, "show", f"HEAD:{rel_path}")
            if content is None:
                continue
            try:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_bytes(content)
            except OSError:
                continue
            repaired.append(rel_path)
    return repaired


def sparse_enabled(root: Path = ROOT) -> bool:
    """True when this worktree has sparse-checkout switched on."""
    return (_git(root, "config", "--get", "core.sparseCheckout") or "").lower() == "true"


def is_linked_worktree(root: Path = ROOT) -> bool:
    """True for a linked Git worktree, false for the repository's primary checkout.

    Codex has no pre-checkout equivalent of Claude's ``WorktreeCreate`` event.
    Its supported local-environment setup and ``SessionStart`` hooks therefore
    call :func:`auto_profile` after Git has created the checkout.  Both hooks can
    also fire for a Local chat, so this discriminator is load-bearing: the
    occupied primary checkout must never be sparsified as a side effect of
    starting Codex.
    """
    git_dir = _git(root, "rev-parse", "--path-format=absolute", "--git-dir")
    common_dir = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not git_dir or not common_dir:
        return False
    try:
        return Path(git_dir).resolve() != Path(common_dir).resolve()
    except OSError:
        return git_dir != common_dir


# Path markers that identify a *session* worktree rather than any linked checkout.
# The operator's designated local root (macro-main) is itself a linked worktree of
# the occupied primary; a SessionStart/workspaceOpen hook that keyed only on
# :func:`is_linked_worktree` would sparsify that 3.8 GiB tree on every Cursor
# chat. Keep this tuple in step with ``config/worktree_gc.json`` roots plus the
# Cursor/Grok in-repo worktree folders those harnesses mint.
SESSION_WORKTREE_MARKERS: tuple[tuple[str, ...], ...] = (
    (".claude", "worktrees"),
    (".claire", "worktrees"),
    (".codex", "worktrees"),
    (".codex-worktrees",),
    (".cursor", "worktrees"),
    (".grok", "worktrees"),
)


def is_session_worktree(root: Path = ROOT) -> bool:
    """True when ``root`` is a linked worktree sitting under a session root.

    Linked-worktree is necessary but not sufficient. ``auto`` must refuse the
    operator's designated local project root even though that folder is a
    linked worktree of the occupied primary.
    """
    if not is_linked_worktree(root):
        return False
    try:
        parts = Path(root).resolve().parts
    except OSError:
        parts = Path(root).parts
    for marker in SESSION_WORKTREE_MARKERS:
        length = len(marker)
        for index in range(len(parts) - length + 1):
            if parts[index:index + length] == marker:
                return True
    return False


def _cone_included(root: Path) -> list[str]:
    """Cone-mode include set (top-level directory names); [] when not cone mode."""
    if (_git(root, "config", "--get", "core.sparseCheckoutCone") or "").lower() != "true":
        return []
    listed = _git(root, "sparse-checkout", "list")
    return [ln.strip() for ln in listed.splitlines() if ln.strip()] if listed else []


def tracked_top_level_dirs(root: Path = ROOT, ref: str = "HEAD") -> list[str]:
    """Top-level directories the given ref tracks (sparse state is irrelevant here)."""
    listed = _git(root, "ls-tree", "-d", "--name-only", ref)
    return sorted(ln.strip() for ln in listed.splitlines() if ln.strip()) if listed else []


def _has_content(path: Path) -> bool:
    """True when the directory exists AND holds at least one entry (husk-aware)."""
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def missing_dirs(root: Path = ROOT) -> list[str]:
    """Top-level dirs that HEAD tracks but this working tree does not materialize.

    Cone mode (what our WorktreeCreate hook sets) is answered exactly from git's
    include set. Non-cone / no-git checkouts fall back to the husk-aware
    emptiness probe. A full checkout returns [] under both paths.
    """
    tracked = tracked_top_level_dirs(root)
    if not tracked:
        return []
    if sparse_enabled(root):
        included = _cone_included(root)
        if included:
            return [d for d in tracked if d not in included]
    return [d for d in tracked if not _has_content(root / d)]


def is_sparse(root: Path = ROOT) -> bool:
    """True when at least one tracked top-level directory is not materialized."""
    return bool(missing_dirs(root))


def require_full_checkout(dirs: list[str], root: Path = ROOT) -> None:
    """Raise RuntimeError naming the remedy when any of ``dirs`` is sparse-omitted.

    Callers that would otherwise produce a vacuous result (an empty pair list, an
    empty glob) use this so the sparse tree fails LOUD instead of passing empty.
    """
    absent = [d for d in missing_dirs(root) if d in set(dirs)]
    if absent:
        raise RuntimeError(remedy_line(absent))


def _drop_husks(root: Path, dirs: list[str]) -> list[str]:
    """Remove 0-entry husk directories left behind by `git reset --hard`."""
    dropped = []
    for name in dirs:
        path = root / name
        if path.is_dir() and not any(path.iterdir()):
            try:
                path.rmdir()
                dropped.append(name)
            except OSError:
                pass
    return dropped


def apply_profile(root: Path = ROOT, exclude_dirs: list[str] | None = None) -> int:
    """(Re-)apply the sparse profile to an existing worktree.

    Narrowing the cone is mostly a DELETE (files leaving the working tree, not
    a from-scratch write of new content), so it does not carry `add`/`full`'s
    truncation risk the same way — but this still runs `git sparse-checkout
    set`, a checkout that can leave a stale `index.lock` if killed regardless
    of which direction it moves the cone, and `auto` calls this on every
    session-worktree creation across four agent runtimes. A lock left behind
    here is inherited by the very next git command any of those runtimes runs
    in this worktree, so the cheap up-front refusal is worth it even though
    the heavier byte-for-byte repair below is not (PR discussion, 2026-08-18).
    """
    excludes = set(exclude_dirs if exclude_dirs is not None else load_profile()["exclude_dirs"])
    tracked = tracked_top_level_dirs(root)
    if not tracked:
        print("worktree-sparse: not a git worktree (or HEAD is unreadable)", file=sys.stderr)
        return 1
    include = [d for d in tracked if d not in excludes]
    if not include:
        print("worktree-sparse: refusing to exclude every tracked directory", file=sys.stderr)
        return 1
    if refuse_if_locked(root):
        return 1
    if _git(root, "sparse-checkout", "init", "--cone") is None:
        print("worktree-sparse: `git sparse-checkout init --cone` failed", file=sys.stderr)
        return 1
    if _git(root, "sparse-checkout", "set", "--cone", "--", *include) is None:
        print("worktree-sparse: `git sparse-checkout set` failed", file=sys.stderr)
        return 1
    _drop_husks(root, sorted(excludes))
    print(f"worktree-sparse: profile applied — omitting {', '.join(sorted(excludes))}")
    return 0


def auto_profile(root: Path = ROOT, config_path: Path | None = None) -> int:
    """Apply the configured profile once to a newly created linked worktree.

    This is the safe entry point for Codex/Cursor/Grok lifecycle automation.
    It deliberately skips the primary checkout, skips a linked checkout that
    is not under a session worktree root (the operator's designated local
    root is one of those), and preserves any sparse selection already present
    in a session worktree, including an explicit ``add site`` opt-in.
    ``enabled: false`` remains the single repo-wide off switch.
    """
    if not is_session_worktree(root):
        print("worktree-sparse: auto skipped — only session worktrees are changed")
        return 0

    profile_path = config_path or root / "config" / "sparse_worktree.json"
    profile = load_profile(profile_path)
    if not profile["enabled"]:
        print("worktree-sparse: auto disabled by config/sparse_worktree.json")
        return 0

    if sparse_enabled(root):
        print("worktree-sparse: auto skipped — linked worktree is already sparse; "
              "preserving its current selection")
        return 0

    return apply_profile(root, exclude_dirs=list(profile["exclude_dirs"]))


def disable_profile(root: Path = ROOT, timeout: float = ADD_TIMEOUT_S) -> int:
    """Opt in to a full checkout. Worktree-scoped: siblings are untouched.

    `sparse-checkout disable` is the LARGER version of `add`'s hazard, not a
    different one: it materializes every currently-omitted tree in one pass
    (measured ~3.31 of the repo's 3.8 GiB) instead of just the one(s) named to
    `add`, so it is more, not less, likely to exceed ``timeout`` and get
    SIGKILLed mid-write. Same three protections as `add_dirs`: refuse up front
    on an existing lock, fail loud on a killed/failed disable, and repair any
    tracked file the partial checkout left truncated.
    """
    if not sparse_enabled(root):
        print("worktree-sparse: already a full checkout")
        return 0
    if refuse_if_locked(root):
        return 1
    omitted_before = missing_dirs(root)
    ok, reason = _run_sparse_checkout_disable(root, timeout=timeout)
    if not ok:
        print(
            f"::error title=worktree-sparse-full-failed::`git sparse-checkout "
            f"disable` {reason} in {root} — the working tree may hold partially "
            f"materialized or truncated tracked files across "
            f"{', '.join(omitted_before) if omitted_before else 'the omitted trees'}; "
            f"verifying and repairing from HEAD now",
            flush=True,
        )
        repaired = verify_and_repair(root, omitted_before) if omitted_before else []
        if repaired:
            print(
                f"worktree-sparse: restored {len(repaired)} truncated tracked "
                f"file(s) from HEAD: {', '.join(repaired[:10])}"
                f"{' …' if len(repaired) > 10 else ''}",
                file=sys.stderr,
            )
        else:
            print("worktree-sparse: no truncated tracked file found to repair",
                  file=sys.stderr)
        return 1
    still = missing_dirs(root)
    if still:
        print(f"worktree-sparse: WARNING — still missing {', '.join(still)}", file=sys.stderr)
        return 1
    print("worktree-sparse: full checkout restored (this worktree only)")
    return 0


def _run_git_timed(root: Path, args: tuple[str, ...], timeout: float) -> tuple[bool, str]:
    """Run a git subcommand under an explicit timeout.

    Returns ``(True, "")`` on success, else ``(False, reason)`` — distinguishing
    a timeout-triggered kill from an ordinary nonzero exit so a failure
    annotation can say which. ``timeout`` is a parameter (not a hard-coded
    constant) so a test can shrink it to deterministically race a real git
    checkout instead of waiting out the production 60s budget.

    Shared by ``sparse-checkout add`` and ``sparse-checkout disable`` — both
    materialize a heavy tree in one shot and are equally exposed to the
    SIGKILL-mid-write corruption this module guards against (`disable` is the
    LARGER hazard: it checks out every omitted tree at once, not just one).
    """
    try:
        out = subprocess.run(
            ("git", "-C", str(root)) + args,
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s and was killed"
    except Exception as exc:  # noqa: BLE001 — git missing, or a hung filesystem
        return False, str(exc)
    if out.returncode != 0:
        stderr = out.stderr.strip()
        return False, f"exited {out.returncode}" + (f": {stderr[:300]}" if stderr else "")
    return True, ""


def _run_sparse_checkout_add(
    root: Path, names: list[str], timeout: float = ADD_TIMEOUT_S,
) -> tuple[bool, str]:
    """Run ``git sparse-checkout add -- <names>``. See ``_run_git_timed``."""
    return _run_git_timed(root, ("sparse-checkout", "add", "--", *names), timeout)


def _run_sparse_checkout_disable(root: Path, timeout: float = ADD_TIMEOUT_S) -> tuple[bool, str]:
    """Run ``git sparse-checkout disable``. See ``_run_git_timed``."""
    return _run_git_timed(root, ("sparse-checkout", "disable"), timeout)


def add_dirs(names: list[str], root: Path = ROOT, timeout: float = ADD_TIMEOUT_S) -> int:
    """Materialize specific excluded directories, keeping the rest sparse."""
    tracked = set(tracked_top_level_dirs(root))
    unknown = [n for n in names if n not in tracked]
    if unknown:
        print(f"worktree-sparse: not tracked at HEAD: {', '.join(unknown)}", file=sys.stderr)
        return 1
    if not sparse_enabled(root):
        print("worktree-sparse: already a full checkout — nothing to add")
        return 0
    if refuse_if_locked(root):
        return 1
    _drop_husks(root, names)
    ok, reason = _run_sparse_checkout_add(root, names, timeout=timeout)
    if not ok:
        print(
            f"::error title=worktree-sparse-add-failed::`git sparse-checkout add "
            f"-- {' '.join(names)}` {reason} in {root} — the working tree may hold "
            f"partially materialized or truncated tracked files; verifying and "
            f"repairing from HEAD now",
            flush=True,
        )
        repaired = verify_and_repair(root, names)
        if repaired:
            print(
                f"worktree-sparse: restored {len(repaired)} truncated tracked "
                f"file(s) from HEAD: {', '.join(repaired[:10])}"
                f"{' …' if len(repaired) > 10 else ''}",
                file=sys.stderr,
            )
        else:
            print("worktree-sparse: no truncated tracked file found to repair",
                  file=sys.stderr)
        return 1
    print(f"worktree-sparse: materialized {', '.join(names)}")
    return 0


def stray_content(root: Path, dirs: list[str], limit: int = 20) -> list[str]:
    """Files sitting inside a sparse-OMITTED tree — i.e. written by something local.

    An omitted tree should hold nothing. Anything here was produced by a tool or
    a test whose output dir was not redirected. It matters because git compares
    such a file against the committed blob and reports ` M`, so it lands in
    `git status` and in ship_loop_guard's dirty snapshot — which is the desired
    behaviour (nothing is silently committable) but reads as a mystery diff on a
    path the session never opened. Naming the files makes the cause obvious.
    """
    found: list[str] = []
    for name in dirs:
        base = root / name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                found.append(str(path.relative_to(root)))
                if len(found) >= limit:
                    return found
    return found


def clean_stray(root: Path = ROOT, force: bool = False) -> int:
    """Report — and with force, delete — content written into a sparse-OMITTED tree.

    Measured 2026-08-13, and the reason this command exists: running the test
    suite in a sparse worktree with the MM_DATA_GUARD tripwire disabled left
    `data/hk_southbound/holdings.parquet` at 45,157 bytes against the 7,295,941
    committed — because the real content was never on disk, an unredirected
    writer does not *modify* the artifact, it *replaces* it. `git diff` showed a
    7 MB truncation and `data/trial_ledger.jsonl` shorter by 1,411 lines. A
    `git add -A` there ships catastrophic data loss to main.

    Deleting a stray is safe: the committed content is in git and the path is
    sparse-omitted, so removing the file restores the tree to exactly the state
    the profile asks for. It is still report-first (worktree_gc.py's idiom) —
    a session may have written into an omitted tree on purpose.
    """
    absent = missing_dirs(root)
    stray = stray_content(root, absent, limit=10_000)
    if not stray:
        print("worktree-sparse: no stray content inside an omitted tree")
        return 0
    verb = "removing" if force else "would remove"
    print(f"worktree-sparse: {verb} {len(stray)} stray file(s) inside "
          f"{', '.join(absent)}:")
    for rel in stray[:40]:
        print(f"  {rel}")
    if len(stray) > 40:
        print(f"  … and {len(stray) - 40} more")
    if not force:
        print("worktree-sparse: re-run with --force to delete them "
              "(the committed content stays in git and is restored by `full`)")
        return 0
    for name in absent:
        shutil.rmtree(root / name, ignore_errors=True)
    _git(root, "sparse-checkout", "reapply")
    remaining = stray_content(root, missing_dirs(root))
    if remaining:
        print(f"worktree-sparse: WARNING — {len(remaining)} file(s) survived", file=sys.stderr)
        return 1
    print("worktree-sparse: omitted trees are empty again")
    return 0


def status(root: Path = ROOT) -> int:
    absent = missing_dirs(root)
    if not absent:
        print("worktree-sparse: FULL checkout — every tracked directory is present")
        return 0
    print(f"worktree-sparse: SPARSE checkout — omitting {', '.join(absent)}")
    print(f"worktree-sparse: {remedy_line(absent)}")
    print(f"worktree-sparse: one directory only, e.g. "
          f"`python3 scripts/worktree_sparse.py add {absent[0]}`")
    stray = stray_content(root, absent)
    if stray:
        print(f"worktree-sparse: WARNING — {len(stray)} file(s) exist inside an omitted "
              f"tree; a local tool or test wrote them and git will report them modified "
              f"against the committed blob: {', '.join(stray[:5])}"
              f"{' …' if len(stray) > 5 else ''}")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        return status()
    if cmd == "auto":
        return auto_profile()
    if cmd == "full":
        return disable_profile()
    if cmd == "sparse":
        return apply_profile()
    if cmd == "clean":
        return clean_stray(force="--force" in argv)
    if cmd == "add":
        names = [a for a in argv[1:] if not a.startswith("-")]
        if not names:
            print("worktree-sparse: `add` needs at least one directory", file=sys.stderr)
            return 1
        return add_dirs(names)
    print(__doc__.split("Usage:")[-1].strip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
