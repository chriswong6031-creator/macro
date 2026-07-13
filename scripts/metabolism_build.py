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


def _cycle_claimed_files(cycle_id: str, root: Path | None = None,
                         exclude_proposal: str | None = None) -> set[str]:
    """Return the set of target_files already claimed this cycle.

    exclude_proposal: skip rows claimed by this proposal_id (its OWN prior
    claim is not a collision — enables bounded re-attempts, #2295 F3).
    NEVER raises."""
    try:
        rows = _read_claims(root)
        claimed: set[str] = set()
        for row in rows:
            if row.get("cycle_id") != cycle_id:
                continue
            if exclude_proposal and row.get("proposal_id") == exclude_proposal:
                continue
            for f in row.get("target_files") or []:
                claimed.add(str(f))
        return claimed
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._cycle_claimed_files: %s", exc)
        return set()


def _load_park_expiry_days(root: Path | None = None) -> int:
    """Read park_expiry_days from metabolism_budget.yml.  Default=30.  NEVER raises.

    FIX-5: park_expiry_days configures how long a parked construction blocks
    new builds before it auto-releases (mirrors the R-V8-8 tap-expiry pattern).
    """
    try:
        import yaml  # noqa: PLC0415
        r = root or _ROOT
        p = r / "config" / "metabolism_budget.yml"
        if not p.exists():
            return 30
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        v = cfg.get("park_expiry_days", 30)
        return max(1, int(v))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._load_park_expiry_days: %s — default 30", exc)
        return 30


def _park_row_is_expired(row: dict, expiry_days: int) -> bool:
    """Return True if a parked_construction row is older than expiry_days.

    A row without a parseable 'ts' is treated as NOT expired (fail-closed: if
    we cannot read when the park was written, we keep the block active).
    NEVER raises.
    """
    try:
        from datetime import datetime, timezone  # noqa: PLC0415
        ts_raw = str(row.get("ts") or "")
        if not ts_raw:
            return False
        row_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - row_dt).days
        return age_days >= expiry_days
    except Exception:  # noqa: BLE001
        return False  # fail-closed: unreadable ts → treat as not expired


def _is_construction_parked(
    proposal: dict,
    *,
    root: Path | None = None,
) -> bool:
    """Return True when the proposal's lobe+kind+sensor overlaps an active parked construction.

    A parked_construction row in claims.jsonl blocks re-builds of the same
    construction (R-V8-9).  A row with release_grant_id set (written by
    ADJUDICATE) unparks — if any release row exists for a parked proposal,
    the construction is NOT blocked.

    FIX-5: a parked row older than park_expiry_days (from metabolism_budget.yml,
    default 30) is treated as auto-released UNLESS a fresh park row also matches
    (re-parked by a new FALSIFIER_TRIPPED).  The release_grant_id path is always
    checked first; expiry is a safety net for dead-unpark situations.

    Match logic: lobe == lobe AND kind == kind AND sensors have non-empty
    intersection.

    NEVER raises.
    """
    try:
        rows = _read_claims(root)
        prop_lobe = str(proposal.get("lobe") or "").strip()
        prop_kind = str(proposal.get("kind") or "").strip()
        sensor_raw = proposal.get("targets_sensor") or proposal.get("sensor") or ""
        prop_sensors: set[str] = (
            set(sensor_raw) if isinstance(sensor_raw, list)
            else {str(sensor_raw)} if sensor_raw
            else set()
        )

        if not prop_lobe:
            return False  # no lobe = cannot match a parked construction

        expiry_days = _load_park_expiry_days(root)

        # FIX-B3: Expiry must be per-row, not per-pid.  proposal_id is a stable
        # dedup_hash (same construction = same pid across fresh falsifiers), so a
        # construction re-parked by a new falsifier shares the pid of its own
        # expired row.  The old per-pid logic added the pid to expired_pids on
        # seeing the old row, then subtracted it from blocked_pids — wrongly
        # unblocking the construction even though a fresh re-park row also exists.
        #
        # Correct logic: for each matching pid, determine whether that pid is
        # blocked by examining whether its MOST-RECENT matching row is:
        #   - explicitly released (release_grant_id present) → not blocked, OR
        #   - expired (age >= expiry_days) → not blocked (auto-release), OR
        #   - neither → blocked.

        # Collect all matching non-release rows per pid; track explicitly-released pids
        from collections import defaultdict  # noqa: PLC0415
        pid_park_rows: dict[str, list[dict]] = defaultdict(list)
        released_pids: set[str] = set()

        for row in rows:
            if row.get("schema") != "metabolism.parked_construction.v1":
                continue
            pc = row.get("parked_construction") or {}
            row_lobe = str(pc.get("lobe") or "").strip()
            row_kind = str(pc.get("kind") or "").strip()
            row_sensors: set[str] = set(pc.get("sensors") or [])
            row_pid = str(row.get("proposal_id") or "")

            # Lobe must match
            if row_lobe != prop_lobe:
                continue
            # Kind must match (if both non-empty)
            if prop_kind and row_kind and prop_kind != row_kind:
                continue
            # Sensor overlap required (if both have sensors)
            if prop_sensors and row_sensors and not prop_sensors.intersection(row_sensors):
                continue

            if row.get("release_grant_id"):
                # Explicit ADJUDICATE release — highest-priority unpark
                released_pids.add(row_pid)
            else:
                pid_park_rows[row_pid].append(row)

        # A pid is blocked iff:
        #   - NOT explicitly released, AND
        #   - its MOST-RECENT park row is not expired (fresh re-park is active)
        blocked_pids: set[str] = set()
        for pid, matching_rows in pid_park_rows.items():
            if pid in released_pids:
                continue  # explicit release wins
            # Sort by ts descending to find the most-recent park row for this pid
            try:
                matching_rows.sort(
                    key=lambda r: str(r.get("ts") or ""),
                    reverse=True,
                )
            except Exception:  # noqa: BLE001
                pass
            most_recent = matching_rows[0]
            if _park_row_is_expired(most_recent, expiry_days):
                log.info(
                    "BUILD: _is_construction_parked: most-recent park row for "
                    "pid=%s lobe=%s is older than park_expiry_days=%d — "
                    "treating as auto-released",
                    pid, prop_lobe, expiry_days,
                )
            else:
                blocked_pids.add(pid)

        if blocked_pids:
            log.info(
                "BUILD: _is_construction_parked: lobe=%s kind=%s sensors=%s matched "
                "parked pids=%s (released=%s)",
                prop_lobe, prop_kind, prop_sensors, blocked_pids, released_pids,
            )
            return True
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_build._is_construction_parked: %s", exc)
        return False  # fail-open: don't block builds on check error


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
        # Self-claims are NOT collisions (#2295 review F3): claim_proposal runs
        # BEFORE dispatch and claims.jsonl is committed, so on a re-attempt of a
        # failed proposal its own prior claim row must not block it — only a
        # claim by a DIFFERENT proposal is a real collision.
        already = _cycle_claimed_files(cycle_id, root, exclude_proposal=proposal_id)
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

    Covers two command surfaces whose union is complete:
      1. Committed changes (git diff --name-only <base> HEAD)
      2. Everything not yet committed — staged, unstaged modifications,
         untracked, and renames — via git status --porcelain

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


