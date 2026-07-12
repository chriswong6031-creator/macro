"""scripts/metabolism_revert.py — Revert-plan executor (R-V8-6).

Scans data/metabolism/verify/*.json for records whose triage.action ==
'revert_plan' and that have NOT been actioned yet (durable actioned-marker
keyed by proposal_id under data/metabolism/revert/).

For each un-actioned revert plan (bounded by max_open_revert_prs from
config/metabolism_budget.yml, default 2):
  1. Resolves the proposal's merged PR number from the verify record / journal.
  2. Resolves the squash-merge commit SHA via `gh pr view --json mergeCommit`.
  3. Creates a temp worktree off origin/main via `git worktree add`.
  4. Runs `git revert <sha> --no-edit` inside the worktree.
     On conflict: aborts (`git revert --abort`), marks actioned with
     status='revert_conflict', records an insight, and moves on.
     NEVER forces through a conflicted revert.
  5. Opens a DRAFT revert PR whose body carries:
     - The do_not_rebuild_row from the plan.
     - Provenance (proposal_id, cycle_id, verify record path).
  6. Writes a durable actioned-marker to data/metabolism/revert/<proposal_id>.json.

SAFETY:
- NEVER auto-merges the revert PR (merging is a future ruling, see masterplan).
- NEVER touches operator_tap records (measurement-lens law).
- AUTONOMY_PAUSED double-gate: first action is the guard check; if paused,
  logs and exits 0 (no marker written = scan will retry when armed again).
- Cron workflow NOT included in this PR — lane invoked manually / wired later.

Exit 0 always (NEVER raises).

Usage:
    python -m scripts.metabolism_revert [--root /path/to/repo] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_revert")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_VERIFY_DIR = Path("data") / "metabolism" / "verify"
_REVERT_DIR = Path("data") / "metabolism" / "revert"
_ACTIONED_SCHEMA = "metabolism.revert_actioned.v1"


# ── Guard ───────────────────────────────────────────────────────────────────���─

def _is_paused() -> bool:
    """Fail-closed kill switch.  NEVER raises."""
    try:
        from scripts.metabolism_guard import is_paused
        return is_paused()
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._is_paused: %s — treating as paused", exc)
        return True


def _pause_reason() -> str:
    try:
        from scripts.metabolism_guard import pause_reason
        return pause_reason()
    except Exception:  # noqa: BLE001
        return "unknown pause reason"


# ── Budget config ─────────────────────────────────────────────────────────────

def _load_max_open_revert_prs(root: Path) -> int:
    """Read max_open_revert_prs from metabolism_budget.yml.  Default=2.  NEVER raises."""
    try:
        import yaml  # noqa: PLC0415
        p = root / "config" / "metabolism_budget.yml"
        if not p.exists():
            return 2
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        v = cfg.get("max_open_revert_prs", 2)
        return max(1, int(v))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._load_max_open_revert_prs: %s — default 2", exc)
        return 2


_REVERT_BRANCH_PREFIX = "claude/metabolism-revert-"
_REVERT_BRANCH_PREFIX_SHORT = "metabolism/revert-"


_COUNT_OPEN_PRS_ERROR = -1  # sentinel: gh call failed → fail closed


def _count_open_revert_prs(root: Path) -> int:
    """Count currently-open revert PRs opened by this lane.

    Queries 'gh pr list --state open' and counts PRs whose head branch starts
    with the revert prefix.

    FIX-B4: Returns _COUNT_OPEN_PRS_ERROR (-1) on ANY gh failure so the caller
    can fail closed (open zero new PRs this run) rather than treating a gh
    outage as "no PRs open" (which would allow up to max_prs NEW PRs while
    max_prs are already open).  NEVER raises.

    FIX-3: bound is on SIMULTANEOUSLY-OPEN PRs, not per-run count.
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--state", "open",
                "--json", "number,headRefName",
                "--limit", "100",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.warning(
                "metabolism_revert._count_open_revert_prs: gh pr list exited %d: %s "
                "— failing closed (no new revert PRs this run)",
                result.returncode, result.stderr[:200],
            )
            return _COUNT_OPEN_PRS_ERROR  # FIX-B4: fail closed
        prs = json.loads(result.stdout or "[]")
        count = sum(
            1 for pr in prs
            if str(pr.get("headRefName") or "").startswith(_REVERT_BRANCH_PREFIX)
            or str(pr.get("headRefName") or "").startswith(_REVERT_BRANCH_PREFIX_SHORT)
        )
        log.info("metabolism_revert._count_open_revert_prs: found %d open revert PR(s)", count)
        return count
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "metabolism_revert._count_open_revert_prs: %s — failing closed "
            "(no new revert PRs this run)",
            exc,
        )
        return _COUNT_OPEN_PRS_ERROR  # FIX-B4: fail closed


