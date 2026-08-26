#!/usr/bin/env python3
"""Enforce Macro Dashboard's commit -> PR -> merge -> live completion contract.

SessionStart records a baseline so a shared checkout's pre-existing dirt is never
mistaken for work from this session. Stop blocks when session-created changes are
uncommitted, unpushed, unmerged, awaiting a render that has not started or that
concluded failed, or not yet present on production.

An IN-FLIGHT covering render no longer blocks: the VPS pulls main every 3 minutes
independent of Actions, so a merged commit is live in minutes regardless, the lane
only re-bakes ``.j2`` pages and the ``?v=`` stamp, house law forbids a waiting
session from cancelling or re-running it, and the nightly ``scope=all`` re-render
self-heals a failed lane within a day — so ``_stop`` defers to the shared
coalescing lane rather than holding a session the lane's ~67+ minutes (observed
sessions sat 3h46m-4h02m for a lane they may not touch).

Rendering is TWO lanes, and the gate asks whichever one owns the merge. #3834 split
the data-free public surfaces out of the heavy self-hosted ``render.yml`` into the
GitHub-hosted ``public-render.yml``, so for a public-only change a push-triggered
``render.yml`` run cannot exist and demanding one blocked forever (#3897, live and
green on the other lane). Ownership is parsed from both workflows at Stop time — see
``_render_lane_filters`` — never transcribed here, so the guard cannot drift from
the split.

ARMING ``merge-on-green`` IS NOT AN EXIT (operator ruling 2026-08-12). The label
still works and the sweeper may still perform the merge — that is a convenience,
not a transfer of ownership. A session owns its work through
commit -> push -> PR -> CI -> squash-merge -> live verification, so ``unmerged``
is satisfied by an actually-merged pull request and by nothing else. The earlier
rule released a session the moment its pull request carried the label with no
concluded red; in the field that turned an unfinished job into a reported-complete
one — a session stopped on a label while its pull request sat ``merge-blocked`` on
a red check, and the work had to be reopened by hand. What the armed pull request
still buys is a better BLOCK: ``_armed_pull_status`` names the reds the sweeper
will refuse, so the session is told what to fix instead of merely that it may not
leave. The merge-on-CONCLUDED-checks law is unchanged — a pending check is not a
pass, and an ``--admin`` merge mid-flight destroyed the pull request's own proof
run (#3867).

THE GUARD MAY NOT WEDGE THE TREE IT IS JUDGING. Its own ``git status`` used to be
run under a plain ``subprocess`` timeout, whose expiry is a SIGKILL git cannot
catch; on 2026-08-19 that left a stale ``index.lock`` in a full worktree's gitdir
and turned a slow read into a broken checkout. Timed-out git is now asked to leave
with SIGTERM before it is killed, a timed-out status is retried once on the warm
index the first pass paid for, and a lock this guard itself orphaned is swept —
but only when zero-byte, unheld, and newer than this process. See
``GIT_TERM_GRACE_SECONDS``, ``_status_output``, and ``_sweep_stale_index_lock``;
none of them relaxes the gate, and a status that cannot answer twice still blocks.

Every blocker also carries an escape ladder, because the field kept producing
UNSATISFIABLE gates: one session refused Stop 258 consecutive times on ``unmerged``
and another 245 times on ``render_failed``, and the guard took 13 patches in 17
days for such classes. See ``_block`` for the two ladders (external: 2 consecutive
or 3 cumulative; any code: 10 consecutive or 15 total; always requiring an explicit
``SHIP LOOP BLOCKED:`` evidence report). Repository rules remain the source of
truth; this hook makes them executable.

The ladders themselves were unreachable until 2026-08-04, so the brick they exist
to prevent happened to them: the release condition demanded a payload flag the
harness clears on any turn it did not itself start. Session 787452b5 filed a
correct ``SHIP LOOP BLOCKED:`` report on ``live_stale`` with both external arms
armed and was refused, because a background ``<task-notification>`` had started
that turn and reset ``stop_hook_active`` to False. Re-entrancy now also counts as
proven when this guard's own persisted ledger shows a prior block, and the report
itself is recovered from ``transcript_path`` when ``last_assistant_message`` — an
UNDOCUMENTED payload field — is absent. Both changes make the report DETECTABLE;
neither makes it optional, and no counter moved.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import fcntl


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))
from scripts import ci_semantic_proof as semantic_proof
from scripts.ci_authority_paths import AuthorityPathError, is_ci_authority_path


LIVE_HEALTH_URL = "https://mastermind-x.com/api/health"
GITHUB_API_HOST = "api.github.com"
GITHUB_API_CACHE_TTL_SECONDS = 30
GITHUB_RATE_LIMIT_RESERVE = 300
GITHUB_RATE_LIMIT_REFRESH_SECONDS = 60
# The label that lets `.github/workflows/merge-on-green.yml` PERFORM the merge.
# It is a backstop, never an exit: a session that arms it still owns the pull
# request until the merge actually lands (see the module docstring).
MERGE_ON_GREEN_LABEL = "merge-on-green"
# A CONCLUDED check outside this set is a genuine red. `neutral` and `skipped` are
# not failures, but they are not proof either (#4779). Kept as a literal here — a
# hook may not reach into the application import graph to learn it, and an empty
# fallback would read `success` itself as a red.
NON_RED_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
# The workflows whose newest CONCLUDED run on main is what main PROVES. Same pair
# `scripts/merge_on_green.py` resolves its base-inherited-red refresh from, and for
# the same reason: `ci.yml` has no `push` trigger, so a commit walk cannot answer
# (CLAUDE.md §"A `merge-blocked` backlog means main is UNPROVEN", #5037).
MAIN_PROOF_WORKFLOWS = ("ci.yml", "fences.yml")
# How far a base-side witness may sit from this head's own red and still describe
# the same base vintage. Used by both the sibling-head window and the main-proof
# staleness bound.
BASE_SIDE_WINDOW = timedelta(hours=24)
SEMANTIC_ARTIFACT_PREFIX = "ci-semantic-evidence-"
SEMANTIC_ARTIFACT_FILE = "ci-semantic-evidence.json"
SEMANTIC_RUN_LOOKBACK = 12
SEMANTIC_ARTIFACT_MAX_BYTES = 8 * 1024 * 1024
EXTERNAL_BLOCKERS = {
    "github_unreachable",
    "github_rate_limited",
    "ci_failed",
    "render_pending",
    "render_failed",
    "live_unreachable",
    "live_stale",
}
# `ci_failed_unmerged` is DELIBERATELY absent from EXTERNAL_BLOCKERS above, and the
# omission is the whole point of the code existing.
#
# `ci_failed` is external because it describes a MERGED pull request: the red is
# pinned to a frozen `refs/pull/N/merge` tree that can never recompute, so a
# session that has reported it genuinely may have no move left, and the 2-consecutive
# / 3-cumulative external ladder is the mercy exit.
#
# A red on an UNMERGED armed head is the opposite state, and it is the exact state
# this whole change exists to prevent being reported as done: the session is alive,
# the pull request is armed, the sweeper will NEVER merge a red, and the head is
# still pushable. Leaving there is what put a `merge-blocked` pull request in front
# of the operator with "worker done" attached. Routed through EXTERNAL_BLOCKERS it
# would have been the CHEAPEST state in the guard to leave — cheaper than the
# benign `unmerged` wait, which is internal and costs 10 consecutive / 15 total.
# So it is internal, and the ladder now matches the severity of the state.
CI_FAILED_UNMERGED = "ci_failed_unmerged"
# ── Ship-watcher quiescence (Sol commission #6379, 2026-08-24) ────────────────
# A "ship watcher" is one long-lived deterministic condition process: currently
# `gh run watch` or `gh pr checks --watch`. It polls INSIDE that process and exits
# only when GitHub materially changes, so unchanged observations produce zero
# task-completion/model turns. Timer transports (`sleep`, computed sleep forms,
# polling loops) are refused: even one-at-a-time timers implement the incident
# loop `timer fires -> model wakes -> unchanged check -> successor timer`.
# Foreground/background tool flags cannot bypass classification, and shell-level
# `&` detachment is refused because the reserved shell would no longer own the
# condition process whose lifetime the ledger tracks.
#
# The platform exposes NO way for a hook to enumerate or cancel Claude-native
# background tasks, so lifetime is controlled at creation. At most one condition
# process is reserved per session state. After it exits, the same HEAD + condition
# fingerprint stays consumed: process absence is not permission for an unchanged
# successor. A genuinely different head/run/check condition may reserve once.
# Nothing here kills a process or task; an unknown/foreign waiter is simply left
# alone, which is the fail-closed direction for ownership.
#
# OCCUPANCY IS BOUND TO THE REAL WATCHER LIFETIME, observed directly (Sol
# re-review 2026-08-25). Neither ledger age nor a head move frees the slot —
# the old Claude-native task may still be alive either way, and hooks cannot
# cancel it. The slot frees on exactly one kind of
# evidence: the reserved command's PROCESS is provably absent from the live
# process table, checked only after the updated command has confirmed its exact
# shell PID/start identity. PreToolUse creates a PENDING claim because sibling
# hooks decide in parallel; the command promotes it only after aggregate allow.
# A denied command therefore cannot permanently consume a condition. Within the
# grace below, a pending claim stays occupied to prevent concurrent hook calls;
# afterward it is replaceable, and its stale command cannot start GitHub because
# confirmation against the replaced marker fails. A confirmed live owner remains
# occupied until its exact PID/start identity exits. Unknown liveness refuses.
WATCHER_START_GRACE_SECONDS = 60
# Test-only knob: seconds to sleep between the locked read and write of the
# watcher acquisition, so the concurrency regression can force the interleaving
# the lock exists to prevent. Unset (production) means zero.
_WATCHER_ACQUIRE_TEST_DELAY_ENV = "SHIP_WATCHER_TEST_ACQUIRE_DELAY"
# Roots holding OTHER agent sessions' checkouts. A repository serving several
# fleets accumulates dozens of them side by side — measured 2026-07-30 in the
# primary checkout: 34 `.codex-worktrees/*` entries plus `.claire/worktrees/*`
# and `.claude/worktrees/*`. Their contents churn continuously while their owners
# work, and a session blocked on them has no move that helps: it cannot commit
# another session's checkout and cannot delete one without destroying live work.
# Keep this list closed and hardcoded rather than environment-driven — it is a
# hole in the dirty gate, so it has to be reviewable in the diff, and a lever
# that could widen it to `/` would turn the gate off.
#
# 2026-08-11: `.codex/worktrees/` was missing and had grown to 55 live checkouts,
# so a session that touched nothing blocked at Stop on another fleet's tree. The
# same list is duplicated in `.gitignore` and `config/worktree_gc.json`; a root
# added to one and not the others is invisible here (false block), untracked in
# every `git status`, and unreachable by the GC. `tests/test_agent_worktree_roots.py`
# pins the three in step — extend all three together.
AGENT_WORKTREE_ROOTS = (
    ".claude/worktrees/",
    ".claire/worktrees/",
    ".codex/worktrees/",
    ".codex-worktrees/",
    ".cursor/worktrees/",
    ".grok/worktrees/",
    ".warp/worktrees/",
)
# `subprocess.run(timeout=...)` shoots a straggler with SIGKILL, which git cannot
# catch — so the `index.lock` git's own lockfile machinery would have unlinked on
# its way out survives its owner. `git status` shrugs at a stale lock (it just
# declines to write the refreshed index), which is what makes this quiet: what
# fails is every git that WRITES the index — `add`, `commit`, `checkout`, `stash`
# — i.e. exactly the session's next move. That is the #5907 class, a guard
# timeout corrupting the checkout it was only reading, observed live 2026-08-19:
# on a FULL worktree (~5,800 files, 3 GiB of `data/`) under fleet I/O load one
# `git status` took 161s wall at 10% CPU, the 90s budget expired, the SIGKILLed
# git left a zero-byte `index.lock` in the worktree gitdir, and the guard filed
# `guard_error` against a tree it had just wedged itself. Asking before shooting
# is the fix: git installs a SIGTERM handler for exactly this case.
#
# `scripts/worktree_sparse.py` fought the same hazard from the other end (#5907,
# a killed `sparse-checkout add` leaving a truncated file plus a stale lock) and
# landed on the same ladder; this is deliberately its `TERM_GRACE_S`, same value
# and same reasoning — generous for a cleanup handler that measures well under a
# second, bounded enough that a process ignoring SIGTERM dies promptly.
GIT_TERM_GRACE_SECONDS = 10
# Two status budgets, because the first `git status` on a cold full checkout PAYS
# FOR the second: the same tree that needed 161s cold answered in 13s once its
# index and page cache were warm. One budget cannot express that — it would have
# to be the cold number, and the cold number does not fit the wall below.
#
# The wall is `.claude/settings.json`, where Stop gives this hook 540s
# (SessionStart, 30s), and the HARNESS enforces it. Budgets larger than that wall
# can never conclude: the hook is cancelled mid-flight and the Stop evaluation
# silently does not happen at all, which is a fail-OPEN — strictly worse than the
# block it was trying to file. So the numbers below are chosen so that the WHOLE
# pathological path fits, sweeps, the untracked-cache heal, and grace periods
# included, not just the two status attempts: 100 + 10 grace, + a first sweep
# (5 + 10 grace to resolve the gitdir, 5 for lsof), + 260 + 10 grace, + a second
# sweep (5 for lsof; the gitdir is cached by then), + the heal (5 + 10 to read the
# config, 20 + 10 to test the filesystem, 5 + 10 to write it) = 465. That path ends
# in a raise and a `guard_error` emit, which is all it needs after.
#
# 465 is NOT the whole story and the residual is deliberate, not slack. The costlier
# shape is the one that SUCCEEDS: a retry that answers just under its budget reaches
# ~449s (110 + 20 + 259 + the 60s heal) and then still owes the entire rest of
# `_stop` — the PR lookup, CI attribution (up to ~16 REST calls when there is a red
# to attribute), render coverage, live verification. Those are what the remaining
# ~90s is for. Sizing the wall to 465 would leave that path ~15s and cancel the hook
# mid-evaluation on exactly the trees this change is meant to serve. The same
# reasoning covers the bounded probes in `main()` ahead of `_fingerprint`
# (`_repo_root`'s `rev-parse` at the default 45s leash, run twice on the delegating
# path): sub-second in health, and not silently assumed to be free.
#
# The 2026-08-21 rebalance (60/70 of a 180s wall -> 100/150 of a 300s wall) fixed a
# tree the old split could not answer at all. The retry's whole premise is that the
# first pass leaves a warmed index for the second — but that only holds if the first
# pass is allowed to FINISH. A sparse, blobless worktree on a slow (iCloud-backed)
# volume measured a ~78s cold `status` against a ~3s warm one: at a 60s first budget
# the cold pass was SIGKILLed at ~77% done, warmed nothing, and the 70s retry then
# paid full cold cost and died too — filing `guard_error` on a tree that answers in
# 3s once warm. BOTH attempts sat under the cold cost, so the pair could never
# succeed no matter how often it ran. The first budget must therefore clear a
# realistic cold walk on its own (100 > 78), while the retry stays the longer of the
# two for the genuinely pathological tree the original incident recorded (161s cold
# / 13s warm): that one still misses the first pass and lands on the warm retry,
# exactly as designed. Raising the wall is the cost of covering both shapes; a Stop
# that takes 5 minutes on the pathological path still beats one that is killed
# mid-evaluation, because a killed Stop hook fails OPEN.
#
# The SECOND rebalance (150 -> 260, 2026-08-21) is the same arithmetic failing at a
# larger scale, and it is why `_enable_untracked_cache` exists. Worktree
# `celh-cycle-autopsy-c5adcc` of the 250-worktree `Macro Dashboard` clone measured a
# **333s** cold `status` (75,427 index entries, `core.untrackedCache` unset) against
# a 1s warm one — the incident hit the then-current 60s first budget, which bought
# ~18% of that walk before the SIGKILL, so the retry started essentially cold too
# and blew its own — `guard_error` on a tree that was clean, committed and pushed.
# A retry only 50% longer than the first attempt cannot absorb a cold walk several
# times either budget: the retry has to clear what the warm-up pass did NOT reach.
# 260 is sized on the assumption that warming is roughly linear in elapsed time —
# 100s of a 333s walk leaves ~233s, so 260 carries ~11% margin. That model is an
# ESTIMATE, not a measurement, and it is exactly why the heal below matters more
# than this number: if the walk is worse than linear the retry still dies, and a
# budget alone would leave the tree in the same loop it is in today.
#
# The budget is the fallback; the heal is the fix. `_enable_untracked_cache` turns
# that walk into a sub-second one — measured on the same clone with it enabled:
# 75,551 index entries, `UNTR` present in the index, `status` in 0.63s. Scope,
# stated precisely because the loose version of this claim is wrong: the CONFIG is
# clone-shared, so every worktree becomes ELIGIBLE at once, but the cache itself is
# an index extension and each worktree has its OWN index — so each still pays a
# single cold walk that must COMPLETE before it is cheap. This heals the clone; it
# does not retroactively heal 250 checkouts.
# `tests/test_ship_loop_guard.py` pins that arithmetic against the settings file so
# the two cannot drift apart unnoticed.
STATUS_TIMEOUT_SECONDS = 100
STATUS_RETRY_TIMEOUT_SECONDS = 260
# `git update-index --test-untracked-cache` measured 6.04/6.06/6.09s on the affected
# volume — it is dominated by deliberate sleeps that probe mtime granularity, not by
# repository size, so this is a ~3x leash on a near-constant cost rather than a
# target. It is bounded at all because an unresponsive filesystem must not be able to
# spend the retry's budget on a heal that is only ever an optimisation.
UNTRACKED_CACHE_TEST_TIMEOUT_SECONDS = 20
# Metadata-only probes (`rev-parse`, `lsof`) that must never become the reason
# the wall above is missed. Both are sub-second in health; this is the leash for
# the pathological case, not a target.
SWEEP_PROBE_TIMEOUT_SECONDS = 5
# When this process started, and therefore the floor for "a lock THIS guard's own
# killed git could have created". Anything older is somebody else's and is never
# ours to remove. Module import time, not Stop time, because a SessionStart
# fingerprint can orphan a lock just as a Stop one can.
_GUARD_STARTED_AT = time.time()
_INDEX_LOCK_CACHE: dict[str, Path | None] = {}
# Whether `_enable_untracked_cache` has already run in this process. Its answer
# cannot change mid-invocation, and its filesystem test costs ~6s to re-learn.
_UNTRACKED_CACHE_HEAL_TRIED = False


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False))


def _capture(
    root: Path, args: tuple[str, ...], timeout: int
) -> subprocess.CompletedProcess[str]:
    """Run ``args`` in ``root``, escalating SIGTERM -> SIGKILL on a timeout.

    Only the escalation distinguishes this from ``subprocess.run(timeout=...)``:
    the same ``TimeoutExpired`` is raised with the same ``cmd``/``timeout``, and
    the completed process carries the same fields, so no caller can tell the two
    apart — except by the state of the worktree afterwards, which is the whole
    point (see ``GIT_TERM_GRACE_SECONDS``). A child that ignores SIGTERM is still
    killed, so this can never hang past ``timeout + GIT_TERM_GRACE_SECONDS``.

    The sibling ladder is ``_run_git_timed`` in ``scripts/worktree_sparse.py``.
    Deliberately NOT written as ``with subprocess.Popen(...)``: that context
    manager's exit waits on the child unconditionally, so an unexpected failure
    mid-``communicate`` would hang the guard on a process nobody has signalled.
    """
    proc = subprocess.Popen(
        args,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        proc.terminate()  # SIGTERM — lets git's own cleanup handlers run
        try:
            proc.communicate(timeout=GIT_TERM_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()  # last resort; `_sweep_stale_index_lock` is its backstop
            proc.communicate()
        raise expired
    except BaseException:  # noqa: BLE001 — always reap, even on an unexpected exit
        # `subprocess.run` reaps on BaseException too, and this claims to be
        # indistinguishable from it. Narrowing to Exception would leak a live git
        # on a KeyboardInterrupt or a SystemExit mid-read.
        proc.kill()
        proc.communicate()
        raise
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


def _run(root: Path, *args: str, timeout: int = 45) -> str:
    proc = _capture(root, args, timeout)
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail[:500]}")
    return proc.stdout.strip()


def _run_raw(root: Path, *args: str, timeout: int = 45) -> str:
    """Run git while preserving porcelain's leading status column."""
    proc = _capture(root, args, timeout)
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail[:500]}")
    return proc.stdout


def _worktree_index_lock(root: Path) -> Path | None:
    """``index.lock`` for THIS worktree — never the clone's shared one.

    A linked worktree keeps its own index under ``<clone>/.git/worktrees/<name>/``,
    so ``--git-common-dir`` (what ``_git_common_dir`` asks, for a different
    question) would point every session in the clone at the PRIMARY checkout's
    lock file — a file this guard must never touch. ``--absolute-git-dir`` is the
    per-worktree answer, and is the same path the killed git wrote to. Same
    resolution ``index_lock_path`` in ``scripts/worktree_sparse.py`` makes, and
    the same None-on-unreadable contract.

    Cached per root, including the failure: the second sweep runs on the far side
    of a second blown budget, and re-paying a probe there is how the pathological
    path would overrun the wall the budgets above are sized against.
    """
    key = str(root)
    if key in _INDEX_LOCK_CACHE:
        return _INDEX_LOCK_CACHE[key]
    try:
        found = _run(
            root,
            "git",
            "rev-parse",
            "--absolute-git-dir",
            timeout=SWEEP_PROBE_TIMEOUT_SECONDS,
        )
    except Exception:
        found = ""
    lock = Path(found) / "index.lock" if found else None
    _INDEX_LOCK_CACHE[key] = lock
    return lock


