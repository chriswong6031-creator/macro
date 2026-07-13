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
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("metabolism_gc")

_WATCHED_PATTERNS = ("wf_*", "metabolism-*", "claude/loop-*", "metabolism/*")

_TERMINAL_STATUSES = frozenset({"done", "failed"})

# F3(b): propose-branch reaper retention window (days).  Propose branches whose
# cycle_id is parseable as a date and older than this threshold are eligible for
# deletion when they also have a terminal journal record.
_PROPOSE_BRANCH_RETENTION_DAYS = 7


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


# ── Stale running marker sweep (R-V5-2) ──────────────────────────────────────

def _load_budget_ttl(repo_root: Path) -> float:
    """Load stale_running_ttl_hours from metabolism_budget.yml.  Returns 3.0 on error."""
    try:
        import yaml
        cfg_path = repo_root / "config" / "metabolism_budget.yml"
        with open(cfg_path) as fh:
            cfg = yaml.safe_load(fh) or {}
        return float(cfg.get("stale_running_ttl_hours", 3))
    except Exception as exc:  # noqa: BLE001
        log.warning("GC: _load_budget_ttl: %s — defaulting to 3h", exc)
        return 3.0


def sweep_stale_running_markers(repo_root: Path, dry_run: bool = False) -> dict:
    """Rewrite stale 'running' journal markers to 'failed' with a GC note (R-V5-2).

    A 'running' marker is stale when its started_at is older than
    stale_running_ttl_hours (from metabolism_budget.yml, default 3h).

    This sweep writes journal state ONLY — it never dispatches, never touches
    git worktrees, and never reads secret values.

    Returns a summary dict: {"swept": int, "errors": list[str]}.
    NEVER raises.
    """
    summary: dict = {"swept": 0, "errors": []}
    try:
        ttl_hours = _load_budget_ttl(repo_root)
        ttl = timedelta(hours=ttl_hours)
        now = datetime.now(timezone.utc)

        journal_dir = repo_root / "data" / "metabolism" / "journal"
        if not journal_dir.exists():
            return summary

        for jf in sorted(journal_dir.glob("*.json")):
            cycle_id = jf.stem
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("GC: stale-running sweep: cannot read %s: %s", jf, exc)
                summary["errors"].append(f"{cycle_id}: read error: {exc}")
                continue

            stages = data.get("stages") or {}
            modified = False
            for stage_name, stage_rec in stages.items():
                if stage_rec.get("status") != "running":
                    continue
                started_at_str = stage_rec.get("started_at", "")
                if not started_at_str:
                    continue
                try:
                    if started_at_str.endswith("Z"):
                        started_at_str = started_at_str[:-1] + "+00:00"
                    started_at = datetime.fromisoformat(started_at_str).astimezone(timezone.utc)
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "GC: stale-running sweep: cannot parse started_at %r in %s/%s: %s",
                        started_at_str, cycle_id, stage_name, exc,
                    )
                    continue

                age = now - started_at
                if age <= ttl:
                    continue

                # Stale — rewrite to "failed" with a GC note
                log.info(
                    "GC: stale running marker: cycle=%s stage=%s age=%.1fh > ttl=%.1fh — "
                    "rewriting to 'failed'",
                    cycle_id, stage_name, age.total_seconds() / 3600, ttl_hours,
                )
                if not dry_run:
                    stage_rec["status"] = "failed"
                    stage_rec["finished_at"] = now.isoformat(timespec="seconds")
                    # Preserve prior note if any; append GC annotation
                    prior_note = stage_rec.get("note", "")
                    try:
                        note_data = json.loads(prior_note) if prior_note.startswith("{") else {}
                    except Exception:  # noqa: BLE001
                        note_data = {}
                    note_data["_gc_note"] = "stale_running reaped by gc"
                    note_data["_failed_attempts"] = int(note_data.get("_failed_attempts", 0)) + 1
                    stage_rec["note"] = json.dumps(note_data, separators=(",", ":"))
                    stages[stage_name] = stage_rec
                    modified = True
                summary["swept"] += 1

            if modified and not dry_run:
                # Update top-level ts; write back atomically
                data["stages"] = stages
                data["ts"] = now.isoformat(timespec="seconds")
                try:
                    tmp = jf.with_suffix(".tmp")
                    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
                    tmp.replace(jf)
                except Exception as exc:  # noqa: BLE001
                    log.warning("GC: stale-running sweep: write failed for %s: %s", jf, exc)
                    summary["errors"].append(f"{cycle_id}: write error: {exc}")

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_gc.sweep_stale_running_markers: %s", exc)
        summary["errors"].append(str(exc))

    return summary


