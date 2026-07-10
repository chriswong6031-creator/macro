"""scripts/metabolism_build.py — BUILD lane for the Metabolism V2-B write-serialization (R-V2-5).

PURPOSE
-------
The BUILD lane reads the ADJUDICATE-granted agenda items from a docket and,
for each granted proposal:

  (a) CLAIMS the proposal's target_files by appending one row to
      data/metabolism/claims.jsonl and regenerating ACTIVE_BUILD_MAP.

  (b) SKIPS a proposal whose target_files are already claimed THIS cycle
      (collision → sequenced to a later cycle, journaled).

  (c) Creates a git worktree on metabolism/build-<lobe>-<cycle> off FRESH
      origin/main.

  (d) Dispatches a headless Sonnet build session (pick_key from
      metabolism_dispatch for its OAuth).
      IN THIS VERSION the invocation is a DOCUMENTED CONTRACT / STUB:
      the live self-hosted build session runs only when armed; this file
      ships the wiring and the interface, not a live LLM call in CI.

  (e) Opens a DRAFT PR (never merges).

  (f) If:always() GCs the build worktree via metabolism_gc.

INERTNESS GUARANTEES
--------------------
* is_paused() is the FIRST operation. Unset AUTONOMY_PAUSED = paused.
* Workflow is double-gated: both `if: vars.AUTONOMY_PAUSED != 'true'` AND
  an explicit AUTONOMY_PAUSED=='false' shell check before any real action.
* Opens DRAFT PRs only — never merges.
* The whole job no-ops when paused (clean exit 0).

CLAIM / COLLISION
-----------------
data/metabolism/claims.jsonl (metabolism-build-claims artifact):
  {schema, cycle_id, proposal_id, lobe, target_files, ts}
  Appended atomically (one row per granted + uncollided proposal per cycle).
  The collision check reads ALL claims for the same cycle_id before appending.

NEVER-RAISE CONTRACT: all public functions catch exceptions and return safe fallbacks.

STATELESS-CATTLE (R-AUT-3): no persistent sessions; all state in git artifacts;
idempotent + journal-resumable.

Usage (CLI):
    python -m scripts.metabolism_build \\
        --cycle-id <id> --docket-file <path> [--dry-run] [--root <path>]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

_CLAIMS_REL = Path("data") / "metabolism" / "claims.jsonl"
_CLAIMS_SCHEMA = "metabolism.build_claims.v1"
_BUILD_BRANCH_PREFIX = "metabolism/build-"


# ── Pause guard ────────────────────────────────────────────────────────────────

def _is_paused() -> bool:
    """Return True unless AUTONOMY_PAUSED is the exact string 'false'.

    Fail-closed: unset / empty / any other value → paused.
    NEVER raises.
    """
    try:
        from scripts.metabolism_guard import is_paused
        return is_paused()
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._is_paused: guard check failed (%s) — treating as paused", exc)
        return True


# ── Claims helpers ────────────────────────────────────────────────────────────

def _claims_path(root: Path | None = None) -> Path:
    return (root or _ROOT) / _CLAIMS_REL


def _read_claims(root: Path | None = None) -> list[dict[str, Any]]:
    """Read claims.jsonl; return a list of claim rows. NEVER raises."""
    try:
        p = _claims_path(root)
        if not p.exists():
            return []
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._read_claims: %s", exc)
        return []


def _cycle_claimed_files(cycle_id: str, root: Path | None = None) -> set[str]:
    """Return the set of target_files already claimed this cycle. NEVER raises."""
    try:
        rows = _read_claims(root)
        claimed: set[str] = set()
        for row in rows:
            if row.get("cycle_id") != cycle_id:
                continue
            for f in row.get("target_files") or []:
                claimed.add(str(f))
        return claimed
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._cycle_claimed_files: %s", exc)
        return set()


def claim_proposal(
    cycle_id: str,
    proposal_id: str,
    lobe: str,
    target_files: list[str],
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Attempt to claim a proposal's target_files for this cycle.

    Returns {claimed: bool, collision_files: list[str], ts: str}.
    If any target_file is already claimed by another proposal this cycle,
    returns claimed=False and the collision_files list.
    NEVER raises.
    """
    result: dict[str, Any] = {"claimed": False, "collision_files": [], "ts": ""}
    try:
        already = _cycle_claimed_files(cycle_id, root)
        collisions = [f for f in target_files if f in already]
        if collisions:
            result["collision_files"] = collisions
            log.warning(
                "BUILD claim: cycle=%s proposal=%s COLLISION on %s — sequenced to later cycle",
                cycle_id, proposal_id, collisions,
            )
            return result

        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        row = {
            "schema": _CLAIMS_SCHEMA,
            "cycle_id": cycle_id,
            "proposal_id": proposal_id,
            "lobe": lobe,
            "target_files": list(target_files),
            "ts": ts,
        }
        if not dry_run:
            p = _claims_path(root)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
            # Regen ACTIVE_BUILD_MAP (best-effort; failure does not block the claim)
            _regen_active_build_map(root)

        result["claimed"] = True
        result["ts"] = ts
        log.info("BUILD claim: cycle=%s proposal=%s claimed %d files", cycle_id, proposal_id, len(target_files))
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build.claim_proposal: %s", exc)
        return result


