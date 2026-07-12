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

# Path to claims.jsonl relative to repo root (same as metabolism_build._CLAIMS_REL)
_CLAIMS_REL = ("data", "metabolism", "claims.jsonl")

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
    Fail-closed: if the changed-files list is empty (could not enumerate),
    the fence REFUSES.  An empty file list means we cannot verify safety.
    NEVER raises.
    """
    try:
        if not pr_files:
            # Cannot enumerate changed files — fail-closed (R-AUT-5).
            # Contrast: ci.yml lines 912-919 exit 1 on empty file list for the same reason.
            msg = "fence fail-closed: could not enumerate PR changed files (empty list)"
            log.warning("metabolism_merge._fence_check_pr: %s", msg)
            return False, msg
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
    expect_sha: str = "",
    root: Path | None = None,
    dry_run: bool = False,
    retries: int = _MAX_REBASE_RETRIES,
) -> dict[str, Any]:
    """Merge a PR via rebase --autostash with retry (registry-race-safe pattern).

    expect_sha : when non-empty, the audited/approved head commit. After the
      fetch, origin/<pr_branch> MUST equal it or the merge aborts — this pins
      the merge to exactly the code the auditor approved (#2377 review B3, the
      SHA-binding TOCTOU). An empty expect_sha keeps the legacy behavior for
      non-audited callers/tests.

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
                # Fetch main and the PR branch fresh
                subprocess.run(
                    ["git", "fetch", "origin", "main", pr_branch],
                    cwd=str(r), capture_output=True, timeout=60,
                )
                # SHA PIN (#2377 B3): the branch tip must still be the audited
                # commit. If it moved between the audit gate and now, an
                # unaudited commit is at the tip — abort, never merge it.
                if expect_sha:
                    tip = subprocess.run(
                        ["git", "rev-parse", f"origin/{pr_branch}"],
                        cwd=str(r), capture_output=True, text=True, timeout=30,
                    )
                    live_sha = (tip.stdout or "").strip()
                    if tip.returncode != 0 or live_sha != expect_sha:
                        result["error"] = (
                            f"sha_pin_mismatch: origin/{pr_branch}={live_sha[:12]} "
                            f"!= audited {expect_sha[:12]} — aborting merge (B3)"
                        )
                        log.warning("MERGE: %s", result["error"])
                        return result  # fail-closed: do not merge unaudited code
                # Reset to a clean origin/main tip before applying the PR.
                # Without this, git pull --rebase would rebase onto whatever branch
                # happens to be checked out in this worktree (the docket branch),
                # and HEAD:main would push that history rather than main + PR commits.
                subprocess.run(
                    ["git", "checkout", "main"],
                    cwd=str(r), capture_output=True, timeout=30,
                )
                reset = subprocess.run(
                    ["git", "reset", "--hard", "origin/main"],
                    cwd=str(r), capture_output=True, text=True, timeout=30,
                )
                if reset.returncode != 0:
                    log.warning("MERGE: reset failed (attempt %d): %s", attempt, reset.stderr[:200])
                    continue
                # Merge the PR branch into the now-clean local main
                rebase = subprocess.run(
                    ["git", "pull", "--rebase", "--autostash", "origin", pr_branch],
                    cwd=str(r), capture_output=True, text=True, timeout=120,
                )
                if rebase.returncode == 0:
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
                    log.warning("MERGE: rebase failed (attempt %d): %s", attempt, rebase.stderr[:200])
            except Exception as exc:  # noqa: BLE001
                log.warning("MERGE: attempt %d exception: %s", attempt, exc)

        result["error"] = f"merge failed after {retries} attempts"
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._rebase_merge_pr: %s", exc)
        result["error"] = str(exc)
        return result


# ── Proposal-ID resolution (the BLOCKING fix) ─────────────────────────────────