# ── Propose-branch reaper (F3b) ──────────────────────────────────────────────

def _is_paused() -> bool:
    """Return True unless AUTONOMY_PAUSED is the exact string 'false'. NEVER raises."""
    try:
        from scripts.metabolism_guard import is_paused  # type: ignore[import]
        return is_paused()
    except Exception as exc:  # noqa: BLE001
        log.warning("GC: _is_paused: %s — treating as paused", exc)
        return True


def _parse_cycle_date(cycle_id: str) -> datetime | None:
    """Extract a UTC date from a cycle_id with a date-like prefix (YYYY-MM-DD...).

    Returns None if the cycle_id does not begin with a parseable date.
    NEVER raises.
    """
    try:
        # Cycle IDs typically look like "cycle-2026-07-10-abc123" or "2026-07-10-abc".
        # Walk through the parts to find a YYYY-MM-DD segment.
        for i in range(min(len(cycle_id), 20)):
            candidate = cycle_id[i:i+10]
            if len(candidate) < 10:
                break
            try:
                return datetime.strptime(candidate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
    except Exception:  # noqa: BLE001
        return None


def reap_propose_branches(repo_root: Path, dry_run: bool = False) -> dict:
    """Delete remote metabolism/propose-* branches for terminal cycles older than
    _PROPOSE_BRANCH_RETENTION_DAYS.

    GATE: this function is a WRITE action — it is gated on AUTONOMY_PAUSED being
    the exact string 'false' (same gate the other autonomous stages use).  When
    the loop is paused, propose-branch deletion is suppressed; worktree reaping
    (which is read-only discovery + local-fs removal, not a remote write) stays
    ungated.

    Eligibility criteria for deletion:
      - Remote branch name matches metabolism/propose-<cycle_id>
      - cycle_id has a parseable date prefix AND that date is older than the
        retention window  (prevents deleting very fresh cycles whose PRs may still
        be in flight)
      - The corresponding journal record in data/metabolism/journal/<cycle_id>.json
        has a terminal top-level status ("done" or "failed") or at least one
        terminal stage — confirms the cycle actually completed before deletion

    Returns a summary dict: {"deleted": list[str], "skipped": list[str], "errors": list[str]}.
    NEVER raises.
    """
    summary: dict = {"deleted": [], "skipped": [], "errors": []}

    # GATE: branch deletion is a write action — respect the autonomous loop pause.
    if _is_paused():
        log.info("GC propose-branch reaper: AUTONOMY_PAUSED — skipping branch deletion (ungated worktree reap still runs)")
        return summary

    try:
        now = datetime.now(timezone.utc)
        retention = timedelta(days=_PROPOSE_BRANCH_RETENTION_DAYS)

        # Enumerate all remote propose-* branches
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", "refs/heads/metabolism/propose-*"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.warning("GC propose-branch reaper: git ls-remote failed: %s", result.stderr[:200])
            return summary

        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            ref = parts[1]  # refs/heads/metabolism/propose-<cycle_id>
            if not ref.startswith("refs/heads/metabolism/propose-"):
                continue
            cycle_id = ref[len("refs/heads/metabolism/propose-"):]
            if not cycle_id:
                continue

            # Age filter: only delete branches whose cycle_id date prefix is older
            # than the retention window.  Fresh or undated cycles are always skipped.
            cycle_date = _parse_cycle_date(cycle_id)
            if cycle_date is None:
                log.info("GC propose-branch reaper: %s — no parseable date prefix, skipping", cycle_id)
                summary["skipped"].append(cycle_id)
                continue
            age = now - cycle_date
            if age < retention:
                log.info(
                    "GC propose-branch reaper: %s — age %.1fd < retention %dd, skipping",
                    cycle_id, age.days + age.seconds / 86400, _PROPOSE_BRANCH_RETENTION_DAYS,
                )
                summary["skipped"].append(cycle_id)
                continue

            # Terminal check: require a journal record with terminal status.
            journal_path = repo_root / "data" / "metabolism" / "journal" / f"{cycle_id}.json"
            if not journal_path.exists():
                log.info("GC propose-branch reaper: %s — no journal record, skipping", cycle_id)
                summary["skipped"].append(cycle_id)
                continue
            try:
                jdata = json.loads(journal_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("GC propose-branch reaper: %s — journal read error: %s", cycle_id, exc)
                summary["errors"].append(f"{cycle_id}: journal read error: {exc}")
                continue

            is_terminal = (
                jdata.get("status") in _TERMINAL_STATUSES
                or any(
                    s.get("status") in _TERMINAL_STATUSES
                    for s in (jdata.get("stages") or {}).values()
                )
            )
            if not is_terminal:
                log.info("GC propose-branch reaper: %s — journal not terminal, skipping", cycle_id)
                summary["skipped"].append(cycle_id)
                continue

            # Eligible — delete the remote branch
            branch = f"metabolism/propose-{cycle_id}"
            if dry_run:
                log.info("GC propose-branch reaper [DRY-RUN]: would delete remote %s", branch)
                summary["deleted"].append(branch)
                continue
            del_result = subprocess.run(
                ["git", "push", "origin", "--delete", branch],
                cwd=str(repo_root), capture_output=True, text=True, timeout=60,
            )
            if del_result.returncode == 0:
                log.info("GC propose-branch reaper: deleted remote %s", branch)
                summary["deleted"].append(branch)
            else:
                # Non-fatal: branch may have been deleted already by merge lane
                log.warning(
                    "GC propose-branch reaper: could not delete %s (non-fatal): %s",
                    branch, del_result.stderr[:200],
                )
                summary["errors"].append(f"{branch}: {del_result.stderr[:100]}")

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_gc.reap_propose_branches: %s", exc)
        summary["errors"].append(str(exc))

    return summary


# ── Insight bus compaction (F2) ──────────────────────────────────────────────

def compact_insight_bus(repo_root: Path, dry_run: bool = False) -> dict:
    """Compact data/metabolism/insight_bus.jsonl via insight_bus.compact_bus().

    Runs even when the metabolism loop is paused (GC is always active).
    Atomic rewrite — safe to interrupt.  NEVER raises.

    Returns a summary dict: {retained, archived, errors}.
    """
    if dry_run:
        log.info("GC [DRY-RUN]: would compact insight_bus.jsonl")
        return {"retained": 0, "archived": 0, "errors": [], "dry_run": True}
    try:
        from engine.metabolism.insight_bus import compact_bus  # noqa: PLC0415
        result = compact_bus(root=repo_root)
        log.info(
            "GC insight_bus compact: retained=%d archived=%d errors=%d",
            result.get("retained", 0),
            result.get("archived", 0),
            len(result.get("errors") or []),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("GC compact_insight_bus: %s", exc)
        return {"retained": 0, "archived": 0, "errors": [str(exc)]}


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
    parser.add_argument("--sweep-stale-running", action="store_true",
                        help="Also rewrite stale 'running' journal markers to 'failed'. "
                             "OFF by default: the cron GC lane runs on a main checkout "
                             "with contents:read where journals don't exist and writes "
                             "can't be committed (#2295 review F2) — the sweep runs "
                             "in-process in the BUILD lane instead, where its rewrites "
                             "ride the lane's own journal commit.")
    args = parser.parse_args(argv)

    if args.root:
        repo_root = Path(args.root)
    else:
        # Auto-detect: scripts/ parent
        repo_root = Path(__file__).resolve().parent.parent

    log.info("GC: repo_root=%s dry_run=%s", repo_root, args.dry_run)

    # Stale running marker sweep (R-V5-2): opt-in only (see --sweep-stale-running help)
    if args.sweep_stale_running:
        sweep_result = sweep_stale_running_markers(repo_root, dry_run=args.dry_run)
        log.info(
            "GC stale-running sweep: swept=%d errors=%d",
            sweep_result["swept"],
            len(sweep_result["errors"]),
        )

    # F3(b): propose-branch reaper — gated on AUTONOMY_PAUSED='false' (write action).
    # Runs alongside every GC invocation; always exits 0 on failure (never fatal).
    propose_result = reap_propose_branches(repo_root, dry_run=args.dry_run)
    log.info(
        "GC propose-branch reaper: deleted=%d skipped=%d errors=%d",
        len(propose_result["deleted"]),
        len(propose_result["skipped"]),
        len(propose_result["errors"]),
    )

    # Insight bus compaction (F2): always runs (acceptable ungated — loop-internal state)
    bus_result = compact_insight_bus(repo_root, dry_run=args.dry_run)
    if bus_result.get("errors"):
        log.warning("GC insight_bus compact errors: %s", bus_result["errors"])

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