# ── Actioned-marker helpers ───────────────────────────────────────────────────

def _actioned_path(proposal_id: str, root: Path) -> Path:
    return root / _REVERT_DIR / f"{proposal_id}.json"


_RETRYABLE_STATUSES = frozenset({"revert_pr_open_failed"})


def _is_actioned(proposal_id: str, root: Path) -> bool:
    """True if a durable actioned-marker exists AND is NOT a retryable status.

    FIX-4: 'revert_pr_open_failed' markers allow retry — they are NOT treated
    as permanently actioned.  NEVER raises.
    """
    try:
        p = _actioned_path(proposal_id, root)
        if not p.exists():
            return False
        # If the marker carries a retryable status, the plan is NOT actioned
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("status") in _RETRYABLE_STATUSES:
                log.info(
                    "metabolism_revert._is_actioned: proposal=%s has retryable "
                    "status=%s — treating as unactioned for retry",
                    proposal_id, data.get("status"),
                )
                return False
        except Exception:  # noqa: BLE001
            pass  # unreadable marker → treat as actioned (fail-closed)
        return True
    except Exception:  # noqa: BLE001
        return False


def _write_actioned_marker(
    proposal_id: str,
    status: str,
    pr_number: int | None,
    root: Path,
    *,
    extra: dict | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write a durable actioned-marker.  NEVER raises."""
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        marker: dict[str, Any] = {
            "schema": _ACTIONED_SCHEMA,
            "ts": ts,
            "proposal_id": proposal_id,
            "status": status,
            "pr_number": pr_number,
        }
        if extra:
            marker.update(extra)
        if dry_run:
            log.info("metabolism_revert [dry-run] actioned-marker: %s", marker)
            return marker
        p = _actioned_path(proposal_id, root)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(marker, indent=2, default=str), encoding="utf-8")
        tmp.replace(p)
        log.info("metabolism_revert: wrote actioned marker %s status=%s", p, status)
        return marker
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._write_actioned_marker(%s): %s", proposal_id, exc)
        return {"schema": _ACTIONED_SCHEMA, "proposal_id": proposal_id,
                "status": status, "error": str(exc)}


# ── Scan helpers ──────────────────────────────────────────────────────────────

def _scan_unactioned_revert_plans(root: Path) -> list[dict[str, Any]]:
    """Scan verify/*.json for un-actioned revert_plan records.

    Returns list of dicts: {proposal_id, cycle_id, verify_path, revert_plan,
    do_not_rebuild_row}.
    NEVER raises.
    """
    plans: list[dict[str, Any]] = []
    try:
        verify_dir = root / _VERIFY_DIR
        if not verify_dir.exists():
            log.info("metabolism_revert: no verify dir — nothing to scan")
            return plans

        for vf in sorted(verify_dir.glob("*.json")):
            try:
                data = json.loads(vf.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("metabolism_revert: cannot read %s: %s", vf, exc)
                continue

            triage = data.get("triage") or {}
            if triage.get("action") != "revert_plan":
                continue
            revert_plan = triage.get("revert_plan") or {}
            if not isinstance(revert_plan, dict):
                continue
            if revert_plan.get("action") != "git_revert":
                continue

            proposal_id = str(
                data.get("proposal_id")
                or revert_plan.get("proposal_id")
                or vf.stem
            )
            if _is_actioned(proposal_id, root):
                log.debug(
                    "metabolism_revert: proposal=%s already actioned — skip", proposal_id,
                )
                continue

            plans.append({
                "proposal_id": proposal_id,
                "cycle_id": str(data.get("cycle_id") or vf.stem),
                "verify_path": str(vf),
                "revert_plan": revert_plan,
                "do_not_rebuild_row": revert_plan.get("do_not_rebuild_row") or {},
            })

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._scan_unactioned_revert_plans: %s", exc)

    return plans


# ── PR + SHA resolution ───────────────────────────────────────────────────────

def _resolve_pr_number(plan_record: dict[str, Any], root: Path) -> int | None:
    """Try to resolve the PR number from journal or revert_plan.  NEVER raises.

    Looks in:
    1. revert_plan.target (branch name) → journal stages for a pr_number
    2. data/metabolism/journal/<cycle_id>.json → any stage with pr_number
    3. Returns None if unresolvable.
    """
    try:
        cycle_id = plan_record.get("cycle_id") or ""
        revert_plan = plan_record.get("revert_plan") or {}
        proposal_id = plan_record.get("proposal_id") or ""

        # Try journal
        journal_path = root / "data" / "metabolism" / "journal" / f"{cycle_id}.json"
        if journal_path.exists():
            try:
                jdata = json.loads(journal_path.read_text(encoding="utf-8"))
                stages = jdata.get("stages") or {}
                for stage_name, stage in stages.items():
                    if not isinstance(stage, dict):
                        continue
                    pr = stage.get("pr_number") or stage.get("pr") or {}
                    if isinstance(pr, dict):
                        n = pr.get("number") or pr.get("pr_number")
                    else:
                        n = pr
                    if n:
                        try:
                            return int(n)
                        except (ValueError, TypeError):
                            pass
                    # Also check note field
                    note_raw = stage.get("note") or ""
                    try:
                        note = json.loads(note_raw) if isinstance(note_raw, str) else note_raw
                        n = (note or {}).get("pr_number")
                        if n:
                            return int(n)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as exc:  # noqa: BLE001
                log.warning("metabolism_revert._resolve_pr_number journal: %s", exc)

        log.info(
            "metabolism_revert._resolve_pr_number: could not resolve PR for "
            "proposal=%s cycle=%s", proposal_id, cycle_id,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._resolve_pr_number: %s", exc)
        return None


def _resolve_merge_sha(pr_number: int, root: Path) -> str | None:
    """Use `gh pr view <pr_number> --json mergeCommit` to get the squash SHA.

    Returns None on any error (gh not available, PR not merged, etc.).
    NEVER raises.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "mergeCommit"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.warning(
                "metabolism_revert._resolve_merge_sha: gh pr view #%d exited %d: %s",
                pr_number, result.returncode, result.stderr[:200],
            )
            return None
        data = json.loads(result.stdout)
        mc = data.get("mergeCommit") or {}
        sha = str(mc.get("oid") or "").strip()
        if not sha:
            log.info(
                "metabolism_revert._resolve_merge_sha: PR #%d has no mergeCommit.oid "
                "(not yet merged?)",
                pr_number,
            )
            return None
        return sha
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._resolve_merge_sha(#%d): %s", pr_number, exc)
        return None


# ── Worktree helpers ──────────────────────────────────────────────────────────

def _create_revert_worktree(branch: str, root: Path) -> dict[str, Any]:
    """Create a temp worktree off origin/main for the revert.  NEVER raises.

    FIX-B2: On a retry (status=revert_pr_open_failed) the branch was already
    pushed on the previous attempt.  If 'git worktree add -b ...' reports
    'branch already exists', we fall back to 'git worktree add --track' to
    check out the existing branch instead of failing with a non-retryable error.
    """
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=str(root), capture_output=True, timeout=60,
        )
        # Also fetch the branch itself in case it exists on origin from a prior attempt
        subprocess.run(
            ["git", "fetch", "origin", branch],
            cwd=str(root), capture_output=True, timeout=60,
        )
        # Worktree path: sibling of repo root
        wt_path = root.parent / branch.replace("/", "_")
        if wt_path.exists():
            log.info("metabolism_revert: worktree already exists at %s", wt_path)
            return {"wt_path": str(wt_path), "error": None}
        # Try the normal new-branch path first
        result = subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", branch, "origin/main"],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return {"wt_path": str(wt_path), "error": None}

        stderr_lower = (result.stderr or "").lower()
        # FIX-B2: detect "branch already exists" and reuse the existing remote branch
        if "already exists" in stderr_lower or "branch named" in stderr_lower:
            log.info(
                "metabolism_revert: branch %s already exists (likely from a prior attempt) "
                "— retrying worktree add without -b to reuse the branch",
                branch,
            )
            # Try to add the worktree using the existing branch from origin
            r2 = subprocess.run(
                ["git", "worktree", "add", str(wt_path), f"origin/{branch}"],
                cwd=str(root), capture_output=True, text=True, timeout=60,
            )
            if r2.returncode == 0:
                # Set the local branch to track origin branch
                subprocess.run(
                    ["git", "-C", str(wt_path), "checkout", "-B", branch,
                     f"origin/{branch}"],
                    cwd=str(root), capture_output=True, text=True, timeout=60,
                )
                return {"wt_path": str(wt_path), "error": None}
            # If that also fails (e.g. branch not yet pushed), fall back to
            # deleting the local branch ref and re-creating
            log.info(
                "metabolism_revert: worktree add from origin/%s failed (%s) "
                "— deleting local branch ref and retrying",
                branch, r2.stderr.strip()[:200],
            )
            subprocess.run(
                ["git", "branch", "-D", branch],
                cwd=str(root), capture_output=True, text=True, timeout=30,
            )
            r3 = subprocess.run(
                ["git", "worktree", "add", str(wt_path), "-b", branch, "origin/main"],
                cwd=str(root), capture_output=True, text=True, timeout=60,
            )
            if r3.returncode == 0:
                return {"wt_path": str(wt_path), "error": None}
            return {"wt_path": None, "error": r3.stderr.strip()[:400]}

        return {"wt_path": None, "error": result.stderr.strip()[:400]}
    except Exception as exc:  # noqa: BLE001
        return {"wt_path": None, "error": str(exc)}


def _remove_revert_worktree(branch: str, wt_path: str | None, root: Path) -> None:
    """Remove a revert worktree.  NEVER raises."""
    try:
        if wt_path and Path(wt_path).exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", wt_path],
                cwd=str(root), capture_output=True, timeout=30,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._remove_revert_worktree: %s", exc)


# ── PR opening ──��─────────────────────────────────────────────────────────────

def _push_revert_branch(branch: str, wt_path: str, root: Path) -> bool:
    """Push the revert branch to origin.  Returns True on success.  NEVER raises."""
    try:
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=wt_path, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.warning(
                "metabolism_revert._push_revert_branch: push failed for %s: %s",
                branch, result.stderr[:200],
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._push_revert_branch(%s): %s", branch, exc)
        return False


def _open_draft_revert_pr(
    branch: str,
    plan_record: dict[str, Any],
    *,
    root: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Open a DRAFT revert PR.  Returns {pr_number, pr_url, opened}.  NEVER raises."""
    try:
        do_not_rebuild = plan_record.get("do_not_rebuild_row") or {}
        proposal_id = plan_record.get("proposal_id") or "unknown"
        cycle_id = plan_record.get("cycle_id") or "unknown"
        verify_path = plan_record.get("verify_path") or "unknown"
        revert_plan = plan_record.get("revert_plan") or {}

        body = (
            "## Revert PR — opened by metabolism_revert.py (R-V8-6)\n\n"
            "**DRAFT — DO NOT MERGE without operator review.**\n"
            "This PR was opened automatically because the VERIFY lane found a "
            "clean-overfit FALSIFIER_TRIPPED outcome and emitted a revert plan.\n\n"
            f"### Provenance\n"
            f"- proposal_id: `{proposal_id}`\n"
            f"- cycle_id: `{cycle_id}`\n"
            f"- verify record: `{verify_path}`\n"
            f"- target branch/sha: `{revert_plan.get('target', '')}`\n\n"
            f"### DO_NOT_REBUILD row\n"
            f"```json\n{json.dumps(do_not_rebuild, indent=2)}\n```\n\n"
            "### Notes\n"
            "- This PR is NEVER auto-merged (future ruling needed, see masterplan).\n"
            "- Cron workflow not yet wired — lane is invoked manually for now.\n"
            "- `operator_tap` records were NOT touched (measurement-lens law).\n\n"
            "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>\n"
        )

        title = f"revert({proposal_id}): auto-revert clean-overfit [DRAFT]"

        if dry_run:
            log.info(
                "metabolism_revert [dry-run] would open draft PR: %s", title,
            )
            return {"pr_number": None, "pr_url": None, "opened": False, "dry_run": True}

        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--draft",
                "--title", title,
                "--body", body,
            ],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.warning(
                "metabolism_revert._open_draft_revert_pr: gh pr create failed: %s",
                result.stderr[:200],
            )
            return {"pr_number": None, "pr_url": None, "opened": False,
                    "error": result.stderr.strip()[:300]}

        pr_url = result.stdout.strip()
        # Extract number from URL
        pr_number: int | None = None
        try:
            pr_number = int(pr_url.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            pass
        log.info("metabolism_revert: opened draft PR #%s at %s", pr_number, pr_url)
        return {"pr_number": pr_number, "pr_url": pr_url, "opened": True}

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._open_draft_revert_pr: %s", exc)
        return {"pr_number": None, "pr_url": None, "opened": False, "error": str(exc)}


# ── Insight helper ────────────────────────────────────────────────────────────

def _emit_insight(
    kind: str,
    proposal_id: str,
    summary: str,
    root: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Emit an insight-bus row.  NEVER raises."""
    try:
        from engine.metabolism.insight_bus import build_row, append_row  # noqa: PLC0415
        row = build_row(
            emitter="metabolism_revert",
            kind=kind,
            severity="medium",
            entities=[proposal_id],
            summary=summary,
        )
        if not dry_run:
            append_row(row, root=root)
        else:
            log.info("metabolism_revert [dry-run] insight: %s", summary)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._emit_insight(%s/%s): %s", kind, proposal_id, exc)


# ── Core executor ─────────────────────────────────────────────────────────────

def _process_one_plan(
    plan_record: dict[str, Any],
    root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Process one un-actioned revert plan.  NEVER raises.

    Returns a result dict with status, pr_number, and diagnostics.
    """
    proposal_id = plan_record.get("proposal_id") or "unknown"
    result: dict[str, Any] = {
        "proposal_id": proposal_id,
        "status": "pending",
    }

    try:
        # ── Resolve PR number ────────────────────────────────────────────────
        pr_number = _resolve_pr_number(plan_record, root)
        result["pr_number_source"] = pr_number

        if pr_number is None:
            msg = (
                f"Cannot resolve PR number for proposal={proposal_id} — "
                "skipping revert (manual lookup needed)"
            )
            log.warning("metabolism_revert: %s", msg)
            result["status"] = "unresolvable_pr"
            result["reason"] = msg
            _emit_insight("revert_plan_conflict", proposal_id, msg, root, dry_run=dry_run)
            return result

        # ── Resolve merge SHA ────────────────────────────────────────────────
        merge_sha = _resolve_merge_sha(pr_number, root)
        result["merge_sha"] = merge_sha

        if not merge_sha:
            msg = (
                f"Cannot resolve merge SHA for PR #{pr_number} (proposal={proposal_id}) "
                "— skipping revert (PR may not be merged yet)"
            )
            log.warning("metabolism_revert: %s", msg)
            result["status"] = "unresolvable_sha"
            result["reason"] = msg
            _emit_insight("revert_plan_conflict", proposal_id, msg, root, dry_run=dry_run)
            return result

        # ── Create worktree ──────────────────────────────────────────────────
        branch = f"metabolism/revert-{proposal_id}"[:72]  # git branch name limit
        wt_result = _create_revert_worktree(branch, root) if not dry_run else {
            "wt_path": tempfile.mkdtemp(prefix="metab_revert_dryrun_"),
            "error": None,
        }
        wt_path = wt_result.get("wt_path") or ""
        wt_error = wt_result.get("error")

        if wt_error or not wt_path:
            msg = f"Worktree creation failed for {branch}: {wt_error}"
            log.warning("metabolism_revert: %s", msg)
            result["status"] = "worktree_error"
            result["reason"] = msg
            _emit_insight("revert_plan_conflict", proposal_id, msg, root, dry_run=dry_run)
            return result

        result["wt_path"] = wt_path

        # ── git revert ──────────────────────────────────────────────────────
        try:
            revert_ok = False
            conflict_detail = ""

            if dry_run:
                revert_ok = True
                log.info("metabolism_revert [dry-run] would git revert %s", merge_sha)
            else:
                rv = subprocess.run(
                    ["git", "revert", merge_sha, "--no-edit"],
                    cwd=wt_path, capture_output=True, text=True, timeout=120,
                )
                if rv.returncode == 0:
                    revert_ok = True
                else:
                    conflict_detail = (rv.stderr or rv.stdout or "")[:400]
                    log.warning(
                        "metabolism_revert: git revert conflict for sha=%s: %s",
                        merge_sha, conflict_detail,
                    )
                    # Abort the conflicted revert — NEVER force
                    subprocess.run(
                        ["git", "revert", "--abort"],
                        cwd=wt_path, capture_output=True, timeout=30,
                    )

            if not revert_ok:
                msg = (
                    f"git revert conflicted for sha={merge_sha} (proposal={proposal_id}); "
                    f"aborted. NEVER forced. detail={conflict_detail}"
                )
                result["status"] = "revert_conflict"
                result["conflict_detail"] = conflict_detail
                _emit_insight("revert_plan_conflict", proposal_id, msg, root, dry_run=dry_run)
                # Write actioned marker with conflict status so we don't retry forever
                _write_actioned_marker(
                    proposal_id, "revert_conflict", pr_number=None, root=root,
                    extra={"conflict_detail": conflict_detail, "merge_sha": merge_sha},
                    dry_run=dry_run,
                )
                return result

            # ── Push + open draft PR ─────────────────────────────────────────
            pushed = False
            if not dry_run:
                pushed = _push_revert_branch(branch, wt_path, root)
            else:
                pushed = True
                log.info("metabolism_revert [dry-run] would push branch %s", branch)

            if not pushed:
                msg = f"Branch push failed for {branch} — draft PR not opened"
                log.warning("metabolism_revert: %s", msg)
                result["status"] = "push_failed"
                result["reason"] = msg
                return result

            pr_result = _open_draft_revert_pr(branch, plan_record, root=root, dry_run=dry_run)
            result["pr"] = pr_result

            # FIX-4: write actioned marker ONLY when the PR was actually opened
            # (opened==True).  On gh failure (opened==False), mark with
            # 'revert_pr_open_failed' so the next run retries rather than silently
            # dropping the intent.
            revert_pr_number = pr_result.get("pr_number")
            if pr_result.get("opened"):
                marker = _write_actioned_marker(
                    proposal_id, "revert_pr_opened",
                    pr_number=revert_pr_number,
                    root=root,
                    extra={
                        "merge_sha": merge_sha,
                        "source_pr_number": pr_number,
                        "branch": branch,
                        "pr_url": pr_result.get("pr_url"),
                    },
                    dry_run=dry_run,
                )
                result["actioned_marker"] = marker
                result["status"] = "revert_pr_opened"

                _emit_insight(
                    "revert_plan_actioned",
                    proposal_id,
                    (
                        f"Draft revert PR opened for proposal={proposal_id} "
                        f"sha={merge_sha} (PR #{revert_pr_number})"
                    ),
                    root,
                    dry_run=dry_run,
                )
                log.info(
                    "metabolism_revert: DONE proposal=%s sha=%s revert_pr=%s",
                    proposal_id, merge_sha, revert_pr_number,
                )
            else:
                # gh pr create failed after push — mark with failed status so
                # the next run retries (plan NOT permanently actioned).
                pr_error = pr_result.get("error") or "gh pr create returned opened=False"
                log.warning(
                    "metabolism_revert: gh pr create failed for proposal=%s: %s — "
                    "marking revert_pr_open_failed for retry",
                    proposal_id, pr_error,
                )
                marker = _write_actioned_marker(
                    proposal_id, "revert_pr_open_failed",
                    pr_number=None,
                    root=root,
                    extra={
                        "merge_sha": merge_sha,
                        "source_pr_number": pr_number,
                        "branch": branch,
                        "error": pr_error,
                    },
                    dry_run=dry_run,
                )
                result["actioned_marker"] = marker
                result["status"] = "revert_pr_open_failed"
                _emit_insight(
                    "revert_plan_conflict",
                    proposal_id,
                    (
                        f"gh pr create failed after push for proposal={proposal_id} "
                        f"sha={merge_sha}; marked for retry: {pr_error}"
                    ),
                    root,
                    dry_run=dry_run,
                )

        finally:
            # Always clean up the temp worktree (except dry-run uses a real tmpdir
            # that we also clean up)
            if not dry_run:
                _remove_revert_worktree(branch, wt_path, root)
            elif wt_path and Path(wt_path).exists():
                try:
                    shutil.rmtree(wt_path, ignore_errors=True)
                except Exception:  # noqa: BLE001
                    pass

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_revert._process_one_plan(%s): %s", proposal_id, exc)
        result["status"] = "error"
        result["error"] = str(exc)

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """Entry point.  Exit 0 always.  NEVER raises."""
    parser = argparse.ArgumentParser(
        description="Metabolism revert-plan executor (R-V8-6)",
    )
    parser.add_argument("--root", default=None, help="Repo root path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan and log but do not write worktrees/PRs/markers")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT

    # ── AUTONOMY_PAUSED first-action gate ──────────────────────────────────
    if _is_paused():
        log.info("metabolism_revert: %s — no-op exit 0", _pause_reason())
        return 0

    # ── Scan un-actioned plans ─────────────────────────────────────────────
    plans = _scan_unactioned_revert_plans(root)
    if not plans:
        log.info("metabolism_revert: no un-actioned revert plans found")
        return 0

    log.info("metabolism_revert: found %d un-actioned revert plan(s)", len(plans))

    # ── Bound by max_open_revert_prs (SIMULTANEOUSLY OPEN, not per-run) ─────
    # FIX-3: query gh pr list for already-open revert PRs so the cap applies
    # to the global count of open PRs, not just PRs opened in this run.
    # FIX-B4: _count_open_revert_prs returns _COUNT_OPEN_PRS_ERROR (-1) on
    # any gh failure; fail closed → open ZERO new PRs this run (defer).
    max_prs = _load_max_open_revert_prs(root)
    already_open = _count_open_revert_prs(root)
    if already_open == _COUNT_OPEN_PRS_ERROR:
        log.warning(
            "metabolism_revert: gh pr list failed — failing closed: "
            "deferring all %d plan(s) to next run (cannot verify open PR count)",
            len(plans),
        )
        return 0
    slots_available = max(0, max_prs - already_open)
    to_process = plans[:slots_available]
    skipped = len(plans) - len(to_process)
    if already_open:
        log.info(
            "metabolism_revert: %d revert PR(s) already open; "
            "max=%d → %d slot(s) available",
            already_open, max_prs, slots_available,
        )
    if skipped:
        log.info(
            "metabolism_revert: %d plan(s) deferred (max_open_revert_prs=%d, "
            "already_open=%d)",
            skipped, max_prs, already_open,
        )

    # ── Process each plan ─────────────────────────────────────────────────
    for plan_record in to_process:
        proposal_id = plan_record.get("proposal_id") or "?"
        log.info("metabolism_revert: processing proposal=%s", proposal_id)
        _process_one_plan(plan_record, root, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