def _resolve_proposal_id_for_branch(
    pr_branch: str,
    cycle_id: str,
    docket: dict[str, Any],
    docket_path: Path,
    *,
    root: Path | None = None,
) -> str | None:
    """Return the proposal_id whose build branch exactly matches pr_branch, or None.

    SECURITY INVARIANT: only an exact branch match is accepted.  A namespace-prefix
    test (startswith "metabolism/build-") is NEVER used — that would let any build PR
    inherit any proposal's two-key grant, defeating write-serialization (R-V2-5).

    Resolution order:
      1. claims.jsonl (authoritative — written atomically by the build lane):
         find a row with cycle_id == cycle_id and lobe such that
         _build_branch_name(row["lobe"], cycle_id) == pr_branch, and whose
         proposal_id exists in the docket's prop_index.
      2. Docket-level lobe (same source the build lane uses): compute
         _build_branch_name(docket["lobe"], cycle_id) and require exact equality.
         If matched, return the first uncollided proposal_id from the docket
         (the build lane skips collided proposals in order, so first-in-docket
         is the one that would have been built).

    If neither step produces an exact match, returns None.
    NEVER raises.
    """
    try:
        from scripts.metabolism_build import _build_branch_name

        prop_index = {
            str(p.get("proposal_id") or ""): p
            for p in (docket.get("proposals") or [])
            if p.get("proposal_id")
        }

        # Step 1: claims.jsonl — authoritative proposal→branch mapping
        r = root or _ROOT
        claims_path = r.joinpath(*_CLAIMS_REL)
        if claims_path.exists():
            try:
                for raw in claims_path.read_text(encoding="utf-8").splitlines():
                    raw = raw.strip()
                    if not raw:
                        continue
                    row = json.loads(raw)
                    if row.get("cycle_id") != cycle_id:
                        continue
                    row_lobe = row.get("lobe") or ""
                    if not row_lobe:
                        continue
                    expected = _build_branch_name(row_lobe, cycle_id)
                    if expected == pr_branch:
                        pid = str(row.get("proposal_id") or "")
                        if pid and pid in prop_index:
                            log.info(
                                "MERGE: branch %s → proposal %s (via claims.jsonl)", pr_branch, pid
                            )
                            return pid
            except Exception as exc:  # noqa: BLE001
                log.warning("MERGE: _resolve_proposal_id_for_branch claims read error: %s", exc)
                # Fall through to docket-level fallback

        # Step 2: docket-level lobe — same source the build lane uses
        docket_lobe = docket.get("lobe") or ""
        if docket_lobe:
            expected = _build_branch_name(docket_lobe, cycle_id)
            if expected == pr_branch:
                # Return the proposal_id of the first proposal in the docket that
                # is present in prop_index (the build lane processes in order).
                for prop in (docket.get("proposals") or []):
                    pid = str(prop.get("proposal_id") or "")
                    if pid and pid in prop_index:
                        log.info(
                            "MERGE: branch %s → proposal %s (via docket lobe fallback)", pr_branch, pid
                        )
                        return pid

        log.info(
            "MERGE: no exact match for branch %s in cycle %s (claims or docket)", pr_branch, cycle_id
        )
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._resolve_proposal_id_for_branch: %s", exc)
        return None


# ── Audit gate (R-V7-3) ──────────────────────────────────────────────────────

