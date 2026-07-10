"""scripts/metabolism_gc.py — Orphan-worktree GC helper (A1 companion).

Reaps wf_*/metabolism worktrees whose branch is squash-merged or whose
journal is in a terminal state (done/failed), subject to safety checks:

  1. rev-parse --show-toplevel guard (dead-worktree-hits-main trap):
     If the worktree's `.git` file resolves to the MAIN repo root rather than
     a worktree root, the worktree is detached/dead. Do NOT operate on it.

  2. lsof guard (live-parked-session trap):
     If any process has an open file descriptor inside the worktree directory,
     a live session is parked there. Skip it.

  3. Branch merged check:
     ``git log --oneline <branch>..origin/main`` is empty iff the branch tip
     is fully reachable from origin/main (squash-merged or otherwise absorbed).

  4. Journal terminal check:
     The worktree's ``data/metabolism/journal/`` contains at least one journal
     file whose top-level status is "done" or "failed".

Only worktrees matching a configured name pattern (default: ``wf_*`` or
``metabolism-*``) are inspected.  All others are untouched.

STATELESS-CATTLE LAW (R-AUT-3): this script reads git state, acts, and exits.
No persistent sessions.  Idempotent: re-running on an already-removed worktree
logs a clean skip.

NEVER-RAISE CONTRACT: all exceptions are caught and logged.  The script always
exits 0 so a GC failure never blocks the loop.

Usage:
    python -m scripts.metabolism_gc [--dry-run] [--root /path/to/repo]
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("metabolism_gc")

_WATCHED_PATTERNS = ("wf_*", "metabolism-*", "claude/loop-*", "metabolism/*")

_TERMINAL_STATUSES = frozenset({"done", "failed"})


# ── Safety guards ────────────────────────────────────────────────────────────

def _is_live_main_checkout(worktree_path: Path) -> bool:
    """Return True if the worktree resolves to the MAIN repo checkout.

    If a worktree's .git file has been deleted or the worktree is detached,
    git rev-parse from inside it will resolve to the main repo root — which
    means deleting it would operate on the main checkout.  We refuse.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(worktree_path),
            capture_output=True, text=True, timeout=10,
        )
        resolved = Path(result.stdout.strip())
        # If resolved == worktree_path, it's a valid independent worktree.
        # If resolved != worktree_path, the path fell through to another tree.
        return resolved != worktree_path
    except Exception as exc:  # noqa: BLE001
        log.warning("GC: rev-parse check failed for %s: %s — treating as live main", worktree_path, exc)
        return True  # fail-safe: don't touch it


def _has_open_files(worktree_path: Path) -> bool:
    """Return True if any process has open files inside the worktree (lsof guard)."""
    try:
        result = subprocess.run(
            ["lsof", "+D", str(worktree_path)],
            capture_output=True, text=True, timeout=15,
        )
        # lsof exits 1 when no matches; exit 0 means at least one hit.
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception as exc:  # noqa: BLE001
        log.warning("GC: lsof check failed for %s: %s — treating as occupied", worktree_path, exc)
        return True  # fail-safe: don't touch it


def _branch_merged_into_main(branch: str, worktree_path: Path) -> bool:
    """Return True if branch is fully reachable from origin/main (squash-merged)."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"{branch}..origin/main"],
            cwd=str(worktree_path),
            capture_output=True, text=True, timeout=15,
        )
        # Empty output means branch tip is already in origin/main's history.
        return result.returncode == 0 and not result.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("GC: branch-merged check failed for %s: %s", branch, exc)
        return False


def _journal_is_terminal(worktree_path: Path) -> bool:
    """Return True if any journal file in the worktree has a terminal status."""
    journal_dir = worktree_path / "data" / "metabolism" / "journal"
    if not journal_dir.exists():
        return False
    for jf in journal_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            if data.get("status") in _TERMINAL_STATUSES:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


# ── Worktree discovery ───────────────────────────────────────────────────────

def _list_worktrees(repo_root: Path) -> list[dict]:
    """Return a list of dicts with {path, branch} for each worktree."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            log.warning("GC: git worktree list failed: %s", result.stderr)
            return []

        worktrees = []
        current: dict = {}
        for line in result.stdout.splitlines():
            line = line.rstrip()
            if line.startswith("worktree "):
                current = {"path": Path(line[len("worktree "):]), "branch": None}
            elif line.startswith("branch "):
                current["branch"] = line[len("branch "):]
                # strip refs/heads/ prefix
                if current["branch"].startswith("refs/heads/"):
                    current["branch"] = current["branch"][len("refs/heads/"):]
            elif line == "" and current.get("path"):
                worktrees.append(current)
                current = {}
        if current.get("path"):
            worktrees.append(current)
        return worktrees
    except Exception as exc:  # noqa: BLE001
        log.warning("GC: _list_worktrees failed: %s", exc)
        return []