# ── Key-failover helpers (V4 follow-up: revert to a working key instead of
#    stranding the cycle when the chosen key is revoked or rate-limited) ──────

# Env var holding the chosen key's env-var NAME for the bash wrapper below.
_KEY_REF_ENV = "METABOLISM_KEY_REF"

# Failure markers in a failed session's output that indict the KEY itself
# (not the build).  Matched case-insensitively against stderr+stdout ONLY
# when the session exits non-zero.
_AUTH_FAIL_MARKERS = (
    "401", "403", "authentication_error", "permission_error",
    "invalid bearer", "oauth token has expired", "invalid api key",
)
_RATE_FAIL_MARKERS = (
    "429", "529", "rate limit", "rate_limit", "usage limit",
    "quota", "overloaded",
)


def _build_session_cmd(task_prompt: str) -> list[str]:
    """Command for one build session.

    The `claude` CLI authenticates via CLAUDE_CODE_OAUTH_TOKEN, but the chosen
    pool key lives under a different env name (e.g. CLAUDE_CODE_OAUTH_TOKEN_1).
    The bash wrapper maps the NAME held in $METABOLISM_KEY_REF onto
    CLAUDE_CODE_OAUTH_TOKEN via indirect expansion, so the token VALUE never
    transits this module (REDLINE).  The task prompt stays a plain argv
    element — it is never shell-parsed.
    """
    return [
        "bash", "-c",
        'if [ -n "${METABOLISM_KEY_REF:-}" ]; then '
        'export CLAUDE_CODE_OAUTH_TOKEN="${!METABOLISM_KEY_REF}"; fi; '
        'exec "$@"',
        "metabolism-build",
        "claude",
        "--model", _BUILD_SESSION_MODEL,
        "--print",           # non-interactive: print final answer only
        "--dangerously-skip-permissions",  # headless build — no interactive prompts
        "-p", task_prompt,
    ]


def _classify_key_failure(run_result: dict) -> str | None:
    """Classify a FAILED session as key-indicting, or None (build's own fault).

    Returns "auth" (revoked/expired token), "window" (rate/usage limited), or
    None.  A None means: do NOT retry with another key — burning a second key
    on a broken build wastes quota.  NEVER raises.
    """
    try:
        blob = ((run_result.get("stderr") or "") + "\n"
                + (run_result.get("stdout") or "")).lower()
        if any(m in blob for m in _AUTH_FAIL_MARKERS):
            return "auth"
        if any(m in blob for m in _RATE_FAIL_MARKERS):
            return "window"
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _classify_key_failure: %s", exc)
    return None


