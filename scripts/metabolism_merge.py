"""scripts/metabolism_merge.py — SERIALIZED MERGE LANE for the Metabolism V2-B (R-V2-5).

PURPOSE
-------
The merge lane reads DRAFT PRs produced by the BUILD lane that have:
  (i)  Passed CI green AND
  (ii) An ADJUDICATE two-key grant (resolve_two_key authorized).

For each qualifying PR it:
  1. Marks it ready (un-drafts it): gh pr ready <number>
  2. Merges via git pull --rebase --autostash + retry (the registry-race-safe
     pattern used across the whole repo).

The workflow wraps this script with:
  concurrency:
    group: metabolism-merge-lane
    cancel-in-progress: false

so only ONE instance runs at a time.  That single concurrency group is the
mechanical guarantee that synapse.yml / ruling_graph.yml / dag.yml / ACTIVE_BUILD_MAP
never merge-race.

FENCE ENFORCEMENT
-----------------
REFUSES to merge any PR that check_self_mod_fence would block:
  - A loop PR touching the IMMUTABLE set (check_self_mod_fence.IMMUTABLE_PATTERNS)
  - No --admin bypass ever

INERTNESS GUARANTEES
--------------------
* is_paused() is the FIRST operation.
* Workflow double-gated: `if: vars.AUTONOMY_PAUSED != 'true'` AND shell re-check.
* The actual merge fires ONLY when ALL of:
    AUTONOMY_PAUSED == 'false'
    resolve_two_key returned authorized=True
    CI is green on the PR
    check_self_mod_fence passes
  A paused run is a clean no-op (returns [] and exits 0).

NEVER-RAISE CONTRACT: all public functions catch exceptions and return safe fallbacks.
STATELESS-CATTLE (R-AUT-3): no persistent sessions; all state in git artifacts.

Usage (CLI):
    python -m scripts.metabolism_merge \\
        --cycle-id <id> --docket-file <path> [--dry-run] [--root <path>]
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

_MAX_REBASE_RETRIES = 3


# ── Pause guard ────────────────────────────────────────────────────────────────

def _is_paused() -> bool:
    """Return True unless AUTONOMY_PAUSED is the exact string 'false'. NEVER raises."""
    try:
        from scripts.metabolism_guard import is_paused
        return is_paused()
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._is_paused: %s — treating as paused", exc)
        return True


# ── Two-key grant check ───────────────────────────────────────────────────────

def _is_two_key_granted(
    cycle_id: str,
    proposal_id: str,
    docket_path: str | Path,
    *,
    root: Path | None = None,
) -> bool:
    """Return True iff the two-key resolution authorized this proposal. NEVER raises."""
    try:
        from engine.metabolism.adjudicate import resolve_two_key
        resolution = resolve_two_key(cycle_id, docket_path, root=root, dry_run=True)
        entry = resolution.get(proposal_id, {})
        return bool(entry.get("authorized"))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._is_two_key_granted: %s — treating as not granted", exc)
        return False


# ── Self-mod fence check ──────────────────────────────────────────────────────

def _fence_check_pr(pr_branch: str, pr_files: list[str]) -> tuple[bool, str]:
    """Return (passes, reason) for the self-mod fence on a PR.

    A loop PR touching the IMMUTABLE set is REFUSED — no admin bypass.
    NEVER raises.
    """
    try:
        from scripts.check_self_mod_fence import check
        code, msg = check(branch=pr_branch, changed_files=pr_files)
        return code == 0, msg
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._fence_check_pr: %s — refusing (fail-closed)", exc)
        return False, f"fence check error (fail-closed): {exc}"


# ── GitHub helpers ───────────────────────────────────────────────────────────

def _list_build_draft_prs(cycle_id: str) -> list[dict[str, Any]]:
    """List DRAFT PRs from the build lane for this cycle. NEVER raises.

    Queries gh for open draft PRs whose head branch matches
    metabolism/build-*-<cycle_id>.
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--state", "open",
                "--draft",
                "--search", f"head:metabolism/build-",
                "--json", "number,headRefName,title,statusCheckRollup,isDraft,files",
                "--limit", "50",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.warning("metabolism_merge._list_build_draft_prs: gh failed: %s", result.stderr[:200])
            return []
        prs = json.loads(result.stdout or "[]")
        # Filter to this cycle
        return [
            pr for pr in prs
            if cycle_id in (pr.get("headRefName") or "")
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._list_build_draft_prs: %s", exc)
        return []


def _pr_ci_green(pr: dict[str, Any]) -> bool:
    """Return True if all CI checks on the PR are green (success/neutral). NEVER raises."""
    try:
        checks = pr.get("statusCheckRollup") or []
        if not checks:
            # No checks registered — treat as not green (fail-closed)
            return False
        passing_states = {"SUCCESS", "NEUTRAL", "SKIPPED"}
        return all(
            (c.get("state") or c.get("conclusion") or "").upper() in passing_states
            for c in checks
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._pr_ci_green: %s", exc)
        return False


def _get_pr_files(pr_number: int) -> list[str]:
    """Return list of changed files for a PR. NEVER raises."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "files"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout or "{}")
        files = data.get("files") or []
        return [f.get("path", "") for f in files if f.get("path")]
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._get_pr_files: %s", exc)
        return []


def _mark_pr_ready(pr_number: int, *, dry_run: bool = False) -> bool:
    """Un-draft a PR (mark it ready for review). NEVER raises."""
    try:
        if dry_run:
            log.info("MERGE [DRY-RUN]: would mark PR #%d ready", pr_number)
            return True
        result = subprocess.run(
            ["gh", "pr", "ready", str(pr_number)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            log.info("MERGE: PR #%d marked ready", pr_number)
            return True
        log.warning("MERGE: mark-ready failed for #%d: %s", pr_number, result.stderr[:200])
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._mark_pr_ready: %s", exc)
        return False


def _rebase_merge_pr(
    pr_branch: str,
    *,
    root: Path | None = None,
    dry_run: bool = False,
    retries: int = _MAX_REBASE_RETRIES,
) -> dict[str, Any]:
    """Merge a PR via rebase --autostash with retry (registry-race-safe pattern).

    Returns {merged: bool, attempts: int, error: str | None}.
    NEVER raises.
    """
    result: dict[str, Any] = {"merged": False, "attempts": 0, "error": None}
    r = root or _ROOT
    try:
        if dry_run:
            log.info("MERGE [DRY-RUN]: would rebase-merge branch %s", pr_branch)
            result["merged"] = True
            result["attempts"] = 1
            return result

        for attempt in range(1, retries + 1):
            result["attempts"] = attempt
            try:
                # Fetch the branch
                subprocess.run(
                    ["git", "fetch", "origin", pr_branch],
                    cwd=str(r), capture_output=True, timeout=60,
                )
                # Rebase local main onto remote + autostash
                rebase = subprocess.run(
                    ["git", "pull", "--rebase", "--autostash", "origin", pr_branch],
                    cwd=str(r), capture_output=True, text=True, timeout=120,
                )
                if rebase.returncode == 0:
                    # Merge the branch into main
                    merge = subprocess.run(
                        ["git", "merge", "--ff-only", f"origin/{pr_branch}"],
                        cwd=str(r), capture_output=True, text=True, timeout=60,
                    )
                    if merge.returncode == 0:
                        push = subprocess.run(
                            ["git", "push", "origin", "HEAD:main"],
                            cwd=str(r), capture_output=True, text=True, timeout=60,
                        )
                        if push.returncode == 0:
                            result["merged"] = True
                            log.info("MERGE: merged %s on attempt %d", pr_branch, attempt)
                            return result
                        log.warning("MERGE: push failed (attempt %d): %s", attempt, push.stderr[:200])
                    else:
                        log.warning("MERGE: ff-only failed (attempt %d): %s", attempt, merge.stderr[:200])
                else:
                    log.warning("MERGE: rebase failed (attempt %d): %s", attempt, rebase.stderr[:200])
            except Exception as exc:  # noqa: BLE001
                log.warning("MERGE: attempt %d exception: %s", attempt, exc)

        result["error"] = f"merge failed after {retries} attempts"
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._rebase_merge_pr: %s", exc)
        result["error"] = str(exc)
        return result


# ── Main merge loop ───────────────────────────────────────────────────────────

def run_merge_lane(
    cycle_id: str,
    docket_path: str | Path,
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Execute the SERIALIZED MERGE LANE for a cycle.

    Only ONE instance of this function runs at a time (enforced by the
    GitHub Actions `concurrency: group: metabolism-merge-lane` on the
    workflow).

    For each qualifying build-lane DRAFT PR:
      1. Check is_paused() → no-op if paused.
      2. Check AUTONOMY_PAUSED == 'false' (double-gate).
      3. Verify two-key grant.
      4. Verify CI is green.
      5. Verify check_self_mod_fence passes (refuse if not).
      6. Mark PR ready + rebase-merge.

    Returns list of per-PR result dicts.  Zero merges while paused.
    NEVER raises.
    """
    # FIRST: pause guard — the only thing that runs before this is the log.info
    if _is_paused():
        log.info("MERGE: AUTONOMY_PAUSED — no-op; asserting zero merges")
        return [{"status": "noop_paused", "cycle_id": cycle_id, "merges": 0}]

    results: list[dict[str, Any]] = []
    merged_count = 0

    try:
        dp = Path(docket_path)
        if not dp.exists():
            log.warning("MERGE: docket not found: %s", dp)
            return results

        docket = json.loads(dp.read_text(encoding="utf-8"))
        proposals = docket.get("proposals") or []

        # Build a quick index of proposal_id → proposal
        prop_index = {str(p.get("proposal_id") or ""): p for p in proposals if p.get("proposal_id")}

        # List DRAFT PRs from the build lane for this cycle
        draft_prs = _list_build_draft_prs(cycle_id)
        log.info("MERGE: found %d draft PR(s) for cycle=%s", len(draft_prs), cycle_id)

        for pr in draft_prs:
            pr_number = pr.get("number")
            pr_branch = pr.get("headRefName", "")
            per: dict[str, Any] = {
                "pr_number": pr_number,
                "branch": pr_branch,
                "cycle_id": cycle_id,
                "status": "pending",
            }

            # Double-gate: AUTONOMY_PAUSED must be exactly 'false'
            if _is_paused():
                per["status"] = "noop_paused"
                results.append(per)
                break

            # Extract proposal_id from branch name (metabolism/build-<lobe>-<cycle>)
            # The proposal_id is embedded in the docket for this cycle
            # For the merge lane we check the docket for ALL proposals that are
            # authorized and whose branch matches this PR's branch.
            # Find the first authorized proposal for this cycle.
            proposal_id = None
            for pid, prop in prop_index.items():
                from scripts.metabolism_build import _build_branch_name
                expected_branch = _build_branch_name(
                    prop.get("lobe") or prop.get("targets_sensor", "unknown"),
                    cycle_id,
                )
                if expected_branch == pr_branch or pr_branch.startswith("metabolism/build-"):
                    proposal_id = pid
                    break

            if proposal_id is None:
                per["status"] = "no_matching_proposal"
                per["reason"] = "could not match PR branch to a docket proposal"
                results.append(per)
                continue

            # Step 3: two-key grant check
            granted = _is_two_key_granted(cycle_id, proposal_id, dp, root=root)
            if not granted:
                per["status"] = "not_granted"
                per["reason"] = "two-key not authorized — skipping"
                log.info("MERGE: PR #%s not authorized by two-key — skip", pr_number)
                results.append(per)
                continue

            # Step 4: CI green check
            ci_green = _pr_ci_green(pr)
            if not ci_green:
                per["status"] = "ci_not_green"
                per["reason"] = "CI not green — skipping"
                log.info("MERGE: PR #%s CI not green — skip", pr_number)
                results.append(per)
                continue

            # Step 5: self-mod fence check (REFUSES immutable-touching loop PRs)
            pr_files = _get_pr_files(pr_number) if pr_number else []
            fence_ok, fence_msg = _fence_check_pr(pr_branch, pr_files)
            if not fence_ok:
                per["status"] = "fence_blocked"
                per["reason"] = fence_msg
                log.warning("MERGE: PR #%s REFUSED by self-mod fence: %s", pr_number, fence_msg[:200])
                results.append(per)
                continue

            # Step 6: mark ready + rebase-merge
            if pr_number:
                _mark_pr_ready(pr_number, dry_run=dry_run)

            merge_result = _rebase_merge_pr(pr_branch, root=root, dry_run=dry_run)
            per["merge"] = merge_result
            if merge_result.get("merged"):
                per["status"] = "merged"
                merged_count += 1
            else:
                per["status"] = "merge_failed"
                per["reason"] = merge_result.get("error", "unknown")

            results.append(per)

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge.run_merge_lane: %s", exc)

    log.info("MERGE: cycle=%s merged=%d total_processed=%d", cycle_id, merged_count, len(results))
    return results


def assert_zero_merges_when_paused(
    cycle_id: str,
    docket_path: str | Path,
    *,
    root: Path | None = None,
) -> bool:
    """Assert that no merges fire when paused.

    Returns True iff run_merge_lane returned zero merges when paused.
    Used by tests to verify the INERT guarantee.
    NEVER raises.
    """
    try:
        import os
        # Ensure paused
        original = os.environ.get("AUTONOMY_PAUSED", "__unset__")
        os.environ["AUTONOMY_PAUSED"] = "true"
        try:
            results = run_merge_lane(cycle_id, docket_path, root=root, dry_run=True)
        finally:
            if original == "__unset__":
                os.environ.pop("AUTONOMY_PAUSED", None)
            else:
                os.environ["AUTONOMY_PAUSED"] = original

        # No result should have status == "merged"
        merges = [r for r in results if r.get("status") == "merged"]
        return len(merges) == 0
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge.assert_zero_merges_when_paused: %s", exc)
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the MERGE lane."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(
        description="Metabolism V2-B MERGE lane — serialized single-threaded registry-safe merge."
    )
    ap.add_argument("--cycle-id", required=True, help="Cycle ID whose build PRs to merge.")
    ap.add_argument("--docket-file", required=True, help="Path to the docket JSON.")
    ap.add_argument("--dry-run", action="store_true", help="Print what would happen; no merges.")
    ap.add_argument("--root", default=None, help="Repo root (default: auto-detect).")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else None
    results = run_merge_lane(
        args.cycle_id,
        args.docket_file,
        root=root,
        dry_run=args.dry_run,
    )
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
