"""scripts/metabolism_build.py — BUILD lane for the Metabolism V2-B/V4 write-serialization (R-V2-5, R-V4-2).

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

  (d) Dispatches a headless Sonnet build session via _dispatch_build_session()
      (R-V4-2: real dispatch, Sonnet-pinned, draft-only, IMMUTABLE-fenced).
      The session is armed-gated (AUTONOMY_PAUSED re-checked at dispatch),
      capability-broker-keyed, and runs in its own worktree.

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

DISPATCH SAFETY (R-V4-2)
--------------------------
* IMMUTABLE-set refusal AT DISPATCH: any target_file matching the immutable
  set causes an immediate refusal before any session launch.
* AUTONOMY_PAUSED re-checked immediately before session launch (fail-closed).
* Key via capability broker resolve() → env ref NAME only; dispatcher reads
  os.environ[ref]; key value never logged or persisted.
* Foreign-file abort: after session ends, diff the worktree; any changed file
  outside the proposal's declared target_files → abort, clean up, no PR.
* dry_run=True: journals a would_dispatch record but launches nothing.
* Idempotent: same cycle_id + proposal_id → never double-dispatched.

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

def _build_branch_name(lobe: str, cycle_id: str, proposal_id: str = "") -> str:
    """Return the worktree branch name for a build lane.

    Format: metabolism/build-<lobe>-<cycle>-<proposal_id>

    The proposal_id suffix is REQUIRED when a cycle docket contains more than
    one proposal for the same lobe: without it, the second worktree/branch
    creation fails with "fatal: a branch named '...' already exists".
    """
    # Sanitize lobe and cycle_id for use as a git branch component
    safe_lobe = lobe.replace("/", "_").replace(" ", "_").lower()
    safe_cycle = cycle_id.replace("/", "_")
    if proposal_id:
        safe_pid = str(proposal_id).replace("/", "_").replace(" ", "_")
        return f"{_BUILD_BRANCH_PREFIX}{safe_lobe}-{safe_cycle}-{safe_pid}"
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


# ── Build session — model pin + immutable check ───────────────────────────────

# The build session is always Sonnet-pinned (R-V4-2: never inherits caller model).
_BUILD_SESSION_MODEL = "claude-sonnet-4-6"

# Sonnet alias accepted by the claude CLI (falls back to full model id on older
# CLI versions; the full id is the authoritative pin).
_BUILD_SESSION_MODEL_ALIAS = "sonnet"

# Journal stage key for dispatch records (one per proposal per cycle).
_DISPATCH_STAGE_PREFIX = "build_dispatch_"

# Loop-Authored trailer required on every commit the session makes (R-V4-2).
_LOOP_AUTHORED_TRAILER = "Loop-Authored:"


def _check_immutable_targets(target_files: list[str]) -> list[str]:
    """Return target_files that match the IMMUTABLE set from check_self_mod_fence.

    Defense-in-depth at dispatch time (R-V4-2), ahead of the F2 CI fence.
    NEVER raises.
    """
    try:
        from scripts.check_self_mod_fence import _matches_immutable
        return [f for f in target_files if _matches_immutable(f)]
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _check_immutable_targets: %s — treating as no hits", exc)
        return []


def _diff_worktree_files(wt_path: str, base_ref: str = "origin/main") -> list[str] | None:
    """Return the union of all files touched in the worktree vs base_ref.

    Covers three surfaces:
      1. Committed changes (git diff --name-only <base> HEAD)
      2. Staged but not-yet-committed changes (git diff --name-only --cached)
      3. Untracked files (git status --porcelain — lines starting with '??' or 'M ')

    Returns None on error (caller treats as a failure).  NEVER raises.

    A build session that writes foreign files without committing them would
    escape a committed-only diff; all three surfaces must be unioned to close
    that gap.
    """
    try:
        # Surface 1: committed changes HEAD vs base_ref
        r1 = subprocess.run(
            ["git", "diff", "--name-only", base_ref, "HEAD"],
            cwd=wt_path, capture_output=True, text=True, timeout=60,
        )
        if r1.returncode != 0:
            log.warning(
                "BUILD: _diff_worktree_files(committed): git diff exited %d: %s",
                r1.returncode, r1.stderr[:200],
            )
            return None

        committed: set[str] = {
            l.strip() for l in r1.stdout.splitlines() if l.strip()
        }

        # Surface 2+3: working-tree and untracked via git status --porcelain
        # Format: XY path  (X=index status, Y=worktree status)
        # '??' = untracked; others with a non-space Y have working-tree changes.
        r2 = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=wt_path, capture_output=True, text=True, timeout=60,
        )
        if r2.returncode != 0:
            log.warning(
                "BUILD: _diff_worktree_files(status): git status exited %d: %s",
                r2.returncode, r2.stderr[:200],
            )
            return None

        status_files: set[str] = set()
        for raw_line in r2.stdout.splitlines():
            if len(raw_line) < 4:
                continue
            # Columns 0-1 are status codes; column 3+ is the path
            path_part = raw_line[3:].strip()
            # Handle renames: "old -> new" — take the new (destination) path
            if " -> " in path_part:
                path_part = path_part.split(" -> ", 1)[1]
            if path_part:
                status_files.add(path_part.strip('"'))

        all_files = sorted(committed | status_files)
        log.debug(
            "BUILD: _diff_worktree_files: committed=%d status=%d union=%d",
            len(committed), len(status_files), len(all_files),
        )
        return all_files

    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _diff_worktree_files(%s): %s", wt_path, exc)
        return None


def _resolve_key_ref(cap_id: str, root: Path | None = None) -> tuple[str | None, str | None]:
    """Resolve cap_id → (ref_name, reason).  Returns (None, reason) on any failure.

    Uses capability_broker.resolve() and key_pool.get_secret_ref().
    REDLINE: returns the ref NAME only, never the value.  NEVER raises.
    """
    try:
        from engine.neuralweb.capability_broker import resolve as broker_resolve
        result = broker_resolve(cap_id, lane="metabolism-build", root=root)
        if not result.get("allowed"):
            return None, f"capability_broker denied: {result.get('reason', 'unknown')}"
        ref_name: str | None = result.get("ref_name")
        if not ref_name:
            return None, "capability_broker returned no ref_name"
        return ref_name, None
    except Exception as exc:  # noqa: BLE001
        # Fail-closed on any broker exception: do NOT fall back to key_pool.get_secret_ref()
        # because that path bypasses the broker's lane-allowlist check.
        log.warning("BUILD: _resolve_key_ref(%s): broker exception — fail-closed: %s", cap_id, exc)
        return None, f"capability_broker exception: {exc}"


def _record_key_session(
    cap_id: str,
    cycle_id: str,
    outcome: str = "ok",
    root: Path | None = None,
) -> None:
    """Record a session in the key ledger for quota accounting.  NEVER raises."""
    try:
        from engine.neuralweb.key_pool import record_session
        record_session(cap_id, est_tokens=0, cycle_id=cycle_id,
                       stage="build", outcome=outcome, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _record_key_session(%s): %s", cap_id, exc)


def _journal_dispatch(
    cycle_id: str,
    proposal_id: str,
    record: dict[str, Any],
    *,
    root: Path | None = None,
) -> None:
    """Persist a dispatch record to the cycle journal.  NEVER raises."""
    try:
        from scripts.metabolism_journal import finish_stage
        stage = f"{_DISPATCH_STAGE_PREFIX}{proposal_id}"
        finish_stage(
            cycle_id, stage, "done",
            note=json.dumps(record, separators=(",", ":"), default=str)[:500],
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _journal_dispatch(%s/%s): %s", cycle_id, proposal_id, exc)


def _is_dispatch_done(cycle_id: str, proposal_id: str, root: Path | None = None) -> bool:
    """Return True if this proposal has already been dispatched (or is in-flight) this cycle.

    Idempotency check — prevents double-dispatch on retry.

    Treats BOTH 'done' (completed) AND 'running' (in-flight) as "already dispatched":
    a concurrent invocation that finds 'running' must not launch a second session.
    The pre-launch call to `start_stage` in `_dispatch_build_session` writes the
    'running' record atomically before subprocess launch, so this guard catches
    concurrent runs even before the session finishes.

    NEVER raises.
    """
    try:
        from scripts.metabolism_journal import _read_journal  # type: ignore[attr-defined]
        stage = f"{_DISPATCH_STAGE_PREFIX}{proposal_id}"
        j = _read_journal(cycle_id, root)
        status = j.get("stages", {}).get(stage, {}).get("status")
        # Treat running (in-flight) and done (completed) both as "dispatch already claimed"
        return status in ("running", "done")
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _is_dispatch_done(%s/%s): %s", cycle_id, proposal_id, exc)
        return False


def _build_session_task_prompt(
    proposal: dict[str, Any],
    wt_path: str,
    branch: str,
    cycle_id: str,
) -> str:
    """Build the task prompt injected into the headless build session.

    The prompt is the sole task specification the session receives.
    NEVER raises.
    """
    pid = proposal.get("proposal_id", "unknown")
    title = proposal.get("title", "")
    rationale = proposal.get("rationale", "")
    target_files = proposal.get("target_files") or []
    fitness_contract = proposal.get("fitness_contract") or {}
    tier = proposal.get("tier", "T1")
    targets_sensor = proposal.get("targets_sensor", "")

    target_files_list = "\n".join(f"  - {f}" for f in target_files) or "  (none declared)"

    # Load the canonical IMMUTABLE list from check_self_mod_fence at call time so
    # the prompt always reflects the source-of-truth (avoids a stale hand-copy).
    try:
        from scripts.check_self_mod_fence import IMMUTABLE_PATTERNS as _immutable_patterns
    except Exception:  # noqa: BLE001
        _immutable_patterns = []
    immutable_list = "\n".join(f"    {p}" for p in _immutable_patterns) or "    (see check_self_mod_fence.py)"

    return (
        f"You are a BUILD session for the Macro Dashboard Metabolism loop (R-V4-2).\n\n"
        f"CYCLE:    {cycle_id}\n"
        f"PROPOSAL: {pid}\n"
        f"TITLE:    {title}\n"
        f"TIER:     {tier}\n"
        f"SENSOR:   {targets_sensor}\n\n"
        f"RATIONALE:\n{rationale}\n\n"
        f"TARGET FILES (you may ONLY change these + data/metabolism/*):\n"
        f"{target_files_list}\n\n"
        f"FITNESS CONTRACT:\n{json.dumps(fitness_contract, indent=2)}\n\n"
        f"HARD LAWS:\n"
        f"  - Commit ONLY to data/metabolism/* and the target_files above.\n"
        f"  - Every commit trailer: {_LOOP_AUTHORED_TRAILER} build={pid} cycle={cycle_id}\n"
        f"  - Open a DRAFT PR on branch {branch} — NEVER merge.\n"
        f"  - Do NOT touch the IMMUTABLE set (enforced by F2 CI fence):\n"
        f"{immutable_list}\n"
        f"  - Do NOT push to main. Do NOT merge any PR.\n"
        f"  - No LLM-originated signals/scores/escalations.\n"
        f"  - Working directory: {wt_path}\n"
        f"  - Model is already pinned — do not change it.\n"
    )


def _launch_build_subprocess(
    cmd: list[str],
    env: dict[str, str],
    cwd: str,
    timeout_s: int = 1800,
) -> dict[str, Any]:
    """Thin subprocess wrapper for the claude CLI build session.

    Separated into its own function so tests can monkeypatch it without
    actually launching a real session.

    Parameters
    ----------
    cmd : list[str]
        The full command list (e.g. ['claude', '--model', ..., '-p', prompt]).
    env : dict[str, str]
        The environment dict (includes the OAuth token under the ref name).
    cwd : str
        The working directory (worktree path).
    timeout_s : int
        Subprocess timeout in seconds.

    Returns
    -------
    dict with keys: returncode (int), stdout (str), stderr (str).
    NEVER raises — returns {returncode: -1, stdout: '', stderr: str(exc)} on error.
    """
    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
        }
    except subprocess.TimeoutExpired as exc:
        log.warning("BUILD: session subprocess timed out after %ds: %s", timeout_s, exc)
        return {"returncode": -1, "stdout": "", "stderr": f"timeout after {timeout_s}s"}
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: session subprocess error: %s", exc)
        return {"returncode": -1, "stdout": "", "stderr": str(exc)}


def _dispatch_build_session(
    proposal: dict[str, Any],
    wt_path: str,
    branch: str,
    cap_id: str | None,
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Dispatch the headless Sonnet build session for a granted proposal (R-V4-2).

    Hard requirements enforced:
      1. Model PINNED to Sonnet — never inherits caller model.
      2. Worktree is already off fresh origin/main (caller created it).
      3. IMMUTABLE-set refusal AT DISPATCH (defense-in-depth).
      4. AUTONOMY_PAUSED re-checked immediately before session launch.
      5. Key via capability_broker.resolve() → env ref NAME only; value never logged.
      6. After session ends: foreign-file diff check; abort + no PR on violation.
      7. Draft PR only (the session is instructed; the dispatcher opens the PR).
      8. Journal + idempotency (same cycle_id+proposal_id → no re-dispatch).
      9. dry_run=True → journal a would_dispatch record, launch nothing, no PR.
      10. NEVER raises.

    Returns
    -------
    dict with keys:
        dispatched (bool)
        reason (str)
        dry_run (bool, present when dry_run=True)
        would_dispatch (dict, present when dry_run=True)
        error (str, present on failure/abort)
        foreign_files (list, present on foreign-file abort)
    """
    # NEVER-RAISE: guard against None/non-dict proposal at the top level
    if not isinstance(proposal, dict):
        return {"dispatched": False, "reason": "invalid_proposal: not a dict", "proposal_id": "unknown"}

    pid = str(proposal.get("proposal_id") or "unknown")
    cycle_id = str(proposal.get("cycle_id") or "")
    target_files = [str(f) for f in (proposal.get("target_files") or []) if f is not None]
    result: dict[str, Any] = {"dispatched": False, "proposal_id": pid}

    try:
        # ── Step 0: idempotency guard ─────────────────────────────────────────
        if not dry_run and cycle_id and _is_dispatch_done(cycle_id, pid, root=root):
            log.info("BUILD: already dispatched cycle=%s proposal=%s — idempotent skip", cycle_id, pid)
            result["reason"] = "already_dispatched"
            result["idempotent_skip"] = True
            return result

        # ── Step 1: IMMUTABLE-set refusal at dispatch ─────────────────────────
        immutable_hits = _check_immutable_targets(target_files)
        if immutable_hits:
            reason = f"IMMUTABLE_REFUSAL: target_files contain immutable paths: {immutable_hits}"
            log.warning("BUILD: %s proposal=%s", reason, pid)
            result["reason"] = reason
            result["immutable_hits"] = immutable_hits
            if cycle_id:
                _journal_dispatch(cycle_id, pid, {"status": "immutable_refusal",
                                                   "immutable_hits": immutable_hits}, root=root)
            return result

        # ── Step 2: AUTONOMY_PAUSED re-check immediately before launch ────────
        try:
            from scripts.metabolism_guard import is_paused as _guard_paused
            if _guard_paused():
                result["reason"] = "autonomy_paused_at_dispatch"
                log.info("BUILD: AUTONOMY_PAUSED re-check fired — aborting dispatch for proposal=%s", pid)
                return result
        except Exception as exc:  # noqa: BLE001
            log.warning("BUILD: AUTONOMY_PAUSED re-check failed (%s) — fail-closed", exc)
            result["reason"] = f"autonomy_pause_check_failed: {exc}"
            return result

        # ── Step 3: resolve key ref (name only — never the value) ─────────────
        if cap_id is None:
            result["reason"] = "no_cap_id"
            log.info("BUILD: no cap_id — cannot dispatch proposal=%s", pid)
            return result

        ref_name, ref_err = _resolve_key_ref(cap_id, root=root)
        if ref_name is None:
            result["reason"] = f"key_resolution_failed: {ref_err}"
            log.warning("BUILD: key resolution failed for cap=%s: %s", cap_id, ref_err)
            return result

        # Verify the env var is present (fail-closed; never log/persist its value)
        if not os.environ.get(ref_name, ""):
            result["reason"] = f"key_env_absent: {ref_name} not set in environment"
            log.warning("BUILD: %s", result["reason"])
            return result

        # ── Step 4: dry_run path ──────────────────────────────────────────────
        if dry_run:
            wt_would = str(wt_path) if wt_path else "(not yet created)"
            would = {
                "proposal_id": pid,
                "cycle_id": cycle_id,
                "model": _BUILD_SESSION_MODEL,
                "worktree_path": wt_would,
                "branch": branch,
                "target_files": target_files,
                "key_ref_name": ref_name,   # ref NAME only — no value
                "cap_id": cap_id,
            }
            result["dry_run"] = True
            result["would_dispatch"] = would
            result["reason"] = "dry_run"
            log.info(
                "BUILD [DRY-RUN]: would dispatch proposal=%s model=%s wt=%s branch=%s key_ref=%s",
                pid, _BUILD_SESSION_MODEL, wt_would, branch, ref_name,
            )
            if cycle_id:
                _journal_dispatch(cycle_id, pid, {"status": "would_dispatch",
                                                   "dry_run": True, "plan": would}, root=root)
            return result

        # ── Step 5: build task prompt + command ───────────────────────────────
        task_prompt = _build_session_task_prompt(proposal, wt_path, branch, cycle_id)
        cmd = [
            "claude",
            "--model", _BUILD_SESSION_MODEL,
            "--print",           # non-interactive: print final answer only
            "--dangerously-skip-permissions",  # headless build — no interactive prompts
            "-p", task_prompt,
        ]

        # Build env: pass the token under its ref name; never capture the value here
        session_env = {**os.environ}
        # The token is already in session_env under ref_name from the runner's env.
        # We do NOT read or log it; we pass the full env so the subprocess inherits it.

        log.info(
            "BUILD: dispatching proposal=%s model=%s wt=%s branch=%s key_ref=%s",
            pid, _BUILD_SESSION_MODEL, wt_path, branch, ref_name,
        )

        # Nit fix (Finding 7): validate wt_path is a real directory before
        # recording a key session or launching, so ledger accounting doesn't
        # burn quota for a session that never runs.
        if not wt_path or not Path(wt_path).is_dir():
            result["reason"] = f"invalid_wt_path: {wt_path!r} is not a directory"
            log.warning("BUILD: %s proposal=%s", result["reason"], pid)
            if cycle_id:
                _journal_dispatch(cycle_id, pid, {"status": "invalid_wt_path",
                                                   "wt_path": wt_path}, root=root)
            return result

        # Double-dispatch race fix (Finding 3): write a 'running' status for this
        # dispatch stage BEFORE launching the subprocess.  A concurrent invocation
        # reading the journal now will find 'running' and be blocked by
        # _is_dispatch_done (which treats 'running' == in-flight == done-for-guard).
        if cycle_id:
            try:
                from scripts.metabolism_journal import start_stage as _start_stage
                _start_stage(cycle_id, f"{_DISPATCH_STAGE_PREFIX}{pid}", root=root)
            except Exception as exc:  # noqa: BLE001
                log.warning("BUILD: start_stage pre-launch failed (%s) — continuing", exc)

        # Record session start in the key ledger (quota accounting)
        _record_key_session(cap_id, cycle_id, outcome="ok", root=root)

        # ── Step 6: launch the build session ─────────────────────────────────
        run_result = _launch_build_subprocess(cmd, session_env, wt_path, timeout_s=1800)
        returncode = run_result.get("returncode", -1)
        log.info(
            "BUILD: session ended proposal=%s rc=%d stdout_len=%d",
            pid, returncode, len(run_result.get("stdout", "")),
        )

        if returncode != 0:
            _record_key_session(cap_id, cycle_id, outcome="error", root=root)
            result["reason"] = f"session_nonzero_rc: {returncode}"
            result["returncode"] = returncode
            result["stderr_snippet"] = run_result.get("stderr", "")[:200]
            if cycle_id:
                _journal_dispatch(cycle_id, pid, {"status": "session_error",
                                                   "returncode": returncode}, root=root)
            return result

        # ── Step 7: foreign-file diff check ──────────────────────────────────
        changed_files = _diff_worktree_files(wt_path)
        if changed_files is None:
            # diff failed — fail-closed: cannot verify containment
            result["reason"] = "foreign_file_check_failed: git diff returned None"
            if cycle_id:
                _journal_dispatch(cycle_id, pid, {"status": "diff_error"}, root=root)
            return result

        # Allowed: declared target_files + anything under data/metabolism/
        allowed_targets = set(target_files)
        foreign: list[str] = []
        for f in changed_files:
            norm = f.replace("\\", "/").lstrip("/")
            if norm in allowed_targets:
                continue
            if norm.startswith("data/metabolism/"):
                continue
            foreign.append(f)

        if foreign:
            reason = f"FOREIGN_FILE_ABORT: session changed files outside target_files + data/metabolism/: {foreign}"
            log.warning("BUILD: %s proposal=%s", reason, pid)
            result["reason"] = reason
            result["foreign_files"] = foreign
            # Clean up worktree (best-effort)
            _cleanup_worktree_on_abort(wt_path)
            if cycle_id:
                _journal_dispatch(cycle_id, pid, {"status": "foreign_file_abort",
                                                   "foreign_files": foreign}, root=root)
            return result

        # ── Step 8: success — record and journal ──────────────────────────────
        result["dispatched"] = True
        result["reason"] = "dispatched"
        result["model"] = _BUILD_SESSION_MODEL
        result["changed_files"] = changed_files
        if cycle_id:
            _journal_dispatch(cycle_id, pid, {"status": "dispatched",
                                               "model": _BUILD_SESSION_MODEL,
                                               "changed_files": changed_files}, root=root)
        log.info("BUILD: dispatch complete proposal=%s %d files changed", pid, len(changed_files))
        return result

    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _dispatch_build_session(%s): %s", pid, exc)
        result["reason"] = f"unexpected_error: {exc}"
        return result


def _cleanup_worktree_on_abort(wt_path: str) -> None:
    """Best-effort cleanup of a worktree on foreign-file abort.  NEVER raises."""
    try:
        if not wt_path or not Path(wt_path).exists():
            return
        # Reset the worktree to HEAD so the branch is clean before GC picks it up
        subprocess.run(
            ["git", "checkout", "--", "."],
            cwd=wt_path, capture_output=True, timeout=30,
        )
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=wt_path, capture_output=True, timeout=30,
        )
        log.info("BUILD: worktree cleanup after abort: %s", wt_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _cleanup_worktree_on_abort(%s): %s", wt_path, exc)


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
            # Pass proposal_id so each proposal in the same lobe+cycle gets its
            # own branch (prevents "branch already exists" on multi-proposal cycles).
            branch = _build_branch_name(lobe, cycle_id, proposal_id=pid)
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