def _cool_failed_key(cap_id: str, kind: str, root: Path | None = None) -> None:
    """Persist a cooling row for a key that failed ("auth" or "window") so all
    later stages and processes skip it.  NEVER raises."""
    try:
        from engine.neuralweb.key_pool import mark_cooling
        mark_cooling(cap_id, cool_kind=kind, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _cool_failed_key(%s, %s): %s", cap_id, kind, exc)


def _worktree_is_clean(wt_path: str) -> bool:
    """True when the build worktree has no uncommitted changes — the only state
    where a retry with a fresh key is safe (never resume into a half-applied
    tree).  Fail-closed: any error → False (no retry)."""
    try:
        import subprocess
        out = subprocess.run(
            ["git", "-C", str(wt_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=60,
        )
        return out.returncode == 0 and not out.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _worktree_is_clean(%s): %s", wt_path, exc)
        return False


def _journal_dispatch(
    cycle_id: str,
    proposal_id: str,
    record: dict[str, Any],
    *,
    root: Path | None = None,
) -> None:
    """Persist a dispatch record to the cycle journal.

    Terminal status mapping (R-V5-1):
      - record["status"] == "dispatched" | "would_dispatch"  → journal "done"
        (the proposal was successfully launched or dry-run noted)
      - record["status"] in retryable error classes           → journal "failed"
        (the proposal may be re-attempted on the next cycle)
      - record["status"] == "immutable_refusal"               → journal "done"
        (permanently refused; retrying is pointless)
      - record["status"] == "foreign_file_abort"              → journal "failed"
        (parks after one occurrence per _is_dispatch_done; must emit insight row)

    NEVER raises.
    """
    try:
        from scripts.metabolism_journal import finish_stage, _read_journal  # type: ignore[attr-defined]
        stage = f"{_DISPATCH_STAGE_PREFIX}{proposal_id}"
        record_status = record.get("status", "")

        # Permanently claimed: success paths and immutable refusal are "done"
        if record_status in ("dispatched", "would_dispatch", "immutable_refusal"):
            terminal_status = "done"
            note_record = record

        # Audit-reject remediation dispatch (R-V7-7): journal as "audit_remediation"
        # so _is_dispatch_done blocks the normal build path but run_build_lane
        # can still advance the remediation counter.
        elif record_status == "audit_remediation":
            terminal_status = "audit_remediation"
            # Read the prior remediation count and increment it.
            prior_rem_count = 0
            try:
                prior_j = _read_journal(cycle_id, root)
                prior_note = prior_j.get("stages", {}).get(stage, {}).get("note", "")
                if prior_note and prior_note.startswith("{"):
                    prior_data = json.loads(prior_note)
                    prior_rem_count = int(prior_data.get("_remediation_attempts", 0))
            except Exception:  # noqa: BLE001
                pass
            note_record = {**record, "_remediation_attempts": prior_rem_count + 1}

            # Emit the exhausted insight exactly ONCE, at the threshold CROSSING.
            try:
                budget = _load_budget_config(root)
                max_rem = int(budget.get("max_audit_rebuild_attempts", 2))
                new_rem_count = prior_rem_count + 1
                if new_rem_count >= max_rem and prior_rem_count < max_rem:
                    _emit_audit_rebuild_exhausted_insight(
                        cycle_id, proposal_id,
                        pr_number=record.get("pr_number"),
                        findings=record.get("findings") or [],
                        remediation_attempts=new_rem_count,
                        root=root,
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("BUILD: audit-exhausted-insight emit failed (%s) — continuing", exc)

        else:
            # All error classes (session_error, invalid_wt_path, diff_error,
            # foreign_file_abort) are "failed" so the proposal is re-attemptable
            # (bounded by max_build_attempts; foreign_file_abort parks after 1).
            terminal_status = "failed"
            # Increment the failure counter embedded in the note (R-V5-1 tracking).
            # Read the prior note to accumulate: each _journal_dispatch call for a
            # failed record increments _failed_attempts so _is_dispatch_done can count.
            prior_count = 0
            try:
                prior_j = _read_journal(cycle_id, root)
                prior_note = prior_j.get("stages", {}).get(stage, {}).get("note", "")
                if prior_note and prior_note.startswith("{"):
                    prior_data = json.loads(prior_note)
                    prior_count = int(prior_data.get("_failed_attempts", 0))
            except Exception:  # noqa: BLE001
                pass
            note_record = {**record, "_failed_attempts": prior_count + 1}

            # Emit the parked insight exactly ONCE, at the threshold CROSSING
            # (write path) — emitting from the _is_dispatch_done read path
            # would append a duplicate row on every subsequent scan (#2295 F5).
            try:
                budget = _load_budget_config(root)
                max_attempts = int(budget.get("max_build_attempts", 2))
                threshold = 1 if record_status == "foreign_file_abort" else max_attempts
                new_count = prior_count + 1
                if new_count >= threshold and prior_count < threshold:
                    _emit_parked_insight(cycle_id, proposal_id, new_count, root=root)
            except Exception as exc:  # noqa: BLE001
                log.warning("BUILD: parked-insight emit failed (%s) — continuing", exc)

        finish_stage(
            cycle_id, stage, terminal_status,
            note=json.dumps(note_record, separators=(",", ":"), default=str)[:600],
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _journal_dispatch(%s/%s): %s", cycle_id, proposal_id, exc)


def _load_budget_config(root: Path | None = None) -> dict[str, Any]:
    """Load metabolism_budget.yml; returns {} on error.  NEVER raises."""
    try:
        import yaml
        p = (root or _ROOT) / "config" / "metabolism_budget.yml"
        with open(p) as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _load_budget_config: %s", exc)
        return {}


def _emit_parked_insight(
    cycle_id: str,
    proposal_id: str,
    failed_count: int,
    *,
    root: Path | None = None,
) -> None:
    """Emit an insight-bus row when a proposal is permanently parked (R-V5-1).

    NEVER raises.
    """
    try:
        from engine.metabolism.insight_bus import append_row, build_row
        row = build_row(
            emitter="metabolism_build._journal_dispatch",
            kind="dispatched_build_parked",
            severity="high",
            entities=[proposal_id, cycle_id],
            summary=(
                f"Proposal {proposal_id} (cycle {cycle_id}) permanently parked after "
                f"{failed_count} failed dispatch attempts. Operator review required."
            ),
            cycle_id=cycle_id,
        )
        append_row(row, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _emit_parked_insight(%s/%s): %s", cycle_id, proposal_id, exc)


# ── Audit-reject remediation helpers (R-V7-7) ────────────────────────────────

def _find_reject_for_proposal(
    proposal_id: str,
    root: Path | None = None,
) -> dict[str, Any] | None:
    """Scan data/metabolism/audit/*.json for the most-recent reject record for this proposal.

    Returns the record dict if verdict=="reject" AND proposal_id matches, else None.
    Disk-only — no network call.  NEVER raises.
    """
    try:
        r = root or _ROOT
        audit_dir = r / "data" / "metabolism" / "audit"
        if not audit_dir.exists():
            return None
        candidates: list[tuple[str, dict[str, Any]]] = []
        for p in audit_dir.glob("*.json"):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("proposal_id") != proposal_id:
                continue
            if rec.get("verdict") != "reject":
                continue
            candidates.append((rec.get("ts", ""), rec))
        if not candidates:
            return None
        # Return the most-recent reject record (by ISO timestamp sort)
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _find_reject_for_proposal(%s): %s", proposal_id, exc)
        return None


def _emit_audit_rebuild_exhausted_insight(
    cycle_id: str,
    proposal_id: str,
    pr_number: int | None,
    findings: list[str],
    remediation_attempts: int,
    *,
    root: Path | None = None,
) -> None:
    """Emit an insight-bus row when audit-reject rebuild cap is exhausted (R-V7-7).

    NEVER raises.
    """
    try:
        from engine.metabolism.insight_bus import append_row, build_row
        findings_str = "; ".join(findings[:5]) if findings else "(see audit record)"
        row = build_row(
            emitter="metabolism_build._emit_audit_rebuild_exhausted_insight",
            kind="audit_rebuild_exhausted",
            severity="high",
            entities=[proposal_id, cycle_id],
            summary=(
                f"Proposal {proposal_id} (cycle {cycle_id}) exhausted "
                f"{remediation_attempts} audit-reject rebuild attempt(s). "
                f"Draft PR #{pr_number} left for operator review. "
                f"Persistent findings: {findings_str}"
            ),
            evidence_ref=(
                f"data/metabolism/audit/{pr_number}.json" if pr_number else None
            ),
            cycle_id=cycle_id,
        )
        append_row(row, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "BUILD: _emit_audit_rebuild_exhausted_insight(%s/%s): %s",
            cycle_id, proposal_id, exc,
        )


def _read_remediation_attempts(
    cycle_id: str,
    proposal_id: str,
    root: Path | None = None,
) -> int:
    """Read the current _remediation_attempts counter from the journal. NEVER raises."""
    try:
        from scripts.metabolism_journal import _read_journal  # type: ignore[attr-defined]
        stage = f"{_DISPATCH_STAGE_PREFIX}{proposal_id}"
        j = _read_journal(cycle_id, root)
        note = j.get("stages", {}).get(stage, {}).get("note", "")
        if note and note.startswith("{"):
            note_data = json.loads(note)
            return int(note_data.get("_remediation_attempts", 0))
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _read_remediation_attempts(%s/%s): %s", cycle_id, proposal_id, exc)
    return 0


def _read_last_remediated_sha(
    cycle_id: str,
    proposal_id: str,
    root: Path | None = None,
) -> str | None:
    """Read the last-remediated head SHA from the journal note. NEVER raises.

    Returns None if no remediation has been recorded or on any error.
    """
    try:
        from scripts.metabolism_journal import _read_journal  # type: ignore[attr-defined]
        stage = f"{_DISPATCH_STAGE_PREFIX}{proposal_id}"
        j = _read_journal(cycle_id, root)
        note = j.get("stages", {}).get(stage, {}).get("note", "")
        if note and note.startswith("{"):
            note_data = json.loads(note)
            sha = note_data.get("_last_remediated_sha")
            return str(sha) if sha else None
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _read_last_remediated_sha(%s/%s): %s", cycle_id, proposal_id, exc)
    return None


def _write_last_remediated_sha(
    cycle_id: str,
    proposal_id: str,
    head_sha: str,
    *,
    root: Path | None = None,
) -> None:
    """Persist the last-remediated head SHA into the journal note. NEVER raises.

    This enables the idempotency guard in run_build_lane without a network call:
    after a remediation fix is dispatched, the reject record's head SHA is stored
    here.  On the next cycle, if _find_reject_for_proposal returns the same SHA,
    we know it was already remediated (fix pushed → SHA changes → no match → clean).
    """
    try:
        from scripts.metabolism_journal import _read_journal, finish_stage  # type: ignore[attr-defined]
        stage = f"{_DISPATCH_STAGE_PREFIX}{proposal_id}"
        j = _read_journal(cycle_id, root)
        note = j.get("stages", {}).get(stage, {}).get("note", "")
        try:
            note_data = json.loads(note) if (note and note.startswith("{")) else {}
        except Exception:  # noqa: BLE001
            note_data = {}
        note_data["_last_remediated_sha"] = head_sha
        finish_stage(
            cycle_id, stage, "audit_remediation",
            note=json.dumps(note_data, separators=(",", ":"), default=str)[:600],
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _write_last_remediated_sha(%s/%s): %s", cycle_id, proposal_id, exc)


def _is_dispatch_done(cycle_id: str, proposal_id: str, root: Path | None = None) -> bool:
    """Return True if this proposal has already been dispatched (or is in-flight) this cycle.

    Idempotency check — prevents double-dispatch on retry.

    Logic (R-V5-1 + R-V5-2 + R-V7-7):
      - "done": permanently claimed.  Old schema "done" rows still claim (backward-compat).
      - "running": claimed IF the started_at is fresh (within stale_running_ttl_hours);
        a stale "running" marker (crashed runner) is treated as NOT claimed.
      - "failed": NOT claimed, BUT bounded — count prior "failed" rows for this stage;
        when count >= max_build_attempts → permanently parked (emit insight bus row,
        return True).
      - "immutable_refusal" journaled as "done" → permanently claimed already.
      - "foreign_file_abort" journaled as "failed" → parks after ONE "failed" row
        (the note encodes "foreign_file_abort"; a single failed foreign-abort → parked).
      - "audit_remediation": an audit-reject rebuild was dispatched — re-dispatchable
        if remediation_attempts < max_audit_rebuild_attempts; parks when exhausted.

    NEVER raises.
    """
    try:
        from scripts.metabolism_journal import _read_journal  # type: ignore[attr-defined]
        from datetime import datetime, timezone, timedelta
        stage = f"{_DISPATCH_STAGE_PREFIX}{proposal_id}"
        j = _read_journal(cycle_id, root)
        stage_rec = j.get("stages", {}).get(stage, {})
        status = stage_rec.get("status")

        # --- "done" (including immutable_refusal path): permanently claimed ---
        if status == "done":
            return True

        # --- "running": claimed only when the marker is fresh (R-V5-2) ---
        if status == "running":
            budget = _load_budget_config(root)
            ttl_hours = float(budget.get("stale_running_ttl_hours", 3))
            started_at_str = stage_rec.get("started_at", "")
            if started_at_str:
                try:
                    if started_at_str.endswith("Z"):
                        started_at_str = started_at_str[:-1] + "+00:00"
                    started_at = datetime.fromisoformat(started_at_str).astimezone(timezone.utc)
                    age = datetime.now(timezone.utc) - started_at
                    if age > timedelta(hours=ttl_hours):
                        # Stale running marker — treat as not claimed (re-attemptable)
                        log.warning(
                            "BUILD: stale 'running' marker for %s/%s (age=%.1fh > ttl=%.1fh) "
                            "— treating as not claimed",
                            cycle_id, proposal_id, age.total_seconds() / 3600, ttl_hours,
                        )
                        return False
                except Exception as exc:  # noqa: BLE001
                    log.warning("BUILD: _is_dispatch_done: started_at parse error: %s", exc)
            # Fresh (or unparseable — fail-safe: treat as claimed to prevent double-dispatch)
            return True

        # --- "failed": count attempts; park when exhausted (R-V5-1) ---
        if status == "failed":
            # Check if the last failure was a foreign_file_abort → park after 1
            note = stage_rec.get("note", "")
            try:
                note_data = json.loads(note) if note.startswith("{") else {}
            except Exception:  # noqa: BLE001
                note_data = {}
            is_foreign_abort = note_data.get("status") == "foreign_file_abort"

            # Count all "failed" journal rows for this stage across all cycle journals
            # (the stage key is proposal-scoped, so we count in this cycle's record).
            # For simplicity: count consecutive failed rows for this stage.
            # Since finish_stage OVERWRITES the stage record, we count by reading
            # all journal rows that match this stage and are "failed".
            # Efficient approach: a single "failed" status record means at least 1 failure.
            # We use a separate counter key appended to the note to track attempts.
            try:
                failed_count = int(note_data.get("_failed_attempts", 1))
            except Exception:  # noqa: BLE001
                failed_count = 1

            budget = _load_budget_config(root)
            max_attempts = int(budget.get("max_build_attempts", 2))

            # foreign_file_abort parks after 1 occurrence; others park after max_attempts
            park_threshold = 1 if is_foreign_abort else max_attempts

            if failed_count >= park_threshold:
                log.warning(
                    "BUILD: proposal %s/%s permanently parked after %d failed attempt(s) "
                    "(threshold=%d, is_foreign_abort=%s)",
                    cycle_id, proposal_id, failed_count, park_threshold, is_foreign_abort,
                )
                # (insight row already emitted at the write-time threshold
                #  crossing in _journal_dispatch — no emission on reads, #2295 F5)
                return True  # permanently parked

            # Under the threshold — re-attemptable
            log.info(
                "BUILD: proposal %s/%s has %d failed attempt(s) (max=%d) — re-attemptable",
                cycle_id, proposal_id, failed_count, max_attempts,
            )
            return False

        # --- "audit_remediation": audit-reject rebuild was dispatched (R-V7-7) ---
        # This status is journaled each time a remediation rebuild is dispatched.
        # We treat it as done (claimed) so the normal build path doesn't double-dispatch.
        # run_build_lane handles the remediation path BEFORE calling _is_dispatch_done.
        if status == "audit_remediation":
            return True

        # No journal entry or unknown status → not claimed
        return False

    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: _is_dispatch_done(%s/%s): %s", cycle_id, proposal_id, exc)
        return False


def _build_session_task_prompt(
    proposal: dict[str, Any],
    wt_path: str,
    branch: str,
    cycle_id: str,
    target_files: list[str] | None = None,
    remediation: dict[str, Any] | None = None,
) -> str:
    """Build the task prompt injected into the headless build session.

    The prompt is the sole task specification the session receives.
    target_files, when given, is the RESOLVED allow-list that the foreign-file
    containment check enforces — the prompt must describe the same list the
    diff check will apply, so they cannot silently diverge.

    remediation, when given, must contain {findings: list[str], rationale: str}.
    A PRIOR AUDIT REJECTION block is prepended to the prompt so the build
    session fixes the auditor's findings (R-V7-7).

    NEVER raises.
    """
    pid = proposal.get("proposal_id", "unknown")
    title = proposal.get("title", "")
    rationale = proposal.get("rationale", "")
    if target_files is None:
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

    # Build the optional prior-audit-rejection block (R-V7-7).
    # Prepended so the build session sees it before the proposal spec.
    remediation_block = ""
    if remediation and isinstance(remediation, dict):
        try:
            rem_rationale = str(remediation.get("rationale") or "").strip()
            rem_findings = [str(f) for f in (remediation.get("findings") or [])]
            findings_lines = (
                "\n".join(f"  - {f}" for f in rem_findings) or "  (see audit record)"
            )
            remediation_block = (
                f"PRIOR AUDIT REJECTION — you MUST fix these before this can merge:\n"
                f"{rem_rationale}\n"
                f"FINDINGS:\n"
                f"{findings_lines}\n"
                f"Fix EXACTLY these issues. Stay within the same target_files. "
                f"Do not expand scope.\n\n"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("BUILD: _build_session_task_prompt remediation block failed: %s", exc)
            remediation_block = ""

    return (
        f"{remediation_block}"
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
    cycle_id: str | None = None,
    target_files: list[str] | None = None,
    root: Path | None = None,
    dry_run: bool = False,
    remediation: dict[str, Any] | None = None,
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

    Parameters
    ----------
    cycle_id : str | None
        The cycle identifier.  Callers (e.g. run_build_lane) MUST pass this
        explicitly because production proposals emitted by propose.py carry
        cycle_id only at the top-level docket, NOT inside each proposal row.
        Falls back to proposal.get('cycle_id') for callers that embed it.
    target_files : list[str] | None
        The resolved target files for this proposal.  Callers (e.g. run_build_lane)
        MUST pass the resolved list because the placeholder computed at claim time
        is never written back into the proposal row.  Falls back to
        proposal.get('target_files') for callers that embed it.
    remediation : dict | None
        When set, carries {findings: list[str], rationale: str} from the most-recent
        audit reject record.  Passed into _build_session_task_prompt so the
        build session receives a PRIOR AUDIT REJECTION preamble (R-V7-7).

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

    # Thread cycle_id: prefer explicit kwarg (set by run_build_lane from docket top-level),
    # fall back to proposal key (for callers that embed it, e.g. unit tests).
    _cycle_id_resolved = cycle_id if cycle_id is not None else proposal.get("cycle_id")
    resolved_cycle_id = str(_cycle_id_resolved or "")

    # Thread target_files: prefer explicit kwarg (resolved at claim time in run_build_lane),
    # fall back to proposal key.
    if target_files is not None:
        resolved_target_files = [str(f) for f in target_files if f is not None]
    else:
        resolved_target_files = [str(f) for f in (proposal.get("target_files") or []) if f is not None]

    # Fail-closed: a dispatch with no cycle_id produces an unauditable session.
    # Refuse rather than silently run unguarded (no idempotency, no journal).
    if not resolved_cycle_id:
        return {
            "dispatched": False,
            "reason": "no_cycle_id: cannot dispatch without a cycle_id (unauditable session refused)",
            "proposal_id": pid,
        }

    cycle_id = resolved_cycle_id
    target_files_resolved = resolved_target_files
    result: dict[str, Any] = {"dispatched": False, "proposal_id": pid}

    try:
        # ── Step 0: idempotency guard ─────────────────────────────────────────
        if not dry_run and cycle_id and _is_dispatch_done(cycle_id, pid, root=root):
            log.info("BUILD: already dispatched cycle=%s proposal=%s — idempotent skip", cycle_id, pid)
            result["reason"] = "already_dispatched"
            result["idempotent_skip"] = True
            return result

        # ── Step 1: IMMUTABLE-set refusal at dispatch ─────────────────────────
        immutable_hits = _check_immutable_targets(target_files_resolved)
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
                "target_files": target_files_resolved,
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
        task_prompt = _build_session_task_prompt(
            proposal, wt_path, branch, cycle_id,
            target_files=target_files_resolved,
            remediation=remediation,
        )
        cmd = _build_session_cmd(task_prompt)

        # Build env: hand the subprocess the chosen key's env-var NAME via
        # METABOLISM_KEY_REF; the bash wrapper in _build_session_cmd maps it
        # onto CLAUDE_CODE_OAUTH_TOKEN by indirect expansion so the `claude`
        # CLI actually authenticates with the POOL key the dispatcher chose
        # (previously the CLI silently used the legacy single token no matter
        # which key was picked).  The token VALUE never transits this module.
        session_env = {**os.environ, _KEY_REF_ENV: ref_name}

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

        # Record session LAUNCH in the key ledger for window_load spread-accounting
        # (R-V5-3): use outcome="launched" so the quota window counts this slot,
        # but is_cooling's ok-clear logic does NOT fire on a mere launch.
        # outcome="ok" is recorded ONLY after returncode==0 (post-success).
        _record_key_session(cap_id, cycle_id, outcome="launched", root=root)

        # ── Step 6: launch the build session (with key failover) ─────────────
        # When a session fails in a way that indicts the KEY (401/403 auth,
        # 429/529 quota), cool that key in the ledger and retry with the next
        # available pool key — at most once per remaining key, never on other
        # failure kinds (a broken build is not a key problem), and never into
        # a dirty worktree.  This is what keeps a revoked or exhausted key
        # from stranding the whole cycle.
        tried_keys: set[str] = {cap_id}
        while True:
            run_result = _launch_build_subprocess(cmd, session_env, wt_path, timeout_s=1800)
            returncode = run_result.get("returncode", -1)
            log.info(
                "BUILD: session ended proposal=%s rc=%d stdout_len=%d",
                pid, returncode, len(run_result.get("stdout", "")),
            )
            if returncode == 0:
                # Record success AFTER confirmed completion (R-V5-3: ok only post-success)
                _record_key_session(cap_id, cycle_id, outcome="ok", root=root)
                break

            _record_key_session(cap_id, cycle_id, outcome="error", root=root)
            failure_kind = _classify_key_failure(run_result)
            next_cap: str | None = None
            next_ref: str | None = None
            if failure_kind is not None:
                _cool_failed_key(cap_id, failure_kind, root=root)
                if _worktree_is_clean(wt_path):
                    next_cap = _pick_build_key(root=root, exclude=tried_keys)
                    if next_cap is not None:
                        next_ref, _ref_err = _resolve_key_ref(next_cap, root=root)
                        if next_ref is None or not os.environ.get(next_ref, ""):
                            log.warning(
                                "BUILD: fallback key cap=%s unusable (%s) — stopping retries",
                                next_cap, _ref_err or "env absent",
                            )
                            next_cap = None
                else:
                    log.warning(
                        "BUILD: %s failure on key=%s but worktree is dirty — "
                        "not retrying into a half-applied tree",
                        failure_kind, cap_id,
                    )

            if next_cap is None or next_ref is None:
                result["reason"] = f"session_nonzero_rc: {returncode}"
                result["returncode"] = returncode
                result["stderr_snippet"] = run_result.get("stderr", "")[:200]
                if failure_kind is not None:
                    result["key_failure"] = failure_kind
                    result["keys_tried"] = sorted(tried_keys)
                if cycle_id:
                    _journal_dispatch(cycle_id, pid, {"status": "session_error",
                                                       "returncode": returncode,
                                                       "key_failure": failure_kind},
                                      root=root)
                return result

            log.warning(
                "BUILD: key %s failed (%s) — retrying proposal=%s with fallback key %s",
                cap_id, failure_kind, pid, next_cap,
            )
            cap_id = next_cap
            tried_keys.add(cap_id)
            session_env[_KEY_REF_ENV] = next_ref
            # Record launch for next key's quota accounting (not ok — not yet confirmed)
            _record_key_session(cap_id, cycle_id, outcome="launched", root=root)

        # ── Step 7: foreign-file diff check ──────────────────────────────────
        changed_files = _diff_worktree_files(wt_path)
        if changed_files is None:
            # diff failed — fail-closed: cannot verify containment
            result["reason"] = "foreign_file_check_failed: git diff returned None"
            if cycle_id:
                _journal_dispatch(cycle_id, pid, {"status": "diff_error"}, root=root)
            return result

        # Allowed: declared target_files + anything under data/metabolism/
        allowed_targets = set(target_files_resolved)
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

    # R-V5-2: reap stale 'running' markers BEFORE scanning dispatch state, so a
    # crashed prior session's marker is honestly 'failed' and re-attemptable.
    # Runs here (not in the cron GC lane) because THIS lane checks out the
    # branch the journals live on and commits them afterward (#2295 review F2).
    try:
        from scripts.metabolism_gc import sweep_stale_running_markers
        _sweep = sweep_stale_running_markers(root or _ROOT, dry_run=dry_run)
        if _sweep.get("swept"):
            log.info("BUILD: stale-running sweep reaped %d marker(s)", _sweep["swept"])
    except Exception as exc:  # noqa: BLE001
        log.warning("BUILD: stale-running sweep failed (%s) — continuing", exc)

    results: list[dict[str, Any]] = []
    try:
        dp = Path(docket_path)
        if not dp.exists():
            log.warning("BUILD: docket not found: %s", dp)
            return results

        docket = json.loads(dp.read_text(encoding="utf-8"))
        proposals = docket.get("proposals") or []
        lobe = docket.get("lobe", "unknown")

        # ── R-V9-9: sort by attention dispatch priority before iterating ─────
        # Stable-sort by (dispatch_priority, original_index) so FOCUS lobes
        # are dispatched first, adjudication order is preserved within a band,
        # and ZERO rows are dropped.  Guarded: any failure leaves order unchanged.
        try:
            from engine.metabolism import attention as _att_build  # noqa: PLC0415
            _keyed: list[tuple[int, int, dict[str, Any]]] = []
            for _orig_idx, _prop in enumerate(proposals):
                _prop_lobe = str(_prop.get("lobe") or lobe)
                try:
                    _prio = _att_build.dispatch_priority(_prop_lobe, root=root)
                except Exception:  # noqa: BLE001
                    _prio = 1  # STANDARD default
                _keyed.append((_prio, _orig_idx, _prop))
            _keyed.sort(key=lambda t: (t[0], t[1]))
            proposals = [t[2] for t in _keyed]
            _order_summary = " ".join(
                f"{t[2].get('lobe', lobe)}:{t[2].get('proposal_id', '?')}"
                for t in _keyed
            )
            log.info("BUILD: dispatch order (attention): %s", _order_summary)
        except Exception as _sort_exc:  # noqa: BLE001
            log.warning(
                "BUILD: attention dispatch sort failed (%s) — using adjudication order",
                _sort_exc,
            )

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

            # Step 1b: Parked-construction check (R-V8-9).
            # If the proposal's lobe+kind+sensor combination is parked (a prior
            # FALSIFIER_TRIPPED clean-overfit appended a parked_construction row),
            # skip this proposal unless a release_grant_id unparks it.
            if _is_construction_parked(prop, root=root):
                per["status"] = "parked_construction"
                per["reason"] = (
                    "construction parked by a prior FALSIFIER_TRIPPED clean-overfit "
                    "(R-V8-9); release requires an ADJUDICATE grant"
                )
                log.info(
                    "BUILD: proposal=%s skipped — construction parked (R-V8-9)", pid,
                )
                results.append(per)
                continue

            # Step 1c: Audit-reject remediation check (R-V7-7).
            # Before the normal build path, check if the proposal has an open
            # unremediated audit reject.  If so, this cycle should fix it, not
            # re-run from scratch.
            reject_rec = _find_reject_for_proposal(pid, root=root)
            if reject_rec is not None:
                reject_head_sha = str(reject_rec.get("head_sha") or "")
                # Idempotency: has this reject already been remediated?
                # We detect that by comparing the reject record's head_sha against
                # the last-remediated SHA stored in the journal note.
                last_rem_sha = _read_last_remediated_sha(cycle_id, pid, root=root)
                already_remediated = (
                    last_rem_sha is not None and last_rem_sha == reject_head_sha
                )
                if already_remediated:
                    # Reject head SHA was already remediated (fix pushed, new SHA
                    # expected next cycle from audit re-run). Normal build path.
                    log.info(
                        "BUILD: proposal=%s audit-reject already remediated (sha=%s) — normal path",
                        pid, reject_head_sha,
                    )
                    reject_rec = None
                else:
                    # Live audit reject — read remediation_attempts counter.
                    rem_attempts = _read_remediation_attempts(cycle_id, pid, root=root)
                    budget = _load_budget_config(root)
                    max_rem = int(budget.get("max_audit_rebuild_attempts", 2))

                    if rem_attempts >= max_rem:
                        # Exhausted — park the proposal.
                        log.warning(
                            "BUILD: proposal=%s audit-reject remediation exhausted "
                            "(%d/%d) — parking, leaving PR for operator",
                            pid, rem_attempts, max_rem,
                        )
                        per["status"] = "audit_rebuild_exhausted"
                        per["reason"] = (
                            f"audit-reject remediation exhausted after {rem_attempts} attempts; "
                            f"PR left for operator review"
                        )
                        per["reject_record"] = reject_rec
                        # Insight already emitted at threshold crossing in _journal_dispatch;
                        # journal a terminal "done" so the proposal is not re-attempted.
                        _journal_dispatch(
                            cycle_id, pid,
                            {
                                "status": "audit_remediation",
                                "action": "exhausted",
                                "remediation_attempts": rem_attempts,
                                "pr_number": reject_rec.get("pr_number"),
                                "findings": reject_rec.get("findings") or [],
                            },
                            root=root,
                        )
                        results.append(per)
                        continue

                    # Attempts remaining — dispatch a remediation rebuild.
                    log.info(
                        "BUILD: proposal=%s dispatching audit-reject remediation "
                        "(attempt %d/%d, reject_sha=%s)",
                        pid, rem_attempts + 1, max_rem, reject_head_sha,
                    )
                    per["remediation_attempt"] = rem_attempts + 1
                    per["reject_record"] = reject_rec

                    # Re-use the SAME branch so the fix commits to the existing open PR.
                    branch = _build_branch_name(lobe, cycle_id, proposal_id=pid)
                    # For the worktree: try to use the existing one if it already exists,
                    # else create a new one off origin/main (the session will see the
                    # existing PR branch code by checking it out).
                    wt_result = _create_build_worktree(branch, root=root, dry_run=dry_run)
                    per["worktree"] = wt_result
                    wt_path = wt_result.get("wt_path") or ""

                    # Claim target_files (self-claim exclusion prevents blocking own retry).
                    prop_target_files = [str(f) for f in (prop.get("target_files") or [])]
                    if not prop_target_files:
                        prop_target_files = [f"data/metabolism/build/{pid}"]
                    claim = claim_proposal(
                        cycle_id, pid, lobe, prop_target_files, root=root, dry_run=dry_run,
                    )
                    per["claim"] = claim

                    remediation_directive = {
                        "findings": reject_rec.get("findings") or [],
                        "rationale": str(reject_rec.get("rationale") or ""),
                    }
                    cap_id = _pick_build_key(root=root)
                    session = _dispatch_build_session(
                        prop, wt_path, branch, cap_id,
                        cycle_id=cycle_id, target_files=prop_target_files,
                        root=root, dry_run=dry_run,
                        remediation=remediation_directive,
                    )
                    per["session"] = session

                    # Journal the remediation dispatch (increments counter, may emit
                    # exhausted insight at threshold crossing).
                    _journal_dispatch(
                        cycle_id, pid,
                        {
                            "status": "audit_remediation",
                            "action": "dispatched",
                            "remediation_attempts": rem_attempts + 1,
                            "pr_number": reject_rec.get("pr_number"),
                            "reject_head_sha": reject_head_sha,
                            "findings": reject_rec.get("findings") or [],
                        },
                        root=root,
                    )
                    # Record the last-remediated SHA so next cycle won't re-fire for
                    # the same reject record (idempotency guard, no network call).
                    _write_last_remediated_sha(
                        cycle_id, pid, reject_head_sha, root=root,
                    )

                    # No new draft PR needed — we committed to the existing PR branch.
                    per["pr"] = {"stub": True, "reason": "remediation_fix_to_existing_pr"}
                    per["status"] = "audit_remediation_dispatched"
                    results.append(per)
                    _gc_worktree(branch, root=root)
                    continue

            # ── Normal (non-remediation) build path ─────────────────────────────
            # Step 2: claim target_files
            prop_target_files = [str(f) for f in (prop.get("target_files") or [])]
            if not prop_target_files:
                # Use a placeholder if no target_files declared (permissive)
                prop_target_files = [f"data/metabolism/build/{pid}"]

            claim = claim_proposal(
                cycle_id, pid, lobe, prop_target_files, root=root, dry_run=dry_run,
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

            # Step 4: dispatch build session.
            # Thread cycle_id (from docket top-level, NOT in proposal rows) and
            # prop_target_files (resolved above, NOT written back into prop) as
            # explicit kwargs so _dispatch_build_session has them for idempotency,
            # pre-launch running-marker, journal audit, and foreign-file containment.
            cap_id = _pick_build_key(root=root)
            session = _dispatch_build_session(
                prop, wt_path, branch, cap_id,
                cycle_id=cycle_id, target_files=prop_target_files,
                root=root, dry_run=dry_run,
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


def _pick_build_key(root: Path | None = None,
                    exclude: set[str] | None = None) -> str | None:
    """Pick a build key via the dispatcher. NEVER raises."""
    try:
        from scripts.metabolism_dispatch import pick_key
        return pick_key(stage="build", root=root, notify_on_freeze=False,
                        exclude=exclude)
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