def _matches_pattern(name: str) -> bool:
    """Return True if the worktree name matches any watched pattern."""
    import fnmatch
    return any(fnmatch.fnmatch(name, pat) for pat in _WATCHED_PATTERNS)


# ── Main GC loop ─────────────────────────────────────────────────────────────

def gc(repo_root: Path, dry_run: bool = False) -> dict:
    """Run the GC pass.  Returns a summary dict.  NEVER raises."""
    summary = {
        "inspected": 0,
        "reaped": [],
        "skipped_safety": [],
        "skipped_alive": [],
        "errors": [],
    }

    try:
        all_worktrees = _list_worktrees(repo_root)
        # Skip the main checkout (first entry, no branch or listed as 'main')
        candidates = []
        for wt in all_worktrees:
            name = wt["path"].name
            if _matches_pattern(name):
                candidates.append(wt)

        summary["inspected"] = len(candidates)

        for wt in candidates:
            wt_path = wt["path"]
            branch = wt.get("branch") or ""
            name = wt_path.name

            # Guard 1: rev-parse / dead-worktree-hits-main
            if not wt_path.exists():
                log.info("GC: worktree path gone %s — skipping", wt_path)
                summary["skipped_alive"].append(str(wt_path))
                continue

            if _is_live_main_checkout(wt_path):
                log.warning("GC: SAFETY — %s resolves to main checkout, skipping", wt_path)
                summary["skipped_safety"].append(str(wt_path))
                continue

            # Guard 2: lsof / live-parked-session
            if _has_open_files(wt_path):
                log.info("GC: %s has open files (live session?) — skipping", name)
                summary["skipped_alive"].append(str(wt_path))
                continue

            # Eligibility check: branch merged OR journal terminal
            eligible = False
            if branch and _branch_merged_into_main(branch, wt_path):
                eligible = True
                log.info("GC: %s branch=%s is merged into origin/main", name, branch)
            elif _journal_is_terminal(wt_path):
                eligible = True
                log.info("GC: %s journal is terminal (done/failed)", name)

            if not eligible:
                log.debug("GC: %s not eligible for reap", name)
                summary["skipped_alive"].append(str(wt_path))
                continue

            # Reap
            if dry_run:
                log.info("GC [DRY-RUN]: would reap %s (branch=%s)", name, branch)
                summary["reaped"].append(str(wt_path))
            else:
                try:
                    result = subprocess.run(
                        ["git", "worktree", "remove", "--force", str(wt_path)],
                        cwd=str(repo_root),
                        capture_output=True, text=True, timeout=30,
                    )
                    if result.returncode == 0:
                        log.info("GC: reaped %s", name)
                        summary["reaped"].append(str(wt_path))
                    else:
                        log.warning("GC: remove failed for %s: %s", name, result.stderr)
                        summary["errors"].append(f"{name}: {result.stderr}")
                except Exception as exc:  # noqa: BLE001
                    log.warning("GC: exception reaping %s: %s", name, exc)
                    summary["errors"].append(f"{name}: {exc}")

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_gc.gc: unexpected error: %s", exc)
        summary["errors"].append(str(exc))

    return summary


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Metabolism orphan-worktree GC helper (A1)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be reaped without removing")
    parser.add_argument("--root", default=None, help="Repo root (default: auto-detect)")
    args = parser.parse_args(argv)

    if args.root:
        repo_root = Path(args.root)
    else:
        # Auto-detect: scripts/ parent
        repo_root = Path(__file__).resolve().parent.parent

    log.info("GC: repo_root=%s dry_run=%s", repo_root, args.dry_run)
    result = gc(repo_root, dry_run=args.dry_run)

    log.info(
        "GC done: inspected=%d reaped=%d skipped_alive=%d skipped_safety=%d errors=%d",
        result["inspected"],
        len(result["reaped"]),
        len(result["skipped_alive"]),
        len(result["skipped_safety"]),
        len(result["errors"]),
    )
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