def _lock_is_held(lock: Path) -> bool:
    """Whether any process still holds ``lock`` open — UNKNOWN counts as held.

    ``lsof`` exits 1 both for "nobody has it open" and for its own errors, so the
    exit code alone cannot answer this: a malformed invocation would read as proof
    that a live git's lock is free. Measured (lsof 4.91, macOS), the three cases
    separate cleanly on the streams instead — unheld: rc 1, both empty; held:
    rc 0, stdout listing the holder; error (bad option, unreadable path): rc 1,
    stdout empty, DIAGNOSTIC ON STDERR. So "unheld" requires all three of rc 1,
    no stdout, and no stderr. ``-w`` suppresses the mount-scan warnings that would
    otherwise put noise on stderr and cost a healthy machine the sweep.

    Everything else is held: a missing ``lsof``, a hang, any other exit code.
    """
    try:
        proc = subprocess.run(
            ("lsof", "-w", "--", str(lock)),
            capture_output=True,
            text=True,
            timeout=SWEEP_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception:
        return True
    quiet = not proc.stdout.strip() and not proc.stderr.strip()
    return not (proc.returncode == 1 and quiet)


def _sweep_stale_index_lock(root: Path) -> Path | None:
    """Remove an ``index.lock`` this guard's OWN killed git left behind.

    Called only after a git of ours timed out, and then only for a lock that is
    all three of: zero-byte (git had not yet written a replacement index into it),
    unheld (nothing is mid-write), and created after this process started (so it
    cannot predate us, and cannot be the operator's or a sibling session's).

    Every condition fails CLOSED — an unresolvable gitdir, an unreadable stat, an
    ``lsof`` that cannot be trusted — because the two errors are not symmetric: a
    lock left behind is loud and fixable with one `rm`, while a lock deleted out
    from under a live git is silent index corruption in a tree somebody is using.

    The sibling ``refuse_if_locked`` in ``scripts/worktree_sparse.py`` refuses on
    ANY lock and deletes none, which is right for it: it is about to start a heavy
    write and cannot know who else is in the tree. This one deletes, because it is
    scoped to the lock its OWN kill just made — that provenance is what the three
    conditions establish, and without all three it declines exactly like the
    sibling does.
    """
    lock = _worktree_index_lock(root)
    if lock is None:
        return None
    try:
        if lock.is_symlink() or not lock.is_file():
            return None
        info = lock.stat()
    except OSError:
        return None
    if info.st_size:
        return None
    created = getattr(info, "st_birthtime", info.st_ctime)
    if created <= _GUARD_STARTED_AT:
        return None
    if _lock_is_held(lock):
        return None
    try:
        lock.unlink()
    except OSError:
        return None
    return lock


def _repo_root(payload: dict[str, Any]) -> Path | None:
    # Prefer the session's explicit cwd over an inherited primary-checkout
    # CLAUDE_PROJECT_DIR. Settings.json launches this file from
    # $CLAUDE_PROJECT_DIR, so the environment path is the hook *source*, not
    # the tree being evaluated (#5756/#5757 class: stale primary logic against
    # a current worktree).
    candidates = [
        payload.get("cwd"),
        os.getcwd(),
        os.environ.get("CLAUDE_PROJECT_DIR"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            root = Path(candidate).resolve()
            found = _run(root, "git", "rev-parse", "--show-toplevel")
            return Path(found)
        except Exception:
            continue
    return None


def _state_path(root: Path, payload: dict[str, Any]) -> Path:
    session = re.sub(r"[^A-Za-z0-9_.-]", "_", str(payload.get("session_id") or "default"))
    repo_key = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    temp_root = Path(tempfile.gettempdir())
    root_fd = _private_directory_fd(
        temp_root, create=False, allow_root_sticky=True
    )
    ledger_fd = -1
    directory_fd = -1
    try:
        ledger_fd = _private_child_directory_fd(
            root_fd, "macro-claude-ship-sessions", create=True
        )
        directory_fd = _private_child_directory_fd(ledger_fd, repo_key, create=True)
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)
        if ledger_fd >= 0:
            os.close(ledger_fd)
        os.close(root_fd)
    directory = temp_root / "macro-claude-ship-sessions" / repo_key
    return directory / f"{session}.json"


def _entry_digest(path: Path) -> str:
    """Describe one status entry by CONTENT, never by metadata that drifts.

    The directory branch is the load-bearing one. `--untracked-files=all` stops
    at a nested repository rather than recursing into it, and every agent
    worktree carries a `.git` file, so git reports each one as a single
    untracked DIRECTORY entry (`?? .codex-worktrees/foo/`). Any stat-derived
    fingerprint of that entry — `st_mtime_ns` above all — changes whenever the
    owning session touches an immediate child, so the entry flips to "touched"
    no matter what the session being judged does. Directories therefore
    fingerprint on presence alone: git already declined to look inside, and
    whether the directory is dirty is a question about its own repository.

    Presence still has to be distinguishable from absence, which is why this
    returns "dir" rather than reusing "missing". Conflating the two would let a
    vanished path and a present directory compare equal.
    """
    try:
        if path.is_symlink():
            return "symlink:" + os.readlink(path)
        if path.is_dir():
            return "dir"
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
    except OSError:
        pass
    return "missing"


def _is_agent_worktree_path(path: str, status: str) -> bool:
    """Whether this entry belongs to another agent session's checkout.

    Fail-CLOSED on two axes. Only UNTRACKED entries qualify: these roots are
    ignored by construction, so anything git tracks under one is real
    repository content and keeps gating normally. And the match is anchored at
    the repository root — porcelain paths are always root-relative, with no
    leading `./` — so a nested `docs/.codex-worktrees/` deeper in the tree is
    not excused by a root named the same.
    """
    if status.strip() != "??":
        return False
    return any(path.startswith(root) for root in AGENT_WORKTREE_ROOTS)


# Exactly what `git update-index --test-untracked-cache` builds inside its scratch
# directory, measured across kill timings t=1..5s on git 2.46.1: a 6-character
# mkdtemp suffix, and a subset of these three entries and nothing else. Pinned as
# data because `_remove_mtime_test_scratch` refuses anything that does not match —
# a future git that writes something else must be left alone, not guessed at.
_MTIME_TEST_GLOB = "mtime-test-??????"
_MTIME_TEST_ENTRIES = frozenset({"newfile", "new-dir", "new-dir/new"})


def _mtime_test_scratches(root: Path) -> set[Path]:
    """Scratch directories matching git's mtime-test glob, at the worktree root."""
    try:
        return set(root.glob(_MTIME_TEST_GLOB))
    except OSError:
        return set()


def _remove_mtime_test_scratch(root: Path, preexisting: set[Path]) -> None:
    """Delete the scratch directory a KILLED `--test-untracked-cache` leaves behind.

    Measured on git 2.46.1: the mtime test builds `mtime-test-XXXXXX/` in the
    process CWD — the worktree ROOT — and cleans it up itself on a normal exit, but
    a SIGTERMed or SIGKILLed git leaves it there. Left alone that directory turns
    the very next `status --untracked-files=all` into `?? mtime-test-XXXXXX/newfile`
    on a tree that is otherwise clean, so the guard would file a false `uncommitted`
    block naming a file THE GUARD ITSELF created — and `uncommitted` is an internal
    code, escapable only at 10 consecutive blocks. Worse, the obvious way out of
    that block is `git add -A && git commit`, which commits the guard's scratch.
    Trading `guard_error` on a clean tree for a false `uncommitted` on a clean tree
    is not a fix, so the heal cleans up after itself on every path.

    Deliberately narrow, because this deletes inside somebody's worktree. Only a
    directory that matches git's exact glob AT THE ROOT, is not a symlink, APPEARED
    during the call being cleaned up, and whose entire contents are a subset of the
    three entries git writes, is removed — and only ever with `unlink`/`rmdir`,
    never a recursive delete. Anything else, including any OSError along the way, is
    left exactly where it is: an unexpected `mtime-test-*` is far better reported as
    dirt than deleted on a guess.

    Provenance is a set difference against the directories that existed before the
    call, NOT a birthtime comparison. A timestamp test has to assume the filesystem's
    creation clock and `time.time()` agree closely enough to order two events
    milliseconds apart; the set difference just asks whether the directory is new,
    which is the actual question and cannot be lost to clock granularity or skew.
    A sibling session's concurrent mtime test is therefore also safe: its scratch
    either predates our snapshot (excluded) or, if it appears alongside ours, is
    removed only once git has left it in the exact inert shape below.
    """
    for scratch in sorted(_mtime_test_scratches(root) - preexisting):
        try:
            if scratch.is_symlink() or not scratch.is_dir():
                continue
            found = [p for p in scratch.rglob("*")]
            names = {p.relative_to(scratch).as_posix() for p in found}
            if not names <= _MTIME_TEST_ENTRIES:
                continue
            if any(p.is_symlink() for p in found):
                continue
            for path in sorted(found, key=lambda p: len(p.parts), reverse=True):
                path.rmdir() if path.is_dir() else path.unlink()
            scratch.rmdir()
        except OSError:
            continue


def _enable_untracked_cache(root: Path) -> bool:
    """Turn on git's untracked cache after a status timeout, so the NEXT one is cheap.

    This is the actual repair for the 2026-08-21 incident; the retry budget is only
    the fallback that lets THIS invocation still answer. A `status
    --untracked-files=all` on a cold cache re-walks every directory in the worktree,
    which on the affected clone cost 333s; the untracked cache makes git reuse the
    previous walk per directory, keyed on the directory's mtime, and the same clone
    then answered in 0.63s. Enabling it converts a tree that cannot be read into one
    that is read for free, permanently and for every worktree of the clone — a
    linked worktree's unscoped `git config` write lands in the clone's SHARED
    config, which is the right scope precisely because the next session gets a
    healed tree without ever paying this path. That holds even though this clone
    runs `extensions.worktreeConfig=true`: only an explicit `--worktree` writes the
    per-worktree file, while `--get` still reads it, so a worktree-scoped value
    would be seen and respected by the refusal below rather than silently reset.

    The cache itself lives in each worktree's own index (the `UNTR` extension) and
    is written by the first walk that COMPLETES there, so the config write is the
    durable half and each worktree populates its own on first success.

    Racing sessions are safe: `git config` takes `config.lock` and the losers exit
    non-zero with `could not lock config file` (measured, 20 concurrent writers —
    one winner, valid config, no duplicate keys), which this reads as "not ours to
    claim" and drops. `--test-untracked-cache` never touches the index (measured:
    identical index hash across it), so it cannot collide with a sibling's git.

    Three refusals, all fail-SAFE, because a wrong "yes" here is the only way this
    function could weaken the gate:

    * An already-configured value is never overwritten, in either direction. An
      operator (or a previous heal) who set `false` decided that deliberately, and
      an unreadable/odd exit status is not evidence of anything — only a clean rc 1,
      git's specific "this key is unset", is taken as permission to write.
    * `--test-untracked-cache` must pass FIRST. The cache trusts directory mtimes,
      so on a filesystem that does not update them reliably git would report a
      directory as unchanged and MISS untracked files in it. That is a fail-OPEN in
      the dirty check this whole hook exists to make — a session's new files would
      simply not appear. Skipping the test to save its ~6s would trade a slow honest
      answer for a fast dishonest one, so it is never skipped.
    * Any exception at all leaves the cache alone. The heal is an optimisation on
      the way to a retry that has its own budget; it must never become the reason
      the retry does not happen.

    Attempted at most once per process: a filesystem that fails the test would
    otherwise re-pay those ~6s on every call, and the result cannot change mid-run.
    """
    global _UNTRACKED_CACHE_HEAL_TRIED
    if _UNTRACKED_CACHE_HEAL_TRIED:
        return False
    _UNTRACKED_CACHE_HEAL_TRIED = True
    try:
        configured = _capture(
            root,
            ("git", "config", "--get", "core.untrackedCache"),
            SWEEP_PROBE_TIMEOUT_SECONDS,
        )
        # rc 0 -> already set (leave it); rc 1 -> unset (ours to set); anything
        # else is an error we decline to interpret.
        if configured.returncode != 1:
            return False
        # The mtime test holds `index.lock` for its whole ~6s run and writes a
        # scratch directory into the worktree root, so a killed one leaves BOTH
        # behind. Clean up after it on every path — success, non-zero, or timeout.
        preexisting = _mtime_test_scratches(root)
        try:
            tested = _capture(
                root,
                ("git", "update-index", "--test-untracked-cache"),
                UNTRACKED_CACHE_TEST_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            _sweep_stale_index_lock(root)
            raise
        finally:
            _remove_mtime_test_scratch(root, preexisting)
        if tested.returncode != 0:
            return False
        written = _capture(
            root,
            ("git", "config", "core.untrackedCache", "true"),
            SWEEP_PROBE_TIMEOUT_SECONDS,
        )
        return written.returncode == 0
    except Exception:  # noqa: BLE001 — a failed optimisation must never block the retry
        return False


def _status_output(root: Path) -> str:
    """`git status --porcelain`, retried ONCE because the first run warms the index.

    The retry is not optimism, it is the measured shape of the failure: the
    2026-08-19 tree that blew a 90s budget at 161s cold answered the very next
    invocation in 13s, because the first pass had already paid the cold-cache
    cost for the second. Failing on the first timeout threw that warm-up away and
    reported `guard_error` on a tree that was one cheap re-run from answering.

    Both timeout paths sweep, because a lock this guard orphaned outlives the
    process that made it: once before the retry, so the retry does not trip over
    our own wreckage, and once more before giving up, so the NEXT invocation
    starts from a tree this one did not wedge.

    A first attempt that timed out also triggers `_enable_untracked_cache`, which
    is the difference between a tree that keeps timing out and one that stops: a
    blown first budget is the only evidence this hook ever gets that a checkout is
    too slow to read, and it is a good one — a healthy tree never reaches that
    line, and so never pays the heal's ~6s filesystem test.

    The heal runs AFTER the status has been read, never between the two attempts,
    and that ordering is load-bearing rather than cosmetic. Its `--test-untracked-
    cache` writes a scratch directory into the worktree root; a killed one leaves it
    there (measured), and a `status` run afterwards would report it as untracked —
    letting the guard file a false `uncommitted` block naming a file the guard
    itself created. `_remove_mtime_test_scratch` is the direct repair for that, and
    reading status first means even a cleanup that fails cannot contaminate THIS
    invocation's answer. Nothing is lost by waiting: the cache is populated by the
    first walk that COMPLETES, so it could never have rescued a retry that follows a
    killed attempt anyway — the retry's own budget has to be able to finish the walk
    alone, and the heal is for every invocation after this one.

    Fail-closed is unchanged. A status that times out twice re-raises, `main`
    files `guard_error`, and Stop blocks — the retry buys a second chance to
    ANSWER, never permission to skip the question, and the heal changes only how
    long the answer takes, never whether one is required.
    """
    args = ("git", "status", "--porcelain=v1", "--untracked-files=all")
    try:
        return _run_raw(root, *args, timeout=STATUS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _sweep_stale_index_lock(root)
    try:
        output = _run_raw(root, *args, timeout=STATUS_RETRY_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _sweep_stale_index_lock(root)
        _enable_untracked_cache(root)
        raise
    _enable_untracked_cache(root)
    return output


def _fingerprint(root: Path) -> dict[str, str]:
    """Return path -> status/content hash for the current dirty set."""
    output = _status_output(root)
    result: dict[str, str] = {}
    for line in output.splitlines():
        if len(line) < 4:
            continue
        status, display_path = line[:2], line[3:]
        # For rename records, the destination is the content-bearing path.
        path = display_path.rsplit(" -> ", 1)[-1].strip('"')
        if _is_agent_worktree_path(path, status):
            continue
        result[path] = f"{status}:{_entry_digest(root / path)}"
    return result


def _changed_since_baseline(baseline: dict[str, str], now: dict[str, str]) -> list[str]:
    """Paths git STILL calls dirty whose state differs from the session baseline.

    Iterating `now` rather than the union with `baseline` is the whole point.
    Under the union, a path that LEAVES the status output — because it became
    gitignored or excluded mid-session, because it was committed, or because
    another session removed its own checkout — compared `<fingerprint>` against
    `None` and was reported as work this session had failed to ship. Measured
    2026-07-30: adding `.codex-worktrees/` to `.git/info/exclude` mid-session
    turned 34 already-baselined directories into outstanding changes, so the act
    of correctly ignoring them CAUSED the block, and no session-side action
    could clear it.

    Git's own status codes stay the authority for the inverse case, which is why
    this reads `now` instead of testing set membership by hand: a tracked file
    the session DELETED is still reported, as ` D`, so it stays in `now` with a
    changed value and still blocks. Only paths git no longer considers dirty at
    all drop out — and a path that is clean by git's account is, by definition,
    not uncommitted work.
    """
    return sorted(path for path, value in now.items() if baseline.get(path) != value)


def _shipped_identical_untracked(
    root: Path, now: dict[str, str], dirty: list[str]
) -> set[str]:
    """Untracked paths whose bytes already sit at the same path on origin/main.

    The 2026-08-20 class: the primary checkout sat on a detached 2026-07-14
    HEAD while a repair session restored the WorktreeCreate hook bytes with
    `git show origin/main:<path> > <path>` — the documented zero-git-state
    repair for stale hook bytes. Those files are tracked on origin/main and
    byte-identical to it, but the old HEAD predates them, so `git status`
    reports `??` and every session evaluating that tree blocked at Stop on
    content with nothing left to ship: a commit would add nothing that main
    does not already have, and the escape ladder was the only exit.

    Scope is deliberately narrow and fail-closed:
    - `??` entries only. A TRACKED file modified to match origin/main still
      blocks — its diff against HEAD is real checkout state, and excusing it
      would also excuse an un-pulled revert riding in the working tree.
    - Regular files only. The fingerprint digest is a content hash for files;
      `dir`, `symlink:*`, and `missing` entries never qualify (a symlink's
      blob is its target STRING, which `git hash-object` of the followed file
      would misjudge).
    - Identity is blob-OID equality at the SAME path: one `git ls-tree` for
      origin/main's OIDs and one `git hash-object` for the working copies.
      Neither reads blob content, so a blobless clone answers without a
      promisor fetch.
    - Any failure — no origin/main ref, a git error, a racing edit — excludes
      nothing, and the path keeps blocking exactly as before.

    A stale origin/main ref is safe on both edges: matching a stale blob
    still proves the bytes shipped on SOME main commit, and failing to match
    keeps the block (the pre-existing behavior).
    """
    candidates = []
    for entry in dirty:
        value = now.get(entry, "")
        if not value.startswith("??:"):
            continue
        digest = value[3:]
        if digest in ("dir", "missing") or digest.startswith("symlink:"):
            continue
        candidates.append(entry)
    if not candidates:
        return set()
    try:
        listing = _run_raw(
            root,
            "git",
            "ls-tree",
            "-z",
            "refs/remotes/origin/main",
            "--",
            *candidates,
        )
        shipped_oid: dict[str, str] = {}
        for record in listing.split("\0"):
            if not record:
                continue
            meta, _, name = record.partition("\t")
            fields = meta.split()
            if len(fields) != 3:
                continue
            mode, object_type, oid = fields
            # Blobs only, in the two regular-file modes. 120000 (symlink) and
            # 160000 (gitlink) records name different object semantics, and a
            # tree here means the untracked path collides with a shipped
            # DIRECTORY — never equivalence.
            if object_type != "blob" or mode not in ("100644", "100755"):
                continue
            shipped_oid[name] = oid
        matched = [entry for entry in candidates if entry in shipped_oid]
        if not matched:
            return set()
        hashed = _run_raw(root, "git", "hash-object", "--", *matched, timeout=90)
        oids = hashed.split()
        if len(oids) != len(matched):
            return set()
        return {
            entry
            for entry, oid in zip(matched, oids)
            if shipped_oid[entry] == oid
        }
    except Exception:
        return set()


_OPEN_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_OPEN_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_OPEN_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def _private_directory_fd(
    directory: Path, *, create: bool, allow_root_sticky: bool = False
) -> int:
    """Open one trusted directory without following its final name.

    Ledger directories are always effective-UID-owned and private. The one
    exception is the operating system's outer temp root: a root-owned sticky,
    world-writable/searchable directory such as ``/tmp`` or ``/private/tmp``.
    Its children still pass through ``_private_child_directory_fd`` and must be
    effective-UID-owned 0700 directories.
    """
    if create:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_RDONLY | _OPEN_CLOEXEC | _OPEN_DIRECTORY | _OPEN_NOFOLLOW
    descriptor = os.open(directory, flags)
    try:
        info = os.fstat(descriptor)
        owned = info.st_uid == os.geteuid()
        root_sticky = (
            allow_root_sticky
            and not create
            and info.st_uid == 0
            and bool(info.st_mode & stat.S_ISVTX)
            and bool(info.st_mode & stat.S_IWOTH)
            and bool(info.st_mode & stat.S_IXOTH)
        )
        if not stat.S_ISDIR(info.st_mode) or not (owned or root_sticky):
            raise OSError(
                "ship ledger directory is neither user-owned nor a trusted "
                "root-owned sticky temp root"
            )
        if create:
            os.fchmod(descriptor, 0o700)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _private_child_directory_fd(parent_fd: int, name: str, *, create: bool) -> int:
    """Open one private child directory relative to a verified parent.

    Component-at-a-time ``dir_fd`` traversal is load-bearing: applying
    ``O_NOFOLLOW`` only to the final repo-key directory still follows a planted
    ``macro-claude-ship-sessions`` ancestor symlink before reaching it.
    """
    if not name or name in {".", ".."} or "/" in name:
        raise OSError("unsafe ship ledger directory component")
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
    descriptor = os.open(
        name,
        os.O_RDONLY | _OPEN_CLOEXEC | _OPEN_DIRECTORY | _OPEN_NOFOLLOW,
        dir_fd=parent_fd,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise OSError("ship ledger directory is not a user-owned directory")
        if create:
            os.fchmod(descriptor, 0o700)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _validate_owned_regular(descriptor: int, label: str) -> None:
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise OSError(f"{label} is not a user-owned regular file")


def _validate_destination(directory_fd: int, name: str) -> None:
    try:
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise OSError("ship ledger destination is not a user-owned regular file")


def _load_ledger(path: Path, *, allow_missing: bool) -> dict[str, Any] | None:
    """Load one ledger while distinguishing absence from unsafe existing state."""
    directory_fd = -1
    descriptor = -1
    try:
        directory_fd = _private_directory_fd(path.parent, create=False)
        try:
            descriptor = os.open(
                path.name,
                os.O_RDONLY | _OPEN_CLOEXEC | _OPEN_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            if allow_missing:
                return None
            raise OSError("ship ledger is missing")
        _validate_owned_regular(descriptor, "ship ledger")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            try:
                value = json.load(handle)
            except json.JSONDecodeError as exc:
                raise OSError("ship ledger is malformed") from exc
        if not isinstance(value, dict):
            raise OSError("ship ledger root is not an object")
        return value
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_fd >= 0:
            os.close(directory_fd)


def _load(path: Path) -> dict[str, Any] | None:
    """Best-effort JSON read for non-authoritative caches and diagnostics."""
    try:
        return _load_ledger(path, allow_missing=True)
    except OSError:
        return None


def _atomic_save_json(path: Path, value: Any) -> None:
    """Atomically replace JSON through an unguessable, no-follow temp file."""
    directory_fd = _private_directory_fd(path.parent, create=True)
    temp_name = ""
    descriptor = -1
    try:
        _validate_destination(directory_fd, path.name)
        for _attempt in range(16):
            temp_name = f".{path.name}.{os.getpid()}.{secrets.token_hex(12)}.tmp"
            try:
                descriptor = os.open(
                    temp_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | _OPEN_CLOEXEC
                    | _OPEN_NOFOLLOW,
                    0o600,
                    dir_fd=directory_fd,
                )
                break
            except FileExistsError:
                continue
        else:
            raise OSError("could not create a unique ship-ledger temp file")
        _validate_owned_regular(descriptor, "ship ledger temp")
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temp_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temp_name = ""
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temp_name:
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


def _save(path: Path, state: dict[str, Any]) -> None:
    _atomic_save_json(path, state)


def _ledger_lock_path(path: Path) -> Path:
    """The one lock for every read-modify-write of a session ledger.

    The historical suffix is retained so an already-running hook from the
    immediately preceding revision contends on the same file during rollout.
    This remains part of the existing per-session ledger, not another store.
    """
    return path.with_suffix(".watcher.lock")


def _update_ledger(path: Path, mutate: Any, *, initial: dict[str, Any] | None = None) -> Any:
    """Apply one coherent ledger transaction and return ``mutate``'s result.

    Every writer re-loads INSIDE the same lock used by watcher admission. The
    optional ``initial`` is used only when the ledger genuinely disappeared;
    it cannot replace a newer on-disk state and therefore cannot erase a
    concurrent watcher reservation.
    """
    with _file_lock(_ledger_lock_path(path)):
        latest = _load_ledger(path, allow_missing=True)
        if not isinstance(latest, dict):
            if initial is None:
                return None
            latest = dict(initial)
        result = mutate(latest)
        _save(path, latest)
        return result


def _proof(state: dict[str, Any], gate: str, key: str) -> Any | None:
    """Return a monotonic ship-gate proof only when its identity still matches."""
    entry = (state.get("ship_proofs") or {}).get(gate) or {}
    if str(entry.get("key") or "") != key:
        return None
    return entry.get("value")


def _remember_proof(
    path: Path,
    state: dict[str, Any],
    gate: str,
    key: str,
    value: Any,
) -> None:
    """Persist completed gates so later Stop turns do not poll GitHub again."""
    def remember(latest: dict[str, Any]) -> dict[str, Any]:
        proofs = latest.setdefault("ship_proofs", {})
        proofs[gate] = {"key": key, "value": value}
        return dict(latest)

    latest = _update_ledger(path, remember, initial=state)
    if isinstance(latest, dict):
        # The current Stop continues from the same authoritative snapshot the
        # transaction persisted; later proof lookups must not use stale state.
        state.clear()
        state.update(latest)


def _external_exit_key(code: str, head: str, reason: str) -> str:
    """Frozen-state identity for an EXTERNAL block's remembered ladder exit.

    External blockers describe machinery the session does not own, so once the
    full escape ladder has ratified an exit (explicit ``SHIP LOOP BLOCKED:``
    report on a re-entrant Stop, counters armed), a later wake — typically a
    leftover background timer's `<task-notification>` turn — re-derives the
    SAME state and must pass silently instead of re-blocking a session that
    already lawfully left (Sol commission #6379, incident PR #6377). The key
    binds code, the exact local HEAD, and a digest of the block evidence:

    - HEAD is load-bearing, not decoration. A generic external reason (an
      unreachable-API exception text, say) can recur verbatim for NEW work; a
      session that escaped, then committed and pushed something new, must not
      have its new head's outage excused by the old head's ratified report.
    - The reason digest keeps the memory state-specific exactly as it does
      for the merged-head ``ci_failed`` key: a materially changed blocker
      (other lane, other run, other error) mints a different key and gates
      fresh. The converse is equally true and intended: a blocker whose
      message is byte-stable for its whole window — a rate-limit reason
      carrying one fixed reset epoch, a render lane that never started —
      stays silent for that window, which is precisely one report per frozen
      state. The digest narrows what one report can cover; it does not
      promise that every underlying retry re-blocks.

    Internal codes NEVER mint a key here: ``unmerged``/``ci_failed_unmerged``/
    ``unpushed``/``uncommitted``/``unsafe_branch``/``guard_error`` remain owned
    repair states with only the 10/15 loop breaker, unchanged (Journey C).
    """
    if code not in EXTERNAL_BLOCKERS:
        return ""
    digest = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:12]
    return f"{code}:{head}:{digest}"


def _python_executes_sleep(source: str) -> bool | None:
    """Classify actual Python sleep calls without matching inert source text."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    modules: dict[str, str] = {}
    imported: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imported[alias.asname or alias.name] = (node.module, alias.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and imported.get(func.id) in {
            ("time", "sleep"),
            ("asyncio", "sleep"),
        }:
            return True
        if not isinstance(func, ast.Attribute) or func.attr != "sleep":
            continue
        owner = func.value
        if isinstance(owner, ast.Name) and modules.get(owner.id) in {"time", "asyncio"}:
            return True
        if (
            isinstance(owner, ast.Call)
            and isinstance(owner.func, ast.Name)
            and owner.func.id == "__import__"
            and owner.args
            and isinstance(owner.args[0], ast.Constant)
            and owner.args[0].value in {"time", "asyncio"}
        ):
            return True
    return False


def _heredoc_delimiters(line: str) -> list[tuple[str, bool]]:
    """Return executable here-document declarations on one shell header.

    The scanner observes shell quotes so inert text such as ``echo '<<EOF'``
    cannot hide later executable lines. Only the delimiter declaration is
    inspected here; the header itself stays in the classifier, preserving an
    executable trailer such as ``cat <<EOF; sleep 1``.
    """
    found: list[tuple[str, bool]] = []
    index = 0
    quote = ""
    escaped = False
    while index < len(line):
        char = line[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote:
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if not line.startswith("<<", index) or line.startswith("<<<", index):
            index += 1
            continue
        cursor = index + 2
        strip_tabs = cursor < len(line) and line[cursor] == "-"
        if strip_tabs:
            cursor += 1
        while cursor < len(line) and line[cursor] in " \t":
            cursor += 1
        if cursor >= len(line):
            index += 2
            continue
        delimiter_quote = line[cursor] if line[cursor] in {"'", '"'} else ""
        if delimiter_quote:
            end = line.find(delimiter_quote, cursor + 1)
            if end < 0:
                index += 2
                continue
            delimiter = line[cursor + 1 : end]
            cursor = end + 1
        else:
            end = cursor
            while end < len(line) and line[end] not in " \t\r\n;&|<>()":
                end += 1
            delimiter = line[cursor:end]
            cursor = end
        if delimiter:
            found.append((delimiter, strip_tabs))
        index = max(cursor, index + 2)
    return found


def _shell_heredoc_parts(command: str) -> tuple[str, list[tuple[str, str, int]]]:
    """Split shell headers from heredoc bodies without deciding body semantics.

    Each document retains its header and declaration ordinal. The caller can
    therefore keep ``cat``/``printf`` bodies as data while classifying stdin to
    ``sh``/``bash``/``python`` as executable code.
    """
    pending: list[dict[str, Any]] = []
    documents: list[tuple[str, str, int]] = []
    kept: list[str] = []
    for line in command.splitlines(keepends=True):
        if pending:
            current = pending[0]
            delimiter = str(current["delimiter"])
            strip_tabs = bool(current["strip_tabs"])
            candidate = line.rstrip("\r\n")
            if strip_tabs:
                candidate = candidate.lstrip("\t")
            if candidate == delimiter:
                documents.append(
                    (
                        str(current["header"]),
                        "".join(current["body"]),
                        int(current["ordinal"]),
                    )
                )
                pending.pop(0)
            else:
                current["body"].append(line)
            # Preserve a command boundary without exposing body text as code.
            if line.endswith(("\n", "\r")):
                kept.append("\n")
            continue
        kept.append(line)
        for ordinal, (delimiter, strip_tabs) in enumerate(_heredoc_delimiters(line)):
            pending.append(
                {
                    "delimiter": delimiter,
                    "strip_tabs": strip_tabs,
                    "header": line,
                    "ordinal": ordinal,
                    "body": [],
                }
            )
    for current in pending:
        documents.append(
            (
                str(current["header"]),
                "".join(current["body"]),
                int(current["ordinal"]),
            )
        )
    return "".join(kept), documents


def _strip_shell_heredoc_bodies(command: str) -> str:
    """Remove here-document bodies while retaining every executable header."""
    return _shell_heredoc_parts(command)[0]


def _heredoc_interpreter(header: str, ordinal: int) -> str | None:
    """Return the interpreter consuming one heredoc, otherwise DATA/unknown."""
    parsed = _shell_segments(header)
    if parsed is None:
        return None
    candidates: list[list[str]] = []
    for segment in parsed[0]:
        if any(word.startswith("<<") and not word.startswith("<<<") for word in segment):
            candidates.append(list(segment))
    if ordinal >= len(candidates):
        return None
    words = candidates[ordinal]
    assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    while words and (assignment.match(words[0]) or words[0] in {"command", "builtin"}):
        words.pop(0)
    while words and os.path.basename(words[0]).lower() in {"env", "nohup", "time"}:
        words.pop(0)
        while words and (words[0].startswith("-") or assignment.match(words[0])):
            words.pop(0)
    if not words:
        return None
    executable = os.path.basename(words.pop(0)).lower()
    arguments = [word for word in words if not word.startswith("<<")]
    if executable in {"bash", "sh", "zsh"} and "-c" not in arguments:
        return "shell"
    if re.fullmatch(r"python(?:3(?:\.\d+)?)?", executable) and "-c" not in arguments:
        return "python"
    return None


def _shell_segments(command: str) -> tuple[list[list[str]], list[str]] | None:
    """Tokenize executable shell forms while preserving command boundaries.

    Quotes are consumed by ``shlex``, so a value printed by echo/printf is an
    argument rather than executable syntax. Newlines remain punctuation so a
    second command cannot hide behind whitespace tokenization.
    """
    try:
        lexer = shlex.shlex(
            _strip_shell_heredoc_bodies(command),
            posix=True,
            punctuation_chars=";&|()\n",
        )
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[list[str]] = []
    separators: list[str] = []
    current: list[str] = []
    for token in tokens:
        if token and all(char in ";&|()\n" for char in token):
            if current:
                segments.append(current)
                current = []
            separators.append(token)
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments, separators


def _gh_wait_condition(words: list[str]) -> tuple[str | None, bool]:
    """Return one canonical GitHub wait identity and parse uncertainty.

    Repository flags are global in ``gh`` and may legally appear before or
    after the positional subcommands. Known option arity is consumed before
    selecting the run/PR subject so flag values can never become identities.
    """
    repo = "current-repo"
    stripped: list[str] = []
    index = 0
    while index < len(words):
        token = words[index]
        if token in {"-R", "--repo"}:
            if index + 1 >= len(words):
                return None, True
            repo = words[index + 1]
            index += 2
            continue
        if token.startswith("--repo="):
            repo = token.split("=", 1)[1]
            if not repo:
                return None, True
            index += 1
            continue
        stripped.append(token)
        index += 1

    lowered = [word.lower() for word in stripped]
    if lowered[:2] == ["run", "watch"]:
        boolean_flags = {"--compact", "--exit-status"}
        value_flags = {"--interval", "-i"}
        subject = ""
        index = 2
        while index < len(stripped):
            token = stripped[index]
            lower = token.lower()
            if lower in boolean_flags:
                index += 1
                continue
            if lower in value_flags:
                if index + 1 >= len(stripped):
                    return None, True
                index += 2
                continue
            if any(lower.startswith(f"{flag}=") for flag in value_flags):
                index += 1
                continue
            if lower.startswith("-"):
                return None, True
            if subject:
                return None, True
            subject = token
            index += 1
        if not subject:
            return None, True
        return f"gh-run:{repo}:{subject}", False

    if lowered[:2] == ["pr", "checks"]:
        boolean_flags = {"--fail-fast", "--required"}
        value_flags = {"--interval", "--json", "--jq", "--template"}
        subject = ""
        watch = False
        index = 2
        while index < len(stripped):
            token = stripped[index]
            lower = token.lower()
            if lower in {"--watch", "--watch=true"}:
                watch = True
                index += 1
                continue
            if lower == "--watch=false":
                index += 1
                continue
            if lower in boolean_flags:
                index += 1
                continue
            if lower in value_flags:
                if index + 1 >= len(stripped):
                    return None, True
                index += 2
                continue
            if any(lower.startswith(f"{flag}=") for flag in value_flags):
                index += 1
                continue
            if lower.startswith("-"):
                return None, True
            if subject:
                return None, True
            subject = token
            index += 1
        if not watch:
            return None, False
        return f"gh-pr-checks:{repo}:{subject or 'current-head'}", False
    return None, False


def _shell_wait_classification(
    command: str,
    *,
    depth: int = 0,
    watch_commands: list[str] | None = None,
) -> tuple[str, str] | None:
    """Return ``(admission, condition)`` for supported executed wait forms."""
    if depth > 3:
        return ("deny_uncertain", "nested-shell-wait")
    _, heredocs = _shell_heredoc_parts(command)
    heredoc_watches: list[str] = []
    heredoc_uncertain = False
    for header, body, ordinal in heredocs:
        interpreter = _heredoc_interpreter(header, ordinal)
        if interpreter == "shell":
            nested = _shell_wait_classification(
                body, depth=depth + 1, watch_commands=watch_commands
            )
            if nested is None:
                continue
            if nested[0] == "reserve_condition":
                heredoc_watches.append(nested[1])
            else:
                return nested
        elif interpreter == "python":
            python_wait = _python_executes_sleep(body)
            if python_wait is True:
                return ("deny_timer", "timer-poll")
            if python_wait is None and re.search(r"(?i)\bsleep\b", body):
                heredoc_uncertain = True
    parsed = _shell_segments(command)
    if parsed is None:
        # A malformed watcher-shaped shell command is uncertainty, not an
        # ordinary command. Avoid broad language-sleep substrings here because
        # quoted data must remain outside this gate.
        if re.search(r"(?i)\b(?:sleep|start-sleep|gh)\b", command):
            return ("deny_uncertain", "unparseable-wait")
        return None
    segments, separators = parsed
    detached = any("&" in token and token != "&&" for token in separators)
    aliases: dict[str, str] = {}
    variables: dict[str, str] = {}
    watches: list[str] = list(heredoc_watches)
    uncertain = heredoc_uncertain
    in_loop = False
    saw_loop_gh = False
    assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(.*)$", re.DOTALL)
    control = {"do", "then", "else", "elif", "if", "!", "{"}

    for original in segments:
        words = list(original)
        while words and words[0] in {"while", "until"}:
            in_loop = True
            words.pop(0)
        while words and words[0] in control:
            words.pop(0)
        if words and words[0] == "done":
            in_loop = False
            continue
        if not words:
            continue

        if words[0] == "alias":
            for definition in words[1:]:
                match = assignment.match(definition)
                if match:
                    aliases[definition.split("=", 1)[0]] = match.group(1)
            continue

        while words:
            match = assignment.match(words[0])
            if not match:
                break
            variables[words[0].split("=", 1)[0]] = match.group(1)
            words.pop(0)
        if not words:
            continue

        executable = words.pop(0)
        if executable == "$":
            # An unquoted command substitution at command position computes
            # the executable only at runtime. Quoted substitutions remain an
            # ordinary argument token and never reach this branch.
            if re.search(r"(?i)\b(?:sleep|start-sleep|gh)\b", command):
                uncertain = True
            continue
        if executable in aliases:
            try:
                words = shlex.split(aliases[executable], posix=True) + words
            except ValueError:
                uncertain = True
                continue
            if not words:
                uncertain = True
                continue
            executable = words.pop(0)

        if executable.startswith("$"):
            name = executable.lstrip("${").rstrip("}")
            assigned = variables.get(name, "")
            if assigned:
                nested_command = " ".join(
                    part for part in (assigned, shlex.join(words)) if part
                )
                nested = _shell_wait_classification(
                    nested_command,
                    depth=depth + 1,
                    watch_commands=watch_commands,
                )
                if nested is not None:
                    # Even a literal assignment is expanded by the shell into
                    # an executable/argv boundary the admission hook cannot
                    # preserve or mark. It is watcher-shaped uncertainty, not
                    # a native owner and not an ordinary command.
                    uncertain = True
                continue
            if words[:2] in (["run", "watch"], ["pr", "checks"]):
                uncertain = True
            continue

        base = os.path.basename(executable).lower()
        while base in {
            "command",
            "builtin",
            "env",
            "nohup",
            "time",
            "nice",
            "caffeinate",
            "timeout",
        }:
            if base == "env" and words[:1] in (["-S"], ["--split-string"]):
                if len(words) < 2:
                    uncertain = True
                    break
                try:
                    words = shlex.split(words[1], posix=True) + words[2:]
                except ValueError:
                    uncertain = True
                    break
            elif base == "nice":
                while words and words[0].startswith("-"):
                    option = words.pop(0)
                    if option in {"-n", "--adjustment"}:
                        if not words:
                            uncertain = True
                            break
                        words.pop(0)
                    elif option.startswith("--adjustment=") or re.fullmatch(
                        r"-[0-9]+", option
                    ):
                        continue
                    elif option == "--":
                        break
                    else:
                        uncertain = True
                        break
            elif base == "caffeinate":
                while words and words[0].startswith("-"):
                    option = words.pop(0)
                    if option in {"-t", "-w"}:
                        if not words:
                            uncertain = True
                            break
                        words.pop(0)
                    elif option == "--" or re.fullmatch(r"-[dimsu]+", option):
                        if option == "--":
                            break
                    else:
                        uncertain = True
                        break
            elif base == "timeout":
                while words and words[0].startswith("-"):
                    option = words.pop(0)
                    if option in {"-k", "--kill-after", "-s", "--signal"}:
                        if not words:
                            uncertain = True
                            break
                        words.pop(0)
                    elif (
                        option in {"--foreground", "--preserve-status", "--verbose"}
                        or option == "--"
                        or option.startswith("--kill-after=")
                        or option.startswith("--signal=")
                    ):
                        if option == "--":
                            break
                    else:
                        uncertain = True
                        break
                if not uncertain:
                    if not words:
                        uncertain = True
                    else:
                        words.pop(0)  # duration precedes the child argv
            else:
                while words and (words[0].startswith("-") or assignment.match(words[0])):
                    words.pop(0)
            if not words:
                uncertain = True
                break
            executable = words.pop(0)
            base = os.path.basename(executable).lower()
        if not base:
            continue

        if base in {"sleep", "start-sleep"}:
            return ("deny_timer", "timer-poll")

        if base == "eval":
            expanded: list[str] = []
            for word in words:
                match = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", word)
                expanded.append(variables.get(match.group(1), word) if match else word)
            nested = _shell_wait_classification(
                " ".join(expanded),
                depth=depth + 1,
                watch_commands=watch_commands,
            )
            if nested is not None:
                return nested
            continue

        if base == "exec":
            if not words:
                continue
            nested = _shell_wait_classification(
                shlex.join(words),
                depth=depth + 1,
                watch_commands=watch_commands,
            )
            if nested is None:
                continue
            if nested[0] in {"reserve_condition", "deny_detached"}:
                return ("deny_uncertain", "exec-replaces-watcher-owner")
            return nested

        if base in {"bash", "sh", "zsh"} and "-c" in words:
            index = words.index("-c")
            if index + 1 >= len(words):
                uncertain = True
            else:
                nested = _shell_wait_classification(
                    words[index + 1],
                    depth=depth + 1,
                    watch_commands=watch_commands,
                )
                if nested is not None:
                    return nested
            continue

        if base in {"pwsh", "powershell", "powershell.exe"}:
            lowered_words = [word.lower() for word in words]
            command_flags = {"-command", "--command", "-c"}
            command_indexes = [
                position
                for position, word in enumerate(lowered_words)
                if word in command_flags
            ]
            if not command_indexes:
                continue
            index = command_indexes[0]
            if index + 1 >= len(words):
                uncertain = True
                continue
            nested = _shell_wait_classification(
                " ".join(words[index + 1 :]),
                depth=depth + 1,
                watch_commands=watch_commands,
            )
            if nested is not None:
                return nested
            continue

        if re.fullmatch(r"python(?:3(?:\.\d+)?)?", base) and "-c" in words:
            index = words.index("-c")
            if index + 1 >= len(words):
                uncertain = True
                continue
            python_wait = _python_executes_sleep(words[index + 1])
            if python_wait is True:
                return ("deny_timer", "timer-poll")
            if python_wait is None and re.search(r"(?i)\bsleep\b", words[index + 1]):
                uncertain = True
            continue

        if base != "gh":
            # Unknown argv transports are ordinary Bash unless their literal
            # child argv is watcher-shaped. Data/prose commands are explicit
            # negatives; quoted prose stays one token and cannot match this
            # executable-position sequence.
            data_commands = {"cat", "echo", "printf"}
            lowered_words = [word.lower() for word in words]
            if base not in data_commands and any(
                lowered_words[index : index + 3] == ["gh", "run", "watch"]
                or (
                    lowered_words[index : index + 2] == ["gh", "pr"]
                    and "checks" in lowered_words[index + 2 : index + 4]
                )
                for index in range(len(lowered_words))
            ):
                uncertain = True
            continue
        if in_loop:
            saw_loop_gh = True
        condition, parse_uncertain = _gh_wait_condition(words)
        if parse_uncertain:
            uncertain = True
        elif condition:
            watches.append(condition)
            if watch_commands is not None:
                watch_commands.append(shlex.join(["gh", *words]))

    if saw_loop_gh:
        return ("deny_timer", "timer-poll")
    if uncertain:
        return ("deny_uncertain", "uncertain-wait")
    if not watches:
        return None
    if len(watches) != 1:
        return ("deny_uncertain", "multiple-condition-watches")
    if detached:
        return ("deny_detached", "detached-condition-watch")
    return ("reserve_condition", watches[0])


def _watcher_request(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Classify executed watcher/timer command forms, not raw substrings.

    Ordinary Bash remains fail-open. Supported native GitHub condition waits
    may reserve one owner; executed sleeps, polling loops, detached watches,
    and watcher-shaped uncertainty fail closed.
    """
    if str(payload.get("tool_name") or "") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = str(tool_input.get("command") or "")
    watch_commands: list[str] = []
    classified = _shell_wait_classification(command, watch_commands=watch_commands)
    if classified is None:
        return None
    admission, condition = classified
    identity = condition if admission == "reserve_condition" else command
    return {
        "command": command,
        "digest": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12],
        "admission": admission,
        "condition": condition,
        "executed_watch_commands": watch_commands,
    }


def _canonical_hot_watch_reason(watch: dict[str, Any]) -> str | None:
    """Consult the configured quota rule before minting a pending claim.

    Claude evaluates sibling PreToolUse hooks in parallel. Without this pure
    preflight, the quota hook can deny execution after this hook has already
    persisted an unconfirmed owner. Importing the quota hook's own helper keeps
    its threshold and denial semantics authoritative and creates no retry or
    lifecycle plane.
    """
    hook = Path(__file__).with_name("gh_quota_guard.py")
    spec = importlib.util.spec_from_file_location("_ship_loop_quota_guard", hook)
    if spec is None or spec.loader is None:
        raise OSError("canonical GitHub quota guard cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    helper = getattr(module, "hot_watch_reason", None)
    if not callable(helper):
        raise OSError("canonical GitHub quota helper is unavailable")
    commands = watch.get("executed_watch_commands")
    if not isinstance(commands, list) or not commands:
        raise OSError("executed watcher command identity is unavailable")
    for command in commands:
        reason = helper(str(command))
        if reason:
            return str(reason)
    return None


def _latched_terminal_heads(state: dict[str, Any]) -> set[str]:
    """HEAD shas this session's ledger holds a PARKED latch for.

    ONLY ``parked_latch`` (``parked:<pr>:<head>``, written by the hold wrapper
    when a lawful HOLD-FOR-SOL becomes PARKED) refuses new watchers. It is the
    one terminal latch with a clearing path — the wrapper removes it the
    moment the hold state positively changes — so a refusal here can never
    outlive the state it describes. ``ladder_exits`` entries deliberately do
    NOT refuse watchers (red-team F4, 2026-08-24): they are append-only with
    no clearing path, and a ratified exit on a TRANSIENT external blocker
    (a spent rate-limit window, say) lawfully resumes at the same head once
    the blocker lifts — a permanent "terminal" refusal there would deny the
    resumed session its one legitimate watcher. Post-exit wake QUIESCENCE is
    already owned by the exit-key memory in ``_block``, while watcher
    admission independently refuses timer transport and an unchanged
    condition successor.
    Unparseable latches contribute nothing: failing to recognise one only
    ALLOWS a watcher, never denies one.
    """
    heads: set[str] = set()
    latch = str(state.get("parked_latch") or "")
    parts = latch.split(":")
    if len(parts) == 3 and parts[0] == "parked" and parts[2]:
        heads.add(parts[2])
    return heads


def _deny_watcher(reason: str) -> None:
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def _allow_watcher(tool_input: dict[str, Any], command: str) -> None:
    updated = dict(tool_input)
    updated["command"] = command
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": updated,
            }
        }
    )


def _watcher_fragment(command: str) -> str:
    """Human-readable reservation receipt; never used as process identity."""
    for line in command.strip().splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return ""


def _marked_watcher_command(command: str, marker: str, path: Path) -> str:
    """Confirm aggregate admission, then retain the marker for shell lifetime."""
    confirmer = shlex.join(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--confirm-watcher",
            str(path),
            marker,
        ]
    )
    return (
        "{\n"
        f"{confirmer} \"$$\" || exit $?\n"
        f"{command}\n"
        "_ship_watcher_status=$?\n"
        f": '{marker}'\n"
        "exit \"$_ship_watcher_status\"\n"
        "}"
    )


def _process_start_identity(pid: int, marker: str) -> str | None:
    """Verify one exact reserving shell PID and return its kernel start time."""
    if pid <= 1 or not marker:
        return None
    try:
        proc = subprocess.run(
            ("ps", "-p", str(pid), "-o", "lstart=", "-o", "command="),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode:
        return None
    rows = [row for row in proc.stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        return None
    match = re.match(r"^\s*(.{24})\s+(.*)$", rows[0])
    if not match or marker not in match.group(2):
        return None
    return match.group(1)


def _confirm_watcher(path: Path, marker: str, pid_text: str) -> bool:
    """Promote one pending reservation only from its executing owner shell."""
    try:
        pid = int(pid_text)
    except (TypeError, ValueError):
        return False
    started = _process_start_identity(pid, marker)
    if not started:
        return False
    with _file_lock(_ledger_lock_path(path)):
        state = _load_ledger(path, allow_missing=True)
        if not isinstance(state, dict):
            return False
        reservation = state.get("ship_watcher")
        if not isinstance(reservation, dict):
            return False
        if str(reservation.get("process_marker") or "") != marker:
            return False
        if reservation.get("confirmed") is True:
            return (
                int(reservation.get("process_pid") or 0) == pid
                and str(reservation.get("process_start") or "") == started
            )
        if reservation.get("confirmed") is not False:
            # Missing means a legacy already-executing reservation, never a
            # pending claim this internal seam is permitted to promote.
            return False
        reservation["confirmed"] = True
        reservation["process_pid"] = pid
        reservation["process_start"] = started
        reservation["confirmed_at"] = time.time()
        _save(path, state)
        return True


def _watcher_process_alive(reservation: dict[str, Any]) -> bool | None:
    """Verify the reserving shell by unique marker plus PID/start identity.

    New reservations arrive pre-bound by the command-side confirmer. Legacy
    reservations without a binding may acquire it on first observation. Later
    polls require marker, PID, and start time, so PID reuse, an identical sibling
    command, and shell/child argv normalization cannot impersonate this owner.
    ``None`` is fail-closed ambiguity (ps failure or duplicate marker).
    """
    marker = str(reservation.get("process_marker") or "")
    if not marker:
        return None
    try:
        proc = subprocess.run(
            ("ps", "-axww", "-o", "pid=", "-o", "lstart=", "-o", "command="),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode:
        return None
    observed: list[tuple[int, str, str]] = []
    for line in proc.stdout.splitlines():
        match = re.match(r"^\s*(\d+)\s+(.{24})\s+(.*)$", line)
        if not match:
            continue
        observed.append((int(match.group(1)), match.group(2), match.group(3)))

    try:
        bound_pid = int(reservation.get("process_pid") or 0)
    except (TypeError, ValueError):
        return None
    bound_start = str(reservation.get("process_start") or "")
    if bound_pid or bound_start:
        if not bound_pid or not bound_start:
            return None
        return any(
            pid == bound_pid and started == bound_start and marker in argv
            for pid, started, argv in observed
        )

    matches = [(pid, started) for pid, started, argv in observed if marker in argv]
    if not matches:
        return False
    if len(matches) != 1:
        return None
    reservation["process_pid"], reservation["process_start"] = matches[0]
    return True


def _watcher_gate(root: Path, path: Path, state: dict[str, Any], watch: dict[str, Any]) -> bool:
    """Enforce the one-watcher law for THIS session's ship state.

    At most one live delayed-wake reservation per session ledger; none at all
    once the state it would watch is already terminal. The reservation lives in
    the same per-session state file every other ship gate uses — worktree and
    session identity are inherited from ``_state_path``, so one session can
    never see (let alone refuse or expire) another session's watcher, and
    nothing is ever killed: an existing background task simply runs out.

    Occupancy is bound to the REAL watcher lifetime (Sol re-review
    2026-08-25), not to the ledger entry's age or the current HEAD. A pending
    claim is occupied through WATCHER_START_GRACE_SECONDS; after that it may be
    replaced because the unconfirmed command did not pass aggregate admission.
    A confirmed claim is occupied for exactly as long as its process is
    observably alive. A head move while the old
    watcher still runs therefore REFUSES — replacing the reservation would
    leave two live watchers with one recorded. Once absent, the SAME
    head/condition remains consumed and refuses a recursive successor; only a
    materially different head or condition can replace it.

    Failure directions are deliberate and split: questions about whether to
    REFUSE extra machinery (the terminal-latch head read) fail open, while
    the OCCUPANCY question fails closed — an unanswerable process table
    refuses, because unknown completion must not permit stacking.
    """
    try:
        head = _run(root, "git", "rev-parse", "HEAD")
    except Exception:
        _deny_watcher(
            "SHIP WATCHER REFUSED: the current Git HEAD is unanswerable, so "
            "this condition watch cannot be bound to a safe state identity. "
            "Unknown identity must not admit an untracked waiter."
        )
        return False
    if head and head in _latched_terminal_heads(state):
        _deny_watcher(
            "SHIP WATCHER REFUSED: this session's ship state at HEAD "
            f"{head[:12]} is already terminal (PARKED / HOLD-FOR-SOL). A new "
            "delayed background timer could only wake the session to re-report "
            "the same frozen hold. Do not create new ship watchers; emit the "
            "single terminal report and end the turn."
        )
        return False
    reservation = state.get("ship_watcher")
    now = time.time()
    if isinstance(reservation, dict):
        try:
            created = float(reservation.get("created") or 0.0)
        except (TypeError, ValueError):
            created = 0.0
        fragment = str(reservation.get("fragment") or "")
        if now < created + WATCHER_START_GRACE_SECONDS:
            _deny_watcher(
                "SHIP WATCHER COALESCED: a background ship watcher was reserved "
                f"{int(now - created)}s ago and is conservatively still starting. "
                "A session carries AT MOST ONE ship-state watcher — rely on the "
                "existing timer; its completion will wake this session."
            )
            return False
        if reservation.get("confirmed") is False:
            # An allow from this hook is only a PENDING claim because sibling
            # PreToolUse hooks decide in parallel. If another hook denied, the
            # updated command never ran and therefore never confirmed. Once the
            # start grace expires, replace that phantom. A late original command
            # is still safe: its confirmer sees a different marker and exits
            # before GitHub starts.
            state.pop("ship_watcher", None)
            return _watcher_gate(root, path, state, watch)
        if not fragment:
            # LEGACY reservation (pre-liveness format, no fragment — observed
            # live 2026-08-25 on this very repair's session): its process can
            # never be identified, so demanding liveness evidence would wedge
            # the slot forever. Release it by its own recorded rule instead:
            # occupied until the deadline the old gate stored, then free.
            # Bounded to entries minted by the superseded intermediate gate;
            # every new reservation carries a fragment.
            try:
                legacy_deadline = float(
                    reservation.get("expires") or reservation.get("nominal_fire") or 0.0
                )
            except (TypeError, ValueError):
                legacy_deadline = 0.0
            if now < legacy_deadline:
                _deny_watcher(
                    "SHIP WATCHER COALESCED: a background ship watcher reserved "
                    "by an earlier guard version still owns this wait (until "
                    f"~{int(legacy_deadline - now)}s from now). Rely on it; its "
                    "completion will wake this session."
                )
                return False
            alive = False
        else:
            alive = _watcher_process_alive(reservation)
        if alive is None:
            _deny_watcher(
                "SHIP WATCHER COALESCED: the reserved ship watcher's liveness "
                "could not be determined (process table unanswerable), and "
                "unknown completion must not permit stacking a second live "
                "watcher. Rely on the existing timer, or retry after its wake."
            )
            return False
        if alive:
            # First observation binds PID + start identity. Persist that
            # binding before refusing the competing request.
            if reservation.get("process_pid") and reservation.get("process_start"):
                _save(path, state)
            _deny_watcher(
                "SHIP WATCHER COALESCED: the reserved background ship watcher "
                f"({fragment[:60]!r}) is still RUNNING. A session carries AT "
                "MOST ONE live ship-state watcher. Completion alone never "
                "authorizes an unchanged successor; only a materially changed "
                "HEAD or external condition may reserve another owner after "
                "this exact PID/start identity has exited."
            )
            return False
        same_condition = (
            str(reservation.get("head") or "") == head
            and str(reservation.get("digest") or "") == str(watch.get("digest") or "")
        )
        if same_condition:
            _deny_watcher(
                "SHIP WATCHER UNCHANGED WAIT REFUSED: the prior deterministic "
                "condition watcher has completed, but this request names the "
                "same HEAD and external condition. Process absence is not "
                "permission to create a successor polling turn. Continue from "
                "the material result that woke the session; do not re-arm the "
                "same wait."
            )
            return False
        # Process absence plus a different head/condition is the only lawful
        # replacement path. The old watcher cannot overlap, and the new
        # fingerprint represents genuinely new external work.
    state["ship_watcher"] = {
        "digest": watch["digest"],
        "fragment": _watcher_fragment(watch["command"]),
        "process_marker": f"ship-watcher:{secrets.token_hex(16)}",
        "condition": watch["condition"],
        "head": head,
        "created": now,
        "confirmed": False,
    }
    _save(path, state)
    return True


def _pre_tool_use(payload: dict[str, Any], raw: bytes) -> None:
    """PreToolUse entry: gate ship-watcher creation, ignore everything else.

    The non-watcher fast path returns BEFORE delegation on purpose — watcher
    classification is pure text with identical semantics in every version of
    this file, and paying a delegated subprocess per ordinary Bash call would
    tax the whole session for a gate that almost never speaks. Watcher-shaped
    calls (rare) take the same delegate-to-evaluated-tree route as Stop.

    Acquisition is LINEARIZABLE (Sol re-review 2026-08-25): the ledger read,
    the occupancy check, and the reservation write happen under one exclusive
    cross-process flock on a sibling of the state file, and the state is
    loaded INSIDE the lock — two concurrent watcher-shaped tool calls cannot
    both observe an empty slot. The lock is scoped to watcher-shaped calls
    only, so ordinary Bash pays nothing.
    """
    watch = _watcher_request(payload)
    if watch is None:
        return
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    admission = str(watch.get("admission") or "")
    if admission == "deny_timer":
        _deny_watcher(
            "SHIP WATCHER TIMER REFUSED: sleep/poll timers are not a lawful "
            "external wait owner. Their completion wakes the reasoning model "
            "even when the observed state is unchanged and enables recursive "
            "successor polling. Use one native condition watch such as "
            "`gh run watch <id> --exit-status` or `gh pr checks --watch`; its "
            "unchanged observations remain inside one process."
        )
        return
    if admission == "deny_detached":
        _deny_watcher(
            "SHIP WATCHER DETACH REFUSED: shell-level `&` detaches the condition "
            "process from the command lifetime recorded in the session ledger. "
            "Run one native condition watch without shell detachment."
        )
        return
    if admission != "reserve_condition":
        _deny_watcher(
            "SHIP WATCHER REFUSED: the watcher-shaped command has no recognized "
            "safe admission policy. Unknown wait transport fails closed."
        )
        return
    if _delegate_to_evaluated_hook(payload, raw):
        return
    try:
        quota_reason = _canonical_hot_watch_reason(watch)
    except Exception as exc:
        _deny_watcher(
            "SHIP WATCHER REFUSED: the canonical GitHub quota admission rule "
            f"could not be evaluated ({exc.__class__.__name__}). A watcher "
            "must fail closed when aggregate permission cannot be proven."
        )
        return
    if quota_reason:
        _deny_watcher(quota_reason)
        return
    root = _repo_root(payload)
    if root is None:
        _deny_watcher(
            "SHIP WATCHER REFUSED: no repository/session identity is available, "
            "so this condition watch cannot be reserved safely."
        )
        return
    path = _state_path(root, payload)
    with _file_lock(_ledger_lock_path(path)):
        delay = os.environ.get(_WATCHER_ACQUIRE_TEST_DELAY_ENV, "")
        state = _load_ledger(path, allow_missing=True)
        if not isinstance(state, dict):
            _deny_watcher(
                "SHIP WATCHER REFUSED: the existing per-session ship ledger is "
                "missing or unreadable, so a one-owner reservation cannot be "
                "proven."
            )
            return
        if delay:
            # Test-only: widen the read→write window so the concurrency
            # regression deterministically catches a de-serialized mutant.
            try:
                time.sleep(float(delay))
            except ValueError:
                pass
        admitted = _watcher_gate(root, path, state, watch)
        if admitted:
            reservation = state["ship_watcher"]
            _allow_watcher(
                tool_input,
                _marked_watcher_command(
                    str(watch["command"]),
                    str(reservation["process_marker"]),
                    path,
                ),
            )


def _github_slug(root: Path) -> tuple[str, str]:
    remote = _run(root, "git", "remote", "get-url", "origin")
    match = re.search(r"github\.com[/:]([^/]+)/([^/\s]+?)(?:\.git)?$", remote)
    if not match:
        raise RuntimeError(f"origin is not a GitHub repository: {remote}")
    return match.group(1), match.group(2)


class RateLimited(RuntimeError):
    """A GitHub call failed because the request quota is spent, not because it was unreachable."""


_TOKEN_CACHE: str | None = None


def _github_token() -> str:
    """Return a GitHub credential: env vars first, then the already-authenticated CLI.

    Claude Code sessions set none of the token env vars, which silently dropped
    every guard evaluation onto the anonymous 60-request/hour-per-IP quota. A
    Stop evaluation spends up to four calls, so a busy session exhausted the
    budget and the guard then failed closed on `github_unreachable` for the rest
    of the hour (measured 2026-07-25: anonymous 0/60 while `gh` held 4998/5000).

    The CLI fallback stores no secret — it reuses the credential `gh auth login`
    already placed on this machine. A missing or logged-out `gh` degrades to the
    previous anonymous behaviour rather than failing.

    Cached for the process lifetime so one evaluation spawns `gh` at most once.
    """
    global _TOKEN_CACHE
    if _TOKEN_CACHE is not None:
        return _TOKEN_CACHE

    token = ""
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            token = value
            break
    if not token:
        try:
            proc = subprocess.run(
                ("gh", "auth", "token"),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                token = proc.stdout.strip()
        except Exception:
            token = ""

    _TOKEN_CACHE = token
    return token


def _github_cache_directory(token: str) -> Path:
    """A private cache shared by every worktree using the same credential.

    A repository can have hundreds of concurrent Claude worktrees. Their Stop
    hooks ask many of the same GitHub questions, so per-process caching does
    almost nothing. The temp directory is user-local on macOS and explicitly
    mode 0700 for Linux hosts. The token itself is never written; only a short
    digest separates credentials with different visibility.
    """
    override = os.environ.get("MACRO_GITHUB_API_CACHE_DIR", "").strip()
    base = (
        Path(override)
        if override
        else Path(tempfile.gettempdir()) / "macro-github-api-cache"
    )
    credential = token or "anonymous"
    directory = base / hashlib.sha256(credential.encode()).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    return directory


@contextmanager
def _file_lock(path: Path):
    """Cross-process advisory lock on one owned regular file, without symlinks."""
    directory_fd = _private_directory_fd(path.parent, create=True)
    descriptor = -1
    try:
        descriptor = os.open(
            path.name,
            os.O_RDWR | os.O_CREAT | _OPEN_CLOEXEC | _OPEN_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        _validate_owned_regular(descriptor, "ship ledger lock")
        os.fchmod(descriptor, 0o600)
        handle = os.fdopen(descriptor, "a+", encoding="utf-8")
        descriptor = -1
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory_fd)
        raise
    try:
        with handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        os.close(directory_fd)


def _save_private_json(path: Path, value: Any) -> None:
    _atomic_save_json(path, value)


def _rate_limit_message(remaining: int, limit: int, reset: int) -> str:
    when = ""
    if reset:
        stamp = datetime.fromtimestamp(reset, timezone.utc)
        when = f", resets {stamp.strftime('%H:%M:%SZ')}"
    reserve = min(GITHUB_RATE_LIMIT_RESERVE, max(5, limit // 10))
    if remaining:
        return (
            f"GitHub API safety reserve reached ({remaining}/{limit}{when}; "
            f"reserve {reserve}). The shared Stop-hook circuit breaker is pausing "
            "GitHub polling until the hourly reset so pushes, merges, and operator "
            "recovery keep working."
        )
    if _github_token():
        hint = "Wait for the reset; no repository or network fault is implied."
    else:
        hint = (
            "The guard is running UNAUTHENTICATED on the 60/hour per-IP quota. "
            "Run `gh auth login` (or export GH_TOKEN) to get the 5000/hour quota."
        )
    return f"GitHub API quota spent (0/{limit}{when}). {hint}"


def _record_rate_limit(directory: Path, headers: Any) -> None:
    """Persist the most conservative primary-budget snapshot from a response."""
    remaining = str((headers or {}).get("X-RateLimit-Remaining") or "")
    limit = str((headers or {}).get("X-RateLimit-Limit") or "")
    reset = str((headers or {}).get("X-RateLimit-Reset") or "")
    if not (remaining.isdigit() and limit.isdigit() and reset.isdigit()):
        return
    path = directory / "rate-limit.json"
    with _file_lock(directory / "rate-limit.lock"):
        current = _load(path) or {}
        observed = {
            "remaining": int(remaining),
            "limit": int(limit),
            "reset": int(reset),
            "observed_at": time.time(),
            "refreshed_at": float(current.get("refreshed_at") or 0),
        }
        # Concurrent responses can arrive out of order. Within one reset window,
        # only the lowest remaining value is safe to publish to sibling hooks.
        if int(current.get("reset") or 0) == observed["reset"]:
            observed["remaining"] = min(
                observed["remaining"], int(current.get("remaining") or observed["remaining"])
            )
        _save_private_json(path, observed)


def _fresh_rate_limit(directory: Path, token: str) -> dict[str, Any] | None:
    """Read the core bucket once a minute; GET /rate_limit costs no primary quota."""
    path = directory / "rate-limit.json"
    now = time.time()
    state = _load(path) or {}
    if (
        int(state.get("reset") or 0) > int(now)
        and now - float(state.get("refreshed_at") or 0) < GITHUB_RATE_LIMIT_REFRESH_SECONDS
    ):
        return state

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "macro-dashboard-ship-loop-guard",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://{GITHUB_API_HOST}/rate_limit", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except Exception:
        # The real endpoint call will surface a useful network/rate-limit error.
        return state or None
    core = (payload.get("resources") or {}).get("core") or {}
    if not all(str(core.get(key) or "").isdigit() for key in ("remaining", "limit", "reset")):
        return state or None
    state = {
        "remaining": int(core["remaining"]),
        "limit": int(core["limit"]),
        "reset": int(core["reset"]),
        "observed_at": now,
        "refreshed_at": now,
    }
    _save_private_json(path, state)
    return state


def _reserve_github_request(directory: Path, token: str) -> None:
    """Reserve one primary request or stop before consuming the safety margin."""
    with _file_lock(directory / "rate-limit.lock"):
        state = _fresh_rate_limit(directory, token)
        if not state:
            return
        now = int(time.time())
        reset = int(state.get("reset") or 0)
        if reset <= now:
            return
        remaining = int(state.get("remaining") or 0)
        limit = int(state.get("limit") or (5000 if token else 60))
        reserve = min(GITHUB_RATE_LIMIT_RESERVE, max(5, limit // 10))
        if remaining <= reserve:
            raise RateLimited(_rate_limit_message(remaining, limit, reset))
        # Reserve before releasing the lock so a burst of sibling hooks cannot
        # all make a decision from the same stale remaining value.
        state["remaining"] = remaining - 1
        _save_private_json(directory / "rate-limit.json", state)


def _http_failure(exc: urllib.error.HTTPError) -> RuntimeError:
    """Classify an HTTP failure so a spent quota does not read as a broken repo.

    `HTTP Error 403: rate limit exceeded` sent sessions hunting for network,
    permission, and remote faults that did not exist. GitHub marks the real
    cause in the response headers, so name it.
    """
    headers = exc.headers or {}
    if exc.code in {403, 429} and headers.get("X-RateLimit-Remaining") == "0":
        limit = int(headers.get("X-RateLimit-Limit") or (5000 if _github_token() else 60))
        reset = str(headers.get("X-RateLimit-Reset") or "")
        return RateLimited(_rate_limit_message(0, limit, int(reset) if reset.isdigit() else 0))
    return RuntimeError(f"GitHub API request failed: HTTP {exc.code} {exc.reason}.")


def _get_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "macro-dashboard-ship-loop-guard",
    }
    # Authenticate to GitHub and nowhere else. This helper also fetches the
    # public production health endpoint, and attaching the credential to that
    # request would hand a repo-scoped token to an unrelated host.
    if urllib.parse.urlsplit(url).hostname != GITHUB_API_HOST:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise _http_failure(exc) from exc

    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    directory = _github_cache_directory(token)
    key = hashlib.sha256(url.encode()).hexdigest()
    cache_path = directory / f"{key}.json"
    lock_path = directory / f"{key}.lock"

    # The URL lock prevents a hundred sessions from refreshing one shared
    # workflow listing simultaneously. Different PR/check URLs remain parallel.
    with _file_lock(lock_path):
        cached = _load(cache_path) or {}
        age = time.time() - float(cached.get("fetched_at") or 0)
        if "payload" in cached and age < GITHUB_API_CACHE_TTL_SECONDS:
            return cached["payload"]

        _reserve_github_request(directory, token)
        etag = str(cached.get("etag") or "")
        if etag:
            headers["If-None-Match"] = etag
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
                _record_rate_limit(directory, response.headers)
                _save_private_json(
                    cache_path,
                    {
                        "etag": str(response.headers.get("ETag") or ""),
                        "fetched_at": time.time(),
                        "payload": payload,
                    },
                )
                return payload
        except urllib.error.HTTPError as exc:
            _record_rate_limit(directory, exc.headers)
            if exc.code == 304 and "payload" in cached:
                cached["fetched_at"] = time.time()
                _save_private_json(cache_path, cached)
                return cached["payload"]
            raise _http_failure(exc) from exc


class _ArtifactRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow GitHub's signed artifact redirect without forwarding its token."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and (
            urllib.parse.urlsplit(req.full_url).hostname
            != urllib.parse.urlsplit(newurl).hostname
        ):
            redirected.remove_header("Authorization")
        return redirected


def _get_artifact_bytes(url: str) -> bytes:
    """Fetch one bounded artifact archive; called only on semantic red paths."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "macro-dashboard-ship-loop-guard",
    }
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    directory = _github_cache_directory(token)
    _reserve_github_request(directory, token)
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_ArtifactRedirectHandler())
    try:
        with opener.open(request, timeout=25) as response:
            _record_rate_limit(directory, response.headers)
            payload = response.read(SEMANTIC_ARTIFACT_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        _record_rate_limit(directory, exc.headers)
        raise _http_failure(exc) from exc
    if len(payload) > SEMANTIC_ARTIFACT_MAX_BYTES:
        raise semantic_proof.SemanticProofError(
            f"semantic artifact exceeds {SEMANTIC_ARTIFACT_MAX_BYTES} byte bound"
        )
    return payload


def _semantic_json_from_archive(archive: bytes) -> Any:
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = [
                entry
                for entry in bundle.infolist()
                if not entry.is_dir() and entry.filename == SEMANTIC_ARTIFACT_FILE
            ]
            if len(members) != 1:
                raise semantic_proof.SemanticProofError(
                    f"semantic artifact contains {len(members)} canonical JSON members"
                )
            member = members[0]
            if member.file_size > SEMANTIC_ARTIFACT_MAX_BYTES:
                raise semantic_proof.SemanticProofError(
                    "semantic evidence JSON exceeds the bounded artifact size"
                )
            raw = bundle.read(member)
    except semantic_proof.SemanticProofError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise semantic_proof.SemanticProofError(
            f"semantic artifact is not a readable zip: {exc}"
        ) from exc
    return semantic_proof.parse_semantic_json(raw)


def _bind_pr_tested_tree(
    owner: str,
    repo: str,
    loaded: Any,
    *,
    bound_base_sha: str,
    subject_head_sha: str,
) -> Any:
    """Bind the artifact's synthetic PR merge to GitHub's exact parents."""
    evidence = getattr(loaded, "evidence", None)
    tested_tree_sha = str(
        evidence.get("tested_tree_sha") if isinstance(evidence, dict) else ""
    ).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", tested_tree_sha):
        raise semantic_proof.SemanticProofError(
            "semantic PR artifact carries no exact tested_tree_sha"
        )
    commit = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/git/commits/{tested_tree_sha}"
    )
    if not isinstance(commit, dict):
        raise semantic_proof.SemanticProofError(
            "semantic tested-tree commit lookup returned no object"
        )
    resolved_sha = str(commit.get("sha") or "").lower()
    if resolved_sha != tested_tree_sha:
        raise semantic_proof.SemanticProofError(
            "semantic tested-tree lookup returned a different commit "
            f"({resolved_sha or 'missing'} != {tested_tree_sha})"
        )
    parents = commit.get("parents")
    parent_shas = (
        [str(parent.get("sha") or "").lower() for parent in parents]
        if isinstance(parents, list) and all(isinstance(parent, dict) for parent in parents)
        else []
    )
    expected_parents = [bound_base_sha.lower(), subject_head_sha.lower()]
    if parent_shas != expected_parents:
        raise semantic_proof.SemanticProofError(
            "semantic tested tree is not the exact two-parent PR merge "
            f"{expected_parents} (observed {parent_shas})"
        )
    return loaded


def _semantic_evidence_for_run(
    owner: str,
    repo: str,
    run: dict[str, Any],
    *,
    role: str,
    expected_base_sha: str | None = None,
) -> Any:
    """Shared-law load for one run; a claimed broken v1 never becomes legacy."""
    run_id = run.get("id")
    head_sha = str(run.get("head_sha") or "")
    if run_id is None:
        raise semantic_proof.SemanticProofError("workflow run carries no id")
    if str(run.get("name") or "") != "ci":
        raise semantic_proof.SemanticProofError(
            f"workflow run {run_id} is not the ci workflow"
        )
    workflow_path = str(run.get("path") or "").split("@", 1)[0]
    if workflow_path != ".github/workflows/ci.yml":
        raise semantic_proof.SemanticProofError(
            f"workflow run {run_id} is not from .github/workflows/ci.yml"
        )
    expected_event = "pull_request" if role == "pr_head" else "workflow_dispatch"
    if str(run.get("event") or "") != expected_event:
        raise semantic_proof.SemanticProofError(
            f"workflow run {run_id} event does not match semantic role {role}"
        )
    associated_bases = {
        str(((pull.get("base") or {}).get("sha")) or "").lower()
        for pull in (run.get("pull_requests") or [])
        if isinstance(pull, dict)
        and str(((pull.get("head") or {}).get("sha")) or "").lower()
        == head_sha.lower()
        and str(((pull.get("base") or {}).get("sha")) or "")
    }
    bound_base_sha = (expected_base_sha or "").lower() or (
        next(iter(associated_bases)) if len(associated_bases) == 1 else ""
    )
    payload = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
        "/artifacts?per_page=100"
    )
    artifact_rows = payload.get("artifacts") or []
    if int(payload.get("total_count") or len(artifact_rows)) > len(artifact_rows):
        raise semantic_proof.SemanticProofError(
            f"run {run_id}'s artifact listing is truncated at {len(artifact_rows)}"
        )
    expected_name = f"{SEMANTIC_ARTIFACT_PREFIX}{run_id}"
    advertised = [
        item
        for item in artifact_rows
        if isinstance(item, dict) and str(item.get("name") or "") == expected_name
    ]
    if not advertised:
        semantic_tree = False
        shas = [head_sha, bound_base_sha, *sorted(associated_bases)]
        for pull in run.get("pull_requests") or []:
            if isinstance(pull, dict):
                base_sha = str(((pull.get("base") or {}).get("sha")) or "")
                if base_sha:
                    shas.append(base_sha)
        for sha in dict.fromkeys(sha for sha in shas if sha):
            marker = (
                f"https://api.github.com/repos/{owner}/{repo}/contents/"
                "scripts/ci_semantic_proof.py?"
                + urllib.parse.urlencode({"ref": sha})
            )
            try:
                _get_json(marker)
                semantic_tree = True
                break
            except RuntimeError as exc:
                if "HTTP 404" in str(exc):
                    continue
                raise
        return semantic_proof.load_semantic_evidence(
            None, advertised=semantic_tree
        )
    if len(advertised) != 1:
        raise semantic_proof.SemanticProofError(
            f"run {run_id} advertises {len(advertised)} semantic artifacts"
        )
    if len(associated_bases) > 1:
        raise semantic_proof.SemanticProofError(
            f"run {run_id} identifies multiple PR proof bases"
        )
    if expected_base_sha and associated_bases and associated_bases != {bound_base_sha}:
        raise semantic_proof.SemanticProofError(
            f"run {run_id}'s PR base metadata disagrees with the expected proof base"
        )
    artifact = advertised[0]
    if role == "pr_head" and not bound_base_sha:
        raise semantic_proof.SemanticProofError(
            f"run {run_id} does not identify the exact PR proof base"
        )
    if artifact.get("expired"):
        raise semantic_proof.SemanticProofError(
            f"run {run_id}'s advertised semantic artifact is expired"
        )
    download_url = str(artifact.get("archive_download_url") or "")
    if not download_url:
        raise semantic_proof.SemanticProofError(
            f"run {run_id}'s advertised semantic artifact has no download URL"
        )
    source = _semantic_json_from_archive(_get_artifact_bytes(download_url))
    expected_tree = head_sha if role == "main" else None
    loaded = semantic_proof.load_semantic_evidence(
        source,
        advertised=True,
        expected_run_id=run_id,
        expected_subject_head_sha=head_sha,
        expected_tested_tree_sha=expected_tree,
        expected_base_sha=bound_base_sha or None,
        expected_event=expected_event,
        expected_role=role,
        expected_workflow="ci",
    )
    if role == "pr_head":
        return _bind_pr_tested_tree(
            owner,
            repo,
            loaded,
            bound_base_sha=bound_base_sha,
            subject_head_sha=head_sha,
        )
    return loaded


def _semantic_pr_base_sha(
    runs: list[dict[str, Any]], head_sha: str, number: Any = None
) -> str | None:
    """Exact event base already bound to the linked ci-gate check run."""
    bases = {
        str(((association.get("base") or {}).get("sha")) or "").lower()
        for run in runs
        if str(run.get("name") or "") == "ci-gate"
        for association in (run.get("pull_requests") or [])
        if isinstance(association, dict)
        and (number is None or str(association.get("number") or "") == str(number))
        and str(((association.get("head") or {}).get("sha")) or "").lower()
        == head_sha.lower()
        and str(((association.get("base") or {}).get("sha")) or "")
    }
    if len(bases) > 1:
        raise semantic_proof.SemanticProofError(
            "ci-gate identifies multiple immutable PR proof bases"
        )
    return next(iter(bases), None)


def _semantic_evidence_for_head(
    owner: str,
    repo: str,
    head_sha: str,
    *,
    check_runs: list[dict[str, Any]] | None = None,
    expected_base_sha: str | None = None,
) -> Any:
    """Newest exact-head PR evidence; costs nothing unless a caller is already red."""
    linked: list[tuple[int, dict[str, Any]]] = []
    for check in check_runs or []:
        if str(check.get("name") or "") != "ci-gate":
            continue
        match = re.search(r"/actions/runs/(\d+)(?:/|$)", str(check.get("details_url") or ""))
        if match:
            linked.append((int(match.group(1)), check))
    # MERGE ARTIFACTS ARE NOT COMPETING VERDICTS (2026-08-15). Merging fires
    # `pull_request: closed`, and ci.yml's concurrency block deliberately starts a
    # ZERO-RUNNER replacement in the same group for it ("The closed event starts a
    # zero-runner replacement ... cancelling a long CI pack when its PR merges or
    # closes").  So EVERY cleanly merged head carries two ci-gate check-runs: the real
    # concluded one, plus a `skipped` artifact created 12-15s later by the merge itself.
    # Counting that artifact as a second opinion made this raise on every merged head —
    # measured on two independently authored PRs the same afternoon:
    #   #5754 c02fc9eac6e8: success 14:22:00Z (run 31887298300) + skipped 14:22:15Z (31889718105)
    #   #5753 f9bdefd484b6: success 13:17:16Z              + skipped 13:17:28Z
    # which blocked their authoring sessions from stopping on work that had merged GREEN,
    # with no session-side remedy: check-runs on a merged commit are immutable and
    # `gh run rerun` preserves the run id, so the two ids can never be collapsed.
    #
    # A `skipped` ci-gate asserts nothing, so it cannot CONFLICT with anything. Drop it
    # and reason on what remains. Ambiguity is still fail-closed: two runs that both
    # reached a real conclusion remain irreconcilable and still raise, and a head whose
    # ONLY evidence is skipped still resolves to no usable evidence below.
    decisive = [
        (run_id, check)
        for run_id, check in linked
        if str(check.get("conclusion") or "").lower() != "skipped"
    ]
    if decisive:
        linked = decisive
    linked_ids = {run_id for run_id, _check in linked}
    if len(linked_ids) > 1:
        raise semantic_proof.SemanticProofError(
            f"head {head_sha[:12]} links multiple latest ci-gate workflow runs"
        )
    if linked:
        run_id, _check = linked[0]
        run = _get_json(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
        )
        if not isinstance(run, dict) or str(run.get("id") or "") != str(run_id):
            raise semantic_proof.SemanticProofError(
                "linked ci-gate workflow run id mismatch"
            )
        if str(run.get("head_sha") or "") != head_sha:
            raise semantic_proof.SemanticProofError(
                "linked ci-gate workflow run head mismatch"
            )
        return _semantic_evidence_for_run(
            owner,
            repo,
            run,
            role="pr_head",
            expected_base_sha=expected_base_sha,
        )
    query = urllib.parse.urlencode(
        {
            "head_sha": head_sha,
            "event": "pull_request",
            "status": "completed",
            "per_page": str(SEMANTIC_RUN_LOOKBACK),
        }
    )
    payload = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/ci.yml/runs?{query}"
    )
    for run in (payload.get("workflow_runs") or [])[:SEMANTIC_RUN_LOOKBACK]:
        if not isinstance(run, dict) or str(run.get("head_sha") or "") != head_sha:
            continue
        loaded = _semantic_evidence_for_run(
            owner,
            repo,
            run,
            role="pr_head",
            expected_base_sha=expected_base_sha,
        )
        if getattr(loaded, "mode", "") == "semantic":
            return loaded
    return semantic_proof.load_semantic_evidence(None, advertised=False)


def _recent_main_semantic_evidence(owner: str, repo: str) -> list[Any]:
    """Bounded newest-first main artifacts, including artifacts from red runs."""
    query = urllib.parse.urlencode(
        {
            "branch": "main",
            "status": "completed",
            "per_page": str(SEMANTIC_RUN_LOOKBACK),
        }
    )
    payload = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/ci.yml/runs?{query}"
    )
    evidence: list[Any] = []
    for run in (payload.get("workflow_runs") or [])[:SEMANTIC_RUN_LOOKBACK]:
        if not isinstance(run, dict):
            continue
        if str(run.get("conclusion") or "").lower() in {
            "cancelled",
            "skipped",
            "neutral",
            "stale",
        }:
            continue
        try:
            loaded = _semantic_evidence_for_run(owner, repo, run, role="main")
        except semantic_proof.SemanticProofError:
            # This row is not a witness. It must never be treated as legacy or
            # PASS, but it also cannot resurrect an old blocker after a different,
            # independently valid descendant PASS in the bounded window.
            continue
        if getattr(loaded, "mode", "") == "semantic":
            evidence.append(getattr(loaded, "evidence", None))
    return evidence


def _semantic_authority_touched(owner: str, repo: str, number: Any) -> bool:
    """Fail-closed pull-files inventory for the semantic self-excuse fence."""
    if number is None:
        return True
    paths: list[str] = []
    seen: set[str] = set()
    for page in range(1, 4):
        query = urllib.parse.urlencode({"per_page": "100", "page": str(page)})
        payload = _get_json(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/files?{query}"
        )
        if not isinstance(payload, list):
            return True
        for item in payload:
            if not isinstance(item, dict):
                return True
            # A rename touches both identities.  In particular, moving an
            # authority file to an innocuous destination cannot erase the old
            # authority path from this self-excuse fence.
            for key in ("filename", "previous_filename"):
                path = str(item.get(key) or "")
                if path and path not in seen:
                    seen.add(path)
                    paths.append(path)
        if len(payload) < 100:
            break
    else:
        return True
    try:
        return any(is_ci_authority_path(path) for path in paths)
    except AuthorityPathError:
        return True


def _semantic_gate(loaded: Any) -> Any | None:
    if loaded is None or getattr(loaded, "mode", "") != "semantic":
        return None
    return semantic_proof.semantic_gate_verdict(getattr(loaded, "evidence", None))


def _semantic_unit_detail(unit: Any) -> str:
    """Operator-facing semantic identity; transport is disclosed, never causal."""
    signature = getattr(unit, "failure_signature", None)
    if isinstance(signature, (list, tuple)):
        signature_text = ",".join(str(atom) for atom in signature)
    else:
        signature_text = str(signature or "unavailable")
    return (
        f"logical job={getattr(unit, 'logical_job_id', '?')}; "
        f"proof id={getattr(unit, 'proof_id', '?')}; "
        f"classification={getattr(unit, 'classification', 'unknown')}; "
        f"failure signature={signature_text}; "
        f"base SHA={str(getattr(unit, 'base_sha', '') or '?')}; "
        f"head SHA={str(getattr(unit, 'head_sha', '') or '?')}; "
        f"transport pack={getattr(unit, 'pack_index', '?')}; "
        f"detail={getattr(unit, 'detail', '') or 'none'}"
    )


def _semantic_unit_details(units: Any, *, limit: int = 8) -> list[str]:
    return [_semantic_unit_detail(unit) for unit in tuple(units)[:limit]]


def _semantic_nonunit_refusal(loaded: Any) -> str:
    """Explain a shared-gate refusal that has no semantic unit to format."""
    evidence = getattr(loaded, "evidence", None)
    if not isinstance(evidence, dict):
        return "semantic evidence has no readable gate payload"
    if evidence.get("authority_changed") is True:
        return (
            "semantic evidence records authority_changed=true; candidate-era proof "
            "may not excuse this authority-changing pull request"
        )
    infrastructure = evidence.get("infrastructure")
    if isinstance(infrastructure, list) and infrastructure:
        return "semantic infrastructure ambiguity: " + str(infrastructure[:4])[:800]
    job_infrastructure = [
        {
            "logical_job_id": job.get("logical_job_id"),
            "infrastructure": job.get("infrastructure"),
        }
        for job in evidence.get("jobs", [])
        if isinstance(job, dict)
        and isinstance(job.get("infrastructure"), dict)
        and job["infrastructure"].get("outcome") != "passed"
    ]
    if job_infrastructure:
        return "semantic job infrastructure ambiguity: " + str(
            job_infrastructure[:4]
        )[:800]
    return (
        f"semantic evidence status={evidence.get('status')!r} is not clear and "
        "contains no classified blocking unit"
    )


def _semantic_has_nonunit_blocker(loaded: Any, gate: Any | None = None) -> bool:
    evidence = getattr(loaded, "evidence", None)
    if not isinstance(evidence, dict):
        return True
    if evidence.get("authority_changed") is True or bool(
        evidence.get("infrastructure")
    ):
        return True
    try:
        resolved_gate = gate if gate is not None else _semantic_gate(loaded)
    except (semantic_proof.SemanticProofError, RuntimeError, ValueError):
        return True
    return bool(
        resolved_gate is not None
        and getattr(resolved_gate, "infrastructure_blocking", False)
    )


def _semantic_authority_refusal(number: Any) -> str:
    return (
        f"PR #{number} changes CI proof authority and may not use candidate-era "
        "semantic evidence to excuse its own red; bootstrap under the old gate"
    )


#: The emitter records the authority freeze ITSELF as an infrastructure row:
#: `ci_semantic_proof.reconcile_evidence` appends this outcome on every pr_head
#: artifact where `authority_changed` is true and any unit classified
#: `inherited_base` (the motivating shape — an authority-changing PR merged
#: while main was red). An infrastructure list holding NOTHING ELSE therefore
#: IS the freeze, not ambiguity. Getting this wrong inverts the gate: the
#: first draft of the predicate below required `infrastructure` empty and
#: `gate.infrastructure_blocking` false, which made the clearing DEAD for the
#: motivating case and OPEN for a head carrying its own classified
#: `pr_regression` — caught by the pre-ship red team, 2026-08-19.
_AUTHORITY_SELF_EXCUSE_OUTCOME = "authority_self_excuse_refused"


def _authority_freeze_is_sole_nonunit_blocker(loaded: Any, gate: Any) -> bool:
    """True when frozen semantic evidence blocks ONLY on the authority freeze.

    This predicate scopes the ONE bounded clearing path an authority freeze has
    (see `_check_ci`). It answers True exactly when every non-clear signal in
    the artifact is the freeze itself: `authority_changed=true`, every
    top-level infrastructure row is the emitter's own self-excuse refusal,
    every job's infrastructure passed, and — decisive — the gate exposes ZERO
    classified blocking units. A `pr_regression`/`unknown` unit is the head's
    OWN red and must never be blanketed by a descendant baseline; those heads
    keep the ordinary frozen refusal. Fail CLOSED on every unreadable shape.
    (`gate.infrastructure_blocking` is deliberately NOT consulted: it is true
    in the motivating case purely because of the self-excuse row.)
    """
    evidence = getattr(loaded, "evidence", None)
    if not isinstance(evidence, dict):
        return False
    if evidence.get("authority_changed") is not True:
        return False
    infrastructure = evidence.get("infrastructure")
    if not isinstance(infrastructure, list):
        return False
    if any(
        not isinstance(row, dict)
        or row.get("outcome") != _AUTHORITY_SELF_EXCUSE_OUTCOME
        for row in infrastructure
    ):
        return False
    jobs = evidence.get("jobs")
    if not isinstance(jobs, list):
        return False
    for job in jobs:
        if not isinstance(job, dict):
            return False
        job_infrastructure = job.get("infrastructure")
        if not isinstance(job_infrastructure, dict):
            return False
        if str(job_infrastructure.get("outcome", "passed")) != "passed":
            return False
    return not getattr(gate, "blocking", True)


def _head_can_advertise_semantic_evidence(runs: list[dict[str, Any]]) -> bool:
    return any(
        str(run.get("name") or "") == "ci-gate"
        and "/actions/runs/" in str(run.get("details_url") or "")
        and str(run.get("status") or "").lower() == "completed"
        and bool(str(run.get("conclusion") or ""))
        for run in runs
    )


def _github_block_code(exc: Exception) -> str:
    """Spent quota and unreachable API are both external, but they are not the same problem."""
    return "github_rate_limited" if isinstance(exc, RateLimited) else "github_unreachable"


def _latest_merged_pr(owner: str, repo: str, branch: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode(
        {"state": "closed", "head": f"{owner}:{branch}", "base": "main", "per_page": "20"}
    )
    pulls = _get_json(f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}")
    merged = [pull for pull in pulls if pull.get("merged_at")]
    return max(merged, key=lambda pull: pull.get("merged_at") or "") if merged else None


def _is_spurious_check(name: str) -> bool:
    """The known-spurious Cloudflare check every CI gate here has always ignored.

    Deliberately narrow, and SELF-CONTAINED: this hook is loaded by file path and
    must never acquire the application import graph to answer one question, so the
    predicate is a literal here rather than an import. `scripts/merge_on_green.py`
    carries its own copy of the identical rule for the same reason.

    Widening this allowlist is a RULING, not a refactor — a broadened predicate
    waves a genuine red through as noise, which is the most expensive mistake this
    function can make. Change it here and in the sweeper together, or in neither.

    NOT the whole "is this a red we own" question — see :func:`_is_non_binding_check`,
    which adds the one context this hook must also skip. Call that one from a gate;
    this predicate stays narrow so the spurious allowlist keeps its own meaning.
    """
    lowered = str(name or "").lower()
    return "workers builds" in lowered and "macro" in lowered


#: The inactive `ci-authority` base context. `.github/workflows/ci-authority.yml`
#: publishes two complementary exact-head contexts — `ci-authority/main` and
#: `ci-authority/codex/merge-queue-pilot` — and states that "each PR run FAILS the
#: inactive context so an edited retarget cannot reuse a success earned against
#: another base". Stop-hook sessions only ever track pull requests targeting main,
#: so on every one of them this context is red BY DESIGN. It is retarget-invalidation
#: state, not a verdict. `ci-authority/main` stays binding everywhere.
CI_AUTHORITY_INACTIVE_CONTEXT = "ci-authority/codex/merge-queue-pilot"


def _is_non_binding_check(name: str) -> bool:
    """Is this check name one no gate here may read as a red we own?

    THE ONE DEFINITION, and it is now actually one. This is NOT a widening of the
    spurious allowlist: `_split_head_runs` and `_red_checks` have BOTH skipped
    `CI_AUTHORITY_INACTIVE_CONTEXT` since it was introduced, and the sweeper carries
    the identical rule (`scripts/merge_on_green.py`, `is_spurious_check` call sites).
    The merged-head CI gate did not — while its own comment claimed "ONE definition
    of 'not a red', shared with `_split_head_runs` above and with the sweeper's own
    copy". A comment asserting parity is not parity, and the divergence is exactly
    the kind a reader cannot see: three loops that look alike, one filtering less.

    THE SCAR. The gate blocked a session whose work had MERGED GREEN, naming a
    context that is red on every pull request in this repository — measured on the
    sibling PR #5767, whose single failing check was this context and which merged
    clean. It stayed invisible because the semantic proof path ahead of it raised
    first (#5771) and produced a different refusal; repairing that unmasked this,
    which is the ordinary shape of a first failing gate hiding the second.

    Deliberately still narrow. `_is_spurious_check` keeps its own meaning and its own
    "widening is a RULING, not a refactor" contract; this adds exactly one name, and
    that name's redness is a documented property of the workflow that emits it.
    """
    return _is_spurious_check(name) or str(name or "") == CI_AUTHORITY_INACTIVE_CONTEXT


def _open_pull(owner: str, repo: str, branch: str) -> dict[str, Any] | None:
    """The branch's OPEN pull request against main, or None.

    Same endpoint shape as `_latest_merged_pr`, so it shares the 30-second shared
    cache and costs one call that sibling worktrees reuse.
    """
    query = urllib.parse.urlencode(
        {"state": "open", "head": f"{owner}:{branch}", "base": "main", "per_page": "20"}
    )
    pulls = _get_json(f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}")
    return pulls[0] if pulls else None


def _red_pairs(runs: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """``(name, conclusion)`` for every non-spurious CONCLUDED red on a head.

    The ONE definition of "which of this head's checks are red", shared by the
    display formatting in `_split_head_runs` and by the base-side probe in
    `_armed_pull_status`. They must never disagree about the set: a name the
    display shows but the probe never asks about is a red that can only ever be
    blamed on this session.
    """
    pairs: list[tuple[str, str]] = []
    for run in runs:
        name = str(run.get("name") or "unnamed check")
        # `_is_non_binding_check` carries both rules (spurious Cloudflare X, and the
        # ci-authority inactive base context that is red on every PR by design).
        if _is_non_binding_check(name):
            continue
        if run.get("status") != "completed":
            continue
        conclusion = run.get("conclusion")
        if conclusion not in NON_RED_CONCLUSIONS:
            pairs.append((name, str(conclusion)))
    return pairs


def _split_head_runs(
    runs: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    """``(red, pending, passed)`` names for a head's check runs, spurious excluded.

    ``red`` entries are formatted ``"<name> (<conclusion>)"`` — a bare name cannot
    tell a `failure` from a `timed_out` from a `cancelled`, and a session reading
    the block message needs that to know whether to re-run or to fix. The other
    two are bare names; there is nothing to disambiguate.
    """
    red = [f"{name} ({conclusion})" for name, conclusion in _red_pairs(runs)]
    pending: list[str] = []
    passed: list[str] = []
    for run in runs:
        name = str(run.get("name") or "unnamed check")
        if _is_non_binding_check(name):
            continue
        if run.get("status") != "completed":
            pending.append(name)
        elif run.get("conclusion") == "success":
            passed.append(name)
    return red, pending, passed


def _main_proof_reds(owner: str, repo: str, reference: str) -> dict[str, str]:
    """Job names RED in main's newest CONCLUDED proof run, name -> citation.

    Costs 2 calls per workflow (newest run + its jobs) and every session in the
    fleet asks for the same two URLs, so `_get_json`'s shared 30-second cache makes
    this effectively one lookup for the whole checkout family — which matters,
    because the population that reaches here is by definition every armed session
    at once.

    Resolved from the RUN, never from a commit walk, for the reason
    `scripts/merge_on_green.py` gives at length: `ci.yml` has no `push` trigger
    while the nightly and wire lanes push ~24 `[skip ci]` commits per 2 hours, so a
    commit-window heuristic ages out in ~100 minutes and returns zero `ci-pack-*`
    names no matter how healthy main is (#5037, 2026-08-08).

    Job names are compared to CHECK names directly. That identity is the sweeper's
    own assumption in `_run_clean_jobs`, and the two must not drift apart.

    STALENESS IS FAIL-CLOSED. A proof run that started more than `BASE_SIDE_WINDOW`
    from ``reference`` describes a different base vintage and is discarded, so a
    three-day-old red main can never excuse today's genuine regression. An
    unreadable run, an undated one, or an empty listing likewise contributes
    nothing — and contributing nothing keeps the red on this session.
    """
    reference_dt = _parse_stamp(reference)
    if reference_dt is None:
        # Nothing to date the proof AGAINST, so no proof could be accepted and the
        # calls would be pure waste on the shared 5,000/hr pool. Answering "no
        # exclusion" without spending anything is both the cheap and the
        # fail-closed move.
        return {}
    reds: dict[str, str] = {}
    for workflow in MAIN_PROOF_WORKFLOWS:
        listing = urllib.parse.urlencode(
            {"branch": "main", "status": "completed", "per_page": "1"}
        )
        runs = _get_json(
            f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}"
            f"/runs?{listing}"
        ).get("workflow_runs", [])
        if not runs:
            continue
        run = runs[0]
        started = _parse_stamp(_started_stamp(run, "run_started_at", "created_at"))
        if reference_dt is None or started is None:
            continue
        if abs(started - reference_dt) > BASE_SIDE_WINDOW:
            continue
        run_id = run.get("id")
        sha = str(run.get("head_sha") or "")
        jobs = _get_json(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
            f"?{urllib.parse.urlencode({'per_page': '100'})}"
        ).get("jobs", [])
        for job in jobs:
            if job.get("status") != "completed":
                continue
            if job.get("conclusion") in NON_RED_CONCLUSIONS:
                continue
            name = str(job.get("name") or "")
            if name:
                reds.setdefault(name, f"{workflow} run {run_id}@{sha[:12] or '?'}")
    return reds


def _base_side_pre_merge(
    owner: str,
    repo: str,
    head_sha: str,
    head_branch: str,
    reference: str,
    names: list[str],
) -> tuple[dict[str, str], list[str]]:
    """Which of an UNMERGED head's reds it INHERITED from the shared base.

    Returns ``(name -> citation, unavailable notes)``.

    WHY THIS EXISTS ON THE PRE-MERGE PATH AT ALL. `_check_ci` has carried
    base-side awareness since 2026-07-26, but it only ever judged a MERGED pull
    request, and under the retired release rule the pre-merge red path was reached
    rarely. It is now reached on EVERY Stop of EVERY armed session — which is
    precisely the population that inherits a red main. Without this, a routine
    fleet-wide pack red tells every session in the fleet "Fix the cause and re-run
    the failed job" about a defect none of them wrote, and several independently
    start healing a pack they did not break: the partial-heal deadlock CLAUDE.md
    §"Healing a red pack" exists to prevent. The measured shape of that day is on
    record — 61 pull requests armed, 60 red on `ci-pack-2`/`ci-pack-3` that main's
    own last run had proven green (#5037).

    Two sources, cheapest and most decisive first:

      B1, main is CURRENTLY red on the same NAME. Main's newest concluded proof run
        failing the same job is the strongest possible statement that the red is
        not ours: we are not on main.
      B2, sibling confirmation — the same name red on at least TWO INDEPENDENT
        concurrent pull-request heads. Identical machinery, bar, and rationale as
        `_check_ci`'s E2 (two distinct BRANCHES, because a pack name fronts many
        jobs and one sibling sharing it is a coincidence), differing only in the
        window: an unmerged head's content is on no shared base, so siblings on
        either side of our red are equally probative.

    FAIL-CLOSED THROUGHOUT, and the direction matters. An exception, an unreadable
    proof, a stale one, or a lone sibling yields NO exclusion, and the red stays
    this session's — a guard that guessed the other way would hand every genuine
    regression a base-side excuse. Both sources degrade independently and every
    failure is NAMED in the returned notes rather than swallowed.

    Nothing here releases anyone. Both outcomes still block: the exclusion only
    decides whether the session is told to fix its own defect or told that main is
    the cause and given main's lever.
    """
    excused: dict[str, str] = {}
    unavailable: list[str] = []
    if not names:
        return excused, unavailable

    try:
        main_reds = _main_proof_reds(owner, repo, reference)
    except Exception as exc:  # noqa: BLE001 — an unreadable proof keeps the red
        main_reds = {}
        unavailable.append(f"main proof: {str(exc)[:160].strip()}")
    for name in names:
        citation = main_reds.get(name)
        if citation:
            excused[name] = f"red on main's own newest proof ({citation})"

    remaining = [name for name in names if name not in excused]
    if remaining:
        anchor = _parse_stamp(reference)
        if anchor is None:
            unavailable.append("sibling confirmation: this head's red carries no start stamp")
        else:
            window = (
                (anchor - BASE_SIDE_WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ"),
                (anchor + BASE_SIDE_WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            try:
                confirmations = _base_side_confirmations(
                    owner, repo, head_sha, head_branch, window, reference, remaining
                )
            except Exception as exc:  # noqa: BLE001 — same reason as above
                confirmations = {}
                unavailable.append(f"sibling confirmation: {str(exc)[:160].strip()}")
            for name in remaining:
                heads = confirmations.get(name) or {}
                if len(heads) < 2:
                    continue
                cited = ", ".join(f"{sha[:7]}@{branch}" for branch, sha in heads.items())
                excused[name] = (
                    f"red on {len(heads)} independent concurrent sibling head(s) ({cited})"
                )
    return excused, unavailable


def _base_red_block(number: Any, excused: dict[str, str], pending: list[str]) -> str:
    """The `unmerged` detail for a head whose every red is provably main's.

    Never says "fix the cause": there is nothing here for this session to fix, and
    saying so is what starts several sessions healing one pack in parallel.
    """
    cited = "; ".join(f"{name} — {why}" for name, why in excused.items())
    tail = (
        f" Still running here: {', '.join(pending[:8])}."
        if pending
        else ""
    )
    return (
        f"Pull request #{number} is armed with `{MERGE_ON_GREEN_LABEL}` and is NOT merged, "
        f"and its red is INHERITED FROM MAIN, not yours: {cited}.{tail} Do not start healing "
        "a pack you did not break — under a fleet-wide red every armed session sees this "
        "same failure, and two partial heals of one pack can never both go green (CLAUDE.md "
        "§'Healing a red pack'). The sweeper drains an inherited backlog by itself once main "
        "is proven again; the lever is `gh workflow run ci.yml --ref main`, and it is "
        "DESTRUCTIVE over a live baseline — preflight `gh run list --workflow ci.yml "
        "--branch main --json databaseId,status --jq '[.[]|select(.status!=\"completed\")]'` "
        "and WATCH an in-flight run (`gh run watch <id> --interval 60`) instead of "
        "re-dispatching over it. You still own this pull request until the merge lands."
    )


def _armed_pull_status(owner: str, repo: str, branch: str, head: str) -> tuple[str, str]:
    """Diagnose this branch's OPEN armed pull request. NEVER releases the session.

    Returns ``(code, detail)``. ``code`` is ``none`` when there is nothing useful
    to say — no open pull request, no `merge-on-green` label, or an armed head that
    is not the local HEAD — and the caller then files its ordinary `unmerged`
    block. Otherwise it is the block code to file:

      ``ci_failed_unmerged`` — a non-spurious check CONCLUDED outside
        `NON_RED_CONCLUSIONS`, and the base-side probe could NOT show it is main's.
        The sweeper never merges a red, so nothing is going to pick this up. This
        is the shape that used to be reported as done: a session stopped on the
        label while its pull request sat `merge-blocked`. Naming the reds is the
        whole value of answering here rather than falling through. The code is
        internal ON PURPOSE — see `CI_FAILED_UNMERGED` — so the state this guard
        exists to prevent is not also the cheapest one to leave.
      ``unmerged`` — armed and not merged, with nothing red that is THIS head's:
        checks pending, all clean, nothing non-spurious at all, or every red
        provably inherited from main (`_base_side_pre_merge`). The label means the
        sweeper MAY perform the merge; it does not mean this session has finished.
        Stay with the pull request until the merge lands.

    The head sha must equal the LOCAL HEAD. An armed pull request whose head is
    older than the worktree means the session's latest work is not what would be
    merged — the `unpushed` gate above usually catches that, but a force-moved
    branch reaches here with a clean ahead-count.
    """
    pull = _open_pull(owner, repo, branch)
    if not pull:
        return "none", ""
    labels = {str((label or {}).get("name") or "") for label in (pull.get("labels") or [])}
    if MERGE_ON_GREEN_LABEL not in labels:
        return "none", ""
    number = pull.get("number")
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    if not head_sha or head_sha != head:
        return "none", ""

    runs = _head_check_runs(owner, repo, head_sha)
    red, pending, passed = _split_head_runs(runs)
    if red:
        try:
            loaded = (
                _semantic_evidence_for_head(
                    owner,
                    repo,
                    head_sha,
                    check_runs=runs,
                    expected_base_sha=_semantic_pr_base_sha(
                        runs, head_sha, number
                    ),
                )
                if _head_can_advertise_semantic_evidence(runs)
                else None
            )
            gate = _semantic_gate(loaded)
        except RateLimited:
            raise
        except Exception as exc:  # advertised/malformed v1 is never legacy
            return CI_FAILED_UNMERGED, (
                f"Failing CI on pull request #{number}: advertised semantic evidence "
                "is unusable and may not downgrade to legacy pack reasoning: "
                f"{str(exc)[:500]}."
            )
        if gate is not None:
            if gate.clear and _semantic_authority_touched(owner, repo, number):
                return CI_FAILED_UNMERGED, _semantic_authority_refusal(number)
            if not gate.clear:
                reasons = _semantic_unit_details(gate.blocking)
                if _semantic_has_nonunit_blocker(loaded, gate):
                    reasons.append(_semantic_nonunit_refusal(loaded))
                detail = "; ".join(reasons) or _semantic_nonunit_refusal(loaded)
                return CI_FAILED_UNMERGED, (
                    f"Failing semantic CI on pull request #{number}: "
                    f"{detail}. "
                    "The refusal is keyed to logical job/proof identity, not ci-pack-N."
                )

            non_transport = [
                run
                for run in runs
                if not re.fullmatch(r"ci-pack-\d+", str(run.get("name") or ""))
            ]
            semantic_red, semantic_pending, semantic_passed = _split_head_runs(
                non_transport
            )
            if semantic_red:
                return CI_FAILED_UNMERGED, (
                    f"Failing CI on pull request #{number}: "
                    + ", ".join(semantic_red[:8])
                    + ". Semantic evidence cleared pack transport only; this "
                    "non-transport failure remains authoritative."
                )
            inherited = "; ".join(_semantic_unit_details(gate.inherited))
            waiting = (
                f" Still running: {', '.join(semantic_pending[:8])}."
                if semantic_pending
                else ""
            )
            if inherited:
                return "unmerged", (
                    f"Pull request #{number} is armed and NOT merged. Its exact-base "
                    f"semantic failure is inherited: {inherited}. ci-pack-N is transport "
                    f"only; the sweeper still applies ProofFreshness before merging.{waiting}"
                )
            if semantic_pending:
                return "unmerged", (
                    f"Pull request #{number} has clear semantic evidence but remains "
                    f"unmerged while checks run: {', '.join(semantic_pending[:8])}."
                )
            if semantic_passed:
                return "unmerged", (
                    f"Pull request #{number} has complete clear semantic evidence and "
                    "is still armed; the next sweep owns ProofFreshness and merge."
                )
        pairs = _red_pairs(runs)
        # Only `failure` is base-side excludable, for `_check_ci`'s reason: a
        # `cancelled`/`timed_out` genuinely can green on a re-run, so it stays the
        # session's to re-run rather than main's to answer for.
        names = list(dict.fromkeys(n for n, conclusion in pairs if conclusion == "failure"))
        # Proximity anchor: when OUR OWN red started. Same-format `...Z` stamps, so
        # the string min is the earliest. An undated head cannot be argued about at
        # all, which is fail-closed: `_base_side_pre_merge` then excuses nothing.
        starts = [
            stamp
            for run in runs
            if not _is_non_binding_check(str(run.get("name") or "unnamed check"))
            and run.get("conclusion") == "failure"
            for stamp in (_started_stamp(run, "started_at", "completed_at"),)
            if stamp
        ]
        reference = min(starts) if starts else ""
        try:
            excused, unavailable = _base_side_pre_merge(
                owner, repo, head_sha, branch, reference, names
            )
        except Exception as exc:  # noqa: BLE001 — an unanswerable probe keeps the red
            excused, unavailable = {}, [f"base-side probe: {str(exc)[:160].strip()}"]
        mine = [
            f"{name} ({conclusion})" for name, conclusion in pairs if name not in excused
        ]
        if not mine:
            return "unmerged", _base_red_block(number, excused, pending)
        detail = (
            f"Failing CI on pull request #{number}: {', '.join(mine[:8])}. It carries "
            f"`{MERGE_ON_GREEN_LABEL}`, but the sweeper never merges a red pull request, "
            "so nothing is going to pick this up while you are away. Fix the cause and "
            "re-run the failed job — the label stays armed and the next sweep merges once "
            "the head is clean — or finish the merge by hand on concluded-green."
        )
        if excused:
            cited = "; ".join(f"{name} — {why}" for name, why in excused.items())
            detail = f"{detail} (Ignored as base-side, inherited from main: {cited}.)"
        if unavailable:
            detail = f"{detail} (Base-side evidence unavailable: {'; '.join(unavailable)}.)"
        return CI_FAILED_UNMERGED, detail
    if pending:
        state = "still running: " + ", ".join(pending[:8])
    elif passed:
        state = "every check has concluded clean; the next sweep should merge it"
    else:
        state = (
            "nothing non-spurious has checked this head, so no sweep will ever merge it "
            "(an absence of red is not a pass) — push a change CI can see, or merge by hand"
        )
    return "unmerged", (
        f"Pull request #{number} is armed with `{MERGE_ON_GREEN_LABEL}` but is NOT merged "
        f"yet — {state}. Arming the label buys a merge you do not have to perform; it does "
        "not end this session. You own this work through commit -> push -> PR -> CI -> "
        "squash-merge -> live verification, so stay with it until the merge lands. Watch "
        "on ONE slow watcher (`gh run watch <id> --interval 60`; a run here takes 30-34 "
        "minutes) and preflight `gh api rate_limit` — the 5,000/hr REST pool is shared "
        "with every other session and with this hook, which fails closed when it is spent."
    )


def _failing_ci_message(display: list[str]) -> str:
    """The blocking verdict for reds this pull request genuinely owns.

    `_stop` keys `ci_failed` off the "Failing" prefix, so every blocking variant
    must keep it.
    """
    return (
        "Failing CI: "
        + ", ".join(display[:8])
        + ". These run against the merged pull request's own head commit, so a later "
        "fix on main does not clear them: re-run the failed job "
        "(`gh run rerun --failed <run-id>`) once the cause is fixed, or carry the fix "
        "through a follow-up pull request with green CI of its own."
    )


def _head_check_runs(owner: str, repo: str, head_sha: str) -> list[dict[str, Any]]:
    """Every check run on ``head_sha``, following pagination to the end.

    A single `per_page=100` call silently truncated: PR #3629's head carries 101
    check runs, so a red beyond the first page was invisible and the gate failed
    OPEN — the one direction it may never fail. A short page means nothing is
    left; a full page with no `total_count` keeps paging rather than guessing the
    tail away. The 5-page cap bounds a pathological head's share of the API budget.
    """
    endpoint = f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/check-runs"
    runs: list[dict[str, Any]] = []
    for page in range(1, 6):
        query = urllib.parse.urlencode({"per_page": "100", "page": str(page)})
        payload = _get_json(f"{endpoint}?{query}")
        batch = payload.get("check_runs") or []
        runs.extend(batch)
        total = int(payload.get("total_count") or 0)
        if len(batch) < 100 or (total and len(runs) >= total):
            break
    return runs


def _started_stamp(run: dict[str, Any], *keys: str) -> str:
    """First non-empty stamp among ``keys`` — workflow runs and check runs name it differently."""
    for key in keys:
        value = str(run.get(key) or "")
        if value:
            return value
    return ""


def _parse_stamp(value: str) -> datetime | None:
    """A GitHub `...Z` stamp as a datetime, or None when it is absent or malformed."""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _merged_content_green(
    root: Path, owner: str, repo: str, merge_sha: str
) -> dict[str, Any] | None:
    """A completed+success ci.yml run whose head is a main DESCENDANT of ``merge_sha``.

    A descendant's tree contains the merge, so a full green run there proves the
    merged content passes — categorically stronger than arguing about any single
    check name. Ancestry alone is load-bearing, so unlike ``_render_status`` there
    is deliberately no created_at floor: a descendant carried this merge whenever
    its run happened.

    The fetch is best-effort because the candidate heads are brand-new main
    commits this checkout may not know yet, while a fixture or offline checkout
    must still be able to answer from its local view rather than erroring out.
    """
    if not merge_sha:
        return None
    try:
        _run(root, "git", "fetch", "origin", "main", timeout=90)
    except Exception:
        pass
    query = urllib.parse.urlencode({"branch": "main", "per_page": "20"})
    endpoint = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/ci.yml/runs"
    for run in _get_json(f"{endpoint}?{query}").get("workflow_runs", []):
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            continue
        head = str(run.get("head_sha") or "")
        if head and _is_ancestor(root, merge_sha, head):
            return run
    return None


def _base_side_confirmations(
    owner: str,
    repo: str,
    head_sha: str,
    head_branch: str,
    window: tuple[str, str],
    reference: str,
    names: list[str],
) -> dict[str, dict[str, str]]:
    """For each name in ``names``, the sibling heads that failed it inside ``window``.

    Returns name -> {sibling head_branch: sibling head_sha}. Independence is
    structural: a distinct head_branch that is not ours, on a sha that is not ours.
    Candidate runs must be `failure` runs created inside the half-open
    ``[floor, ceiling)`` the caller supplies.

    THE CEILING IS THE CALLER'S because the two callers are asking about different
    risks. `_check_ci` judges a MERGED pull request and passes
    ``(merged_at - 24h, merged_at)``: our content is on main from `merged_at`
    onward, so a sibling red after it can have OUR merge as its cause and is not
    evidence of anything. `_armed_pull_status` judges an UNMERGED head, whose
    content is on no shared base at all, so a sibling red on either side of our own
    red is equally probative and the window is centred on it. Passing the merged
    ceiling there would have discarded exactly the siblings that matter — under a
    fleet-wide red the other sessions' packs run continuously, and half of them run
    after ours.

    Candidates are keyed BY HEAD SHA, never per branch. A branch whose newer head
    dodged the defect does not retract the red its older head recorded: on the
    2026-07-26 live replay w2-support-page's 13:22 head had `ci-pack-1` green, and
    per-branch keep-newest silently discarded that branch's valid 12:51 red.

    Probe order is PROXIMITY to ``reference`` — the moment our own red started —
    not newest-first. This class of base-side defect is a temporal STRIPE (the
    chronicle red depends on the base vintage the merge ref happened to catch), so
    the siblings that ran nearest our failing check are the most probative, and
    proximity is immune to a burst of newer candidates crowding the listing.
    Newest-first UNDER-CONFIRMED a true base-side red in the field: with merged_at
    13:24:17Z and our `ci-pack-1` red started 12:06:25Z, a 13:14–13:22Z burst of
    other sessions' pushes filled the top five candidate slots and every one had
    `ci-pack-1` GREEN (their runs failed on other checks), while the 11:59–12:17Z
    band around our own red held `ci-pack-1` completed+failure on SIX of seven
    distinct branches (outbox 12:07:08, cool-allen 12:04:51, w1-china 12:09:53,
    zealous 12:10:30, inline-shim 11:59:41, pss-f2 12:17:30; only jolly 12:00:48
    was green). An undated candidate cannot be ranked and sorts last.

    A confirmation is matched by CHECK SUITE, never by the check run's own clock.
    `github.sha` is frozen at event time, so `started_at` on a check run measures
    queue latency, not tree vintage: under runner contention (load ~44) a run
    created 13:22:00 had its `ci-pack-1` job start at 13:25:04 — after the merge —
    while still testing the pre-merge tree. The suite id is the precise linkage
    (workflow runs carry `check_suite_id`, check runs carry `check_suite.id`): a
    rerun replaces check runs within the SAME suite and replays the frozen tree, so
    it stays valid evidence, whereas a fresh post-merge pull_request event mints a
    NEW suite and is not. A missing suite id on either side is not a confirmation.

    Costs one listing call plus one probe per candidate head (at most 8). The probe
    is UNFILTERED so a single call answers every candidate name; truncation there
    can only UNDER-confirm, which keeps the red.
    """
    floor, ceiling = window
    if not (floor and ceiling and head_branch and names):
        return {}
    reference_dt = _parse_stamp(reference) or _parse_stamp(ceiling)
    if reference_dt is None:
        return {}

    def in_window(stamp: str) -> bool:
        # GitHub emits second-precision `...Z` stamps, so plain string compares
        # are ordering-correct (same reasoning as `_render_status`).
        return bool(stamp) and floor <= stamp < ceiling

    def run_start(run: dict[str, Any]) -> str:
        return _started_stamp(run, "run_started_at", "created_at")

    def proximity(run: dict[str, Any]) -> tuple[int, timedelta]:
        parsed = _parse_stamp(run_start(run))
        if parsed is None:
            return 1, timedelta(0)
        return 0, abs(parsed - reference_dt)

    endpoint = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/ci.yml/runs"
    query = urllib.parse.urlencode({"event": "pull_request", "per_page": "100"})
    candidates: dict[str, dict[str, Any]] = {}
    for run in _get_json(f"{endpoint}?{query}").get("workflow_runs", []):
        if run.get("conclusion") != "failure":
            continue
        branch = str(run.get("head_branch") or "")
        sha = str(run.get("head_sha") or "")
        if not branch or branch == head_branch or not sha or sha == head_sha:
            continue
        if not in_window(run_start(run)):
            continue
        # One probe per head sha. The listing is newest-first, so the first run
        # seen for a sha is the one whose suite owns that head's current checks.
        candidates.setdefault(sha, run)

    wanted = set(names)
    found: dict[str, dict[str, str]] = {}
    for probe in sorted(candidates.values(), key=proximity)[:8]:
        sha = str(probe.get("head_sha") or "")
        branch = str(probe.get("head_branch") or "")
        suite = probe.get("check_suite_id")
        listing = _get_json(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs"
            f"?{urllib.parse.urlencode({'per_page': '100'})}"
        ).get("check_runs", [])
        for run in listing:
            name = str(run.get("name") or "")
            if name not in wanted:
                continue
            if run.get("status") != "completed" or run.get("conclusion") != "failure":
                continue
            run_suite = (run.get("check_suite") or {}).get("id")
            if suite is None or run_suite is None or run_suite != suite:
                continue
            # Keyed by branch: two heads of one branch are one independent observation.
            found.setdefault(name, {})[branch] = sha
        if all(len(found.get(name) or {}) >= 2 for name in wanted):
            break
    return found


def _check_ci(
    root: Path,
    owner: str,
    repo: str,
    head_sha: str,
    merge_sha: str,
    merged_at: str,
    head_branch: str,
    base_sha: str = "",
) -> tuple[bool, str]:
    """Judge the merged pull request's OWN head commit, then ask whose red it is.

    Head-only scoring stays deliberate: main's combined status is the product of
    every concurrent session's merges, so scoring against it would let an
    unrelated green main mask this pull request's red check (and an unrelated red
    one block a clean ship). The head commit is the only sha that answers "did
    THIS work pass".

    What a head sha cannot answer is WHOSE red it is. A defect already on main at
    pull time lands on the pull request's merge ref, and there it is PERMANENT:
    `gh run rerun` replays the frozen `refs/pull/N/merge` tree — a merged pull
    request's merge ref never recomputes against a healed base — and a follow-up
    pull request is impossible when the fix is already on main. Observed
    2026-07-26: the chronicle gate-1 staleness window (heal owned by PR #3634,
    still open) pinned merged PR #3629's `ci-pack-1` red forever; earlier #3503
    inherited a `tier-gate` red from #3488 the same way. Both sessions shipped
    green work and were forced into the `SHIP LOOP BLOCKED:` escape.

    The obvious comparisons are structurally unavailable in THIS repo (verified
    2026-07-26). ci.yml triggers on `pull_request` + `workflow_dispatch` ONLY, so
    main commits carry ZERO ci.yml check runs — merge base 8773e511b79 held only
    third-party "Workers Builds"/"Supabase Preview" app runs — which kills
    "compare the same check on the merge-base sha". ci-main-heartbeat.yml is
    schedule-only and mirrors a curated subset of individual pure-guard job names
    (nav-gap, tier-gate, …); it never runs `ci-pack-N`, which is exactly where
    suite failures like the chronicle pair surface, so name-matching against
    heartbeat conclusions cannot reach a pack. And a pack's legacy member names
    exist only as `if: false` definitions that publish `skipped` check runs —
    member granularity is not available at all.

    So the evidence model uses the two sources that DO exist.

    E1, merged-content-green (strongest; clears EVERY bad conclusion): a
    completed+success ci.yml run on branch=main whose head_sha is a main
    descendant of merge_sha. A descendant's tree contains the merge, so one full
    green run there proves the merged content passes and no per-name argument is
    needed. No ci.yml run on main has ever existed (total_count=0 today), which is
    the point: E1 is the OPERATOR'S DELIBERATE UNBLOCK LEVER — dispatch ci.yml on
    main once the base-side cause is healed and every pinned session clears at
    once. This mirrors `_render_status` accepting a dispatched render on a
    descendant. Since 2026-08-19, E1 is also the ONE clearing path for a frozen
    semantic `authority_changed=true` head whose only nonunit blocker is the
    authority freeze itself: the descendant run executes ON the merged authority,
    so it is proof of main under the new gate rather than the candidate-era
    evidence the fence forbids. Infrastructure ambiguity stays outside it.

    E2, base-side-red confirmation (per check name, `failure` conclusions only):
    the SAME name concluded `failure` on at least TWO INDEPENDENT concurrent
    sibling pull-request heads — distinct head_branch values, neither ours, on
    shas that are not ours — in runs created before this merge and no more than 24h
    before it. Run-level conclusions are NEVER evidence: in the 2026-07-26
    12:50–13:03Z window three sibling ci.yml runs (gracious-moser, brain-symmetric,
    brain-consistency) concluded failure with `ci-pack-1` GREEN — their own bugs —
    so nothing short of a per-head probe of the same NAME counts. The candidate run
    must PREDATE merged_at: an open pull request's merge ref recomputes against the
    moving base, so a post-merge sibling red can have OUR merged content as its
    cause. Inside that window, heads are probed in order of PROXIMITY to the moment
    our own red started (this defect class is a temporal stripe in the base
    vintage), and the second hop matches on CHECK SUITE rather than on the check
    run's clock (a job queued late under contention still tests the event-frozen
    tree). Both rules replaced weaker ones that under-confirmed a genuine base-side
    red on the live replay; `_base_side_confirmations` carries the dated evidence.
    The bar is two distinct BRANCHES — several heads of one branch count once —
    because pack-level names are the coarsest granularity available (see above):
    `ci-pack-1` fronts many jobs, so one sibling sharing the name is a real
    coincidence rather than a shared cause. Evidence is contemporaneous by
    construction (one listing page is roughly the last few hours on this repo),
    which matches when the guard actually evaluates: right after the merge.

    Fail-closed throughout. A lone sibling confirmation keeps the red. An absent
    merged_at, head_branch, or merge_sha skips the gate that depends on it rather
    than assuming it, and a missing check-suite id on either side of a probe is not
    a confirmation. The two gates degrade independently — either one's failure
    means "that gate found no exclusions" and is named in the reason, never a
    reclassified or swallowed verdict. Conclusions other than `failure`
    (cancelled, timed_out) are not E2-excludable, because rerunning the frozen
    tree genuinely can green those, while E1 clears them wholesale by proving the
    content. Pending checks keep the "CI still running" verdict even when every
    bad check is excluded. And the head listing is paginated for the same
    fail-closed reason: PR #3629's head carries 101 check runs, so the old single
    `per_page=100` call could hide a red past the first page.
    """
    runs = _head_check_runs(owner, repo, head_sha)
    if not runs:
        return False, "No CI check runs were found for the pull-request head."
    # ONE definition of "not a red", shared with `_split_head_runs` above and with
    # the sweeper's own copy in `scripts/merge_on_green.py` — and it is `_is_non_
    # binding_check`, not `_is_spurious_check`. This loop called the narrower one
    # while the comment claimed parity, so it alone counted the ci-authority
    # inactive base context as a red we own and blocked sessions whose work had
    # merged GREEN on a context that is red on every PR in this repository.
    non_red = NON_RED_CONCLUSIONS
    bad: list[tuple[str, str]] = []
    pending: list[str] = []
    failure_starts: list[str] = []
    for run in runs:
        name = str(run.get("name") or "unnamed check")
        if _is_non_binding_check(name):
            continue
        # The inactive pilot authority context, excluded on the MERGED path too
        # (2026-08-16). `_red_pairs` and `_split_head_runs` above have always
        # skipped it and `scripts/merge_on_green.py` carries the same rule, but
        # this loop did not — so the three disagreed about one check on one head.
        # Measured on #5765's merged head 8c279038: `_red_pairs` returned [] while
        # this loop returned [("ci-authority/codex/merge-queue-pilot","failure")],
        # and the session was blocked after a fully green merge. It is worse than
        # a plain false red: a non-empty `bad` is what ARMS the semantic-evidence
        # path, and a merged head can no longer bind its proof base (GitHub drops
        # `pull_requests` from check-runs once the PR closes), so the block
        # surfaced as "advertised semantic evidence is unusable ... does not
        # identify the exact PR proof base" — a message about proof plumbing that
        # named nothing the session could fix, for a check that is BY DESIGN a
        # retarget-invalidation receipt. Every PR touching a ci-authority path
        # hit this. `ci-authority/main` stays binding here exactly as elsewhere;
        # this skips ONLY the one literal pilot context, and widens nothing.
        # (The literal that stood here is gone: `_is_non_binding_check` above
        # already answers it, and leaving a second spelling behind is how this
        # loop drifted from its siblings in the first place.)
        if run.get("status") != "completed":
            pending.append(name)
        elif run.get("conclusion") not in non_red:
            conclusion = str(run.get("conclusion"))
            bad.append((name, conclusion))
            if conclusion == "failure":
                stamp = _started_stamp(run, "started_at")
                if stamp:
                    failure_starts.append(stamp)
    if not bad:
        # The green path costs exactly one API call and touches no git: evidence
        # is only ever gathered to argue about a red.
        if pending:
            return False, "CI still running: " + ", ".join(pending[:8])
        # AN ABSENCE OF RED IS NOT A PASS — the other edge of the exclusion above,
        # and the reason the sweeper's verdict has an `unproven` state at all
        # (#4779; `scripts/merge_on_green.py`: "a head whose every surviving check
        # concluded `skipped`/`neutral` is that same nothing wearing a name").
        #
        # `NON_RED_CONCLUSIONS` holds `skipped` and `neutral`, so this return has
        # always been reachable by a head that proved NOTHING. What kept such a
        # head out of it was an accident: the inactive pilot context is red on
        # every pull request in this repository, so `bad` was never empty for it.
        # Excluding that context — correctly, #5773/#5776 — removed the accident
        # and left the hole. Measured on 65f9669f: a merged head whose every
        # binding check was `skipped`, one whose only check was `neutral`, and one
        # carrying NOTHING but the pilot and the spurious Cloudflare X all
        # returned `(True, "")`. The guard released a session on a head with no CI
        # verdict whatsoever, which is the failure it exists to prevent, in the
        # direction that costs the most: a false red pins a session, a false green
        # ships unproven work.
        #
        # So require what the sweeper requires of the same head: one check that
        # actually said `success`. Excluding a check from the reds must never
        # promote the head to proven.
        #
        # Scoped to THIS return deliberately. The two green returns below are
        # reached only after a real red was argued away on evidence, which means
        # CI demonstrably ran; this is the cheap path that gathers nothing. It
        # cannot strand a normal merge either — the sweeper refuses to merge a
        # head with no `success` at all, and even the records-only PR #5772
        # carried 10 of them.
        binding = [
            run
            for run in runs
            if not _is_non_binding_check(str(run.get("name") or "unnamed check"))
        ]
        if not any(run.get("conclusion") == "success" for run in binding):
            names = [str(run.get("name") or "unnamed check") for run in binding]
            return False, (
                "Failing CI: the merged head carries no affirmative passing check "
                f"({len(binding)} binding check(s) concluded, none `success`"
                + (f": {', '.join(names[:8])}" if names else "")
                + "). An absence of red is not a pass."
            )
        return True, ""

    semantic_notes: list[str] = []
    try:
        loaded = (
            _semantic_evidence_for_head(
                owner,
                repo,
                head_sha,
                check_runs=runs,
                # A MERGED head has no PR associations left to bind its base with
                # (2026-08-15): GitHub drops `pull_requests` from check-runs once the
                # pull request closes — measured on #5754's ci-gate, `n_prs: 0` on BOTH
                # entries — so `_semantic_pr_base_sha` returns None here every time and
                # the loader then refused with "does not identify the exact PR proof
                # base". That is the same shape as the skipped-gate artifact above: a
                # merged head cannot repair its own metadata, and no session-side action
                # exists. The merged pull request record itself still carries the
                # authoritative base, so pass it as the fallback. Preference order is
                # deliberate — the check-run-bound base is immutable and exact, so it
                # still wins whenever it is present (open heads, and any future API that
                # keeps associations after merge).
                expected_base_sha=(
                    _semantic_pr_base_sha(runs, head_sha) or base_sha or None
                ),
            )
            if _head_can_advertise_semantic_evidence(runs)
            else None
        )
        gate = _semantic_gate(loaded)
    except RateLimited:
        raise
    except Exception as exc:
        return False, (
            "Failing CI: advertised semantic evidence is unusable and may not "
            f"downgrade to legacy reasoning ({str(exc)[:500]})."
        )
    if gate is not None:
        semantic_resolved = bool(gate.clear)
        witness_notes: list[str] = []
        unclearable_notes: list[str] = []
        unresolved_units: list[Any] = []
        # None until the artifact window is actually read. Every consumer below
        # treats None as "inventory unknown", which keeps the fail-closed
        # reading when the witness search itself raised.
        inventory: Any = None
        if not gate.clear:
            if _semantic_has_nonunit_blocker(loaded, gate):
                refusal = (
                    "Failing semantic CI on the frozen merged head: "
                    f"{_semantic_nonunit_refusal(loaded)}. Descendant unit healing "
                    "cannot erase infrastructure or authority ambiguity."
                )
                if not _authority_freeze_is_sole_nonunit_blocker(loaded, gate):
                    return False, refusal
                # An authority-only freeze has exactly ONE clearing path, and it
                # is E1 above, not anything semantic: a completed+success ci.yml
                # run on a main DESCENDANT of this merge. That run executes ON the
                # merged authority, so it is proof of main under the new gate —
                # the post-merge transposition of the pre-merge standard "an
                # authority-changing PR needs main itself green" — and it uses
                # none of the candidate-era classification machinery the fence
                # exists to distrust. Before 2026-08-19 this branch returned the
                # refusal unconditionally, which made an authority-changing PR
                # merged while main was red UNCLEARABLE FOREVER (its own run is
                # frozen at merge; unit healing is disabled here by design): a
                # session that performed an operator-granted main-red-repair
                # merge (#5954/#5969/#6002) re-blocked on every Stop for the rest
                # of its life and could only exit by re-filing the same
                # `SHIP LOOP BLOCKED:` report dozens of times. E1 was already
                # doctrine on the legacy path below ("the OPERATOR'S DELIBERATE
                # UNBLOCK LEVER ... clears EVERY bad conclusion") — advertising
                # semantic evidence must not make a head strictly less clearable
                # than having none. Fail-closed: an unanswerable probe keeps the
                # refusal, and pending checks still outrank a clearing.
                try:
                    green = _merged_content_green(root, owner, repo, merge_sha)
                except Exception as exc:  # noqa: BLE001 — unanswerable keeps the freeze
                    return False, (
                        f"{refusal} The one clearing path — a full ci.yml run "
                        "concluding success on a main descendant of this merge — "
                        f"could not be probed: {str(exc)[:200].strip()}."
                    )
                if green is None:
                    return False, (
                        f"{refusal} This authority-only freeze clears through "
                        "exactly one lever: a completed ci.yml run concluding "
                        "SUCCESS on branch=main whose head is a main descendant of "
                        "this merge (proof of main under the merged authority "
                        "itself, never candidate-era evidence). Preflight for an "
                        "in-flight baseline (`gh run list --workflow ci.yml "
                        "--branch main --json databaseId,status --jq "
                        "'[.[]|select(.status!=\"completed\")]'`) and WATCH it "
                        "(`gh run watch <id> --interval 60`) rather than "
                        "re-dispatching over it; dispatch `gh workflow run ci.yml "
                        "--ref main` only over a clear field. The next Stop "
                        "re-reads the result."
                    )
                if pending:
                    return False, "CI still running: " + ", ".join(pending[:8])
                return True, (
                    "Ignored frozen authority_changed semantic evidence on the "
                    f"merged head: full ci.yml run {green.get('id')} concluded "
                    "success on main descendant "
                    f"{str(green.get('head_sha') or '')[:12]}, proving the merged "
                    "content green under the merged authority (E1). The head's "
                    "red — "
                    + ", ".join(f"{name} ({conclusion})" for name, conclusion in bad[:8])
                    + " — stays pinned to the frozen pull_request merge ref "
                    "(base-side)."
                )
            if not gate.blocking:
                return False, (
                    "Failing semantic CI on the frozen merged head: the artifact "
                    "is not clear but exposes no healable semantic unit ("
                    f"{_semantic_nonunit_refusal(loaded)}). Descendant healing is "
                    "unavailable."
                )
            try:
                # Candidate commits are often newer than this checkout. Fetch once;
                # every per-unit witness then uses real local git ancestry.
                try:
                    _run(root, "git", "fetch", "origin", "main", timeout=90)
                except Exception:
                    pass
                candidates = _recent_main_semantic_evidence(owner, repo)
                ancestry_cache: dict[tuple[str, str], bool] = {}

                def ancestry_witness(ancestor: str, descendant: str) -> bool:
                    key = (ancestor, descendant)
                    if key not in ancestry_cache:
                        ancestry_cache[key] = _is_ancestor(root, ancestor, descendant)
                    return ancestry_cache[key]

                inventory = semantic_proof.main_role_job_inventory(
                    merge_sha,
                    candidates,
                    ancestry_witness,
                    max_candidates=SEMANTIC_RUN_LOOKBACK,
                )
                for unit in gate.blocking:
                    witness = semantic_proof.find_descendant_pass_witness(
                        unit.logical_job_id,
                        unit.proof_id,
                        merge_sha,
                        candidates,
                        ancestry_witness,
                        old_step_spec_sha=unit.step_spec_sha256,
                        max_candidates=SEMANTIC_RUN_LOOKBACK,
                    )
                    if witness is None:
                        unresolved_units.append(unit)
                        continue
                    witness_notes.append(
                        f"{unit.logical_job_id}/{unit.proof_id} healed by main run "
                        f"{getattr(witness, 'workflow_run_id', '?')} at "
                        f"{str(getattr(witness, 'tested_tree_sha', '') or '?')} "
                        f"(old spec "
                        f"{str(getattr(witness, 'old_step_spec_sha', '') or '?')}, "
                        f"witness spec "
                        f"{str(getattr(witness, 'witness_step_spec_sha', '') or '?')}, "
                        "contract_changed="
                        f"{str(bool(getattr(witness, 'contract_changed', False))).lower()})"
                    )
                # THE PERMANENT-TRAP FENCE (2026-08-19, PR #5936).
                #
                # `find_descendant_pass_witness` clears a frozen blocking unit
                # only with a main-role PASS naming the same `logical_job_id`.
                # But semantic ELIGIBILITY is role-dependent: `ci.yml` plans the
                # merge gate `--gate code`, while the 74 `gate: data` jobs moved
                # to `data-health.yml` (W2, research/
                # CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md), a lane
                # that emits no main-role semantic evidence at all. A head
                # planned before that split froze blocking units for jobs main
                # will never name again, so the witness search could not
                # succeed on any future run — measured on #5936's head run
                # 32223270543 (`house-law-registry`, `signal-contract`) against
                # seven consecutive post-merge main runs plus an hour-long
                # ancestry watcher. A job that can never clear must never block:
                # the session was pinned by the guard's own bookkeeping, not by
                # anything wrong with its work.
                #
                # Fail-closed in both directions. The inventory is read from the
                # SAME bounded artifacts the witness search already fetched (no
                # extra API calls, no second source of truth), it counts only
                # ancestry-valid main artifacts, and with fewer than
                # `MIN_INVENTORY_ARTIFACTS` of them it answers "unknown" and
                # every unit stays blocking exactly as before. Retirement is
                # never silent: the excluded units are named in the release
                # note, so a genuinely broken job cannot vanish from the record.
                retired = semantic_proof.unclearable_units(
                    unresolved_units, inventory
                )
                if retired:
                    retired_ids = {id(unit) for unit in retired}
                    unresolved_units = [
                        unit
                        for unit in unresolved_units
                        if id(unit) not in retired_ids
                    ]
                    for unit in retired:
                        unclearable_notes.append(
                            f"{unit.logical_job_id}/{unit.proof_id} retired as "
                            "structurally unclearable: "
                            + semantic_proof.format_main_eligibility(
                                unit, inventory
                            )
                            + " — no main-role run plans this logical job, so no "
                            "descendant PASS can ever exist for it"
                        )
                semantic_resolved = not unresolved_units
            except Exception as exc:
                unresolved_units = list(gate.blocking)
                semantic_notes.append(
                    "descendant semantic witness search unavailable: "
                    + str(exc)[:300]
                )

        if not semantic_resolved:
            blocked_units = list(unresolved_units or gate.blocking)
            detail = "; ".join(_semantic_unit_details(blocked_units))
            # Whether waiting is even capable of helping is the one fact a
            # pinned session cannot derive on its own, so state it per unit:
            # `main-eligible=yes` means a later main run can still emit the PASS
            # that clears this, `unknown` means the inventory was unreadable.
            eligibility = [
                f"{unit.logical_job_id}/{unit.proof_id}: "
                + semantic_proof.format_main_eligibility(unit, inventory)
                for unit in blocked_units[:8]
                if inventory is not None
            ]
            if eligibility:
                detail += "; " + "; ".join(eligibility)
            if unclearable_notes:
                detail += "; " + "; ".join(unclearable_notes)
            if semantic_notes:
                detail += "; " + "; ".join(semantic_notes)
            return False, (
                "Failing semantic CI on the frozen merged head: "
                f"{detail}. No ancestry-valid descendant PASS was found in the "
                f"bounded {SEMANTIC_RUN_LOOKBACK}-artifact main history."
            )

        # A valid semantic artifact makes pack identities transport-only. A
        # descendant PASS also supersedes the frozen ci-gate failure for those
        # exact semantic units, even when its own overall workflow stayed red.
        def semantic_transport(entry: tuple[str, str]) -> bool:
            name = entry[0]
            # A retirement supersedes the frozen `ci-gate` for the same reason
            # a descendant PASS does: the units that reddened it are no longer
            # a live verdict on this head. Leaving `ci-gate` behind would keep
            # the exact trap this fence removes, one name further down.
            return bool(re.fullmatch(r"ci-pack-\d+", name)) or (
                bool(witness_notes or unclearable_notes) and name == "ci-gate"
            )

        bad = [entry for entry in bad if not semantic_transport(entry)]
        semantic_notes.extend(witness_notes)
        semantic_notes.extend(unclearable_notes)
        if not bad:
            if pending:
                return False, "CI still running: " + ", ".join(pending[:8])
            inherited = "; ".join(_semantic_unit_details(gate.inherited))
            note = "; ".join(semantic_notes)
            if inherited:
                note = (note + "; " if note else "") + (
                    "exact-base inherited semantic failure: " + inherited
                )
            return True, note

    display = {entry: f"{entry[0]} ({entry[1]})" for entry in bad}
    excluded: set[tuple[str, str]] = set()
    evidence: dict[str, list[str]] = {}
    notes: list[str] = list(semantic_notes)
    unavailable: list[str] = []

    try:
        green = _merged_content_green(root, owner, repo, merge_sha)
    except Exception as exc:
        green = None
        unavailable.append(f"merged-content-green: {str(exc)[:200].strip()}")
    if green is not None:
        excluded.update(bad)
        proof = str(green.get("head_sha") or "")
        notes.append(
            "Ignored failing CI on the merged head: "
            + ", ".join(display[entry] for entry in bad[:8])
            + f" — full ci.yml run {green.get('id')} concluded success on main descendant "
            f"{proof[:12]}, proving the merged content green; the head's red is pinned to "
            "the frozen pull_request merge ref (base-side)."
        )
    else:
        names: list[str] = []
        for name, conclusion in bad:
            if conclusion == "failure" and name not in names:
                names.append(name)
        # Proximity anchor: when OUR OWN red started. Same-format `...Z` stamps, so
        # the string min is the earliest one. Nothing dated falls back to the merge.
        reference = min(failure_starts) if failure_starts else merged_at
        # Half-open [merged_at - 24h, merged_at): our merged content is on main
        # from `merged_at` onward, so only a sibling red that PREDATES it is
        # provably not our own doing.
        merged_dt = _parse_stamp(merged_at)
        window = (
            (merged_dt - BASE_SIDE_WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ") if merged_dt else "",
            merged_at,
        )
        try:
            confirmations = _base_side_confirmations(
                owner, repo, head_sha, head_branch, window, reference, names
            )
        except Exception as exc:
            confirmations = {}
            unavailable.append(f"base-side confirmation: {str(exc)[:200].strip()}")
        for name in names:
            heads = confirmations.get(name) or {}
            if len(heads) < 2:
                continue
            cited = [f"{sha[:7]}@{branch}" for branch, sha in heads.items()]
            evidence[name] = cited
            excluded.add((name, "failure"))
            notes.append(
                f"Ignored base-side CI: {name} (failure) — the same check failed on "
                f"{len(heads)} independent concurrent PR head(s) ({', '.join(cited)}) before "
                "this merge; the red pre-existed on the shared base, and re-runs replay the "
                "frozen merge ref so it can never self-clear."
            )

    unexcluded = [display[entry] for entry in bad if entry not in excluded]
    if not unexcluded:
        # A still-running check outranks an exclusion: coverage is unknown, not clear.
        if pending:
            return False, "CI still running: " + ", ".join(pending[:8])
        return True, " ".join(notes)
    message = _failing_ci_message(unexcluded)
    if evidence:
        cited = "; ".join(f"{name} ({', '.join(evidence[name])})" for name in evidence)
        message = f"{message} (Ignored as base-side: {cited}.)"
    if unavailable:
        message = f"{message} (Base-side evidence unavailable: {'; '.join(unavailable)}.)"
    return False, message


# Fail-closed fallback used only when the workflow push filters cannot be read.
# The normal path reads render.yml's explicit builder allowlist directly, so
# builders owned by nightly/collector/research lanes no longer create an
# impossible ship-loop wait for a heavy render that deliberately does not run
# them. These four shared inputs still belong to the fallback because they
# rewrite every page in site/.
_RENDER_INPUT_PATHS = {
    "scripts/inject_data_base.py",
    "scripts/externalize_css.py",
    "scripts/optimize_assets.py",
    "lib/pages.py",
}
# The old workflow admitted every top-level build_*.py. Keep that broad rule
# only as the unreadable-filter fallback: ignorance must over-require, while a
# successfully parsed explicit allowlist is authoritative.
_FALLBACK_RENDER_BUILDER = re.compile(r"^scripts/build_[^/]*\.py$")

# The two render lanes. `render.yml` is the heavy self-hosted market renderer;
# #3834 split the data-free public surfaces out of it into `public-render.yml`,
# a GitHub-hosted fast lane that renders the Jinja public pages, re-stamps the
# immutable assets, and pushes the site/ + templates/ delta straight to main.
# `_stop` walks them in this order, and each satisfies its own half of the gate.
_HEAVY_RENDER_WORKFLOW = "render.yml"
_PUBLIC_RENDER_WORKFLOW = "public-render.yml"
_RENDER_LANE_HEAVY = "render"
_RENDER_LANE_PUBLIC = "public-render"
_WORKFLOW_DIR = Path(".github") / "workflows"

_YAML_LIST_ITEM = re.compile(
    r"""^-[ \t]+(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^#\s].*?))[ \t]*(?:\#.*)?$"""
)


def _workflow_push_paths(workflow: Path) -> list[str]:
    """A workflow's ordered ``on.push.paths`` filter, read without PyYAML.

    A line scanner rather than a parser, on purpose. This hook runs under
    whatever ``python3`` the Stop event hands it, so every third-party import is
    one more way for a completion gate to die outright — and PyYAML would be the
    wrong parser anyway: its YAML 1.1 resolver turns a workflow's ``on:`` key
    into the boolean ``True``, a footgun that has no place in a gate whose only
    unforgivable failure mode is releasing a session it should have held.

    Both lanes write the block as plain quoted scalars, one per line, which the
    scanner below reads exactly. Anything it does not recognise — a flow list, a
    nested mapping, a missing trigger, an unreadable file — yields ``[]``, and
    every caller reads that as ignorance rather than permission.
    """
    try:
        lines = workflow.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    on_indent = push_indent = paths_indent = -1
    stage = "on"
    found: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if stage == "on":
            if indent == 0 and stripped == "on:":
                on_indent, stage = indent, "push"
            continue
        if stage == "push":
            if indent <= on_indent:
                return []  # left the trigger block without a push filter
            if stripped == "push:":
                push_indent, stage = indent, "paths"
            continue
        if stage == "paths":
            if indent <= push_indent:
                return []  # a push trigger with no `paths:` filter at all
            if stripped == "paths:":
                paths_indent, stage = indent, "items"
            continue
        if indent <= paths_indent:
            break
        match = _YAML_LIST_ITEM.match(stripped)
        if match is None:
            return []
        value = match.group("dq")
        if value is None:
            value = match.group("sq")
        if value is None:
            value = (match.group("bare") or "").strip()
        if not value:
            return []
        found.append(value)
    return found


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def _github_glob(pattern: str) -> re.Pattern[str]:
    """Compile one GitHub path-filter glob. ``*``/``?`` never cross ``/``; ``**`` does.

    The metacharacters neither lane uses (``+``, character classes) are escaped to
    literals rather than modelled. That under-matches if one ever appears, which
    reads as "public-render does not claim this" and leaves the heavy lane's
    demand standing — the fail-closed direction.
    """
    compiled = _GLOB_CACHE.get(pattern)
    if compiled is None:
        parts: list[str] = []
        index = 0
        while index < len(pattern):
            char = pattern[index]
            if char == "*":
                if pattern[index + 1 : index + 2] == "*":
                    parts.append(".*")
                    index += 2
                    continue
                parts.append("[^/]*")
            elif char == "?":
                parts.append("[^/]")
            else:
                parts.append(re.escape(char))
            index += 1
        compiled = re.compile("^" + "".join(parts) + "$")
        _GLOB_CACHE[pattern] = compiled
    return compiled


def _path_filter_includes(item: str, patterns: list[str]) -> bool:
    """Whether a push filter fires for ``item``. LAST matching pattern wins.

    GitHub evaluates the list in order and lets a later entry overturn an
    earlier one, which is the whole mechanism render.yml uses for
    ``templates/**`` followed by its public-surface negations. Reading it as
    "any negation excludes" would happen to agree today, but only by the
    accident that no positive pattern currently follows a negation of the same
    path — exactly the kind of accident that rots the next time someone
    reorders the block.
    """
    verdict = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        if _github_glob(pattern[1:] if negated else pattern).match(item):
            verdict = not negated
    return verdict


def _render_lane_filters(root: Path) -> tuple[list[str], list[str]]:
    """Both lanes' push filters, parsed from the workflows themselves.

    Never hardcoded here. The #3834 split lives in exactly two files, and the
    guard's job is to agree with them rather than to carry a third copy that
    drifts — the drift is precisely what produced the false gate this function
    exists to close. ``tests/test_public_render_fastlane.py`` pins both halves of
    the split; this reads the same two lists at runtime.

    Either list coming back empty disables the ownership test entirely (see
    ``_public_render_owns``), which restores the pre-split behaviour of
    demanding a render.yml run for every templates/ path — the fail-CLOSED
    direction, and the same stance ``_plain_copy_pairs`` takes on an unreadable
    pair list.
    """
    heavy = _workflow_push_paths(root / _WORKFLOW_DIR / _HEAVY_RENDER_WORKFLOW)
    public = _workflow_push_paths(root / _WORKFLOW_DIR / _PUBLIC_RENDER_WORKFLOW)
    return heavy, public


def _public_render_owns(item: str, filters: tuple[list[str], list[str]]) -> bool:
    """Whether ``public-render.yml`` — and NOT ``render.yml`` — renders ``item``.

    Both halves are required. A path public-render claims but render.yml also
    still matches is not a lane split, it is a double-fire, and the heavy lane's
    demand stands. A path render.yml excludes but public-render never claims is
    a dead wire: nothing renders it, and this function must not pretend a lane
    exists to satisfy.
    """
    heavy, public = filters
    if not heavy or not public:
        return False
    return _path_filter_includes(item, public) and not _path_filter_includes(item, heavy)


def _plain_copy_pairs(root: Path) -> set[str]:
    """Names under ``templates/`` that also ship as a committed ``site/`` copy.

    Loaded from ``scripts/check_template_site_sync.find_pairs`` — the very
    enumeration CI's ui.template_site_sync gate walks — rather than re-deriving
    the rule here, so the exemption in ``_render_lanes_for_paths`` and the sync
    law can never drift apart as pairs are added or retired (56 today).

    Every failure path returns the empty set, which REQUIRES a render rather
    than skipping one: an unreadable pair list is ignorance, not permission.
    """
    module_path = root / "scripts" / "check_template_site_sync.py"
    # It is loaded by PATH, never registered in sys.modules, and its own
    # `sys.path.insert` is rolled back: reading the pair list must not leave a
    # repo root on the import path of whatever process is asking.
    saved_path = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location("_mm_template_site_sync", module_path)
        if spec is None or spec.loader is None:
            return set()
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {name for name, _tpl, _site in module.find_pairs(root)}
    except Exception:
        return set()
    finally:
        sys.path[:] = saved_path


def _render_lanes_for_paths(
    changed: list[str], pairs: set[str], filters: tuple[list[str], list[str]]
) -> set[str]:
    """Which render lanes ``changed`` actually needs — possibly neither.

    render.yml's push filter USED to be a bare `templates/**`, and its builder
    rule used to admit every top-level `scripts/build_*.py`, so those paths all
    demanded a render from the heavy self-hosted lane. Three things have since
    made that read wrong, and each one produced its own unsatisfiable gate.

    First, the lane only produces two things: re-baked `.j2` pages and the `?v=`
    content-hash re-stamp. A paired PLAIN-COPY asset — a non-.j2 file under
    templates/ that also ships as `site/<name>` — is neither. Its site/ copy is
    committed straight to main, and the VPS `macro-update` cron pulls main every
    3 minutes, so those bytes are live within minutes whether render ever runs or
    not.

    Demanding a render for them was a real, recurring false gate. Observed
    2026-07-26 on PR #3671 (templates/mm_brain.js + site/mm_brain.js, no .j2):
    merged 14:30Z, VPS served the new bytes by 14:33Z, byte-verified at three
    successive box HEADs — and the guard still refused Stop with `render_pending`
    for 40+ minutes, while 28 of the last 30 render.yml runs concluded
    `cancelled` and none concluded `success` (a repo-wide treadmill jam from a
    concurrent merge spree, unrelated to the PR). House law forbids cancelling
    or re-running a shared in-flight render to unblock a session, so the only
    exit was the `SHIP LOOP BLOCKED:` escape — which reads as a failed ship when
    the deploy had in fact succeeded. `go-live-deploy-mechanics` has recorded
    this as "a real false gate" since #3464/#3486.

    KNOWN AND ACCEPTED LIMIT: the exemption gives up the `?v=` re-stamp for the
    assets that carry one. The Caddyfile pins `?v=`-carrying requests to
    `max-age=31536000, immutable` for an enumerated list (theme.js, live.js,
    theme.css, product-nav-icons.css, onboard.*, landing.css, account.js,
    nav_market.js, supabase.js, data_base.js, chat*.css, assets/{css,landing}/*),
    so for THOSE a warm-cache visitor keeps the old body until a render re-hashes
    the pages that reference them (`asset-stamp-frozen-not-stable`). Assets off
    that list — mm_brain.js among them, which is why #3671 was fully live — fall
    back to `max-age=300, must-revalidate` and go live on the next revalidate.
    New visitors always get fresh bytes either way. Trading a stamp refresh for
    an unsatisfiable gate is the operator's call, taken deliberately.

    A `.j2` page, a builder, a sweep script, or anything else under templates/
    (`templates/fonts/`, a subdirectory, an unpaired asset) still requires a
    render. So does a paired asset whose `site/` twin is NOT in the same commit:
    that is a one-sided edit the sync gate rejects anyway, and it means the live
    bytes have not moved. Fail-closed on everything the pair list cannot vouch for.

    Second — and this is the same class of false gate, one lane over — #3834
    stopped `templates/**` being one lane at all. The public/marketing surfaces
    were split into `public-render.yml`, and render.yml's push filter now carries
    explicit template negations, while its builder trigger is now a positive
    allowlist that simply omits `scripts/build_public_pages.py`, so the scarce
    self-hosted market renderer is never occupied merely to bake the three
    data-free public pages. For those paths a push-triggered render.yml run
    CANNOT EXIST, so demanding one blocked forever. Observed 2026-07-28 on
    PR #3897 (templates/plans.html.j2 + site/plans.html): merged as 7fe17018,
    public-render.yml run 30349907107 concluded `success` on that exact sha and
    pushed d4ac971df7a, https://www.mastermind-x.com/plans.html was browser-
    verified live in production — and the guard returned `render_pending`
    regardless, with no run it could ever have been waiting for.

    Third, the old `scripts/build_*.py` wildcard admitted 283 top-level builders
    while this workflow executed or transitively imported only 101 of them.
    Changes to nightly collectors, research factories, marketing builders, and
    live-flow producers therefore queued a 50-100 minute render whose body never
    invoked the changed module. render.yml now carries the executable positive
    ownership list. When both workflow filters parse successfully, that list is
    authoritative here too: an unclaimed builder owes no render and cannot leave
    the ship loop waiting on a run GitHub never created.

    So the question is not one bool but which LANE owes the work. A path
    public-render.yml claims and render.yml excludes belongs to
    ``_RENDER_LANE_PUBLIC``, and ``_stop`` satisfies it from that workflow's own
    runs under the same coalescing rule. Ownership is parsed out of both
    workflows at runtime (``_render_lane_filters``) rather than transcribed here,
    so the guard and the split cannot drift; when the parse cannot vouch for a
    path the ownership test goes silent and the heavy lane's demand stands,
    exactly as before the split.

    The pair exemption is applied FIRST and still wins, including for the public
    surfaces it covers. Those bytes are live on the VPS pull with or without any
    lane, the only thing forfeited is the `?v=` re-stamp, and that trade is the
    operator's standing call from #3671 — re-imposing a wait on them through the
    new lane would quietly undo it.
    """
    touched = set(changed)
    heavy_filters, public_filters = filters
    filters_complete = bool(heavy_filters and public_filters)
    lanes: set[str] = set()
    for item in changed:
        if item.startswith("templates/"):
            name = item[len("templates/") :]
            if name in pairs and f"site/{name}" in touched:
                continue
        if filters_complete and _public_render_owns(item, filters):
            lanes.add(_RENDER_LANE_PUBLIC)
            continue
        if filters_complete:
            if _path_filter_includes(item, heavy_filters):
                lanes.add(_RENDER_LANE_HEAVY)
            continue
        if (
            item in _RENDER_INPUT_PATHS
            or _FALLBACK_RENDER_BUILDER.match(item)
            or item.startswith("templates/")
        ):
            lanes.add(_RENDER_LANE_HEAVY)
    return lanes


def _merge_changed_paths(
    root: Path, merge_sha: str, start_head: str, head: str
) -> list[str]:
    """The paths ``merge_sha`` itself changed.

    Scoped to the merge's OWN diff, never the session range: this repo runs many
    concurrent sessions, and a worktree synced to origin/main sweeps every OTHER
    session's merges into start_head..head. The session range survives only as the
    fallback for a root/orphan merge with no reachable parent, where it
    over-reports rather than under-reports — the fail-closed direction for every
    caller here, since each of them reads "this merge touched a path" as "this
    merge owes proof".
    """
    try:
        return _run(
            root, "git", "diff", "--name-only", f"{merge_sha}^", merge_sha
        ).splitlines()
    except Exception:
        return _run(root, "git", "diff", "--name-only", start_head, head).splitlines()


_RENDER_LANE_CACHE: dict[tuple[str, str, str, str], frozenset[str]] = {}


def _required_render_lanes(
    root: Path, merge_sha: str, start_head: str, head: str
) -> set[str]:
    """Which render lanes must have a run for ``merge_sha``.

    Scoped to THIS merge's own diff, not the whole session range. Both lanes'
    push triggers are path-filtered, so a push render attributable to this merge
    can exist if and only if merge_sha ITSELF touched those paths. (What
    SATISFIES the requirement is a separate question: ``_render_status`` accepts
    either the push render at merge_sha or a later successful run on a main
    descendant, per the shared-lane coalescing law. That widens coverage, not
    this requirement, which stays scoped as below.)

    start_head..head was the wrong basis on a shared main: this repo runs many
    concurrent sessions, and a session that syncs its worktree to origin/main
    sweeps every OTHER session's merges into that range. One unrelated
    templates/ merge then demanded a render on a merge commit that could never
    have produced one — an unsatisfiable block, not a real gap. (Observed
    2026-07-25: PR #3481 changed only .github/workflows/ci.yml, yet five
    template/builder files from concurrent merges set needs_render.)

    Within that scope, ``_render_lanes_for_paths`` asks the narrower question the
    gate actually cares about: not "would render.yml fire?" but "does this merge
    contain anything a render lane PRODUCES, and which lane?" — see its docstring
    for why a paired plain-copy asset needs neither.

    The pair list and both push filters are read from the worktree, which carries
    this merge's files (the session's branch is what was merged). A worktree that
    cannot answer yields no pairs and no ownership, which requires the heavy
    render — ignorance, not permission.

    Memoised because ``_stop`` asks once per lane and the answer is a pure
    function of a merge that cannot change under it: one git diff, one walk of
    templates/, two workflow reads, not two of each. Only successes are cached,
    so a transient git failure still re-raises on the next ask.
    """
    memo_key = (str(root), merge_sha, start_head, head)
    cached = _RENDER_LANE_CACHE.get(memo_key)
    if cached is not None:
        return set(cached)
    changed = _merge_changed_paths(root, merge_sha, start_head, head)
    lanes = _render_lanes_for_paths(
        changed, _plain_copy_pairs(root), _render_lane_filters(root)
    )
    _RENDER_LANE_CACHE[memo_key] = frozenset(lanes)
    return lanes


def _needs_render(root: Path, merge_sha: str, start_head: str, head: str) -> bool:
    """Whether a push-triggered ``render.yml`` run must exist for ``merge_sha``."""
    return _RENDER_LANE_HEAVY in _required_render_lanes(root, merge_sha, start_head, head)


def _needs_public_render(root: Path, merge_sha: str, start_head: str, head: str) -> bool:
    """Whether a push-triggered ``public-render.yml`` run must exist for ``merge_sha``."""
    return _RENDER_LANE_PUBLIC in _required_render_lanes(root, merge_sha, start_head, head)


_DEPLOY_UPDATE_SCRIPT = Path("app") / "deploy" / "update.sh"
# The macro-api restart condition in app/deploy/update.sh, identified by the one
# thing no other restart block in that script shares: `$API_UNIT_UPDATED`. The
# script holds a dozen `grep -qE` restart guards (admin, press feeds, biocatalyst,
# the live timers), and matching the wrong one would answer a different question
# than /api/health's `commit` field does.
_API_RESTART_GUARD = re.compile(r"API_UNIT_UPDATED.*?grep -qE '(?P<filter>[^']+)'")


def _api_restart_filter(root: Path) -> str:
    """The ERE ``app/deploy/update.sh`` restarts macro-api on, read from the script.

    Parsed at runtime, never transcribed — the same stance ``_render_lane_filters``
    takes on the two render workflows, and for the same reason. That list names
    ~120 modules and grows most weeks as new engine code enters the API's
    ``sys.modules``; a second copy here would be wrong within days, and wrong in
    the one direction this gate must never be wrong in.

    Returns ``""`` on anything it cannot vouch for — missing file, renamed guard,
    a rewrite that splits the condition across lines. Every caller reads that as
    ignorance rather than permission.
    """
    try:
        text = (root / _DEPLOY_UPDATE_SCRIPT).read_text(encoding="utf-8")
    except Exception:
        return ""
    match = _API_RESTART_GUARD.search(text)
    return match.group("filter") if match else ""


def _needs_api_restart(root: Path, merge_sha: str, start_head: str, head: str) -> bool:
    """Whether ``merge_sha`` changes code the running macro-api process imported.

    Which is exactly the question "does this merge owe an API DEPLOY, or only a
    pull?" — and therefore which field of /api/health can prove it live. The
    predicate is the deploy script's own restart condition applied to this
    merge's own diff, so it can be neither wider nor narrower than what the VPS
    actually does.

    True on every uncertainty: an unreadable script, an unparseable filter, a
    diff git cannot produce. Not knowing whether the API restarts means demanding
    the field that proves it did.
    """
    pattern = _api_restart_filter(root)
    if not pattern:
        return True
    try:
        compiled = re.compile(pattern)
        changed = _merge_changed_paths(root, merge_sha, start_head, head)
    except Exception:
        return True
    return any(compiled.search(item) for item in changed)


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """Whether ``descendant``'s history contains ``ancestor`` (equal shas count).

    Every failure mode collapses to False on purpose: rc=1 means "not an
    ancestor" and rc=128 means the sha is unknown to this checkout, and neither
    one can establish that the descendant's tree carried the merge. Here both
    read the same way — not covering.
    """
    try:
        _run(root, "git", "merge-base", "--is-ancestor", ancestor, descendant)
        return True
    except Exception:
        return False


def _render_status(
    root: Path,
    owner: str,
    repo: str,
    merge_sha: str,
    merged_at: str,
    workflow: str = _HEAVY_RENDER_WORKFLOW,
) -> tuple[str, str]:
    """Judge render COVERAGE for ``merge_sha``, not a dedicated run at that sha.

    render.yml is one shared coalescing lane (`concurrency.group: pipeline-render`
    with `cancel-in-progress: false`): a render already running always finishes,
    while a run still PENDING is superseded — GitHub displays it ``cancelled`` —
    the moment a newer merge queues its own. The survivor's scope-union `pick`
    step then renders every region dirty since its last covering watermark, so ONE
    success at any later main descendant covers every earlier merge in the train.
    AGENTS.md §"Shared render-lane safety" states exactly this: do not demand a
    dedicated successful run for every merge SHA.

    Requiring `head_sha == merge_sha` therefore made every merge-train member
    except the last unsatisfiable, and permanently — a superseded run can never
    re-conclude on its own. Observed 2026-07-26: PR #3572 merged as b4449443590,
    its push render 30190635141 was superseded-cancelled seconds later, and
    descendant run 30193723520 (push, main, 8f5cfe12a66) concluded ``success``
    with b4449443590 in its history — yet the guard returned ``failed`` forever
    and forced a manual ~50-minute rerun of work already covered.

    Coverage is now (a) a successful push render at merge_sha itself — one API
    call, the common case, unchanged — or (b) a successful later render whose
    head_sha is a main DESCENDANT of merge_sha. Descendants are the only runs
    whose checkout contained the merge; a sibling or pre-merge head rendered a
    tree without it. The ``merged_at`` floor is belt-and-braces (ancestry already
    excludes pre-merge heads, but a re-run of pre-merge history must not read as
    coverage).

    Three non-success verdicts, and only ONE of them blocks Stop:

    - ``deferred`` — a candidate render is IN FLIGHT (queued/running) and covers
      this merge. ``_stop`` treats this as satisfied and falls through to the live
      gate rather than holding the session for the lane to finish. The VPS pulls
      main every 3 minutes independent of Actions, so a merged commit is live in
      minutes regardless; the render lane only re-bakes ``.j2`` pages and the
      ``?v=`` content-hash stamp; house law forbids a waiting session from
      cancelling or re-running the shared lane; and the nightly ``scope=all``
      re-render self-heals a failed lane within a day. Holding a session the
      lane's ~67+ minutes — observed sessions sat 3h46m-4h02m — for work that is
      already live and a lane they may not touch was the single largest by-design
      cost, so an in-flight covering run now DEFERS to the shared coalescing lane
      with the nightly re-render as backstop.
    - ``pending`` — NO run has fired for this merge yet. This is the dead-wire
      trap (a lane that never triggered) and it must still BLOCK: absence of any
      run is not deferral, it is a missing gate.
    - ``failed`` — every candidate has completed, the newest is non-success, and
      nothing is in flight. Actionable and blocking, exactly as before.

    ``workflow`` selects the lane. All of the above holds for the public fast lane
    too, for a different reason that lands in the same place: `public-render.yml`
    runs `cancel-in-progress: TRUE`, so a newer push kills an older run outright —
    but every run checks out `ref: main` and rebuilds the public surfaces from
    scratch, so the survivor's tree already contains every merge it superseded.
    Coalescing by supersession rather than by scope-union, identical coverage
    algebra. Only the remediation wording differs.
    """
    label = workflow[: -len(".yml")] if workflow.endswith(".yml") else workflow
    public = workflow == _PUBLIC_RENDER_WORKFLOW
    endpoint = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/runs"
    )

    exact_query = urllib.parse.urlencode(
        {"event": "push", "head_sha": merge_sha, "per_page": "20"}
    )
    exact = _get_json(f"{endpoint}?{exact_query}").get("workflow_runs", [])
    if any(
        run.get("status") == "completed" and run.get("conclusion") == "success"
        for run in exact
    ):
        return "success", ""

    # The descendant scan. Filter client-side: the endpoint takes one `event`
    # value only, and a rejected server-side parameter would 422 the whole guard.
    branch_query = urllib.parse.urlencode({"branch": "main", "per_page": "50"})
    listing = _get_json(f"{endpoint}?{branch_query}").get("workflow_runs", [])
    covering: list[dict[str, Any]] = []
    for run in listing:
        if run.get("event") not in {"push", "workflow_dispatch"}:
            continue
        created = str(run.get("created_at") or "")
        # GitHub emits second-precision `...Z` stamps, so a plain string compare
        # is ordering-correct. A missing stamp on either side skips the cutoff
        # rather than guessing at it.
        if created and merged_at and created < merged_at:
            continue
        head = str(run.get("head_sha") or "")
        if not head or not _is_ancestor(root, merge_sha, head):
            continue
        covering.append(run)
    if any(
        run.get("status") == "completed" and run.get("conclusion") == "success"
        for run in covering
    ):
        return "success", ""

    # An exact-sha run also appears in the branch listing; key on the run id so
    # the verdict below weighs it once.
    candidates = {run.get("id"): run for run in (*exact, *covering)}
    if not candidates:
        return "pending", f"The required {label} workflow has not started yet."

    def _created(run: dict[str, Any]) -> str:
        return str(run.get("created_at") or "")

    in_flight = [run for run in candidates.values() if run.get("status") != "completed"]
    if in_flight:
        run = max(in_flight, key=_created)
        status = run.get("status") or "pending"
        backstop = (
            "the public fast lane, which rebuilds every public surface from current "
            "main, so the newest run supersedes this one and still covers the merge"
            if public
            else "the shared coalescing lane, with the nightly scope=all re-render as "
            "backstop"
        )
        return "deferred", (
            f"{label.capitalize()} run {run.get('id')} is {status} and covers this "
            f"merge; completion is deferred to {backstop}."
        )

    newest = max(candidates.values(), key=_created)
    coalescing = (
        "Every run of the lane checks out main and rebuilds the public surfaces from "
        "scratch, so one success at any later main commit covers this merge — a "
        "dedicated run at this exact sha is not required."
        if public
        else "The lane unions every dirty scope since its last covering watermark, so "
        "one success at any later main commit covers this merge — a dedicated run at "
        "this exact sha is not required."
    )
    return "failed", (
        f"{label.capitalize()} workflow concluded {newest.get('conclusion') or 'unknown'} "
        f"(run {newest.get('id')}), and no later successful {label} run on a main "
        "descendant of this merge exists yet: re-run that run "
        f"(`gh run rerun {newest.get('id')}`) once the cause is fixed, or dispatch "
        f"{workflow} on main. {coalescing}"
    )


# The two shas /api/health reports, which answer DIFFERENT questions (app/main.py
# health()): `commit` is the build the running macro-api PROCESS imported at
# startup, `checkout` is /opt/macro's working tree at request time. They diverge
# whenever the 3-minute pull loop has advanced past the last restart — measured
# 2026-08-04 at 70 commits and ~14 hours apart.
_LIVE_PROCESS_FIELD = "commit"
_LIVE_CHECKOUT_FIELD = "checkout"


def _health_sha(payload: Any, field: str) -> str:
    """The git sha under a NAMED top-level key of the health payload.

    Named, never sniffed. The helper this replaced walked the payload for any
    plausible sha-ish key and returned whichever it reached first — the right
    answer to "did anything deploy" and the wrong one here, since `commit` and
    `checkout` answer different questions and the gate must read the specific
    field it decided proves THIS merge, not whichever the endpoint serialises
    first. It was deleted rather than left beside this one: a sniffing reader in
    reach of the live gate is the defect, not a spare part.
    """
    if not isinstance(payload, dict):
        return ""
    value = payload.get(field)
    if not isinstance(value, str):
        return ""
    match = re.search(r"\b[0-9a-f]{7,40}\b", value, re.I)
    return match.group(0) if match else ""


def _live_health_fields(
    root: Path, merge_sha: str, start_head: str, head: str
) -> tuple[str, ...]:
    """Which /api/health fields are allowed to prove ``merge_sha`` is live.

    A merge that changes code macro-api imported is not live until the API has
    RESTARTED into it, and only `commit` shows that. A merge that changes nothing
    the deploy script restarts on is live the moment /opt/macro's tree carries it,
    which is what `checkout` shows — and its `commit` may never advance at all.

    Reading `commit` for both was structurally unsatisfiable for the second kind
    (observed 2026-08-04, PR #4499: a tests-only merge sat in `checkout` while
    `commit` was 70 commits behind, so the gate blocked `live_stale` on a merge
    that had been fully live for hours, and no action the session could take would
    ever satisfy it — restarting production to bless a test-only merge is the
    wrong move, so the session was pinned until an unrelated later PR happened to
    touch API code).

    `commit` stays in the tuple for the pull-only case as a fallback, not as a
    softening: the pull loop only ever moves forward, so a process that IMPORTED a
    sha containing the merge proves the tree containing it too. That keeps the
    gate satisfiable against a health payload that omits `checkout` entirely
    (an older API build) without ever accepting weaker evidence than the question
    demands — for an api-code merge the tuple is `commit` alone, and `checkout`
    carrying the merge means nothing.
    """
    if _needs_api_restart(root, merge_sha, start_head, head):
        return (_LIVE_PROCESS_FIELD,)
    return (_LIVE_CHECKOUT_FIELD, _LIVE_PROCESS_FIELD)


def _live_gate(
    root: Path, merge_sha: str, start_head: str, head: str, payload: Any
) -> tuple[bool, str]:
    """Whether production demonstrably carries ``merge_sha``, plus the detail why.

    Fail-closed at every step. A field that is absent, non-string, sha-less, or
    unknown to this checkout is NO EVIDENCE, never permission: it is skipped, and
    if no permitted field clears, the caller blocks. ``_is_ancestor`` collapses
    its own failures to False for the same reason.
    """
    fields = _live_health_fields(root, merge_sha, start_head, head)
    seen: list[str] = []
    for field in fields:
        sha = _health_sha(payload, field)
        if not sha:
            seen.append(f"{field}=<absent>")
            continue
        try:
            _run(root, "git", "rev-parse", sha)
        except Exception:
            seen.append(f"{field}={sha} (unknown to this checkout — try `git fetch origin main`)")
            continue
        if _is_ancestor(root, merge_sha, sha):
            return True, f"{field}={sha} contains the merge"
        seen.append(f"{field}={sha}")
    demanded = (
        "this merge changes code macro-api imported, so only a RESTARTED API "
        f"(`{_LIVE_PROCESS_FIELD}`) proves it live"
        if fields == (_LIVE_PROCESS_FIELD,)
        else "this merge restarts nothing, so the VPS pull loop "
        f"(`{_LIVE_CHECKOUT_FIELD}`) is what makes it live"
    )
    return False, f"{demanded}; production reports {', '.join(seen) or '<no usable field>'}"


# How much of the tail of a transcript to scan for the final assistant message
# before giving up and re-reading the whole file. Transcripts are JSONL whose bulk
# is tool_result rows, so a few MB is many turns deep, but one pathological result
# row can exceed it — hence the escalation rather than a hard cap.
_TRANSCRIPT_TAIL_BYTES = 4 * 1024 * 1024


def _jsonl_tail(path: Path, limit: int | None) -> tuple[list[str], bool]:
    """Return (lines, whole_file) for the last `limit` bytes of a JSONL file.

    A byte window almost always cuts mid-line, so the first line of a windowed read
    is dropped as a fragment. `whole_file` reports whether the window covered the
    entire file, which is how the caller knows a miss is final rather than an
    artifact of the window.
    """
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = 0 if limit is None else max(0, size - limit)
        handle.seek(start)
        data = handle.read()
    if start:
        _, _, data = data.partition(b"\n")
    return data.decode("utf-8", "replace").splitlines(), start == 0


def _last_assistant_text(lines: list[str]) -> str:
    """The newest assistant message's visible text, or "" if the window holds none.

    Only `text` blocks count. `thinking` blocks are excluded deliberately: the
    harness's own `last_assistant_message` carries visible text only (measured
    2026-08-04), and a report has to be something the operator can read in the
    transcript, not reasoning the session never surfaced. Sidechain rows are
    subagent turns, not this session's final word, so they are skipped too.
    """
    for line in reversed(lines):
        line = line.strip()
        if not line or '"assistant"' not in line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict) or row.get("type") != "assistant":
            continue
        if row.get("isSidechain"):
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            if content.strip():
                return content
            continue
        if not isinstance(content, list):
            continue
        text = "".join(
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
        if text.strip():
            return text
    return ""


def _transcript_final_message(payload: dict[str, Any]) -> str:
    """Recover the final assistant message from `transcript_path`.

    `last_assistant_message` is NOT a documented field of the Stop hook payload
    (documented: session_id, transcript_path, cwd, hook_event_name,
    stop_hook_active). This harness does supply it, but a client that does not
    would make the `SHIP LOOP BLOCKED:` report undetectable and the escape ladders
    unreachable — the exact brick this guard exists to prevent. `transcript_path`
    IS documented, so it is the durable source.

    Fails CLOSED: any unreadable, missing, or textless transcript returns "", which
    leaves the report unfiled and the session blocked.
    """
    raw = payload.get("transcript_path")
    if not raw:
        return ""
    try:
        path = Path(str(raw)).expanduser()
    except Exception:
        return ""
    for limit in (_TRANSCRIPT_TAIL_BYTES, None):
        try:
            lines, whole_file = _jsonl_tail(path, limit)
        except OSError:
            return ""
        text = _last_assistant_text(lines)
        if text or whole_file:
            return text
    return ""


def _block(
    path: Path,
    state: dict[str, Any],
    payload: dict[str, Any],
    code: str,
    reason: str,
    exit_key: str = "",
) -> None:
    """Block Stop, except when a reported blocker has ping-ponged past the ceiling.

    Two escape ladders, both requiring an explicit `SHIP LOOP BLOCKED:` report on a
    re-entrant Stop, so a session cannot bail on the first attempt. The report is
    read from `last_assistant_message` when the harness supplies it and recovered
    from `transcript_path` when it does not; re-entrancy is proven by the payload's
    `stop_hook_active` OR by this guard's own block ledger (see below):

    - EXTERNAL codes escape at 2 CONSECUTIVE or 3 CUMULATIVE external blocks. The
      cumulative arm is what the field forced: a session ping-ponging
      render_pending -> github_rate_limited -> render_pending resets the
      consecutive counter every hop, so `blocker_count >= 2` alone never armed and
      one session refused Stop 245 times on render_failed while genuinely blocked.
    - ANY code (including the internal ones — unmerged/ci_failed_unmerged/unpushed/
      uncommitted/unsafe_branch/guard_error) escapes at 10 CONSECUTIVE or 15 TOTAL
      blocks.
      Internal codes had NO escape at all, which produced an observed 258x infinite
      loop on `unmerged` (a zero-diff stand-down whose chain was unsatisfiable). The
      internal ceiling is deliberately high — it is a last-resort loop breaker, not
      a routine exit — and every earlier gate (the stand-down exemption, the
      deferred-render acceptance below) exists to keep a healthy session from ever
      reaching it.

    `last_blocker`/`blocker_count` track the CONSECUTIVE same-code run and are left
    exactly as they were. `total_blocks` and `external_blocks` are cumulative and
    are NEVER reset within a session, so a ping-pong cannot erase them.

    The ladders are a LAST resort, not the intended exit. The release valves
    upstream of them — the stand-down exemption and the deferred render — exist so
    a healthy session reaches a clean stop and never counts toward a ceiling at
    all. There is deliberately no valve for `unmerged` or `ci_failed_unmerged`: a
    session owns its pull request until the merge lands, and the internal ceiling
    is the only thing that can end that wait early.

    A RATIFIED ladder exit is REMEMBERED for the exact frozen state it excused
    (2026-08-19, operator complaint; widened to every EXTERNAL code by Sol
    commission #6379, 2026-08-24). ``exit_key`` names one evaluated state: the
    merged-head red keeps its original
    ``ci_failed:<head_sha>:<merge_sha>:<sha256(reason)[:12]>`` key, and every
    other external block site now passes ``_external_exit_key``'s
    ``<code>:<head_sha>:<sha256(reason)[:12]>``. The reason digest is
    load-bearing, not decoration: a merged head's check SET is not immutable
    (a `gh run rerun` or a late-attaching cron can bind a different red to the
    same shas), and an external blocker that materially changes (other lane,
    other error) is a NEW state — so a changed reason mints a different key
    and a fresh block, which is the fail-closed direction. Without the memory,
    a long-lived session re-blocked on every subsequent Stop and had to
    re-file the SAME `SHIP LOOP BLOCKED:` report dozens of times (measured on
    the 2026-08-19 authority-frozen main-red-repair session); the same shape
    re-entered a lawfully escaped session whenever a leftover background
    timer's `<task-notification>` turn hit Stop after the escape (incident
    PR #6377). The memory records an exit key ONLY at the moment an escape
    actually fires — which itself required the full evidence report on a
    re-entrant Stop — and a later block carrying a remembered key passes
    through without bumping any counter. A DIFFERENT key (new PR, new merge,
    new head, new evidence) never matches, internal codes never carry a key,
    and an unratified block records nothing, so no ladder widens: the report
    is demanded once per frozen state instead of once per Stop.
    """
    final = str(payload.get("last_assistant_message") or "").lstrip()
    if not final:
        final = _transcript_final_message(payload).lstrip()
    # Re-entrancy is proven by the guard's OWN ledger, not only by the payload flag.
    # `stop_hook_active` describes how the CURRENT turn was started, not whether this
    # guard has ever blocked: measured 2026-08-04, a turn started by a background
    # `<task-notification>` arrives with the flag False even though the guard had
    # already blocked three times. Session 787452b5 filed a correct, token-leading
    # `SHIP LOOP BLOCKED:` report on such a turn with live_stale at count 5 — both
    # external arms armed — and was refused anyway, because the flag alone vetoed it.
    # A repository whose sessions routinely wait on background tasks hits that reset
    # constantly, so the ladder was unreachable exactly when it was most needed.
    #
    # `total_blocks >= 2` is the durable form of the same fact and never widens a
    # ladder: EVERY escape arm below already requires at least two blocks (external
    # needs count >= 2 or external_blocks >= 3; any-code needs count >= 10 or
    # total_blocks >= 15). So the first-attempt bailout the flag was guarding against
    # stays impossible — on a first Stop total_blocks is 1 and no arm can fire.
    def apply_block(latest: dict[str, Any]) -> dict[str, Any]:
        exits = latest.get("ladder_exits")
        remembered = [str(item) for item in exits] if isinstance(exits, list) else []
        if exit_key and exit_key in remembered:
            return {"silent": True}

        previous = latest.get("last_blocker")
        count = int(latest.get("blocker_count") or 0) + 1 if previous == code else 1
        latest["last_blocker"] = code
        latest["blocker_count"] = count
        total_blocks = int(latest.get("total_blocks") or 0) + 1
        latest["total_blocks"] = total_blocks
        external_blocks = int(latest.get("external_blocks") or 0)
        if code in EXTERNAL_BLOCKERS:
            external_blocks += 1
            latest["external_blocks"] = external_blocks

        reentrant = bool(payload.get("stop_hook_active")) or total_blocks >= 2
        reported = reentrant and final.startswith("SHIP LOOP BLOCKED:")
        external_escape = code in EXTERNAL_BLOCKERS and (
            count >= 2 or external_blocks >= 3
        )
        any_code_escape = count >= 10 or total_blocks >= 15
        escaped = reported and (external_escape or any_code_escape)
        if escaped and exit_key:
            # Bounded: the list only ever holds frozen state identities, and a
            # session mints at most a handful of them.
            latest["ladder_exits"] = (remembered + [exit_key])[-20:]
        return {
            "silent": False,
            "escaped": escaped,
            "count": count,
            "total_blocks": total_blocks,
        }

    outcome = _update_ledger(path, apply_block, initial=state)
    if not isinstance(outcome, dict):
        # This path is only reachable if the lock/transaction itself failed;
        # preserve the guard's blocking direction instead of granting an exit.
        _emit(
            {
                "decision": "block",
                "reason": (
                    "SHIP LOOP guard_error: session ledger transaction was "
                    "unanswerable; completion cannot be proven safely."
                ),
            }
        )
        return
    if outcome.get("silent") or outcome.get("escaped"):
        return
    # The escape hint is only inviting when an escape is plausibly one attempt away:
    # an external code (its ceiling is low), or an internal code already near the
    # any-code ceiling. Offering it to a fresh internal block would invite a bailout
    # long before the loop breaker is meant to arm.
    count = int(outcome["count"])
    total_blocks = int(outcome["total_blocks"])
    escape_hint = code in EXTERNAL_BLOCKERS or count >= 9 or total_blocks >= 14
    body = (
        f"SHIP LOOP {code}: {reason}\n"
        "Continue the task and complete commit → push → PR → CI → squash-merge → "
        "render/deploy → live verification."
    )
    if escape_hint:
        body += (
            " If the same genuine blocker persists after another attempt, "
            "finish with `SHIP LOOP BLOCKED:` and the specific evidence."
        )
    _emit({"decision": "block", "reason": body})


def _session_start(root: Path, path: Path, payload: dict[str, Any]) -> None:
    source = str(payload.get("source") or "")
    state = _load_ledger(path, allow_missing=True)
    if state is None or source in {"startup", "clear"}:
        baseline_state = {
            "root": str(root),
            "start_head": _run(root, "git", "rev-parse", "HEAD"),
            "baseline": _fingerprint(root),
            "last_blocker": "",
            "blocker_count": 0,
            "total_blocks": 0,
            "external_blocks": 0,
        }

        def reset(latest: dict[str, Any]) -> None:
            # A concurrent/live watcher remains reserved across a SessionStart
            # reset; erasing it would reopen the slot while its process lives.
            watcher = latest.get("ship_watcher")
            latest.clear()
            latest.update(baseline_state)
            if isinstance(watcher, dict):
                latest["ship_watcher"] = watcher

        _update_ledger(path, reset, initial={})
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "MANDATORY SHIP LOOP: Repository rules grant standing approval for "
                    "commit, push, pull request, CI repair, same-day squash merge, deploy "
                    "waiting, and real-live verification. Work only in a fresh "
                    ".claude/worktrees/ claude/* branch. Do not stop at a local change, "
                    "commit, or open PR. This session's starting dirty files were recorded "
                    "and are excluded from enforcement."
                ),
            }
        }
    )


def _fast_forwarded_onto_main(root: Path) -> bool:
    """Whether HEAD is origin/main's own history with nothing of this session on top.

    The exemption above this one catches a session that never moved. A stand-down
    session — one assigned a defect that turns out to be already fixed on main,
    the common shape under the duplicate-fixes playbook — DOES move: it runs
    `git reset --hard origin/main` to verify the fix at tip before concluding,
    which walks HEAD off start_head while creating zero commits of its own.

    From there the full chain is unsatisfiable. GitHub refuses a zero-diff pull
    request ("No commits between main and <branch>"), and `unmerged` is not in
    EXTERNAL_BLOCKERS, so the repeated-blocker `SHIP LOOP BLOCKED:` escape never
    arms. Observed 2026-07-26 on claude/serene-colden-e5b716: the only exit was
    resetting BACK to start_head to re-qualify for the no-op exemption — a
    non-obvious and wasteful ritual for a session that verified and built nothing.

    Fail-closed, and the fetch is load-bearing. Ancestry has to be judged against
    origin's CURRENT tip, never a stale local ref this worktree happened to keep,
    so a fetch that does not SUCCEED means the exemption simply does not apply and
    the ordinary chain takes over — whose GitHub-side failures are escapable
    external blockers, so nothing is trapped by going offline. The ancestry test
    and the zero-ahead count are belt-and-braces statements of one claim; both
    must hold, and every git failure — a failed fetch, rc=1 for "not an ancestor",
    rc=128 for an origin/main this checkout cannot name — reads as "not exempt".

    Shipped sessions are untouched: a squash merge mints a NEW sha, so a merged
    branch head is never an ancestor of origin/main and still falls through to the
    merged-PR, CI, render, and live verification exactly as before.

    The branch gate must run BEFORE this, and that ordering is load-bearing rather
    than cosmetic. Ancestry proves POSITION, never authorship: a session that
    synced to someone else's fix and a session that committed its own work on main
    and pushed it straight to origin/main both end with HEAD equal to origin's tip
    and a zero ahead-count, and nothing here can tell them apart. The second one
    genuinely shipped something, so exempting it would skip the render and live
    gates on live work — fail-open, which this guard may never be. Running the
    branch check first leaves that session blocking on `unsafe_branch` and makes
    the exemption reachable only from a claude/* worktree branch, where a zero
    ahead-count really does mean nothing shippable exists.
    """
    try:
        _run(root, "git", "fetch", "origin", "main", timeout=90)
        _run(root, "git", "merge-base", "--is-ancestor", "HEAD", "origin/main")
        return _run(root, "git", "rev-list", "--count", "origin/main..HEAD") == "0"
    except Exception:
        return False


def _branch_was_pushed(root: Path, branch: str) -> bool:
    """Whether ``branch`` has ever reached origin — by upstream config or remote ref.

    The stand-down exemption needs this because ``_fast_forwarded_onto_main``
    answers only where HEAD SITS, and the branch gate above it can only rule out
    main itself. Neither sees the third way a session arrives at origin's tip
    with a zero ahead-count: it pushed real commits, opened a pull request, and
    then ran `git reset --hard origin/main` to look at main while waiting.
    `reset --hard` moves the LOCAL branch ref, so those commits survive only on
    the remote — the worktree looks exactly like a stand-down while an unmerged
    pull request is still open. A branch that was never pushed cannot be in that
    state: no pull request of ours can exist, so nothing is waiting on CI,
    render, or deploy.

    Both halves are needed. `@{upstream}` alone misses
    `git push origin HEAD:<branch>`, which sets no upstream but does update the
    remote-tracking ref (so does any later fetch); the remote ref alone misses
    nothing in practice but is the cheaper, more direct question, so it is asked
    second and only when there is no upstream to consult.

    Fail-CLOSED: a missing branch name or an unanswerable probe reports True,
    which only ever DECLINES the exemption and keeps the full completion chain.
    `for-each-ref` is used rather than `rev-parse --verify` because it exits 0
    whether or not the ref matches, keeping "absent" distinguishable from "git
    could not answer".
    """
    if not branch:
        return True
    try:
        if _run(root, "git", "rev-parse", "--abbrev-ref", "@{upstream}"):
            return True
    except Exception:
        pass
    try:
        listing = _run(
            root,
            "git",
            "for-each-ref",
            "--format=%(refname)",
            f"refs/remotes/origin/{branch}",
        )
    except Exception:
        return True
    return bool(listing.strip())


def _stop(root: Path, path: Path, payload: dict[str, Any]) -> None:
    """Judge the completion chain, in the order the cheapest evidence answers it.

    Dirty tree -> no-op exemption -> branch -> stand-down -> pushed -> merged pull
    request -> CI -> origin/main -> render -> live. Each gate blocks with a code
    `_block` can count, and every gate that proved something durable stores a
    proof so a later Stop turn does not re-poll GitHub for it.

    ONE gate releases a session for machinery it does not own: a DEFERRED render —
    an in-flight covering run, satisfied rather than waited on (see
    `_render_status`). The VPS pulls main every 3 minutes, so that merge is live
    regardless, and house law forbids a waiting session from touching the lane.

    THE MERGE ITSELF IS NOT SUCH A GATE. An open pull request carrying
    `merge-on-green` used to release the session here; the operator removed that
    on 2026-08-12 after it reported an unfinished job as complete. The label lets
    the sweeper PERFORM the merge — it does not transfer ownership — so the
    `if not pull:` branch now always blocks, and only chooses which block to file
    (see `_armed_pull_status`).
    """
    state = _load_ledger(path, allow_missing=True)
    # Hooks can be installed during an already-running session. Fail open once so
    # that pre-hook work is not misclassified; every later session is enforced.
    if state is None:
        return

    baseline = state.get("baseline") or {}
    now = _fingerprint(root)
    dirty = _changed_since_baseline(baseline, now)
    if dirty:
        # Untracked bytes already shipped at the same path on origin/main are
        # not committable work (see _shipped_identical_untracked). Checked only
        # here, on the paths about to block, so the cost stays two bounded git
        # calls at Stop rather than per-status-entry.
        shipped = _shipped_identical_untracked(root, now, dirty)
        if shipped:
            dirty = [entry for entry in dirty if entry not in shipped]
    if dirty:
        preview = ", ".join(dirty[:12])
        _block(path, state, payload, "uncommitted", f"Session-created changes remain: {preview}")
        return

    head = _run(root, "git", "rev-parse", "HEAD")
    if head == state.get("start_head"):
        return

    branch = _run(root, "git", "branch", "--show-current")
    if not branch.startswith("claude/"):
        location = branch or "detached HEAD"
        _block(
            path,
            state,
            payload,
            "unsafe_branch",
            f"Work is on {location}; project work must use a claude/* branch.",
        )
        return

    # A stand-down session may stop — but only one that never pushed anything.
    #
    # `_fast_forwarded_onto_main` proves POSITION and the branch gate above rules
    # out main itself; neither can see that this branch already put commits on
    # the remote. A session that pushed, opened a pull request, then ran
    # `git reset --hard origin/main` to look at main while waiting on CI lands at
    # origin's tip with a zero ahead-count and a clean tree — indistinguishable
    # from a stand-down by position alone, yet its commits are alive on
    # `origin/<branch>` under an unmerged pull request. Exempting it abandons
    # that pull request silently. The same shape covers a merge commit or rebase
    # merge, which (unlike a squash) preserve the branch's own shas on main, so
    # the tip becomes a literal ancestor of origin/main with no reset at all —
    # skipping the CI, render, and live gates for a merge that really landed.
    #
    # Asking whether the branch was ever pushed is what separates the two, and it
    # costs nothing when the answer is no. Fail-closed: an unanswerable probe
    # reports "pushed" and keeps the full chain.
    if _fast_forwarded_onto_main(root) and not _branch_was_pushed(root, branch):
        return

    # A missing upstream means one of two opposite things: never pushed, or
    # pushed and merged, with the remote branch auto-deleted on merge. Blocking
    # here judged the second case as the first and made a COMPLETED ship
    # unsatisfiable — the branch is merged, so there is nothing left to push and
    # recreating it would be wrong. The merged-PR lookup below is what tells the
    # two apart (GitHub keeps serving a merged PR by head ref after the branch is
    # gone), so defer the verdict rather than pre-empt it.
    try:
        upstream = _run(root, "git", "rev-parse", "--abbrev-ref", "@{upstream}")
    except RuntimeError:
        upstream = ""
    if upstream:
        ahead = int(_run(root, "git", "rev-list", "--count", f"{upstream}..HEAD") or "0")
        if ahead:
            _block(path, state, payload, "unpushed", f"{ahead} commit(s) have not been pushed.")
            return

    try:
        owner, repo = _github_slug(root)
    except Exception as exc:
        _block(
            path, state, payload, "github_unreachable", str(exc),
            exit_key=_external_exit_key("github_unreachable", head, str(exc)),
        )
        return
    pull_key = f"{branch}:{head}"
    pull = _proof(state, "merged_pull", pull_key)
    if pull is not None and not str((pull.get("base") or {}).get("sha") or ""):
        # A PRE-FIX CACHE SHAPE IS NOT A PROOF. The narrowing below did not keep
        # `base.sha` until 2026-08-16, and this proof is keyed by branch+head —
        # neither of which ever moves again once the branch is merged — so a
        # session that already remembered the old shape would keep reading its own
        # stale record and stay blocked by the very defect the narrowing fix
        # repairs. The cache, not the API, is what the CI gate would be answering
        # from. Treat an incomplete record as no record and pay one call: the
        # refetch re-remembers the complete shape and every later Stop hits the
        # cache again. A pull request whose API record genuinely carries no base
        # re-asks once per Stop, which is the cheap direction — the alternative is
        # pinning a session forever on a record that can never answer.
        pull = None
    if pull is None:
        try:
            pull = _latest_merged_pr(owner, repo, branch)
        except Exception as exc:
            code = _github_block_code(exc)
            _block(
                path, state, payload, code, str(exc),
                exit_key=_external_exit_key(code, head, str(exc)),
            )
            return
        if pull:
            # A merged PR and its head/merge/base identities are immutable. Keep
            # only the fields the remaining gates consume, not the full API
            # payload — and `base.sha` IS one of them, as of #5757: the CI gate
            # threads it in as the MERGED head's semantic proof base, because
            # GitHub drops `pull_requests` from check-runs the moment a pull
            # request closes, so `_semantic_pr_base_sha` returns None on every
            # merged head and this record is the only surviving source of the
            # exact base.
            #
            # Dropping it is why that fallback shipped dead. #3746 narrowed this
            # record long before the fallback existed, so `_check_ci` was handed
            # `""` on every merged head, `_semantic_evidence_for_run` found no
            # bound base on either side, and it refused with "run <id> does not
            # identify the exact PR proof base" — surfacing as `ci_failed` on
            # work that had merged GREEN, fleet-wide, with no session-side
            # remedy: check runs on a merged commit are immutable. Measured on
            # PR #5769 (merged 2026-08-16T02:43:09Z): run 31921385097 concluded
            # `success` carrying `prs: []`, while `/pulls/5769` still carried
            # base c2484fe7134b63b8acba50471396edf9929d20a3.
            #
            # Only the sha is kept. The narrowing exists to bound what is written
            # into the state file, and no gate reads anything else off the base.
            pull = {
                "number": pull.get("number"),
                "head": {
                    "sha": (pull.get("head") or {}).get("sha"),
                    "ref": (pull.get("head") or {}).get("ref"),
                },
                "base": {"sha": (pull.get("base") or {}).get("sha")},
                "merge_commit_sha": pull.get("merge_commit_sha"),
                "merged_at": pull.get("merged_at"),
            }
            _remember_proof(path, state, "merged_pull", pull_key, pull)
    if not pull:
        # There is no merged pull request, so this session is NOT done — arming
        # `merge-on-green` is a merge convenience, never an exit (operator ruling
        # 2026-08-12; see the module docstring). The only question left is which
        # block to file: an armed head with concluded reds gets `ci_failed` and the
        # names, because "your sweeper will refuse this" is the fact the old
        # release path used to hide.
        #
        # Fail-closed in every direction: a probe that raises, a pull request
        # without the label, or a head that does not match the local HEAD all fall
        # through to the ordinary block below. The escape ladder in `_block` covers
        # a persistently failing API.
        try:
            armed_code, armed_detail = _armed_pull_status(owner, repo, branch, head)
        except Exception:
            armed_code, armed_detail = "none", ""
        if armed_code != "none":
            _block(path, state, payload, armed_code, armed_detail)
            return

        # No merged pull request: an absent upstream now genuinely means unpushed.
        if not upstream:
            _block(path, state, payload, "unpushed", f"{branch} has no upstream branch.")
        else:
            _block(
                path, state, payload, "unmerged", f"No merged main pull request found for {branch}."
            )
        return

    head_sha = str((pull.get("head") or {}).get("sha") or head)
    # The CI gate needs the merge's identity too: a red on the merged head may be
    # base-side, and only merge_sha (ancestry), merged_at (the pre-merge window),
    # and the pull request's own head ref (sibling independence) can show that.
    head_ref = str((pull.get("head") or {}).get("ref") or "")
    merge_sha = str(pull.get("merge_commit_sha") or "")
    merged_at = str(pull.get("merged_at") or "")
    ci_key = f"{head_sha}:{merge_sha}"
    ci_proof = _proof(state, "ci", ci_key)
    if ci_proof is not None:
        ci_ok, ci_reason = True, str((ci_proof or {}).get("reason") or "")
    else:
        try:
            ci_ok, ci_reason = _check_ci(
                root, owner, repo, head_sha, merge_sha, merged_at, head_ref,
                str((pull.get("base") or {}).get("sha") or ""),
            )
        except Exception as exc:
            code = _github_block_code(exc)
            _block(
                path, state, payload, code, str(exc),
                exit_key=_external_exit_key(code, head, str(exc)),
            )
            return
        if ci_ok:
            _remember_proof(path, state, "ci", ci_key, {"reason": ci_reason})
    if not ci_ok:
        code = "ci_failed" if ci_reason.startswith("Failing") else "render_pending"
        # The merged-head red keeps its richer three-part key (head:merge:digest)
        # so already-ratified exits stay recognisable; the render_pending shape of
        # this site uses the standard external key like every other external
        # block. Both bind the exact evidence text: one ratified ladder exit
        # covers later Stops on the IDENTICAL frozen state only — a different
        # red re-blocks, while a render state whose detail text is byte-stable
        # (a lane that never started) stays covered by its one ratified report.
        reason_digest = hashlib.sha256(ci_reason.encode("utf-8")).hexdigest()[:12]
        _block(
            path,
            state,
            payload,
            code,
            ci_reason,
            exit_key=(
                f"{code}:{ci_key}:{reason_digest}"
                if code == "ci_failed"
                else _external_exit_key(code, head, ci_reason)
            ),
        )
        return
    if _proof(state, "origin_main", merge_sha) is None:
        try:
            _run(root, "git", "fetch", "origin", "main", timeout=90)
            _run(root, "git", "merge-base", "--is-ancestor", merge_sha, "origin/main")
        except Exception as exc:
            reason = f"Merge is not confirmed on origin/main: {exc}"
            _block(
                path,
                state,
                payload,
                "github_unreachable",
                reason,
                exit_key=_external_exit_key("github_unreachable", head, reason),
            )
            return
        _remember_proof(path, state, "origin_main", merge_sha, True)

    render_notes: list[str] = []
    start_head = str(state.get("start_head"))
    # Two lanes since #3834, each satisfied from its OWN workflow's runs: the heavy
    # self-hosted market renderer, and the GitHub-hosted public fast lane that
    # render.yml's negations handed the public surfaces to. A merge usually owes
    # one or neither — asking both cost a session an unsatisfiable `render_pending`
    # for every public-only change (#3897). Heavy first, so a mixed merge reports
    # the slow lane's verdict rather than the fast one's.
    lanes: list[tuple[str, str]] = []
    if _needs_render(root, merge_sha, start_head, head):
        lanes.append((_HEAVY_RENDER_WORKFLOW, "render"))
    if _needs_public_render(root, merge_sha, start_head, head):
        lanes.append((_PUBLIC_RENDER_WORKFLOW, "public_render"))
    for workflow, gate in lanes:
        render_proof = _proof(state, gate, merge_sha)
        if render_proof is None:
            try:
                status, detail = _render_status(
                    root, owner, repo, merge_sha, merged_at, workflow
                )
            except Exception as exc:
                code = _github_block_code(exc)
                _block(
                    path, state, payload, code, str(exc),
                    exit_key=_external_exit_key(code, head, str(exc)),
                )
                return
            if status == "deferred":
                # An in-flight covering run satisfies the gate: the merge is already
                # live via the VPS's 3-min pull, and the shared coalescing lane (with
                # the nightly scope=all re-render as backstop) owns the re-bake. Record
                # the deferral so a later Stop turn reads it back and so the audit
                # systemMessage below can name it. Fall through to the live gate.
                _remember_proof(path, state, gate, merge_sha, {"deferred": detail})
                render_notes.append(detail)
            elif status != "success":
                code = "render_failed" if status == "failed" else "render_pending"
                _block(
                    path,
                    state,
                    payload,
                    code,
                    detail,
                    exit_key=_external_exit_key(code, head, detail),
                )
                return
            else:
                _remember_proof(path, state, gate, merge_sha, True)
        elif isinstance(render_proof, dict) and "deferred" in render_proof:
            render_notes.append(str(render_proof.get("deferred") or ""))

    # Which /api/health field can prove this merge live depends on whether the
    # merge owes an API DEPLOY or only a pull — see _live_health_fields. Asking
    # `commit` of a merge that restarts nothing is unsatisfiable by construction.
    try:
        health = _get_json(LIVE_HEALTH_URL)
    except Exception as exc:
        reason = f"Production health check failed: {exc}"
        _block(
            path, state, payload, "live_unreachable", reason,
            exit_key=_external_exit_key("live_unreachable", head, reason),
        )
        return
    live_ok, live_detail = _live_gate(root, merge_sha, start_head, head, health)
    if not live_ok:
        reason = f"Production does not yet contain the merge: {live_detail}"
        _block(
            path,
            state,
            payload,
            "live_stale",
            reason,
            exit_key=_external_exit_key("live_stale", head, reason),
        )
        return

    audit: list[str] = []
    if ci_reason:
        # A pass that rests on excluded reds is a judgement call; the operator has
        # to be able to audit which checks were ignored and on what evidence.
        audit.append(f"Ship-loop CI gate: {ci_reason}")
    for render_note in render_notes:
        # Likewise a render this Stop DEFERRED rather than waited for, once per lane
        # that deferred: the operator must be able to see that a lane still owes a
        # re-bake — with the nightly scope=all as the heavy lane's backstop and the
        # next push as the fast lane's — even though the session was released.
        audit.append(f"Ship-loop render gate: {render_note}")
    if audit:
        # Emitted only here, once every later gate has passed, and as ONE combined
        # object: hook stdout must stay a single JSON value, and a systemMessage
        # line ahead of a later block line would make the whole output unparseable
        # — silently defeating that block, the one direction this guard may never
        # fail. Every path that reaches this point is a clean stop with no block to
        # follow, so the invariant holds.
        _emit({"systemMessage": " | ".join(audit)})

    try:
        path.unlink()
    except OSError:
        pass


# Settings.json launches this file via $CLAUDE_PROJECT_DIR, so the executing
# copy is often the primary checkout. The tree being evaluated is resolved
# separately from the hook payload. When those two identities differ and they
# share a git object store (linked worktrees of the same clone), this process
# is only a bootstrap: it delegates exactly once to the evaluated tree's own
# ship_loop_guard.py. A stale primary can then no longer enforce old Stop
# logic against a current worktree. If delegation is required but impossible,
# Stop fails closed as hook_source_mismatch rather than a misleading ci_failed.
DELEGATION_ENV = "SHIP_LOOP_GUARD_DELEGATED"
TARGET_HOOK_REL = Path(".claude") / "hooks" / "ship_loop_guard.py"


def _hook_source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _short_head(root: Path) -> str:
    try:
        return _run(root, "git", "rev-parse", "--short=12", "HEAD") or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _git_common_dir(root: Path) -> Path | None:
    try:
        found = _run(root, "git", "rev-parse", "--git-common-dir")
    except Exception:
        return None
    if not found:
        return None
    common = Path(found)
    if not common.is_absolute():
        common = (root / common)
    try:
        return common.resolve()
    except OSError:
        return None


def _same_git_repository(source: Path, evaluated: Path) -> bool:
    source_common = _git_common_dir(source)
    evaluated_common = _git_common_dir(evaluated)
    return bool(source_common and evaluated_common and source_common == evaluated_common)


def _classify_hook_target(path: Path) -> str:
    """Return 'ok', 'missing', 'unreadable', or 'malformed'."""
    try:
        if not path.is_file():
            return "missing"
    except OSError:
        return "unreadable"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "unreadable"
    if not text.strip():
        return "malformed"
    try:
        compile(text, str(path), "exec")
    except SyntaxError:
        return "malformed"
    return "ok"


def _format_hook_source_mismatch(source: Path, evaluated: Path, detail: str) -> str:
    return (
        "hook_source_mismatch: "
        f"executing={source}@{_short_head(source)} "
        f"evaluating={evaluated}@{_short_head(evaluated)} "
        f"{detail}"
    )


def _emit_hook_source_mismatch(event: str, reason: str) -> None:
    if event == "Stop":
        _emit(
            {
                "decision": "block",
                "reason": f"SHIP LOOP hook_source_mismatch: {reason}",
            }
        )
        return
    if event == "PreToolUse":
        _deny_watcher(
            "SHIP WATCHER REFUSED: hook_source_mismatch: evaluated-tree "
            f"admission could not be enforced ({reason})."
        )
        return
    _emit({"systemMessage": f"SHIP LOOP hook_source_mismatch: {reason}"})


def _spawn_delegated_guard(target: Path, raw: bytes, *, cwd: Path) -> tuple[int, bytes, bytes]:
    env = os.environ.copy()
    env[DELEGATION_ENV] = "1"
    proc = subprocess.run(
        [sys.executable, "-u", str(target)],
        input=raw,
        env=env,
        cwd=str(cwd),
        capture_output=True,
        check=False,
    )
    return int(proc.returncode), bytes(proc.stdout or b""), bytes(proc.stderr or b"")


def _write_hook_bytes(stream: Any, value: bytes) -> None:
    if not value:
        return
    stream.buffer.write(value)
    stream.flush()


def _load_payload_and_raw() -> tuple[dict[str, Any] | None, bytes]:
    """Read stdin once so a delegated child can receive the original bytes.

    Prefer ``stdin.buffer`` so the child sees the exact bytes Claude sent.
    Fall back to ``json.load`` so existing tests that patch it still drive
    ``main()``.
    """
    stream = sys.stdin
    raw = b""
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        try:
            raw = buf.read()
        except Exception:
            raw = b""
        if raw:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                return None, raw
            if isinstance(payload, dict):
                return payload, raw
            return None, raw
    try:
        payload = json.load(stream)
    except Exception:
        return None, raw
    if not isinstance(payload, dict):
        return None, raw
    return payload, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _delegate_to_evaluated_hook(payload: dict[str, Any], raw: bytes) -> bool:
    """True when this process is done (delegated, or mismatch already emitted).

    Unrelated repositories (including the tmp repos in this hook's own tests)
    are not a source mismatch — only linked worktrees of the same clone.
    """
    if os.environ.get(DELEGATION_ENV):
        return False
    source = _hook_source_root().resolve()
    evaluated = _repo_root(payload)
    if evaluated is None:
        return False
    evaluated = evaluated.resolve()
    if source == evaluated:
        return False
    if not _same_git_repository(source, evaluated):
        return False
    event = str(payload.get("hook_event_name") or "")
    target = evaluated / TARGET_HOOK_REL
    status = _classify_hook_target(target)
    if status != "ok":
        detail = {
            "missing": "target hook unavailable",
            "unreadable": "target hook unreadable",
            "malformed": "target hook malformed",
        }.get(status, status)
        _emit_hook_source_mismatch(
            event,
            _format_hook_source_mismatch(source, evaluated, detail),
        )
        return True
    try:
        outcome = _spawn_delegated_guard(target, raw, cwd=evaluated)
    except Exception as exc:
        _emit_hook_source_mismatch(
            event,
            _format_hook_source_mismatch(
                source, evaluated, f"target hook spawn failed: {exc}"
            ),
        )
        return True
    if isinstance(outcome, tuple):
        returncode, child_stdout, child_stderr = outcome
    else:
        # Test stubs and one-revision rolling compatibility may still return
        # the historical integer result.
        returncode, child_stdout, child_stderr = int(outcome), b"", b""
    if not returncode:
        _write_hook_bytes(sys.stdout, child_stdout)
        _write_hook_bytes(sys.stderr, child_stderr)
        return True
    # A failing child may have emitted a partial/allow JSON before crashing.
    # Hook stdout must remain ONE authoritative denial, so retain diagnostics
    # on stderr only.
    _write_hook_bytes(sys.stderr, child_stdout)
    _write_hook_bytes(sys.stderr, child_stderr)
    if returncode:
        _emit_hook_source_mismatch(
            event,
            _format_hook_source_mismatch(
                source, evaluated, f"target hook exited nonzero ({returncode})"
            ),
        )
    return True


def main() -> None:
    payload, raw = _load_payload_and_raw()
    if payload is None:
        return
    if str(payload.get("hook_event_name") or "") == "PreToolUse":
        # Ordinary Bash remains fail-open because _watcher_request returns
        # before touching state. A command already classified as watcher-shaped
        # fails CLOSED if admission itself crashes: allowing an untracked wait
        # is exactly how duplicate/no-progress model wakes bypass the gate.
        try:
            _pre_tool_use(payload, raw)
        except Exception:
            try:
                watch = _watcher_request(payload)
            except Exception:
                watch = None
            if watch is not None:
                _deny_watcher(
                    "SHIP WATCHER REFUSED: watcher admission was unanswerable, "
                    "so safe single-owner tracking could not be proven."
                )
        return
    if _delegate_to_evaluated_hook(payload, raw):
        return
    root = _repo_root(payload)
    if root is None:
        return
    event = str(payload.get("hook_event_name") or "")
    path: Path | None = None
    try:
        path = _state_path(root, payload)
        if event == "SessionStart":
            _session_start(root, path, payload)
        elif event == "Stop":
            _stop(root, path, payload)
    except Exception as exc:
        # A broken enforcement hook must be visible, but must not brick Claude.
        # Route the guard_error through `_block` so the any-code escape ladder can
        # release a PERSISTENTLY crashing guard — a bug in the hook itself used to
        # brick a session forever, with no counter and no exit. guard_error stays
        # OUT of EXTERNAL_BLOCKERS, so it is escapable only via the 10-consecutive /
        # 15-total any-code ceiling, never the low external one.
        if event == "Stop":
            reason = (
                "The completion guard failed unexpectedly: "
                f"{exc}. Repair `.claude/hooks/ship_loop_guard.py` before stopping."
            )
            state = _load(path) if path is not None else None
            if state is not None and path is not None:
                try:
                    _block(path, state, payload, "guard_error", reason)
                    return
                except Exception:
                    pass
            _emit(
                {
                    "decision": "block",
                    "reason": f"SHIP LOOP guard_error: {reason}",
                }
            )
        elif event == "SessionStart":
            _emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": (
                            "SHIP LOOP guard_error: mandatory enforcement did not load: "
                            f"{exc}. Repair `.claude/hooks/ship_loop_guard.py` and the "
                            "private session ledger path before modifying repository state."
                        ),
                    }
                }
            )


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--confirm-watcher":
        try:
            confirmed = _confirm_watcher(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
        except Exception as exc:
            print(f"SHIP WATCHER confirmation failed: {exc}", file=sys.stderr)
            confirmed = False
        raise SystemExit(0 if confirmed else 1)
    main()
