"""scripts/metabolism_audit.py — AUDIT stage entrypoint (R-V7-1..6).

Reviews each build-lane draft PR for the cycle using a deterministic
containment re-check + an adversarial Opus code review, then writes an audit
record and governance event. The merge lane's _audit_approved() gate reads
the record to decide whether the PR may merge.

GUARD ORDER (fail-closed; NEVER raises; always exits 0):
  1. metabolism_guard.is_paused()  → clean no-op exit 0
  2. Discover build-lane draft PRs for the cycle.
  3. For each PR: resolve its proposal, fetch diff + head SHA, call audit_pr().
  4. Idempotent: skip PRs already audited at the SAME head SHA.

Modes:
  --scan        (cron default) audit ALL build-lane draft PRs for recent cycles
  --pr-number N audit a single PR (must supply --cycle-id)
  --cycle-id    required with --pr-number; also used to filter in --scan

Usage:
    python -m scripts.metabolism_audit --scan [--root <path>]
    python -m scripts.metabolism_audit --pr-number 123 --cycle-id <id> [--root <path>]

Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_audit")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# ── Pause guard ────────────────────────────────────────────────────────────────

def _is_paused() -> bool:
    """Return True unless AUTONOMY_PAUSED is the exact string 'false'. NEVER raises."""
    try:
        from scripts.metabolism_guard import is_paused  # type: ignore[import]
        return is_paused()
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._is_paused: %s — treating as paused", exc)
        return True


# ── GitHub helpers ─────────────────────────────────────────────────────────────

def _list_build_draft_prs(cycle_id: str) -> list[dict[str, Any]]:
    """List DRAFT PRs from the build lane for this cycle. NEVER raises."""
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--state", "open",
                "--draft",
                "--search", "head:metabolism/build-",
                "--json", "number,headRefName,title,headRefOid",
                "--limit", "50",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.warning("metabolism_audit._list_build_draft_prs: gh failed: %s", result.stderr[:200])
            return []
        prs = json.loads(result.stdout or "[]")
        return [pr for pr in prs if cycle_id in (pr.get("headRefName") or "")]
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._list_build_draft_prs: %s", exc)
        return []


def _get_pr_diff(pr_number: int) -> str | None:
    """Fetch the unified diff for a PR via gh pr diff. NEVER raises."""
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(pr_number), "--patch"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.warning("metabolism_audit._get_pr_diff #%d: gh failed: %s",
                        pr_number, result.stderr[:200])
            return None
        return result.stdout or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._get_pr_diff #%d: %s", pr_number, exc)
        return None


def _get_pr_head_sha(pr_number: int) -> str | None:
    """Fetch the current head SHA for a PR. NEVER raises."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "headRefOid"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "{}")
        return data.get("headRefOid") or None
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._get_pr_head_sha #%d: %s", pr_number, exc)
        return None


# ── Proposal resolution (mirrors metabolism_merge._resolve_proposal_id_for_branch) ──

def _load_docket(cycle_id: str, root: Path) -> dict[str, Any]:
    """Load docket for cycle_id from data/metabolism/dockets/. NEVER raises."""
    try:
        p = root / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._load_docket(%s): %s", cycle_id, exc)
        return {}


def _resolve_proposal_for_branch(
    pr_branch: str,
    cycle_id: str,
    root: Path,
) -> dict[str, Any] | None:
    """Resolve the proposal dict for a build-lane PR branch. NEVER raises.

    Mirrors metabolism_merge._resolve_proposal_id_for_branch exactly:
    uses claims.jsonl first (authoritative), then docket lobe fallback.
    Returns the full proposal dict or None.
    """
    try:
        from scripts.metabolism_merge import _resolve_proposal_id_for_branch  # type: ignore[import]

        docket = _load_docket(cycle_id, root)
        if not docket:
            return None

        prop_index = {
            str(p.get("proposal_id") or ""): p
            for p in (docket.get("proposals") or [])
            if p.get("proposal_id")
        }
        docket_path = root / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"
        pid = _resolve_proposal_id_for_branch(pr_branch, cycle_id, docket, docket_path, root=root)
        if pid is None:
            return None
        return prop_index.get(pid)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._resolve_proposal_for_branch: %s", exc)
        return None


# ── Audit record idempotency check ────────────────────────────────────────────