def _audit_approved(pr_number: int, head_sha: str, root: Path | None = None) -> tuple[bool, str]:
    """Return (approved, reason) for the V7 audit gate (step 5.5).

    Reads data/metabolism/audit/<pr_number>.json and requires:
      - verdict == "approve"
      - record["head_sha"] == head_sha (post-audit push invalidates the record)

    Fail-closed: missing record / reject / SHA mismatch → (False, reason).
    NEVER raises.
    """
    try:
        r = root or _ROOT
        audit_path = r / "data" / "metabolism" / "audit" / f"{pr_number}.json"
        if not audit_path.exists():
            return False, f"no audit record found for PR #{pr_number}"

        record = json.loads(audit_path.read_text(encoding="utf-8"))

        stored_sha = record.get("head_sha") or ""
        if stored_sha != head_sha:
            return False, (
                f"audit record SHA mismatch for PR #{pr_number}: "
                f"recorded={stored_sha[:8]!r} current={head_sha[:8]!r} — "
                "re-audit required (post-audit push detected)"
            )

        verdict = str(record.get("verdict") or "reject").lower()
        if verdict != "approve":
            rationale = str(record.get("rationale") or "")[:200]
            return False, f"audit verdict={verdict!r} for PR #{pr_number}: {rationale}"

        return True, f"audit approved PR #{pr_number} at sha={head_sha[:8]}"

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_merge._audit_approved: %s — refusing (fail-closed)", exc)
        return False, f"audit gate error (fail-closed): {exc}"


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
      5.5. Verify AUDIT-APPROVE record exists and matches current head SHA (R-V7-3).
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

            # --- BLOCKING FIX: exact proposal matching only; never namespace-prefix ---
            # The build lane names branches from the DOCKET-level `lobe` (not per-proposal).
            # The merge lane must resolve proposal_id the same way — an exact branch match
            # against the branch the build lane would have created for THIS docket.
            #
            # Two-step resolution (both require EXACT match — no startswith fallback):
            #   1. PRIMARY: consult claims.jsonl. The build lane writes one row per
            #      claimed proposal, containing {cycle_id, proposal_id, lobe}.
            #      We compute the branch from the claims row's lobe and require it to
            #      exactly equal pr_branch.  This is the authoritative mapping: the row
            #      was written atomically by the build lane that opened the PR.
            #   2. FALLBACK: if claims.jsonl is absent or has no row for this cycle/branch,
            #      derive the expected branch from the DOCKET-level lobe (the same source
            #      the build lane uses at line 475/517) and require an exact match.
            #      This handles the in-flight window before claims.jsonl is committed.
            #
            # If neither produces an exact match, skip with no_matching_proposal.
            # Under NO circumstances does a namespace-prefix test (startswith) gate a merge.
            proposal_id = _resolve_proposal_id_for_branch(
                pr_branch, cycle_id, docket, dp, root=root
            )

            if proposal_id is None:
                per["status"] = "no_matching_proposal"
                per["reason"] = (
                    f"could not exactly match PR branch {pr_branch!r} to a docket proposal — "
                    "skipping (never merge under a mis-matched grant)"
                )
                log.warning("MERGE: PR #%s %s", pr_number, per["reason"])
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

            # Step 5.5: AUDIT-APPROVE gate (R-V7-3) — require a fresh, SHA-matched
            # audit record from the V7 adversarial code review stage.
            # Fail-closed: missing record / reject / SHA mismatch → skip, never merge.
            if pr_number:
                pr_head_result = subprocess.run(
                    ["gh", "pr", "view", str(pr_number), "--json", "headRefOid"],
                    capture_output=True, text=True, timeout=30,
                )
                pr_head_sha = ""
                if pr_head_result.returncode == 0:
                    try:
                        pr_head_sha = json.loads(pr_head_result.stdout or "{}").get("headRefOid") or ""
                    except Exception:  # noqa: BLE001
                        pass
            else:
                pr_head_sha = ""

            audit_ok, audit_msg = _audit_approved(
                pr_number, pr_head_sha, root=root
            ) if pr_number else (False, "no pr_number for audit check")
            if not audit_ok:
                per["status"] = "audit_not_approved"
                per["reason"] = audit_msg
                log.info("MERGE: PR #%s audit gate not satisfied — skip: %s",
                         pr_number, audit_msg[:200])
                results.append(per)
                continue

            # Step 6: mark ready + rebase-merge — PINNED to the audited SHA
            # (R-V7-3 / #2377 review B3): the merge must ship exactly the commit
            # the auditor approved (and step-4 CI went green on). expect_sha makes
            # _rebase_merge_pr abort if origin/<branch> moved since the audit,
            # closing the TOCTOU between the step-5.5 SHA check and the merge.
            if pr_number:
                _mark_pr_ready(pr_number, dry_run=dry_run)

            merge_result = _rebase_merge_pr(
                pr_branch, expect_sha=pr_head_sha, root=root, dry_run=dry_run)
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