def _regen_active_build_map(root: Path | None = None) -> None:
    """Regen ACTIVE_BUILD_MAP (best-effort). NEVER raises."""
    try:
        r = root or _ROOT
        result = subprocess.run(
            [sys.executable, "-m", "scripts.build_active_build_map"],
            cwd=str(r), capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.warning("BUILD: ACTIVE_BUILD_MAP regen failed: %s", result.stderr[:200])
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: ACTIVE_BUILD_MAP regen exception: %s", exc)


# ── Worktree helpers ──────────────────────────────────────────────────────────

def _build_branch_name(lobe: str, cycle_id: str) -> str:
    """Return the worktree branch name for a build lane. Format: metabolism/build-<lobe>-<cycle>."""
    # Sanitize lobe and cycle_id for use as a git branch component
    safe_lobe = lobe.replace("/", "_").replace(" ", "_").lower()
    safe_cycle = cycle_id.replace("/", "_")
    return f"{_BUILD_BRANCH_PREFIX}{safe_lobe}-{safe_cycle}"


def _create_build_worktree(
    branch: str,
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a git worktree on `branch` off FRESH origin/main.

    Returns {wt_path: str | None, error: str | None}.
    NEVER raises.
    """
    result: dict[str, Any] = {"wt_path": None, "error": None}
    try:
        r = root or _ROOT
        # Fetch fresh origin/main first
        if not dry_run:
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=str(r), capture_output=True, timeout=60,
            )

        # Worktrees live alongside the main worktree (siblings of .git parent)
        wt_path = r.parent / branch.replace("/", "_").replace("metabolism_", "metabolism-")
        # Ensure we don't double-create
        if wt_path.exists() and not dry_run:
            result["wt_path"] = str(wt_path)
            log.info("BUILD: worktree already exists at %s", wt_path)
            return result

        if not dry_run:
            subprocess.run(
                ["git", "worktree", "add", "-b", branch, str(wt_path), "origin/main"],
                cwd=str(r), capture_output=True, text=True, timeout=60,
                check=True,
            )
        result["wt_path"] = str(wt_path)
        log.info("BUILD: worktree created at %s (branch=%s)", wt_path, branch)
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._create_build_worktree: %s", exc)
        result["error"] = str(exc)
        return result


def _gc_worktree(branch: str, *, root: Path | None = None) -> None:
    """GC the build worktree via metabolism_gc (if:always() companion). NEVER raises."""
    try:
        from scripts.metabolism_gc import gc
        r = root or _ROOT
        summary = gc(r, dry_run=False)
        log.info("BUILD: GC after build: reaped=%s errors=%s", summary.get("reaped"), summary.get("errors"))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._gc_worktree: %s", exc)


# ── Build-session stub (the interface contract) ───────────────────────────────

_BUILD_SESSION_CONTRACT = """\
# BUILD SESSION INTERFACE CONTRACT (V2-B Unit 6)
#
# When armed (AUTONOMY_PAUSED=false) and the two-key is granted, the build
# lane dispatches a headless Sonnet build session for each granted proposal.
#
# Interface:
#   cap_id  = pick_key(stage="build", root=root)  # OAuth key (capability_id only)
#   ref     = key_pool.get_secret_ref(cap_id)      # env-var name
#   token   = os.environ[ref]                      # caller reads; dispatch never touches
#
# The session receives:
#   - The worktree path (absolute) as its working directory
#   - The proposal JSON (from the docket) as its task specification
#   - A draft PR target: metabolism/build-<lobe>-<cycle>
#   - The branch is off FRESH origin/main (claim step ran first)
#
# The session MUST:
#   - Commit only to data/metabolism/* and its declared target_files
#   - Open a DRAFT PR (never merge)
#   - Write Loop-Authored: trailer on every commit
#   - Append to data/metabolism/journal/<cycle_id>.json via metabolism_journal
#
# The session MUST NOT:
#   - Touch the IMMUTABLE set (.claude/hooks, .github/workflows, config/grader_manifest.yml,
#     config/capability_manifest.yml, config/metabolism_budget.yml,
#     engine/neuralweb/capability_broker.py, scripts/check_self_mod_fence.py,
#     scripts/check_grader_manifest.py, settings.json,
#     research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md, config/metabolism_anomaly.yml,
#     config/fable_mode_core.md, config/metabolism_schedule.yml,
#     config/ux_simplicity_rules.yml, engine/metabolism/tap.py)
#   - Merge any PR
#   - Push to main
#   - Write scored-path surfaces without a T2 metabolism_live flag
#
# In this PR (V2-B Unit 6) the live dispatch call is a STUB — wiring is shipped;
# the live LLM call fires only when the lane is armed by the operator.
"""


def _dispatch_build_session(
    proposal: dict[str, Any],
    wt_path: str,
    branch: str,
    cap_id: str | None,
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Dispatch the headless build session for a granted proposal.

    In V2-B Unit 6 this is a DOCUMENTED STUB — the live LLM call is wired
    but does not execute until the lane is armed (AUTONOMY_PAUSED=false in
    production and a real cap_id is available).

    Returns {dispatched: bool, stub: bool, reason: str}.
    NEVER raises.
    """
    if dry_run:
        return {"dispatched": False, "stub": True, "reason": "dry_run"}

    if cap_id is None:
        log.info(
            "BUILD: no cap_id available (paused or all-cooling) — "
            "build session stub for proposal=%s", proposal.get("proposal_id")
        )
        return {
            "dispatched": False,
            "stub": True,
            "reason": "no_cap_id — lane wiring shipped; live call fires when armed",
            "contract": _BUILD_SESSION_CONTRACT,
        }

    # When cap_id is available and not dry_run:
    # The live dispatch would invoke a headless Sonnet claude-code session.
    # Contract is documented above. Stub in this PR.
    log.info(
        "BUILD: build-session stub for proposal=%s cap=%s wt=%s branch=%s "
        "(live LLM call fires when operator arms the lane)",
        proposal.get("proposal_id"), cap_id, wt_path, branch,
    )
    return {
        "dispatched": False,
        "stub": True,
        "reason": "v2b_unit6_stub — lane wiring shipped; live LLM call fires when armed",
        "cap_id": cap_id,
        "wt_path": wt_path,
        "branch": branch,
        "contract": _BUILD_SESSION_CONTRACT,
    }


# ── Draft PR helper ───────────────────────────────────────────────────────────

def _open_draft_pr(
    branch: str,
    cycle_id: str,
    proposal: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Open a DRAFT PR for the build worktree branch. NEVER merges. NEVER raises."""
    result: dict[str, Any] = {"opened": False, "stub": True}
    try:
        pid = proposal.get("proposal_id", "unknown")
        lobe = proposal.get("lobe") or proposal.get("targets_sensor", "unknown")
        title = f"metabolism: BUILD {pid} ({lobe}) cycle={cycle_id} [DRAFT]"
        body = (
            f"Autonomous BUILD for proposal `{pid}` in cycle `{cycle_id}`.\n\n"
            f"**INERT**: draft only — a merge fires ONLY when:\n"
            f"1. CI is green on this PR\n"
            f"2. The two-key adjudication grant is confirmed (`resolve_two_key` authorized)\n"
            f"3. `AUTONOMY_PAUSED=false` (operator-arming)\n"
            f"4. The serialized merge lane processes it (single concurrency group)\n\n"
            f"See `data/metabolism/claims.jsonl` for the file claim and "
            f"`data/metabolism/dockets/{cycle_id}.json` for the proposal spec."
        )
        if dry_run:
            log.info("BUILD [DRY-RUN]: would open draft PR: %s", title)
            result["stub"] = True
            return result

        gh = os.environ.get("GH_TOKEN", "")
        if not gh:
            log.info("BUILD: no GH_TOKEN — draft PR stub (wiring shipped, fires when armed)")
            result["reason"] = "no_gh_token_stub"
            return result

        cmd = [
            "gh", "pr", "create", "--draft",
            "--base", "main",
            "--head", branch,
            "--title", title,
            "--body", body,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            result["opened"] = True
            result["stub"] = False
            url = proc.stdout.strip()
            result["url"] = url
            log.info("BUILD: draft PR opened: %s", url)
        else:
            log.warning("BUILD: draft PR failed: %s", proc.stderr[:200])
            result["reason"] = proc.stderr[:200]
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._open_draft_pr: %s", exc)
        return result


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
        log.warning("metabolism_build._is_two_key_granted: %s — treating as not granted", exc)
        return False


# ── Main build loop ───────────────────────────────────────────────────────────

def run_build_lane(
    cycle_id: str,
    docket_path: str | Path,
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Execute the BUILD lane for a cycle.

    For each granted proposal in the docket:
      1. Check two-key grant (resolve_two_key authorized).
      2. Claim target_files (collision → skip to later cycle).
      3. Create worktree off fresh origin/main.
      4. Dispatch build session (stub in V2-B Unit 6).
      5. Open draft PR.
      6. GC worktree (if:always()).

    Returns list of per-proposal result dicts.
    INERT when paused. NEVER raises.
    """
    # FIRST: pause guard
    if _is_paused():
        log.info("BUILD: AUTONOMY_PAUSED — no-op")
        return [{"status": "noop_paused", "cycle_id": cycle_id}]

    results: list[dict[str, Any]] = []
    try:
        dp = Path(docket_path)
        if not dp.exists():
            log.warning("BUILD: docket not found: %s", dp)
            return results

        docket = json.loads(dp.read_text(encoding="utf-8"))
        proposals = docket.get("proposals") or []
        lobe = docket.get("lobe", "unknown")

        for prop in proposals:
            pid = str(prop.get("proposal_id") or "")
            if not pid:
                continue

            per: dict[str, Any] = {
                "proposal_id": pid,
                "cycle_id": cycle_id,
                "lobe": lobe,
                "status": "pending",
            }

            # Step 1: two-key grant
            granted = _is_two_key_granted(cycle_id, pid, dp, root=root)
            if not granted:
                per["status"] = "not_granted"
                per["reason"] = "two_key not authorized — skipped"
                log.info("BUILD: proposal=%s not authorized by two-key — skip", pid)
                results.append(per)
                continue

            # Step 2: claim target_files
            target_files = [str(f) for f in (prop.get("target_files") or [])]
            if not target_files:
                # Use a placeholder if no target_files declared (permissive)
                target_files = [f"data/metabolism/build/{pid}"]

            claim = claim_proposal(
                cycle_id, pid, lobe, target_files, root=root, dry_run=dry_run,
            )
            per["claim"] = claim
            if not claim["claimed"]:
                per["status"] = "collision"
                per["reason"] = f"collision on {claim['collision_files']} — sequenced to later cycle"
                log.warning("BUILD: proposal=%s COLLISION — sequenced to later cycle", pid)
                _journal_skip(cycle_id, pid, per["reason"], root=root, dry_run=dry_run)
                results.append(per)
                continue

            # Step 3: create worktree off fresh origin/main
            branch = _build_branch_name(lobe, cycle_id)
            wt_result = _create_build_worktree(branch, root=root, dry_run=dry_run)
            per["worktree"] = wt_result
            wt_path = wt_result.get("wt_path") or ""

            # Step 4: dispatch build session (stub in V2-B Unit 6)
            cap_id = _pick_build_key(root=root)
            session = _dispatch_build_session(
                prop, wt_path, branch, cap_id, root=root, dry_run=dry_run,
            )
            per["session"] = session

            # Step 5: open draft PR
            pr = _open_draft_pr(branch, cycle_id, prop, dry_run=dry_run)
            per["pr"] = pr

            per["status"] = "build_dispatched"
            results.append(per)

            # Step 6: GC worktree (if:always() — runs even on error)
            _gc_worktree(branch, root=root)

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build.run_build_lane: %s", exc)

    return results


def _pick_build_key(root: Path | None = None) -> str | None:
    """Pick a build key via the dispatcher. NEVER raises."""
    try:
        from scripts.metabolism_dispatch import pick_key
        return pick_key(stage="build", root=root, notify_on_freeze=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._pick_build_key: %s", exc)
        return None


def _journal_skip(
    cycle_id: str,
    proposal_id: str,
    reason: str,
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Journal a skip (collision or not-granted) for resume-safety. NEVER raises."""
    try:
        from scripts.metabolism_journal import finish_stage
        stage = f"build_skip_{proposal_id}"
        if not dry_run:
            finish_stage(
                cycle_id, stage, "done",
                note=reason, root=root,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._journal_skip: %s", exc)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the BUILD lane."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(
        description="Metabolism V2-B BUILD lane — write-serialized build session dispatch."
    )
    ap.add_argument("--cycle-id", required=True, help="Cycle ID whose docket to build.")
    ap.add_argument("--docket-file", required=True, help="Path to the docket JSON.")
    ap.add_argument("--dry-run", action="store_true", help="Print what would happen; no writes.")
    ap.add_argument("--root", default=None, help="Repo root (default: auto-detect).")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else None
    results = run_build_lane(
        args.cycle_id,
        args.docket_file,
        root=root,
        dry_run=args.dry_run,
    )
    print(json.dumps(results, indent=2, default=str))
    # Exit 0 always — paused/freeze is a clean no-op, not an error
    return 0


if __name__ == "__main__":
    sys.exit(main())