def _already_audited(pr_number: int, head_sha: str, root: Path) -> bool:
    """Return True if a matching audit record exists for (pr_number, head_sha). NEVER raises."""
    try:
        audit_path = root / "data" / "metabolism" / "audit" / f"{pr_number}.json"
        if not audit_path.exists():
            return False
        record = json.loads(audit_path.read_text(encoding="utf-8"))
        return record.get("head_sha") == head_sha
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._already_audited #%d: %s", pr_number, exc)
        return False


# ── Recent cycle discovery (for scan mode) ────────────────────────────────────

# F3 bound: max age for propose-* branch discovery in scan mode.  Branches
# whose cycle_id date prefix is older than this are skipped — bounding the scan
# regardless of whether the gc reaper has run yet.
_DISCOVER_MAX_AGE_DAYS = 30


def _parse_cycle_date(cycle_id: str) -> datetime | None:
    """Extract a UTC datetime from a date-prefixed cycle_id (YYYY-MM-DD...).

    Returns None if no parseable date is found.  NEVER raises.
    """
    try:
        for i in range(min(len(cycle_id), 20)):
            candidate = cycle_id[i:i + 10]
            if len(candidate) < 10:
                break
            try:
                return datetime.strptime(candidate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
    except Exception:  # noqa: BLE001
        return None


def _discover_recent_cycle_ids() -> list[str]:
    """Discover cycle IDs from open metabolism/propose-* and metabolism/build-* branches.

    F3 max-age filter: cycle IDs whose date prefix is older than
    _DISCOVER_MAX_AGE_DAYS are excluded from the scan — bounding discovery
    even when the gc propose-branch reaper has not run yet.

    NEVER raises. Returns a deduplicated list (most recent first heuristic).
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin",
             "refs/heads/metabolism/propose-*",
             "refs/heads/metabolism/build-*"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return []
        now = datetime.now(timezone.utc)
        max_age = timedelta(days=_DISCOVER_MAX_AGE_DAYS)
        cycle_ids: list[str] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            ref = parts[1]
            # metabolism/propose-<cycle_id> or metabolism/build-<lobe>-<cycle_id>
            if "/propose-" in ref:
                cid = ref.rsplit("/propose-", 1)[-1]
            elif "/build-" in ref:
                # build-<lobe>-<cycle_id> — cycle id is after last known segment
                # Convention: cycle_id starts with "cycle-" or a date-like prefix
                # Take the last 'cycle-...' segment
                segs = ref.split("/build-", 1)[-1].split("-")
                # Find "cycle" marker
                try:
                    idx = segs.index("cycle")
                    cid = "-".join(segs[idx:])
                except ValueError:
                    continue
            else:
                continue
            if not cid or cid in seen:
                continue
            # Max-age filter: skip cycles whose date prefix is too old.
            cycle_date = _parse_cycle_date(cid)
            if cycle_date is not None and (now - cycle_date) > max_age:
                log.info(
                    "metabolism_audit._discover_recent_cycle_ids: %s is >%dd old — skipping",
                    cid, _DISCOVER_MAX_AGE_DAYS,
                )
                continue
            seen.add(cid)
            cycle_ids.append(cid)
        return cycle_ids
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._discover_recent_cycle_ids: %s", exc)
        return []


# ── Core scan logic ────────────────────────────────────────────────────────────

def _audit_pr_for_cycle(
    pr_number: int,
    pr_branch: str,
    cycle_id: str,
    root: Path,
) -> dict[str, Any]:
    """Audit a single PR. Returns a status dict. NEVER raises."""
    status: dict[str, Any] = {
        "pr_number": pr_number,
        "branch": pr_branch,
        "cycle_id": cycle_id,
        "status": "pending",
    }
    try:
        from engine.metabolism.audit import audit_pr  # type: ignore[import]

        # Get current head SHA
        head_sha = _get_pr_head_sha(pr_number) or ""
        status["head_sha"] = head_sha

        # Idempotent: skip if already audited at this SHA
        if head_sha and _already_audited(pr_number, head_sha, root):
            log.info("metabolism_audit: PR #%d already audited at sha=%s — skip",
                     pr_number, head_sha[:8])
            status["status"] = "already_audited"
            return status

        # Resolve proposal
        proposal = _resolve_proposal_for_branch(pr_branch, cycle_id, root)
        if proposal is None:
            log.warning("metabolism_audit: PR #%d no matching proposal — skip", pr_number)
            status["status"] = "no_matching_proposal"
            return status

        # Fetch diff
        diff_text = _get_pr_diff(pr_number)
        if diff_text is None:
            log.warning("metabolism_audit: PR #%d could not fetch diff — skip", pr_number)
            status["status"] = "diff_fetch_failed"
            return status

        # SHA↔diff consistency (#2377 review residual 1): head_sha and the diff
        # come from two separate `gh` calls. If a push landed between them, the
        # recorded SHA would not describe the reviewed diff. Re-read the head
        # AFTER the diff; on any drift, skip and re-audit next cycle on the new
        # SHA — never record a verdict bound to a SHA that isn't the diff we saw.
        head_sha_after = _get_pr_head_sha(pr_number) or ""
        if not head_sha or head_sha_after != head_sha:
            log.warning(
                "metabolism_audit: PR #%d head moved during audit (%s → %s) — "
                "skip; re-audit next cycle", pr_number,
                head_sha[:8] or "?", head_sha_after[:8] or "?")
            status["status"] = "head_moved_during_audit"
            return status

        # Run audit
        record = audit_pr(pr_number, proposal, diff_text, head_sha, root=root)
        status["status"] = "audited"
        status["verdict"] = record.get("verdict")
        log.info("metabolism_audit: PR #%d verdict=%s", pr_number, record.get("verdict"))
        return status

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit._audit_pr_for_cycle #%d: %s", pr_number, exc)
        status["status"] = "error"
        status["error"] = str(exc)
        return status


# ── Main ────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the AUDIT stage. Exit 0 always."""
    parser = argparse.ArgumentParser(
        description="Metabolism V7 AUDIT stage — adversarial PR code review gate"
    )
    parser.add_argument(
        "--scan", action="store_true",
        help="Scan mode: audit all build-lane draft PRs for recent cycles",
    )
    parser.add_argument(
        "--pr-number", type=int, default=None,
        help="Single PR mode: audit this specific PR number",
    )
    parser.add_argument(
        "--cycle-id", default=None,
        help="Cycle ID (required with --pr-number; used to filter in --scan)",
    )
    parser.add_argument(
        "--root", default=None,
        help="Repo root (default: auto-detect)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT

    # ── Gate 1: KILL SWITCH (first action) ──────────────────────────────────
    if _is_paused():
        log.info("metabolism_audit: AUTONOMY_PAUSED — no-op exit 0")
        return 0

    results: list[dict[str, Any]] = []

    try:
        if args.pr_number is not None:
            # Single-PR mode
            if not args.cycle_id:
                log.error("metabolism_audit: --cycle-id required with --pr-number")
                return 0

            pr_branch_result = subprocess.run(
                ["gh", "pr", "view", str(args.pr_number), "--json", "headRefName"],
                capture_output=True, text=True, timeout=30,
            )
            pr_branch = ""
            if pr_branch_result.returncode == 0:
                pr_branch = json.loads(pr_branch_result.stdout or "{}").get("headRefName") or ""

            r = _audit_pr_for_cycle(
                args.pr_number, pr_branch, args.cycle_id, root
            )
            results.append(r)

        else:
            # Scan mode (default)
            cycle_ids: list[str] = []
            if args.cycle_id:
                cycle_ids = [args.cycle_id]
            else:
                cycle_ids = _discover_recent_cycle_ids()

            if not cycle_ids:
                log.info("metabolism_audit: no open cycle branches found — clean no-op")
                return 0

            for cycle_id in cycle_ids:
                draft_prs = _list_build_draft_prs(cycle_id)
                log.info("metabolism_audit: cycle=%s found %d draft PR(s)",
                         cycle_id, len(draft_prs))
                for pr in draft_prs:
                    pr_number = pr.get("number")
                    pr_branch = pr.get("headRefName", "")
                    if pr_number is None:
                        continue
                    r = _audit_pr_for_cycle(pr_number, pr_branch, cycle_id, root)
                    results.append(r)

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_audit.main: unexpected error: %s", exc)

    log.info("metabolism_audit: done — %d PR(s) processed", len(results))
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
